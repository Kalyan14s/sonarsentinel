"""ST-110 / Gate G2 thin slice: sample XTF → `sonarsentinel detect` → schema-valid report.

TC-REP-001 (schema), TC-REP-005 (metadata), TC-REP-006 (determinism), TC-REP-008 (CLI end to
end), TC-DET-007 (model version), plus chunk-overlap de-duplication and the image-only path.
Uses the rule-based detector so it runs in CI without model weights.
"""

import csv
import io
import json
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
jsonschema = pytest.importorskip("jsonschema")
cv2 = pytest.importorskip("cv2")

from pyproj import Geod  # noqa: E402
from tools.make_synthetic_xtf import SyntheticSurvey, write_synthetic_xtf  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from sonarsentinel.cli import app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.ingest.chunking import chunk_ranges  # noqa: E402
from sonarsentinel.pipeline import run_pipeline  # noqa: E402

GEOD = Geod(ellps="WGS84")
runner = CliRunner()
RULES = ["--detector", "classical"]  # keep CI and local runs on the rule-based detector


def _schema() -> Any:
    text = resources.files("sonarsentinel.report").joinpath("schema", "report-1.0.schema.json")
    return jsonschema.Draft202012Validator(json.loads(text.read_text("utf-8")))


@pytest.fixture(scope="module")
def survey(tmp_path_factory: pytest.TempPathFactory) -> SyntheticSurvey:
    path = tmp_path_factory.mktemp("g2") / "line_g2.xtf"
    return write_synthetic_xtf(
        path,
        n_pings=1400,
        samples_per_side=1000,
        step_m=0.1,
        targets=[(300, "starboard", 400), (640, "port", 500), (1100, "starboard", 700)],
        target_extent=(12, 30),
    )


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 700, "overlap_pings": 150}  # target 640 in the overlap
    return cfg


def test_cli_detect_produces_valid_reports(survey: SyntheticSurvey, tmp_path: Path) -> None:
    """TC-REP-008 + TC-REP-001: exit code 0, JSON and CSV written, schema valid."""
    result = runner.invoke(
        app,
        ["detect", survey.path, "--out", str(tmp_path), "--formats", "json,csv", "--quiet", *RULES],
    )
    assert result.exit_code == 0, result.output
    folders = list(tmp_path.iterdir())
    assert len(folders) == 1 and folders[0].name == "SRV-20260912-001"
    report = json.loads((folders[0] / "report.json").read_text(encoding="utf-8"))
    errors = [e.message for e in _schema().iter_errors(report)]
    assert errors == []
    rows = list(csv.DictReader(io.StringIO((folders[0] / "report.csv").read_text("utf-8"))))
    assert [r["detection_id"] for r in rows] == [d["detection_id"] for d in report["detections"]]
    for row, det in zip(rows, report["detections"], strict=True):
        assert row["lat"] == f"{det['position']['lat']:.6f}"


def test_pipeline_finds_each_target_once_at_its_position(
    survey: SyntheticSurvey, config: dict[str, Any]
) -> None:
    events: list[dict[str, Any]] = []
    report = run_pipeline(survey.path, config=config, on_event=events.append)
    dets = report["detections"]
    assert len(dets) == len(survey.targets), [d["sonar_ref"] for d in dets]
    for target, det in zip(survey.targets, dets, strict=True):
        assert det["sonar_ref"]["side"] == target.side
        # object spans 12 pings (1.2 m) × 30 slant samples; compare with its first corner
        _, _, err = GEOD.inv(target.lon, target.lat, det["position"]["lon"], det["position"]["lat"])
        assert err < 2.5, (target, det["position"])
        assert det["dimensions"]["length_m"] > 0.5
        assert det["position"]["depth_m"] == pytest.approx(18.2, abs=0.5)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "progress" and kinds[-1] == "done"
    n_chunks = len(chunk_ranges(survey.n_pings, 700, 150))  # one track event per chunk
    assert n_chunks == 3
    assert kinds.count("track") == n_chunks and kinds.count("detection") == len(dets)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


def test_report_metadata_and_model_version(survey: SyntheticSurvey, config: dict[str, Any]) -> None:
    """TC-REP-005 and TC-DET-007."""
    report = run_pipeline(survey.path, config=config)
    processing = report["processing"]
    assert processing["models"]["detector"] == "classical-bright-target@0.1.0"
    assert processing["config_hash"].startswith("sha256:")
    assert report["summary"]["total_detections"] == len(report["detections"])
    assert sum(report["summary"]["by_tier"].values()) == len(report["detections"])
    assert all(d["model_version"] == processing["models"]["detector"] for d in report["detections"])
    survey_section = report["survey"]
    assert survey_section["track_length_km"] == pytest.approx(0.1399, abs=0.002)
    assert survey_section["start_utc"] == "2026-09-12T05:10:02.00Z"


def test_same_input_gives_same_report(survey: SyntheticSurvey, config: dict[str, Any]) -> None:
    """TC-REP-006: identical apart from generated_utc and duration_s."""

    def strip(report: dict[str, Any]) -> dict[str, Any]:
        report = json.loads(json.dumps(report))
        report.pop("generated_utc")
        report["processing"].pop("duration_s")
        return report

    first = run_pipeline(survey.path, config=config)
    second = run_pipeline(survey.path, config=config)
    assert strip(first) == strip(second)


def test_min_conf_filters(survey: SyntheticSurvey, config: dict[str, Any]) -> None:
    report = run_pipeline(survey.path, config=config, min_conf=99.0)
    assert report["detections"] == [] and _schema().is_valid(report)


def test_image_only_report_is_not_geotagged(tmp_path: Path) -> None:
    """Image without navigation: null positions, pixel boxes, NOT_GEOTAGGED (schema-enforced)."""
    rng = np.random.default_rng(0)
    image = np.clip(rng.normal(110, 12, (700, 800)), 0, 255).astype(np.uint8)
    image[300:315, 600:640] = 250
    path = tmp_path / "harbour.png"
    cv2.imwrite(str(path), image)
    result = runner.invoke(
        app,
        ["detect", str(path), "--out", str(tmp_path / "out"), "--allow-no-gps", "--quiet", *RULES],
    )
    assert result.exit_code == 0, result.output
    report_path = next((tmp_path / "out").glob("*/report.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert _schema().is_valid(report)
    assert report["detections"], "bright patch should be detected"
    det = report["detections"][0]
    assert det["position"]["lat"] is None and det["footprint"] is None
    assert "NOT_GEOTAGGED" in det["quality_flags"] and len(det["sonar_ref"]["pixel_bbox"]) == 4


def test_cli_reports_unknown_format(survey: SyntheticSurvey, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["detect", survey.path, "--out", str(tmp_path), "--formats", "kml", "--quiet", *RULES]
    )
    assert result.exit_code == 1 and "VALIDATION_ERROR" in result.output
