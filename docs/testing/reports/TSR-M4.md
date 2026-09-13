# Test Summary Report — TSR-M4 (Sprint 4 · Scoring, reports & API)

| | |
|---|---|
| **Milestone / gate** | M4 · G3 (model quality) |
| **Date** | 2026-09-13 |
| **Prepared by** | R6 (QA) with R1 (ML) and R4 (backend) |
| **Template** | [Test Plan §9](../TEST_PLAN.md#9-test-summary-report-template) |
| **Recommendation** | **No-go for G3 (model quality). Go for Sprint 5 development** with the waivers in §6 |

## 1. Build under test

| Item | Value |
|---|---|
| Commit | Sprint 4 commit on `main` (after `286e499`) |
| Pipeline version | 0.2.0 (`backend/configs/pipeline.yaml`) |
| Models | `detector/yolo11s-seg-sonar-real@0.1.0` (CPU baseline) · `anomaly/patchcore-seafloor@0.1.0` · `fp_filter/lgbm-fp@0.1.0` · `calibrator/isotonic@0.1.0` |
| Environments | Windows 11, Intel i5-13420H, 16 GB, CPU only (conda `sonarsentinel`, torch 2.14.0+cpu, ultralytics 8.4.150, lightgbm 4.7.0); CI-equivalent venv without torch/ultralytics/lightgbm; GitHub Actions (Ubuntu + Windows) on push |
| Test data | Synthetic XTF (TD-01 generator), synthetic images, mine-SSS YOLO splits (`val` site 2017, `calib` site 2021); no TD-02, TD-08 (frozen test), TD-11 or TD-13 used |

## 2. Execution summary

| Area | Planned | Executed | Passed | Failed | Blocked / not run |
|---|---|---|---|---|---|
| TC-CONF (confidence) | 10 | 8 | 8 | 0 | 2 blocked: TC-CONF-005 (needs TD-13), TC-CONF-009 (needs TD-11) |
| TC-REP (reports) | 9 | 6 | 5 | 0 | 1 partial (TC-REP-002, no TD-02); 3 not run: TC-REP-003, 004, 007 (Sprint 5 stories ST-072 and filtered export) |
| TC-API (API) | 9 | 8 | 5 | 0 | 3 against the mock only (TC-API-004, 005, 007; real endpoints are ST-083/084/086 in Sprint 5); TC-API-009 not run (schemathesis not installed) |
| TC-GEO (Sprint 4 items) | 2 | 2 | 2 | 0 | — (TC-GEO-009 layback, TC-GEO-013 cross-line merge) |
| Backend unit + integration (pytest) | — | 260 | 260 | 0 | CI-equivalent venv: 258 passed, 2 skipped (need torch/ultralytics) |
| ML tooling tests (pytest) | — | 28 | 28 | 0 | — |
| Frontend (Vitest) | — | 16 | 16 | 0 | TC-UI-001/002 automation is scheduled for Sprint 5 |

Static checks: ruff lint and format clean (backend, ml, scripts); strict mypy clean on 56 source files; frontend lint, typecheck and build pass; documentation check 0 problems.

### 2.1 Test case detail

| ID | Result | Evidence |
|---|---|---|
| TC-CONF-001 | Pass | `test_pipeline_scoring.py::test_confidence_range_and_schema`, `test_scoring_fusion.py::test_fused_clipped_to_unit_interval` |
| TC-CONF-002 | Pass | `test_scoring_fusion.py::test_tier_boundaries` (79.9/80.0/50.0/49.9 with anomaly ≥ τ and < τ/29.9) |
| TC-CONF-003 | Pass | fused recomputed within 1e-6: unit and end to end (`test_pipeline_scoring.py`, `test_pipeline_anomaly.py`) |
| TC-CONF-004 | Pass | object with shadow beats shadow-only patch by ≥ 0.3 (`test_scoring_shadow.py`) |
| TC-CONF-005 | Blocked | AC-08 needs 50 curated shadow/rock false positives (TD-13) |
| TC-CONF-006 | Pass | synthetic 1 m object height within ±30%, starboard and port |
| TC-CONF-007 | Pass (scoring rule) | dropout penalty lowers fused score; `DROPOUT` flag set by the pipeline when rows overlap a dropout. An end-to-end fixture with a target inside a dropout is still to add |
| TC-CONF-008 | Pass (tooling) | calib split ECE 0.144 → **0.048** out of fold (95% CI 0.027–0.080) with the CPU baseline ([EXP-20260913-scoring](../../../ml/experiments/EXP-20260913-scoring.md)) |
| TC-CONF-009 | Blocked | FP/km² reduction needs contact-free survey lines (TD-11) |
| TC-CONF-010 | Pass | LightGBM out-of-fold AUROC 0.747; SHAP summary produced |
| TC-REP-001 | Pass | reports from single-line, two-line, image-only and API-job runs validate against `report-1.0` |
| TC-REP-002 | Partial | CSV written and read back in the CLI integration test; row-by-row CSV↔JSON on TD-02 not run |
| TC-REP-005, 006, 008 | Pass | metadata and summary counts; determinism apart from `generated_utc`/`duration_s`; CLI `detect --formats json,csv` |
| TC-REP-009 | Pass | one chip per detection with `mask`, `shadow`, `anomaly`, `none` overlays (unit and CLI end to end) |
| TC-API-001, 002, 003 | Pass | `test_api_surveys.py`: 202 with IDs and `ws_url`; validate metadata and no-navigation warning; 400/404/413/415/422 error codes |
| TC-API-006 | Pass | running job cancelled within one chunk; finished job → 409 |
| TC-API-008 | Pass | `/api/v1/health` |
| TC-GEO-009 | Pass | 100 m cable, 20 m depth → 97.98 m astern, `LAYBACK_ESTIMATED` |
| TC-GEO-013 | Pass | two synthetic lines → merged detections with `n_views = 2`, persistence 0.75, removal/update events |

## 3. Acceptance criteria

| AC | Result | Evidence / note |
|---|---|---|
| AC-04 (confidence 0–100, tier consistent; UI slider) | **Partial** | Confidence range and tier consistency pass (TC-CONF-001/002); the UI slider part is Sprint 5 (TC-UI-004) |
| AC-07 (JSON validates; CSV opens with correct columns) | **Partial** | JSON validates in CI; CSV columns generated per 06 §3.1; opening in Excel/LibreOffice is a manual check not yet done |
| AC-08 (≥ 50% shadow-only FPs demoted) | **Blocked** | Needs TD-13 |

## 4. Metrics against targets

| Metric | Target | Measured | 95% CI | Status |
|---|---|---|---|---|
| mAP@50 (box) | ≥ 0.70 (G3 gate: ≥ 0.56) | 0.283 (val, CPU baseline) | 0.174–0.456 | **Fail** |
| Ghost-net recall (TD-09) | ≥ 0.80 (G3: ≥ 0.64) | not measured (ST-051 blocked) | — | **Not measured** |
| FP/km² reduction after scoring | ≥ 50% (G3: ≥ 40%) | not measured (no TD-11) | — | **Not measured** |
| ECE after calibration | ≤ 0.10 | 0.048 (calib, out of fold) | 0.027–0.080 | Pass (tooling on CPU baseline) |
| Geolocation error | ≤ 10 m | not in scope this sprint (ST-037) | — | — |
| Throughput (1 km in 60 s / 5 min) | NFR-01…07 | not in scope this sprint (ST-112) | — | — |

## 5. Open defects

| ID | Severity | Summary | Owner |
|---|---|---|---|
| D-M4-01 | S2 | Detector far below the model-quality targets (CPU baseline on 118 objects) | R1 |
| D-M4-02 | S3 | With the CPU-baseline calibrator almost every confidence is below 40, so real reports are mostly `hidden`; the top reliability bin holds 2 false positives | R1 |
| D-M4-03 | S3 | `POST /surveys/validate` needs the whole file, so the upload screen sends a 2 GB XTF twice (validate, then upload) | R4, R5 |
| D-M4-04 | S3 | No end-to-end fixture for TC-CONF-007 (target inside a dropout) | R6 |
| D-M4-05 | S4 | Mock fixtures record the local FP-filter/calibrator versions; regenerate after refitting | R4 |
| D-M4-06 | S4 | Local conda env only: `import torch` fails with WinError 127 when `test_api_main.py` runs after the job tests in the same process (normal order passes; CI has no torch) | R6 |

## 6. Waivers and limitations

- **Model quality (G3):** waived for continuing development only. GPU training (ADR-016), ST-051/ST-055 and real labels (ST-014) are required before G3 can pass.
- **Scoring artefacts** (`lgbm-fp@0.1.0`, `isotonic@0.1.0`) were fitted on 20 and 33 true positives from the CPU baseline; they validate the tooling (ADR-017 §7) and must be refitted.
- **Job worker** is a single thread (ADR-017 §10), not ADR-001 process workers.
- **Layback** does not apply the along-track time lag (no formula in the design).

## 7. Go / No-go

- **G3 model quality: No-go.** Exit criterion "model metrics ≥ 80% of PRD targets" is not met.
- **M4 functional scope: Go.** Scoring, calibration tooling, reports with chips, upload API, storage and jobs run end to end on the real pipeline and are covered by automated tests.
