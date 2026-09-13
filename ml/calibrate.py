"""ST-064: isotonic calibration of the fused score, reliability table and ECE.

Runs the detector on the calibration split (default ``calib``, a site not used for training or
fusion tuning), computes the fused score with the configured weights (FP-filter scores from
``--fp-filter`` when given), labels detections TP/FP by IoU ≥ 0.5 and fits the isotonic
calibrator used by the pipeline (JSON breakpoints). The ECE reported for acceptance is measured
out of fold with image-grouped folds, with a bootstrap 95% interval over images; the saved
calibrator is fitted on all rows.

    python ml/calibrate.py --data data/processed/yolo/0.1.0-real --split calib \
        --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt \
        --fp-filter models/fp_filter/lgbm-fp/0.1.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scoring_data import ROOT, collect, image_folds, load_rows, save_rows  # noqa: E402
from sonarsentinel.scoring.fusion import (  # noqa: E402
    FpFilter,
    IsotonicCalibrator,
    expected_calibration_error,
    fuse,
    reliability_table,
)


def fused_scores(rows: list[dict[str, Any]], weights: dict[str, float]) -> np.ndarray:
    return np.array(
        [
            fuse(
                {
                    "detector": r["detector"],
                    "shadow": r.get("shadow"),
                    "fp_filter": r.get("fp_filter"),
                    "persistence": 0.5,
                },
                weights,
            )
            for r in rows
        ]
    )


def cross_validated(
    fused: np.ndarray, labels: np.ndarray, images: list[str], folds: int, seed: int = 0
) -> np.ndarray:
    """Out-of-fold calibrated probabilities (calibrator fitted on the other image folds)."""
    fold_of = image_folds(images, folds, seed)
    calibrated = np.zeros_like(fused)
    for fold in range(folds):
        test = fold_of == fold
        if not test.any():
            continue
        train = ~test
        calibrator = IsotonicCalibrator.fit(fused[train].tolist(), labels[train].tolist())
        calibrated[test] = [calibrator(v) for v in fused[test]]
    return calibrated


def bootstrap_ece(
    probabilities: np.ndarray, labels: np.ndarray, images: list[str], n: int = 200, seed: int = 0
) -> list[float]:
    rng = np.random.default_rng(seed)
    unique = sorted(set(images))
    index_of: dict[str, list[int]] = {}
    for i, name in enumerate(images):
        index_of.setdefault(name, []).append(i)
    values = []
    for _ in range(n):
        pick = [i for name in rng.choice(unique, len(unique)) for i in index_of[name]]
        values.append(
            expected_calibration_error(probabilities[pick].tolist(), labels[pick].tolist())
        )
    low, high = np.percentile(values, [2.5, 97.5])
    return [round(float(low), 4), round(float(high), 4)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="calib")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fp-filter", type=Path, default=None)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "backend" / "configs" / "pipeline.yaml"
    )
    parser.add_argument("--conf", type=float, default=0.05)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--name", default="isotonic")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "calibrator")
    args = parser.parse_args()

    registry = args.out / args.name / args.version
    cache = registry / f"detections_{args.split}.jsonl"
    rows = (
        load_rows(cache)
        if cache.exists()
        else collect(args.data, args.split, args.model, conf=args.conf)
    )
    save_rows(rows, cache)
    if args.fp_filter is not None:
        fp = FpFilter.load(args.fp_filter)
        for row, score in zip(rows, fp.predict([r["features"] for r in rows]), strict=True):
            row["fp_filter"] = score
    labels = np.array([r["label"] for r in rows], dtype=float)
    images = [r["image"] for r in rows]
    if len(rows) < 10 or labels.min() == labels.max():
        sys.exit(
            f"Need both TP and FP detections to calibrate (rows={len(rows)}, TP={labels.sum()})"
        )

    weights = {
        k: float(v)
        for k, v in yaml.safe_load(args.config.read_text("utf-8"))["scoring"]["weights"].items()
    }
    fused = fused_scores(rows, weights)
    oof = cross_validated(fused, labels, images, args.folds)
    ece_raw = expected_calibration_error(fused.tolist(), labels.tolist())
    ece_cv = expected_calibration_error(oof.tolist(), labels.tolist())
    calibrator = IsotonicCalibrator.fit(
        fused.tolist(), labels.tolist(), name=args.name, version=args.version
    )
    metrics = {
        "split": args.split,
        "rows": len(rows),
        "true_positives": int(labels.sum()),
        "images": len(set(images)),
        "fp_filter": str(args.fp_filter) if args.fp_filter else None,
        "weights": weights,
        "ece_uncalibrated": round(ece_raw, 4),
        "ece_cross_validated": round(ece_cv, 4),
        "ece_cross_validated_ci95": bootstrap_ece(oof, labels, images),
        "acceptance_ece_le_0_10": ece_cv <= 0.10,
        "folds": args.folds,
    }
    calibrator.save(registry / "calibrator.json", metrics=metrics)
    table = reliability_table(oof.tolist(), labels.tolist())
    lines = ["bin_low,bin_high,count,mean_predicted,observed"] + [
        f"{r['bin_low']:.1f},{r['bin_high']:.1f},{int(r['count'])},{r['mean_predicted']:.4f},{r['observed']:.4f}"
        for r in table
    ]
    (registry / "reliability.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
