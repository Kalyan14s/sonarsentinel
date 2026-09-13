"""Detector interface shared by every detection model (stage S8).

A detector takes 3-channel uint8 tiles from the preprocessing pipeline and returns, per tile,
:class:`RawDetection` objects in tile pixel coordinates. The pipeline shifts them into chunk
coordinates, merges overlaps (:mod:`sonarsentinel.detect.merge`) and scores them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

#: Classes the detector may output (``unknown_anomaly`` comes from the anomaly model).
DETECTOR_CLASSES = ("shipwreck", "pipe", "cylinder", "ghost_net", "debris_other")


@dataclass(frozen=True)
class RawDetection:
    """One detection before scoring.

    Attributes:
        cls: Class name.
        score: Raw model score in [0, 1].
        box: ``(x1, y1, x2, y2)`` pixel box, end-exclusive (``x`` = column, ``y`` = row).
        mask: Boolean mask of shape ``(y2 - y1, x2 - x1)``, or ``None`` for boxes only.
    """

    cls: str
    score: float
    box: tuple[int, int, int, int]
    mask: npt.NDArray[np.bool_] | None = None

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]

    @property
    def area(self) -> int:
        return max(self.width, 0) * max(self.height, 0)

    @property
    def center(self) -> tuple[float, float]:
        """``(row, col)`` centre of the box."""
        return (self.box[1] + self.box[3]) / 2, (self.box[0] + self.box[2]) / 2

    def shifted(self, rows: int, cols: int) -> RawDetection:
        x1, y1, x2, y2 = self.box
        return replace(self, box=(x1 + cols, y1 + rows, x2 + cols, y2 + rows))

    def full_mask(self) -> npt.NDArray[np.bool_]:
        """The mask, or a filled box when there is none."""
        if self.mask is not None:
            return self.mask
        return np.ones((self.height, self.width), dtype=bool)


class Detector(Protocol):
    """Anything that turns tiles into detections."""

    model_version: str

    def predict(self, tiles: Sequence[npt.NDArray[np.uint8]]) -> list[list[RawDetection]]:
        """Detections per tile, in tile coordinates."""
        ...


def describe(detector: Any) -> str:
    """Model version string recorded in reports (TC-DET-007)."""
    return str(getattr(detector, "model_version", type(detector).__name__))
