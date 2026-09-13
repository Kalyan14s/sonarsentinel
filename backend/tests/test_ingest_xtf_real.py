"""TC-ING-006: parse public XTF files (test data TD-02).

Uses USGS Grand Bay 2015 lines (Klein 3900, doi:10.5066/P9374DKQ) from ``data/raw/usgs`` (DVC,
not in git). Skipped when the files are not present, e.g. in CI. Reference values come from
pyxtf's own packet parser, which is independent of our two-pass reader.
"""

from pathlib import Path

import numpy as np
import pytest

pyxtf = pytest.importorskip("pyxtf")

from sonarsentinel.geo.track import track_bbox  # noqa: E402
from sonarsentinel.ingest.xtf_reader import detect_port_order, read_xtf, scan_xtf  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "raw" / "usgs" / "grandbay_2015-315-FA"
FILES = sorted(DATA.glob("*.xtf")) if DATA.exists() else []
#: Survey bounding box from the release metadata: west, south, east, north.
METADATA_BBOX = (-88.412144, 30.342408, -88.317322, 30.417417)

pytestmark = pytest.mark.skipif(not FILES, reason="USGS Grand Bay XTF files not downloaded")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_real_file_matches_reference_parser(path: Path) -> None:
    log = read_xtf(path)
    _, packets = pyxtf.xtf_read(str(path), types=[pyxtf.XTFHeaderType.sonar])
    pings = packets[pyxtf.XTFHeaderType.sonar]
    assert log.n_pings == len(pings)
    # A 10-ping line has too little signal to detect the port order; the far-first default is used.
    expected = [] if log.n_pings >= 100 else ["PORT_ORDER_ASSUMED"]
    assert log.warnings == expected
    assert log.sonar.channel_layout == "port_stbd"
    assert log.port is not None and log.starboard is not None

    for i in np.linspace(0, log.n_pings - 1, 10).astype(int):
        p = pings[i]
        assert log.nav["lat"].iloc[i] == p.SensorYcoordinate
        assert log.nav["lon"].iloc[i] == p.SensorXcoordinate
        assert log.nav["heading_deg"].iloc[i] == pytest.approx(p.SensorHeading)
        assert log.nav["slant_range_m"].iloc[i] == pytest.approx(p.ping_chan_headers[0].SlantRange)
        stbd, port = p.data[1], p.data[0]
        np.testing.assert_array_equal(log.starboard[i, : len(stbd)], stbd)
        np.testing.assert_array_equal(log.port[i, : len(port)], port[::-1])  # far range first


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_real_track_is_inside_survey_area(path: Path) -> None:
    bbox = track_bbox(read_xtf(path))
    assert bbox is not None
    west, south, east, north = METADATA_BBOX
    assert west <= bbox[0] <= bbox[2] <= east
    assert south <= bbox[1] <= bbox[3] <= north


@pytest.mark.parametrize("path", [f for f in FILES if f.stat().st_size > 1_000_000], ids=str)
def test_real_port_order_is_far_first(path: Path) -> None:
    assert detect_port_order(scan_xtf(path)) == "far_first"
