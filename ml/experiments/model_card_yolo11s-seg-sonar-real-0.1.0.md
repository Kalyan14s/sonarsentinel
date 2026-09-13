# Model Card — `detector/yolo11s-seg-sonar-real@0.1.0` (draft)

> Draft for the CPU baseline. The registry folder `models/detector/yolo11s-seg-sonar-real/0.1.0/` is git-ignored, so this card is kept here and copied next to the weights when they are pushed to DVC. Template: [MODEL_CARD_TEMPLATE](../../docs/ml/MODEL_CARD_TEMPLATE.md).

| | |
|---|---|
| **Model ID** | `detector/yolo11s-seg-sonar-real@0.1.0` |
| **Kind** | detector |
| **Status** | candidate (CPU baseline; not for operational use) |
| **Date** | 2026-09-13 |
| **Owner role** | R1 (ML Lead) |
| **Git commit** | `69f90cb` |
| **Experiment(s)** | [EXP-20260913-baseline](EXP-20260913-baseline.md) |
| **Replaces** | — (first detector; before it, the rule-based `classical-bright-target@0.1.0` stand-in) |

---

## 1. Model details

| Item | Value |
|---|---|
| Architecture | Ultralytics YOLO11s-seg |
| Framework / versions | torch 2.14.0+cpu, ultralytics 8.4.150 |
| Input | 640×640×3 uint8; channels: raw normalised, Lee despeckled, local std, from the SonarSentinel preprocessing pipeline |
| Output | boxes, masks and scores for 5 classes |
| Classes | `shipwreck, pipe, cylinder, ghost_net, debris_other` — **only `cylinder` has training data** |
| Pretraining | COCO weights from Ultralytics (`yolo11s-seg.pt`) |
| Training config | `args.yaml` / `train_record.json` next to the weights: 20 epochs, imgsz 640, batch 8, freeze 10, cosine LR, flips, brightness 0.3, scale 0.3, mosaic (off for the last 5 epochs), copy-paste 0.4 |
| Files | `best.pt` (19.6 MB) |
| Licence | Ultralytics YOLO11 is AGPL-3.0 (compatible with the project licence); training data CC BY 4.0 (mine-SSS D2). See [Licences](../../docs/legal/LICENSES_AND_COMPLIANCE.md) |

## 2. Intended use

- **Primary use:** exercising the detection path of the SonarSentinel pipeline and serving as the reference for later detector experiments.
- **Intended users:** the development team.
- **Out of scope:** any operational survey decision; classes other than `cylinder`; sonar other than the mine-SSS data it was trained on without revalidation; images not preprocessed by the pipeline.

## 3. Training data

| Source | Images | Objects | Real/synthetic | Manifest |
|---|---|---|---|---|
| Mine SSS 2024 (D2), sites 2010 + 2018 | 150 (100 with objects, 50 background) | 118 `cylinder` (MILCO) | Real | `sonar-seg@0.1.0` |
| **Total** | 150 | 118 | synthetic share 0% | |

- **Preprocessing:** 3-channel conversion by `preprocess/channels.py` (pipeline 0.1.0); ground resolution assumed 0.10 m/px for D2.
- **Known biases:** one sonar, one object type, few sites; NOMBO (non-mine-like bottom objects) not yet reviewed, so some real objects are unlabelled background.

## 4. Evaluation data

| Set | Description | Images / objects | Sites |
|---|---|---|---|
| Validation | real, site-held-out | 93 / 28 cylinders | 2017 |
| Ghost-net holdout (TD-09) | synthetic nets on unseen backgrounds | 200 / 329 nets | 2017 backgrounds |
| Frozen test (TD-08) | real, site-held-out | 120 / 242 cylinders | 2015 — **not used** (reserved for release candidates) |
| Contact-free lines (TD-11) | for FP/km² | — | not available yet |

## 5. Performance

### 5.1 Overall (validation, 95% bootstrap CI)

| Metric | This model | PRD target |
|---|---|---|
| mAP@50 (box) | 0.283 (0.174–0.456) | ≥ 0.70 (frozen test) |
| mAP@50 (mask) | 0.280 | report |
| Ghost-net recall (TD-09) | 0.00 (no ghost-net training data; 37 of 329 nets detected as `cylinder`) | ≥ 0.80 |
| FP per km² | not measured | ≥ 50% reduction vs. detector-only |
| ECE | not calibrated (identity calibrator) | ≤ 0.10 |

### 5.2 Per class (validation, conf 0.25)

| Class | Precision | Recall | AP@50 | # objects |
|---|---|---|---|---|
| cylinder | 0.375 | 0.429 | 0.283 | 28 |
| shipwreck, pipe, ghost_net, debris_other | — | — | — | 0 (no training data) |

### 5.3–5.5
Not measured for this draft: size/seabed slices, robustness perturbations and deployment variants (ONNX in ST-100, TensorRT in ST-101). SAHI vs. full-image small-object recall: *pending* (`sahi_val.json`).

## 7. Limitations and failure modes
- Far below the PRD target: a 20-epoch CPU run on 118 objects. Treat every detection as a lead for review, not a finding.
- Detects only `cylinder`-like objects; ghost nets, wrecks, pipes and debris are missed or mislabelled.
- 20 false positives on 93 validation images at conf 0.25; they have not been inspected yet (error analysis open).
- Validation has 28 objects, so metrics move several points with a single hit or miss.

## 8. Ethical and safety considerations
- Outputs support human review only; no autonomous action.
- Training data contains no images of human remains.
- Mine-like objects in D2 are training targets; the model is not a mine-countermeasure tool.
- Restricted/partner data used: No.

## 9. How to use

```bash
sonarsentinel detect line_07.xtf --detector yolo \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt --out results/
```

```python
from sonarsentinel.detect.yolo import YoloDetector
det = YoloDetector("models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt", sahi=True)
detections = det.predict(tiles_3ch)   # tiles from the SonarSentinel preprocessing pipeline only
```

**Thresholds:** `conf` 0.20 (adapter default); tiers use the identity calibrator until ST-064.

## 10. Promotion checklist
- [ ] Metrics ≥ previous model on the frozen test set — not applicable yet
- [ ] Calibrator refitted and ECE recorded (ST-064)
- [ ] Robustness and deployment-variant tables filled
- [ ] Limitations section reviewed by a second team member
- [ ] Files and hashes in the registry; DVC pushed
- [x] CHANGELOG entry added

## 11. Version history

| Version | Date | Change | Key metric change |
|---|---|---|---|
| 0.1.0 | 2026-09-13 | CPU baseline, real data only | val mAP@50 box 0.283 |
