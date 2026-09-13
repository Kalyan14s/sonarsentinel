"""Shared helpers for YOLO segmentation labels (``class x1 y1 x2 y2 ...``, normalised 0–1).

Class IDs follow ``ml/datasets/sonar-seg.yaml`` (docs/data/DATASETS.md §7).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

CLASS_IDS = {"shipwreck": 0, "pipe": 1, "cylinder": 2, "ghost_net": 3, "debris_other": 4}


def box_to_polygon(xc: float, yc: float, w: float, h: float) -> list[tuple[float, float]]:
    """YOLO box (centre, size; normalised) → 4 clockwise corners, clipped to the image."""

    def clip(v: float) -> float:
        return min(max(v, 0.0), 1.0)

    x1, x2 = clip(xc - w / 2), clip(xc + w / 2)
    y1, y2 = clip(yc - h / 2), clip(yc + h / 2)
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def format_polygon(class_id: int, points: Sequence[tuple[float, float]], decimals: int = 6) -> str:
    """One YOLO-seg label line."""
    coords = " ".join(f"{x:.{decimals}f} {y:.{decimals}f}" for x, y in points)
    return f"{class_id} {coords}"


def mask_to_polygons(
    mask: np.ndarray, *, min_area_px: int = 16, epsilon_px: float = 1.0
) -> list[list[tuple[float, float]]]:
    """Binary mask → simplified outer contours as normalised polygons (≥ 3 points each)."""
    import cv2

    binary = (np.asarray(mask) > 0).astype(np.uint8)
    h, w = binary.shape
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area_px:
            continue
        approx = cv2.approxPolyDP(contour, epsilon_px, True).reshape(-1, 2)
        if len(approx) < 3:
            continue
        polygons.append([(float(x) / w, float(y) / h) for x, y in approx])
    return polygons
