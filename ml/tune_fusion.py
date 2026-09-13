"""ST-063: tune the fusion weights on validation detections (grid search, AP).

Reads the rows written by ``train_fp_filter.py`` (detector score, shadow score and the
out-of-fold FP-filter score per detection, with TP/FP labels). The anomaly and persistence weights
stay at their configured values (no anomaly scores on tiles; persistence is 0.5 for single views);
the detector, shadow and FP-filter weights are searched on a grid that keeps all weights ≥ 0 and
summing to 1. Acceptance: AP of the fused score ≥ AP of the detector score alone.

    python ml/tune_fusion.py --rows models/fp_filter/lgbm-fp/0.1.0/detections_val_oof.jsonl \
        --n-truth 28 --out models/fusion/0.1.0/weights.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scoring_data import ROOT, average_precision, load_rows  # noqa: E402
from sonarsentinel.scoring.fusion import fuse  # noqa: E402

SEARCHED = ("detector", "shadow", "fp_filter")


def components(row: dict[str, Any]) -> dict[str, float | None]:
    return {
        "detector": row["detector"],
        "shadow": row.get("shadow"),
        "fp_filter": row.get("fp_filter_oof"),
        "persistence": 0.5,
        "anomaly": None,
    }


def fused_ap(rows: list[dict[str, Any]], weights: dict[str, float], n_truth: int | None) -> float:
    scores = [fuse(components(r), weights) for r in rows]
    return average_precision(scores, [r["label"] for r in rows], n_truth)


def grid_search(
    rows: list[dict[str, Any]],
    base: dict[str, float],
    *,
    step: float = 0.05,
    n_truth: int | None = None,
) -> tuple[dict[str, float], float]:
    """Best weights by AP; ties go to the weights closest to ``base``."""
    budget = 1.0 - base.get("anomaly", 0.0) - base.get("persistence", 0.0)
    ticks = round(budget / step)
    best: tuple[float, float, dict[str, float]] | None = None
    for a, b in itertools.product(range(ticks + 1), repeat=2):
        if a + b > ticks:
            continue
        values = (a * step, b * step, budget - (a + b) * step)
        weights = {**base, **{k: round(v, 4) for k, v in zip(SEARCHED, values, strict=True)}}
        ap = fused_ap(rows, weights, n_truth)
        distance = sum(abs(weights[k] - base.get(k, 0.0)) for k in SEARCHED)
        key = (round(ap, 6), -distance)
        if best is None or key > (round(best[0], 6), -best[1]):
            best = (ap, distance, weights)
    assert best is not None
    return best[2], best[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "backend" / "configs" / "pipeline.yaml"
    )
    parser.add_argument(
        "--n-truth", type=int, default=None, help="Ground-truth objects in the split"
    )
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = load_rows(args.rows)
    config_weights = {
        k: float(v)
        for k, v in yaml.safe_load(args.config.read_text("utf-8"))["scoring"]["weights"].items()
    }
    detector_ap = average_precision(
        [r["detector"] for r in rows], [r["label"] for r in rows], args.n_truth
    )
    config_ap = fused_ap(rows, config_weights, args.n_truth)
    weights, best_ap = grid_search(rows, config_weights, step=args.step, n_truth=args.n_truth)
    result = {
        "rows": len(rows),
        "true_positives": sum(r["label"] for r in rows),
        "n_truth": args.n_truth,
        "ap_detector": round(detector_ap, 4),
        "ap_config_weights": round(config_ap, 4),
        "ap_tuned": round(best_ap, 4),
        "config_weights": config_weights,
        "tuned_weights": weights,
        "acceptance_fused_ge_detector": best_ap >= detector_ap,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
