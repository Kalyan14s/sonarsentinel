"""TC-ING-004, TC-ING-010, TC-ING-011: waterfall image with and without a navigation CSV."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

cv2 = pytest.importorskip("cv2")
from pyproj import Geod, Transformer  # noqa: E402

from sonarsentinel.errors import (  # noqa: E402
    CorruptHeaderError,
    CrsRequiredError,
    NavCsvInvalidError,
)
from sonarsentinel.ingest.image_nav_reader import (  # noqa: E402
    read_image_nav,
    read_image_only,
    read_nav_csv,
    split_channels,
)
from sonarsentinel.ingest.models import (  # noqa: E402
    GPS_INTERPOLATED,
    HEADING_FROM_COG,
    NOT_GEOTAGGED,
)

GEOD = Geod(ellps="WGS84")
ROWS, COLS = 101, 400


def _png(path: Path) -> Path:
    image = np.zeros((ROWS, COLS), dtype=np.uint8)
    image[:, 0] = 10  # far port
    image[:, COLS // 2 - 1] = 20  # port next to nadir
    image[:, COLS // 2] = 30  # starboard next to nadir
    image[:, -1] = 40  # far starboard
    cv2.imwrite(str(path), image)
    return path


def _track(n: int, heading: float = 62.4, step_m: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    lon, lat, _ = GEOD.fwd(
        np.full(n, 80.3071), np.full(n, 13.0802), np.full(n, heading), np.arange(n) * step_m
    )
    return np.asarray(lat), np.asarray(lon)


def _csv(path: Path, pings: np.ndarray, **extra: object) -> Path:
    lat, lon = _track(ROWS)
    df = pd.DataFrame(
        {
            "ping": pings,
            "time_utc": pd.to_datetime("2026-09-12T05:10:02Z") + pd.to_timedelta(pings * 0.1, "s"),
            "lat": lat[pings],
            "lon": lon[pings],
            "heading_deg": 62.4,
            "slant_range_m": 50.0,
            "altitude_m": 8.0,
        }
    )
    for key, value in extra.items():
        if value is None:
            df = df.drop(columns=[key])
        else:
            df[key] = value
    df.to_csv(path, index=False)
    return path


def test_split_channels_puts_nadir_first() -> None:
    image = np.arange(8).reshape(1, 8)
    port, stbd, n = split_channels(image, "port_stbd")
    assert n == 4
    assert port is not None and stbd is not None
    assert port.tolist() == [[3, 2, 1, 0]]
    assert stbd.tolist() == [[4, 5, 6, 7]]
    port, stbd, n = split_channels(np.arange(5).reshape(1, 5), "port_stbd")
    assert port is not None and stbd is not None
    assert (port.tolist(), stbd.tolist(), n) == ([[1, 0]], [[3, 4]], 2)


def test_full_csv_reads_every_row(tmp_path: Path) -> None:
    log = read_image_nav(_png(tmp_path / "w.png"), _csv(tmp_path / "nav.csv", np.arange(ROWS)))
    assert log.source_format == "image_nav"
    assert log.n_pings == ROWS and log.sonar.samples_per_channel == COLS // 2
    assert log.port is not None and log.starboard is not None
    assert log.port[0, 0] == 20 and log.port[0, -1] == 10
    assert log.starboard[0, 0] == 30 and log.starboard[0, -1] == 40
    assert log.warnings == []
    assert set(log.nav["nav_source"]) == {"csv"}
    assert log.has_navigation


def test_sparse_csv_is_interpolated(tmp_path: Path) -> None:
    """TC-ING-010: every 25th row given; positions interpolated and flagged."""
    pings = np.arange(0, ROWS, 25)
    log = read_image_nav(_png(tmp_path / "w.png"), _csv(tmp_path / "nav.csv", pings))
    assert GPS_INTERPOLATED in log.warnings
    lat, lon = _track(ROWS)
    _, _, err = GEOD.inv(lon, lat, log.nav["lon"].to_numpy(), log.nav["lat"].to_numpy())
    assert np.max(err) < 0.01  # straight track: linear interpolation is exact to mm level
    assert log.nav.loc[30, "nav_source"] == "interpolated"
    assert log.nav.loc[25, "nav_source"] == "csv"
    assert log.nav["time_utc"].iloc[50] == pd.Timestamp("2026-09-12T05:10:07Z")


def test_sparse_csv_extrapolates_beyond_last_fix(tmp_path: Path) -> None:
    pings = np.array([10, 20, 30])
    log = read_image_nav(_png(tmp_path / "w.png"), _csv(tmp_path / "nav.csv", pings))
    lat, lon = _track(ROWS)
    _, _, err = GEOD.inv(lon, lat, log.nav["lon"].to_numpy(), log.nav["lat"].to_numpy())
    assert np.max(err) < 0.05


def test_heading_interpolates_across_north() -> None:
    from sonarsentinel.ingest.image_nav_reader import _interp_heading

    out = _interp_heading(np.array([0.0, 1.0, 2.0]), np.array([0.0, 2.0]), np.array([358.0, 2.0]))
    assert out[1] == pytest.approx(0.0, abs=1e-9) or out[1] == pytest.approx(360.0, abs=1e-9)


def test_missing_heading_uses_course_over_ground(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "nav.csv", np.arange(ROWS), heading_deg=None)
    log = read_image_nav(_png(tmp_path / "w.png"), csv)
    assert HEADING_FROM_COG in log.warnings
    assert log.nav["heading_deg"].to_numpy() == pytest.approx(62.4, abs=0.01)


def test_missing_columns_are_listed(tmp_path: Path) -> None:
    """TC-ING-004: CSV without lat → NAV_CSV_INVALID listing the missing columns."""
    csv = _csv(tmp_path / "nav.csv", np.arange(ROWS), lat=None)
    with pytest.raises(NavCsvInvalidError) as exc_info:
        read_nav_csv(csv, ROWS)
    err = exc_info.value
    assert err.code == "NAV_CSV_INVALID" and err.http_status == 400
    assert err.details["missing"] == ["lat"]


@pytest.mark.parametrize(
    ("pings", "match"),
    [
        (np.array([0, 5, 500]), "whole numbers"),
        (np.array([0, 5, 5]), "duplicate"),
        (np.array([3]), "two fixes"),
    ],
)
def test_bad_ping_values(tmp_path: Path, pings: np.ndarray, match: str) -> None:
    lat, lon = _track(len(pings))
    pd.DataFrame(
        {"ping": pings, "lat": lat, "lon": lon, "heading_deg": 0.0, "slant_range_m": 50.0}
    ).to_csv(tmp_path / "nav.csv", index=False)
    with pytest.raises(NavCsvInvalidError, match=match):
        read_nav_csv(tmp_path / "nav.csv", ROWS)


def test_non_numeric_values_are_rejected(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "nav.csv", np.arange(3), slant_range_m=["50", "x", "50"])
    with pytest.raises(NavCsvInvalidError, match="non-numeric"):
        read_nav_csv(csv, ROWS)


def test_utm_columns_need_epsg_and_match_latlon(tmp_path: Path) -> None:
    lat, lon = _track(ROWS)
    east, north = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform(
        lon, lat
    )
    pings = np.arange(ROWS)
    pd.DataFrame({"ping": pings, "easting": east, "northing": north, "slant_range_m": 50.0}).to_csv(
        tmp_path / "utm.csv", index=False
    )
    with pytest.raises(CrsRequiredError):
        read_nav_csv(tmp_path / "utm.csv", ROWS)
    nav, warnings, _ = read_nav_csv(tmp_path / "utm.csv", ROWS, epsg=32644)
    _, _, err = GEOD.inv(lon, lat, nav["lon"].to_numpy(), nav["lat"].to_numpy())
    assert np.max(err) < 0.1
    assert HEADING_FROM_COG in warnings


def test_ground_range_flag(tmp_path: Path) -> None:
    csv = _csv(tmp_path / "nav.csv", np.arange(ROWS), ground_range_corrected="true")
    assert read_image_nav(_png(tmp_path / "w.png"), csv).ground_range_corrected


def test_image_only_is_not_geotagged(tmp_path: Path) -> None:
    """TC-ING-011 (reader part): no navigation → NaN positions and NOT_GEOTAGGED."""
    log = read_image_only(_png(tmp_path / "w.png"))
    assert log.source_format == "image_only"
    assert log.warnings == [NOT_GEOTAGGED]
    assert log.n_pings == ROWS
    assert not log.has_navigation


def test_undecodable_image(tmp_path: Path) -> None:
    f = tmp_path / "bad.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
    with pytest.raises(CorruptHeaderError):
        read_image_only(f)
