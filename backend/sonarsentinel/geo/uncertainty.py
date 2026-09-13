"""Horizontal position uncertainty budget (ST-035, FR-GEO-06).

``docs/architecture/04-geotagging-engine.md`` §8: the 1-σ horizontal uncertainty of a detection is
the root-sum-square of independent terms (ADR-018)::

    σ_gnss     receiver spec                                  geo.uncertainty.gnss_m
    σ_layback  layback_fraction × layback, only if estimated  geo.uncertainty.layback_fraction
    σ_heading  ground_range × sin(σ_heading)                  geo.uncertainty.heading_deg
    σ_alt      σ_alt × altitude / ground_range (≥ 1 m)         geo.uncertainty.altitude_m
    σ_time     speed × σ_time                                 geo.uncertainty.time_s
    σ_pixel    ground_res / √12 per axis, both axes combined

Missing (``None`` or NaN) inputs contribute 0 to their term.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Geod

GEOD: Any = Geod(ellps="WGS84")

DEFAULTS: dict[str, float] = {
    "gnss_m": 2.0,
    "heading_deg": 2.0,
    "altitude_m": 0.5,
    "time_s": 0.2,
    "layback_fraction": 0.10,
}


def uncertainty_config(config: Mapping[str, Any] | None = None) -> dict[str, float]:
    """``geo.uncertainty`` values from a pipeline configuration, with the defaults filled in."""
    geo = (config or {}).get("geo") or {}
    section = geo.get("uncertainty") or {}
    return {key: float(section.get(key, default)) for key, default in DEFAULTS.items()}


def _finite(value: float | None) -> float:
    if value is None:
        return 0.0
    number = float(value)
    return number if math.isfinite(number) else 0.0


def uncertainty_terms(
    *,
    ground_range_m: float | None,
    altitude_m: float | None,
    ground_res_m: float | None,
    speed_mps: float | None,
    layback_m: float | None = None,
    layback_estimated: bool = False,
    config: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Each 1-σ term in metres, keyed ``gnss``, ``layback``, ``heading``, ``altitude``, ``time``,
    ``pixel``."""
    p = uncertainty_config(config)
    ground = abs(_finite(ground_range_m))
    return {
        "gnss": p["gnss_m"],
        "layback": p["layback_fraction"] * abs(_finite(layback_m)) if layback_estimated else 0.0,
        "heading": ground * math.sin(math.radians(p["heading_deg"])),
        "altitude": p["altitude_m"] * abs(_finite(altitude_m)) / max(ground, 1.0),
        "time": abs(_finite(speed_mps)) * p["time_s"],
        "pixel": abs(_finite(ground_res_m)) / math.sqrt(12.0) * math.sqrt(2.0),
    }


def position_uncertainty_m(
    *,
    ground_range_m: float | None,
    altitude_m: float | None,
    ground_res_m: float | None,
    speed_mps: float | None,
    layback_m: float | None = None,
    layback_estimated: bool = False,
    config: Mapping[str, Any] | None = None,
) -> float:
    """1-σ horizontal position uncertainty in metres, rounded to 2 decimals.

    Args:
        ground_range_m: Across-track distance of the detection from the track.
        altitude_m: Sonar altitude above the seabed.
        ground_res_m: Pixel size of the processed image.
        speed_mps: Vessel ground speed (see :func:`speed_mps_from_nav`).
        layback_m: Applied layback; only counts when ``layback_estimated``.
        config: Pipeline configuration (reads ``geo.uncertainty``) or ``None`` for defaults.
    """
    terms = uncertainty_terms(
        ground_range_m=ground_range_m,
        altitude_m=altitude_m,
        ground_res_m=ground_res_m,
        speed_mps=speed_mps,
        layback_m=layback_m,
        layback_estimated=layback_estimated,
        config=config,
    )
    return round(math.sqrt(sum(value * value for value in terms.values())), 2)


def speed_mps_from_nav(nav: pd.DataFrame) -> float:
    """Median ground speed (m/s) between consecutive valid fixes; NaN when it can't be measured."""
    if not {"lat", "lon", "time_utc"} <= set(nav.columns) or len(nav) < 2:
        return float("nan")
    lat = pd.to_numeric(nav["lat"], errors="coerce").to_numpy(np.float64)
    lon = pd.to_numeric(nav["lon"], errors="coerce").to_numpy(np.float64)
    times = pd.to_datetime(nav["time_utc"], utc=True, errors="coerce")
    valid = np.isfinite(lat) & np.isfinite(lon) & times.notna().to_numpy()
    if valid.sum() < 2:
        return float("nan")
    lat, lon = lat[valid], lon[valid]
    seconds = (times[valid] - times[valid].iloc[0]).dt.total_seconds().to_numpy(np.float64)
    _, _, step = GEOD.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
    dt = np.diff(seconds)
    moving = dt > 0
    if not moving.any():
        return float("nan")
    return float(np.median(np.asarray(step, dtype=np.float64)[moving] / dt[moving]))
