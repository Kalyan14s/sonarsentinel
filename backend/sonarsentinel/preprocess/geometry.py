"""Geometric correction (ST-042, stage S5): slant → ground range and along-track resampling.

Sample ``i`` of a side is at slant range ``i / n_samples × slant_range_m`` (same convention as
:func:`sonarsentinel.geo.georef.slant_samples_to_latlon`). Ground bin ``k`` is at ``k ×
ground_res_m``. In the output image starboard bin ``k`` is column ``nadir_col + k`` and port bin
``k`` is column ``nadir_col − k``, so :func:`sonarsentinel.geo.georef.pixels_to_latlon` works on it
directly. Rows are spaced ``ground_res_m`` along the GPS track; ``row_to_ping`` keeps the link to
the original pings. See ``docs/architecture/02-data-pipeline.md`` S5.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from pyproj import Geod

from sonarsentinel.errors import ValidationError

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

_GEOD: Any = Geod(ellps="WGS84")


def ground_bins(
    slant_range_m: npt.ArrayLike, altitude_m: npt.ArrayLike, ground_res_m: float
) -> int:
    """Number of ground bins needed for the longest horizontal range in the chunk."""
    slant = np.asarray(slant_range_m, dtype=np.float64)
    alt = np.nan_to_num(np.asarray(altitude_m, dtype=np.float64), nan=0.0)
    ground = np.sqrt(np.maximum(slant**2 - alt**2, 0.0))
    finite = ground[np.isfinite(ground)]
    if not finite.size:
        raise ValidationError("Slant range is missing for every ping")
    return int(np.floor(finite.max() / ground_res_m)) + 1


def slant_to_ground(
    side: npt.NDArray[Any],
    slant_range_m: npt.ArrayLike,
    altitude_m: npt.ArrayLike,
    *,
    ground_res_m: float = 0.10,
    n_ground: int | None = None,
) -> npt.NDArray[np.float32]:
    """Resample one side from slant-range samples onto a fixed ground-range grid.

    Missing altitude counts as 0 (no correction). Bins beyond the recorded slant range are 0.
    """
    x = np.asarray(side, dtype=np.float32)
    n_pings, n_samples = x.shape
    slant = np.broadcast_to(np.asarray(slant_range_m, dtype=np.float64), (n_pings,))
    alt = np.nan_to_num(np.broadcast_to(np.asarray(altitude_m, dtype=np.float64), (n_pings,)))
    if n_ground is None:
        n_ground = ground_bins(slant, alt, ground_res_m)
    ground = np.arange(n_ground, dtype=np.float64) * ground_res_m
    idx = np.sqrt(ground[None, :] ** 2 + alt[:, None] ** 2) / slant[:, None] * n_samples
    valid = np.isfinite(idx) & (idx <= n_samples - 1)
    idx = np.where(valid, idx, 0.0)
    lo = np.minimum(np.floor(idx).astype(np.int64), n_samples - 2) if n_samples > 1 else idx * 0
    frac = (idx - lo).astype(np.float32)
    lo = lo.astype(np.int64)
    hi = np.minimum(lo + 1, n_samples - 1)
    out = np.take_along_axis(x, lo, axis=1) * (1 - frac) + np.take_along_axis(x, hi, axis=1) * frac
    out[~valid] = 0
    return np.asarray(out, dtype=np.float32)


def cumulative_distance_m(lat: npt.ArrayLike, lon: npt.ArrayLike) -> FloatArray:
    """Distance travelled from the first ping (m); non-finite positions add no distance."""
    la = np.asarray(lat, dtype=np.float64)
    lo = np.asarray(lon, dtype=np.float64)
    if len(la) < 2:
        return np.zeros(len(la))
    _, _, step = _GEOD.inv(lo[:-1], la[:-1], lo[1:], la[1:])
    step = np.nan_to_num(np.asarray(step, dtype=np.float64), nan=0.0)
    return np.concatenate([[0.0], np.cumsum(step)])


def along_track_rows(lat: npt.ArrayLike, lon: npt.ArrayLike, spacing_m: float = 0.10) -> IntArray:
    """``row_to_ping``: nearest ping for rows every ``spacing_m`` metres along the track."""
    distance = cumulative_distance_m(lat, lon)
    if len(distance) == 0:
        return np.zeros(0, dtype=np.int64)
    rows = np.arange(int(np.floor(distance[-1] / spacing_m)) + 1) * spacing_m
    after = np.clip(np.searchsorted(distance, rows, side="left"), 0, len(distance) - 1)
    before = np.clip(after - 1, 0, len(distance) - 1)
    use_before = np.abs(distance[before] - rows) < np.abs(distance[after] - rows)
    return np.asarray(np.where(use_before, before, after), dtype=np.int64)


def build_ground_image(
    port_ground: npt.NDArray[Any] | None,
    starboard_ground: npt.NDArray[Any] | None,
    row_to_ping: npt.ArrayLike,
) -> tuple[npt.NDArray[Any], int]:
    """Assemble the resampled waterfall: port flipped on the left, starboard on the right.

    Both sides must have ``n + 1`` ground bins; the image is ``2n`` wide with ``nadir_col = n``.

    Returns:
        ``(image, nadir_col)``.
    """
    rows = np.asarray(row_to_ping, dtype=np.int64)
    reference = starboard_ground if starboard_ground is not None else port_ground
    if reference is None:
        raise ValidationError("No channel to build an image from")
    n = reference.shape[1] - 1
    image = np.zeros((len(rows), 2 * n), dtype=reference.dtype)
    if starboard_ground is not None:
        image[:, n:] = starboard_ground[rows, :n]
    if port_ground is not None:
        image[:, :n] = port_ground[rows, n:0:-1]
    return image, n


def near_nadir_columns(
    width: int, nadir_col: int, ground_res_m: float, altitude_m: float, factor: float = 0.3
) -> npt.NDArray[np.bool_]:
    """Columns whose ground range is below ``factor × altitude`` (``NEAR_NADIR``)."""
    ground = np.abs(np.arange(width) - nadir_col) * ground_res_m
    return np.asarray(ground < factor * altitude_m, dtype=bool)
