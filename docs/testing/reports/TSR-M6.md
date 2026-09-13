# Test Summary Report — TSR-M6 (Sprint 6 · Hardening, validation, edge & demo)

| | |
|---|---|
| **Milestone / gate** | M6 · G5 (release candidate, [Test Plan §8.2](../TEST_PLAN.md#82-release-candidate-m6-exit-criteria)) |
| **Date** | 2026-09-14 |
| **Prepared by** | R6 (QA) with R4 (API), R5 (dashboard) and R3 (geo) |
| **Template** | [Test Plan §9](../TEST_PLAN.md#9-test-summary-report-template) |
| **Recommendation** | **No-go for G5.** Do not tag `v1.0.0-rc1` (ADR-019 §9). The software is hardened and deployable for demos and development; model quality, real-world geolocation, streaming latency, usability and rehearsals are open (§6) |

## 1. Build under test

| Item | Value |
|---|---|
| Commit | Sprint 6 commit on `main` (after `38a0790`) |
| Pipeline version | 0.2.0 · report schema `report-1.0` |
| Models | `detector/yolo11s-seg-sonar-real@0.1.0` (PyTorch and ONNX) · `anomaly/patchcore-seafloor@0.1.0` · `fp_filter/lgbm-fp@0.1.0` · `calibrator/isotonic@0.1.0` |
| Environments | Windows 11, i5-13420H, 16 GB, CPU only (conda `sonarsentinel`: torch 2.14.0+cpu, onnxruntime 1.30.0); CI-equivalent venv without torch/ultralytics/lightgbm; Node 22 with vite 8.3, vitest 5.0, react-router-dom 7.18; GitHub Actions (backend, docs, frontend, conda, `security`, `docker` jobs) |
| Test data | Synthetic XTF (TD-01) and its TD-05/TD-07 fault variants, demo asset A3, mine-SSS validation tiles, USGS Grand Bay line `15CCT03_SSS_150528201100.xtf`; no TD-02, TD-08 run, TD-10, TD-11 or TD-13 |

## 2. Execution summary

| Area | Planned | Executed | Passed | Failed | Blocked / manual |
|---|---|---|---|---|---|
| TC-ROB / TC-ING-012 (robustness suite) | 8 variants | 8 | 8 | 0 | TC-DET-008 needs TD-08 and a trained detector |
| TC-PERF (benchmarks) | 001–006 | CPU rows | NFR-02, 06, 07 | NFR-04, NFR-05 | NFR-01 (no GPU), NFR-03 (no Jetson), map frame rate (browser) |
| TC-SEC | 001–006 | 001–004 | 001–003; 004 in CI | 0 | 005 LAN scan and 006 network monitoring manual |
| TC-EDGE | 001–004 | 001, 003 | 2 | 0 | 002 and 004 need a Jetson |
| TC-GEO-012 (charted wreck) | 1 | tooling smoke only | — | — | Needs a survey over a charted wreck (ST-013) |
| TC-USE-001/002 | 2 | 0 | — | — | Needs ≥ 3 new users |
| Backend unit + integration (pytest) | — | 396 | 396 | 0 | CI-equivalent venv: 391 passed, 3 skipped (torch/ultralytics) |
| ML tooling (pytest) | — | 28 | 28 | 0 | — |
| Frontend (Vitest) | — | 69 | 69 | 0 | One test failed once while the backend suite was loading the CPU and passed on rerun (timing-sensitive; watch in CI) |

Static checks: ruff lint and format clean; strict mypy clean on 71 source files; frontend lint, typecheck and production build pass (JS bundle 463 kB, 142 kB gzip); documentation check 0 problems; pre-commit clean.

### 2.1 Test case detail

| ID | Result | Evidence |
|---|---|---|
| AC-06 / TC-ROB | Pass (synthetic) | [Robustness report](ROBUSTNESS_2026-09-14.md): 7 fault variants complete with valid reports, ranged warnings and all 3 targets; corrupt header fails with `CORRUPT_HEADER`, exit 1. Two defects found and fixed (GPS gap across chunks, zeroed pings in gain) |
| Chunk retry / `CPU_FALLBACK` / `JOB_TIMEOUT` | Pass | `test_pipeline*.py`, `test_yolo*.py`, `test_jobs.py` (ADR-019 §2) |
| TC-PERF-002 (NFR-02 CPU) | Pass | [Benchmark report](BENCHMARK_2026-09-14.md): 240.5 s/km on the real 0.444 km line; 53.9 s median on a synthetic 1 km line |
| NFR-04 / NFR-05 | **Fail** | First detection 53.8 s (synthetic) / 106.8 s (USGS) vs. ≤ 15 s; progress gap 12.0 s / 60.7 s vs. ≤ 5 s |
| NFR-06 / NFR-07 | Pass | `best.pt` 19.6 MB ≤ 25 MB; peak memory 1,027 MB ≤ 8 GB |
| TC-SEC-001 | Pass | `test_security.py`: `../../evil.xtf` and `..\..\evil.xtf` stored only as `uploads/<survey>/evil.xtf` |
| TC-SEC-002 | Pass | PNG renamed `.xtf` rejected with 422 `CORRUPT_HEADER` (magic-byte check) |
| TC-SEC-003 | Pass | Over-limit upload returns 413; nothing beyond the limit written (test client sends one chunk, so a partial network stream is not simulated) |
| TC-SEC-004 | Pass (local) / CI | `npm audit`: 0 vulnerabilities after upgrades. `pip-audit` baseline in the [dependency scan](SECURITY_SCAN_2026-09-14.md): GDAL 3.12.3 (conda, unreachable HDF4/netCDF drivers) and diskcache (DVC tooling only) accepted for development. CI `security` job gates on pip-audit and `npm audit --audit-level=critical`; `docker` job runs Trivy on both images, failing on critical |
| TC-SEC-005 | Partial | `serve` defaults to 127.0.0.1; Compose ports bound to 127.0.0.1; LAN scan not run |
| TC-SEC-006 | Not run | Needs network monitoring during an offline AC-01 run |
| TC-EDGE-003 | Pass | `test_watch.py`: file processed once after its size is stable, state survives restart, report and `SS1|…` alert lines ≤ 256 bytes written |
| TC-E2E-004 (Docker) | CI build + health smoke | Images built and `/api/v1/health` checked in CI; fresh-install timing and browser run manual |
| ST-096 / ST-098 / ST-099 UI | Pass (Vitest) | Review queue keys and undo, history filters/delete, settings validation and save, basemap switch and offline badge |
| TC-GEO-012 | Tooling only | `scripts/validate_charted_wreck.py` on demo A3 (synthetic truth): matched detection 2.62 m from truth, within 2× its 2.07 m uncertainty. Not a real charted-wreck result |

## 3. Acceptance criteria

| AC | Result | Evidence / note |
|---|---|---|
| AC-01 | Pass (API + UI units) | TC-E2E-001, TC-UI-003 (TSR-M5); browser run on TD-02 not done |
| AC-02 | Pass (API + UI units) | TC-E2E-003, TC-UI-009 |
| AC-03 | Pass (API level) | TC-E2E-002; GPS-gap interpolation now works across chunk borders |
| AC-04 | Pass | TC-CONF-001/002, TC-UI-004 |
| AC-05 | **Fail / blocked** | No GPU-trained detector (ST-051); demo net found only as a hidden `cylinder` |
| AC-06 | **Pass (synthetic)** | Robustness suite |
| AC-07 | Partial | Four formats generated and structure-tested; Excel, QGIS, Google Earth checks not done |
| AC-08 | **Blocked** | Needs curated shadow/rock false positives (TD-13) |
| AC-09 | **Waived** | No Jetson (ST-101) |
| AC-10 | Partial | Offline MBTiles basemap, tiles endpoint and settings switch built; network-off run not done |

## 4. Measurements

| Metric | Target | Measured | Status |
|---|---|---|---|
| CPU time per km (NFR-02) | ≤ 300 s | 240.5 s (real, 0.444 km) · 53.9 s (synthetic 1 km, median of 3) | Pass |
| GPU time per km (NFR-01) | ≤ 60 s | not measured (no GPU) | Open |
| Edge real-time factor (NFR-03) | ≥ 1× | not measured (no Jetson) | Waived |
| First detection event (NFR-04) | ≤ 15 s | 53.8 s / 106.8 s | **Fail** |
| Progress interval (NFR-05) | ≤ 5 s | 12.0 s / 60.7 s | **Fail** |
| FP32 detector size (NFR-06) | ≤ 25 MB | 19.6 MB | Pass |
| Peak memory (NFR-07) | ≤ 8 GB | 1,027 MB | Pass |
| Detection mAP@50 | ≥ 0.70 (test) | 0.283 (val, CPU baseline) | Not met |
| Ghost-net recall (synthetic) | ≥ 0.80 | 0.00 (no ghost-net training data) | Not met |
| ECE | ≤ 0.10 | 0.048 (calib, CPU baseline tooling) | Met as tooling evidence |
| Charted-wreck median error | ≤ 10 m | not measured | Open |

## 5. Open defects

| ID | Severity | Summary | Owner |
|---|---|---|---|
| D-M6-01 | S2 | Detection quality remains the CPU baseline: AC-05 fails; real-line detections are all `hidden` (carries D-M5-01) | R1 |
| D-M6-02 | S2 | **Possible split leakage in the synthetic set:** the Datasets guide records synthetic training backgrounds from sites 2010, 2015, 2018 and 2021, so training tiles reuse seabed pixels from the test site (2015) and the calibration site (2021). The existing leakage check (real-image site membership, thumbnail correlation) passes but does not cover synthetic backgrounds. Regenerate synthetic tiles with backgrounds from training sites only and re-run the leakage check before GPU training (ST-051) | R1, R2 |
| D-M6-03 | S3 | NFR-04/05: detections are sent only after all chunks are merged and progress once per chunk | R4 |
| D-M6-04 | S3 | Position uncertainty has no GPS-gap term; interpolated positions get the same `uncertainty_m` | R3 |
| D-M6-05 | S3 | Health `runtime` can report `cuda` while `sonarsentinel detect` builds the YOLO detector on CPU; the ONNX session is loaded several times in one run | R4, R6 |
| D-M6-06 | S4 | Settings: coordinate format (DD/DMS) is saved but not applied to the display; Re-run only pre-fills the survey name | R5 |
| D-M6-07 | S4 | Documentation inconsistencies found by the report draft: split ratios (70/15/15 vs. 70/10/5/15) and demo water depth (~2 vs. ~3 m) | R6 |
| D-M5-02…04, D-M4-03 | S3 | Still open from TSR-M5 (multi-line mosaic, cancelled-job report, undo of reclassify, double validation upload) | R3, R4, R5 |

## 6. Waivers and limitations

- **Model quality (AC-05, mAP, ghost-net recall, AC-08):** needs GPU training on data free of D-M6-02, the AI4Shipwrecks conversion (ST-010) and curated false positives (TD-13).
- **Jetson (ST-101, AC-09, NFR-03, TC-EDGE-002/004):** no hardware; waived for this release.
- **Charted-wreck validation (ST-037):** tooling ready, needs a survey over a charted wreck (ST-013); demo assets A1/A2 depend on it.
- **GPU benchmark (NFR-01):** no GPU workstation.
- **Docker:** images are only built, health-checked and scanned in CI; not run on a user machine.
- **People-dependent:** usability test (ST-113), three rehearsals and backup video (ST-115), screenshots, P0 freeze decision, team ID and idea PDF upload.

## 7. Go / No-go

- **G5: No-go.** Test Plan §8.2 is not met: AC-05 and AC-08 fail or are blocked, charted-wreck error is not measured, NFR-04/05 fail, and ML metrics are far below target (documented honestly above). `v1.0.0-rc1` is not tagged.
- **M6 engineering scope: Go.** Robustness, CPU benchmarks, security tests and scans, Docker images, watch mode, review queue, history, settings and offline basemap are implemented and covered by automated tests; the manuals match the implementation.
