"""YOLO11-seg detector adapter (M1, ADR-002) with optional SAHI sliced inference (ST-052).

Tiles are the pipeline's 3-channel uint8 images in the same channel order that
``ml/datasets/prepare_yolo.py`` writes to disk for training, so training and inference see
identical inputs. Masks come from the model's polygons, rasterised inside each box.
Requires the ML dependencies (``backend/requirements-ml.txt``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.detect.base import DETECTOR_CLASSES, RawDetection
from sonarsentinel.errors import ModelsNotLoadedError

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def registry_version(weights: Path) -> str:
    """``<name>@<version>`` from ``models/detector/<name>/<version>/best.pt``, else ``0.0.0``."""
    version = weights.parent.name if _SEMVER.match(weights.parent.name) else "0.0.0"
    name = weights.parent.parent.name if _SEMVER.match(weights.parent.name) else weights.stem
    return f"{re.sub(r'[^A-Za-z0-9._-]', '-', name) or 'yolo'}@{version}"


def polygon_mask(
    polygon: npt.NDArray[Any], box: tuple[int, int, int, int]
) -> npt.NDArray[np.bool_]:
    """Rasterise an image-coordinate polygon into a mask aligned with ``box``."""
    import cv2

    x1, y1, x2, y2 = box
    mask = np.zeros((max(y2 - y1, 1), max(x2 - x1, 1)), np.uint8)
    if len(polygon) >= 3:
        pts = np.rint((np.asarray(polygon, np.float64) - [x1, y1]) * 16).astype(np.int32)
        cv2.fillPoly(mask, [pts], 1, shift=4)
    if not mask.any():
        mask[:] = 1  # degenerate polygon: fall back to the box
    return mask.astype(bool)


RUNTIMES = ("auto", "torch", "onnxruntime")


def resolve_runtime_weights(weights: Path, runtime: str, *, onnxruntime_available: bool) -> Path:
    """Weights file for ``detection.runtime`` (ADR-018 §10).

    ``auto`` uses ``<weights>.onnx`` next to the configured file when it exists and ONNX Runtime is
    installed, otherwise the configured file; ``torch`` uses the ``.pt`` file; ``onnxruntime``
    requires the ``.onnx`` file.
    """
    if runtime not in RUNTIMES:
        from sonarsentinel.errors import ValidationError

        raise ValidationError(f"Unknown detection runtime: {runtime}", supported=list(RUNTIMES))
    onnx = weights.with_suffix(".onnx")
    if runtime == "torch":
        return weights.with_suffix(".pt") if weights.suffix == ".onnx" else weights
    if runtime == "onnxruntime":
        if not onnxruntime_available:
            raise ModelsNotLoadedError("ONNX Runtime is not installed", runtime=runtime)
        return onnx
    return onnx if onnxruntime_available and onnx.is_file() else weights


class YoloDetector:
    """Ultralytics YOLO11-seg weights (``.pt`` or exported ``.onnx``) or a model YAML (tests)."""

    runtime = "torch-cpu"

    def __init__(
        self,
        weights: str | Path,
        *,
        imgsz: int = 640,
        conf: float = 0.20,
        sahi: bool = False,
        slice_px: int = 512,
        slice_overlap: float = 0.2,
        device: str = "cpu",
        class_names: Sequence[str] = DETECTOR_CLASSES,
    ) -> None:
        path = Path(weights)
        if path.suffix != ".yaml" and not path.is_file():
            raise ModelsNotLoadedError(f"Detector weights not found: {path}", path=str(path))
        from ultralytics import YOLO  # type: ignore[attr-defined, unused-ignore]  # absent in CI

        self.weights = path
        if path.suffix == ".onnx":
            # Exported models don't carry the task; ONNX Runtime executes them (ADR-012, ADR-018).
            self.model: Any = YOLO(str(path), task="segment")
            self.runtime = "onnxruntime-cpu"
        else:
            self.model = YOLO(str(path))
        self.imgsz, self.conf, self.device = imgsz, conf, device
        self.sahi, self.slice_px, self.slice_overlap = sahi, slice_px, slice_overlap
        self.class_names = tuple(class_names)
        self.model_version = registry_version(path)
        self._sahi_model: Any = None

    def _name(self, cls_id: int) -> str:
        return self.class_names[cls_id] if 0 <= cls_id < len(self.class_names) else str(cls_id)

    def predict(self, tiles: Sequence[npt.NDArray[np.uint8]]) -> list[list[RawDetection]]:
        if not tiles:
            return []
        if self.sahi:
            return [self._predict_sliced(t) for t in tiles]
        results = self.model.predict(
            list(tiles), imgsz=self.imgsz, conf=self.conf, device=self.device, verbose=False
        )
        return [self._convert(r) for r in results]

    def _convert(self, result: Any) -> list[RawDetection]:
        out: list[RawDetection] = []
        if result.boxes is None or len(result.boxes) == 0:
            return out
        polygons = result.masks.xy if result.masks is not None else [None] * len(result.boxes)
        h, w = result.orig_shape
        for xyxy, cls_id, score, poly in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.cls.tolist(),
            result.boxes.conf.tolist(),
            polygons,
            strict=True,
        ):
            x1, y1 = max(int(np.floor(xyxy[0])), 0), max(int(np.floor(xyxy[1])), 0)
            x2, y2 = min(int(np.ceil(xyxy[2])), w), min(int(np.ceil(xyxy[3])), h)
            if x2 <= x1 or y2 <= y1:
                continue
            box = (x1, y1, x2, y2)
            mask = polygon_mask(poly, box) if poly is not None else None
            out.append(RawDetection(self._name(int(cls_id)), round(float(score), 4), box, mask))
        return out

    def _predict_sliced(self, tile: npt.NDArray[np.uint8]) -> list[RawDetection]:
        from sahi import AutoDetectionModel
        from sahi.predict import get_sliced_prediction

        if self._sahi_model is None:
            self._sahi_model = AutoDetectionModel.from_pretrained(
                model_type="ultralytics",
                model_path=str(self.weights),
                confidence_threshold=self.conf,
                device=self.device,
                image_size=self.imgsz,
            )
        # SAHI treats numpy input as RGB and flips it before calling Ultralytics.
        result = get_sliced_prediction(
            np.ascontiguousarray(tile[..., ::-1]),
            self._sahi_model,
            slice_height=self.slice_px,
            slice_width=self.slice_px,
            overlap_height_ratio=self.slice_overlap,
            overlap_width_ratio=self.slice_overlap,
            verbose=0,
        )
        h, w = tile.shape[:2]
        out: list[RawDetection] = []
        for pred in result.object_prediction_list:
            x1, y1, x2, y2 = (int(round(v)) for v in pred.bbox.to_xyxy())
            x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, w), min(y2, h)
            if x2 <= x1 or y2 <= y1:
                continue
            mask = None
            if pred.mask is not None and pred.mask.segmentation:
                seg = max(pred.mask.segmentation, key=len)
                mask = polygon_mask(np.asarray(seg, np.float64).reshape(-1, 2), (x1, y1, x2, y2))
            out.append(
                RawDetection(
                    self._name(int(pred.category.id)),
                    round(float(pred.score.value), 4),
                    (x1, y1, x2, y2),
                    mask,
                )
            )
        return out
