"""Surface-return band (ST-047, FR-PRE-09, quality mask S6).

In shallow water the echo from the sea surface arrives at a slant range roughly equal to the sensor
depth below the surface. The ground-range image maps slant range ``s`` to ground range
``g = sqrt(s² − H²)`` (``preprocess/geometry.py``, ``H`` = altitude), so the surface return draws a
band at ``g = sqrt(d² − H²)`` on both sides of nadir, parallel to the track. When the sensor is no
deeper than its altitude (``d ≤ H``) the return falls inside the water column, which is already
masked, and there is no band.

The band spans slant ranges ``d ± tolerance``. Every detection mostly inside it is flagged
``SURFACE_RETURN_BAND``; long thin detections parallel to the track in the band are the typical
false positive and can be suppressed when ``preprocess.surface_return_mask`` is on (ADR-018).
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

SURFACE_RETURN_BAND = "SURFACE_RETURN_BAND"


def surface_band_mask(
    sensor_depth_m: npt.ArrayLike,
    altitude_m: npt.ArrayLike,
    nadir_col: int,
    width: int,
    ground_res_m: float,
    tolerance_m: float = 0.5,
) -> npt.NDArray[np.bool_]:
    """Boolean mask ``(rows, width)`` of the surface-return band.

    Args:
        sensor_depth_m: Sensor depth below the surface per image row (scalar broadcasts).
        altitude_m: Sensor altitude above the seabed per image row (scalar broadcasts).
        nadir_col: Column of the track line; ground bin ``k`` is at ``|col − nadir_col| × res``.
        width: Image width in pixels.
        ground_res_m: Metres per pixel.
        tolerance_m: Half-width of the band in slant range.
    """
    depth, altitude = np.broadcast_arrays(
        np.atleast_1d(np.asarray(sensor_depth_m, dtype=np.float64)),
        np.atleast_1d(np.asarray(altitude_m, dtype=np.float64)),
    )
    valid = np.isfinite(depth) & np.isfinite(altitude) & (depth > altitude)
    with np.errstate(invalid="ignore"):
        near = np.maximum(depth - tolerance_m, 0.0)
        far = depth + tolerance_m
        ground_near = np.sqrt(np.maximum(near**2 - altitude**2, 0.0))
        ground_far = np.sqrt(np.maximum(far**2 - altitude**2, 0.0))
    ground = np.abs(np.arange(width, dtype=np.float64) - nadir_col) * ground_res_m
    mask = (
        valid[:, None]
        & (ground[None, :] >= ground_near[:, None])
        & (ground[None, :] <= ground_far[:, None])
    )
    return np.asarray(mask, dtype=bool)


def in_surface_band(
    box: tuple[int, int, int, int], band_mask: npt.NDArray[np.bool_], min_fraction: float = 0.5
) -> bool:
    """True when at least ``min_fraction`` of the box ``(x1, y1, x2, y2)`` lies in the band."""
    x1, y1, x2, y2 = box
    region = band_mask[max(y1, 0) : max(y2, 0), max(x1, 0) : max(x2, 0)]
    return bool(region.size) and float(region.mean()) >= min_fraction


def suppress_surface_detection(
    in_band: bool,
    length_m: float,
    width_m: float,
    orientation_rel_track_deg: float | None,
    *,
    min_aspect: float = 4.0,
    max_angle_deg: float = 15.0,
) -> bool:
    """True for linear objects (length/width ≥ 4) parallel to the track (≤ 15°) inside the band."""
    if not in_band or width_m <= 0 or orientation_rel_track_deg is None:
        return False
    angle = float(orientation_rel_track_deg)
    if not math.isfinite(angle):
        return False
    folded = abs(angle) % 180.0
    folded = min(folded, 180.0 - folded)
    return length_m / width_m >= min_aspect and folded <= max_angle_deg
