"""TC-GEO-004 (heading wrap-around) and TC-GEO-005 (invalid fixes): navigation cleaning, ST-032."""

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("scipy")
from pyproj import Geod  # noqa: E402

from sonarsentinel.geo.navigation import (  # noqa: E402
    clean_navigation,
    course_over_ground,
    elapsed_seconds,
    find_invalid_fixes,
    smooth_heading,
)
from sonarsentinel.ingest.models import GPS_INTERPOLATED, HEADING_FROM_COG, empty_nav  # noqa: E402

GEOD = Geod(ellps="WGS84")


def _angle_diff(a: np.ndarray, b: float) -> np.ndarray:
    return np.abs((np.asarray(a) - b + 180.0) % 360.0 - 180.0)


def _nav(n: int = 200, heading: float = 62.4, speed_mps: float = 2.0) -> pd.DataFrame:
    nav = empty_nav(n)
    lon, lat, _ = GEOD.fwd(
        np.full(n, 80.3071), np.full(n, 13.0802), np.full(n, heading), np.arange(n) * speed_mps
    )
    nav["lat"], nav["lon"] = lat, lon
    nav["heading_deg"] = heading
    nav["time_utc"] = pd.Timestamp("2026-09-12T05:10:02Z") + pd.to_timedelta(np.arange(n), "s")
    nav["nav_source"] = "sensor"
    return nav


def test_heading_wraparound_smooths_to_north() -> None:
    """TC-GEO-004: 358, 359, 0, 1, 2 → about 0°, not 180°."""
    out = smooth_heading([358.0, 359.0, 0.0, 1.0, 2.0], window=5)
    assert _angle_diff(out[2], 0.0) < 1e-9
    assert np.all(_angle_diff(out, 0.0) < 2.0)


def test_heading_smoothing_skips_nan() -> None:
    out = smooth_heading([10.0, np.nan, 12.0, np.nan, np.nan, np.nan, np.nan], window=3)
    assert out[1] == pytest.approx(11.0)
    assert np.isnan(out[5])


def test_invalid_fixes_are_interpolated() -> None:
    """TC-GEO-005: a (0, 0) fix and a 500 m jump are replaced and flagged."""
    nav = _nav()
    truth_lat, truth_lon = nav["lat"].to_numpy().copy(), nav["lon"].to_numpy().copy()
    nav.loc[20, ["lat", "lon"]] = 0.0
    lon_j, lat_j, _ = GEOD.fwd(truth_lon[50], truth_lat[50], 150.0, 500.0)
    nav.loc[50, ["lat", "lon"]] = [lat_j, lon_j]
    nav.loc[120, "lat"] = np.nan

    result = clean_navigation(nav)
    assert np.flatnonzero(result.invalid).tolist() == [20, 50, 120]
    assert GPS_INTERPOLATED in result.warnings
    assert result.utm_epsg == 32644
    assert result.nav.loc[50, "nav_source"] == "interpolated"
    _, _, err = GEOD.inv(truth_lon, truth_lat, result.nav["lon"], result.nav["lat"])
    assert np.max(err) < 0.05  # straight track: interpolation and smoothing are exact
    assert np.all(_angle_diff(result.nav["heading_deg"].to_numpy(), 62.4) < 1e-6)


def test_bad_first_fix_does_not_poison_track() -> None:
    nav = _nav(60)
    lon_j, lat_j, _ = GEOD.fwd(nav["lon"][0], nav["lat"][0], 0.0, 2000.0)
    nav.loc[0, ["lat", "lon"]] = [lat_j, lon_j]
    seconds = elapsed_seconds(nav)
    invalid = find_invalid_fixes(nav["lat"], nav["lon"], seconds)
    assert np.flatnonzero(invalid).tolist() == [0]


def test_gap_allows_matching_distance() -> None:
    """A long GPS outage followed by a distant but reachable fix is kept."""
    nav = _nav(100, speed_mps=5.0)
    nav.loc[10:59, ["lat", "lon"]] = np.nan
    invalid = find_invalid_fixes(nav["lat"], nav["lon"], elapsed_seconds(nav))
    assert invalid.sum() == 50 and not invalid[60]


def test_missing_heading_uses_course_over_ground() -> None:
    nav = _nav(80, heading=135.0)
    nav["heading_deg"] = np.nan
    result = clean_navigation(nav)
    assert HEADING_FROM_COG in result.warnings
    assert np.all(_angle_diff(result.nav["heading_deg"].to_numpy(), 135.0) < 0.01)


def test_curved_track_smoothing_stays_close() -> None:
    n = 400
    headings = np.linspace(0.0, 180.0, n)
    lat, lon = [13.08], [80.30]
    for h in headings[:-1]:
        lo, la, _ = GEOD.fwd(lon[-1], lat[-1], h, 1.0)
        lat.append(la)
        lon.append(lo)
    nav = _nav(n)
    nav["lat"], nav["lon"], nav["heading_deg"] = lat, lon, headings
    rng = np.random.default_rng(0)
    noisy = nav.copy()
    noisy["lat"] = nav["lat"] + rng.normal(0, 1e-6, n)  # ~0.1 m noise
    result = clean_navigation(noisy)
    _, _, err = GEOD.inv(nav["lon"], nav["lat"], result.nav["lon"], result.nav["lat"])
    assert np.median(err) < 0.1
    assert np.all(_angle_diff(course_over_ground(lat, lon)[:-1], 0.0) <= 180.0)


def test_no_valid_fixes_is_left_alone() -> None:
    nav = empty_nav(5)
    result = clean_navigation(nav)
    assert result.utm_epsg is None and result.invalid.all() and result.warnings == []
