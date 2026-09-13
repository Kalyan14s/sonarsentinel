"""Reader dispatch (S0 + S1), track export and the ``inspect`` / ``track`` CLI commands."""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pyxtf")
cv2 = pytest.importorskip("cv2")
from pyproj import Geod  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from sonarsentinel.cli import app  # noqa: E402
from sonarsentinel.errors import UnsupportedFormatError, ValidationError  # noqa: E402
from sonarsentinel.geo.track import track_bbox, track_geojson, track_length_km  # noqa: E402
from sonarsentinel.ingest.reader import read_source, summarize  # noqa: E402

runner = CliRunner()
GEOD = Geod(ellps="WGS84")


@pytest.fixture(scope="module")
def xtf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("td01") / "line.xtf"
    write_synthetic_xtf(path, n_pings=200, samples_per_side=400, step_m=0.5)
    return path


def test_xtf_summary(xtf: Path) -> None:
    log = read_source(xtf)
    summary = summarize(log, xtf.stat().st_size)
    assert summary["format"] == "xtf" and summary["pings"] == 200
    assert summary["sonar"]["channels"] == 2
    assert summary["has_navigation"] and summary["warnings"] == []
    assert summary["start_utc"] == "2026-09-12T05:10:02.00Z"
    assert summary["end_utc"] == "2026-09-12T05:10:21.90Z"
    assert summary["track_length_km"] == pytest.approx(199 * 0.5 / 1000, abs=1e-3)
    min_lon, min_lat, max_lon, max_lat = summary["bbox"]
    assert min_lon < max_lon and min_lat < max_lat


def test_track_geojson(xtf: Path) -> None:
    log = read_source(xtf)
    geo = track_geojson(log, every=50)
    coords = geo["features"][0]["geometry"]["coordinates"]
    assert len(coords) == 5  # pings 0, 50, 100, 150 and the last one
    lon, lat = coords[-1]
    assert lat == pytest.approx(log.nav["lat"].iloc[-1], abs=1e-6)
    assert lon == pytest.approx(log.nav["lon"].iloc[-1], abs=1e-6)
    assert track_length_km(log) == pytest.approx(0.0995, abs=1e-4)
    assert track_bbox(log) is not None


def test_image_without_nav_needs_permission(tmp_path: Path) -> None:
    img = tmp_path / "harbour.png"
    cv2.imwrite(str(img), np.full((20, 40), 90, dtype=np.uint8))
    with pytest.raises(ValidationError, match="no navigation"):
        read_source(img)
    log = read_source(img, allow_no_gps=True)
    assert log.warnings == ["NOT_GEOTAGGED"]
    summary = summarize(log)
    assert not summary["has_navigation"] and "bbox" not in summary


def test_csv_alone_is_unsupported(tmp_path: Path) -> None:
    f = tmp_path / "nav.csv"
    f.write_text("ping,lat,lon\n0,13.0,80.0\n", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        read_source(f)


def test_cli_inspect(xtf: Path) -> None:
    result = runner.invoke(app, ["inspect", str(xtf)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["pings"] == 200 and data["format"] == "xtf"


def test_cli_inspect_reports_coded_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xtf"
    bad.write_bytes(b"\x7b" + b"\x00" * 2000)
    result = runner.invoke(app, ["inspect", str(bad)])
    assert result.exit_code == 1
    assert "CORRUPT_HEADER" in result.output


def test_cli_track(xtf: Path, tmp_path: Path) -> None:
    out = tmp_path / "track.geojson"
    result = runner.invoke(app, ["track", str(xtf), "--out", str(out), "--every", "10"])
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["features"][0]["geometry"]["type"] == "LineString"
    assert data["features"][0]["properties"]["pings"] == 200


def test_cli_projected_track_needs_epsg(tmp_path: Path) -> None:
    utm = tmp_path / "utm.xtf"
    write_synthetic_xtf(utm, n_pings=20, samples_per_side=100, utm_epsg=32644)
    result = runner.invoke(app, ["inspect", str(utm)])
    assert result.exit_code == 1 and "CRS_REQUIRED" in result.output
    result = runner.invoke(app, ["inspect", str(utm), "--utm-epsg", "32644"])
    assert result.exit_code == 0, result.output
