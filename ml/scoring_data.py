"""Per-detection scoring data from a YOLO folder split (shared by ST-062…064 scripts).

Runs the detector on every image of a split, matches detections to the ground-truth labels
(IoU ≥ 0.5, one-to-one in score order) and computes the shadow score and the ST-061 feature
vector exactly as the pipeline does. Tiles from ``prepare_yolo.py`` carry no navigation, so the
shadow side is unknown: both directions are scored and the stronger one is kept. Results are
cached as JSON lines so the FP filter, fusion tuning and calibration reuse one detector pass.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # see train_detector.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sonarsentinel.detect.merge import box_iou  # noqa: E402
from sonarsentinel.geo.measure import ImageGeometry, measure_mask  # noqa: E402
from sonarsentinel.scoring.features import FEATURE_NAMES, detection_features  # noqa: E402
from sonarsentinel.scoring.shadow import shadow_score  # noqa: E402

RES_M = 0.10  # ground resolution assumed for the mine-SSS tiles (prepare_yolo.py)


def truth_boxes(label: Path, width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Pixel boxes ``(x1, y1, x2, y2)`` of the YOLO-seg polygons in a label file."""
    boxes = []
    if label.exists():
        for line in label.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 7:
                continue
            xy = np.array([float(v) for v in parts[1:]]).reshape(-1, 2) * [width, height]
            x1, y1 = np.floor(xy.min(axis=0)).astype(int)
            x2, y2 = np.ceil(xy.max(axis=0)).astype(int)
            boxes.append((int(x1), int(y1), int(x2), int(y2)))
    return boxes


def match(
    boxes: list[tuple[int, int, int, int]],
    scores: list[float],
    truths: list[tuple[int, int, int, int]],
    iou: float = 0.5,
) -> list[int]:
    """1 for detections matching an unused ground-truth box at IoU ≥ ``iou`` (score order)."""
    labels = [0] * len(boxes)
    used = [False] * len(truths)
    for i in sorted(range(len(boxes)), key=lambda k: -scores[k]):
        best, best_iou = -1, iou
        for j, truth in enumerate(truths):
            if not used[j] and (value := box_iou(boxes[i], truth)) >= best_iou:
                best, best_iou = j, value
        if best >= 0:
            used[best] = True
            labels[i] = 1
    return labels


def tile_record(image: np.ndarray, det: Any, *, res_m: float = RES_M) -> dict[str, Any]:
    """Detector score, shadow score and features for one detection on a 3-channel tile."""
    grey = np.ascontiguousarray(image[..., 0])
    texture = np.ascontiguousarray(image[..., 2])
    height, width = grey.shape
    mask = det.full_mask()
    x1, y1, _, _ = det.box
    geometry = ImageGeometry(
        ground_res_m=res_m,
        nadir_col=0,
        row_to_ping=np.arange(height, dtype=np.int64),
        heading_deg=np.zeros(height),
    )
    m = measure_mask(mask, geometry, row0=y1, col0=x1)
    shadow = max(
        (
            shadow_score(grey, mask, det.box, nadir_col=col, ground_res_m=res_m, altitude_m=None)
            for col in (0, width)
        ),
        key=lambda s: s.score,
    )
    features = detection_features(
        grey,
        mask,
        det.box,
        cls=det.cls,
        detector_score=float(det.score),
        shadow=shadow,
        length_m=m.length_m,
        width_m=m.width_m,
        area_m2=m.area_m2,
        texture=texture,
    )
    return {
        "cls": det.cls,
        "box": [int(v) for v in det.box],
        "detector": round(float(det.score), 4),
        "shadow": shadow.score,
        "features": features,
    }


def collect(
    data: Path, split: str, weights: Path, *, conf: float = 0.05, imgsz: int = 640
) -> list[dict[str, Any]]:
    """Detections with labels and features for every image of ``split``."""
    import cv2
    from sonarsentinel.detect.yolo import YoloDetector

    detector = YoloDetector(weights, imgsz=imgsz, conf=conf, sahi=False)
    rows: list[dict[str, Any]] = []
    for path in sorted((data / "images" / split).glob("*.png")):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        detections = detector.predict([image])[0]
        truths = truth_boxes(
            data / "labels" / split / f"{path.stem}.txt", image.shape[1], image.shape[0]
        )
        labels = match([d.box for d in detections], [d.score for d in detections], truths)
        for det, label in zip(detections, labels, strict=True):
            rows.append({"image": path.name, "label": label, **tile_record(image, det)})
    return rows


def n_truth_objects(data: Path, split: str) -> int:
    """Ground-truth objects in a split (the AP denominator, missed objects included)."""
    total = 0
    for label in (data / "labels" / split).glob("*.txt"):
        total += sum(
            1 for line in label.read_text(encoding="utf-8").splitlines() if len(line.split()) >= 7
        )
    return total


def save_rows(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8"
    )
    return path


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def feature_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.array([[float(r["features"][name]) for name in FEATURE_NAMES] for r in rows])


def average_precision(
    scores: list[float], labels: list[int], n_positive: int | None = None
) -> float:
    """Non-interpolated AP of a ranking; ``n_positive`` counts missed objects too."""
    y = np.asarray(labels, dtype=float)[np.argsort(-np.asarray(scores, dtype=float), kind="stable")]
    positives = float(y.sum()) if n_positive is None else float(n_positive)
    if positives <= 0:
        return float("nan")
    precision = np.cumsum(y) / np.arange(1, y.size + 1)
    return float((precision * y).sum() / positives)


def auroc(scores: list[float], labels: list[int]) -> float:
    """Area under the ROC curve (Mann–Whitney U with average ranks for ties)."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=int)
    n_pos, n_neg = int(y.sum()), int((1 - y).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="stable")
    ranks = np.empty(s.size, dtype=float)
    sorted_s = s[order]
    i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and sorted_s[j + 1] == sorted_s[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def image_folds(images: list[str], k: int, seed: int = 0) -> np.ndarray:
    """Fold index per row so that all detections of one image share a fold."""
    unique = sorted(set(images))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(unique))
    fold_of = {unique[idx]: pos % k for pos, idx in enumerate(order)}
    return np.array([fold_of[name] for name in images], dtype=int)
