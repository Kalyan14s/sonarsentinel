"""Navigation cleaning (ST-032, pipeline stage S2).

Invalid fixes ((0, 0), NaN, out of range, or jumps faster than ``max_speed_mps``) are marked and
interpolated; positions are smoothed with a Savitzky–Golay filter in the survey's UTM zone and
headings are smoothed on the circle, with course over ground filling missing headings.
See ``docs/architecture/02-data-pipeline.md`` S2 and ``04-geotagging-engine.md`` §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from pyproj import Geod, Transformer

from sonarsentinel.geo.units import utm_epsg_for
from sonarsentinel.ingest.models import GPS_INTERPOLATED, HEADING_FROM_COG

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

_GEOD: Any = Geod(ellps="WGS84")

#: Extra distance allowed between fixes on top of ``max_speed × Δt`` (GNSS noise).
GPS_NOISE_M = 5.0


def smooth_heading(heading_deg: npt.ArrayLike, window: int = 25) -> FloatArray:
    """Circular moving average of headings (359° and 1° average to 0°, not 180°).

    NaN headings are ignored; positions with no valid heading inside the window stay NaN.
    """
    from scipy.ndimage import uniform_filter1d

    h = np.asarray(heading_deg, dtype=np.float64)
    if h.size == 0:
        return h.copy()
    ok = np.isfinite(h)
    size = max(1, min(window, len(h)))
    rad = np.radians(np.where(ok, h, 0.0))
    weight = ok.astype(np.float64)
    s = uniform_filter1d(np.sin(rad) * weight, size, mode="nearest")
    c = uniform_filter1d(np.cos(rad) * weight, size, mode="nearest")
    out = np.mod(np.degrees(np.arctan2(s, c)), 360.0)
    out[uniform_filter1d(weight, size, mode="nearest") == 0] = np.nan
    return np.asarray(out, dtype=np.float64)


def course_over_ground(lat: npt.ArrayLike, lon: npt.ArrayLike) -> FloatArray:
    """Direction of travel between consecutive positions (degrees true); the last value repeats."""
    la = np.asarray(lat, dtype=np.float64)
    lo = np.asarray(lon, dtype=np.float64)
    if len(la) < 2:
        return np.full(len(la), np.nan)
    az, _, _ = _GEOD.inv(lo[:-1], la[:-1], lo[1:], la[1:])
    cog = np.mod(np.asarray(az, dtype=np.float64), 360.0)
    return np.append(cog, cog[-1])


def elapsed_seconds(nav: pd.DataFrame, ping_interval_s: float | None = None) -> FloatArray:
    """Seconds since the first ping; missing times are interpolated by ping index.

    Without any timestamps, pings are assumed ``ping_interval_s`` apart (default 1 s, which makes
    the speed check lenient).
    """
    n = len(nav)
    times = pd.to_datetime(nav["time_utc"], utc=True, errors="coerce")
    known = times.notna().to_numpy()
    if known.sum() >= 2:
        ref = times[known].iloc[0]
        secs = (times[known] - ref).dt.total_seconds().to_numpy(dtype=np.float64)
        return np.asarray(np.interp(np.arange(n), np.flatnonzero(known), secs), dtype=np.float64)
    return np.arange(n, dtype=np.float64) * (ping_interval_s or 1.0)


def find_invalid_fixes(
    lat: npt.ArrayLike,
    lon: npt.ArrayLike,
    seconds: npt.ArrayLike,
    *,
    max_speed_mps: float = 6.0,
    noise_m: float = GPS_NOISE_M,
) -> BoolArray:
    """Mark fixes that are missing, (0, 0), out of range, or imply an impossible speed.

    Starting from the fix closest to the median position (so a bad first fix can't poison the
    track), fixes are accepted forwards and backwards while the distance to the last accepted fix
    is at most ``max_speed_mps × Δt + noise_m``.
    """
    la = np.asarray(lat, dtype=np.float64)
    lo = np.asarray(lon, dtype=np.float64)
    t = np.asarray(seconds, dtype=np.float64)
    invalid = ~(np.isfinite(la) & np.isfinite(lo))
    invalid |= (la == 0) & (lo == 0)
    invalid |= (np.abs(la) > 90) | (np.abs(lo) > 180)
    valid = np.flatnonzero(~invalid)
    if len(valid) < 2:
        return invalid

    _, _, to_median = _GEOD.inv(
        np.full(len(valid), np.median(lo[valid])),
        np.full(len(valid), np.median(la[valid])),
        lo[valid],
        la[valid],
    )
    anchor = int(valid[int(np.argmin(to_median))])
    accepted = np.zeros(len(la), dtype=bool)
    accepted[anchor] = True
    for sequence in (valid[valid > anchor], valid[valid < anchor][::-1]):
        last = anchor
        for i in sequence:
            _, _, dist = _GEOD.inv(lo[last], la[last], lo[i], la[i])
            if dist <= max_speed_mps * abs(t[i] - t[last]) + noise_m:
                accepted[i] = True
                last = int(i)
    return ~accepted


@dataclass
class CleanedNavigation:
    """Result of :func:`clean_navigation`."""

    nav: pd.DataFrame
    invalid: BoolArray
    utm_epsg: int | None
    warnings: list[str] = field(default_factory=list)


def clean_navigation(
    nav: pd.DataFrame,
    *,
    max_speed_mps: float = 6.0,
    smoothing_window: int = 31,
    heading_window: int = 25,
    ping_interval_s: float | None = None,
) -> CleanedNavigation:
    """Clean a navigation table (pipeline stage S2).

    Args:
        nav: Navigation with ``lat``, ``lon``, ``heading_deg``, ``time_utc`` (``NAV_COLUMNS``).
        max_speed_mps: Largest plausible speed between fixes.
        smoothing_window: Savitzky–Golay window in pings (odd; shortened for short logs).
        heading_window: Circular heading smoothing window in pings.
        ping_interval_s: Assumed ping interval when the log has no timestamps.

    Returns:
        A copy with cleaned ``lat``/``lon``/``heading_deg``, per-ping ``invalid`` flags, the UTM
        zone used and warning codes (``GPS_INTERPOLATED``, ``HEADING_FROM_COG``).
    """
    from scipy.signal import savgol_filter

    out = nav.copy()
    n = len(out)
    lat = out["lat"].to_numpy(dtype=np.float64)
    lon = out["lon"].to_numpy(dtype=np.float64)
    seconds = elapsed_seconds(out, ping_interval_s)
    invalid = find_invalid_fixes(lat, lon, seconds, max_speed_mps=max_speed_mps)
    valid = np.flatnonzero(~invalid)
    warnings: list[str] = []
    if len(valid) == 0:
        return CleanedNavigation(out, invalid, None, warnings)

    epsg = utm_epsg_for(float(np.median(lon[valid])), float(np.median(lat[valid])))
    to_utm: Any = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    to_geo: Any = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    east, north = to_utm.transform(lon[valid], lat[valid])
    pings = np.arange(n, dtype=np.float64)
    east = np.interp(pings, valid, east)
    north = np.interp(pings, valid, north)
    if invalid.any():
        warnings.append(GPS_INTERPOLATED)
        source = out["nav_source"].to_numpy(dtype=object)
        source[invalid] = "interpolated"
        out["nav_source"] = source

    window = min(smoothing_window, n if n % 2 else n - 1)
    if window >= 5:
        east = savgol_filter(east, window, 2)
        north = savgol_filter(north, window, 2)
    lon_s, lat_s = to_geo.transform(east, north)
    out["lat"] = np.asarray(lat_s, dtype=np.float64)
    out["lon"] = np.asarray(lon_s, dtype=np.float64)

    heading = out["heading_deg"].to_numpy(dtype=np.float64)
    missing = ~np.isfinite(heading)
    if missing.any():
        cog = course_over_ground(out["lat"].to_numpy(), out["lon"].to_numpy())
        heading = np.where(missing, cog, heading)
        warnings.append(HEADING_FROM_COG)
    out["heading_deg"] = smooth_heading(heading, heading_window)
    return CleanedNavigation(out, invalid, epsg, warnings)
