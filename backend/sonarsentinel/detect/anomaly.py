"""PatchCore anomaly model (M2, ADR-005; ST-053): scores, heatmaps, ``unknown_anomaly`` regions.

Implementation of PatchCore (Roth et al., "Towards Total Recall in Industrial Anomaly Detection",
CVPR 2022) directly in PyTorch: ImageNet ResNet-18 ``layer2`` + ``layer3`` features, 3 × 3
neighbourhood averaging, a coreset memory bank of normal seafloor patches, and nearest-neighbour
distance as the anomaly score. Tiles are the pipeline's 3-channel images, resized to
``input_px`` (256). Written directly instead of through anomalib, whose releases pin specific torch
and lightning versions.

Registry layout: ``models/anomaly/<name>/<version>/{memory_bank.pt, model.json}``; training is
``ml/train_anomaly.py``. Requires the ML dependencies.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.detect.base import RawDetection
from sonarsentinel.errors import ModelsNotLoadedError

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class FeatureExtractor:
    """ResNet-18 layer2 + layer3 patch embeddings (384-D on a 1/8-resolution grid)."""

    def __init__(self, pretrained: bool = True, device: str = "cpu") -> None:
        import torch
        import torchvision

        weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        net = torchvision.models.resnet18(weights=weights).eval().to(device)
        self.stem = torch.nn.Sequential(net.conv1, net.bn1, net.relu, net.maxpool, net.layer1)
        self.layer2, self.layer3 = net.layer2, net.layer3
        self.device = device
        self.mean = torch.tensor(IMAGENET_MEAN, device=device).view(1, 3, 1, 1)
        self.std = torch.tensor(IMAGENET_STD, device=device).view(1, 3, 1, 1)

    def __call__(self, tiles: npt.NDArray[np.uint8]) -> Any:
        """``(N, H, W, 3)`` uint8 → ``(N, 384, H/8, W/8)`` float tensor."""
        import torch
        import torch.nn.functional as F  # noqa: N812

        with torch.no_grad():
            x = torch.from_numpy(np.ascontiguousarray(tiles)).to(self.device)
            x = x.permute(0, 3, 1, 2).float() / 255.0
            x = (x - self.mean) / self.std
            f1 = self.stem(x)
            f2 = self.layer2(f1)
            f3 = self.layer3(f2)
            f3 = F.interpolate(f3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
            feats = torch.cat([f2, f3], dim=1)
            return F.avg_pool2d(feats, kernel_size=3, stride=1, padding=1)


def resize_tiles(tiles: Sequence[npt.NDArray[np.uint8]], size: int) -> npt.NDArray[np.uint8]:
    import cv2

    out = []
    for tile in tiles:
        img = tile if tile.ndim == 3 else np.dstack([tile] * 3)
        if img.shape[:2] != (size, size):
            out.append(np.asarray(cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)))
        else:
            out.append(img)
    return np.stack(out).astype(np.uint8)


def greedy_coreset(
    features: Any, n_select: int, *, projection_dim: int = 128, seed: int = 0
) -> Any:
    """Greedy k-center subset (PatchCore §3.3) on randomly projected features; returns indices."""
    import torch

    n = features.shape[0]
    n_select = max(1, min(n_select, n))
    generator = torch.Generator().manual_seed(seed)
    if features.shape[1] > projection_dim:
        projection = torch.randn(features.shape[1], projection_dim, generator=generator)
        reduced = features @ projection
    else:
        reduced = features
    selected = [int(torch.randint(0, n, (1,), generator=generator))]
    min_dist = torch.cdist(reduced, reduced[selected]).squeeze(1)
    for _ in range(n_select - 1):
        idx = int(torch.argmax(min_dist))
        selected.append(idx)
        min_dist = torch.minimum(min_dist, torch.cdist(reduced, reduced[idx : idx + 1]).squeeze(1))
    return torch.tensor(selected)


def heat_regions(
    heat: npt.NDArray[np.float32],
    pixel_threshold: float,
    *,
    min_area_px: int = 25,
    exclude_boxes: Sequence[tuple[int, int, int, int]] = (),
    max_iou: float = 0.1,
) -> list[RawDetection]:
    """``unknown_anomaly`` regions of an image-sized heatmap above ``pixel_threshold``.

    Regions overlapping a detector box with IoU ≥ ``max_iou`` are left to the detector. The score
    is the peak heat relative to twice the threshold, capped at 1.
    """
    import cv2

    from sonarsentinel.detect.merge import box_iou

    mask = (heat >= pixel_threshold).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < min_area_px:
            continue
        box = (x, y, x + w, y + h)
        if any(box_iou(box, other) >= max_iou for other in exclude_boxes):
            continue
        region = labels[y : y + h, x : x + w] == i
        peak = float(heat[y : y + h, x : x + w][region].max())
        score = float(np.clip(peak / (2.0 * pixel_threshold), 0.0, 1.0))
        out.append(RawDetection("unknown_anomaly", round(score, 4), box, region))
    return out


@dataclass
class AnomalyResult:
    scores: npt.NDArray[np.float32]  # one per tile
    heatmaps: npt.NDArray[np.float32]  # (N, input_px, input_px)


class PatchCoreModel:
    """Memory bank + extractor; scores tiles and extracts anomalous regions."""

    runtime = "torch-cpu"

    def __init__(
        self,
        memory_bank: Any,
        *,
        input_px: int = 256,
        threshold: float | None = None,
        pixel_threshold: float | None = None,
        name: str = "patchcore-seafloor",
        version: str = "0.0.0",
        pretrained: bool = True,
        device: str = "cpu",
    ) -> None:
        self.memory_bank = memory_bank
        self.input_px = input_px
        self.threshold = threshold
        self.pixel_threshold = pixel_threshold if pixel_threshold is not None else threshold
        self.model_version = f"{name}@{version}"
        self.extractor = FeatureExtractor(pretrained=pretrained, device=device)

    @classmethod
    def load(cls, folder: str | Path, device: str = "cpu") -> PatchCoreModel:
        import torch

        path = Path(folder)
        if not (path / "memory_bank.pt").is_file() or not (path / "model.json").is_file():
            raise ModelsNotLoadedError(f"Anomaly model not found in {path}", path=str(path))
        meta = json.loads((path / "model.json").read_text(encoding="utf-8"))
        bank = torch.load(path / "memory_bank.pt", map_location=device)
        return cls(
            bank,
            input_px=meta["input_px"],
            threshold=meta["threshold"],
            pixel_threshold=meta.get("pixel_threshold"),
            name=meta["name"],
            version=meta["version"],
            device=device,
        )

    def save(self, folder: str | Path, extra: dict[str, Any] | None = None) -> None:
        import torch

        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        torch.save(self.memory_bank, path / "memory_bank.pt")
        name, version = self.model_version.split("@")
        meta = {
            "name": name,
            "version": version,
            "input_px": self.input_px,
            "threshold": self.threshold,
            "pixel_threshold": self.pixel_threshold,
            "memory_bank_size": int(self.memory_bank.shape[0]),
            "backbone": "resnet18",
            "layers": ["layer2", "layer3"],
            **(extra or {}),
        }
        (path / "model.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def patch_features(self, tiles: Sequence[npt.NDArray[np.uint8]], batch: int = 16) -> Any:
        """``(N × P, 384)`` patch embeddings for tiles at ``input_px``."""
        import torch

        chunks = []
        resized = resize_tiles(tiles, self.input_px)
        for start in range(0, len(resized), batch):
            feats = self.extractor(resized[start : start + batch])
            chunks.append(feats.permute(0, 2, 3, 1).reshape(-1, feats.shape[1]))
        return torch.cat(chunks)

    def score(self, tiles: Sequence[npt.NDArray[np.uint8]], batch: int = 16) -> AnomalyResult:
        import cv2
        import torch
        import torch.nn.functional as F  # noqa: N812

        resized = resize_tiles(tiles, self.input_px)
        scores, maps = [], []
        with torch.no_grad():
            for start in range(0, len(resized), batch):
                feats = self.extractor(resized[start : start + batch])
                n, c, h, w = feats.shape
                flat = feats.permute(0, 2, 3, 1).reshape(-1, c)
                dist = torch.cat(
                    [
                        torch.cdist(part, self.memory_bank).min(dim=1).values
                        for part in flat.split(4096)
                    ]
                )
                grid = dist.reshape(n, 1, h, w)
                up = (
                    F.interpolate(
                        grid,
                        size=(self.input_px, self.input_px),
                        mode="bilinear",
                        align_corners=False,
                    )
                    .squeeze(1)
                    .cpu()
                    .numpy()
                )
                for heat in up:
                    smooth = cv2.GaussianBlur(heat.astype(np.float32), (0, 0), 4)
                    maps.append(smooth)
                    scores.append(float(smooth.max()))
        return AnomalyResult(np.asarray(scores, np.float32), np.stack(maps).astype(np.float32))

    def regions(
        self,
        heatmap: npt.NDArray[np.float32],
        tile_px: int,
        *,
        min_area_px: int = 25,
        exclude_boxes: Sequence[tuple[int, int, int, int]] = (),
        max_iou: float = 0.1,
    ) -> list[RawDetection]:
        """``unknown_anomaly`` detections where the heatmap exceeds the pixel threshold.

        The heatmap is resized to the tile size; regions overlapping a detector box with IoU ≥
        ``max_iou`` are left to the detector.
        """
        import cv2

        from sonarsentinel.detect.merge import box_iou

        if self.pixel_threshold is None:
            return []
        heat = cv2.resize(heatmap, (tile_px, tile_px), interpolation=cv2.INTER_LINEAR)
        mask = (heat >= self.pixel_threshold).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out = []
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < min_area_px:
                continue
            box = (x, y, x + w, y + h)
            if any(box_iou(box, other) >= max_iou for other in exclude_boxes):
                continue
            region = labels[y : y + h, x : x + w] == i
            peak = float(heat[y : y + h, x : x + w][region].max())
            score = float(np.clip(peak / (2.0 * self.pixel_threshold), 0.0, 1.0))
            out.append(RawDetection("unknown_anomaly", round(score, 4), box, region))
        return out
