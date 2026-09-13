"""ST-063…065 fusion, calibration and tiers (TC-CONF-001, 002, 003, 008 tooling)."""

from pathlib import Path

import numpy as np
import pytest

from sonarsentinel.geo.cluster import persistence_score
from sonarsentinel.report.builder import alert_tier
from sonarsentinel.scoring.fusion import (
    IsotonicCalibrator,
    expected_calibration_error,
    fit_isotonic,
    fuse,
    load_calibrator,
    load_fp_filter,
    reliability_table,
)

WEIGHTS = {
    "detector": 0.45,
    "anomaly": 0.15,
    "shadow": 0.15,
    "fp_filter": 0.15,
    "persistence": 0.10,
}
TIERS = {"hazard": 80, "review": 50, "anomaly": 30}


def test_fused_recomputes_from_breakdown() -> None:
    """TC-CONF-003: fused from weights and penalties within 1e-6."""
    scores = {"detector": 0.9, "anomaly": 0.6, "shadow": 0.7, "fp_filter": 0.8, "persistence": 0.5}
    expected = sum(WEIGHTS[k] * v for k, v in scores.items()) - 0.02 - 0.1
    assert fuse(scores, WEIGHTS, dropout_penalty=0.02, motion_penalty=0.1) == pytest.approx(
        expected, abs=1e-6
    )


def test_missing_components_are_renormalised() -> None:
    scores = {"detector": 0.8, "anomaly": None, "shadow": 0.4, "persistence": 0.5}
    used = {"detector": 0.45, "shadow": 0.15, "persistence": 0.10}
    expected = (0.45 * 0.8 + 0.15 * 0.4 + 0.10 * 0.5) / sum(used.values())
    assert fuse(scores, WEIGHTS) == pytest.approx(expected, abs=1e-9)


def test_fused_clipped_to_unit_interval() -> None:
    """TC-CONF-001 at the fusion level: 0 ≤ fused ≤ 1 even with large penalties."""
    assert fuse({"detector": 0.1}, WEIGHTS, dropout_penalty=0.2, motion_penalty=0.1) == 0.0
    assert fuse({"detector": 1.0, "shadow": 1.0}, WEIGHTS) == 1.0
    assert fuse({}, WEIGHTS) == 0.0


def test_dropout_penalty_lowers_confidence() -> None:
    """TC-CONF-007 scoring rule: the same detection over a dropout scores lower."""
    scores = {"detector": 0.8, "shadow": 0.6, "persistence": 0.5}
    clean = fuse(scores, WEIGHTS)
    over_dropout = fuse(scores, WEIGHTS, dropout_penalty=0.20 * 0.5)
    assert over_dropout == pytest.approx(clean - 0.1) and over_dropout < clean


@pytest.mark.parametrize(
    ("confidence", "anomaly", "tier"),
    [
        (79.9, None, "review"),
        (80.0, None, "hazard"),
        (50.0, None, "review"),
        (49.9, 0.6, "anomaly"),
        (49.9, 0.4, "hidden"),
        (49.9, None, "hidden"),
        (30.0, 0.5, "anomaly"),
        (29.9, 0.9, "hidden"),
    ],
)
def test_tier_boundaries(confidence: float, anomaly: float | None, tier: str) -> None:
    """TC-CONF-002 including the anomaly ≥ τ rule (τ = 0.5)."""
    assert alert_tier(confidence, TIERS, anomaly_score=anomaly, anomaly_threshold=0.5) == tier


def test_persistence() -> None:
    assert persistence_score(1) == 0.5 and persistence_score(2) == 0.75


def test_isotonic_fit_is_monotone_and_matches_pooled_means() -> None:
    xs, ys = fit_isotonic([0.1, 0.2, 0.3, 0.4], [0, 1, 0, 1])
    assert ys == sorted(ys)
    calibrator = IsotonicCalibrator(tuple(xs), tuple(ys))
    assert calibrator(0.25) == pytest.approx(0.5)
    assert calibrator(0.0) == pytest.approx(0.0) and calibrator(1.0) == pytest.approx(1.0)


def test_calibration_reduces_ece_on_overconfident_scores(tmp_path: Path) -> None:
    """TC-CONF-008 tooling: isotonic fit on a calib set lowers ECE on held-out data."""
    rng = np.random.default_rng(0)

    def sample(n: int) -> tuple[np.ndarray, np.ndarray]:
        fused = rng.uniform(0, 1, n)
        labels = rng.uniform(0, 1, n) < fused**2  # true probability is fused²: overconfident
        return fused, labels.astype(float)

    calib_x, calib_y = sample(4000)
    test_x, test_y = sample(4000)
    calibrator = IsotonicCalibrator.fit(calib_x, calib_y, version="9.9.9")
    before = expected_calibration_error(test_x, test_y)
    after = expected_calibration_error([calibrator(v) for v in test_x], test_y)
    assert before > 0.1 and after <= 0.05

    path = calibrator.save(tmp_path / "calibrator.json", ece=after)
    loaded = IsotonicCalibrator.load(path)
    assert loaded(0.42) == pytest.approx(calibrator(0.42)) and loaded.describe() == "isotonic@9.9.9"
    assert sum(row["count"] for row in reliability_table(test_x, test_y)) == 4000


def test_loaders_return_none_when_models_missing(tmp_path: Path) -> None:
    cfg = {
        "scoring": {
            "calibrator": str(tmp_path / "missing.json"),
            "fp_filter_model": str(tmp_path / "missing_folder"),
        }
    }
    assert load_calibrator(cfg) is None and load_fp_filter(cfg) is None
    assert load_calibrator({}) is None and load_fp_filter({}) is None
