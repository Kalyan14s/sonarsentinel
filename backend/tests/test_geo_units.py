"""TC-ING-007 / TC-ING-008: coordinate units and UTM equivalence."""

import numpy as np
import pytest
from pyproj import Geod, Transformer

from sonarsentinel.errors import CrsRequiredError, ValidationError
from sonarsentinel.geo.units import (
    XTF_NAV_UNITS_LATLON,
    XTF_NAV_UNITS_METERS,
    looks_geographic,
    to_wgs84,
    utm_epsg_for,
)

GEOD = Geod(ellps="WGS84")
LAT = np.linspace(13.080, 13.090, 50)  # track off Chennai
LON = np.linspace(80.305, 80.320, 50)


def test_looks_geographic() -> None:
    assert looks_geographic(LON, LAT)
    assert not looks_geographic([412345.0], [1446789.0])
    assert looks_geographic([0.0, 80.3], [0.0, 13.1])  # (0, 0) fixes are ignored
    assert not looks_geographic([np.nan], [np.nan])


@pytest.mark.parametrize(
    ("lon", "lat", "epsg"),
    [
        (80.31, 13.08, 32644),
        (72.8, 19.0, 32643),
        (88.4, 21.9, 32645),
        (151.2, -33.9, 32756),
        (180.0, 0.0, 32660),
    ],
)
def test_utm_epsg_for(lon: float, lat: float, epsg: int) -> None:
    assert utm_epsg_for(lon, lat) == epsg


def test_utm_epsg_rejects_polar() -> None:
    with pytest.raises(ValidationError):
        utm_epsg_for(10.0, 85.0)


def test_geographic_passthrough_by_header() -> None:
    lat, lon = to_wgs84(LON, LAT, nav_units=XTF_NAV_UNITS_LATLON)
    np.testing.assert_array_equal(lat, LAT)
    np.testing.assert_array_equal(lon, LON)


def test_projected_without_epsg_requires_crs() -> None:
    """TC-ING-007: projected coordinates without an EPSG code raise CRS_REQUIRED."""
    with pytest.raises(CrsRequiredError) as exc_info:
        to_wgs84([412345.0], [1446789.0], nav_units=XTF_NAV_UNITS_METERS)
    assert exc_info.value.code == "CRS_REQUIRED"
    with pytest.raises(CrsRequiredError):
        to_wgs84([412345.0], [1446789.0], epsg="auto")


def test_utm_and_latlon_give_same_positions() -> None:
    """TC-ING-008: the same track in degrees and in UTM metres agrees within 0.1 m."""
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)
    easting, northing = fwd.transform(LON, LAT)
    lat_back, lon_back = to_wgs84(easting, northing, nav_units=XTF_NAV_UNITS_METERS, epsg=32644)
    _, _, dist = GEOD.inv(LON, LAT, lon_back, lat_back)
    assert np.max(np.abs(dist)) < 0.1


def test_geographic_crs_given_for_projected_values_is_rejected() -> None:
    with pytest.raises(ValidationError):
        to_wgs84([412345.0], [1446789.0], epsg=4326)


def test_shape_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        to_wgs84([1.0, 2.0], [1.0])
