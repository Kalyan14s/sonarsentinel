"""ST-036 GCP-based georeferenced mosaic (TC-GEO-011)."""

import json
from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
cv2 = pytest.importorskip("cv2")

from sonarsentinel.errors import ValidationError  # noqa: E402
from sonarsentinel.geo.georef import GEOD, GeoFrame, pixels_to_latlon  # noqa: E402
from sonarsentinel.geo.mosaic import MosaicBuilder  # noqa: E402

RES = 0.10
N_PINGS = 400
NADIR = 200
WIDTH = 401


def _frame(turn_deg_per_ping: float, rows: slice | None = None) -> GeoFrame:
    rows = slice(None) if rows is None else rows
    lat, lon, heading = [13.08], [80.31], [30.0]
    for _ in range(N_PINGS - 1):
        next_lon, next_lat, _ = GEOD.fwd(lon[-1], lat[-1], heading[-1], RES)
        lat.append(float(next_lat))
        lon.append(float(next_lon))
        heading.append((heading[-1] + turn_deg_per_ping) % 360.0)
    return GeoFrame(
        lat=np.array(lat),
        lon=np.array(lon),
        heading_deg=np.array(heading),
        row_to_ping=np.arange(N_PINGS, dtype=np.int64)[rows],
        nadir_col=NADIR,
        ground_res_m=RES,
    )


def _image(rows: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(40, 200, (rows, WIDTH), dtype=np.uint8)


@pytest.mark.parametrize("turn", [0.0, 0.1])
def test_mosaic_residual_bounds_and_files(tmp_path: Path, turn: float) -> None:
    """TC-GEO-011: straight and curved (40° over the line) tracks, GCP residual < 1 m."""
    builder = MosaicBuilder(ground_res_m_out=0.10)
    first, second = _frame(turn, slice(0, 220)), _frame(turn, slice(180, N_PINGS))
    image_a, image_b = _image(220, 1), _image(220, 2)
    image_a[100:105, 300:305] = 255  # marker to find in the output
    builder.add(image_a, first)
    builder.add(image_b, second)
    result = builder.finish(tmp_path)

    assert result.gcp_residual_max_m < 1.0
    (south, west), (north, east) = result.bounds
    track = _frame(turn)
    assert south <= track.lat.min() and track.lat.max() <= north
    assert west <= track.lon.min() and track.lon.max() <= east

    with rasterio.open(result.tif) as dataset:
        assert dataset.crs.to_epsg() == 4326
        assert dataset.nodata == 0
        data = dataset.read(1)
        marker_rows, marker_cols = np.nonzero(data == 255)
        assert marker_rows.size, "marker missing from the mosaic"
        xs, ys = rasterio.transform.xy(
            dataset.transform, [float(marker_rows.mean())], [float(marker_cols.mean())]
        )
    true_lat, true_lon = pixels_to_latlon(np.array([102]), np.array([302]), first)
    _, _, offset = GEOD.inv(xs[0], ys[0], float(true_lon[0]), float(true_lat[0]))
    assert abs(offset) < 1.0

    png = cv2.imread(str(result.png), cv2.IMREAD_UNCHANGED)
    assert png.shape[2] == 4
    assert (png[..., 3] == 0).any() and (png[..., 3] == 255).any()
    saved = json.loads(result.bounds_json.read_text("utf-8"))
    assert saved["bounds"] == [list(result.bounds[0]), list(result.bounds[1])]
    assert saved["crs"] == "EPSG:4326"


def test_output_is_coarsened_to_the_pixel_cap(tmp_path: Path) -> None:
    builder = MosaicBuilder(ground_res_m_out=0.10, max_pixels=20_000)
    builder.add(_image(N_PINGS), _frame(0.0))
    result = builder.finish(tmp_path)
    assert result.shape[0] * result.shape[1] <= 20_000 * 1.05
    assert result.ground_res_m > 0.10


def test_downsampled_chunks_and_empty_builder(tmp_path: Path) -> None:
    builder = MosaicBuilder(ground_res_m_out=0.25)
    builder.add(_image(N_PINGS), _frame(0.05))
    result = builder.finish(tmp_path)
    assert result.ground_res_m == 0.25 and result.gcp_residual_max_m < 1.0
    with pytest.raises(ValidationError):
        MosaicBuilder().finish(tmp_path / "empty")
