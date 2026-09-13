"""Rule-based bright-target detector: a transparent stand-in for the trained model.

Used for the thin slice (Gate G2), the CI integration test and machines without trained weights.
It finds compact regions that are much brighter than the local seabed and labels them
``debris_other``. It is **not** a trained classifier and reports a low, contrast-based score;
reports record it as ``classical-bright-target@0.1.0`` so it can't be mistaken for YOLO11-seg.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from sonarsentinel.detect.base import RawDetection


class BrightTargetDetector:
    """Bright compact regions above a median-filtered background."""

    model_version = "classical-bright-target@0.1.0"

    def __init__(
        self,
        *,
        min_contrast: int = 100,
        min_area_px: int = 12,
        max_area_fraction: float = 0.05,
        background_window: int = 31,
        cls: str = "debris_other",
    ) -> None:
        self.min_contrast = min_contrast
        self.min_area_px = min_area_px
        self.max_area_fraction = max_area_fraction
        self.background_window = background_window | 1
        self.cls = cls

    def predict(self, tiles: Sequence[npt.NDArray[np.uint8]]) -> list[list[RawDetection]]:
        return [self._predict_one(tile) for tile in tiles]

    def _predict_one(self, tile: npt.NDArray[np.uint8]) -> list[RawDetection]:
        import cv2

        # Lee-despeckled channel: after gain stretching, raw speckle forms bright clusters.
        raw = tile[..., 1] if tile.ndim == 3 else tile
        raw = np.ascontiguousarray(raw, dtype=np.uint8)
        # Median at quarter resolution: a window ~4× wider than on the full image, so objects that
        # fill most of a small window don't become their own "background".
        h, w = raw.shape
        small = cv2.resize(raw, (max(w // 4, 1), max(h // 4, 1)), interpolation=cv2.INTER_AREA)
        background = cv2.resize(
            cv2.medianBlur(small, self.background_window), (w, h), interpolation=cv2.INTER_LINEAR
        )
        contrast = raw.astype(np.int16) - background.astype(np.int16)
        # No morphological closing: it joined isolated noise pixels into low-contrast blobs.
        # On processed synthetic lines the despeckled noise tail reaches ~80 above background
        # (99.9th percentile) while real targets sit well above 100.
        candidate = (contrast >= self.min_contrast).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
        max_area = self.max_area_fraction * raw.size
        found = []
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < self.min_area_px or area > max_area:
                continue
            mask = labels[y : y + h, x : x + w] == i
            peak = float(contrast[y : y + h, x : x + w][mask].mean())
            score = float(np.clip(0.2 + peak / 400.0, 0.0, 0.6))
            found.append(RawDetection(self.cls, round(score, 4), (x, y, x + w, y + h), mask))
        return found
