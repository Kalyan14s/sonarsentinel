"""TC-GEO-001…003 and TC-GEO-014: pixel → WGS84 geotagging.

Expected positions are checked independently with the *inverse* geodesic: the distance from the
sonar to each computed point must equal the pixel's ground range, and the azimuth must be the
heading ± 90°. Tolerance: 0.05 m (golden-test requirement).
"""

import numpy as np
import pytest
from pyproj import Geod

from sonarsentinel.errors import ValidationError
from sonarsentinel.geo.formatting import format_decimal, to_dms
from sonarsentinel.geo.georef import (
    GeoFrame,
    offset_position,
    pixel_to_latlon,
    pixels_to_latlon,
    slant_to_ground_range,
)

GEOD = Geod(ellps="WGS84")
TOL_M = 0.05


def _track(
    headings: np.ndarray, start=(13.080, 80.305), step_m: float = 0.1
) -> tuple[np.ndarray, np.ndarray]:
    lats, lons = [start[0]], [start[1]]
    for h in headings[:-1]:
        lon2, lat2, _ = GEOD.fwd(lons[-1], lats[-1], h, step_m)
        lats.append(lat2)
        lons.append(lon2)
    return np.array(lats), np.array(lons)


def _frame(headings: np.ndarray, nadir_col: int = 500, res: float = 0.1) -> GeoFrame:
    lat, lon = _track(headings)
    return GeoFrame(
        lat=lat,
        lon=lon,
        heading_deg=headings.astype(np.float64),
        row_to_ping=np.arange(len(headings), dtype=np.int64),
        nadir_col=nadir_col,
        ground_res_m=res,
    )


def _assert_geometry(frame: GeoFrame, rows: np.ndarray, cols: np.ndarray) -> None:
    lat, lon = pixels_to_latlon(rows, cols, frame)
    ping = frame.row_to_ping[rows]
    offset = cols - frame.nadir_col
    az, _, dist = GEOD.inv(frame.lon[ping], frame.lat[ping], lon, lat)
    expected_dist = np.abs(offset) * frame.ground_res_m
    np.testing.assert_allclose(dist, expected_dist, atol=TOL_M)
    moved = expected_dist > 0
    expected_az = np.mod(frame.heading_deg[ping] + np.where(offset >= 0, 90.0, -90.0), 360.0)
    az_error = (np.mod(az, 360.0) - expected_az + 180.0) % 360.0 - 180.0
    assert np.max(np.abs(az_error[moved])) < 1e-6


def test_straight_track_golden() -> None:
    """TC-GEO-001."""
    frame = _frame(np.full(2000, 45.0))
    rng = np.random.default_rng(42)
    rows = rng.integers(0, 2000, 300)
    cols = rng.integers(0, 1001, 300)
    _assert_geometry(frame, rows, cols)


def test_curved_track_golden() -> None:
    """TC-GEO-002."""
    headings = np.mod(np.linspace(0.0, 270.0, 3000), 360.0)
    frame = _frame(headings)
    rng = np.random.default_rng(7)
    _assert_geometry(frame, rng.integers(0, 3000, 300), rng.integers(0, 1001, 300))


def test_port_and_starboard_directions() -> None:
    """TC-GEO-003: heading north, starboard is east and port is west."""
    frame = _frame(np.zeros(10), nadir_col=500, res=0.1)
    lat0, lon0 = float(frame.lat[5]), float(frame.lon[5])
    lat_s, lon_s = pixel_to_latlon(5, 1000, frame)  # 50 m starboard
    lat_p, lon_p = pixel_to_latlon(5, 0, frame)  # 50 m port
    assert lon_s > lon0 > lon_p
    assert abs(lat_s - lat0) < 1e-6 and abs(lat_p - lat0) < 1e-6
    assert pixel_to_latlon(5, 500, frame) == pytest.approx((lat0, lon0), abs=1e-12)


def test_scalar_matches_vectorised() -> None:
    frame = _frame(np.full(20, 130.0))
    lat, lon = pixels_to_latlon(np.array([3, 7]), np.array([120, 880]), frame)
    assert pixel_to_latlon(7, 880, frame) == pytest.approx((lat[1], lon[1]), abs=1e-12)


def test_offset_position_matches_geodesic() -> None:
    lat, lon = offset_position(13.084, 80.3127, 62.4, "starboard", 23.7)
    az, _, dist = GEOD.inv(80.3127, 13.084, lon, lat)
    assert dist == pytest.approx(23.7, abs=TOL_M)
    assert np.mod(az, 360.0) == pytest.approx(152.4, abs=1e-6)
    with pytest.raises(ValidationError):
        offset_position(13.0, 80.0, 0.0, "port", -1.0)


def test_slant_to_ground_range() -> None:
    np.testing.assert_allclose(
        slant_to_ground_range([50.0, 5.0], [10.0, 10.0]), [np.sqrt(2400.0), 0.0]
    )


def test_frame_validation() -> None:
    lat = np.zeros(3)
    with pytest.raises(ValidationError):
        GeoFrame(
            lat=lat,
            lon=np.zeros(2),
            heading_deg=lat,
            row_to_ping=np.arange(3),
            nadir_col=0,
            ground_res_m=0.1,
        )
    with pytest.raises(ValidationError):
        GeoFrame(
            lat=lat,
            lon=lat,
            heading_deg=lat,
            row_to_ping=np.array([0, 5]),
            nadir_col=0,
            ground_res_m=0.1,
        )
    with pytest.raises(ValidationError):
        GeoFrame(
            lat=lat,
            lon=lat,
            heading_deg=lat,
            row_to_ping=np.arange(3),
            nadir_col=0,
            ground_res_m=0.0,
        )
    frame = GeoFrame(
        lat=lat, lon=lat, heading_deg=lat, row_to_ping=np.arange(3), nadir_col=0, ground_res_m=0.1
    )
    with pytest.raises(ValidationError):
        pixel_to_latlon(3, 0, frame)


def test_coordinate_formatting() -> None:
    """TC-GEO-014."""
    assert format_decimal(13.08412) == "13.084120"
    assert to_dms(13.084120, "lat") == "13° 05' 02.83\" N"
    assert to_dms(80.312750, "lon") == "80° 18' 45.90\" E"
    assert to_dms(-33.9, "lat") == "33° 54' 00.00\" S"
    assert to_dms(10.999999, "lon") == "11° 00' 00.00\" E"  # carries instead of 60.00"
    with pytest.raises(ValidationError):
        to_dms(91.0, "lat")
