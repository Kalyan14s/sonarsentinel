"""Towfish layback correction (ST-034, ``docs/architecture/04-geotagging-engine.md`` §4).

When a file stores only the **ship** position and the sonar is towed, the towfish is behind the
ship by the layback::

    layback ≈ sqrt(max(L² − (d − tow_point_height)², 0)) + antenna_to_tow_point
    fish position = geod.fwd(ship_lon, ship_lat, heading + 180°, layback)

Precedence: explicit ``false`` → no change; a manual layback; the XTF ``Layback`` field when it is
populated; an estimate from cable out and fish depth (flag ``LAYBACK_ESTIMATED``). Only pings whose
``nav_source`` is ``ship`` are moved when that column says so; sensor fixes are already at the fish.

Not applied: the along-track time lag (the fish passes a point after the ship). The design names it
but gives no formula; with the fish position shifted astern the remaining error is the timing of
each ping, which is small at survey speeds and is left to the uncertainty budget (ST-035).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from pyproj import Geod

GEOD = Geod(ellps="WGS84")
LAYBACK_ESTIMATED = "LAYBACK_ESTIMATED"

LaybackSource = Literal["none", "manual", "xtf_field", "cable_out"]
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class LaybackResult:
    """Corrected positions and how they were obtained."""

    lat: FloatArray
    lon: FloatArray
    layback_m: FloatArray | None
    applied: bool
    estimated: bool
    source: LaybackSource
    warnings: list[str] = field(default_factory=list)


def estimate_layback_m(
    cable_out_m: Any,
    fish_depth_m: Any,
    *,
    tow_point_height_m: float = 0.0,
    antenna_to_tow_point_m: float = 0.0,
) -> Any:
    """Straight-cable layback in metres; NaN where cable out is missing or not positive.

    ``tow_point_height_m`` enters exactly as in the design formula (``d − tow_point_height``): it is
    the vertical offset subtracted from the fish depth. Scalars in give a float, arrays an array.
    """
    cable = np.asarray(cable_out_m, dtype=np.float64)
    depth = np.nan_to_num(np.asarray(fish_depth_m, dtype=np.float64), nan=0.0)
    vertical = depth - tow_point_height_m
    horizontal = np.sqrt(np.maximum(cable**2 - vertical**2, 0.0)) + antenna_to_tow_point_m
    result = np.where(np.isfinite(cable) & (cable > 0), horizontal, np.nan)
    return float(result) if result.ndim == 0 else result


def apply_layback(
    lat: Any, lon: Any, heading_deg: Any, layback_m: Any
) -> tuple[FloatArray, FloatArray]:
    """Move each position ``layback_m`` astern (heading + 180°); NaN or 0 layback leaves it."""
    lat_a = np.atleast_1d(np.asarray(lat, dtype=np.float64)).copy()
    lon_a = np.atleast_1d(np.asarray(lon, dtype=np.float64)).copy()
    heading = np.broadcast_to(np.asarray(heading_deg, dtype=np.float64), lat_a.shape)
    distance = np.broadcast_to(np.asarray(layback_m, dtype=np.float64), lat_a.shape)
    move = (
        np.isfinite(lat_a)
        & np.isfinite(lon_a)
        & np.isfinite(heading)
        & np.isfinite(distance)
        & (distance > 0)
    )
    if move.any():
        azimuth = (heading[move] + 180.0) % 360.0
        new_lon, new_lat, _ = GEOD.fwd(lon_a[move], lat_a[move], azimuth, distance[move])
        lat_a[move] = new_lat
        lon_a[move] = new_lon
    return lat_a, lon_a


def _mode(value: str | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    if text not in ("auto", "true", "false"):
        raise ValueError(f"apply_layback must be auto, true or false, not {value!r}")
    return text


def _column(nav: pd.DataFrame, name: str) -> FloatArray:
    if name not in nav.columns:
        return np.full(len(nav), np.nan)
    return np.asarray(pd.to_numeric(nav[name], errors="coerce"), dtype=np.float64)


def resolve_layback(
    nav: pd.DataFrame,
    *,
    mode: str | bool = "auto",
    manual_layback_m: float | None = None,
    ship_position_only: bool,
    tow_point_height_m: float = 0.0,
    antenna_to_tow_point_m: float = 0.0,
) -> LaybackResult:
    """Decide whether and how to correct ``nav`` positions for layback.

    Args:
        nav: ``SonarLog.nav``: ``lat``, ``lon``, ``heading_deg``, ``sensor_depth_m``,
            ``cable_out_m``, ``layback_m`` and optionally ``nav_source``.
        mode: ``navigation.apply_layback`` (``auto`` | ``true`` | ``false``) or a bool.
        manual_layback_m: Operator-supplied layback; wins over file values and estimates.
        ship_position_only: The reader found ship positions only (``SHIP_POSITION_ONLY``).
        tow_point_height_m: Vertical tow-point offset in the design formula.
        antenna_to_tow_point_m: Horizontal GNSS antenna → tow point distance.
    """
    lat = _column(nav, "lat")
    lon = _column(nav, "lon")
    unchanged = LaybackResult(lat, lon, None, applied=False, estimated=False, source="none")
    how = _mode(mode)
    if how == "false" or len(nav) == 0:
        return unchanged

    if "nav_source" in nav.columns and (nav["nav_source"] == "ship").any():
        rows = np.asarray(nav["nav_source"] == "ship", dtype=bool)
    else:
        rows = np.ones(len(nav), dtype=bool)
    heading = _column(nav, "heading_deg")

    def corrected(values: FloatArray, source: LaybackSource, estimated: bool) -> LaybackResult:
        distance = np.where(rows, values, np.nan)
        new_lat, new_lon = apply_layback(lat, lon, heading, distance)
        applied = bool(np.isfinite(distance[rows]).any() and (distance[rows] > 0).any())
        if not applied:
            return unchanged
        warnings = [LAYBACK_ESTIMATED] if estimated else []
        return LaybackResult(new_lat, new_lon, distance, True, estimated, source, warnings)

    if manual_layback_m is not None:
        return corrected(np.full(len(nav), float(manual_layback_m)), "manual", estimated=False)

    field_values = _column(nav, "layback_m")
    if (np.isfinite(field_values[rows]) & (field_values[rows] > 0)).any():
        return corrected(field_values, "xtf_field", estimated=False)

    cable = _column(nav, "cable_out_m")
    wants_estimate = how == "true" or ship_position_only
    if wants_estimate and (np.isfinite(cable[rows]) & (cable[rows] > 0)).any():
        estimate = estimate_layback_m(
            cable,
            _column(nav, "sensor_depth_m"),
            tow_point_height_m=tow_point_height_m,
            antenna_to_tow_point_m=antenna_to_tow_point_m,
        )
        return corrected(np.asarray(estimate, dtype=np.float64), "cable_out", estimated=True)
    return unchanged
