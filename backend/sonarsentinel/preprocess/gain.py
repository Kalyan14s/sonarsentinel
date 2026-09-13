"""Radiometric correction (ST-041, stage S4).

1. Across-track: divide each column by its running mean over ``along_track_window_pings`` pings
   (removes beam pattern and range loss, adapting slowly along the track).
2. Per side: scale port and starboard to the same median (removes roll imbalance).
3. Dynamic range: ``log1p``, clip to percentiles shared by both sides, scale to uint8.

See ``docs/architecture/02-data-pipeline.md`` S4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.errors import ValidationError

U8Array = npt.NDArray[np.uint8]


@dataclass
class GainResult:
    """uint8 channels plus the display range used (in ``log1p`` units)."""

    port: U8Array | None
    starboard: U8Array | None
    low: float
    high: float


def flatten_across_track(
    side: npt.NDArray[Any], window_pings: int = 200
) -> npt.NDArray[np.float32]:
    """Divide every column by its running mean along the track."""
    from scipy.ndimage import uniform_filter1d

    x = np.asarray(side, dtype=np.float32)
    size = max(1, min(window_pings, x.shape[0]))
    profile = uniform_filter1d(x, size, axis=0, mode="nearest")
    floor = max(float(np.median(profile)) * 1e-3, 1e-6)
    return np.asarray(x / np.maximum(profile, floor), dtype=np.float32)


def normalize_gain(
    port: npt.NDArray[Any] | None,
    starboard: npt.NDArray[Any] | None,
    *,
    along_track_window_pings: int = 200,
    per_side: bool = True,
    clip_percentiles: tuple[float, float] | list[float] = (1.0, 99.5),
) -> GainResult:
    """Apply stage S4 to both sides and return uint8 channels."""
    sides = {"port": port, "starboard": starboard}
    if all(v is None for v in sides.values()):
        raise ValidationError("Gain normalisation needs at least one channel")
    flat: dict[str, npt.NDArray[np.float32]] = {}
    for name, side in sides.items():
        if side is None:
            continue
        x = flatten_across_track(side, along_track_window_pings)
        if per_side:
            positive = x[x > 0]
            if positive.size:
                x = x / np.float32(np.median(positive))
        flat[name] = np.log1p(x)

    joined = np.concatenate([v.ravel() for v in flat.values()])
    low, high = (float(v) for v in np.percentile(joined, list(clip_percentiles)))
    scale = 255.0 / max(high - low, 1e-6)

    def to_u8(v: npt.NDArray[np.float32]) -> U8Array:
        return np.asarray(np.clip(np.rint((v - low) * scale), 0, 255), dtype=np.uint8)

    return GainResult(
        port=to_u8(flat["port"]) if "port" in flat else None,
        starboard=to_u8(flat["starboard"]) if "starboard" in flat else None,
        low=low,
        high=high,
    )
