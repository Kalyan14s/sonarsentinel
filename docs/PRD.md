# SonarSentinel — Product Requirements Document (PRD)

| | |
|---|---|
| **Product** | SonarSentinel (working title) |
| **Problem Statement** | SIH 26057 — AI-Powered Automated Underwater Marine Debris and Anomaly Detection System using Side-Scan Sonar Imagery |
| **Organization** | MoES — National Institute of Ocean Technology (NIOT) |
| **Version / Status** | v1.0 · ✅ Baseline approved by team lead 2026-09-13 (R1–R5 confirm in Sprint 0) |
| **Date** | 2026-09-13 |
| **Owner** | Product / Integration lead |

**Related:** [Documentation index](README.md) · [Project Idea](PROJECT_IDEA.md) · [Architecture](architecture/README.md) · [Wireframes](wireframes/README.md) · [Project Plan](planning/PROJECT_PLAN.md) · [TODO](../TODO.md)

**Priority legend:** **P0** = must have for MVP · **P1** = should have · **P2** = could have / future

---

## Table of contents

1. [Overview](#1-overview)
2. [Goals and non-goals](#2-goals-and-non-goals)
3. [Users and personas](#3-users-and-personas)
4. [User stories](#4-user-stories)
5. [Scope](#5-scope)
6. [Functional requirements](#6-functional-requirements)
7. [Non-functional requirements](#7-non-functional-requirements)
8. [Data requirements](#8-data-requirements)
9. [Output and report specification](#9-output-and-report-specification)
10. [UX requirements](#10-ux-requirements)
11. [Success metrics](#11-success-metrics)
12. [Acceptance criteria](#12-acceptance-criteria)
13. [Assumptions, constraints, dependencies](#13-assumptions-constraints-dependencies)
14. [Risks and mitigations](#14-risks-and-mitigations)
15. [Milestones](#15-milestones)
16. [Open questions](#16-open-questions)
17. [Traceability to the problem statement](#17-traceability-to-the-problem-statement)
18. [Glossary](#18-glossary)

---

## 1. Overview

### 1.1 Problem
Side-scan sonar (SSS) surveys produce huge volumes of acoustic imagery. Today analysts inspect them manually to find man-made debris, which is slow, tedious and error-prone. Ghost nets and other debris blend into rocks, sand ripples and acoustic shadows. Speckle noise, varying resolution, dropouts and vehicle motion (heave, pitch, roll) make the imagery harder still to read.

### 1.2 Product summary
SonarSentinel is an end-to-end, edge-deployable computer vision system that:
1. **Ingests** raw SSS logs (`.xtf`, GeoTIFF mosaics, images with navigation CSV).
2. **Preprocesses** them to handle sonar-specific problems.
3. **Detects and segments** man-made objects: shipwrecks, pipes, cylinders, ghost nets, other debris and unknown anomalies.
4. **Scores** every detection with a calibrated **0–100% confidence** after physics-aware false-positive filtering.
5. **Geotags** every detection (latitude/longitude, footprint, dimensions) from sonar navigation metadata.
6. **Reports** results in JSON/CSV (plus GeoJSON/KML) and shows them live on a **map dashboard**.

### 1.3 Detection classes

| Class ID | Label | Description |
|---|---|---|
| `ghost_net` | Ghost net | Abandoned/lost fishing nets, entangled ropes and lines, often with floats or trapped debris |
| `shipwreck` | Shipwreck | Wrecked vessels or large wreck fragments |
| `pipe` | Pipe | Pipelines, cables, pipe sections; long linear objects |
| `cylinder` | Cylinder | Drums, barrels, mine-like cylindrical objects |
| `debris_other` | Other debris | Other man-made objects: tyres, containers, aircraft parts, construction debris |
| `unknown_anomaly` | Unknown anomaly | Region that doesn't match normal seafloor but matches no known class (from the anomaly model) |

---

## 2. Goals and non-goals

### 2.1 Goals
| ID | Goal |
|---|---|
| G1 | Automatically detect and localise man-made debris in SSS imagery with high recall |
| G2 | Detect ghost nets, including when no real ghost-net examples exist in the training data |
| G3 | Reduce false positives from rocks, shadows, ripples and noise, and give a trustworthy confidence per detection |
| G4 | Output the exact GPS location, dimensions and class of each hazard in structured formats |
| G5 | Let users upload a log and watch detections appear on a map in near real time |
| G6 | Run efficiently on edge hardware without cloud dependency |

### 2.2 Non-goals (this release)
- Real-time control of AUV navigation (future: adaptive missions)
- Processing multibeam bathymetry or forward-looking sonar (future fusion)
- Producing IHO-certified nautical chart products
- Physical recovery planning and logistics beyond exporting locations
- Multi-tenant cloud SaaS

---

## 3. Users and personas

| Persona | Context | Needs | Pain points today |
|---|---|---|---|
| **Survey Operator** (on vessel/AUV team) | Runs sonar surveys; limited time and connectivity at sea | Quick check that data is usable; early warning of targets while still on site | Can't review hours of data during a survey; returns later to re-survey |
| **Marine Analyst** (NIOT scientist) | Post-processes surveys on a workstation | Accurate detections, confidence, ability to verify, standard exports | Manual scrolling; inconsistent contact picking; copying coordinates by hand |
| **Recovery Team Lead** (divers/ROV/NGO) | Plans dives and recovery | Reliable coordinates, size, type, depth; files for GPS/Google Earth | Vague locations; wasted dive time |
| **Port / Disaster Authority Officer** | Post-cyclone navigation safety | Prioritised hazard list for channels; quick summary | Slow turnaround from survey to decision |
| **ML Engineer** (internal) | Maintains models | Labelled feedback, metrics, versioned models | No labelled ghost-net data; domain shift between sonars |

---

## 4. User stories

| ID | As a... | I want to... | So that... | Priority |
|---|---|---|---|---|
| US-01 | Marine Analyst | upload an `.xtf` sonar log and have all debris detected automatically | I don't have to scroll through the whole survey manually | P0 |
| US-02 | Marine Analyst | see detections appear on a map while the file is being processed | I can start assessing results immediately | P0 |
| US-03 | Recovery Team Lead | get the latitude/longitude, size, depth and class of each hazard | I can plan dives directly to the object | P0 |
| US-04 | Marine Analyst | see a confidence percentage and why the system believes it | I can decide what to trust and what to verify | P0 |
| US-05 | Marine Analyst | be told about possible ghost nets even though the model has seen few real ones | ghost nets aren't missed | P0 |
| US-06 | Marine Analyst | download reports as JSON and CSV (and GeoJSON/KML) | I can use them in GIS tools and share them | P0 |
| US-07 | Marine Analyst | upload an image without GPS plus a navigation CSV | older or exported images can still be geotagged | P0 |
| US-08 | Marine Analyst | filter detections by class, confidence and alert tier | I can focus on the most important hazards | P0 |
| US-09 | Marine Analyst | view the sonar image chip with the mask overlay for each detection | I can visually verify it | P0 |
| US-10 | Marine Analyst | confirm, reject or reclassify detections | the report is accurate and the model improves | P1 |
| US-11 | Survey Operator | run detection on board without internet | I get alerts while still on site | P1 |
| US-12 | Port Authority Officer | see a summary of hazards ranked by confidence and size | I can prioritise clearance | P1 |
| US-13 | Marine Analyst | see the georeferenced sonar mosaic under the detections | I can understand the context on the map | P1 |
| US-14 | Marine Analyst | browse earlier surveys and their reports | I can compare and re-download | P1 |
| US-15 | ML Engineer | export reviewed detections as a labelled dataset | I can retrain models | P2 |
| US-16 | Marine Analyst | be warned where data quality is poor (dropouts, heavy motion) | I know where detections are less reliable or a re-survey is needed | P0 |

---

## 5. Scope

### 5.1 MVP (P0)
- Ingestion: `.xtf`, GeoTIFF, PNG/JPG/TIFF + navigation CSV, image-only (no geotag)
- Preprocessing: bottom tracking, slant-range correction, gain normalisation, despeckle + 3-channel input, dropout masks, motion flags, fixed-resolution resampling, tiling
- Detection: YOLO11-seg (5 classes) with sliced inference; PatchCore anomaly model → `unknown_anomaly`
- Scoring: shadow consistency, fused score, isotonic calibration, alert tiers, score breakdown
- Geotagging: pixel → WGS84, footprint polygon, length/width/area, GPS/heading smoothing
- Reports: JSON, CSV
- Dashboard: upload, live map with streaming detections and track, filters, detection detail, downloads
- CLI for headless batch processing
- Synthetic ghost-net generator (training tool)

### 5.2 Release 2 (P1)
- GeoJSON, KML exports; georeferenced mosaic overlay; waterfall viewer
- Shape/texture LightGBM false-positive filter; shadow-based height estimate
- Layback correction; geolocation uncertainty estimate; cross-line duplicate merging
- Review queue; survey history; settings
- `.jsf`, `.sl2/.sl3` ingestion; batch upload
- ONNX/TensorRT/OpenVINO export; offline basemaps

### 5.3 Future (P2)
- Edge console UI and compact satellite/acoustic alerts
- PDF summary report; user authentication and roles
- Labelled dataset export and active-learning retraining pipeline
- Humminbird ingestion (PINGMapper); change detection between repeat surveys

---

## 6. Functional requirements

### 6.1 Ingestion (FR-ING)

| ID | Requirement | Priority |
|---|---|---|
| FR-ING-01 | The system shall accept `.xtf` files up to 2 GB (configurable) through the dashboard and CLI. | P0 |
| FR-ING-02 | The system shall accept GeoTIFF sonar mosaics and use their embedded georeferencing. | P0 |
| FR-ING-03 | The system shall accept PNG/JPG/TIFF waterfall images with a navigation CSV ([format](architecture/06-data-models.md#5-navigation-csv-input-format)). | P0 |
| FR-ING-04 | The system shall process images without navigation data, output pixel coordinates, and mark results `NOT_GEOTAGGED`. | P0 |
| FR-ING-05 | The system shall validate uploads (extension, magic bytes/header, size, readable channels) and return human-readable errors. | P0 |
| FR-ING-06 | The system shall extract per-ping navigation: time, lat/lon, heading, altitude, sensor depth, speed, roll, pitch, slant range, cable out / layback where available. | P0 |
| FR-ING-07 | The system shall detect coordinate units (geographic vs. projected) from file headers and value ranges, and allow a manual UTM zone override. | P0 |
| FR-ING-08 | The system shall convert all supported inputs into a common internal `SonarLog` structure. | P0 |
| FR-ING-09 | The system shall accept EdgeTech `.jsf` and Lowrance `.sl2/.sl3` files. | P1 |
| FR-ING-10 | The system shall accept multiple files (survey lines) in one batch and process them as one survey. | P1 |
| FR-ING-11 | The system shall accept Humminbird recordings (via PINGMapper). | P2 |

### 6.2 Preprocessing (FR-PRE)

| ID | Requirement | Priority |
|---|---|---|
| FR-PRE-01 | Detect the seabed first return per ping (bottom tracking) when altitude is missing or unreliable, and mask the water column. | P0 |
| FR-PRE-02 | Apply slant-range to ground-range correction per ping. | P0 |
| FR-PRE-03 | Normalise brightness across-track (beam pattern/range loss), along-track, and per side (roll imbalance). | P0 |
| FR-PRE-04 | Produce a 3-channel model input: normalised raw, despeckled (Lee filter), local standard deviation. | P0 |
| FR-PRE-05 | Detect dropout pings (zero/flat/duplicated rows, invalid navigation), inpaint gaps ≤ 3 pings, and mask longer gaps. | P0 |
| FR-PRE-06 | Flag high-motion pings using roll, pitch and yaw-rate thresholds (configurable). | P0 |
| FR-PRE-07 | Resample imagery to a fixed ground resolution (default 0.10 m/px) across-track and along-track (GPS distance). | P0 |
| FR-PRE-08 | Split imagery into overlapping tiles (default 640 px, 25% overlap) and process long files in overlapping chunks (default 2,000 pings, 200 overlap). | P0 |
| FR-PRE-09 | Mask the surface-return band. | P1 |

### 6.3 Detection (FR-DET)

| ID | Requirement | Priority |
|---|---|---|
| FR-DET-01 | Detect and segment `shipwreck`, `pipe`, `cylinder`, `ghost_net`, `debris_other` with bounding boxes and pixel masks. | P0 |
| FR-DET-02 | Use sliced (tiled) inference so small objects (≥ 0.5 m) are not lost to downscaling. | P0 |
| FR-DET-03 | Run an anomaly model trained on normal seafloor; anomalous regions without a known-class detection become `unknown_anomaly`. | P0 |
| FR-DET-04 | Merge duplicate detections across tiles and chunks. | P0 |
| FR-DET-05 | Merge detections of the same object across overlapping survey lines (GPS clustering, default 5 m radius) and record `n_views`. | P1 |
| FR-DET-06 | Refine masks for thin structures (`ghost_net`, `pipe`) with a segmentation refinement model. | P1 |
| FR-DET-07 | Record the model version used for every detection. | P0 |

### 6.4 Confidence scoring & noise filtering (FR-CONF)

| ID | Requirement | Priority |
|---|---|---|
| FR-CONF-01 | Compute a shadow-consistency score (highlight followed by a far-range shadow) per detection. | P0 |
| FR-CONF-02 | Compute shape/texture features (straight lines, solidity, mesh periodicity, GLCM) and a learned false-positive probability. | P1 |
| FR-CONF-03 | Fuse detector, anomaly, shadow, false-positive filter and persistence scores, minus data-quality penalties, into one score. | P0 |
| FR-CONF-04 | Calibrate the fused score into a **confidence from 0 to 100%** for every detection. | P0 |
| FR-CONF-05 | Assign an alert tier: `hazard` (≥ 80), `review` (50–79.9), `anomaly` (30–49.9 with anomaly score above threshold), `hidden` (below). Thresholds configurable. | P0 |
| FR-CONF-06 | Expose the score breakdown and quality flags for every detection. | P0 |
| FR-CONF-07 | Estimate object height above the seabed from shadow length. | P1 |
| FR-CONF-08 | Lower confidence for detections overlapping dropouts or high-motion segments and flag them. | P0 |

### 6.5 Geotagging (FR-GEO)

| ID | Requirement | Priority |
|---|---|---|
| FR-GEO-01 | Convert each detection's centroid from pixel to WGS84 latitude/longitude (decimal degrees, 6 decimals). | P0 |
| FR-GEO-02 | Output a footprint polygon (4 corners of the minimum-area rectangle) in WGS84. | P0 |
| FR-GEO-03 | Compute length, width (m), area (m²) and orientation (° from true north). | P0 |
| FR-GEO-04 | Smooth GPS positions and heading (circular) before geotagging. | P0 |
| FR-GEO-05 | Apply towfish layback correction when the file contains only vessel position and cable-out data. | P1 |
| FR-GEO-06 | Estimate a horizontal position uncertainty (m) per detection. | P1 |
| FR-GEO-07 | Generate a georeferenced mosaic (GeoTIFF/PNG + bounds) for map display. | P1 |
| FR-GEO-08 | Report depth at the detection (sensor depth + altitude) when available. | P0 |

### 6.6 Reporting (FR-REP)

| ID | Requirement | Priority |
|---|---|---|
| FR-REP-01 | Generate a JSON report matching the [report schema](architecture/06-data-models.md). | P0 |
| FR-REP-02 | Generate a CSV report with one row per detection. | P0 |
| FR-REP-03 | Include survey metadata, processing metadata (model versions, config hash, duration), a summary (counts by class/tier) and all detections. | P0 |
| FR-REP-04 | Generate GeoJSON (FeatureCollection with point + footprint) and KML. | P1 |
| FR-REP-05 | Export either all detections or only those matching the current filters. | P1 |
| FR-REP-06 | Generate a printable PDF summary with map snapshot and hazard table. | P2 |

### 6.7 Dashboard (FR-UI)

| ID | Requirement | Priority |
|---|---|---|
| FR-UI-01 | Upload screen with drag-and-drop, per-file validation status, nav CSV attachment and advanced options. | P0 |
| FR-UI-02 | Live processing view with progress (stage, %, ETA), streaming track line and detection markers. | P0 |
| FR-UI-03 | Map with basemap layers, class-coloured and shape-coded markers, marker clustering, footprint polygons at high zoom. | P0 |
| FR-UI-04 | Filters: class, confidence range slider, alert tier, quality flags. | P0 |
| FR-UI-05 | Detection list sortable by confidence, size, class, position along track. | P0 |
| FR-UI-06 | Detection detail: sonar chip with mask/shadow overlay, class, confidence, score breakdown, coordinates (DD and DMS, copy button), dimensions, depth, flags. | P0 |
| FR-UI-07 | Report download buttons (JSON, CSV; GeoJSON, KML when available). | P0 |
| FR-UI-08 | Data quality warnings on the map (dropout and high-motion segments highlighted on the track). | P0 |
| FR-UI-09 | Waterfall viewer synchronised with the map (click detection → scroll to ping). | P1 |
| FR-UI-10 | Review queue: confirm, reject, reclassify with note; keyboard shortcuts. | P1 |
| FR-UI-11 | Survey history with search and re-download. | P1 |
| FR-UI-12 | Settings: thresholds, resolution, UTM zone, model selection, basemap source. | P1 |
| FR-UI-13 | Mosaic overlay toggle and opacity control. | P1 |
| FR-UI-14 | Full operation with offline basemap tiles. | P1 |
| FR-UI-15 | Edge console: minimal live status and alert view for on-board use. | P2 |

### 6.8 CLI, edge and learning (FR-OPS)

| ID | Requirement | Priority |
|---|---|---|
| FR-OPS-01 | CLI: `sonarsentinel detect <file> [--nav nav.csv] --out <dir> --formats json,csv`. | P0 |
| FR-OPS-02 | Synthetic ghost-net generator tool producing tiles and masks for training. | P0 |
| FR-OPS-03 | Export models to ONNX, TensorRT (FP16/INT8) and OpenVINO (INT8). | P1 |
| FR-OPS-04 | Save reviewed detections (confirm/reject/reclassify) as labelled training samples. | P1 |
| FR-OPS-05 | Export labelled samples in YOLO-seg format. | P2 |
| FR-OPS-06 | Emit compact alert messages (≤ 256 bytes) for low-bandwidth links. | P2 |

---

## 7. Non-functional requirements

| ID | Category | Requirement | Target |
|---|---|---|---|
| NFR-01 | Performance (workstation GPU) | End-to-end processing of a 1 km survey line (50 m range per side, 0.10 m resolution), excluding upload | ≤ 60 s on an RTX 3060-class GPU |
| NFR-02 | Performance (CPU only) | Same workload | ≤ 5 min on an 8-core laptop CPU |
| NFR-03 | Performance (edge) | On-board inference throughput | ≥ 1× acquisition rate on a Jetson Orin Nano-class device (target ≥ 5×) |
| NFR-04 | Latency | First detection event after processing starts (if one exists in the first chunk) | ≤ 15 s |
| NFR-05 | Streaming | Progress update interval while processing | ≤ 5 s |
| NFR-06 | Footprint | Detector model size (FP32) | ≤ 25 MB; INT8 ≤ 10 MB |
| NFR-07 | Memory | Peak RAM when processing a 2 GB `.xtf` file | ≤ 8 GB (chunked processing) |
| NFR-08 | Reliability | Corrupt/partial files | No crash; process valid portion; clear warnings |
| NFR-09 | Availability | Offline operation | All P0 features work without internet |
| NFR-10 | Portability | Deployment targets | Windows 10/11, Ubuntu 22.04+, Jetson (JetPack 6); Docker images |
| NFR-11 | Security | Data handling | On-premise by default; no external calls except optional basemap tiles; upload type/size validation; no execution of uploaded content |
| NFR-12 | Security (P2) | Access control | Login with roles (viewer, analyst, admin) |
| NFR-13 | Usability | Time for a first-time user to go from upload to downloaded report | ≤ 5 min without training |
| NFR-14 | Accessibility | Dashboard | WCAG 2.1 AA contrast; classes distinguished by colour **and** marker shape; keyboard navigation |
| NFR-15 | Maintainability | Code | Modular packages per pipeline stage; ≥ 70% unit-test coverage on `geo/`, `scoring/`, `ingest/` |
| NFR-16 | Reproducibility | Results | Report records pipeline version, model versions and config hash; same input + config ⇒ same output |
| NFR-17 | Observability | Logs/metrics | Structured JSON logs per job; per-stage timings stored with the job |
| NFR-18 | Interoperability | Outputs | GeoJSON valid per RFC 7946; KML opens in Google Earth; CSV UTF-8 with header |

---

## 8. Data requirements

### 8.1 Training and evaluation data

| Dataset | Use | Classes contributed |
|---|---|---|
| AI4Shipwrecks | Segmentation training/test | `shipwreck` |
| Side-scan sonar imaging data for mine detection (2024) | Detection training/test; hard negatives | `cylinder` (MILCO); NOMBO reviewed → `debris_other` or hard negatives |
| SeabedObjects-KLSG | Classification crops; seafloor background | `shipwreck`, `debris_other` (airplane); normal seafloor for anomaly model; **drowning-victim images excluded** |
| S3Simulator | Excluded unless the authors grant written permission (no licence published) | — |
| Synthetic generator (ours) | Training for rare classes | `ghost_net`, `pipe`, `debris_other` |
| NOAA NCEI / InPort / USGS `.xtf` | Inference, pseudo-labelling, geolocation validation | Charted wrecks (hand-labelled) |
| GhostNetZero / WWF / NIOT (on request) | Real-world validation | `ghost_net` |

**Data rules:**
- Split train/val/test **by survey site**, never randomly by tile.
- Synthetic samples ≤ 40% of positive training tiles; the test set is real data only (plus a separately reported synthetic ghost-net holdout).
- Keep dataset licences and citations recorded in `ml/datasets/LICENSES.md`.

### 8.2 Runtime inputs
- `.xtf` with sonar channels and navigation in ping headers (P0)
- GeoTIFF with CRS and geotransform (P0)
- Image + navigation CSV (P0), [template](architecture/06-data-models.md#5-navigation-csv-input-format)
- `.jsf`, `.sl2`, `.sl3` (P1)

---

## 9. Output and report specification

Full schemas: [architecture/06-data-models.md](architecture/06-data-models.md).

**Per detection (minimum fields):**

| Field | Type | Example |
|---|---|---|
| `detection_id` | string | `SRV-20260913-001-D0003` |
| `class` | enum | `ghost_net` |
| `confidence` | number 0–100 | `87.4` |
| `alert_tier` | enum | `hazard` |
| `position.lat`, `position.lon` | number (WGS84, 6 dp) | `13.084120`, `80.312750` |
| `position.depth_m` | number / null | `18.5` |
| `position.uncertainty_m` | number / null | `4.2` |
| `footprint` | array of [lat, lon] × 4 | — |
| `dimensions.length_m`, `width_m`, `area_m2`, `height_m` | number | `6.2`, `3.1`, `14.8`, `0.4` |
| `orientation_deg` | number | `12.0` |
| `sonar_ref` | object | side, ping range, ground range, time |
| `scores` | object | score breakdown |
| `quality_flags` | array | `["HIGH_MOTION"]` |
| `review.status` | enum | `pending` / `confirmed` / `rejected` / `reclassified` |

---

## 10. UX requirements

- Wireframes: [docs/wireframes](wireframes/README.md)
- Main flow: **Upload → Live Map → Detection Detail → (Review) → Download**
- The map is the main workspace; everything else is a panel or drawer over it
- Class colours plus marker shapes are consistent across map, lists, charts and exports (KML styles)
- Confidence is always shown as a percentage with a tier badge; the score breakdown is one click away
- Poor data quality is always visible (track segment styling plus flag badges), never hidden
- Coordinates can always be copied in decimal degrees and DMS

---

## 11. Success metrics

| Metric | Target (prototype) | How measured |
|---|---|---|
| Detection mAP@50 (real test set, all known classes) | ≥ 0.70 | Site-held-out test set |
| Recall on `shipwreck` + `cylinder` | ≥ 0.85 | Test set |
| Ghost-net recall (synthetic holdout on real seafloor) | ≥ 0.80 | Held-out synthetic set; real samples reported separately |
| False positives per km² after filtering | ≥ 50% reduction vs. detector alone | Same test surveys, before/after |
| Confidence calibration (ECE) | ≤ 0.10 | Reliability diagram on validation |
| Geolocation error vs. charted wrecks (towed SSS) | Median ≤ 10 m (report actual) | NOAA survey with charted wreck |
| Processing speed | NFR-01 to NFR-03 | Benchmark script |
| Analyst time saved | ≥ 70% vs. manual review of the same line | Timed user test |
| Usability | First report downloaded in ≤ 5 min | Timed user test with 3+ new users |

---

## 12. Acceptance criteria

**AC-01 · Geotagged XTF processing (FR-ING-01, FR-GEO-01, FR-UI-02)**
- *Given* a valid `.xtf` file with navigation in ping headers
- *When* the user uploads it and starts analysis
- *Then* the track line appears on the map, detections stream in as markers, and every detection has WGS84 lat/lon with 6 decimals
- *And* the CSV and JSON exports contain identical coordinates for each `detection_id`.

**AC-02 · Image without GPS (FR-ING-04)**
- *Given* a PNG with no navigation CSV
- *When* the user chooses "Continue without GPS"
- *Then* detections are shown on a pixel-coordinate image view, `position.lat/lon` are `null`, and every detection has the `NOT_GEOTAGGED` flag.

**AC-03 · Image with navigation CSV (FR-ING-03)**
- *Given* a waterfall PNG and a CSV following the template
- *When* processed
- *Then* detections are geotagged, and a row count mismatch between image and CSV is interpolated with the `GPS_INTERPOLATED` flag.

**AC-04 · Confidence and tiers (FR-CONF-04, FR-CONF-05, FR-UI-04)**
- Every detection has `confidence` in [0, 100] and an `alert_tier` consistent with the configured thresholds.
- Moving the confidence slider immediately hides or shows markers and list rows accordingly.

**AC-05 · Ghost nets and anomalies (FR-DET-01, FR-DET-03)**
- On the synthetic ghost-net holdout set, `ghost_net` recall ≥ 80%.
- An anomalous region with no known-class detection is reported as `unknown_anomaly` with an anomaly heatmap in the detail view.

**AC-06 · Robustness (FR-PRE-05, FR-PRE-06, FR-CONF-08, NFR-08)**
- *Given* a file with 10% of pings zeroed and a truncated final record
- *Then* processing completes, warnings list the affected ping ranges, and detections overlapping masked regions carry `DROPOUT` and reduced confidence.

**AC-07 · Reports (FR-REP-01, FR-REP-02, FR-REP-04)**
- JSON validates against the published JSON Schema.
- CSV opens in Excel/LibreOffice with correct columns.
- GeoJSON loads in QGIS and KML loads in Google Earth at the correct locations.

**AC-08 · Shadow filtering (FR-CONF-01)**
- On a curated set of 50 shadow-only / rock false positives from the raw detector, at least 50% are demoted below the `review` tier.

**AC-09 · Edge export (FR-OPS-03, NFR-03)**
- The exported INT8 model gives mAP@50 within 3 points of FP32 and meets NFR-03 on the target device.

**AC-10 · Offline (NFR-09)**
- With network disabled and offline tiles configured, AC-01 still passes.

---

## 13. Assumptions, constraints, dependencies

**Assumptions**
- Survey data uses the WGS84 datum, or a CRS that can be identified.
- `.xtf` files contain per-ping navigation (sensor or ship position) and slant range.
- Seafloor is imaged at resolutions where target objects span at least ~5 pixels (≈ 0.5 m at 0.10 m/px).
- Ghost nets are detectable in high-frequency SSS (typically ≥ 600 kHz) through structure, attached ropes/floats and texture.

**Constraints**
- Few publicly available labelled SSS datasets; no public labelled ghost-net SSS dataset.
- Must run without cloud services; edge hardware limits compute and power.
- Hackathon/prototype timeline (~6 weeks of build).

**Dependencies**
- Open-source libraries: PyTorch, Ultralytics, SAHI, anomalib, OpenCV, GDAL, pyproj, pyxtf, FastAPI, React, Leaflet
- Public datasets (see §8) and their licences
- Optional: sample data and domain expertise from NIOT

---

## 14. Risks and mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Too little real ghost-net data; synthetic nets don't transfer to real data | High | High | Anomaly model as a safety net; varied synthetic generator; request real samples (NIOT, WWF/GhostNetZero); human review tier |
| R2 | Domain gap between public datasets and Indian survey sonars | High | Medium | Fixed-resolution resampling, normalisation, augmentation, fine-tune on a small NIOT sample |
| R3 | XTF variants break the parser | Medium | High | Test with multiple NOAA/USGS files; adapter layer; fallback parser; clear errors |
| R4 | Geolocation errors (layback, units, heading) | Medium | High | Units detection, layback correction, smoothing, charted-wreck validation, uncertainty field |
| R5 | High false-positive rate on rocky seabeds | Medium | Medium | Shadow physics, LightGBM filter, hard-negative mining, calibrated tiers |
| R6 | Edge performance insufficient | Low | Medium | Smaller model, INT8, heavier modules (anomaly, mosaic) moved to shore |
| R7 | Large files exhaust memory | Medium | Medium | Chunked processing, memory-mapped arrays |
| R8 | Dataset licence restrictions | Low | Medium | Track licences; use academic-use data only for research prototype; document |
| R9 | Scope creep within the timeline | High | Medium | Strict P0 list; weekly milestone demos |

---

## 15. Milestones

| Milestone | Week | Deliverables | Exit criteria |
|---|---|---|---|
| M1 · Ingest & Geo | 1 | XTF/GeoTIFF/image+CSV readers, `SonarLog`, pixel → GPS | NOAA XTF track plotted correctly; unit tests for georef |
| M2 · Preprocess & Data | 2 | Preprocessing pipeline, dataset conversion to YOLO-seg, site-based splits, synthetic ghost-net generator | Preprocessed tiles visually verified; dataset stats report |
| M3 · Models & thin slice | 3 | YOLO11-seg trained, PatchCore trained, SAHI inference, orchestrator + CLI | Baseline mAP and ghost-net holdout recall reported; CLI produces a schema-valid JSON/CSV report from an XTF |
| M4 · Scoring & Reports | 4 | Shadow check, fusion, calibration, tiers, JSON/CSV reports, chips, upload API + jobs | ECE ≤ 0.10; AC-04 pass; JSON/CSV parts of AC-07 pass |
| M5 · Dashboard (P0 freeze) | 5 | Upload, live map, filters, detail view, downloads, WebSocket streaming, GeoJSON/KML | AC-01…AC-05 and AC-07 pass end-to-end |
| M6 · Hardening & Demo | 6 | Robustness tests, ONNX/TensorRT export, charted-wreck validation, Docker, demo script | AC-06, AC-08, AC-09, AC-10; demo rehearsed |

---

## 16. Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Can NIOT provide sample `.xtf`/`.jsf` logs from Indian waters (with any known targets)? | PM | M2 |
| Q2 | Which sonar models and frequencies does NIOT use (affects resolution and ghost-net detectability)? | Sonar engineer | M2 |
| Q3 | Required report fields or formats beyond JSON/CSV (e.g. S-57/S-100 hazard objects)? | PM | M4 |
| Q4 | Target edge hardware (Jetson model, Intel NUC, AUV payload computer)? | Edge lead | M5 |
| Q5 | Is class taxonomy sufficient, or are more classes needed (e.g. anchors, containers, aircraft)? | ML lead | M2 |
| Q6 | Can we obtain real ghost-net SSS samples (GhostNetZero/WWF, MARELITT, NIOT)? | PM | M3 |
| Q7 | Required datum/CRS for official reports (WGS84 assumed)? | Geo engineer | M1 |

---

## 17. Traceability to the problem statement

| Problem statement requirement | Requirements |
|---|---|
| Ingest side-scan sonar imagery | FR-ING-01…11 |
| Handle speckle noise | FR-PRE-04 |
| Handle varying pixel resolutions | FR-PRE-02, FR-PRE-07 |
| Handle acoustic shadows | FR-CONF-01, FR-CONF-07 |
| Handle data dropouts from heave/pitch/roll | FR-PRE-05, FR-PRE-06, FR-CONF-08 |
| Separate natural seafloor from artificial anomalies | FR-DET-01, FR-DET-03, FR-CONF-02 |
| Detection/segmentation model (boxes or masks) for shipwrecks, pipes, cylinders, debris nets | FR-DET-01, FR-DET-02, FR-DET-06 |
| Confidence score 0–100% for every anomaly; minimise false positives | FR-CONF-01…08 |
| Read sonar metadata (coordinate files, ping headers) | FR-ING-03, FR-ING-06, FR-ING-07 |
| Structured JSON/CSV report with lat/lon, bounding dimensions, classification | FR-GEO-01…08, FR-REP-01…05 |
| UI: upload raw sonar log, view detections on map in real time, download reports | FR-UI-01…08 |
| Efficient; edge/marine drone deployment without heavy cloud | NFR-01…03, NFR-06, NFR-09, FR-OPS-03 |

---

## 18. Glossary

| Term | Meaning |
|---|---|
| **SSS** | Side-scan sonar: acoustic imaging sonar looking sideways from a towfish or AUV |
| **Ping** | One transmitted acoustic pulse and its received echoes; one row of the waterfall |
| **Waterfall** | Image made by stacking pings; rows = time/along-track, columns = range |
| **Nadir** | Seabed directly below the sonar; appears as a dark centre strip |
| **Slant range** | Straight-line distance from sonar to seabed point; differs from horizontal ground range |
| **Acoustic shadow** | Dark area behind an object where sound can't reach |
| **Speckle** | Grainy multiplicative noise typical of coherent acoustic imaging |
| **Layback** | Horizontal distance between the ship's GPS antenna and the towed sonar |
| **XTF** | eXtended Triton Format, a common hydrographic survey file format with sonar data and navigation |
| **AUV** | Autonomous Underwater Vehicle |
| **ALDFG / ghost net** | Abandoned, lost or otherwise discarded fishing gear |
| **MILCO / NOMBO** | Mine-like contact / non-mine-like bottom object (mine-detection dataset labels) |
| **SAHI** | Slicing Aided Hyper Inference: tiled inference for small objects |
| **PatchCore** | Anomaly detection method comparing patch features to a memory bank of normal samples |
| **ECE** | Expected Calibration Error |
| **WGS84 / UTM** | Global geodetic datum used by GPS / projected metric coordinate system |
