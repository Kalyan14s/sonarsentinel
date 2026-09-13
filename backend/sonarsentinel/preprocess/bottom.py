"""Bottom tracking and water-column mask (ST-040, stage S3).

The first seabed return per ping is the first sample (after the transmit pulse) where the smoothed
port+starboard intensity rises above ``threshold_k`` × the noise floor, median-filtered across
pings. Recorded altitude is used when it agrees with the tracked value; otherwise the tracked
altitude replaces it and ``NO_ALTITUDE_BOTTOM_TRACKED`` is raised. Samples are nadir first.
See ``docs/architecture/02-data-pipeline.md`` S3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.errors import ValidationError

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

NO_ALTITUDE_BOTTOM_TRACKED = "NO_ALTITUDE_BOTTOM_TRACKED"


@dataclass
class BottomTrack:
    """First-return sample and altitude per ping (NaN where no return was found)."""

    first_return: FloatArray
    altitude_m: FloatArray


def track_bottom(
    port: npt.NDArray[Any] | None,
    starboard: npt.NDArray[Any] | None,
    slant_range_m: npt.ArrayLike,
    *,
    threshold_k: float = 3.0,
    median_window: int = 31,
    smooth_samples: int | None = None,
    blank_fraction: float = 0.005,
) -> BottomTrack:
    """Estimate the first seabed return and altitude for every ping.

    Args:
        port: Port samples ``(n_pings, n_samples)``, nadir first.
        starboard: Starboard samples, nadir first.
        slant_range_m: Slant range per ping (or one value).
        threshold_k: Return threshold as a multiple of the noise floor.
        median_window: Across-ping median filter length.
        smooth_samples: Along-sample smoothing length (default ``n_samples // 200``, at least 3).
        blank_fraction: Leading fraction of samples ignored (transmit pulse).
    """
    from scipy.ndimage import median_filter, uniform_filter1d

    sides = [np.asarray(c, dtype=np.float32) for c in (port, starboard) if c is not None]
    if not sides:
        raise ValidationError("Bottom tracking needs at least one channel")
    n_samples = min(s.shape[1] for s in sides)
    profile = np.mean(np.stack([s[:, :n_samples] for s in sides]), axis=0)
    n_pings = profile.shape[0]
    window = smooth_samples or max(3, n_samples // 200)
    smoothed = uniform_filter1d(profile, window, axis=1, mode="nearest")

    blank = int(n_samples * blank_fraction)
    search = smoothed[:, blank : max(blank + 1, n_samples // 2)]
    noise = np.maximum(np.percentile(search, 5, axis=1), 1.0)
    above = search > (threshold_k * noise)[:, None]
    found = above.any(axis=1)
    first = np.where(found, above.argmax(axis=1) + blank, np.nan).astype(np.float64)

    if found.any() and n_pings > 1:
        idx = np.arange(n_pings)
        filled = np.interp(idx, idx[found], first[found])
        size = max(1, min(median_window, n_pings))
        first = np.where(found, median_filter(filled, size=size, mode="nearest"), np.nan)

    slant = np.broadcast_to(np.asarray(slant_range_m, dtype=np.float64), (n_pings,))
    altitude = first / n_samples * slant
    return BottomTrack(first_return=first, altitude_m=np.asarray(altitude, dtype=np.float64))


def resolve_altitude(
    recorded_m: npt.ArrayLike,
    tracked_m: npt.ArrayLike,
    *,
    mode: str | bool = "auto",
    rel_tolerance: float = 0.25,
) -> tuple[FloatArray, BoolArray]:
    """Choose recorded or tracked altitude per ping.

    Args:
        recorded_m: Altitude from the file (NaN if missing).
        tracked_m: Altitude from :func:`track_bottom`.
        mode: ``"auto"`` (recorded if within ``rel_tolerance`` of tracked), ``True`` (always
            tracked) or ``False`` (always recorded).

    Returns:
        ``(altitude_m, used_tracking)``.
    """
    recorded = np.asarray(recorded_m, dtype=np.float64)
    tracked = np.asarray(tracked_m, dtype=np.float64)
    if mode is False or mode == "false":
        return recorded.copy(), np.zeros(len(recorded), dtype=bool)
    if mode is True or mode == "true":
        use = np.isfinite(tracked)
    else:
        agree = np.abs(recorded - tracked) <= rel_tolerance * np.maximum(tracked, 1e-6)
        use = np.isfinite(tracked) & ~(np.isfinite(recorded) & agree)
    return np.where(use, tracked, recorded), np.asarray(use, dtype=bool)


def water_column_mask(first_return: npt.ArrayLike, n_samples: int) -> BoolArray:
    """``(n_pings, n_samples)`` mask of samples before the first return (NaN → nothing masked)."""
    first = np.nan_to_num(np.asarray(first_return, dtype=np.float64), nan=0.0)
    return np.asarray(np.arange(n_samples)[None, :] < first[:, None], dtype=bool)
