"""Motion quality flags (ST-044, stage S6): roll, pitch and yaw rate above thresholds.

Defaults come from ``preprocess.motion`` in ``pipeline.yaml``. See
``docs/architecture/02-data-pipeline.md`` S6.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

BoolArray = npt.NDArray[np.bool_]
FloatArray = npt.NDArray[np.float64]

HIGH_MOTION = "HIGH_MOTION"


@dataclass(frozen=True)
class MotionFlags:
    """Per-ping flags for each motion rule."""

    roll: BoolArray
    pitch: BoolArray
    yaw_rate: BoolArray

    @property
    def any(self) -> BoolArray:
        """Pings failing at least one rule (``HIGH_MOTION``)."""
        return np.asarray(self.roll | self.pitch | self.yaw_rate, dtype=bool)


def yaw_rate_deg_per_ping(heading_deg: npt.ArrayLike) -> FloatArray:
    """Absolute heading change from the previous ping, wrapped to [0, 180]; the first ping is 0."""
    h = np.asarray(heading_deg, dtype=np.float64)
    if h.size == 0:
        return h.copy()
    diff = (np.diff(h) + 180.0) % 360.0 - 180.0
    return np.asarray(np.abs(np.concatenate([[0.0], diff])), dtype=np.float64)


def motion_flags(
    nav: pd.DataFrame,
    *,
    max_roll_deg: float = 5.0,
    max_pitch_deg: float = 5.0,
    max_yaw_rate_deg_per_ping: float = 3.0,
) -> MotionFlags:
    """Flag pings whose |roll|, |pitch| or yaw rate is *above* the threshold (NaN never flags)."""

    def over(values: npt.ArrayLike, limit: float) -> BoolArray:
        v = np.abs(np.asarray(values, dtype=np.float64))
        return np.asarray(np.nan_to_num(v, nan=0.0) > limit, dtype=bool)

    return MotionFlags(
        roll=over(nav["roll_deg"], max_roll_deg),
        pitch=over(nav["pitch_deg"], max_pitch_deg),
        yaw_rate=over(yaw_rate_deg_per_ping(nav["heading_deg"]), max_yaw_rate_deg_per_ping),
    )


def flag_segments(mask: npt.ArrayLike) -> list[tuple[int, int]]:
    """Runs of True as inclusive ``(start, end)`` ping ranges, for quality events."""
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return []
    padded = np.concatenate([[False], m, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(s), int(e) - 1) for s, e in zip(edges[::2], edges[1::2], strict=True)]
