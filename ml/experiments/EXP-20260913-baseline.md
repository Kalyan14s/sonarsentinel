# EXP-20260913-baseline

| | |
|---|---|
| **Owner role** | R1 |
| **Date(s)** | 2026-09-13 |
| **Backlog story** | ST-050 (ST-052 SAHI comparison, ST-057 evaluation) |
| **Status** | done |
| **Git commit** | `69f90cb` (code); registry folder is DVC/git-ignored |
| **Model kind** | detector |

## 1. Hypothesis
YOLO11s-seg fine-tuned from COCO weights on the real mine-SSS training sites learns the `cylinder` class well enough to give a usable CPU baseline (validation mAP@50 clearly above zero with a bounded CI) and a reference for the synthetic-data ablation (ST-051).

## 2. Baseline
None: first detector.

## 3. What changed
First run. Real data only; no synthetic tiles.

## 4. Setup

| Item | Value |
|---|---|
| Dataset manifest | `sonar-seg@0.1.0` → YOLO folder `data/processed/yolo/0.1.0-real` (`ml/datasets/prepare_yolo.py --variant real`) |
| Train | 150 images (sites 2010 + 2018): 100 with objects (118 cylinders), 50 background (ratio 0.5) |
| Validation | 93 images, site 2017: 17 with objects, 28 cylinders |
| Synthetic share of positives | 0% |
| Input | 3-channel PNG (raw normalised, Lee despeckled, local std), 640 px |
| Model / pretrained weights | `yolo11s-seg.pt` (Ultralytics COCO) |
| Key hyperparameters | imgsz 640 · epochs 20 · patience 10 · batch 8 · freeze 10 · cosine LR · close_mosaic 5 · deterministic |
| Augmentations | fliplr 0.5 · flipud 0.5 · hsv_v 0.3 · scale 0.3 · mosaic 1.0 · copy_paste 0.4 · no rotation, shear, perspective or hue |
| Seed | 42 |
| Hardware | Intel i5-13420H, 16 GB RAM, **CPU only**, workers 0 |
| Software | torch 2.14.0+cpu · ultralytics 8.4.150 |
| Wall-clock time | 0.80 h (20 epochs) |

**Commands**
```bash
python ml/train_detector.py --data data/processed/yolo/0.1.0-real/data.yaml \
    --model models/pretrained/yolo11s-seg.pt --name yolo11s-seg-sonar-real --version 0.1.0 \
    --epochs 20 --patience 10 --imgsz 640 --batch 8 --close-mosaic 5
python ml/evaluate.py --data data/processed/yolo/0.1.0-real --split val \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt --out models/detector/yolo11s-seg-sonar-real/0.1.0/eval_val
python ml/evaluate.py --data data/processed/yolo/0.1.0-real_synth --split holdout --bootstrap 0 \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt --out models/detector/yolo11s-seg-sonar-real/0.1.0/eval_holdout
python ml/compare_sahi.py --data data/processed/yolo/0.1.0-real --split val \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt --out models/detector/yolo11s-seg-sonar-real/0.1.0/sahi_val.json
```

## 5. Results (validation, site 2017)

`ml/evaluate.py` (101-point AP, IoU 0.5, 200 bootstrap resamples over images):

| Metric | Value |
|---|---|
| mAP@50 (box) | **0.283** (95% CI 0.174–0.456) |
| mAP@50 (mask) | 0.280 |
| Precision / recall @ conf 0.25 | 0.375 / 0.429 |
| Confusion @ conf 0.25 | 12 cylinders found, 16 missed, 20 false positives on 93 images |
| Ghost-net recall (synthetic holdout, 329 nets) | **0.00** as expected (no ghost-net training data): 37 nets detected as `cylinder`, 292 missed, 158 `cylinder` false positives on 200 images |
| Small-object recall, full image vs SAHI | *pending* |
| FP per km² | not measured (needs contact-free survey lines, TD-11) |

Ultralytics' own validation of the same weights (final epoch): box P 0.343, R 0.393, mAP@50 0.329, mAP@50-95 0.140; mask mAP@50 0.302, mAP@50-95 0.068. The two mAP@50 values differ because Ultralytics interpolates the PR curve differently; `evaluate.py` is the project's reference.

**Artifacts:** `models/detector/yolo11s-seg-sonar-real/0.1.0/` — `best.pt`, `results.csv`, `args.yaml`, `train_record.json`, `eval_val/` (metrics, PR curves, confusion); training plots in `runs/detector/yolo11s-seg-sonar-real/`.

## 6. Observations
- Validation mAP@50 swung between 0.20 and 0.35 across the last ten epochs: with 28 validation objects every hit moves AP by several points, so the CI is wide and single-epoch differences mean little.
- The training set is tiny (118 objects, one class) and the schedule is short (20 epochs on CPU, backbone partly frozen). The result is a pipeline baseline, not a measure of what YOLO11-seg can do on sonar.
- The model has never seen shipwrecks, pipes, ghost nets or debris; those classes rely on synthetic data (ST-051) and on AI4Shipwrecks (ST-010), both still to come.

## 7. Decision
- [x] **Adopt** as the CPU baseline `detector/yolo11s-seg-sonar-real@0.1.0` and as the reference for ST-051. It is configured in `backend/configs/pipeline.yaml`, so `sonarsentinel detect` uses it by default where the weights exist.

## 8. Next steps
1. ST-051 ablation: same schedule with synthetic ghost nets added (EXP-20260913-synth).
2. Add AI4Shipwrecks (ST-010) and reviewed NOMBO objects (ST-011) to reach several hundred real objects.
3. Full 200-epoch GPU training before Gate G3; report on the frozen test split only for the release candidate.
