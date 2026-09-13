"""ST-053 pipeline wiring: anomaly heatmaps → scores.anomaly and unknown_anomaly detections.

Uses a fake anomaly model (no torch), so it runs in CI: its heatmap is hot on bright pixels and on a
fixed "novel object" patch that the rule-based detector can't see.
"""

import json
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
jsonschema = pytest.importorskip("jsonschema")
cv2 = pytest.importorskip("cv2")

from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.detect.anomaly import heat_regions  # noqa: E402
from sonarsentinel.pipeline import run_pipeline  # noqa: E402


class FakeAnomaly:
    model_version = "fake-patchcore@0.0.1"
    pixel_threshold = 1.0
    runtime = "cpu"

    def score(self, tiles: list[np.ndarray]) -> SimpleNamespace:
        maps = []
        for tile in tiles:
            heat = (tile[..., 1] >= 240).astype(np.float32) * 1.8  # bright objects
            heat[300:330, 100:160] = 1.6  # a region only the anomaly model sees
            maps.append(cv2.resize(heat, (256, 256), interpolation=cv2.INTER_NEAREST))
        heatmaps = np.stack(maps)
        return SimpleNamespace(scores=heatmaps.max(axis=(1, 2)), heatmaps=heatmaps)


def test_heat_regions_excludes_detector_boxes() -> None:
    heat = np.zeros((100, 100), np.float32)
    heat[10:20, 10:30] = 1.5
    heat[60:70, 60:70] = 3.0
    regions = heat_regions(heat, 1.0, min_area_px=20, exclude_boxes=[(10, 10, 30, 20)])
    assert [r.box for r in regions] == [(60, 60, 70, 70)]
    assert regions[0].cls == "unknown_anomaly" and regions[0].score == 1.0


def test_pipeline_emits_anomaly_scores_and_unknown_anomalies(tmp_path: Path) -> None:
    survey = write_synthetic_xtf(
        tmp_path / "anom.xtf",
        n_pings=700,
        samples_per_side=1000,
        targets=[(300, "starboard", 400)],
        target_extent=(12, 30),
    )
    cfg = load_config()
    report: dict[str, Any] = run_pipeline(survey.path, config=cfg, anomaly_model=FakeAnomaly())
    schema = json.loads(
        resources.files("sonarsentinel.report")
        .joinpath("schema", "report-1.0.schema.json")
        .read_text()
    )
    assert jsonschema.Draft202012Validator(schema).is_valid(report)
    assert report["processing"]["models"]["anomaly"] == "fake-patchcore@0.0.1"

    by_class: dict[str, list[dict[str, Any]]] = {}
    for det in report["detections"]:
        by_class.setdefault(det["class"], []).append(det)
    target = by_class["debris_other"][0]
    assert target["scores"]["anomaly"] > 0.5  # bright object is hot in the heatmap
    unknown = by_class["unknown_anomaly"]
    assert unknown, "patch seen only by the anomaly model should become unknown_anomaly"
    assert all(d["alert_tier"] in ("anomaly", "review", "hazard") for d in unknown)
    assert all(d["scores"]["fused"] == d["scores"]["anomaly"] for d in unknown)

    plain = run_pipeline(survey.path, config=cfg)
    assert plain["processing"]["models"]["anomaly"] is None
    assert all("anomaly" not in d["scores"] for d in plain["detections"])
