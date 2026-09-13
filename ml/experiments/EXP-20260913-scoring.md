# EXP-20260913-scoring

| | |
|---|---|
| **Owner role** | R1 |
| **Date(s)** | 2026-09-13 |
| **Backlog story** | ST-062 (FP filter), ST-063 (fusion weights), ST-064 (calibration) |
| **Status** | done (tooling evidence on the CPU baseline; ADR-017 §7) |
| **Git commit** | Sprint 4 commit on `main` (after `286e499`); registry folders are DVC/git-ignored |
| **Model kind** | fp_filter · calibrator |

## 1. Hypothesis
On detections of the CPU baseline detector, (a) a LightGBM filter on the ST-061 features separates true from false positives better than the detector score, (b) fusing detector, shadow, FP-filter and persistence scores ranks detections at least as well as the detector score alone, and (c) isotonic calibration of the fused score reaches ECE ≤ 0.10 on a site not used for fitting the filter or the weights.

## 2. Baseline
[EXP-20260913-baseline](EXP-20260913-baseline.md): `detector/yolo11s-seg-sonar-real@0.1.0`, validation mAP@50 box 0.283. Before Sprint 4 the pipeline used `fused = detector − penalties` and an identity calibrator.

## 3. What changed
New scoring stage (ADR-017): shadow score, 36 features, LightGBM FP filter, weighted fusion, isotonic calibrator.

## 4. Setup

| Item | Value |
|---|---|
| Detector | `yolo11s-seg-sonar-real@0.1.0`, conf ≥ 0.05, no SAHI, 640 px |
| Data | `data/processed/yolo/0.1.0-real` (mine SSS): FP filter and fusion on `val` (site 2017), calibration on `calib` (site 2021) |
| Labels | Detection = TP when IoU ≥ 0.5 with an unused ground-truth box (score order) |
| Features | `sonarsentinel.scoring.features` (same code as the pipeline); shadow side unknown on tiles, so both directions are scored and the stronger kept; altitude unknown (no height) |
| FP filter | LightGBM binary, 150 rounds, 7 leaves, min 5 rows per leaf, feature/bagging fraction 0.8, L2 1.0, seed 0; 5 image-grouped folds for out-of-fold scores |
| Fusion search | Detector, shadow and FP-filter weights on a 0.05 grid; anomaly 0.15 and persistence 0.10 fixed; persistence = 0.5 (single view) |
| Calibration | Pool-adjacent-violators isotonic fit on the fused score with the configured weights and the FP filter; ECE with 10 equal-width bins, out of fold over 5 image-grouped folds, bootstrap 95% CI over images (200) |
| Hardware / software | Intel i5-13420H, CPU only · lightgbm 4.7.0, ultralytics 8.4.150 |
| Wall-clock time | 39 s for all three steps |

**Commands**
```bash
python ml/train_fp_filter.py --data data/processed/yolo/0.1.0-real --split val \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt
python ml/tune_fusion.py --rows models/fp_filter/lgbm-fp/0.1.0/detections_val_oof.jsonl \
    --n-truth 28 --out models/fusion/0.1.0/weights.json
python ml/calibrate.py --data data/processed/yolo/0.1.0-real --split calib \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt --fp-filter models/fp_filter/lgbm-fp/0.1.0
```

## 5. Results

### 5.1 FP filter (`fp_filter/lgbm-fp@0.1.0`, validation)

| Metric | Value |
|---|---|
| Detections (TP / FP) | 137 (20 / 117) on 42 images |
| AUROC, detector score alone | 0.692 |
| **AUROC, FP filter (out of fold)** | **0.747** |

Top features by mean |SHAP| (LightGBM `pred_contrib`, full fit): ring texture similarity 0.88, detector score 0.54, FFT peak ratio 0.39, ripple FFT peak 0.36, GLCM homogeneity 0.34, ring contrast 0.30, shadow length 0.24, shadow coverage 0.21, GLCM contrast 0.19, extent 0.17. Full table: `models/fp_filter/lgbm-fp/0.1.0/shap_summary.csv`.

### 5.2 Fusion weights (validation, AP over 28 ground-truth objects)

| Scoring | AP |
|---|---|
| Detector score alone | 0.246 |
| Fused, configured weights (0.45 / 0.15 / 0.15 / 0.15 / 0.10) | **0.251** |
| Fused, best grid weights (detector 0.20, shadow 0.00, FP filter 0.55) | 0.278 |

Acceptance (AP fused ≥ AP detector) holds for both the configured and the tuned weights.

### 5.3 Calibration (`calibrator/isotonic@0.1.0`, calib split)

| Metric | Value |
|---|---|
| Detections (TP) | 402 (33) on 48 images |
| ECE of the fused score before calibration | 0.144 |
| **ECE after calibration, out of fold** | **0.048** (95% CI 0.027–0.080) |

Reliability (out of fold):

| Bin | Detections | Mean predicted | Observed |
|---|---|---|---|
| 0.0–0.1 | 288 | 0.048 | 0.052 |
| 0.1–0.2 | 77 | 0.132 | 0.234 |
| 0.2–0.3 | 29 | 0.217 | 0.000 |
| 0.3–0.4 | 6 | 0.342 | 0.000 |
| 0.9–1.0 | 2 | 1.000 | 0.000 |

## 6. Observations
- All three acceptance checks pass, but on small data: 20 true positives for the filter and the weights, 33 for the calibrator. The numbers show that the tooling works end to end on real detections; they are not model-quality evidence (ADR-017 §7).
- The tuned weights drop the shadow score to 0. On these tiles the shadow side and altitude are unknown, so the shadow score is weaker than in the pipeline, where the side comes from the nadir column. With 20 positives the AP gain (0.251 → 0.278) is within noise. **The configured weights stay unchanged.**
- The calibrator is honest about a weak detector: only ~8% of baseline detections are true, so almost every calibrated confidence is below 40 and would fall in the `hidden` tier. The two detections in the top bin are false positives that the isotonic fit on other folds mapped to 1.0 — a sign of too little data at high scores.
- Texture/context features (ring texture similarity, FFT periodicity, GLCM) matter more than geometry for separating cylinders from seabed clutter at this stage.

## 7. Decision
- [x] **Adopt as tooling defaults**: `fp_filter/lgbm-fp@0.1.0` and `calibrator/isotonic@0.1.0` are configured in `pipeline.yaml` and load when present (local runs); CI and fresh clones fall back to identity calibration without the filter.
- [ ] Refit both, and re-run the fusion search, on the GPU-trained detector and real labels before Gate G3 sign-off.

## 8. Next steps
1. Retrain with the GPU detector; refit the FP filter on `val` and the calibrator on `calib`, then check that high-score bins are populated.
2. Add labelled real detections (ST-014) and curated shadow/rock false positives (TD-13) so AC-08 and the shadow weight can be tested.
3. Report ECE on the frozen test split only for the release candidate.
