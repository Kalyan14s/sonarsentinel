"""Scoring data helpers, fusion grid search and cross-validated calibration (ST-062…064)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibrate import cross_validated  # noqa: E402
from scoring_data import auroc, average_precision, image_folds, match, truth_boxes  # noqa: E402
from sonarsentinel.scoring.fusion import expected_calibration_error  # noqa: E402
from tune_fusion import fused_ap, grid_search  # noqa: E402


def test_match_is_one_to_one_in_score_order() -> None:
    truths = [(0, 0, 10, 10), (20, 20, 30, 30)]
    boxes = [(0, 0, 10, 10), (1, 1, 10, 10), (20, 20, 30, 31), (50, 50, 60, 60)]
    scores = [0.5, 0.9, 0.7, 0.8]
    assert match(boxes, scores, truths) == [0, 1, 1, 0]


def test_truth_boxes_from_polygon(tmp_path: Path) -> None:
    label = tmp_path / "tile.txt"
    label.write_text("2 0.1 0.1 0.2 0.1 0.2 0.2\n\n", encoding="utf-8")
    assert truth_boxes(label, 100, 100) == [(10, 10, 20, 20)]
    assert truth_boxes(tmp_path / "missing.txt", 100, 100) == []


def test_average_precision_and_auroc() -> None:
    assert average_precision([0.9, 0.8, 0.7], [1, 0, 1], n_positive=3) == pytest.approx(
        (1.0 + 2 / 3) / 3
    )
    assert auroc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)
    assert auroc([0.5, 0.5], [1, 0]) == pytest.approx(0.5)
    assert np.isnan(auroc([0.2, 0.3], [1, 1]))


def test_image_folds_keep_images_together() -> None:
    images = ["a", "b", "a", "c", "b", "d", "e"]
    folds = image_folds(images, 3, seed=1)
    assert folds[0] == folds[2] and folds[1] == folds[4]
    assert np.array_equal(folds, image_folds(images, 3, seed=1))


def test_grid_search_finds_informative_component() -> None:
    rng = np.random.default_rng(0)
    rows = [
        {
            "detector": float(rng.uniform()),
            "shadow": 0.1 + 0.8 * label,
            "fp_filter_oof": 0.5,
            "label": label,
        }
        for label in [0, 1] * 20
    ]
    base = {
        "detector": 0.45,
        "anomaly": 0.15,
        "shadow": 0.15,
        "fp_filter": 0.15,
        "persistence": 0.10,
    }
    weights, best = grid_search(rows, base, step=0.05)
    detector_only = fused_ap(rows, {"detector": 1.0}, None)
    assert best == pytest.approx(1.0) and best >= detector_only
    assert weights["shadow"] > 0 and weights["anomaly"] == 0.15 and weights["persistence"] == 0.10
    assert sum(weights.values()) == pytest.approx(1.0)


def test_cross_validated_calibration_lowers_ece() -> None:
    rng = np.random.default_rng(0)
    fused = rng.uniform(0, 1, 2000)
    labels = (rng.uniform(0, 1, 2000) < fused**2).astype(float)
    images = [f"img{i}" for i in range(2000)]
    calibrated = cross_validated(fused, labels, images, folds=5)
    assert expected_calibration_error(calibrated.tolist(), labels.tolist()) < 0.05
    assert expected_calibration_error(fused.tolist(), labels.tolist()) > 0.1
