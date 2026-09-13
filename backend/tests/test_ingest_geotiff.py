"""TC-ING-009: GeoTIFF reader and raster pixel → WGS84 conversion."""

from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from pyproj import Transformer  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

from sonarsentinel.errors import CorruptHeaderError, CrsRequiredError  # noqa: E402
from sonarsentinel.geo.georef import raster_pixels_to_latlon  # noqa: E402
from sonarsentinel.ingest.geotiff_reader import read_geotiff  # noqa: E402

RES_M = 0.25
ORIGIN = (412_000.0, 1_447_000.0)  # UTM 44N, off Chennai


def _write_tiff(path: Path, crs: str | None = "EPSG:32644") -> None:
    data = (np.arange(200 * 300) % 251).astype(np.uint8).reshape(200, 300)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=200,
        width=300,
        count=1,
        dtype="uint8",
        crs=crs,
        transform=from_origin(ORIGIN[0], ORIGIN[1], RES_M, RES_M),
    ) as dst:
        dst.write(data, 1)


def test_reads_image_transform_and_crs(tmp_path: Path) -> None:
    f = tmp_path / "mosaic.tif"
    _write_tiff(f)
    log = read_geotiff(f)
    assert log.source_format == "geotiff"
    assert log.image is not None and log.image.shape == (200, 300)
    assert log.crs_hint == "EPSG:32644"
    assert log.geotransform == (ORIGIN[0], RES_M, 0.0, ORIGIN[1], 0.0, -RES_M)
    assert log.n_pings == 0


def test_pixels_match_rasterio_within_one_pixel(tmp_path: Path) -> None:
    """Five pixels converted by our code agree with rasterio's own pixel centres."""
    f = tmp_path / "mosaic.tif"
    _write_tiff(f)
    log = read_geotiff(f)
    assert log.geotransform is not None and log.crs_hint is not None
    rows = np.array([0, 10, 99, 150, 199])
    cols = np.array([0, 250, 150, 7, 299])
    lat, lon = raster_pixels_to_latlon(rows, cols, log.geotransform, log.crs_hint)

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)
    x, y = to_utm.transform(lon, lat)
    with rasterio.open(f) as ds:
        ref_x, ref_y = ds.transform @ (cols + 0.5, rows + 0.5)  # rasterio's pixel centres
    error_m = np.hypot(np.asarray(ref_x) - x, np.asarray(ref_y) - y)
    assert np.max(error_m) < RES_M  # well inside one pixel
    assert np.max(error_m) < 1e-6


def test_missing_crs_requires_epsg(tmp_path: Path) -> None:
    f = tmp_path / "nocrs.tif"
    _write_tiff(f, crs=None)
    with pytest.raises(CrsRequiredError):
        read_geotiff(f)
    assert read_geotiff(f, epsg=32644).crs_hint == "EPSG:32644"


def test_not_a_tiff_is_corrupt(tmp_path: Path) -> None:
    f = tmp_path / "broken.tif"
    f.write_bytes(b"II*\x00" + b"\x00" * 20)
    with pytest.raises(CorruptHeaderError):
        read_geotiff(f)
