"""ST-062: LightGBM false-positive filter on detector outputs of a site-held-out split.

Runs the registry detector on ``--split`` (default ``val``), labels each detection TP/FP by
IoU ≥ 0.5 with the ground truth, and trains a small LightGBM classifier on the ST-061 features.
AUROC is measured out of fold with image-grouped folds; the final model is fitted on all rows.
SHAP values come from LightGBM's own ``pred_contrib`` (no ``shap`` dependency).

Writes ``<out>/<name>/<version>/``: ``model.txt``, ``model.json`` (feature names, metrics),
``shap_summary.csv`` and ``detections_<split>_oof.jsonl`` (rows with out-of-fold FP-filter
scores, used by ``tune_fusion.py``).

    python ml/train_fp_filter.py --data data/processed/yolo/0.1.0-real --split val \
        --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scoring_data import (  # noqa: E402
    FEATURE_NAMES,
    ROOT,
    auroc,
    collect,
    feature_matrix,
    image_folds,
    load_rows,
    save_rows,
)

PARAMS = {
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 7,
    "min_data_in_leaf": 5,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
    "deterministic": True,
    "num_threads": 2,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="val")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--conf", type=float, default=0.05)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=150)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--name", default="lgbm-fp")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "fp_filter")
    args = parser.parse_args()

    import lightgbm

    started = time.time()
    registry = args.out / args.name / args.version
    cache = registry / f"detections_{args.split}.jsonl"
    rows = (
        load_rows(cache)
        if cache.exists()
        else collect(args.data, args.split, args.model, conf=args.conf)
    )
    save_rows(rows, cache)
    labels = np.array([r["label"] for r in rows], dtype=int)
    if len(rows) < 20 or labels.min() == labels.max():
        sys.exit(f"Need both TP and FP detections to train (rows={len(rows)}, TP={labels.sum()})")

    x = feature_matrix(rows)
    params = {**PARAMS, "seed": args.seed}
    folds = image_folds([r["image"] for r in rows], args.folds, args.seed)
    oof = np.zeros(len(rows))
    for fold in range(args.folds):
        train, test = folds != fold, folds == fold
        if not test.any() or labels[train].min() == labels[train].max():
            oof[test] = labels[train].mean()
            continue
        booster = lightgbm.train(
            params,
            lightgbm.Dataset(x[train], labels[train], feature_name=list(FEATURE_NAMES)),
            args.rounds,
        )
        oof[test] = booster.predict(x[test])

    final = lightgbm.train(
        params, lightgbm.Dataset(x, labels, feature_name=list(FEATURE_NAMES)), args.rounds
    )
    registry.mkdir(parents=True, exist_ok=True)
    final.save_model(str(registry / "model.txt"))
    contrib = final.predict(x, pred_contrib=True)[:, :-1]
    importance = sorted(
        zip(FEATURE_NAMES, np.abs(contrib).mean(axis=0), strict=True), key=lambda t: -t[1]
    )
    (registry / "shap_summary.csv").write_text(
        "feature,mean_abs_shap\n" + "".join(f"{n},{v:.5f}\n" for n, v in importance),
        encoding="utf-8",
    )

    detector_auroc = auroc([r["detector"] for r in rows], labels.tolist())
    metrics = {
        "split": args.split,
        "rows": len(rows),
        "true_positives": int(labels.sum()),
        "false_positives": int(len(rows) - labels.sum()),
        "images": len({r["image"] for r in rows}),
        "auroc_oof": round(auroc(oof.tolist(), labels.tolist()), 4),
        "auroc_detector_score": round(detector_auroc, 4),
        "folds": args.folds,
        "detector_conf": args.conf,
        "top_features": [n for n, _ in importance[:8]],
        "wall_clock_min": round((time.time() - started) / 60, 2),
    }
    meta = {
        "name": args.name,
        "version": args.version,
        "feature_names": list(FEATURE_NAMES),
        "params": params,
        "rounds": args.rounds,
        "detector": str(args.model),
        "metrics": metrics,
    }
    (registry / "model.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for row, score in zip(rows, oof, strict=True):
        row["fp_filter_oof"] = round(float(score), 4)
    save_rows(rows, registry / f"detections_{args.split}_oof.jsonl")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
