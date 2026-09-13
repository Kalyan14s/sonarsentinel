"""ST-103 edge watch mode (TC-EDGE-003): new stable files are processed once."""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
pytest.importorskip("cv2")

from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from sonarsentinel.cli import app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.detect.classical import BrightTargetDetector  # noqa: E402
from sonarsentinel.edge.watch import (  # noqa: E402
    ALERT_MAX_BYTES,
    ALERTS_LOG,
    WATCH_STATE,
    WatchState,
    alert_line,
    find_inputs,
    make_processor,
    scan_once,
    touch_old,
)


def _line(folder: Path, name: str = "line_01.xtf") -> Path:
    survey = write_synthetic_xtf(
        folder / name,
        n_pings=700,
        samples_per_side=1000,
        step_m=0.1,
        targets=[(350, "starboard", 400)],
        target_extent=(12, 30),
    )
    return Path(survey.path)


def _processor(out: Path) -> Any:
    cfg = load_config()
    cfg["report"]["mosaic"] = False
    return make_processor(cfg, BrightTargetDetector(), None, out)


def test_new_stable_file_processed_once(tmp_path: Path) -> None:
    folder, out = tmp_path / "acq", tmp_path / "out"
    folder.mkdir()
    path = _line(folder)
    touch_old(path, 120)
    messages: list[str] = []

    state = WatchState.load(out)
    attempted = scan_once(
        folder, out, state, process=_processor(out), alerts_min_conf=0.0, echo=messages.append
    )
    assert attempted == [path]
    record = state.files[str(path.resolve())]
    assert record.status == "done" and record.survey_id
    report = json.loads((out / record.survey_id / "report.json").read_text("utf-8"))
    assert (out / record.survey_id / "report.csv").is_file()
    assert report["detections"], "the synthetic target should be detected"
    assert record.alerts == len(report["detections"])
    alerts = (out / ALERTS_LOG).read_text("utf-8").splitlines()
    assert len(alerts) == record.alerts and all(a.startswith("SS1|") for a in alerts)
    assert any(m.startswith("[ok] line_01.xtf") for m in messages)

    # A restart reloads the state from disk and does not reprocess the file.
    reloaded = WatchState.load(out)
    assert scan_once(folder, out, reloaded, process=_processor(out)) == []
    saved = json.loads((out / WATCH_STATE).read_text("utf-8"))
    assert saved["files"][str(path.resolve())]["status"] == "done"


def test_growing_file_waits_until_stable(tmp_path: Path) -> None:
    folder, out = tmp_path / "acq", tmp_path / "out"
    folder.mkdir()
    path = _line(folder)  # just written: mtime is now
    state = WatchState()
    assert scan_once(folder, out, state, process=_processor(out), stable_seconds=10) == []
    assert state.files[str(path.resolve())].status == "pending"
    touch_old(path, 60)
    assert scan_once(folder, out, state, process=_processor(out), stable_seconds=10) == [path]
    assert state.files[str(path.resolve())].status == "done"


def test_failed_file_is_recorded_and_not_retried(tmp_path: Path) -> None:
    folder, out = tmp_path / "acq", tmp_path / "out"
    folder.mkdir()
    bad = folder / "broken.xtf"
    bad.write_bytes(b"not an xtf file" * 100)
    touch_old(bad, 120)
    messages: list[str] = []
    state = WatchState()
    assert scan_once(folder, out, state, process=_processor(out), echo=messages.append) == [bad]
    record = state.files[str(bad.resolve())]
    assert record.status == "failed" and record.error and ":" in record.error
    assert messages and messages[-1].startswith("[X] broken.xtf")
    assert scan_once(folder, out, state, process=_processor(out)) == []


def test_inputs_need_navigation_for_images(tmp_path: Path) -> None:
    (tmp_path / "a.xtf").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "c.png").write_bytes(b"x")
    (tmp_path / "c_nav.csv").write_text("ping,lat,lon\n", encoding="utf-8")
    (tmp_path / ".hidden.xtf").write_bytes(b"x")
    found = {p.name: (nav.name if nav else None) for p, nav in find_inputs(tmp_path)}
    assert found == {"a.xtf": None, "c.png": "c_nav.csv"}


def test_alert_line_format_and_byte_limit() -> None:
    detection = {
        "detection_id": "SRV-20260914-001-D0007",
        "class": "ghost_net",
        "confidence": 91.46,
        "position": {"lat": 13.084123, "lon": 80.312756, "depth_m": 18.24},
        "dimensions": {"length_m": 8.04, "width_m": 3.96},
        "sonar_ref": {"time_utc": "2026-09-14T05:17:21.50Z"},
    }
    line = alert_line(detection, "SRV-20260914-001")
    assert line == (
        "SS1|SRV-20260914-001|D0007|ghost_net|91|13.084123|80.312756|8.0x4.0|18.2|"
        "2026-09-14T05:17:21.50Z"
    )
    assert len(line.split("|")) == 10
    long = alert_line({**detection, "class": "x" * 400}, "SRV-20260914-001")
    assert len(long.encode("utf-8")) <= ALERT_MAX_BYTES
    empty = alert_line({"detection_id": "SRV-1-D0001", "class": "pipe"}, "SRV-1")
    assert empty == "SS1|SRV-1|D0001|pipe||||||"


def test_cli_watch_once(tmp_path: Path) -> None:
    folder, out = tmp_path / "acq", tmp_path / "out"
    folder.mkdir()
    touch_old(_line(folder), 120)
    result = CliRunner().invoke(
        app,
        [
            "watch",
            str(folder),
            "--out",
            str(out),
            "--once",
            "--detector",
            "classical",
            "--no-anomaly",
            "--no-mosaic",
            "--alerts-min-conf",
            "101",
        ],
    )
    assert result.exit_code == 0, result.output
    assert list(out.glob("*/report.json"))
    assert "[ok] line_01.xtf" in result.output


def test_cli_watch_rejects_unknown_runtime(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["watch", str(tmp_path), "--runtime", "fpga", "--once"])
    assert result.exit_code == 2
