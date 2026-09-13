"""Detector selection for `sonarsentinel detect` and the rule-based-detector warning."""

from pathlib import Path

import pytest

from sonarsentinel.cli import build_anomaly, build_detector
from sonarsentinel.config import load_config
from sonarsentinel.detect.classical import BrightTargetDetector
from sonarsentinel.errors import ValidationError


def test_auto_falls_back_to_rule_based_without_weights(tmp_path: Path) -> None:
    cfg = load_config()
    cfg["detection"]["model"] = str(tmp_path / "missing" / "best.pt")
    assert isinstance(build_detector("auto", None, cfg), BrightTargetDetector)
    assert isinstance(build_detector("classical", None, cfg), BrightTargetDetector)
    with pytest.raises(ValidationError, match="Unknown detector"):
        build_detector("rcnn", None, cfg)


def test_anomaly_model_disabled_or_missing(tmp_path: Path) -> None:
    cfg = load_config()
    assert build_anomaly(cfg, disabled=True) is None
    cfg["anomaly"]["model"] = str(tmp_path / "no-model")
    assert build_anomaly(cfg, disabled=False) is None
    cfg["anomaly"]["enabled"] = False
    assert build_anomaly(cfg, disabled=False) is None


def test_rule_based_reports_carry_a_warning(tmp_path: Path) -> None:
    pytest.importorskip("pyxtf")
    pytest.importorskip("scipy")
    from tools.make_synthetic_xtf import write_synthetic_xtf

    from sonarsentinel.pipeline import run_pipeline

    survey = write_synthetic_xtf(tmp_path / "w.xtf", n_pings=200, samples_per_side=300)
    report = run_pipeline(survey.path, config=load_config())
    assert "RULE_BASED_DETECTOR" in report["processing"]["quality"]["warnings"]
