# Experiments

One file per experiment, following the [experiment log template](../../docs/ml/EXPERIMENT_LOG_TEMPLATE.md). Tune on **validation** only; the frozen test split (site 2015) is used for release candidates.

| ID | Date | Owner | Hypothesis (short) | Key result | Decision |
|---|---|---|---|---|---|
| [EXP-20260913-baseline](EXP-20260913-baseline.md) | 2026-09-13 | R1 | Real-data-only YOLO11s-seg CPU baseline (20 epochs) | Val mAP@50 box 0.283 (CI 0.17–0.46); ghost-net recall 0.00 | Adopt as baseline ([model card draft](model_card_yolo11s-seg-sonar-real-0.1.0.md)) |
| [EXP-20260913-synth](EXP-20260913-synth.md) | 2026-09-13 | R1 | + 250 synthetic ghost-net tiles lift ghost-net recall to ≥ 0.60 without hurting cylinders | Blocked: stopped twice for low memory in epoch 2 | Rerun with more free memory or on GPU |
| [EXP-20260914-onnx](EXP-20260914-onnx.md) | 2026-09-14 | R6 | ONNX export matches PyTorch and keeps CPU runs within NFR-02 | TC-EDGE-001 38/38 matched, 0 score mismatches; 150 vs 170 ms/tile (idle CPU); ≈ 220 s per km on a real line | Adopt ONNX as default CPU runtime |
| [EXP-20260913-scoring](EXP-20260913-scoring.md) | 2026-09-13 | R1 | LightGBM FP filter, fusion weights and isotonic calibration on the CPU baseline | FP filter AUROC 0.747 (detector 0.692); fused AP 0.251 ≥ detector 0.246; ECE 0.144 → 0.048 (CI 0.027–0.080) | Adopt as tooling defaults; refit before G3 |
| [EXP-20260913-patchcore](EXP-20260913-patchcore.md) | 2026-09-13 | R1 | PatchCore on object-free seafloor flags objects on a held-out site | Tile AUROC 0.957; recall 0.74 at 1.2% false alarms | Adopt `patchcore-seafloor@0.1.0` |
