# SonarSentinel — Product Backlog

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Owner** | PM (R6), groomed with all role owners |
| **Status** | Living document — mirror of the GitHub Projects board |

**Related:** [Project Plan](PROJECT_PLAN.md) · [PRD](../PRD.md) · [Test Cases](../testing/TEST_CASES.md) · [Contributing (Definition of Done)](../../CONTRIBUTING.md#7-definition-of-done-stories)

---

## 1. How to read this backlog

- **Epics** (`EP-NN`) group stories by WBS area.
- **Stories** (`ST-NNN`) are small enough to finish in one sprint.
- **Points:** Fibonacci (1, 2, 3, 5, 8). 1 point ≈ half a focused day. Team capacity ≈ **45–50 points/sprint** (6 people).
- **Sprint:** planned sprint (`S0`–`S6`). `BL` = backlog (not planned). ⭐ = stretch goal (dropped first if behind).
- **Owner:** role from the [Project Plan](PROJECT_PLAN.md#6-team-roles-and-responsibilities).
- **Refs:** PRD requirement IDs. Every story must meet the Definition of Done.

## 2. Sprint summary

| Sprint | Goal | Committed pts | Stretch pts |
|---|---|---|---|
| S0 | Team can build, test and collaborate; datasets downloading | 12 | — |
| S1 | Read sonar logs and put them on the map with correct GPS | 33 | — |
| S2 | Clean, normalised, tiled sonar data; training data ready | 42 | — |
| S3 | Trained models; end-to-end CLI report (thin slice) | 52 | — |
| S4 | Trustworthy confidence; reports; upload + jobs API | 52 | — |
| S5 | Live dashboard end to end (P0 freeze) | 47 | 5 |
| S6 | Hardening, validation, edge, P1 UI, demo | 44 | 18 |

## 3. Epics

| Epic | Title | Owner | Stories |
|---|---|---|---|
| EP-01 | Project setup & DevOps | R6 | ST-001…006 |
| EP-02 | Data acquisition, labelling & synthesis | R1 / R2 | ST-010…018 |
| EP-03 | Ingestion | R2 | ST-020…026 |
| EP-04 | Geotagging | R3 | ST-030…038 |
| EP-05 | Preprocessing | R2 | ST-040…048 |
| EP-06 | Detection & anomaly models | R1 | ST-050…057 |
| EP-07 | Scoring & calibration | R1 | ST-060…065 |
| EP-08 | Reporting, orchestration & CLI | R4 / R3 | ST-070…075 |
| EP-09 | Backend API & jobs | R4 | ST-080…087 |
| EP-10 | Frontend dashboard | R5 | ST-090…099 |
| EP-11 | Edge deployment | R6 | ST-100…105 |
| EP-12 | Testing, validation, docs & demo | R6 (all) | ST-110…116 |

---

## EP-01 · Project setup & DevOps

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-001 | Scaffold repository (`backend/`, `ml/`, `frontend/`, `edge/`, `docker/`), `sonarsentinel` package skeleton, `pyproject.toml` | P0 | 3 | S0 | R6 | NFR-15 | `pip install -e backend` works; `sonarsentinel --help` runs |
| ST-002 | CI: ruff, mypy, pytest, eslint, tsc, build on every PR | P0 | 3 | S0 | R6 | NFR-15 | PR shows checks; failing lint blocks merge |
| ST-003 | Reproducible environments (`environment.yml` with GDAL + PyTorch; Node LTS) verified on Windows and Ubuntu | P0 | 3 | S0 | R6 | NFR-10 | 2 team members on each OS complete [Developer Setup](../guides/DEVELOPER_SETUP.md) |
| ST-004 | `scripts/fetch_test_data.py` downloads small sample XTF + dataset subsets with checksums | P0 | 2 | S0 | R2 | — | Script runs idempotently; checksum mismatch fails |
| ST-005 | Docker images (backend CPU/GPU, frontend nginx) + compose | P1 | 5 | S6 | R6 | NFR-10 | `docker compose up` → dashboard at :8080 with health OK |
| ST-006 | pre-commit hooks, PR/issue templates, branch protection | P0 | 1 | S0 | R6 | — | Hooks run locally; `main` protected |

## EP-02 · Data acquisition, labelling & synthesis

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-010 | Download AI4Shipwrecks; convert masks to YOLO-seg polygons | P0 | 3 | S1 | R1 | PRD §8 | Converted labels overlay correctly on 20 random images |
| ST-011 | Download mine-detection SSS dataset; convert MILCO → `cylinder`, review NOMBO | P0 | 3 | S1 | R1 | PRD §8 | Class mapping table filled; conversion verified visually |
| ST-012 | Download SeabedObjects-KLSG; build normal seafloor pool | P0 | 2 | S1 | R1 | FR-DET-03 | ≥ 500 normal tiles across seabed types, spot-checked |
| ST-013 | Acquire ≥ 3 NOAA/USGS XTF surveys incl. ≥ 1 covering a charted wreck | P0 | 3 | S1 | R3 | AC-01 | Files on shared drive with provenance record; wreck position noted |
| ST-014 | Set up CVAT/Label Studio with SAM 2 assist (not SAM 3, per licence review); label charted wreck + pipes/objects in NOAA tiles | P0 | 5 | S2 | R2 | — | ≥ 100 labelled real tiles following [guidelines](../data/ANNOTATION_GUIDELINES.md); 10% double-labelled |
| ST-015 | Site-grouped train/val/calibration/test splits; dataset manifest + stats report | P0 | 3 | S2 | R1 | PRD §8 | No site in more than one split (automated check) |
| ST-016 | Synthetic ghost-net generator v1 (mesh, crumple, envelope, burial, speckle, shadow, blend, mask) | P0 | 8 | S2 | R2 | FR-OPS-02 | Generates 2,000 tiles + masks; parameters logged per tile |
| ST-017 | Synthetic pipe and cylinder generators | P1 | 5 | S3 | R2 | FR-OPS-02 | 1,000 tiles each; visual review passes |
| ST-018 | Synthetic realism review (analyst rates 100 tiles; tune generator) | P1 | 2 | S3 | R2 | — | ≥ 70% rated "plausible"; tuning notes recorded |

## EP-03 · Ingestion

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-020 | `SonarLog` data contract, validators, error types | P0 | 3 | S1 | R2 | FR-ING-05, FR-ING-08 | Typed dataclasses; invalid inputs raise coded errors (TC-ING-001…004) |
| ST-021 | XTF reader: channels, per-ping nav, `NavUnits`, sonar info | P0 | 5 | S1 | R2 | FR-ING-01, FR-ING-06 | 3 NOAA/USGS files parse; nav matches vendor viewer on 10 pings |
| ST-022 | GeoTIFF reader with CRS/transform | P0 | 2 | S1 | R3 | FR-ING-02 | Pixel → lat/lon matches QGIS within 1 pixel |
| ST-023 | Image + nav CSV reader (layout options, interpolation) | P0 | 3 | S1 | R2 | FR-ING-03 | Template CSV works; row mismatch sets `GPS_INTERPOLATED` |
| ST-024 | Image-only path with `NOT_GEOTAGGED` | P0 | 1 | S1 | R2 | FR-ING-04 | Report has null lat/lon and pixel boxes |
| ST-025 | EdgeTech `.jsf` and Lowrance `.sl2/.sl3` readers | P1 | 5 | S6 ⭐ | R2 | FR-ING-09 | One sample file per format → `SonarLog` |
| ST-026 | Memory-mapped chunked reading of large XTF | P0 | 3 | S1 | R4 | NFR-07 | 2 GB file processed with peak RAM ≤ 8 GB |

## EP-04 · Geotagging

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-030 | Units/CRS detection; UTM ↔ WGS84 conversion; user EPSG override | P0 | 2 | S1 | R3 | FR-ING-07 | Degrees and UTM versions of one track give identical output (< 0.1 m) |
| ST-031 | `pixel_to_latlon` for processed chunks, raw slant images and GeoTIFF + golden tests | P0 | 3 | S1 | R3 | FR-GEO-01 | Golden tests < 0.05 m |
| ST-032 | Navigation cleaning: invalid fixes, Savitzky–Golay smoothing, circular heading, COG fallback | P0 | 3 | S2 | R3 | FR-GEO-04 | Heading wrap-around test (359°→1°) passes |
| ST-033 | Measurements: centroid, footprint, length/width/area, orientation, depth | P0 | 3 | S3 | R3 | FR-GEO-02, 03, 08 | Synthetic rectangle of known size measured within 1 pixel |
| ST-034 | Layback correction from cable-out and fish depth | P1 | 3 | S4 | R3 | FR-GEO-05 | Unit tests; `LAYBACK_ESTIMATED` flag set |
| ST-035 | Position uncertainty budget | P1 | 2 | S5 | R3 | FR-GEO-06 | `uncertainty_m` populated from config defaults |
| ST-036 | GCP-based georeferenced mosaic + bounds | P1 | 5 | S5 | R3 | FR-GEO-07 | Mosaic aligns with track in Leaflet and QGIS |
| ST-037 | Charted-wreck geolocation validation report | P0 | 3 | S6 | R3 | PRD §11 | Error (m) measured and documented in test report |
| ST-038 | Cross-line DBSCAN clustering + persistence score | P1 | 3 | S4 | R3 | FR-DET-05 | Same object on 2 lines merged; `n_views = 2` |

## EP-05 · Preprocessing

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-040 | Bottom tracking + water-column mask | P0 | 3 | S2 | R2 | FR-PRE-01 | Tracked altitude within 10% of recorded altitude on sample files |
| ST-041 | Gain normalisation: across-track, along-track, per side, log + clip | P0 | 3 | S2 | R2 | FR-PRE-03 | Column-mean profile flat within ±10% after correction |
| ST-042 | Slant-range correction + along-track GPS resampling (fixed 0.10 m) + `row_to_ping` | P0 | 5 | S2 | R2 | FR-PRE-02, 07 | Known-size synthetic object has correct size after resampling |
| ST-043 | Dropout detection, short-gap inpainting, long-gap masks | P0 | 3 | S2 | R2 | FR-PRE-05 | Injected dropouts detected ≥ 95% |
| ST-044 | Motion flags (roll, pitch, yaw rate) | P0 | 2 | S2 | R2 | FR-PRE-06 | Flags match thresholds on synthetic nav |
| ST-045 | 3-channel input (raw, Lee, local std) | P0 | 2 | S2 | R2 | FR-PRE-04 | Same function used by training and inference (import check) |
| ST-046 | Tiling + chunking with overlap and offsets | P0 | 3 | S2 | R4 | FR-PRE-08 | Tile ↔ chunk coordinate round trip exact |
| ST-047 | Surface-return band mask | P1 | 2 | S5 | R2 | FR-PRE-09 | Band identified on sample shallow-water file |
| ST-048 | Preprocessing QA notebook (before/after visuals per stage) | P0 | 2 | S2 | R2 | — | Reviewed at M2 demo |

## EP-06 · Detection & anomaly models

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-050 | Baseline YOLO11s-seg on real data only | P0 | 5 | S3 | R1 | FR-DET-01 | Metrics logged; baseline model card draft |
| ST-051 | Train with synthetic data + sonar augmentations; ablation vs. baseline | P0 | 5 | S3 | R1 | FR-DET-01 | Ablation table in experiment log |
| ST-052 | SAHI sliced inference integration | P0 | 3 | S3 | R1 | FR-DET-02 | Small-object recall ≥ non-sliced on val |
| ST-053 | PatchCore training; `unknown_anomaly` region extraction | P0 | 5 | S3 | R1 | FR-DET-03 | AUROC reported; anomalies emitted with heatmap |
| ST-054 | Merge/dedupe across tiles and chunks | P0 | 3 | S3 | R4 | FR-DET-04 | No duplicates on overlap test fixture |
| ST-055 | Small-object variant (imgsz 1024 / P2 head) if ghost-net recall is low | P1 | 5 | S4 | R1 | R1 risk | Decision recorded with metrics |
| ST-056 | U-Net mask refiner for `ghost_net`/`pipe` | P1 | 5 | S5 ⭐ | R1 | FR-DET-06 | Mask IoU improves on holdout |
| ST-057 | `ml/evaluate.py`: metrics.json, PR curves, confusion matrix | P0 | 3 | S3 | R1 | PRD §11 | Runs on any registry model; outputs saved to registry |

## EP-07 · Scoring & calibration

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-060 | Shadow consistency score + height estimate | P0 | 5 | S4 | R1 | FR-CONF-01, 07 | ≥ 50% of shadow-only false positives demoted (AC-08) |
| ST-061 | Shape/texture feature extraction | P1 | 3 | S4 | R1 | FR-CONF-02 | Features computed < 5 ms per detection |
| ST-062 | LightGBM false-positive filter | P1 | 3 | S4 | R1 | FR-CONF-02 | AUROC TP vs FP reported; SHAP summary in model card |
| ST-063 | Fusion + weight tuning | P0 | 3 | S4 | R1 | FR-CONF-03 | AP of fused ≥ AP of detector score alone |
| ST-064 | Isotonic calibration, reliability diagram, ECE | P0 | 3 | S4 | R1 | FR-CONF-04 | ECE ≤ 0.10 on calibration split |
| ST-065 | Alert tiers, quality penalties, quality flags on detections | P0 | 2 | S4 | R1 | FR-CONF-05, 06, 08 | TC-CONF tests pass |

## EP-08 · Reporting, orchestration & CLI

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-070 | JSON Schema `report-1.0` + JSON export | P0 | 3 | S4 | R4 | FR-REP-01, 03 | Exports validate against schema in CI |
| ST-071 | CSV export | P0 | 1 | S4 | R4 | FR-REP-02 | Opens correctly in Excel/LibreOffice |
| ST-072 | GeoJSON + KML export | P1 | 3 | S5 | R3 | FR-REP-04 | Loads in QGIS / Google Earth at correct positions |
| ST-073 | Detection chips with overlays (mask/shadow/anomaly) | P0 | 2 | S4 | R4 | FR-UI-06 | Chip per detection; overlay variants |
| ST-074 | CLI `detect`, `validate`, `serve` | P0 | 3 | S3 | R4 | FR-OPS-01 | Commands per API spec §5 work on sample data |
| ST-075 | `pipeline.py` orchestrator (per-chunk stages, events, config hash) | P0 | 5 | S3 | R4 | NFR-16 | Same input + config ⇒ identical report |

## EP-09 · Backend API & jobs

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-080 | FastAPI app skeleton, `/health`, `/models`, OpenAPI | P0 | 2 | S3 | R4 | — | `/docs` lists endpoints |
| ST-081 | `POST /surveys/validate` and `POST /surveys` (multipart, options) | P0 | 3 | S4 | R4 | FR-ING-05 | TC-API upload tests pass |
| ST-082 | Job manager, worker, cancel, job status | P0 | 5 | S4 | R4 | FR-UI-02 | Cancel stops within one chunk |
| ST-083 | WebSocket events with `seq` and replay | P0 | 5 | S5 | R4 | FR-UI-02, NFR-04/05 | Reconnect replays without duplicates |
| ST-084 | Surveys, detections (filters), track, report endpoints | P0 | 3 | S5 | R4 | FR-UI-04, 07 | Filter params per API spec |
| ST-085 | SQLite storage layer (SQLAlchemy models) | P0 | 3 | S4 | R4 | — | Migrations run; ER model implemented |
| ST-086 | Review `PATCH` + label store | P1 | 3 | S5 | R4 | FR-UI-10, FR-OPS-04 | Label record written per decision |
| ST-087 | Mock API server from OpenAPI for frontend development | P0 | 2 | S3 | R4 | — | Frontend runs against mock with sample events |

## EP-10 · Frontend dashboard

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-090 | App shell, routing, design tokens, API client generation | P0 | 3 | S3 | R5 | NFR-14 | Navigation per wireframes; class colour tokens |
| ST-091 | Upload screen (S-01) | P0 | 5 | S4 | R5 | FR-UI-01 | Wireframe S-01 states implemented |
| ST-092 | Live map: streaming markers, track, quality segments (S-02) | P0 | 8 | S5 | R5 | FR-UI-02, 03, 08 | AC-01 passes; 2,000 markers smooth |
| ST-093 | Filters + detection list | P0 | 5 | S5 | R5 | FR-UI-04, 05 | Filter update < 100 ms for 2,000 items |
| ST-094 | Detection detail drawer (S-03) | P0 | 5 | S5 | R5 | FR-UI-06 | Values match exports exactly |
| ST-095 | Reports & export screen (S-06) + quick downloads | P0 | 3 | S5 | R5 | FR-UI-07 | AC-07 downloads work |
| ST-096 | Review queue (S-05) with keyboard shortcuts | P1 | 5 | S6 | R5 | FR-UI-10 | 20 items reviewed in ≤ 3 min |
| ST-097 | Waterfall viewer (S-04) | P1 | 8 | S6 ⭐ | R5 | FR-UI-09 | Smooth scroll on 20k pings |
| ST-098 | Survey history + settings (S-07) | P1 | 5 | S6 | R5 | FR-UI-11, 12 | CRUD per wireframe |
| ST-099 | Offline basemap support | P1 | 3 | S6 | R5 | FR-UI-14 | AC-10 passes |

## EP-11 · Edge deployment

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-100 | ONNX export + ONNX Runtime CPU inference path | P1 | 3 | S5 | R6 | FR-OPS-03 | CPU run meets NFR-02 |
| ST-101 | TensorRT FP16/INT8 on Jetson + benchmark | P1 | 5 | S6 | R6 | NFR-03, AC-09 | Benchmark table; INT8 drop ≤ 3 mAP points |
| ST-102 | OpenVINO INT8 export | P2 | 3 | BL | R6 | FR-OPS-03 | — |
| ST-103 | Edge `watch` mode for acquisition folder | P1 | 5 | S6 ⭐ | R6 | — | New file processed automatically |
| ST-104 | Edge console (S-08) | P2 | 5 | BL | R5 | FR-UI-15 | — |
| ST-105 | Compact alert messages | P2 | 2 | BL | R6 | FR-OPS-06 | — |

## EP-12 · Testing, validation, docs & demo

| ID | Story | Pri | Pts | Sprint | Owner | Refs | Acceptance criteria |
|---|---|---|---|---|---|---|---|
| ST-110 | Integration test: sample XTF → schema-valid report in CI | P0 | 3 | S3 | R6 | G2 | Runs in < 5 min in CI |
| ST-111 | Robustness suite (injected dropouts, noise, truncation) | P0 | 3 | S6 | R6 | AC-06 | All robustness test cases pass |
| ST-112 | Performance benchmarks (NFR-01…03, 07) | P0 | 3 | S6 | R6 | NFR-01…07 | Results table in test report |
| ST-113 | Usability test with ≥ 3 new users | P1 | 2 | S6 | R5 | NFR-13 | Findings + fixes logged |
| ST-114 | Verify User Manual and Runbook against the implementation | P0 | 2 | S6 | R6 | — | All commands/screens checked |
| ST-115 | SIH deck + demo script; 3 rehearsals | P0 | 3 | S6 | R6 | — | Timed under limit; backup video recorded |
| ST-116 | Final project report | P0 | 5 | S6 | R6 | — | Template sections complete with measured results |

---

## 4. Backlog grooming rules

1. Refine the next sprint's stories at Friday review: clear acceptance criteria, estimate, owner.
2. A story larger than 8 points is split before it enters a sprint.
3. New bugs are triaged daily: P0 bugs enter the current sprint; others go to the backlog.
4. When behind: drop ⭐ stretch items first, then P1 items, never P0 without a PRD scope change.
