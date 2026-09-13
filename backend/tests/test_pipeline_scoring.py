"""Sprint 4 scoring end to end: TC-CONF-001/003, TC-REP-009 (chips), TC-GEO-013 (cross-line merge).

Uses the rule-based detector on synthetic XTF so it runs in CI without model weights.
"""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
cv2 = pytest.importorskip("cv2")
jsonschema = pytest.importorskip("jsonschema")

from importlib import resources  # noqa: E402

from tools.make_synthetic_xtf import SyntheticSurvey, write_synthetic_xtf  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from sonarsentinel.cli import app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.report.chips import OVERLAYS, chip_filename  # noqa: E402
from sonarsentinel.scoring.fusion import fuse  # noqa: E402

TARGETS = [(250, "starboard", 400), (600, "port", 500)]


def _schema() -> Any:
    text = resources.files("sonarsentinel.report").joinpath("schema", "report-1.0.schema.json")
    return jsonschema.Draft202012Validator(json.loads(text.read_text("utf-8")))


def _line(path: Path, seed: int) -> SyntheticSurvey:
    return write_synthetic_xtf(
        path,
        n_pings=900,
        samples_per_side=1000,
        step_m=0.1,
        targets=TARGETS,
        target_extent=(12, 30),
        seed=seed,
    )


@pytest.fixture(scope="module")
def cli_report(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    root = tmp_path_factory.mktemp("scoring")
    survey = _line(root / "line_a.xtf", seed=0)
    out = root / "out"
    result = CliRunner().invoke(
        app,
        ["detect", str(survey.path), "--out", str(out), "--quiet", "--detector", "classical"],
    )
    assert result.exit_code == 0, result.output
    report_path = next(out.glob("*/report.json"))
    return json.loads(report_path.read_text("utf-8")), report_path.parent


def test_confidence_range_and_schema(cli_report: tuple[dict[str, Any], Path]) -> None:
    """TC-CONF-001: 0 ≤ confidence ≤ 100 on every detection; report still schema-valid."""
    report, _ = cli_report
    assert report["detections"]
    assert all(0.0 <= d["confidence"] <= 100.0 for d in report["detections"])
    assert _schema().is_valid(report), list(_schema().iter_errors(report))[:3]
    assert report["processing"]["pipeline_version"] == "0.2.0"


def test_fused_recomputes_from_breakdown(cli_report: tuple[dict[str, Any], Path]) -> None:
    """TC-CONF-003: fused from the score breakdown and configured weights within 1e-6."""
    report, _ = cli_report
    weights = load_config()["scoring"]["weights"]
    for det in report["detections"]:
        scores = det["scores"]
        expected = fuse(
            scores,
            weights,
            dropout_penalty=scores["dropout_penalty"],
            motion_penalty=scores["motion_penalty"],
        )
        assert scores["fused"] == pytest.approx(expected, abs=1e-6)
        assert scores["persistence"] == 0.5 and "shadow" in scores
        if report["processing"]["models"]["calibrator"] == "identity@0.1.0":
            assert det["confidence"] == pytest.approx(100 * scores["fused"], abs=0.05)


def test_one_chip_per_detection_with_overlays(cli_report: tuple[dict[str, Any], Path]) -> None:
    """TC-REP-009: every detection has chips for all overlays; no stray temporary chips."""
    report, folder = cli_report
    chips = folder / "chips"
    expected = {
        chip_filename(d["detection_id"], overlay)
        for d in report["detections"]
        for overlay in OVERLAYS
    }
    assert {p.name for p in chips.iterdir()} == expected
    for det in report["detections"]:
        assert det["chip_url"] == f"/api/v1/detections/{det['detection_id']}/chip.png"
        assert cv2.imread(str(chips / chip_filename(det["detection_id"], "mask"))).shape == (
            256,
            256,
            3,
        )


def test_same_object_on_two_lines_is_merged(tmp_path: Path) -> None:
    """TC-GEO-013 end to end: two lines over the same targets → one detection each, n_views = 2."""
    from sonarsentinel.detect.classical import BrightTargetDetector
    from sonarsentinel.pipeline import run_pipeline, run_survey

    line_a = _line(tmp_path / "line_a.xtf", seed=0)
    line_b = _line(tmp_path / "line_b.xtf", seed=1)
    cfg = load_config()
    single = run_pipeline(line_a.path, config=cfg, detector=BrightTargetDetector())
    events: list[dict[str, Any]] = []
    survey = run_survey(
        [line_a.path, line_b.path],
        config=cfg,
        detector=BrightTargetDetector(),
        on_event=events.append,
        results_dir=tmp_path / "results",
    )

    merged = [d for d in survey["detections"] if d["n_views"] == 2]
    assert len(merged) >= len(TARGETS)
    assert len(survey["detections"]) == len(single["detections"])
    assert all(d["scores"]["persistence"] == 0.75 for d in merged)
    assert survey["survey"]["source_files"] == ["line_a.xtf", "line_b.xtf"]
    removed = [e for e in events if e["type"] == "detection_removed"]
    updated = [e for e in events if e["type"] == "detection_update"]
    assert len(removed) == len(merged) and len(updated) == len(merged)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1]["type"] == "done"
    chips = tmp_path / "results" / survey["survey"]["survey_id"] / "chips"
    for event in removed:
        assert not (chips / chip_filename(event["detection_id"], "mask")).exists()
    ids = [d["detection_id"] for d in survey["detections"]]
    assert len(ids) == len(set(ids))
    assert _schema().is_valid(survey)
