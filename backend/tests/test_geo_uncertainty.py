"""ST-035 position uncertainty budget (TC-GEO-010)."""

import math

import numpy as np
import pandas as pd
import pytest

from sonarsentinel.geo.uncertainty import (
    GEOD,
    position_uncertainty_m,
    speed_mps_from_nav,
    uncertainty_config,
    uncertainty_terms,
)


def test_heading_term_matches_design_example() -> None:
    """TC-GEO-010: 50 m ground range with a 2° heading error ≈ 1.75 m."""
    terms = uncertainty_terms(ground_range_m=50.0, altitude_m=8.0, ground_res_m=0.1, speed_mps=2.0)
    assert terms["heading"] == pytest.approx(1.745, abs=0.01)
    assert terms["time"] == pytest.approx(0.4)
    assert terms["pixel"] == pytest.approx(0.1 / math.sqrt(12) * math.sqrt(2))


def test_rss_matches_hand_calculation() -> None:
    expected = math.sqrt(
        2.0**2
        + (0.10 * 30.0) ** 2
        + (50.0 * math.sin(math.radians(2.0))) ** 2
        + (0.5 * 8.0 / 50.0) ** 2
        + (2.0 * 0.2) ** 2
        + (0.1 / math.sqrt(12) * math.sqrt(2)) ** 2
    )
    value = position_uncertainty_m(
        ground_range_m=50.0,
        altitude_m=8.0,
        ground_res_m=0.1,
        speed_mps=2.0,
        layback_m=30.0,
        layback_estimated=True,
    )
    assert value == pytest.approx(round(expected, 2))
    without_layback = position_uncertainty_m(
        ground_range_m=50.0, altitude_m=8.0, ground_res_m=0.1, speed_mps=2.0, layback_m=30.0
    )
    assert without_layback < value


def test_missing_inputs_contribute_zero_and_near_nadir_is_floored() -> None:
    only_gnss = position_uncertainty_m(
        ground_range_m=None, altitude_m=float("nan"), ground_res_m=None, speed_mps=None
    )
    assert only_gnss == 2.0
    terms = uncertainty_terms(ground_range_m=0.0, altitude_m=6.0, ground_res_m=0.1, speed_mps=0.0)
    assert terms["altitude"] == pytest.approx(0.5 * 6.0 / 1.0)


def test_config_overrides_defaults() -> None:
    cfg = {"geo": {"uncertainty": {"gnss_m": 0.05, "heading_deg": 0.5}}}
    params = uncertainty_config(cfg)
    assert params["gnss_m"] == 0.05 and params["time_s"] == 0.2
    rtk = position_uncertainty_m(
        ground_range_m=20.0, altitude_m=5.0, ground_res_m=0.1, speed_mps=1.0, config=cfg
    )
    standalone = position_uncertainty_m(
        ground_range_m=20.0, altitude_m=5.0, ground_res_m=0.1, speed_mps=1.0
    )
    assert rtk < standalone
    assert uncertainty_config(None) == uncertainty_config({})


def test_speed_from_navigation() -> None:
    lon, lat = [80.3], [13.08]
    for _ in range(9):
        next_lon, next_lat, _ = GEOD.fwd(lon[-1], lat[-1], 45.0, 1.5)
        lon.append(float(next_lon))
        lat.append(float(next_lat))
    times = pd.date_range("2026-09-12T05:00:00Z", periods=10, freq="500ms")
    nav = pd.DataFrame({"lat": lat, "lon": lon, "time_utc": times})
    assert speed_mps_from_nav(nav) == pytest.approx(3.0, rel=1e-3)
    nav.loc[3, "lat"] = np.nan
    assert speed_mps_from_nav(nav) == pytest.approx(3.0, rel=1e-3)
    assert math.isnan(speed_mps_from_nav(nav.iloc[:1]))
    assert math.isnan(speed_mps_from_nav(pd.DataFrame({"lat": [1.0, 2.0]})))
