# Model Card — `<kind>/<model-name>@<version>`

> **Template.** Copy to `models/<kind>/<name>/<version>/model_card.md` and fill in every section before a model is promoted ([Contributing §5](../../CONTRIBUTING.md#5-ml-experiment-hygiene)). Structure adapted from Mitchell et al., *Model Cards for Model Reporting* (FAT\* 2019). Delete the guidance in *italics* when done.

| | |
|---|---|
| **Model ID** | `detector/yolo11s-seg-sonar@1.2.0` *(example)* |
| **Kind** | detector · anomaly · fp_filter · calibrator · mask_refiner |
| **Status** | candidate · promoted · deprecated |
| **Date** | YYYY-MM-DD |
| **Owner role** | R1 (ML Lead) |
| **Git commit** | `abc1234` |
| **Experiment(s)** | `EXP-YYYYMMDD-…` ([log](EXPERIMENT_LOG_TEMPLATE.md)) |
| **Replaces** | `…@1.1.0` |

---

## 1. Model details

| Item | Value |
|---|---|
| Architecture | *e.g. Ultralytics YOLO11s-seg (~10 M parameters)* |
| Framework / versions | *torch x.y, ultralytics x.y* |
| Input | *640×640×3 uint8; channels: raw normalised, Lee despeckled, local std; 0.10 m/px ground range* |
| Output | *boxes, masks, scores for 5 classes* |
| Classes | `shipwreck, pipe, cylinder, ghost_net, debris_other` |
| Pretraining | *COCO weights from Ultralytics* |
| Training config | *link to `train_config.yaml`; epochs, imgsz, augmentations* |
| Files | `best.pt` (xx MB) · `best.onnx` (xx MB) · `best_int8.engine` (device-specific) |
| Licence | *Model weights inherit terms from framework and training data, see [Licences](../legal/LICENSES_AND_COMPLIANCE.md)* |

## 2. Intended use

- **Primary use:** *automated detection of man-made objects in side-scan sonar imagery preprocessed by the SonarSentinel pipeline, for decision support by marine analysts.*
- **Intended users:** *NIOT analysts, survey operators, cleanup/recovery planners.*
- **Out of scope:** *navigation-safety certification; forward-looking or synthetic aperture sonar without revalidation; images not preprocessed by the pipeline; identifying human remains; autonomous action without human review.*

## 3. Training data

| Source | Tiles | Classes contributed | Real/synthetic | Manifest |
|---|---|---|---|---|
| *AI4Shipwrecks* | | | Real | `sonar-seg@x.y.z` |
| *Mine SSS 2024* | | | Real | |
| *NOAA pseudo-labels (verified)* | | | Real | |
| *Ghost-net generator vX* | | | Synthetic | |
| **Total** | | | *synthetic share: xx% of positives* | |

- **Preprocessing:** *pipeline version, config hash*
- **Known biases:** *e.g. mostly temperate/freshwater seabeds; few real ghost nets; limited sonar models*

## 4. Evaluation data

| Set | Description | Tiles / objects | Sites |
|---|---|---|---|
| Frozen test (TD-08) | *real, site-held-out* | | |
| Ghost-net holdout (TD-09) | *synthetic on unseen backgrounds* | | |
| Real ghost-net samples (if any) | | | |
| Contact-free lines (TD-11) | *for FP/km²* | *km²* | |

## 5. Performance

### 5.1 Overall (frozen test set, 95% bootstrap CI)

| Metric | This model | Previous model | PRD target |
|---|---|---|---|
| mAP@50 (box) | | | ≥ 0.70 |
| mAP@50-95 (box) | | | report |
| mAP@50 (mask) | | | report |
| Ghost-net recall (TD-09) | | | ≥ 0.80 |
| FP per km² (TD-11, after scoring) | | | ≥ 50% reduction vs. detector-only |
| ECE (after calibration) | | | ≤ 0.10 |

### 5.2 Per class

| Class | Precision | Recall | AP@50 | # test objects |
|---|---|---|---|---|
| shipwreck | | | | |
| pipe | | | | |
| cylinder | | | | |
| ghost_net | | | | |
| debris_other | | | | |

### 5.3 By condition (disaggregated)

| Slice | mAP@50 | Notes |
|---|---|---|
| Object size < 2 m / 2–10 m / > 10 m | | |
| Seabed: sand / mud / rock / vegetated | | |
| Sonar frequency band | | |
| With quality flags (DROPOUT, HIGH_MOTION) | | |

### 5.4 Robustness

| Perturbation | mAP@50 | Δ vs. clean |
|---|---|---|
| Heavy speckle | | |
| 10% dropouts | | |
| Row jitter ±3 px | | |

### 5.5 Deployment variants

| Variant | Runtime / device | Size | Latency per 640 tile | mAP@50 | Δ vs. FP32 |
|---|---|---|---|---|---|
| FP32 | PyTorch, RTX 3060 | | | | — |
| ONNX FP32 | ONNX Runtime, 8-core CPU | | | | |
| TensorRT FP16 | Jetson Orin | | | | |
| TensorRT INT8 | Jetson Orin | | | | ≤ 3 points |

*Figures: PR curves, confusion matrix, reliability diagram → link to files in this folder.*

## 6. Explainability *(FP filter / fusion models)*
*SHAP summary plot, top features, known feature interactions.*

## 7. Limitations and failure modes
*Be specific and honest. Examples:*
- *Ghost-net performance is measured mainly on synthetic nets; real-world recall is unknown or based on N samples.*
- *Dense rock fields produce false positives in the `debris_other` class.*
- *Objects < 0.5 m are not reliably detected at 0.10 m/px.*
- *Performance drops near nadir and in dropout regions.*

## 8. Ethical and safety considerations
- *Outputs support human decisions; high-impact actions need expert confirmation.*
- *Training data excludes images of human remains; the model is not intended to detect them.*
- *Precise coordinates of protected wrecks may be sensitive; follow data-handling rules.*
- *Restricted/partner data used? Yes/No; terms.*

## 9. How to use

```python
from sonarsentinel.detect.yolo_detector import YoloDetector
det = YoloDetector.from_registry("detector/yolo11s-seg-sonar", version="1.2.0", runtime="auto")
detections = det.predict(tiles_3ch)   # tiles from the SonarSentinel preprocessing pipeline only
```

**Recommended thresholds:** `min_raw_score` = …; tiers per calibrator `isotonic@…`.

## 10. Promotion checklist
- [ ] Metrics ≥ previous model on the frozen test set (or trade-off approved and documented)
- [ ] Calibrator refitted and ECE recorded
- [ ] Robustness and deployment-variant tables filled
- [ ] Limitations section reviewed by a second team member
- [ ] Files and hashes in the registry; DVC pushed
- [ ] CHANGELOG entry added

## 11. Version history

| Version | Date | Change | Key metric change |
|---|---|---|---|
| | | | |
