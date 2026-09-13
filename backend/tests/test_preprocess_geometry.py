"""TC-PRE-003 (slant-range correction), TC-PRE-004 (along-track resampling), preprocessing chain."""

import numpy as np
import pytest

pytest.importorskip("scipy")
pytest.importorskip("pyxtf")

from pyproj import Geod  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.geo.georef import pixels_to_latlon  # noqa: E402
from sonarsentinel.ingest.models import NOT_GEOTAGGED  # noqa: E402
from sonarsentinel.ingest.xtf_reader import read_xtf  # noqa: E402
from sonarsentinel.preprocess.geometry import (  # noqa: E402
    along_track_rows,
    build_ground_image,
    cumulative_distance_m,
    ground_bins,
    near_nadir_columns,
    slant_to_ground,
)
from sonarsentinel.preprocess.pipeline import preprocess_chunk, preprocess_log  # noqa: E402

GEOD = Geod(ellps="WGS84")


def test_object_lands_at_its_ground_range() -> None:
    """TC-PRE-003: an object at 20 m ground range is at column nadir ± 200 (±1)."""
    n_samples, slant_max, altitude = 2000, 50.0, 8.0
    sample = int(round(np.sqrt(20.0**2 + altitude**2) / slant_max * n_samples))
    side = np.full((10, n_samples), 10.0, dtype=np.float32)
    side[:, sample] = 1000.0
    n = ground_bins(slant_max, altitude, 0.1) + 1
    ground = slant_to_ground(side, slant_max, altitude, ground_res_m=0.1, n_ground=n)
    image, nadir = build_ground_image(ground, ground, np.arange(10))
    stbd_peak = int(np.argmax(image[0, nadir:])) + nadir
    port_peak = int(np.argmax(image[0, :nadir]))
    assert abs(stbd_peak - (nadir + 200)) <= 1
    assert abs(port_peak - (nadir - 200)) <= 1
    assert image.shape[1] == 2 * (n - 1)


def test_ground_image_matches_georef_convention() -> None:
    ground = np.arange(6, dtype=np.float32)[None, :].repeat(2, axis=0)  # value = bin index
    image, nadir = build_ground_image(ground * 10, ground, np.array([0, 1]))
    assert nadir == 5
    assert image[0].tolist() == [50, 40, 30, 20, 10, 0, 1, 2, 3, 4]
    # column c: side by c >= nadir, ground bin |c - nadir| (port k=5 at col 0, stbd k=0 at nadir)


def test_variable_speed_resampling() -> None:
    """TC-PRE-004: a 5 m object spans 50 ± 1 rows whatever the ping spacing."""
    rng = np.random.default_rng(0)
    steps = rng.uniform(0.03, 0.25, 800)  # 3–25 cm per ping
    distance = np.concatenate([[0.0], np.cumsum(steps)])
    lon, lat, _ = GEOD.fwd(np.full(801, 80.3), np.full(801, 13.08), np.full(801, 45.0), distance)
    rows = along_track_rows(lat, lon, 0.1)
    assert np.allclose(cumulative_distance_m(lat, lon), distance, atol=1e-6)
    for start in (10.0, 40.0, 70.0):
        pings = np.flatnonzero((distance >= start) & (distance < start + 5.0))
        spanned = np.isin(rows, pings).sum()
        assert abs(spanned - 50) <= 1, (start, spanned)


def test_slant_beyond_range_is_zero_and_near_nadir_mask() -> None:
    side = np.ones((1, 100), dtype=np.float32)
    out = slant_to_ground(side, 10.0, 6.0, ground_res_m=0.5, n_ground=30)
    # bin 15 (7.5 m) needs slant sample 96; bin 16 (8.0 m) would need sample 100 (> last, 99)
    assert out[0, :16].min() == 1.0 and np.all(out[0, 16:] == 0)
    mask = near_nadir_columns(10, 5, 1.0, altitude_m=10.0)
    assert mask.tolist() == [False, False, False, True, True, True, True, True, False, False]


def test_chain_places_target_correctly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """End to end on TD-01: after S2–S7 a target pixel still geotags to its true position."""
    survey = write_synthetic_xtf(
        tmp_path / "td01.xtf", n_pings=1200, samples_per_side=1000, step_m=0.1, track="curved"
    )
    log = read_xtf(survey.path)
    config = load_config()
    chunks = list(preprocess_log(log, config))
    assert [c.ping_offset for c in chunks] == [0]
    chunk = chunks[0]
    assert chunk.image.dtype == np.uint8 and chunk.image_3ch.shape == (*chunk.image.shape, 3)
    assert chunk.image.shape[1] == 2 * chunk.nadir_col
    assert abs(len(chunk.row_to_ping) - 1200) <= 2  # 0.1 m pings resampled at 0.1 m
    frame = chunk.geo_frame()
    for target in survey.targets:
        rows = np.flatnonzero(chunk.row_to_ping == target.ping)
        k = int(round(target.ground_range_m / chunk.ground_res_m))
        col = chunk.nadir_col + k if target.side == "starboard" else chunk.nadir_col - k
        lat, lon = pixels_to_latlon(rows[:1], np.array([col]), frame)
        _, _, err = GEOD.inv(target.lon, target.lat, lon[0], lat[0])
        assert err < 0.15, target  # quantisation to 0.1 m plus smoothing
        window = chunk.image[rows[0], col - 2 : col + 3]
        assert window.max() >= np.percentile(chunk.image[rows[0]], 99)  # target still stands out
    assert "NO_ALTITUDE_BOTTOM_TRACKED" not in chunk.warnings  # recorded altitude agrees


def test_chunks_follow_config_and_image_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    survey = write_synthetic_xtf(tmp_path / "long.xtf", n_pings=500, samples_per_side=400)
    log = read_xtf(survey.path)
    config = load_config()
    config["chunking"] = {"pings_per_chunk": 200, "overlap_pings": 20}
    offsets = [c.ping_offset for c in preprocess_log(log, config)]
    assert offsets == [0, 180, 360]

    log.nav["lat"] = np.nan
    log.nav["lon"] = np.nan
    log.nav["slant_range_m"] = np.nan
    log.warnings.append(NOT_GEOTAGGED)
    chunk = preprocess_chunk(log, config)
    assert not chunk.geotagged and chunk.image.shape == (500, 800)
    with pytest.raises(Exception, match="NOT_GEOTAGGED"):
        chunk.geo_frame()
