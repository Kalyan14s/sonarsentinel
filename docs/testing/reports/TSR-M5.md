# Test Summary Report — TSR-M5 (Sprint 5 · Dashboard)

| | |
|---|---|
| **Milestone / gate** | M5 · G4 (all P0 stories Done; AC-01…AC-05 and AC-07 end to end) |
| **Date** | 2026-09-14 |
| **Prepared by** | R6 (QA) with R4 (API) and R5 (dashboard) |
| **Template** | [Test Plan §9](../TEST_PLAN.md#9-test-summary-report-template) |
| **Recommendation** | **No-go for G4** (AC-05 and manual checks open; carried P0 data stories). **Go for Sprint 6** hardening with the waivers in §6 |

## 1. Build under test

| Item | Value |
|---|---|
| Commit | Sprint 5 commit on `main` (after `12e5e85`) |
| Pipeline version | 0.2.0 |
| Models | `detector/yolo11s-seg-sonar-real@0.1.0` (PyTorch and ONNX) · `anomaly/patchcore-seafloor@0.1.0` · `fp_filter/lgbm-fp@0.1.0` · `calibrator/isotonic@0.1.0` |
| Environments | Windows 11, i5-13420H, 16 GB, CPU only (conda `sonarsentinel`: torch 2.14.0+cpu, onnxruntime 1.30.0, ultralytics 8.4.150); CI-equivalent venv without torch/ultralytics/lightgbm; Node 22 + Vitest 2 (jsdom); GitHub Actions on push |
| Test data | Synthetic XTF and images (TD-01 generator), demo asset A3, mine-SSS validation tiles, USGS Grand Bay line `15CCT03_SSS_150528201100.xtf`; no TD-02, TD-11, TD-13 or TD-14 browser run |

## 2. Execution summary

| Area | Planned | Executed | Passed | Failed | Blocked / manual |
|---|---|---|---|---|---|
| TC-WS (WebSocket) | 6 | 4 | 4 | 0 | TC-WS-002/003 need timing on TD-02 (manual) |
| TC-UI (dashboard) | 10 + TC-UI-014 | 10 | 10 | 0 | TC-UI-010 (axe, screen reader) manual |
| TC-E2E | 3 | 3 (API level) | 3 | 0 | Browser end-to-end runner not installed |
| TC-API (Sprint 5 items) | 004, 005, 007, 009 | 3 | 3 | 0 | TC-API-009 (schemathesis) not installed |
| TC-REP (Sprint 5 items) | 003, 004, 007 | 3 | 3 | 0 | QGIS / Google Earth viewer checks manual |
| TC-GEO-010, 011; TC-PRE-012 | 3 | 3 | 3 | 0 | QGIS overlay and real shallow-water file manual |
| TC-EDGE-001 / TC-PERF-002 | 2 | 2 | 1 | 0 | TC-PERF-002 extrapolated (see §4) |
| Backend unit + integration (pytest) | — | 320 | 320 | 0 | CI-equivalent venv: 316 passed, 3 skipped (torch/ultralytics) |
| ML tooling (pytest) | — | 28 | 28 | 0 | — |
| Frontend (Vitest) | — | 50 | 50 | 0 | — |

Static checks: ruff lint and format clean (backend, ml, scripts); strict mypy clean on 64 source files in both environments; frontend lint, typecheck and production build pass; documentation check 0 problems.

### 2.1 Test case detail

| ID | Result | Evidence |
|---|---|---|
| TC-WS-001 | Pass | `test_ws.py`: progress first, strictly increasing `seq`, `done` last with four `report_urls` and mosaic, close 1000, report downloadable immediately |
| TC-WS-004 | Pass | Resume after a dropped connection without gaps or duplicates; replay from `job.log.jsonl` after the in-memory buffer is cleared |
| TC-WS-005 | Pass | Two-line survey emits `detection_removed` with `merged_into` |
| TC-WS-006 | Pass | Failing job emits `error` and ends `failed` |
| TC-UI-001, 002 | Pass | Upload screen tests (Sprint 4) |
| TC-UI-003 | Pass | Track grows, markers and counts update from WebSocket events |
| TC-UI-004 | Pass | Filtering 2,000 detections < 100 ms (filter function); slider updates the list |
| TC-UI-005, 006 | Pass | Drawer values equal the detection JSON, DMS identical to the Python formatter; copy writes `"13.084120, 80.312750"` |
| TC-UI-007 | Pass | Warning click zooms to its segment (map controller spy) |
| TC-UI-008 | Pass | Report URLs for four formats and scopes; GeoJSON/KML disabled without GPS |
| TC-UI-009 | Pass | Not-geotagged survey shows the pixel view and banner, no lat/lon |
| TC-UI-014 | Pass | Unexpected close → "Reconnecting…" → resume `after_seq` → no duplicate markers |
| TC-UI-010 | Manual | Keyboard shortcuts tested; axe and screen-reader pass not run |
| TC-E2E-001 | Pass (API level) | Upload synthetic XTF → WebSocket to `done` → survey, detections, track → CSV lat/lon equal JSON per `detection_id` |
| TC-E2E-002 | Pass (API level) | Image + nav CSV with fewer rows → `GPS_INTERPOLATED` |
| TC-E2E-003 | Pass (API level) | Image with "continue without GPS" → `NOT_GEOTAGGED`, null lat/lon, `pixel_bbox` |
| TC-API-004, 005, 007 | Pass | Filters/sort/paging against an independent reference; review rows and label store; four media types with `Content-Disposition` |
| TC-REP-003, 004, 007 | Pass (structure) | GeoJSON `[lon,lat]` and closed polygons; KML class folders and `lon,lat,0` placemarks; filtered/hazards/confirmed scopes |
| TC-GEO-010 | Pass | Heading term 1.745 m at 50 m / 2°; `uncertainty_m` on every geotagged detection end to end |
| TC-GEO-011 | Pass (residual) | GCP residual 0.20 m mean, 0.32 m max on a curved synthetic track; mosaic bounds contain every detection |
| TC-PRE-012 | Pass (synthetic) | Band columns match the analytic ground range on both sides |
| TC-EDGE-001 | Pass | ONNX vs PyTorch on 93 validation tiles: 38/38 matched, 0 score mismatches, 0 extra |
| TC-PERF-002 | Indicative pass | 0.444 km line in 97.5 s ≈ 220 s per km (target ≤ 300 s); not the 1 km reference line on an idle 8-core machine |

## 3. Acceptance criteria

| AC | Result | Evidence / note |
|---|---|---|
| AC-01 (XTF → track, streaming markers, 6-decimal WGS84; CSV = JSON) | **Pass (API + UI units)** | TC-E2E-001, TC-UI-003; browser run on TD-02 not done |
| AC-02 (image without GPS → pixel view, `NOT_GEOTAGGED`) | **Pass (API + UI units)** | TC-E2E-003, TC-UI-009 |
| AC-03 (image + CSV → geotagged, `GPS_INTERPOLATED`) | **Pass (API level)** | TC-E2E-002 |
| AC-04 (confidence/tier; slider hides and shows markers) | **Pass** | TC-CONF-001/002 (Sprint 4), TC-UI-004 |
| AC-05 (ghost-net recall ≥ 80%; `unknown_anomaly` with heatmap) | **Fail / blocked** | No GPU-trained detector (ST-051); demo A3 net found only as a hidden `cylinder`. The anomaly overlay is available in the drawer chip |
| AC-07 (JSON validates; CSV in Excel; GeoJSON in QGIS; KML in Google Earth) | **Partial** | All four formats generated and structure-tested; viewer checks not done |

## 4. Measurements

| Metric | Target | Measured | Status |
|---|---|---|---|
| Filter update, 2,000 detections | < 100 ms | < 100 ms (Vitest, jsdom) | Pass |
| Map frame rate, 2,000 clustered markers | ≥ 30 fps | not measured (needs a browser) | Open |
| CPU time per km (full default pipeline, ONNX) | ≤ 300 s | ≈ 220 s (0.444 km in 97.5 s) | Indicative pass |
| ONNX per-tile latency | report | 150 ms (PyTorch 170 ms), idle CPU | — |
| Mosaic GCP residual | < 1 m | 0.20 m mean / 0.32 m max | Pass |
| First detection event (NFR-04) / progress interval (NFR-05) | ≤ 15 s / ≤ 5 s | not measured on TD-02 | Open |

## 5. Open defects

| ID | Severity | Summary | Owner |
|---|---|---|---|
| D-M5-01 | S2 | Detection quality remains the CPU baseline: AC-05 fails; real-line detections are all `hidden` (carries D-M4-01/02) | R1 |
| D-M5-02 | S3 | Multi-line surveys keep only the last line's mosaic (each line writes `mosaic.*` in the same survey folder) | R3 |
| D-M5-03 | S3 | Cancelled jobs keep detections but have no downloadable report | R4 |
| D-M5-04 | S3 | Undo (`pending`) does not reverse a reclassification | R4 |
| D-M5-05 | S4 | S-06 score-breakdown / low-confidence / DMS options, basemap switcher, pointer coordinates and C/R/K review shortcuts not built | R5 |
| D-M5-06 | S4 | `npm install` reports 7 advisories in existing frontend dependencies (to review with the Sprint 6 dependency scan) | R6 |
| D-M4-03 | S3 | Still open: validation uploads whole files twice | R4, R5 |

## 6. Waivers and limitations

- **AC-05 / model quality:** waived for development; needs GPU training (ST-051, ST-055, ST-056).
- **Manual checks** (QGIS, Google Earth, Excel/LibreOffice, real-browser frame rate, axe/screen reader, NFR-04/05 on TD-02) are scheduled for the Sprint 6 validation week (ST-112, ST-113, ST-114).
- **Demo assets A1/A2** need a real survey over a charted wreck (ST-013).
- **Map tiles** are online until ST-099.

## 7. Go / No-go

- **G4: No-go.** P0 data stories carried from earlier phases, the ST-092 browser check, AC-05 and the AC-07 viewer checks are open.
- **M5 functional scope: Go.** Upload → live streaming map → filters → detail and review → four export formats work end to end against the real pipeline and are covered by automated tests.
