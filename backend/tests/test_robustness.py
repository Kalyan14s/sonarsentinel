"""ST-111 robustness: faulty inputs complete with ranged warnings, flags and penalties.

TC-ROB-001 (AC-06: 10% zeroed pings + truncated final record), TC-ROB-002 (30 s GPS gap),
TC-ROB-003 (±10° roll), TC-ROB-004 (no altitude), TC-ROB-005 (GPU runtime → CPU fallback) and
TC-ROB-006 (chunk failure → retry once, then skip). Uses the rule-based detector and an identity
calibrator so results are the same in CI and on machines with trained scoring models.
"""

import json
from collections import Counter
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
pytest.importorskip("cv2")
jsonschema = pytest.importorskip("jsonschema")

from tools.make_synthetic_xtf import truncate, write_synthetic_xtf  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

import sonarsentinel.pipeline as pipeline  # noqa: E402
from sonarsentinel.cli import app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.detect.classical import BrightTargetDetector  # noqa: E402
from sonarsentinel.detect.yolo import (  # noqa: E402
    CPU_FALLBACK,
    resolve_runtime_weights,
    runtime_fallback_warnings,
)
from sonarsentinel.ingest.chunking import chunk_ranges  # noqa: E402
from sonarsentinel.pipeline import CHUNK_SKIPPED, run_pipeline  # noqa: E402

N_PINGS = 1400
TARGETS = [(250, "starboard", 400), (640, "port", 500), (1100, "starboard", 700)]
CHUNKING = {"pings_per_chunk": 700, "overlap_pings": 150}


def _schema() -> Any:
    text = resources.files("sonarsentinel.report").joinpath("schema", "report-1.0.schema.json")
    return jsonschema.Draft202012Validator(json.loads(text.read_text("utf-8")))


def _cfg() -> dict[str, Any]:
    cfg = load_config()
    cfg["chunking"] = dict(CHUNKING)
    cfg["scoring"]["calibrator"] = None  # identity calibration: comparable confidences everywhere
    cfg["scoring"]["fp_filter_model"] = None
    return cfg


def _line(path: Path, **faults: Any) -> Path:
    write_synthetic_xtf(
        path,
        n_pings=N_PINGS,
        samples_per_side=1000,
        step_m=0.1,
        targets=TARGETS,
        target_extent=(12, 30),
        **faults,
    )
    return path


def _run(path: Path, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return run_pipeline(
        path,
        config=_cfg(),
        detector=BrightTargetDetector(),
        on_event=None if events is None else events.append,
    )


def _near(report: dict[str, Any], ping: int, tol: int = 40) -> list[dict[str, Any]]:
    return [
        d
        for d in report["detections"]
        if d["sonar_ref"]["ping_start"] - tol <= ping <= d["sonar_ref"]["ping_end"] + tol
    ]


def _without_source(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detections without the file name, to compare runs on differently named copies."""
    return [
        {**d, "sonar_ref": {k: v for k, v in d["sonar_ref"].items() if k != "source_file"}}
        for d in detections
    ]


def _warnings(report: dict[str, Any]) -> list[str]:
    return list(report["processing"]["quality"]["warnings"])


@pytest.fixture(scope="module")
def clean(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _run(_line(tmp_path_factory.mktemp("robust") / "clean.xtf"))


def test_dropouts_and_truncation_complete_with_ranged_warnings(
    tmp_path: Path, clean: dict[str, Any]
) -> None:
    """TC-ROB-001 / AC-06: 10% zeroed pings (one run over a target) + truncated last record."""
    dropouts = [(60, 100), (400, 440), (646, 652), (900, 954)]  # 140 pings = 10%
    raw = _line(tmp_path / "raw.xtf", dropout_pings=dropouts)
    path = truncate(raw, tmp_path / "ac06.xtf", drop_bytes=1500)
    events: list[dict[str, Any]] = []
    report = _run(path, events)

    assert _schema().is_valid(report)
    assert events[-1]["type"] == "done" and events[-1]["status"] == "completed_with_warnings"
    assert {"TRUNCATED_FILE", "DROPOUT"} <= set(_warnings(report))
    ranged = [e for e in events if e["type"] == "warning" and e["code"] == "DROPOUT"]
    assert ranged and all(e["ping_end"] >= e["ping_start"] for e in ranged)
    assert report["processing"]["quality"]["dropout_pings"] >= 100

    faulty = [d for d in _near(report, 640) if "DROPOUT" in d["quality_flags"]]
    assert faulty, "the target overlapping a dropout carries DROPOUT"
    assert all(d["scores"]["dropout_penalty"] > 0 for d in faulty)
    reference = max(d["confidence"] for d in _near(clean, 640))
    assert max(d["confidence"] for d in faulty) < reference

    out = tmp_path / "cli"
    cli = CliRunner().invoke(
        app, ["detect", str(path), "--out", str(out), "--quiet", "--detector", "classical"]
    )
    assert cli.exit_code == 0, cli.output
    cli_report = json.loads(next(out.glob("*/report.json")).read_text("utf-8"))
    assert _schema().is_valid(cli_report) and "TRUNCATED_FILE" in _warnings(cli_report)


def test_gps_gap_is_interpolated_and_flagged(tmp_path: Path, clean: dict[str, Any]) -> None:
    """TC-ROB-002: a 30 s gap (300 pings, across a chunk border) over a target.

    The target is still found, flagged GPS_INTERPOLATED, and its uncertainty is not lower.
    """
    report = _run(_line(tmp_path / "gap.xtf", gps_gap=(500, 800)))
    assert "GPS_INTERPOLATED" in _warnings(report)
    near = _near(report, 640)
    assert near and all("GPS_INTERPOLATED" in d["quality_flags"] for d in near)
    before = min(d["position"]["uncertainty_m"] for d in _near(clean, 640))
    assert min(d["position"]["uncertainty_m"] for d in near) >= before


def test_strong_roll_flags_high_motion(tmp_path: Path) -> None:
    """TC-ROB-003: ±10° roll → HIGH_MOTION warnings, flags and the motion penalty."""
    events: list[dict[str, Any]] = []
    report = _run(_line(tmp_path / "roll.xtf", roll_deg_amplitude=10.0), events)
    assert "HIGH_MOTION" in _warnings(report)
    assert any(e["type"] == "warning" and e["code"] == "HIGH_MOTION" for e in events)
    flagged = [d for d in report["detections"] if "HIGH_MOTION" in d["quality_flags"]]
    assert flagged and all(d["scores"]["motion_penalty"] > 0 for d in flagged)


def test_missing_altitude_uses_bottom_tracking(tmp_path: Path) -> None:
    """TC-ROB-004: no altitude in the file → bottom tracking and NO_ALTITUDE_BOTTOM_TRACKED."""
    report = _run(_line(tmp_path / "noalt.xtf", write_altitude=False))
    assert "NO_ALTITUDE_BOTTOM_TRACKED" in _warnings(report)
    assert report["processing"]["quality"]["bottom_tracked"] is True
    assert report["detections"]
    assert all("NO_ALTITUDE_BOTTOM_TRACKED" in d["quality_flags"] for d in report["detections"])


def test_gpu_runtime_falls_back_to_cpu(tmp_path: Path) -> None:
    """TC-ROB-005 selection: TensorRT/CUDA requested without a GPU → ONNX Runtime or PyTorch CPU."""
    pt = tmp_path / "best.pt"
    pt.write_bytes(b"x")
    assert resolve_runtime_weights(pt, "tensorrt", onnxruntime_available=True) == pt
    (tmp_path / "best.onnx").write_bytes(b"x")
    assert resolve_runtime_weights(pt, "tensorrt", onnxruntime_available=True).suffix == ".onnx"
    assert resolve_runtime_weights(pt, "cuda", onnxruntime_available=False) == pt
    assert resolve_runtime_weights(pt, "cuda", onnxruntime_available=True, accelerator=True) == pt
    assert runtime_fallback_warnings("tensorrt", "onnxruntime-cpu", "yolo@0.1.0") == [CPU_FALLBACK]
    assert runtime_fallback_warnings("cuda", "tensorrt-fp16", "yolo@0.1.0") == []
    assert runtime_fallback_warnings("auto", "torch-cpu", "yolo@0.1.0") == []
    assert runtime_fallback_warnings("cuda", "cpu", "classical-bright-target@0.1.0") == []


class _CpuYoloStandIn(BrightTargetDetector):
    """Behaves like a YOLO detector that ended up on the CPU runtime."""

    model_version = "yolo11s-seg-sonar-real@0.1.0"
    runtime = "onnxruntime-cpu"


def test_pipeline_reports_cpu_fallback(tmp_path: Path) -> None:
    """TC-ROB-005 end to end: the report names the CPU runtime and carries CPU_FALLBACK."""
    cfg = _cfg()
    cfg["detection"]["runtime"] = "tensorrt"
    report = run_pipeline(_line(tmp_path / "cpu.xtf"), config=cfg, detector=_CpuYoloStandIn())
    assert CPU_FALLBACK in _warnings(report)
    assert report["processing"]["runtime"] == "onnxruntime-cpu" and _schema().is_valid(report)


def test_real_weights_fall_back_to_cpu(tmp_path: Path) -> None:
    """TC-ROB-005 with the trained detector, when its weights and Ultralytics are available."""
    pytest.importorskip("ultralytics")
    from sonarsentinel.cli import build_detector
    from sonarsentinel.scoring.fusion import repo_path

    cfg = _cfg()
    if not repo_path(cfg["detection"]["model"]).is_file():
        pytest.skip("trained detector weights not available")
    cfg["detection"] |= {"runtime": "tensorrt", "sahi": False}
    detector = build_detector("yolo", None, cfg)
    path = tmp_path / "short.xtf"
    write_synthetic_xtf(path, n_pings=300, samples_per_side=600, targets=[(150, "starboard", 300)])
    report = run_pipeline(path, config=cfg, detector=detector)
    assert CPU_FALLBACK in _warnings(report)
    assert report["processing"]["runtime"].endswith("cpu")


def test_failed_chunk_is_retried_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean: dict[str, Any]
) -> None:
    """TC-ROB-006: chunk 2 fails once → retried, same result as a clean run, no skip."""
    original = pipeline._chunk_detections
    attempts: Counter[int] = Counter()

    def flaky(chunk: Any, *args: Any, **kwargs: Any) -> Any:
        attempts[chunk.chunk_id] += 1
        if chunk.chunk_id == 1 and attempts[1] == 1:
            raise RuntimeError("injected chunk failure")
        return original(chunk, *args, **kwargs)

    monkeypatch.setattr(pipeline, "_chunk_detections", flaky)
    report = _run(_line(tmp_path / "retry.xtf"))
    assert attempts[1] == 2 and attempts[0] == 1
    assert CHUNK_SKIPPED not in _warnings(report)
    assert _without_source(report["detections"]) == _without_source(clean["detections"])


def test_chunk_failing_twice_is_skipped_with_its_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-ROB-006: chunk 2 fails twice → CHUNK_SKIPPED over its pings, completed_with_warnings."""
    original = pipeline._chunk_detections

    def broken(chunk: Any, *args: Any, **kwargs: Any) -> Any:
        if chunk.chunk_id == 1:
            raise RuntimeError("injected chunk failure")
        return original(chunk, *args, **kwargs)

    monkeypatch.setattr(pipeline, "_chunk_detections", broken)
    events: list[dict[str, Any]] = []
    report = _run(_line(tmp_path / "skip.xtf"), events)
    start, stop = chunk_ranges(N_PINGS, CHUNKING["pings_per_chunk"], CHUNKING["overlap_pings"])[1]
    skipped = [e for e in events if e["type"] == "warning" and e["code"] == CHUNK_SKIPPED]
    assert [(e["ping_start"], e["ping_end"]) for e in skipped] == [(start, stop - 1)]
    assert CHUNK_SKIPPED in _warnings(report) and _schema().is_valid(report)
    assert events[-1]["type"] == "done" and events[-1]["status"] == "completed_with_warnings"
    assert _near(report, 250), "chunks before and after the failed one still report detections"
