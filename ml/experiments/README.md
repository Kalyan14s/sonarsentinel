# Experiments

One file per experiment, following the [experiment log template](../../docs/ml/EXPERIMENT_LOG_TEMPLATE.md). Tune on **validation** only; the frozen test split (site 2015) is used for release candidates.

| ID | Date | Owner | Hypothesis (short) | Key result | Decision |
|---|---|---|---|---|---|
| [EXP-20260913-baseline](EXP-20260913-baseline.md) | 2026-09-13 | R1 | Real-data-only YOLO11s-seg CPU baseline (20 epochs) | Val mAP@50 box 0.283 (CI 0.17–0.46); ghost-net recall 0.00 | Adopt as baseline ([model card draft](model_card_yolo11s-seg-sonar-real-0.1.0.md)) |
| [EXP-20260913-patchcore](EXP-20260913-patchcore.md) | 2026-09-13 | R1 | PatchCore on object-free seafloor flags objects on a held-out site | Tile AUROC 0.957; recall 0.74 at 1.2% false alarms | Adopt `patchcore-seafloor@0.1.0` |
