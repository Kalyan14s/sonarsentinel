# Changelog

All notable changes to SonarSentinel are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

Categories: **Added** · **Changed** · **Deprecated** · **Removed** · **Fixed** · **Security** · **Models** (model/calibrator releases) · **Data** (dataset manifest versions)

## [Unreleased]

*(Phase 2 merged to `main` in `8d13648`, Phase 3 in `4237954`. Sprint 3 / Phase 4 on `main`.)*

### Added (Sprint 5)
- WebSocket `/ws/jobs/{job_id}` (ST-083): resume after `seq`, ping/pong, replay from memory or `job.log.jsonl`, live tail without duplicates, close 1000 after `done`/`error` and 4404 for unknown jobs; `done` now comes from the job manager after results are stored, with `report_urls` and `mosaic`
- Results API (ST-084): `GET /surveys`, `/surveys/{id}`, `/surveys/{id}/detections` (class, confidence range, tier, review status, flags, bbox, sort, paging), `/surveys/{id}/track` (track + quality segments), `/surveys/{id}/report` (JSON/CSV/GeoJSON/KML with `all|filtered|hazards|confirmed` scopes), `/surveys/{id}/mosaic.png`, `/detections/{id}`, `/detections/{id}/chip.png`; one shared filter module for the API, mock and exports
- Review `PATCH /detections/{id}` (ST-086): confirm, reject with reason, reclassify, undo; REVIEW rows and label store `labels/<yyyy-mm>/<detection_id>/label.json` + chip
- GeoJSON (RFC 7946) and KML exports with class folders, styles, footprints and track (ST-072)
- Dashboard (ST-092…095): live map with clustered markers, growing track, quality segments, footprints and mosaic overlay; reconnecting job subscription; client-side filters synced to the URL; windowed detection list with keyboard navigation; detection drawer with chip overlays, DD/DMS (same formatting as the backend), score breakdown, flags and review; reports & export screen; 50 Vitest tests
- Position uncertainty budget per detection (ST-035, `geo.uncertainty` defaults), surface-return band flag with optional suppression (ST-047), GCP thin-plate-spline mosaic GeoTIFF/PNG/bounds per survey (ST-036)
- ONNX export and runtime (ST-100): `ml/export_onnx.py` with TC-EDGE-001 parity check; `detection.runtime: auto` uses `best.onnx` when ONNX Runtime is installed
- Demo asset A3 (`demo/harbour_synthetic.*`, `scripts/make_demo_assets.py`), clearly labelled synthetic
- Sprint 5 plan; ADR-018

### Changed (Sprint 5)
- Cancelled jobs keep the detections found so far; failed jobs send `error` to WebSocket listeners
- API validation errors (including FastAPI's) use the `VALIDATION_ERROR` shape; the real API allows the dashboard dev origin
- `requirements-ml.txt` adds `onnx` and `onnxslim`

### Added (Sprint 4)
- Scoring (ST-060…065, ADR-017): shadow consistency score and height from shadow length; 36 model, shadow, geometry, edge, texture, context and quality features per detection (< 5 ms); fusion of detector, anomaly, shadow, FP-filter and persistence scores with renormalised weights; isotonic calibrator (JSON breakpoints, pool-adjacent-violators) and LightGBM FP filter loaded at run time when present; `anomaly` tier requires anomaly score ≥ τ
- Layback correction (ST-034): XTF layback field, manual value or cable-out estimate (`LAYBACK_ESTIMATED`); new `navigation.manual_layback_m`, `tow_point_height_m`, `antenna_to_tow_point_m`
- Cross-line clustering and persistence (ST-038): `run_survey` merges the same object seen on several lines (`n_views`, `detection_update` / `detection_removed` events)
- Detection chips (ST-073): 256 px PNG per detection with `mask`, `shadow`, `anomaly` and `none` overlays under `results/<survey_id>/chips/`; `chip_url` filled
- SQLite storage (ST-085): SQLAlchemy models for the 06 §4 tables, versioned migrations; job manager with a background worker, cancel within one chunk and job status (ST-082); `POST /surveys/validate` and `POST /surveys` with streamed uploads, size limit and file checks (ST-081)
- Upload screen S-01 (ST-091): drop zone, per-file validation and badges, nav CSV or "continue without GPS", advanced options, upload progress and cancel; live map follows `?job=`
- ML tooling: `ml/train_fp_filter.py` (out-of-fold AUROC, SHAP summary), `ml/tune_fusion.py` (grid search on AP), `ml/calibrate.py` (cross-validated ECE, reliability table), shared `ml/scoring_data.py`
- Sprint 4 plan; ADR-017

### Changed (Sprint 4)
- `pipeline_version` 0.2.0; `run_pipeline` gains `should_cancel`, `results_dir`, layback options; `sonarsentinel detect` writes chips next to the report
- Scoring config points to `models/fp_filter/lgbm-fp/0.1.0` and `models/calibrator/isotonic/0.1.0/calibrator.json`

### Fixed (Sprint 4)
- `alert_tier` put detections in the `anomaly` tier without checking the anomaly score against τ

### Added (Sprint 3)
- Thin slice (Gate G2): `pipeline.py` orchestrator (ST-075) runs S0–S7, detection, merge, measurement, scoring and report per file with job events (progress, track, warning, detection, done); `sonarsentinel detect` writes `report.json` and `report.csv` (ST-074)
- Detection: `Detector` interface, YOLO11-seg adapter with SAHI slicing (ST-052), rule-based stand-in `classical-bright-target@0.1.0`, merge/dedupe across tiles and chunks (ST-054), PatchCore anomaly model with `unknown_anomaly` regions (ST-053)
- Measurements: footprint polygon, length/width, orientation from heading, depth (ST-033)
- Report builder and JSON/CSV export (report schema 1.0), alert tiers, quality flags per detection
- FastAPI skeleton with `/api/v1/health`, `/api/v1/models`, `/docs` (ST-080); mock API with canned survey, filters, paging, CSV, review `PATCH` and WebSocket replay with `seq` resume (ST-087); `sonarsentinel serve [--mock]`
- Dashboard shell (ST-090): React + TypeScript + Vite, routing for all screens, design tokens, typed API client, generated report types, Live Map against the mock API
- ML: `ml/evaluate.py` (AP@50 box/mask, PR curves, confusion, bootstrap CI; ST-057), synthetic pipe and cylinder generators (ST-017), `prepare_yolo.py`, `train_detector.py` (with `--resume` for interrupted runs), `train_anomaly.py`, `compare_sahi.py`
- Integration test ST-110: synthetic XTF → CLI → schema-valid JSON/CSV, chunk-overlap dedupe, determinism, image-only path
- Sprint 3 plan; ADR-016 (own PatchCore, rule-based stand-in, CPU baselines)

### Changed (Sprint 3)
- `detect --detector auto` (default) uses trained YOLO11-seg weights when present, otherwise the rule-based stand-in; stand-in reports carry the `RULE_BASED_DETECTOR` warning
- CI installs the `api` extra and runs the frontend lint, typecheck, tests and build; `requirements-ml.txt` drops anomalib and documents the verified CPU stack

### Fixed (Sprint 3)
- Across-track gain: cap each column at its 99th percentile before the running mean, so bright objects no longer darken their own range bins
- CI: strict mypy without the ML packages (torch treated as an optional untyped import)

### Models (Sprint 3)
- `detector/yolo11s-seg-sonar-real@0.1.0`: CPU baseline, 20 epochs on 118 real cylinders; validation mAP@50 box 0.283 (95% CI 0.17–0.46), mask 0.280 ([EXP-20260913-baseline](ml/experiments/EXP-20260913-baseline.md))
- `anomaly/patchcore-seafloor@0.1.0`: ResNet-18 PatchCore, 3,000-patch memory bank; tile AUROC 0.957 on held-out site 2017 ([EXP-20260913-patchcore](ml/experiments/EXP-20260913-patchcore.md))

### Data (Sprint 3)
- Synthetic pipes and cylinders 1.0.0: 1,000 tiles each; YOLO folders `yolo/0.1.0-real` (real only) and `yolo/0.1.0-real_synth` (+ synthetic ghost nets, holdout 200 tiles)

### Added (Sprint 2)
- Navigation cleaning (ST-032): speed-gated invalid-fix detection, UTM Savitzky–Golay smoothing, circular heading smoothing, COG fallback
- Preprocessing stages (ST-040…046): bottom tracking with altitude resolution, gain normalisation, slant-range correction and along-track resampling, dropout detection and repair, motion flags, 3-channel input, tiling; `preprocess/pipeline.py` runs S2–S7 per chunk into `ProcessedChunk`
- `ml/datasets/xtf_to_tiles.py` (labelling tiles with sidecars), `scripts/preprocess_qa.py` + `ml/notebooks/preprocessing_qa.ipynb` (ST-048)
- Synthetic ghost-net generator v1 `ml/synth/ghost_net_generator.py` (ST-016)
- `ml/datasets/make_splits.py` (ST-015): site-grouped splits, holdout-site exclusion, leakage check, manifest, stats report, Ultralytics YAML
- Sprint 2 plan

### Data (Sprint 2)
- Synthetic ghost nets 1.0.0: 2,000 train tiles + 200 holdout tiles (generated locally, reproducible from seed 2026)
- Dataset manifest `sonar-seg@0.1.0` (mine-SSS + synthetic; test = site 2015, hash frozen)

### Fixed (Sprint 2)
- Bottom tracking on shallow-water Klein data: ignore thin artifact lines, estimate the water-column level from the leading samples with a relative rise, and remove long outlier runs with a 1,000-ping continuity check

### Added
- `SonarLog` contract 1.0 (ST-020): `image`, `ground_range_corrected`, warning codes, `has_navigation`
- XTF reader (ST-021) with header-only scan, truncated-file recovery, sensor/ship navigation, NavUnits handling, channel selection and port sample-order detection; memory-mapped storage and overlapping chunk views (ST-026)
- GeoTIFF reader (ST-022); image + navigation CSV reader with interpolation (ST-023); image-only path (ST-024); `ingest/reader.py` dispatcher and validate-style summary
- Geo: units/CRS conversion and UTM zones (ST-030); `pixel_to_latlon` for processed chunks, raw slant-range samples and GeoTIFF pixels (ST-031); DMS formatting; track length, bbox and GeoJSON export
- CLI `inspect` (JSON summary) and `track` (GeoJSON), with `--nav`, `--utm-epsg`, `--allow-no-gps`
- Report JSON Schema 1.0 with a validated example (Gate G1 candidate)
- Synthetic XTF generator for test data TD-01/TD-05 (`backend/tests/tools/make_synthetic_xtf.py`); `scripts/bench_xtf_memory.py`
- Dataset scripts: `convert_mine_sss.py` (ST-011), `build_normal_pool.py` (ST-012), `convert_ai4shipwrecks.py` (ST-010), with tests in `ml/tests`
- ADR-015 (proposed): reports use WGS84 geographic coordinates (PRD Q7)

### Changed
- `numpy`, `pandas`, `pyproj` are core dependencies; `jsonschema` added to dev; CI installs the `geo` extra and runs dataset script tests
- Architecture 02: contract fields and XTF reading details

### Fixed
- XTF port sample-order detection: correlate port and starboard range profiles instead of assuming the darker end is nadir, which was wrong in shallow water

### Data
- USGS Grand Bay 2015 (doi:10.5066/P9374DKQ, Klein 3900, public domain): 4 XTF lines (65 MB) added to DVC with provenance. Reader output matches pyxtf's parser on 10 pings per file (TC-ING-006), and tracks lie inside the survey bounding box
- Mine SSS (D2) converted locally: 1,170 images, 437 MILCO → `cylinder`, 231 NOMBO queued for review; normal seafloor pool of 1,687 tiles from object-free D2 images (KLSG download has no seafloor images)

## [0.3.0] — 2026-09-13 — Phase 1 complete (Sprint 0)

Phase 1 closed by the team lead; three team items (team ID, idea PDF upload, S3Simulator permission request) carried over to Phase 2.

### Added
- Working repository at `C:\dev\sonarsentinel` (git `main`); Phase 0 documentation baseline committed and tagged `docs-baseline-1.0`
- Backend scaffold (ST-001): `sonarsentinel` package with typed errors matching the API error model, config loading and hashing, upload validation (stage S0: extension, size, magic bytes), and CLI (`version`, `validate`, `config`; `detect` and `serve` are placeholders)
- `backend/environment.yml` (core + geo + dev), `backend/requirements-ml.txt` (Sprint 3), `.env.example`, root `ruff.toml`
- CI workflow (ST-002): backend lint, format check, strict mypy, pytest with coverage; documentation checks; frontend job that activates once `frontend/package.json` exists
- `scripts/fetch_test_data.py` with SHA-256 pinning and trust-on-first-use, manifest and tests (ST-004)
- pre-commit hooks: whitespace, end-of-file, YAML/TOML, merge conflicts, large files, ruff (`LICENSE` and deck binaries excluded)
- SIH 2026 idea deck draft (PPTX + PDF) built on the official template: `docs/hackathon/idea-deck/`
- `docs/planning/SPRINT_1_PLAN.md`, `docs/communications/OUTREACH_DRAFTS.md`, `ml/datasets/LICENSES.md` (dataset licence register)
- ADR-014: CSS Modules + CSS custom-property design tokens for the dashboard
- Placeholder READMEs for `frontend/`, `edge/`, `docker/`, `ml/`

### Changed
- Developer Setup: split environment files documented; test commands run from `backend/` (same as CI); commands available now vs planned; note on using conda without PATH
- Docs index lists the Sprint 1 plan, outreach drafts, licence register and idea deck
- README: status, quick start (works today vs planned)

### Notes
- Verified on Windows 11 with Miniforge 26.7.2 (installer SHA-256 matched the GitHub release digest; signature valid) and Python 3.11.16: GDAL 3.12.3, rasterio 1.4.4, pyproj 3.7.2, OpenCV 5.0.0, pyxtf 1.5.0 import correctly
- ruff check and format clean · mypy `--strict` no issues (14 files) · pytest 32 passed, 96% coverage · all pre-commit hooks pass
- Repository published: https://github.com/Kalyan14s/sonarsentinel (public); `main` and tag `docs-baseline-1.0` pushed
- First CI run on GitHub passed: backend (lint, types, tests on Ubuntu), documentation checks, frontend job
- CI job builds the conda environment and runs tests on ubuntu-latest and windows-latest: passing (ST-003)
- Branch protection on `main`: pull request required, 5 required checks, no force pushes or deletion (ST-006)
- 91 backlog stories created as GitHub issues with epic/priority/role labels and sprint milestones S0–S6 + Backlog
- DVC initialised (analytics off, local remote); datasets downloaded with provenance and added to DVC: mine-detection SSS (0.61 GB, MD5 verified), SeabedObjects-KLSG (48 MB). AI4Shipwrecks licence confirmed CC BY 4.0 (automated download blocked, needs browser download); S3Simulator samples kept locally for private evaluation only (no licence)
- Idea deck: team name "Vashishta" on the title slide and team badges (team ID pending)

## [0.2.0] — 2026-09-13 — Phase 0 complete

### Added
- `LICENSE`: official GNU AGPL-3.0 text; project licence decision recorded as ADR-013 (README, CONTRIBUTING and Licences & Compliance updated)
- `docs/planning/PHASE0_REVIEW_SIGNOFF.md`: Phase 0 review checklist, issue log and sign-off record per role
- SIH 2026 facts in the Project Plan, TODO and SIH Presentation: official idea template rules, idea deadline 30 Sept 2026 (milestone IS), team composition rules, finale proposed Dec 2026
- `TODO.md`: master phase-by-phase checklist covering all 91 backlog stories, gates, exit criteria and continuous tasks
- `scripts/docs/verify_docs.ps1`: automated documentation verification (links, anchors, IDs, wireframe frames)
- `docs/reports/DOCUMENTATION_VERIFICATION_REPORT.md`
- API spec: `GET /surveys` query parameters and `GET /surveys/{id}/waterfall` parameters

### Changed
- PRD §15 and Project Plan milestone exit criteria aligned (M3 thin slice, M4 JSON/CSV, M5 AC-01…05 + AC-07)
- Review API and data model: `reject_reason` added for rejected detections
- Literature Review and Datasets: 11 references verified; 7 corrected (full authors, venues, pages, DOIs); STARS is now cited as BMVC 2023 and S3Simulator as ICPR 2024 (LNCS 15316); † markers removed
- TODO: Phase 0 closing items updated; team details moved to Phase 1; SIH idea-submission tasks added to Phase 1
- Licences & Compliance v1.1: all *verify* items checked against primary sources (status column added); AI4Shipwrecks licence still unconfirmed (manual check moved to Phase 1)
- ADR-009 amended: dashboard uses Leaflet directly instead of react-leaflet (Hippocratic License 2.1 is incompatible with AGPL-3.0)
- Annotation Guidelines: SAM 2 (Apache-2.0) specified; SAM 3 excluded (licence prohibits military uses)
- Datasets: licence status per dataset recorded; S3Simulator and SeabedObjects-KLSG-II excluded (no licence); NOAA "not for navigation" notice required
- **Phase 0 closed:** documentation baseline (PRD v1.0, architecture) approved by the team lead (R6); R1–R5 confirmations and the `docs-baseline-1.0` tag moved to Sprint 0

### Fixed
- Edge alert message format in `07-deployment.md` now matches the S-08 wireframe
- Victim-image exclusion stated in PRD §8.1 and Project Idea dataset tables

## [0.1.0] — 2026-09-13 — Documentation baseline

### Added
- Project idea and Product Requirements Document (`docs/PROJECT_IDEA.md`, `docs/PRD.md`)
- Architecture set: system architecture, data pipeline, ML models, geotagging engine, API specification, data models, deployment, architecture decisions (`docs/architecture/`)
- Wireframes for 8 screens with navigation flow and visual language (`docs/wireframes/`)
- Project plan and product backlog (`docs/planning/`)
- Datasets guide, annotation guidelines, data management plan (`docs/data/`)
- Test plan and test cases with traceability matrix (`docs/testing/`)
- Developer setup, user manual, operations runbook (`docs/guides/`)
- Model card and experiment log templates (`docs/ml/`)
- Literature and technology review (`docs/research/`)
- SIH presentation content and demo script with judge Q&A (`docs/hackathon/`)
- Final project report template (`docs/reports/`)
- Licences & compliance (`docs/legal/`), security policy, contributing guide, GitHub issue/PR templates
