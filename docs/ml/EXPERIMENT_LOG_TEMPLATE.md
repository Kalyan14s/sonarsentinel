# Experiment Log

> **Template.** Keep one file per experiment in `ml/experiments/EXP-YYYYMMDD-<short-name>.md` and add a row to the index in `ml/experiments/README.md`. Tune on **validation** only; touch the frozen test set only for release candidates ([Test Plan §6.1](../testing/TEST_PLAN.md#61-ml-evaluation-protocol)).

## Experiment index (copy into `ml/experiments/README.md`)

| ID | Date | Owner | Hypothesis (short) | Key result (val) | Decision |
|---|---|---|---|---|---|
| EXP-20261006-baseline | 2026-10-06 | R1 | Real-data-only baseline | mAP@50 0.xx | Keep as baseline |
| EXP-20261007-synth40 | 2026-10-07 | R1 | +40% synthetic improves ghost-net recall | GN recall 0.xx → 0.xx | Adopt |

---

# EXP-YYYYMMDD-<short-name>

| | |
|---|---|
| **Owner role** | R1 |
| **Date(s)** | YYYY-MM-DD → YYYY-MM-DD |
| **Backlog story** | ST-0xx |
| **Status** | planned · running · done · abandoned |
| **Git commit** | `abc1234` |
| **Model kind** | detector · anomaly · fp_filter · calibrator · mask_refiner · generator |

## 1. Hypothesis
*One or two sentences: "Adding X will improve metric Y by at least Z because …"*

## 2. Baseline
*Experiment ID and its key validation metrics.*

## 3. What changed
*Only the differences from the baseline (data, model, augmentation, hyperparameters, preprocessing).*

## 4. Setup

| Item | Value |
|---|---|
| Dataset manifest | `sonar-seg@0.3.0` (sha256 …) |
| Train / val tiles | … / … |
| Synthetic share of positives | …% (generator `ghost_net@1.1.0`) |
| Preprocessing config hash | `sha256:…` |
| Model / pretrained weights | `yolo11s-seg.pt` |
| Key hyperparameters | imgsz 640 · epochs 200 · batch 16 · lr0 … · freeze 10 |
| Augmentations | fliplr 0.5 · flipud 0.5 · hsv_v 0.3 · mosaic 1.0 · copy_paste 0.4 · offline speckle/gain/dropout |
| Seed(s) | 42 (and 7, 123 if repeated) |
| Hardware | *e.g. Kaggle P100 16 GB / RTX 3060 12 GB* |
| Software | torch … · ultralytics … · CUDA … |
| Wall-clock time | … h |

**Command(s)**
```bash
python ml/train_detector.py --config ml/configs/exp-synth40.yaml --seed 42
python ml/evaluate.py --model runs/segment/exp-synth40/weights/best.pt --split val
```

## 5. Results (validation)

| Metric | Baseline | This experiment | Δ |
|---|---|---|---|
| mAP@50 (box) | | | |
| mAP@50 (mask) | | | |
| Recall @ review threshold | | | |
| Ghost-net recall (synthetic val) | | | |
| Small-object recall (< 2 m) | | | |
| FP per km² (val lines) | | | |
| Inference latency (ms/tile) | | | |

*Repeated seeds: report mean ± std.*

**Per-class notes:** …

**Artifacts:** `results.csv`, PR curve, confusion matrix, sample predictions (good and bad): *links/paths*

## 6. Observations
- *What went as expected, what didn't*
- *Error analysis: typical false positives / negatives (with tile IDs)*
- *Any data problems found (open a data issue)*

## 7. Decision
- [ ] **Adopt**: becomes the new baseline / release candidate
- [ ] **Reject**: reason
- [ ] **Inconclusive**: what is needed

## 8. Next steps
1. …
2. …
