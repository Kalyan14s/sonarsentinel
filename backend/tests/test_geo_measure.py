"""TC-GEO-006 (measurements), TC-GEO-007 (footprint), TC-GEO-008 (depth): ST-033."""

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from pyproj import Geod  # noqa: E402

from sonarsentinel.errors import ValidationError  # noqa: E402
from sonarsentinel.geo.georef import GeoFrame  # noqa: E402
from sonarsentinel.geo.measure import (  # noqa: E402
    ImageGeometry,
    measure_mask,
    order_clockwise,
    orientation_from_heading,
)

GEOD = Geod(ellps="WGS84")
RES = 0.1


def _geometry(n_rows: int = 400, heading: float = 0.0, geotagged: bool = True) -> ImageGeometry:
    lon, lat, _ = GEOD.fwd(
        np.full(n_rows, 80.30),
        np.full(n_rows, 13.08),
        np.full(n_rows, heading),
        np.arange(n_rows) * RES,
    )
    frame = GeoFrame(
        lat=np.asarray(lat),
        lon=np.asarray(lon),
        heading_deg=np.full(n_rows, heading),
        row_to_ping=np.arange(n_rows),
        nadir_col=300,
        ground_res_m=RES,
    )
    return ImageGeometry(
        ground_res_m=RES,
        nadir_col=300,
        row_to_ping=np.arange(n_rows),
        ping_offset=1000,
        frame=frame if geotagged else None,
        heading_deg=np.full(n_rows, heading),
        sensor_depth_m=np.full(n_rows, 10.2),
        altitude_m=np.full(n_rows, 8.0),
    )


def _rotated_rectangle(
    shape: tuple[int, int],
    centre: tuple[float, float],
    length_px: float,
    width_px: float,
    angle_deg: float,
) -> np.ndarray:
    """Long axis at ``angle_deg`` clockwise from +rows (forward) towards +cols (starboard)."""
    # Pixel-centre sampling like a segmentation mask (fillPoly would add every touched edge pixel).
    a = math.radians(angle_deg)
    rows, cols = np.mgrid[0 : shape[0], 0 : shape[1]].astype(np.float64)
    dr, dc = rows - centre[0], cols - centre[1]
    along = dc * math.sin(a) + dr * math.cos(a)
    across = dc * math.cos(a) - dr * math.sin(a)
    return (np.abs(along) <= length_px / 2) & (np.abs(across) <= width_px / 2)


def test_rectangle_dimensions_and_orientation() -> None:
    """TC-GEO-006: 6.2 × 3.1 m at 12° → ±0.1 m, area ±5%, orientation ±2°."""
    mask = _rotated_rectangle((400, 600), (200.0, 420.0), 62, 31, 12.0)
    m = measure_mask(mask, _geometry())
    assert m.length_m == pytest.approx(6.2, abs=0.1)
    assert m.width_m == pytest.approx(3.1, abs=0.1)
    assert m.area_m2 == pytest.approx(6.2 * 3.1, rel=0.05)
    assert m.orientation_deg is not None and abs(m.orientation_deg - 12.0) <= 2.0
    assert m.side == "starboard" and m.ground_range_m == pytest.approx(12.0, abs=0.1)
    assert m.ping == 1200


def test_orientation_follows_heading() -> None:
    mask = _rotated_rectangle((400, 600), (200.0, 150.0), 62, 31, 12.0)
    m = measure_mask(mask, _geometry(heading=90.0))
    assert m.side == "port"
    assert m.orientation_deg is not None and abs(m.orientation_deg - 102.0) <= 2.0
    assert orientation_from_heading(1.0, 0.0, 350.0) == pytest.approx(80.0)  # 440 mod 180


def _inside(point: tuple[float, float], poly: list[list[float]]) -> bool:
    lat, lon = point
    inside = False
    for (la1, lo1), (la2, lo2) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (la1 > lat) != (la2 > lat):
            cross = lo1 + (lat - la1) * (lo2 - lo1) / (la2 - la1)
            if lon < cross:
                inside = not inside
    return inside


def test_footprint_is_clockwise_and_contains_centroid() -> None:
    """TC-GEO-007."""
    mask = _rotated_rectangle((400, 600), (200.0, 420.0), 62, 31, 12.0)
    m = measure_mask(mask, _geometry())
    assert m.footprint is not None and len(m.footprint) == 4
    assert m.lat is not None and m.lon is not None
    lat0 = math.radians(m.lat)
    area = sum(
        (a[1] * math.cos(lat0)) * b[0] - (b[1] * math.cos(lat0)) * a[0]
        for a, b in zip(m.footprint, m.footprint[1:] + m.footprint[:1], strict=True)
    )
    assert area < 0  # clockwise with x = lon, y = lat
    assert _inside((m.lat, m.lon), m.footprint)
    _, _, dist = GEOD.inv(80.30, 13.08, m.lon, m.lat)
    expected = math.hypot(20.0, 12.0)  # 200 rows forward, 120 cols to starboard
    assert dist == pytest.approx(expected, abs=0.15)
    shuffled = [m.footprint[2], m.footprint[0], m.footprint[3], m.footprint[1]]
    assert order_clockwise(shuffled) in (
        m.footprint[i:] + m.footprint[:i] for i in range(4)
    )  # same cyclic order


def test_depth_and_missing_values() -> None:
    """TC-GEO-008: depth = sensor depth + altitude; null when either is missing."""
    mask = np.zeros((400, 600), bool)
    mask[100:110, 350:360] = True
    geo = _geometry()
    assert measure_mask(mask, geo).depth_m == pytest.approx(18.2)
    alt = geo.altitude_m.copy()  # type: ignore[union-attr]
    alt[:] = np.nan
    no_alt = ImageGeometry(**{**geo.__dict__, "altitude_m": alt})
    assert measure_mask(mask, no_alt).depth_m is None


def test_not_geotagged_and_offsets() -> None:
    crop = np.ones((10, 20), bool)
    m = measure_mask(crop, _geometry(geotagged=False), row0=50, col0=100)
    assert m.lat is None and m.footprint is None
    assert m.centroid_row == pytest.approx(54.5) and m.centroid_col == pytest.approx(109.5)
    assert m.length_m == pytest.approx(2.0) and m.width_m == pytest.approx(1.0)
    with pytest.raises(ValidationError):
        measure_mask(np.zeros((3, 3), bool), _geometry())
