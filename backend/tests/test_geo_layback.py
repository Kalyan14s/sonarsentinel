"""ST-034 layback correction (TC-GEO-009)."""

import math

import numpy as np
import pandas as pd
import pytest
from pyproj import Geod

from sonarsentinel.geo.layback import (
    LAYBACK_ESTIMATED,
    apply_layback,
    estimate_layback_m,
    resolve_layback,
)

GEOD = Geod(ellps="WGS84")
LAT0, LON0 = 13.08, 80.29


def _nav(n: int = 5, heading: float = 90.0, **columns: object) -> pd.DataFrame:
    data: dict[str, object] = {
        "lat": np.full(n, LAT0),
        "lon": np.full(n, LON0),
        "heading_deg": np.full(n, heading),
        "sensor_depth_m": np.full(n, 20.0),
        "cable_out_m": np.full(n, 100.0),
        "layback_m": np.full(n, np.nan),
        "nav_source": np.array(["ship"] * n, dtype=object),
    }
    data.update(columns)
    return pd.DataFrame(data)


def test_estimate_matches_tc_geo_009() -> None:
    assert estimate_layback_m(100.0, 20.0) == pytest.approx(math.sqrt(100**2 - 20**2), abs=1e-9)
    assert estimate_layback_m(100.0, 20.0) == pytest.approx(97.98, abs=0.01)
    assert estimate_layback_m(100.0, 20.0, antenna_to_tow_point_m=5.0) == pytest.approx(
        102.98, 0.01
    )
    assert math.isnan(estimate_layback_m(float("nan"), 20.0))
    assert math.isnan(estimate_layback_m(0.0, 20.0))
    assert estimate_layback_m(10.0, 20.0) == 0.0  # cable shorter than depth: fish below tow point


def test_tc_geo_009_fish_astern_with_flag() -> None:
    result = resolve_layback(_nav(heading=90.0), ship_position_only=True)
    assert result.applied and result.estimated and result.source == "cable_out"
    assert LAYBACK_ESTIMATED in result.warnings
    azimuth, _, distance = GEOD.inv(LON0, LAT0, result.lon[0], result.lat[0])
    assert distance == pytest.approx(97.98, abs=0.1)
    assert (azimuth % 360) == pytest.approx(270.0, abs=0.01)  # heading east → fish to the west


def test_heading_wraps_at_350() -> None:
    lat, lon = apply_layback([LAT0], [LON0], [350.0], [50.0])
    azimuth, _, distance = GEOD.inv(LON0, LAT0, lon[0], lat[0])
    assert distance == pytest.approx(50.0, abs=1e-6)
    assert (azimuth % 360) == pytest.approx(170.0, abs=0.01)


def test_nan_or_zero_layback_leaves_points() -> None:
    lat, lon = apply_layback([LAT0, LAT0], [LON0, LON0], [0.0, 0.0], [np.nan, 0.0])
    assert np.allclose(lat, LAT0) and np.allclose(lon, LON0)


def test_manual_override_wins() -> None:
    nav = _nav(layback_m=np.full(5, 30.0))
    result = resolve_layback(nav, manual_layback_m=12.0, ship_position_only=True)
    assert result.applied and not result.estimated and result.source == "manual"
    assert result.warnings == []
    _, _, distance = GEOD.inv(LON0, LAT0, result.lon[0], result.lat[0])
    assert distance == pytest.approx(12.0, abs=1e-6)


def test_false_mode_changes_nothing() -> None:
    for mode in ("false", False):
        result = resolve_layback(_nav(), mode=mode, manual_layback_m=12.0, ship_position_only=True)
        assert not result.applied and result.source == "none"
        assert np.allclose(result.lat, LAT0) and np.allclose(result.lon, LON0)
    with pytest.raises(ValueError, match="auto, true or false"):
        resolve_layback(_nav(), mode="maybe", ship_position_only=True)


def test_xtf_field_takes_precedence_over_estimate() -> None:
    result = resolve_layback(_nav(layback_m=np.full(5, 42.0)), ship_position_only=True)
    assert result.applied and not result.estimated and result.source == "xtf_field"
    _, _, distance = GEOD.inv(LON0, LAT0, result.lon[0], result.lat[0])
    assert distance == pytest.approx(42.0, abs=1e-6)


def test_nan_cable_leaves_positions() -> None:
    result = resolve_layback(
        _nav(cable_out_m=np.full(5, np.nan)), mode="true", ship_position_only=True
    )
    assert not result.applied and result.source == "none"
    assert np.allclose(result.lat, LAT0)


def test_auto_without_ship_only_does_not_estimate() -> None:
    nav = _nav(nav_source=np.array(["sensor"] * 5, dtype=object))
    assert not resolve_layback(nav, ship_position_only=False).applied
    assert resolve_layback(nav, mode="true", ship_position_only=False).estimated


def test_only_ship_rows_move() -> None:
    sources = np.array(["ship", "sensor", "ship", "sensor", "ship"], dtype=object)
    result = resolve_layback(_nav(nav_source=sources), ship_position_only=True)
    assert result.applied
    moved = ~np.isclose(result.lon, LON0)
    assert moved.tolist() == [True, False, True, False, True]
    assert result.layback_m is not None and np.isnan(result.layback_m[1])
