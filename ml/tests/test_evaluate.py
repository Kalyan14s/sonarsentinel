"""ST-057: evaluation metrics on hand-made predictions."""

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate import (  # noqa: E402
    ImageRecord,
    Instance,
    attach_predictions_jsonl,
    average_precision,
    evaluate,
    load_split,
    write_outputs,
)


def _square(x: float, y: float, s: float) -> np.ndarray:
    return np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]])


def test_perfect_predictions_give_ap_one() -> None:
    records = [
        ImageRecord(
            "a", [Instance(2, _square(0.1, 0.1, 0.2))], [Instance(2, _square(0.1, 0.1, 0.2), 0.9)]
        ),
        ImageRecord(
            "b", [Instance(3, _square(0.5, 0.5, 0.3))], [Instance(3, _square(0.5, 0.5, 0.3), 0.8)]
        ),
    ]
    metrics, curves = evaluate(records, bootstrap=20)
    assert metrics["map50_box"] == pytest.approx(1.0)
    assert metrics["map50_mask"] == pytest.approx(1.0)
    assert metrics["per_class"]["cylinder"]["recall"] == 1.0
    assert metrics["map50_box_ci95"] == [1.0, 1.0]
    assert set(curves) == {"cylinder", "ghost_net"}


def test_false_positive_ranked_first_lowers_ap_and_confusion() -> None:
    truth = Instance(2, _square(0.1, 0.1, 0.2))
    records = [
        ImageRecord(
            "a",
            [truth],
            [Instance(2, _square(0.6, 0.6, 0.2), 0.95), Instance(2, _square(0.1, 0.1, 0.2), 0.5)],
        ),
        ImageRecord(
            "b", [Instance(2, _square(0.3, 0.3, 0.1))], [Instance(4, _square(0.3, 0.3, 0.1), 0.7)]
        ),
    ]
    metrics, _ = evaluate(records, conf=0.25, kinds=("box",), bootstrap=0)
    cyl = metrics["per_class"]["cylinder"]
    assert cyl["n_truth"] == 2 and cyl["recall"] == 0.5 and cyl["precision"] == 0.5
    assert 0.2 < cyl["ap50_box"] < 0.5
    assert metrics["per_class"]["debris_other"]["ap50_box"] is None  # no truths
    assert metrics["confusion"]["cylinder"] == {"cylinder": 1, "debris_other": 1}
    assert metrics["confusion"]["background"] == {"cylinder": 1}


def test_average_precision_edge_cases() -> None:
    assert np.isnan(average_precision([], 0)[0])
    assert average_precision([], 3)[0] == 0.0
    ap, curve = average_precision([(0.9, True), (0.8, False), (0.7, True)], 2)
    assert ap == pytest.approx((51 * 1.0 + 50 * (2 / 3)) / 101, abs=1e-6)
    assert curve.shape == (3, 3)


def test_split_loading_predictions_file_and_outputs(tmp_path: Path) -> None:
    (tmp_path / "images" / "val").mkdir(parents=True)
    (tmp_path / "labels" / "val").mkdir(parents=True)
    (tmp_path / "images" / "val" / "t1.png").write_bytes(b"")
    (tmp_path / "labels" / "val" / "t1.txt").write_text("2 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n")
    preds = tmp_path / "preds.jsonl"
    preds.write_text(
        '{"image": "t1.png", "detections": [{"cls": 2, "score": 0.9, '
        '"polygon": [[0.1,0.1],[0.3,0.1],[0.3,0.3],[0.1,0.3]]}]}\n'
    )
    records = load_split(tmp_path, "val")
    attach_predictions_jsonl(records, preds)
    metrics, curves = evaluate(records, bootstrap=0)
    write_outputs(tmp_path / "out", metrics, curves)
    assert (tmp_path / "out" / "metrics.json").exists()
    assert (tmp_path / "out" / "pr_cylinder.csv").read_text().startswith("score,precision,recall")
    assert "true\\pred" in (tmp_path / "out" / "confusion.csv").read_text()
