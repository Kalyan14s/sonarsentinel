"""XTF reader on synthetic survey TD-01 and its corrupt/truncated variants TD-05.

TC-ING-002 (corrupt header), TC-ING-005 (exact parse), TC-ING-007 (units), TC-ING-008 (UTM
equivalence), TC-ING-012 (truncated file), TC-GEO-001/002 on raw slant-range pings, ST-026 chunks.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyxtf")
from pyproj import Geod  # noqa: E402
from tools.make_synthetic_xtf import (  # noqa: E402
    SyntheticSurvey,
    corrupt_header,
    truncate,
    write_synthetic_xtf,
)

from sonarsentinel.errors import CorruptHeaderError, CrsRequiredError  # noqa: E402
from sonarsentinel.geo.georef import slant_samples_to_latlon  # noqa: E402
from sonarsentinel.ingest.chunking import chunk_ranges, iter_chunks  # noqa: E402
from sonarsentinel.ingest.models import TRUNCATED_FILE  # noqa: E402
from sonarsentinel.ingest.xtf_reader import (  # noqa: E402
    detect_port_order,
    read_xtf,
    scan_xtf,
)

GEOD = Geod(ellps="WGS84")
TOL_M = 0.05


@pytest.fixture(scope="module")
def straight(tmp_path_factory: pytest.TempPathFactory) -> SyntheticSurvey:
    path = tmp_path_factory.mktemp("td01") / "straight.xtf"
    return write_synthetic_xtf(path, n_pings=300, samples_per_side=800, track="straight")


def test_parse_matches_generated_values(straight: SyntheticSurvey) -> None:
    """TC-ING-005."""
    log = read_xtf(straight.path)
    assert log.source_format == "xtf"
    assert log.n_pings == straight.n_pings
    assert log.sonar.channel_layout == "port_stbd"
    assert log.sonar.samples_per_channel == straight.samples_per_side
    assert log.sonar.model == "SYNTH-SSS"
    assert log.sonar.frequency_khz == pytest.approx(600.0)
    assert log.warnings == []

    nav = log.nav
    np.testing.assert_allclose(nav["lat"], straight.lat, atol=1e-12)
    np.testing.assert_allclose(nav["lon"], straight.lon, atol=1e-12)
    np.testing.assert_allclose(nav["heading_deg"], straight.heading_deg, atol=1e-4)
    np.testing.assert_allclose(nav["altitude_m"], straight.altitude_m, atol=1e-5)
    np.testing.assert_allclose(nav["sensor_depth_m"], straight.sensor_depth_m, atol=1e-5)
    np.testing.assert_allclose(nav["slant_range_m"], straight.slant_range_m)
    np.testing.assert_allclose(nav["speed_mps"], straight.speed_mps, rtol=1e-5)
    np.testing.assert_allclose(nav["roll_deg"], 0.5, atol=1e-6)
    np.testing.assert_allclose(nav["cable_out_m"], 25.0)
    assert set(nav["nav_source"]) == {"sensor"}
    assert nav["ping"].tolist() == list(range(straight.n_pings))
    assert nav["time_utc"].iloc[0] == pd.Timestamp(straight.start_utc)
    assert nav["time_utc"].iloc[15] == pd.Timestamp(straight.start_utc) + pd.Timedelta(seconds=1.5)


def test_port_is_reordered_to_nadir_first(straight: SyntheticSurvey) -> None:
    log = read_xtf(straight.path)
    assert log.port is not None and log.starboard is not None
    water = int(straight.altitude_m / straight.slant_range_m * straight.samples_per_side)
    for side, array in (("port", log.port), ("starboard", log.starboard)):
        assert np.all(array[:, :water] == 5), side  # dark water column next to nadir
        assert array[:, water:].mean() > 200
        for t in straight.targets:
            if t.side == side:
                assert array[t.ping, t.sample] == straight.target_level


def test_nadir_first_port_files_are_detected(tmp_path: Path) -> None:
    survey = write_synthetic_xtf(tmp_path / "nf.xtf", n_pings=50, port_order="nadir_first")
    log = read_xtf(survey.path)
    assert log.port is not None
    water = int(survey.altitude_m / survey.slant_range_m * survey.samples_per_side)
    assert np.all(log.port[:, :water] == 5)
    forced = read_xtf(survey.path, port_order="far_first")
    assert forced.port is not None and np.all(forced.port[:, -water:] == 5)


@pytest.mark.parametrize("track", ["straight", "curved"])
def test_raw_slant_pings_geotag_to_targets(tmp_path: Path, track: str) -> None:
    """TC-GEO-001/002 on raw slant-range data: target samples map to their true positions."""
    survey = write_synthetic_xtf(tmp_path / f"{track}.xtf", n_pings=400, track=track)  # type: ignore[arg-type]
    log = read_xtf(survey.path)
    pings = np.array([t.ping for t in survey.targets])
    sides = np.array([t.side for t in survey.targets])
    samples = np.array([t.sample for t in survey.targets])
    lat, lon = slant_samples_to_latlon(pings, sides, samples, log)
    _, _, err = GEOD.inv([t.lon for t in survey.targets], [t.lat for t in survey.targets], lon, lat)
    assert np.max(err) < TOL_M


def test_projected_navigation_needs_epsg_and_matches(tmp_path: Path) -> None:
    """TC-ING-007 and TC-ING-008: NavUnits 0 without EPSG fails; with EPSG matches lat/lon copy."""
    geo = write_synthetic_xtf(tmp_path / "ll.xtf", n_pings=120, track="curved")
    utm = write_synthetic_xtf(tmp_path / "utm.xtf", n_pings=120, track="curved", utm_epsg=32644)
    with pytest.raises(CrsRequiredError) as exc_info:
        read_xtf(utm.path)
    assert exc_info.value.code == "CRS_REQUIRED"

    a = read_xtf(geo.path)
    b = read_xtf(utm.path, epsg=32644)
    _, _, track_err = GEOD.inv(a.nav["lon"], a.nav["lat"], b.nav["lon"], b.nav["lat"])
    assert np.max(track_err) < 0.1

    pings = np.array([t.ping for t in geo.targets])
    sides = np.array([t.side for t in geo.targets])
    samples = np.array([t.sample for t in geo.targets])
    lat_a, lon_a = slant_samples_to_latlon(pings, sides, samples, a)
    lat_b, lon_b = slant_samples_to_latlon(pings, sides, samples, b)
    _, _, det_err = GEOD.inv(lon_a, lat_a, lon_b, lat_b)
    assert np.max(det_err) < 0.1


def test_ship_position_fallback(tmp_path: Path) -> None:
    survey = write_synthetic_xtf(tmp_path / "ship.xtf", n_pings=30, write_sensor_position=False)
    log = read_xtf(survey.path)
    assert "SHIP_POSITION_ONLY" in log.warnings
    assert set(log.nav["nav_source"]) == {"ship"}
    np.testing.assert_allclose(log.nav["lat"], survey.lat, atol=1e-12)


def test_no_navigation_is_flagged(tmp_path: Path) -> None:
    survey = write_synthetic_xtf(
        tmp_path / "nonav.xtf", n_pings=20, write_sensor_position=False, write_ship_position=False
    )
    log = read_xtf(survey.path)
    assert "NO_NAVIGATION" in log.warnings
    assert not log.has_navigation


def test_corrupt_header_is_rejected(straight: SyntheticSurvey, tmp_path: Path) -> None:
    """TC-ING-002."""
    bad = corrupt_header(straight.path, tmp_path / "bad.xtf")
    with pytest.raises(CorruptHeaderError) as exc_info:
        read_xtf(bad)
    assert exc_info.value.http_status == 422
    header_only = tmp_path / "header_only.xtf"
    header_only.write_bytes(Path(straight.path).read_bytes()[:1024])
    with pytest.raises(CorruptHeaderError, match="no readable sonar pings"):
        read_xtf(header_only)


def test_truncated_file_keeps_valid_pings(straight: SyntheticSurvey, tmp_path: Path) -> None:
    """TC-ING-012 (reader part): readable pings are kept and TRUNCATED_FILE is raised."""
    cut = truncate(straight.path, tmp_path / "cut.xtf", drop_bytes=1000)
    log = read_xtf(cut)
    assert log.n_pings == straight.n_pings - 1
    assert log.warnings == [TRUNCATED_FILE]
    np.testing.assert_allclose(log.nav["lat"], straight.lat[:-1], atol=1e-12)


def test_scan_does_not_read_samples(straight: SyntheticSurvey) -> None:
    scan = scan_xtf(straight.path)
    assert scan.n_pings == straight.n_pings
    assert scan.max_samples == {"port": 800, "starboard": 800}
    assert scan.nav_units == 3 and not scan.truncated


def test_memory_mapped_read_matches_in_memory(straight: SyntheticSurvey, tmp_path: Path) -> None:
    """ST-026: samples written to .npy memmaps are identical to the in-memory read."""
    in_ram = read_xtf(straight.path)
    mapped = read_xtf(straight.path, work_dir=tmp_path / "work")
    assert isinstance(mapped.port, np.memmap) and isinstance(mapped.starboard, np.memmap)
    assert in_ram.port is not None and in_ram.starboard is not None
    np.testing.assert_array_equal(mapped.port, in_ram.port)
    np.testing.assert_array_equal(mapped.starboard, in_ram.starboard)
    assert (tmp_path / "work" / "straight_port.npy").exists()


def test_chunks_cover_all_pings_with_overlap(straight: SyntheticSurvey, tmp_path: Path) -> None:
    assert chunk_ranges(300, 100, 20) == [(0, 100), (80, 180), (160, 260), (240, 300)]
    assert chunk_ranges(100, 100, 20) == [(0, 100)]
    assert chunk_ranges(0) == []
    log = read_xtf(straight.path, work_dir=tmp_path / "work")
    chunks = list(iter_chunks(log, size=100, overlap=20))
    assert [offset for offset, _ in chunks] == [0, 80, 160, 240]
    offset, chunk = chunks[1]
    assert chunk.n_pings == 100 and chunk.nav["ping"].iloc[0] == 80
    assert chunk.port is not None and log.port is not None
    assert np.shares_memory(chunk.port, log.port)  # a view, not a copy
    np.testing.assert_array_equal(chunk.port, log.port[80:180])


@pytest.mark.parametrize("order", ["far_first", "nadir_first"])
def test_port_order_detected_in_shallow_water(tmp_path: Path, order: str) -> None:
    """Brightest at nadir with no dark water column (like the USGS Klein 3900 lines)."""
    survey = write_synthetic_xtf(
        tmp_path / f"{order}.xtf",
        n_pings=60,
        samples_per_side=1024,
        port_order=order,  # type: ignore[arg-type]
        profile="attenuation",
        targets=[],
    )
    assert detect_port_order(scan_xtf(survey.path)) == order
    log = read_xtf(survey.path)
    assert log.warnings == []
    assert log.port is not None and log.starboard is not None
    assert log.port[:, :100].mean() > 3 * log.port[:, -100:].mean()  # nadir first after reading
    assert log.starboard[:, :100].mean() > 3 * log.starboard[:, -100:].mean()
