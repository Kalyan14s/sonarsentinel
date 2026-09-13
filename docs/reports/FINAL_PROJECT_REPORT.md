# SonarSentinel — Final Project Report (draft)

> **Status: DRAFT (story ST-116), 2026-09-14, written during Sprint 6.** This report follows the [final report template](FINAL_PROJECT_REPORT_TEMPLATE.md). Every number comes from a recorded test report, experiment log, manifest or changelog entry, linked where it is used. Where a result does not exist yet, the text shows a **[PENDING: …]** marker instead of a value. **Do not submit until every marker is resolved or explicitly waived.**
>
> **Pending sources at the time of writing:**
> - **GPU-trained models:** synthetic-data ablation ST-051, small-object variant ST-055, mask refiner ST-056; refit of the FP filter and calibrator on those models (ADR-017 §7)
> - **Data that does not exist yet:** frozen test set evaluation TD-08, contact-free survey lines TD-11 (FP/km²), curated confuser set TD-13 (AC-08), a survey over a charted wreck TD-10 (ST-013, ST-037, TC-GEO-012), AI4Shipwrecks conversion ST-010, NOMBO review ST-011, real labelled tiles and annotator agreement ST-014, synthetic realism review ST-018
> - **People and hardware:** usability test and SUS ST-113, Jetson/TensorRT ST-101, dashboard screenshots, team details
> - **Sprint 6 results still being produced:** robustness suite ST-111, benchmarks ST-112, Docker images ST-005, Test Summary Report TSR-M6
>
> Results on **synthetic data** and results on **real data** are kept in separate tables and labelled in every chapter.

---

## Front matter

### Title page

- **AI-Powered Automated Underwater Marine Debris and Anomaly Detection System using Side-Scan Sonar Imagery — SonarSentinel**
- Smart India Hackathon 2026 · Problem Statement 26057 · Ministry of Earth Sciences — National Institute of Ocean Technology
- **Team name:** Vashishta · **Team ID:** **[PENDING: SIH portal team ID]** · **Institution:** **[PENDING: institution name]** · **Mentor(s):** **[PENDING: mentor names]**
- **Team members and roles:**

| Role | Responsibility ([Project Plan §6](../planning/PROJECT_PLAN.md#6-team-roles-and-responsibilities)) | Member |
|---|---|---|
| R1 · ML Lead | Detector, anomaly model, FP filter, calibration, evaluation, model cards | **[PENDING: member name]** |
| R2 · Sonar & Signal Engineer | Ingest readers, preprocessing, synthetic generators, annotation QA | **[PENDING: member name]** |
| R3 · Geospatial Engineer | Geotagging, measurements, mosaic, GeoJSON/KML exports, geo validation | **[PENDING: member name]** |
| R4 · Backend Engineer | FastAPI, jobs, WebSocket, storage, orchestrator, CLI | **[PENDING: member name]** |
| R5 · Frontend Engineer | Dashboard screens, map, UX, accessibility, usability test | **[PENDING: member name]** |
| R6 · Integration, Edge & PM | Plan, backlog, CI/CD, Docker, edge export, test plan, demo, docs | **[PENDING: member name]** |

- **Month, Year:** September 2026 (draft)

### Declaration / certificate

**[PENDING: declaration and certificate in the institution's required wording, signed by the team and mentor(s)]**

### Abstract

Abandoned fishing nets ("ghost nets") and other seabed debris endanger marine life and navigation. Side-scan sonar (SSS) surveys can find them, but analysts still review hours of imagery by hand. SonarSentinel is an open, offline pipeline that ingests raw XTF logs, GeoTIFF mosaics or images with navigation, and reports every detection with a calibrated 0–100% confidence and a WGS84 position. It corrects sonar geometry and radiometry, masks dropouts and motion, and runs a YOLO11s-seg detector with sliced (SAHI) inference. A PatchCore anomaly model catches objects the detector has no class for. Confidence fuses detector, anomaly, shadow-physics, false-positive-filter and persistence scores and is calibrated by isotonic regression. Positions come from ping-header navigation with layback correction and an uncertainty budget, and a React dashboard streams detections onto a live map. Data: a public mine-detection SSS dataset (118 training cylinders in the baseline), one USGS Klein 3900 survey, and synthetic ghost nets rendered on real seabed. All models so far are CPU baselines. On real validation data the detector reaches mAP@50 0.283 (95% CI 0.174–0.456). Its ghost-net recall on the synthetic holdout is 0.00, because it was trained without ghost nets; the synthetic-data run is **[PENDING: GPU training — ST-051]**. PatchCore reaches tile AUROC 0.957 on a held-out site against synthetic positives. The calibrator lowers ECE from 0.144 to 0.048 on a held-out site, as tooling evidence only. The ONNX runtime matches PyTorch on 38/38 detections and processes a real line at about 220 s per km on a laptop CPU. FP/km² reduction, charted-wreck geolocation error, GPU/Jetson speed and usability are not yet measured. The software path is complete, but the models are not yet good enough for operational use.

**Keywords:** side-scan sonar; marine debris; ghost nets; object detection; anomaly detection; georeferencing; edge AI; disaster management

### Acknowledgements

We thank our mentors **[PENDING: mentor names]** and NIOT/MoES for the problem statement. We also thank the authors and hosts of the datasets used or evaluated: the Mine-detection SSS dataset (N. Pessanha Santos et al., CC BY 4.0), SeabedObjects-KLSG (G. Huo et al.), AI4Shipwrecks (University of Michigan Field Robotics Group, CC BY 4.0), and USGS for the public-domain Grand Bay 2015 survey. NOAA NCEI and the Office of Coast Survey provide the survey catalogues. The work relies on open-source projects including PyTorch, Ultralytics, SAHI, ONNX Runtime, LightGBM, GDAL/rasterio, pyproj, pyxtf, OpenCV, FastAPI, SQLAlchemy, React, Vite and Leaflet. Licences are listed in [Licences & Compliance](../legal/LICENSES_AND_COMPLIANCE.md).

### Table of contents · List of figures · List of tables · Abbreviations

- **Table of contents:** generated at PDF export.
- **List of figures:** the figures below exist as data in the model registry or as wireframes, but have not yet been exported for print. **[PENDING: export figures with captions, units and sources — ST-116]**
  - Fig. 1 System context and containers ([01-system-architecture](../architecture/01-system-architecture.md))
  - Fig. 2 Processing stages S0–S12 ([02-data-pipeline](../architecture/02-data-pipeline.md))
  - Fig. 3 Synthetic ghost-net generator steps ([03-ml-models §4](../architecture/03-ml-models.md))
  - Fig. 4 Validation PR curve and confusion table (`models/detector/yolo11s-seg-sonar-real/0.1.0/eval_val/`, git-ignored registry)
  - Fig. 5 Reliability diagram (data in [EXP-20260913-scoring §5.3](../../ml/experiments/EXP-20260913-scoring.md))
  - Fig. 6 Dashboard screens S-01, S-02, S-03, S-06 **[PENDING: screenshots on real data]**
- **List of tables:** generated at PDF export.
- **Abbreviations:** see the [PRD Glossary](../PRD.md#18-glossary). Also used here: AP (average precision), AUROC (area under the ROC curve), CI (confidence interval), DD/DMS (decimal degrees / degrees-minutes-seconds), ECE (expected calibration error), FP (false positive), GCP (ground control point), NFR/FR (non-functional/functional requirement), RSS (root sum of squares), SUS (System Usability Scale), TP (true positive).

---

## Chapter 1 — Introduction

**Sources:** [Project Idea](../PROJECT_IDEA.md) §1–2, [PRD](../PRD.md) §1–2, [Literature Review](../research/LITERATURE_REVIEW.md) §2

### 1.1 Background

Abandoned, lost or otherwise discarded fishing gear (ALDFG), also called ghost gear, keeps catching marine life, damages habitats and creates navigation hazards [1]. A global meta-analysis estimated that about 5.7% of fishing nets, 8.6% of traps and 29% of lines are lost each year [2]. Recovery programmes use sonar surveys to find nets before divers retrieve them, and manual review of that imagery is the bottleneck [3]. After cyclones and floods, the same kind of debris (wrecks, containers, construction material) blocks channels and ports. Port and disaster authorities then need a ranked hazard list quickly, which is why the problem statement also has a disaster-management angle.

### 1.2 Side-scan sonar and the manual-inspection bottleneck

A side-scan sonar images the seabed on both sides of a towfish or AUV. Each acoustic ping becomes one row of a "waterfall" image. The imagery is hard to read: speckle hides fine structure, the slant-range geometry distorts sizes near nadir, brightness changes with range and between sides, and vehicle motion and dropouts corrupt rows. Objects cast acoustic shadows, but so do rocks and sand ripples [4], [5]. A single survey produces hours of waterfall. Analysts scroll through it, pick contacts and copy coordinates by hand, which is slow and inconsistent (PRD §3 personas).

### 1.3 Problem statement

SIH 2026 problem statement 26057 (MoES/NIOT) asks for an AI system that ingests SSS imagery; copes with speckle, varying resolution, acoustic shadows and dropouts from heave, pitch and roll; and separates natural seafloor from man-made anomalies. The system must detect or segment shipwrecks, pipes, cylinders and debris nets, and give every anomaly a 0–100% confidence while keeping false positives low. It must read sonar metadata (coordinate files and ping headers) and produce a structured JSON/CSV report with latitude/longitude, bounding dimensions and class. A user interface must let users upload a raw log, watch detections on a map in real time and download reports. The system should be efficient enough for edge or marine-drone deployment without heavy cloud use. We read "debris nets" to include lost fishing nets, for which no public labelled SSS data exists, and "real time" to mean streaming results while a file is processed. The full mapping to requirements is in [PRD §17](../PRD.md#17-traceability-to-the-problem-statement) and in Section 3.6.

### 1.4 Objectives

From [PRD §2.1](../PRD.md#2-goals-and-non-goals):

| ID | Goal |
|---|---|
| G1 | Automatically detect and localise man-made debris in SSS imagery with high recall |
| G2 | Detect ghost nets, including when no real ghost-net examples exist in the training data |
| G3 | Reduce false positives from rocks, shadows, ripples and noise, and give a trustworthy confidence per detection |
| G4 | Output the exact GPS location, dimensions and class of each hazard in structured formats |
| G5 | Let users upload a log and watch detections appear on a map in near real time |
| G6 | Run efficiently on edge hardware without cloud dependency |

### 1.5 Scope and non-goals

The minimum viable product (PRD §5.1) covers XTF, GeoTIFF and image + navigation CSV ingestion; preprocessing; five-class detection and segmentation with sliced inference; PatchCore anomalies; shadow-aware fused and calibrated scoring; geotagging with footprint and dimensions; JSON/CSV reports; the dashboard; a CLI; and the synthetic ghost-net generator. Out of scope for this release: controlling AUV navigation, multibeam or forward-looking sonar, IHO-certified chart products, recovery logistics, and multi-tenant cloud service (PRD §2.2).

### 1.6 Contributions

- **Physics-aware, explainable confidence:** a fused score of detector, anomaly, shadow-consistency, learned false-positive and cross-line persistence components with data-quality penalties, calibrated by isotonic regression. The breakdown of every score is stored in the report ([ADR-017](../architecture/08-architecture-decisions.md#adr-017--sprint-4-scoring-storage-and-job-decisions)).
- **Geotagging from ping headers:** each pixel is mapped to WGS84 through navigation cleaning, slant-range correction, layback and a per-detection position-uncertainty budget. Image-only inputs are explicitly marked `NOT_GEOTAGGED`.
- **A synthetic ghost-net generator and anomaly safety net:** nets with mesh, ropes, floats, burial and far-range shadows are rendered onto real seabed. A PatchCore model trained on object-free seabed flags objects outside the known classes.
- **An open, offline, edge-ready pipeline:** one Python package drives the CLI, API and job worker. It streams events over WebSocket with replay, and exports the detector to ONNX with measured parity. The code is published under AGPL-3.0.
- **Honest evaluation tooling:** site-grouped splits with a leakage check, a frozen test hash, bootstrap confidence intervals and experiment logs that keep CPU-baseline results separate from model-quality claims.

### 1.7 Report organisation

Chapter 2 reviews the literature and identifies the gap. Chapter 3 summarises requirements, Chapter 4 the system design and Chapter 5 the data. Chapter 6 describes the methods and Chapter 7 the implementation and development process. Chapter 8 reports test results against the targets, Chapter 9 discusses limitations, and Chapter 10 concludes.

---

## Chapter 2 — Literature Review

**Sources:** [Literature Review](../research/LITERATURE_REVIEW.md)

### 2.1 Side-scan sonar principles and artefacts

Standard references are Blondel [4] and Lurton [5]. The artefacts that matter for detection are slant-range distortion near nadir, acoustic shadows (evidence of height, but also a source of false alarms), multiplicative speckle, range- and beam-dependent gain, per-side imbalance from roll, motion artefacts, dropouts, and the trade-off between frequency and range. Towed systems also need layback correction. Each of these has a matching stage in SonarSentinel (Literature Review §3).

### 2.2 Classical detection approaches

Adaptive despeckling filters (Lee [6], Frost [7]) are fast but oversmooth fine texture. Highlight–shadow segmentation for mine-like objects [8] is physically grounded but sensitive to parameters and seabed type. Handcrafted texture features such as GLCM [9], Gabor filters and FFT, combined with classical classifiers, work with little data but are limited by feature quality. We keep these cues as complementary evidence in the scoring stage (shadow, GLCM and FFT features feeding LightGBM [10]) rather than as the primary detector.

### 2.3 Deep learning for sonar imagery

A recent survey [11] describes the move from handcrafted features to CNN detection and segmentation for sonar. It also notes the recurring problems of small datasets, domain shift between sonars and few public benchmarks. One-stage YOLO detectors [12], [13] are fast and exportable; two-stage Faster/Mask R-CNN [14], [15] can be more accurate but are heavier for edge use; U-Net [16] suits thin-structure refinement; and Segment Anything [17] speeds up mask annotation. Transfer learning with semi-synthetic data helps SSS classification when real data is scarce [19]. Shipwreck segmentation now has a public benchmark [20], and zero-shot sim-to-real transfer has been shown for shipwrecks [21]. From this work we take four lessons: use pretrained backbones with careful augmentation; validate simulation on real data; avoid physically invalid augmentations such as arbitrary rotation, which breaks shadow geometry; and resample to a fixed metres-per-pixel scale.

### 2.4 Datasets and their gaps

| Dataset | Sensor | Content | Gap for this problem |
|---|---|---|---|
| AI4Shipwrecks [20] | EdgeTech 2205 on Iver3 AUV | 286 images, 28 wrecks, pixel masks | Wrecks only; freshwater site |
| Mine-detection SSS [23] | Marine Sonic on Gavia AUV | 1,170 images, MILCO/NOMBO boxes | Mine-like objects only |
| SeabedObjects-KLSG [19] | Several vendors | Image-level class crops | No masks, no nets; academic use only |
| Marine Debris FLS [24] | Forward-looking sonar (ARIS) | Tank debris, semantic masks | Different sensor geometry |
| S3Simulator [22] | Simulated SSS | Synthetic scenes | No published licence |
| NOAA NCEI surveys | Various SSS | Real surveys with navigation | Unlabelled |

**Key gap:** no public, labelled side-scan dataset of ghost nets was found (Literature Review §6).

### 2.5 Ghost-net detection efforts

GhostNetZero (WWF Germany with Microsoft) applies computer vision to SSS-derived imagery, uses a human-in-the-loop validation platform, and reports about 90% ghost-net detection on its own data, which is not released as a benchmark [3]. Nylon and polyethylene nets reflect sound weakly. Detection therefore relies on structure such as mesh texture, ropes, floats, lead lines and entangled debris, and on high-frequency, short-range surveys [4], [5]. Forward-looking sonar work [24] shows debris segmentation at close range, but that geometry differs from SSS.

### 2.6 Anomaly detection, small-object detection and calibration

PatchCore [25] builds a memory bank of normal patch features and needs no anomalous training data. EfficientAD [26] targets very low latency, and anomalib [27] provides implementations. For sonar, "normal" seabed varies widely, so the normal pool must cover seabed types and must not contain hidden debris. For small objects, tiled inference (SAHI [18]), higher input resolution and high-resolution detection heads help. Neural networks are often miscalibrated [28]. Isotonic regression [29], [30] maps scores to probabilities, ECE measures calibration, SHAP [31] explains tree models, and DBSCAN [32] merges repeated sightings.

### 2.7 Georeferencing and edge deployment

Georeferencing SSS pixels needs sonar position, heading, altitude and slant range per ping, plus layback for towed systems [4]. XTF stores these per ping and has open Python readers [33]. PINGMapper [34] shows that automated georectification of recreational SSS is practical. Validation is done against known targets such as charted wrecks and with reciprocal lines. At the edge, ONNX export feeds TensorRT on Jetson or OpenVINO on Intel. INT8 quantisation needs representative calibration data and accuracy checks.

### 2.8 Research gap and how this project addresses it

| Gap | SonarSentinel response | Status in this draft |
|---|---|---|
| No public labelled SSS ghost-net data | Synthetic nets, anomaly detection, review-driven label store | Generator, PatchCore and label store built; synthetic-trained detector **[PENDING: GPU training — ST-051]** |
| Small, heterogeneous SSS datasets | Transfer learning, fixed resolution, physics-valid augmentation, grouped splits | Built; only one real labelled source used so far |
| Uncalibrated scores and false alarms on rocks and shadows | Shadow physics, LightGBM filter, isotonic calibration, tiers | Built and tested on CPU-baseline detections; FP/km² **[PENDING: contact-free lines TD-11 — TC-CONF-009]** |
| Detections without actionable positions | Per-pixel geotagging with uncertainty; GeoJSON/KML | Built; real-world error **[PENDING: charted-wreck survey — ST-037/TC-GEO-012]** |
| Dropouts and motion rarely handled end to end | Quality masks, flags and penalties | Built; robustness suite passes on 7 synthetic fault variants and fails cleanly on a corrupt header ([robustness report](../testing/reports/ROBUSTNESS_2026-09-14.md)) |
| Cloud-dependent or desktop-only tools | Offline operation, Docker, ONNX/edge runtime | ONNX CPU path measured; Jetson **[PENDING: Jetson hardware — ST-101]** |
| Opaque decisions | Score breakdown, model cards, ADRs | Built |

---

## Chapter 3 — Requirements Analysis

**Sources:** [PRD](../PRD.md) §3–7, §11–12

### 3.1 Stakeholders and personas

Five personas drive the requirements ([PRD §3](../PRD.md#3-users-and-personas)). A **survey operator** needs a quick data-quality check and early warnings while still on site. A **marine analyst** at NIOT needs accurate, verifiable detections and standard exports. A **recovery team lead** needs reliable coordinates, size and depth. A **port or disaster authority officer** needs a prioritised hazard list after a cyclone. An internal **ML engineer** needs labelled feedback and versioned models. External stakeholders are MoES/NIOT as problem owner and the dataset providers.

### 3.2 Key user stories

The full list (US-01…US-16) is in [PRD §4](../PRD.md#4-user-stories). The P0 stories that shape the design are: upload an XTF and have debris detected automatically (US-01); see detections appear on a map during processing (US-02); get position, size, depth and class (US-03); see a confidence and the reason for it (US-04); be told about possible ghost nets despite few real examples (US-05); download JSON/CSV and GIS formats (US-06); geotag images from a navigation CSV (US-07); filter by class, confidence and tier (US-08); inspect a chip with its mask (US-09); and be warned about poor data quality (US-16).

### 3.3 Functional requirements summary

| Module | Key requirements | Count (P0/P1/P2) |
|---|---|---|
| Ingestion (FR-ING) | XTF up to 2 GB, GeoTIFF, image + nav CSV, image-only, validation, per-ping navigation, units/CRS, common `SonarLog` | 8 / 2 / 1 |
| Preprocessing (FR-PRE) | Bottom tracking, slant-range correction, gain normalisation, 3-channel input, dropouts, motion flags, 0.10 m resampling, tiling and chunking | 8 / 1 / 0 |
| Detection (FR-DET) | Five classes with masks, sliced inference, anomaly model, tile/chunk merge, model version per detection | 5 / 2 / 0 |
| Confidence (FR-CONF) | Shadow score, features and FP filter, fusion, 0–100 calibration, tiers, breakdown, height, quality penalties | 6 / 2 / 0 |
| Geotagging (FR-GEO) | WGS84 centroid (6 dp), footprint, dimensions, smoothing, depth; layback, uncertainty, mosaic | 5 / 3 / 0 |
| Reporting (FR-REP) | JSON schema, CSV, metadata and summary; GeoJSON/KML, filtered export; PDF | 3 / 2 / 1 |
| Dashboard (FR-UI) | Upload, live view, map, filters, list, detail, downloads, quality warnings; waterfall, review, history, settings, mosaic, offline tiles; edge console | 8 / 6 / 1 |
| CLI, edge, learning (FR-OPS) | CLI, synthetic generator; ONNX/TensorRT/OpenVINO, label store; YOLO export, compact alerts | 2 / 2 / 2 |

Details: [PRD §6](../PRD.md#6-functional-requirements).

### 3.4 Non-functional requirements

| Area | Requirement (target) |
|---|---|
| Performance | NFR-01 1 km line ≤ 60 s on an RTX 3060-class GPU; NFR-02 ≤ 5 min on an 8-core laptop CPU; NFR-03 ≥ 1× acquisition rate on a Jetson Orin Nano-class device (target ≥ 5×) |
| Streaming | NFR-04 first detection event ≤ 15 s; NFR-05 progress interval ≤ 5 s |
| Footprint and memory | NFR-06 detector ≤ 25 MB FP32, ≤ 10 MB INT8; NFR-07 peak RAM ≤ 8 GB on a 2 GB XTF |
| Reliability, offline, portability | NFR-08 no crash on corrupt files; NFR-09 all P0 features offline; NFR-10 Windows, Ubuntu, Jetson, Docker |
| Security | NFR-11 on-premise by default, upload validation, no execution of uploaded content; NFR-12 roles (P2) |
| Usability and accessibility | NFR-13 first report downloaded in ≤ 5 min without training; NFR-14 WCAG 2.1 AA contrast, colour plus shape, keyboard navigation |
| Maintainability, reproducibility, observability, interoperability | NFR-15 ≥ 70% coverage on `geo/`, `scoring/`, `ingest/`; NFR-16 same input + config ⇒ same output; NFR-17 JSON logs and stage timings; NFR-18 valid GeoJSON, KML and UTF-8 CSV |

Full table: [PRD §7](../PRD.md#7-non-functional-requirements).

### 3.5 Success metrics and acceptance criteria

The prototype targets are ([PRD §11](../PRD.md#11-success-metrics)): detection mAP@50 ≥ 0.70 on a real site-held-out test set; recall ≥ 0.85 on `shipwreck` and `cylinder`; ghost-net recall ≥ 0.80 on the synthetic holdout; ≥ 50% fewer false positives per km² after filtering; ECE ≤ 0.10; median geolocation error ≤ 10 m against charted wrecks; the speed targets NFR-01…03; ≥ 70% analyst time saved; and first report in ≤ 5 min. Acceptance criteria AC-01…AC-10 ([PRD §12](../PRD.md#12-acceptance-criteria)) turn these into testable checks: geotagged XTF processing, image without GPS, image with CSV, confidence and tiers, ghost nets and anomalies, robustness, reports, shadow filtering, edge export and offline operation. Section 8.11 compares each target with what was achieved.

### 3.6 Traceability to the problem statement

| Problem statement requirement | Requirements | Where addressed |
|---|---|---|
| Ingest side-scan sonar imagery | FR-ING-01…11 | §6.1, §7.3 |
| Handle speckle noise | FR-PRE-04 | §6.1.6 |
| Handle varying pixel resolutions | FR-PRE-02, FR-PRE-07 | §6.1.4 |
| Handle acoustic shadows | FR-CONF-01, FR-CONF-07 | §6.4.1 |
| Handle dropouts from heave/pitch/roll | FR-PRE-05, FR-PRE-06, FR-CONF-08 | §6.1.5, §8.8 |
| Separate natural seafloor from artificial anomalies | FR-DET-01, FR-DET-03, FR-CONF-02 | §6.2–6.4 |
| Detection/segmentation of shipwrecks, pipes, cylinders, debris nets | FR-DET-01, FR-DET-02, FR-DET-06 | §6.2, §8.3–8.4 |
| Confidence 0–100% for every anomaly; minimise false positives | FR-CONF-01…08 | §6.4, §8.5–8.6 |
| Read sonar metadata (coordinate files, ping headers) | FR-ING-03, FR-ING-06, FR-ING-07 | §6.1.1, §6.5 |
| JSON/CSV report with lat/lon, dimensions, classification | FR-GEO-01…08, FR-REP-01…05 | §4.4, §8.2 |
| UI: upload, real-time map, download reports | FR-UI-01…08 | §4.6, §7.4 |
| Efficient; edge deployment without heavy cloud | NFR-01…03, NFR-06, NFR-09, FR-OPS-03 | §6.7, §8.9 |

---

## Chapter 4 — System Design

**Sources:** [Architecture](../architecture/README.md), [Wireframes](../wireframes/README.md), [ADRs](../architecture/08-architecture-decisions.md)

### 4.1 Architecture principles

Five principles guided the design. **One processing core:** a single `sonarsentinel` Python package serves the CLI, API and edge runs (ADR-001). **Contract-first:** the `SonarLog` contract, the report JSON Schema 1.0 and the API specification were written before the screens, and the frontend developed against a mock API. **Stream, don't batch:** long files are processed in overlapping chunks and events stream over WebSocket (ADR-008). **Offline by default:** no cloud services, optional basemap tiles only (NFR-09, NFR-11). **Explainability:** every score, model version and configuration hash is written to the report (NFR-16).

### 4.2 System context and container architecture

The dashboard (React + TypeScript + Leaflet) talks to a FastAPI service over HTTP and WebSocket. The API hands uploads to a job manager, which runs the processing core. The core calls the model runtime (PyTorch or ONNX Runtime now; TensorRT or OpenVINO planned) and writes to a metadata database (SQLite, with PostgreSQL/PostGIS planned for production, ADR-010), a file store for uploads, chips, mosaics and reports, and a versioned model registry. The CLI calls the processing core directly. Diagrams: [01-system-architecture §1–2](../architecture/01-system-architecture.md). **[PENDING: export Fig. 1 for print — ST-116]**

### 4.3 Processing pipeline design

The pipeline has thirteen stages ([02-data-pipeline §1](../architecture/02-data-pipeline.md)): S0 validate → S1 parse into `SonarLog` → S2 navigation cleaning → S3 bottom tracking → S4 radiometric correction → S5 slant-to-ground and along-track resampling → S6 quality masks → S7 tiling and 3-channel input → S8 inference (YOLO11-seg with SAHI, plus PatchCore) → S9 scoring → S10 geotag and measure → S11 merge across tiles, chunks and lines → S12 report and mosaic. GeoTIFF mosaics skip S3–S5 and use their embedded geotransform. Image-only inputs skip navigation and are flagged `NOT_GEOTAGGED`.

The internal contracts are `SonarLog` (contract 1.0: source format, sonar info, per-ping navigation table, port/starboard sample arrays that may be memory-mapped, warnings), `ProcessedChunk` (ground-range image, 3-channel image, `row_to_ping`, ground resolution, nadir column, quality masks, cleaned navigation) and `Detection` (class, box, mask, scores, confidence, tier, flags, geo).

### 4.4 Data models and report schema

A report ([06-data-models](../architecture/06-data-models.md)) contains survey metadata, processing metadata (pipeline version, model versions, configuration hash, duration), a summary by class and tier, quality events and all detections. Each detection carries `detection_id`, `class`, `confidence` (0–100), `alert_tier`, `position` (lat/lon at 6 decimals, depth, uncertainty), a four-corner `footprint`, `dimensions` (length, width, area, height), `orientation_deg`, a `sonar_ref` (side, ping range, ground range, time), the full `scores` breakdown, `quality_flags` and `review` status. Datum and CRS are WGS84 geographic, EPSG:4326 ([ADR-015](../architecture/08-architecture-decisions.md), proposed and awaiting NIOT confirmation). CSV has 23 columns per 06 §3.1; GeoJSON follows RFC 7946; KML groups detections by class. The database holds the 06 §4 tables plus the full detection JSON per row, so exports reflect review changes (ADR-017, ADR-018).

### 4.5 API and real-time streaming design

REST endpoints under `/api/v1` cover upload and validation, job status and cancel, survey list and detail, filtered and paged detections, track with quality segments, reports in four formats and four scopes, chips, mosaics, review `PATCH` and health ([05-api-specification](../architecture/05-api-specification.md)). The WebSocket `/ws/jobs/{job_id}` sends `progress`, `track`, `warning`, `detection`, `detection_update`, `detection_removed`, `done` and `error` events with a strictly increasing `seq`. A client resumes after its last `seq`. The server replays from memory or from `job.log.jsonl`, sends `done` only after reports and database rows are written, and closes with 1000 (finished) or 4404 (unknown job) ([ADR-018](../architecture/08-architecture-decisions.md#adr-018--sprint-5-dashboard-streaming-export-and-edge-decisions)). Errors use one shape with codes such as `VALIDATION_ERROR` and `JOB_NOT_CANCELLABLE`.

### 4.6 User interface design

Eight screens were wireframed ([wireframes index](../wireframes/README.md)): S-01 [Upload](../wireframes/01-upload.md), S-02 [Live map](../wireframes/02-live-map.md), S-03 [Detection detail](../wireframes/03-detection-detail.md), S-04 [Waterfall viewer](../wireframes/04-waterfall-viewer.md), S-05 [Review queue](../wireframes/05-review-queue.md), S-06 [Reports & export](../wireframes/06-reports-export.md), S-07 [History & settings](../wireframes/07-history-settings.md) and S-08 [Edge console](../wireframes/08-edge-console.md). The main flow is Upload → Live Map → Detection Detail → (Review) → Download, with the map as the main workspace. Classes are distinguished by colour **and** marker shape. Confidence always appears with a tier badge, and poor data quality is always visible on the track. Final screenshots: **[PENDING: dashboard screenshots of S-01, S-02, S-03, S-06 on real data — User Manual screenshot task]**

### 4.7 Deployment architecture

The design ([07-deployment](../architecture/07-deployment.md)) has three topologies: a shore workstation with Docker Compose (backend, nginx frontend, optional GPU override), an edge device (Jetson) running the detector, shadow scoring and geotagging with heavier stages deferred to shore, and a CLI-only mode. Sprint 6 decisions ([ADR-019](../architecture/08-architecture-decisions.md#adr-019--sprint-6-hardening-deployment-and-edge-decisions)) fix the environment variables, a CPU image on `python:3.11-slim`, offline tiles served from an MBTiles file, and an edge `watch` command that prints compact alert lines of at most 256 bytes. Docker images are built, health-checked and scanned with Trivy in CI because the development laptop has no Docker ([docker/README.md](../../docker/README.md); result in [TSR-M6](../testing/reports/TSR-M6.md)).

### 4.8 Key design decisions

| ADR | Decision | Rationale (short) |
|---|---|---|
| ADR-001 | Python + FastAPI for pipeline and API | Sonar, geo and ML libraries are Python-first; native WebSocket |
| ADR-002 | YOLO11s-seg as primary detector | Boxes and masks, speed, one-line exports |
| ADR-003 | 3-channel input: raw, Lee-despeckled, local std | Keeps texture and shape; pretrained weights still apply |
| ADR-004 | Segmentation for nets and pipes | Boxes overestimate irregular and thin objects |
| ADR-005 | Synthetic nets + PatchCore anomaly model | No public ghost-net data |
| ADR-006 | Physics-aware fusion + isotonic calibration | Meaningful 0–100% confidence with a breakdown |
| ADR-007 | Geotag from ping-header navigation | Image files rarely carry positions |
| ADR-008 | Chunked streaming over WebSocket | Bounded memory, live results, resume |
| ADR-009 | React + Leaflet used directly | Offline, no API keys; react-leaflet dropped for licence reasons |
| ADR-010 / ADR-011 | SQLite now, PostGIS later; WGS84 decimal degrees | Zero-setup prototype; interoperable outputs |
| ADR-012 | ONNX as interchange format | One export path, many runtimes |
| ADR-013 | AGPL-3.0 project licence | Compatible with Ultralytics AGPL-3.0 |
| ADR-014 | CSS Modules + design tokens | No extra styling dependency |
| ADR-015 | WGS84 geographic in reports (proposed) | Matches GNSS, ENCs, GeoJSON, KML |
| ADR-016 | Own PatchCore, rule-based stand-in detector, CPU baselines | No GPU; avoid anomalib version pins; CI without weights |
| ADR-017 | Shadow score, renormalised fusion, persistence, JSON calibrator, thread worker | Fill gaps in the design; tooling on CPU baseline must be refitted |
| ADR-018 | WebSocket resume and terminal events, filters, scopes, label store, uncertainty defaults, ONNX `auto` | Reconnect without loss; exports and dashboard agree |
| ADR-019 | Env vars, chunk retry and CPU fallback, settings, offline tiles, watch mode, Docker in CI, benchmarks | Deployable, graceful failure, honest gating |

---

## Chapter 5 — Data

**Sources:** [Datasets](../data/DATASETS.md), [Annotation Guidelines](../data/ANNOTATION_GUIDELINES.md), [Data Management Plan](../data/DATA_MANAGEMENT_PLAN.md), manifest statistics [`sonar-seg-0.1.0.stats.md`](../../data/manifests/sonar-seg-0.1.0.stats.md), [CHANGELOG](../../CHANGELOG.md)

### 5.1 Datasets used

| Dataset | Used as | Size actually used | Licence | Status |
|---|---|---|---|---|
| D2 Mine-detection SSS (2024) [23] | `cylinder` training/val/calib/test; normal seabed pool; demo background | 1,170 images converted (0.61 GB download); 437 MILCO → `cylinder`; 231 NOMBO queued for review | CC BY 4.0 | Converted; NOMBO review **[PENDING: NOMBO review — ST-011]** |
| D2-derived normal seafloor pool | PatchCore memory bank and evaluation normals | 1,687 tiles of 256 px from 866 object-free images | CC BY 4.0 | Built (ST-012) |
| D3 SeabedObjects-KLSG [19] | Planned seafloor pool | 48 MB downloaded; public repository holds only ship and airplane crops, no seafloor images | Academic use only | Not used in training |
| D1 AI4Shipwrecks [20] | Planned `shipwreck` class | Not downloaded (site returns HTTP 403 to scripts) | CC BY 4.0 | **[PENDING: browser download and conversion — ST-010]** |
| USGS Grand Bay 2015 (Klein 3900) | Parser validation, bottom tracking, throughput, anomaly run on real seabed | 4 XTF lines, 65 MB | Public domain (doi:10.5066/P9374DKQ) | In DVC with provenance |
| D5 Synthetic ghost nets 1.0.0 | `ghost_net` training and holdout TD-09 | 2,000 train tiles (3,433 nets) + 200 holdout tiles (329 nets) | Own; backgrounds from D2 | Generated, seed 2026 |
| D5 Synthetic pipes / cylinders 1.0.0 | Future training; PatchCore positives (pipes) | 1,000 pipe tiles (3,626 polygons); 1,000 cylinder tiles (1,015) | Own | Generated |
| D4 S3Simulator [22] | — | Samples kept local only | No licence | Excluded unless authors grant permission |
| D6–D9 NOAA surveys and charted wrecks | Geolocation ground truth | None: no public raw NOAA XTF was reachable | Public | **[PENDING: survey over a charted wreck — ST-013]** |

The training run of the baseline detector used only a subset of D2: 150 images from sites 2010 and 2018 (100 with objects containing 118 cylinders, 50 background) ([EXP-20260913-baseline](../../ml/experiments/EXP-20260913-baseline.md)).

### 5.2 Class taxonomy and mapping

Five detector classes (`shipwreck`, `pipe`, `cylinder`, `ghost_net`, `debris_other`) plus `unknown_anomaly` from PatchCore ([Datasets §4](../data/DATASETS.md)). MILCO maps to `cylinder`. Reviewed man-made NOMBO objects will map to `debris_other` and natural or ambiguous ones become hard negatives. AI4Shipwrecks masks map to `shipwreck`. `ghost_net` currently comes only from the synthetic generator. KLSG drowning-victim images are excluded everywhere. **In practice only `cylinder` (real) and `ghost_net` (synthetic) have labels in manifest 0.1.0**, and the baseline detector was trained on `cylinder` alone.

### 5.3 Annotation process and quality control

The guidelines specify CVAT or Label Studio with SAM 2-assisted masks (SAM 3 excluded for licence reasons), class definitions and edge cases, a 20-tile calibration session and 10% double labelling ([Annotation Guidelines §9](../data/ANNOTATION_GUIDELINES.md#9-quality-control)). The tile source for real XTF labelling exists (`ml/datasets/xtf_to_tiles.py`). No real tiles have been labelled yet, so no agreement values exist. **[PENDING: ≥ 100 labelled real tiles and inter-annotator agreement — ST-014]**

### 5.4 Synthetic data generation

The ghost-net generator ([03-ml-models §4](../architecture/03-ml-models.md)) builds a regular mesh (5–30 cm), crumples it elastically, cuts an irregular clump envelope (1–15 m), optionally adds ropes, float lines and floats, and buries 0–60% of it. It then renders a weak highlight with Rayleigh speckle, casts a far-range shadow whose length depends on height, and blends the result onto a real seabed tile with an automatic mask. Every tile stores its generator version, seed and parameters. Version 1.0.0 produced 2,000 train tiles and 200 holdout tiles on 2017 backgrounds, a site excluded from training. A developer spot check found that nets with floats and ropes and the correct shadow side look plausible, while some solid clumps look more like debris (TODO, ST-016). Background pixel size is assumed to be 0.10 m/px. The planned realism rating has not been done. **[PENDING: realism review of 100 tiles, ≥ 70% plausible — ST-018]**

### 5.5 Dataset splits and leakage prevention

`ml/datasets/make_splits.py` assigns whole sites to splits, keeps synthetic tiles in training only, and excludes the holdout background site (2017) from training. An automated leakage check compares sites and 64 × 64 thumbnail correlations (≥ 0.97). dHash was rejected because unrelated waterfalls hash within 3 bits. The test split hash is frozen. Final statistics of `sonar-seg@0.1.0`:

| Split | Sites | Images | cylinder | ghost_net |
|---|---|---|---|---|
| train | 3 (2010, 2018, synthetic) | 2,909 | 118 | 3,433 |
| val | 1 (2017) | 93 | 28 | 0 |
| calib | 1 (2021) | 48 | 49 | 0 |
| test (TD-08, frozen) | 1 (2015) | 120 | 242 | 0 |
| synthetic holdout (TD-09) | 1 (2017 backgrounds) | 200 | 0 | 329 |

`shipwreck`, `pipe` and `debris_other` have 0 objects in every split. Median object size is 0.045 × 0.025 of the image side for cylinders and 0.055 × 0.056 for ghost nets. The leakage check passed: no site appears in more than one split, and no cross-split image pair reaches thumbnail correlation 0.97. For the synthetic ablation, positives are 71% synthetic by image and 79% by object, above the ≤ 40% guideline, which applies once real ghost-net positives exist ([EXP-20260913-synth](../../ml/experiments/EXP-20260913-synth.md)).

### 5.6 GPS-tagged survey data and ground truth for geolocation

The only real geotagged survey is USGS Grand Bay 2015: four Klein 3900 XTF lines. The reader matches pyxtf's independent packet parser on lat/lon, heading, slant range and samples for 10 pings per file (TC-ING-006), and all four tracks lie inside the survey's metadata bounding box. The recorded altitude in these files is implausible (1–74 m in a shallow estuary), so bottom tracking replaces it (Section 7.7). No line crosses a charted wreck, so the geolocation ground truth planned in [Datasets §5](../data/DATASETS.md) is still missing. **[PENDING: ≥ 3 surveys, ≥ 2 sonar models, ≥ 1 charted wreck — ST-013; TD-10]**

### 5.7 Ethics and sensitive data handling

Drowning-victim images in KLSG are excluded from training, demos and screenshots ([DMP §7](../data/DATA_MANAGEMENT_PLAN.md#7-sensitive-data-and-ethics)). Datasets without a published licence (S3Simulator, KLSG-II) are not used. NOAA-derived outputs must carry a "not for navigation" notice. Mine-like objects in D2 are training targets, but the model is not a mine-countermeasure tool (model card §8). The demo asset A3 uses a fictional track off Chennai harbour and is always labelled synthetic ([demo README](../../demo/README.md)). No restricted or partner data has been used. Dataset licences are recorded in [Licences & Compliance §3](../legal/LICENSES_AND_COMPLIANCE.md#3-datasets-and-data-sources).

---

## Chapter 6 — Methodology

**Sources:** [02-data-pipeline](../architecture/02-data-pipeline.md), [03-ml-models](../architecture/03-ml-models.md), [04-geotagging-engine](../architecture/04-geotagging-engine.md), ADR-016…019, experiment logs

### 6.1 Preprocessing

#### 6.1.1 Navigation cleaning and units

Units come from the XTF `NavUnits` header (0 = projected metres, which requires an EPSG code; 3 = latitude/longitude) plus a value-range check. Projected coordinates are converted to WGS84 with pyproj, and the user can override the UTM zone. Invalid fixes, meaning (0, 0), NaN, or jumps implying more than the maximum plausible speed (default 6 m/s), are rejected relative to the median position and interpolated with `GPS_INTERPOLATED`. Positions are smoothed with a Savitzky–Golay filter on UTM eastings and northings (window 31 pings). Heading is smoothed circularly (window 25) by averaging sine and cosine. When heading is missing, course over ground is used and flagged `HEADING_FROM_COG`.

#### 6.1.2 Bottom tracking

For each ping, the first seabed return is the first sample after transmit blanking where the smoothed port + starboard intensity exceeds

`max(k × water_level, water_level + 0.3 × (seabed_median − water_level))`

and stays above it for about 1% of the range, so thin water-column lines are ignored. The water level is the lower of the 5th percentile of the first half and the median of the leading samples. Runs far from a 1,000-ping rolling median are interpolated, and a 31-ping median filter follows. In `auto` mode the recorded altitude is kept where it agrees with the tracked value within 25%. Otherwise the tracked altitude is used and `NO_ALTITUDE_BOTTOM_TRACKED` is raised. Samples before the first return form the water-column mask.

#### 6.1.3 Radiometric correction

Across-track gain divides each column by a running mean profile over a 200-ping window. Each column is capped at its 99th percentile before the mean, so bright objects do not darken their own range bins (fixed in Sprint 3). Port and starboard medians are normalised separately to remove roll imbalance. Dynamic range is compressed with `log1p` and a 1–99.5% percentile clip to uint8.

#### 6.1.4 Slant-range correction and resampling

Ground range `g` follows from slant range `s` and altitude `h`:

`g = sqrt(s² − h²)`

Samples are interpolated onto a fixed ground grid (0.10 m). Along track, the cumulative GPS distance between pings maps to rows at 0.10 m spacing, and `row_to_ping` is kept for geotagging. The result is a square-pixel image with nadir at the centre, port on the left and starboard on the right. For unprocessed images with a navigation CSV, slant range is `|col − nadir_col| / samples_per_side × slant_range_max` before the same correction.

#### 6.1.5 Quality masks: dropouts and motion

| Flag | Rule (defaults) | Effect |
|---|---|---|
| `DROPOUT` | Row std < 5% of the median row std, row mean < 1, or a duplicate of the previous row | Gaps ≤ 3 pings inpainted; longer gaps masked; overlapping detections penalised |
| `HIGH_MOTION` | \|roll\| > 5°, \|pitch\| > 5°, or yaw rate > 3° per ping (wrapping at 360°) | Penalty; track segment highlighted |
| `SURFACE_RETURN_BAND` | Slant range ≈ sensor depth | Flag; linear track-parallel detections removed only when `preprocess.surface_return_mask` is on |
| `NEAR_NADIR`, `TILE_EDGE` | Steep-incidence zone; object cut by the swath edge | Flags without penalty (ADR-017) |

#### 6.1.6 Three-channel input and tiling

The model input stacks raw normalised intensity, a Lee-despeckled image (5 × 5) and a local standard deviation (7 × 7), each scaled to uint8 (ADR-003). A single implementation in `preprocess/channels.py` is used for both training tiles and inference. Chunks are 2,000 pings with a 200-ping overlap, and tiles are 640 × 640 px with 25% overlap. Tiles more than 80% masked are skipped.

### 6.2 Detection and segmentation (YOLO11-seg, SAHI)

The detector is Ultralytics YOLO11s-seg, fine-tuned from COCO weights (ADR-002). The design configuration is 200 epochs, batch 16, patience 40, `close_mosaic` 15 and `freeze` 10, with rotation, perspective, shear, hue and saturation disabled so shadows stay aligned with the range axis ([03-ml-models §3.2–3.3](../architecture/03-ml-models.md)). **The only completed training run is a CPU baseline with a shorter schedule:**

| Setting | Baseline run (EXP-20260913-baseline) |
|---|---|
| Data | 150 real images (100 with objects, 118 cylinders; 50 background) |
| Input | 3-channel PNG, 640 px |
| Schedule | 20 epochs, patience 10, batch 8, freeze 10, cosine LR, `close_mosaic` 5, deterministic, seed 42 |
| Augmentations | fliplr 0.5, flipud 0.5, hsv_v 0.3, scale 0.3, mosaic 1.0, copy_paste 0.4; no rotation, shear, perspective or hue |
| Hardware / time | Intel i5-13420H, 16 GB, CPU only, workers 0 · 0.80 h |

The design's offline sonar augmentations (speckle, gain ramp, dropout stripes, row jitter) are not part of the baseline run.

**Sliced inference:** the pipeline uses SAHI with 512 px slices and 20% overlap (the default in `pipeline.yaml`). The raw score threshold in the adapter is 0.20. **Merging:** detections of the same class are merged across tile overlaps by IoU/IoS. Across chunks, the copy farther from its chunk edge is kept (ST-054). When no trained weights exist, a transparent rule-based detector `classical-bright-target@0.1.0` stands in, so the thin slice and CI run everywhere. Its reports carry `RULE_BASED_DETECTOR` (ADR-016).

### 6.3 Anomaly detection (PatchCore)

PatchCore [25] is implemented directly in PyTorch, without anomalib (ADR-016). It uses ImageNet ResNet-18 layer2 + layer3 features with 3 × 3 neighbourhood pooling on 256 px tiles. From 150,000 sampled patches, a greedy coreset of 3,000 is kept, using a 128-d random projection. The anomaly score is the kNN distance, and heatmaps are smoothed with a Gaussian of σ = 4. The **normal pool** is 1,687 object-free D2 tiles; the memory bank uses 600 tiles from sites other than 2017. **Thresholds** are set on held-out normals: the tile threshold is the 99th percentile of normal tile scores (3.380) and the pixel threshold the 99.9th percentile of normal heatmaps (2.947). In the pipeline, the mean heatmap inside each mask becomes `scores.anomaly`. Heatmap regions outside detector boxes become `unknown_anomaly` detections ([EXP-20260913-patchcore](../../ml/experiments/EXP-20260913-patchcore.md)).

### 6.4 Confidence scoring

#### 6.4.1 Shadow consistency and height estimation

The shadow score is the geometric mean of highlight contrast (object versus its surrounding ring) and far-range shadow darkness, scaled by the fraction of object rows that have a shadow run. It is 0 when the object is not brighter than its surroundings (ADR-017 §1). Height above the seabed follows from shadow length `Ls`, ground range `r` to the object's far edge and sensor altitude `H`:

`h = Ls · H / (r + Ls)`

`height_m` is null without a usable shadow. On tiles without navigation (the ML tooling datasets), the shadow side is unknown, so both directions are scored and the stronger one is kept; in the pipeline the side comes from the nadir column.

#### 6.4.2 Feature-based false-positive filter

For every detection, `scoring/features.py` computes 36 features in seven groups: model, shadow, geometry, edge, texture (GLCM, FFT periodicity), context (ring texture similarity, ripple FFT peak) and data quality. The median time is under 5 ms per detection. A LightGBM binary classifier predicts whether a detection is a true positive (150 rounds, 7 leaves, at least 5 rows per leaf, feature and bagging fraction 0.8, L2 1.0). It is trained on validation-split detections labelled TP when IoU ≥ 0.5 with an unused ground-truth box, and evaluated out of fold over 5 image-grouped folds. SHAP contributions explain the model ([EXP-20260913-scoring](../../ml/experiments/EXP-20260913-scoring.md)).

#### 6.4.3 Score fusion, isotonic calibration and alert tiers

The fused score is a weighted mean over the components present, minus quality penalties, clipped to [0, 1] (ADR-017 §2):

`fused = Σ wᵢ·sᵢ / Σ wᵢ − 0.20·dropout_overlap − 0.10·motion_flag`

The configured weights are detector 0.45, anomaly 0.15, shadow 0.15, FP filter 0.15 and persistence 0.10. Persistence is `1 − 0.5^n_views`: 0.50 for one view and 0.75 for two (ADR-017 §3). The weights were checked by a grid search on validation AP with a 0.05 step.

Calibration fits pool-adjacent-violators isotonic regression on (fused score, is-TP) using the separate calibration split (site 2021). The calibrator is stored as JSON breakpoints and applied by linear interpolation, with no pickle or scikit-learn at runtime. The reported confidence is `100 × calibrator(fused)`. ECE uses 10 equal-width bins, out of fold over 5 image-grouped folds, with a 200-resample bootstrap CI over images.

| Tier | Rule |
|---|---|
| `hazard` | confidence ≥ 80 |
| `review` | 50 ≤ confidence < 80 |
| `anomaly` | 30 ≤ confidence < 50 **and** anomaly score ≥ τ |
| `hidden` | otherwise |

Sprint 4 fixed a bug in which detections were placed in the `anomaly` tier without checking the anomaly score against τ ([CHANGELOG](../../CHANGELOG.md), Fixed Sprint 4).

### 6.5 Geotagging and measurement

**Coordinate frames:** image (row, col) → sonar (ping, side, ground range) → local tangent (along/across track) → WGS84 geodetic, with UTM used internally for metric work ([04-geotagging-engine §1](../architecture/04-geotagging-engine.md)). **Pixel to position:** `ping = row_to_ping[row]`; the side follows from `col` relative to `nadir_col`; `ground_range = |col − nadir_col| × ground_res_m`; bearing is heading + 90° (starboard) or − 90° (port); and `(lat, lon) = geod.fwd(lon_fish, lat_fish, bearing, ground_range)` on the WGS84 ellipsoid. GeoTIFF pixels use the raster geotransform and CRS.

**Measurements:** the mask centroid gives the position. `cv2.minAreaRect` gives four footprint corners, length, width and orientation from true north. Area is mask pixels × resolution². Depth is sensor depth + altitude.

**Layback:** when only ship position exists,

`layback ≈ sqrt(max(L² − (d − tow_point_height)², 0)) + antenna_to_tow_point`

with cable out `L` and towfish depth `d`. The towfish position is then projected astern along heading + 180°, and the detection is flagged `LAYBACK_ESTIMATED`. An XTF layback field or a manual value takes precedence. The along-track time lag in the design is **not** applied, because the design gives no formula (TSR-M4 §6).

**Uncertainty budget:** horizontal 1-σ uncertainty is the root-sum-square of GNSS, layback, heading (`ground_range × sin σ_heading`), altitude (`σ_alt × altitude / ground_range`), time (`speed × σ_time`) and pixel quantisation (`ground_res_m / √12`) terms ([04 §8](../architecture/04-geotagging-engine.md#8-position-uncertainty-budget)). The defaults are GNSS 2.0 m, heading 2.0°, altitude 0.5 m, time 0.2 s and estimated-layback fraction 0.10 (ADR-018 §8).

**Mosaic:** ground control points are sampled along each chunk and the image is warped with thin-plate splines to EPSG:4326 through rasterio's GDAL, written as GeoTIFF, RGBA PNG and Leaflet bounds (ADR-018 §9).

### 6.6 Merging across tiles, chunks and survey lines

Across tiles, same-class detections in overlaps are merged by IoU and intersection-over-smaller. Across chunks, duplicates in the 200-ping overlap are matched and the copy whose centre is farther from its chunk edge is kept; the dashboard receives `detection_update` or `detection_removed`. Across survey lines (P1), a haversine DBSCAN with 5 m radius, `min_samples` 1, same class and at least 2 lines keeps the most confident member. The merged detection gets the averaged position, `n_views`, the persistence term and a rescored confidence (ST-038). Lines are processed in upload order, and detection IDs are renumbered across lines (ADR-017 §11).

### 6.7 Edge optimisation (ONNX, TensorRT, INT8)

The detector is exported with Ultralytics at a fixed 640 px input (opset 18, simplified with onnxslim) and executed by ONNX Runtime's CPU provider. `detection.runtime: auto` picks `best.onnx` when ONNX Runtime is installed and falls back to PyTorch (ADR-018 §10). Parity is checked by matching detections of the same class one to one at IoU ≥ 0.95 with a score tolerance of 0.02 (TC-EDGE-001). TensorRT FP16/INT8 engines must be built on the Jetson with real calibration tiles, and INT8 must stay within 3 mAP@50 points of FP32 (AC-09). An unavailable accelerator falls back to ONNX Runtime and then PyTorch with `CPU_FALLBACK` (ADR-019 §2). **[PENDING: TensorRT FP16/INT8 build and benchmark on Jetson — ST-101]**

---

## Chapter 7 — Implementation

**Sources:** repository, [Contributing](../../CONTRIBUTING.md), [Developer Setup](../guides/DEVELOPER_SETUP.md), [Project Plan](../planning/PROJECT_PLAN.md), [CHANGELOG](../../CHANGELOG.md)

### 7.1 Technology stack and versions

**Backend and ML (verified environment).** Versions are those recorded in the verified-combination note in [Developer Setup §3.2](../guides/DEVELOPER_SETUP.md), [`requirements-ml.txt`](../../backend/requirements-ml.txt), the Phase 1 environment check in the CHANGELOG, the [ONNX log](../../ml/experiments/EXP-20260914-onnx.md) and the [dependency scan](../testing/reports/SECURITY_SCAN_2026-09-14.md). All were verified on Windows 11, CPU only.

| Component | Version | Source |
|---|---|---|
| Miniforge / Python | 26.7.2 / 3.11.16 | CHANGELOG 0.3.0 notes |
| GDAL · rasterio · pyproj · OpenCV · pyxtf | 3.12.3 · 1.4.4 · 3.7.2 · 5.0.0 · 1.5.0 | CHANGELOG 0.3.0 notes; TODO ST-003 |
| NumPy | 2.4.6 | Developer Setup §3.2 |
| torch · torchvision | 2.14.0+cpu · 0.29.0+cpu | Developer Setup §3.2; `requirements-ml.txt` |
| ultralytics · sahi | 8.4.150 · 0.12.6 | same |
| lightgbm · scikit-learn | 4.7.0 · 1.9.1 | same |
| onnxruntime · onnx · onnxslim | 1.30.0 · 1.22.0 · 0.1.96 | ONNX log; `requirements-ml.txt` |
| pip-audit · npm | 2.10.1 · 10.9.3 | Dependency scan |

**Declared constraints (installed versions not recorded).** [`pyproject.toml`](../../backend/pyproject.toml) sets the package version to 0.1.0 and requires Python ≥ 3.11. Core dependencies are typer ≥ 0.12, PyYAML ≥ 6.0, numpy ≥ 1.26, pandas ≥ 2.1 and pyproj ≥ 3.6. The `geo` extra adds scipy ≥ 1.11, rasterio ≥ 1.3, shapely ≥ 2.0, opencv-python-headless ≥ 4.9 and pyxtf ≥ 1.4. The `api` extra adds fastapi ≥ 0.110, uvicorn ≥ 0.29, sqlalchemy ≥ 2.0, pydantic-settings ≥ 2.2 and python-multipart ≥ 0.0.9. The `dev` extra adds pytest ≥ 8, ruff ≥ 0.6, mypy ≥ 1.10, jsonschema ≥ 4.21 and httpx ≥ 0.27. `requirements-ml.txt` pins `ultralytics>=8.4,<8.5` and `sahi>=0.12,<0.13`. The pipeline configuration version is 0.2.0 and the report schema is `report-1.0`.

**Frontend (after the Sprint 6 upgrade).** [`frontend/package.json`](../../frontend/package.json) was upgraded in Sprint 6 to clear the advisories in Section 8.2: react and react-dom ^18.3.1, react-router-dom ^7.18.3, leaflet ^1.9.4, leaflet.markercluster ^1.5.3, vite ^8.3.0, vitest ^5.0.0, @vitejs/plugin-react ^6.1.1, typescript ~5.6.3, eslint ^9.39.5, jsdom ^25.0.1 and json-schema-to-typescript ^15.0.4. `npm audit` reports 0 vulnerabilities. The runtime is Node.js 22 LTS (Developer Setup §3.2.1; TSR-M6).

### 7.2 Repository structure and module overview

| Path | Contents |
|---|---|
| `backend/sonarsentinel/` | `ingest/` (readers, `SonarLog`, chunking), `geo/` (units, navigation, measure, layback, uncertainty, cluster, mosaic), `preprocess/` (bottom, gain, geometry, dropout, motion, surface, channels, tiling, pipeline), `detect/` (YOLO adapter with SAHI, rule-based stand-in, PatchCore, merge), `scoring/` (shadow, features, fusion, calibration), `report/` (schema, exports, chips), `pipeline.py`, `jobs/`, `storage/`, `api/`, `edge/`, `cli.py`, `config.py`, `errors.py` |
| `backend/configs/`, `backend/tests/` | `pipeline.yaml`; pytest suites including the synthetic XTF generator |
| `ml/` | `train_detector.py`, `evaluate.py`, `compare_sahi.py`, `train_anomaly.py`, `train_fp_filter.py`, `tune_fusion.py`, `calibrate.py`, `export_onnx.py`, `datasets/`, `synth/`, `experiments/`, `notebooks/`, `tests/` |
| `frontend/src/` | `api/`, `components/`, `dashboard/`, `geo/`, `map/`, `pages/`, `upload/`, `styles/`, `tokens.ts`, tests |
| `data/`, `models/` | DVC-tracked datasets and manifests; git-ignored model registry |
| `demo/`, `docs/`, `scripts/`, `edge/`, `docker/`, `.github/workflows/ci.yml` | Demo assets, documentation, utilities (fetch, QA, benchmarks, docs check), edge and container files, CI |

### 7.3 Backend and job pipeline implementation highlights

- **Readers:** the XTF reader makes a header-only scan, recovers truncated files (`TRUNCATED_FILE`), falls back from sensor to ship navigation, handles `NavUnits`, selects channels and detects port sample order. It copies samples into `.npy` memory maps in two passes. On a 2.0 GB synthetic XTF (53,176 pings × 2 × 10,000 samples) it read the file in 6 s with 91 MB peak private memory and a 2.1 GB peak working set, mostly reclaimable mapped pages (ST-026). GeoTIFF pixels match rasterio's pixel centres to < 1 µm (ST-022).
- **Orchestrator:** `pipeline.py` runs S0–S7 → detect → merge → measure → score → report and emits progress, track, warning, detection and done events. The same input and configuration give an identical report apart from `generated_utc` and `duration_s` (TC-REP-005, TC-REP-006).
- **CLI:** `version`, `validate`, `config`, `inspect`, `track`, `detect` (with `--nav`, `--utm-epsg`, `--min-conf`, `--no-anomaly`, `--allow-no-gps`, `--detector auto|classical|yolo`, `--formats`) and `serve [--mock]`.
- **Jobs and storage:** a single background worker thread with a FIFO queue (a deviation from ADR-001's process workers, ADR-017 §10). Cancellation stops a running job within one chunk. Events go to `job.log.jsonl`. SQLite is accessed through SQLAlchemy 2.0 with in-app versioned migrations.
- **API:** streamed multipart upload with a 413 at the size limit, sanitised filenames, SHA-256 and magic-byte checks. It also provides results, filters shared by API, mock and exports, review with a label store (`labels/<yyyy-mm>/<detection_id>/label.json` plus chip), and the WebSocket with resume and replay.
- **Reports:** JSON Schema 1.0, 23-column CSV, RFC 7946 GeoJSON, KML with class folders, 256 px chips with `mask`, `shadow`, `anomaly` and `none` overlays, and the mosaic.

### 7.4 Dashboard implementation

Built in Sprints 3–5 with React, TypeScript, Vite and Leaflet used directly, with CSS Modules and design tokens:

- **S-01 Upload** (ST-091): drop zone, per-file validation and badges, nav CSV or "continue without GPS", advanced options, progress and cancel, offline and error states.
- **S-02 Live map** (ST-092): incremental Leaflet layers, clustered markers, growing track, dropout and high-motion segments, footprints at zoom ≥ 17, mosaic overlay, progress/ETA, and Reconnecting, failed and not-geotagged states.
- **Filters and list** (ST-093): client-side filters with the same rules as the API, synced to the URL; a windowed list with keyboard navigation.
- **S-03 Detail drawer** (ST-094): chip with overlay switch, DD at 6 dp and DMS identical to the backend formatter, copy button, size, depth and uncertainty, "Why N%?" score bars, flags and review actions.
- **S-06 Reports & export** (ST-095): four format cards (GeoJSON/KML disabled without GPS), four scopes, preview and downloads.

Not built by the end of Sprint 5 (D-M5-05): score-breakdown, low-confidence and DMS options on S-06, basemap switcher, pointer coordinates and C/R/K review shortcuts. Sprint 6 added the S-05 review queue with C/R/K keyboard decisions and undo (ST-096), S-07 history with search, filters and delete and a settings screen (ST-098), and the offline MBTiles basemap switch (ST-099). The coordinate-format setting is stored but not yet applied to the display, and Re-run only pre-fills the survey name. S-04 waterfall viewer (ST-097) was dropped (ADR-019 §9). **[PENDING: final screenshots of S-01…S-06 on real data — User Manual screenshot task]**

### 7.5 Edge deployment implementation

The ONNX CPU path is implemented and measured (Section 8.9). Sprint 6 adds, per ADR-019: `SS_*` environment variables, chunk retry with `CHUNK_SKIPPED`, the `CPU_FALLBACK` chain, a job timeout, and the `sonarsentinel watch DIR --out OUT` folder watcher with `SS1|…` alert lines of at most 256 bytes. Tailing a growing file chunk by chunk is not implemented. Watch mode processes each stable file once, keeps state across restarts and writes `alerts.log` (TC-EDGE-003 automated in `test_watch.py`). Docker images and Compose files for shore, GPU override and edge are built and scanned in CI (ST-005); a browser run against the containers (TC-E2E-004) is still manual. **[PENDING: Jetson TensorRT — ST-101 / TC-EDGE-002]**

### 7.6 Development process

**Process.** The plan was Scrum-lite: a setup Sprint 0 plus six one-week sprints, each ending in a milestone and quality gate ([Project Plan §2](../planning/PROJECT_PLAN.md)). Work is tracked as 91 backlog stories imported as GitHub issues with epic, priority and role labels and sprint milestones. [TODO.md](../../TODO.md) is the master checklist, with evidence notes on each ticked item and explicit carry-over of open items between phases.

**CI and quality.** GitHub Actions runs backend lint (ruff), format check, strict mypy, pytest with coverage, documentation checks (`scripts/docs/verify_docs.ps1`), the frontend lint, typecheck, tests and build, and a conda environment build on ubuntu-latest and windows-latest. Branch protection on `main` requires a pull request and 5 checks and forbids force pushes, though admins may push directly. Pre-commit hooks run whitespace, YAML/TOML, large-file and ruff checks. Every training run gets an experiment log and every model a card. Architectural choices are recorded as ADRs. **[PENDING: code-review record (reviewed pull requests per sprint) — ST-116]**

**Planned versus actual timeline.** The sprint plans kept the illustrative calendar dates, but the work started early and ran far ahead of it. Sprints 0–5 were all built on 2026-09-13 and 2026-09-14.

| Sprint | Planned dates | Actual | Evidence | Gate result |
|---|---|---|---|---|
| S0 · Setup | 09-14 → 09-18 | 2026-09-13 | Phase 1 closed 2026-09-13; CI green on Ubuntu and Windows | M0 met |
| S1 · Ingest & Geo | 09-21 → 09-25 | 2026-09-13 | Merged `8d13648` | M1 exit met; G1 contract approval still open |
| S2 · Preprocess & Data | 09-28 → 10-02 | 2026-09-13 | Merged `4237954` | M2 partly met (QA review, AI4Shipwrecks open) |
| S3 · Models & thin slice | 10-05 → 10-09 | 2026-09-13 | `d0f97c1`, CI fix `69f90cb` | G2 thin slice green in CI |
| S4 · Scoring & API | 10-12 → 10-16 | 2026-09-13 → 09-14 | `21a76c0`; closed 09-14 ([TSR-M4](../testing/reports/TSR-M4.md)) | **G3 No-go** (model quality) |
| S5 · Dashboard | 10-19 → 10-23 | 2026-09-14 | `4abccc8` ([TSR-M5](../testing/reports/TSR-M5.md)) | **G4 No-go** |
| S6 · Hardening & demo | 10-26 → 10-30 | 2026-09-14 | [Sprint 6 plan](../planning/SPRINT_6_PLAN.md) ([TSR-M6](../testing/reports/TSR-M6.md)) | **G5 No-go** (no release-candidate tag) |

Items needing people, external data or hardware did not move at the same pace. By Phase 7, 35 items had been carried forward, some since Phase 1 (team ID, idea PDF upload, S3Simulator request). The SIH idea submission deadline is 30 Sept 2026, and the finale is proposed for December 2026.

### 7.7 Challenges encountered and how they were solved

1. **OpenMP runtime clash on Windows.** Conda NumPy/SciPy (Intel OpenMP) and pip PyTorch (LLVM OpenMP) aborted training with "OMP: Error #15". The training scripts set `KMP_DUPLICATE_LIB_OK=TRUE`, the documented workaround, and Developer Setup explains it (ADR-016 §4). A related local-only issue remains: `import torch` fails with WinError 127 when one API test runs after the job tests in the same process (D-M4-06). CI has no torch, so it is not affected.
2. **Memory-limited CPU training.** The synthetic-data ablation (ST-051) was stopped twice during epoch 2 for low memory. The trainer swung between about 1 and 3.5 GB within an epoch while other applications held about 10 GB of the 16 GB. We added `--resume` to continue from the last checkpoint, but kept batch 8 rather than halving it: a smaller batch would change the schedule and make the comparison with the baseline unfair. The run still needs ≥ 6 GB free RAM or a GPU ([EXP-20260913-synth](../../ml/experiments/EXP-20260913-synth.md)). Without a GPU, ADR-016 also limited Sprint 3 to short CPU baselines, and ADR-017 §7 labels all scoring artefacts fitted on them as tooling evidence.
3. **Port sample order on Klein data.** The XTF specification stores odd-numbered side-scan channels reversed, so port is far range first. The first heuristic assumed the darker end was nadir and guessed wrong on 3 of 4 USGS lines, because in shallow water nadir is bright. The reader now correlates the port and starboard range profiles. It falls back to far-first with `PORT_ORDER_ASSUMED` when evidence is weak, and the check must be repeated on each new sonar model (02-data-pipeline S1).
4. **Bottom tracking in shallow water.** Recorded altitudes in the Grand Bay files were 1–74 m in water only a few metres deep, so they could not be used. Three fixes found on real data made tracking stable: a persistent-return rule that ignores thin artefact lines, a water-column level taken from the leading samples plus a relative rise, and a 1,000-ping continuity check that removes long outlier runs. Tracked altitude is 0.49–1.2 m with no outlier runs, and `auto` mode became the default (ST-040).
5. **CI without torch.** CI does not install torch, ultralytics or lightgbm. The first Sprint 3 push (`d0f97c1`) failed strict mypy for that reason; `69f90cb` treats torch as an optional untyped import. Tests that need the ML stack skip in the CI-equivalent environment (2 skipped in TSR-M4, 3 in TSR-M5). The rule-based stand-in detector and identity calibrator let the thin slice run in CI without weights.
6. **Data access and licences.** AI4Shipwrecks blocks scripted downloads (HTTP 403). The public KLSG repository has no seafloor images, so the normal pool was rebuilt from D2. react-leaflet's Hippocratic License is incompatible with AGPL-3.0, so Leaflet is used directly. SAM 3's licence excludes military uses, so SAM 2 was chosen. S3Simulator and KLSG-II have no licence and were excluded.
7. **Smaller defects found along the way.** Bright objects darkened their own range bins in gain normalisation (fixed with a per-column 99th-percentile cap). The `anomaly` tier ignored τ (fixed). dHash proved useless for waterfall leakage checks, since unrelated images hash within 3 bits, so thumbnail correlation replaced it.

---

## Chapter 8 — Testing and Results

**Sources:** [Test Plan](../testing/TEST_PLAN.md), [Test Cases](../testing/TEST_CASES.md), [TSR-M4](../testing/reports/TSR-M4.md), [TSR-M5](../testing/reports/TSR-M5.md), [dependency scan](../testing/reports/SECURITY_SCAN_2026-09-14.md), experiment logs in [`ml/experiments/`](../../ml/experiments/README.md), [model card draft](../../ml/experiments/model_card_yolo11s-seg-sonar-real-0.1.0.md)

> **Reading guide.** Every ML result in this chapter comes from **CPU-baseline models** (20-epoch detector on 118 real cylinders). Tables are labelled **Real** or **Synthetic**. Scoring and calibration numbers are **tooling evidence** under ADR-017 §7 and must be refitted on GPU-trained models. None of them is a claim about operational model quality.

### 8.1 Test strategy and environments

The test plan defines unit, component, integration, API, UI, end-to-end, ML evaluation, robustness, performance, security and usability levels. ML metrics use a site-held-out design: tune on `val`, calibrate on `calib`, and evaluate only release candidates on the frozen test set TD-08, with 95% bootstrap CIs ([Test Plan §6.1](../testing/TEST_PLAN.md)).

| Environment | Planned | Used so far |
|---|---|---|
| Dev laptop | Windows 11 / Ubuntu, ≥ 16 GB | Windows 11, Intel i5-13420H (8 cores / 12 threads), 16 GB, CPU only; conda `sonarsentinel` with torch 2.14.0+cpu, onnxruntime 1.30.0, ultralytics 8.4.150, lightgbm 4.7.0 |
| CI | GitHub Actions `ubuntu-latest` | GitHub Actions Ubuntu + Windows; CI-equivalent venv without torch, ultralytics or lightgbm |
| Frontend | Browsers (Chrome, Firefox, Edge) | Node 22 + Vitest 2 with jsdom; no real-browser run |
| GPU workstation (RTX 3060-class) | NFR-01, ML evaluation | **Not available** |
| CPU reference (8-core, idle) | NFR-02 | Dev laptop with other work running |
| Edge (Jetson Orin) | NFR-03, AC-09 | **Not available** |
| Offline workstation | AC-10 | Not yet run |

### 8.2 Functional testing results

**Automated suites (latest recorded run, TSR-M5):** backend 320 tests passed (CI-equivalent venv: 316 passed, 3 skipped), ML tooling 28 passed, frontend 50 Vitest tests passed. ruff lint and format are clean, strict mypy is clean on 64 source files, the frontend lint, typecheck and build pass, and the documentation check reported 0 problems.

| Area | Sprint | Executed | Passed | Failed | Blocked / manual |
|---|---|---|---|---|---|
| TC-CONF (confidence) | 4 | 8 of 10 | 8 | 0 | TC-CONF-005 (needs TD-13), TC-CONF-009 (needs TD-11) |
| TC-REP (reports) | 4–5 | 9 of 9 | 8 | 0 | TC-REP-002 partial (no TD-02); QGIS/Google Earth viewer checks manual |
| TC-API | 4–5 | 8 of 9 | 8 | 0 | TC-API-009 not run (schemathesis not installed) |
| TC-GEO (Sprint 4–5 items) | 4–5 | 4 | 4 | 0 | QGIS overlay manual |
| TC-WS (WebSocket) | 5 | 4 of 6 | 4 | 0 | TC-WS-002/003 timing on TD-02 manual |
| TC-UI (dashboard) | 4–5 | 10 + TC-UI-014 | 10 + 1 | 0 | TC-UI-010 (axe, screen reader) manual |
| TC-E2E | 5 | 3 (API level) | 3 | 0 | Browser end-to-end runner not installed |
| TC-EDGE-001 / TC-PERF-002 | 5 | 2 | 1 + 1 indicative | 0 | TC-PERF-002 extrapolated |
| TC-ING, TC-PRE, TC-GEO-001…008, TC-DET | 1–3 | Automated in CI as recorded in TODO | — | — | TC-ING-006 local only (DVC data); TC-DET-005 needs labelled real anomalies |

**Acceptance criteria:**

| AC | Result | Evidence / note |
|---|---|---|
| AC-01 Geotagged XTF → track, streaming markers, CSV = JSON | **Pass (API + UI units)** | TC-E2E-001, TC-UI-003; browser run on TD-02 not done |
| AC-02 Image without GPS → pixel view, `NOT_GEOTAGGED` | **Pass (API + UI units)** | TC-E2E-003, TC-UI-009 |
| AC-03 Image + CSV → geotagged, `GPS_INTERPOLATED` | **Pass (API level)** | TC-E2E-002 |
| AC-04 Confidence/tiers; slider | **Pass** | TC-CONF-001/002, TC-UI-004 |
| AC-05 Ghost-net recall ≥ 80%; `unknown_anomaly` with heatmap | **Fail / blocked** | No GPU-trained detector (ST-051); anomaly overlay available in the drawer chip |
| AC-06 Robustness | **Pass (synthetic faults)** | 10% zeroed pings + truncation, GPS gap, roll, no altitude, speckle: valid reports with ranged warnings, all targets kept; corrupt header fails cleanly ([robustness report](../testing/reports/ROBUSTNESS_2026-09-14.md)) |
| AC-07 JSON validates; CSV in Excel; GeoJSON in QGIS; KML in Google Earth | **Partial** | All formats generated and structure-tested; viewer checks not done |
| AC-08 ≥ 50% shadow-only FPs demoted | **Blocked** | **[PENDING: curated confuser set TD-13 — TC-CONF-005]** |
| AC-09 INT8 within 3 mAP points, NFR-03 on device | **Not run** | **[PENDING: Jetson hardware — ST-101 / TC-DET-009]** |
| AC-10 Offline | **Partial** | Offline MBTiles basemap, tiles endpoint and settings switch built and tested (ST-099); network-off run with monitoring (TC-E2E-005, TC-SEC-006) not done |

**Gates:** G2 thin slice passed in CI. **G3 (model quality) No-go** (TSR-M4) and **G4 (P0 complete) No-go** (TSR-M5); development continued under documented waivers. **G5 (release candidate) No-go** ([TSR-M6](../testing/reports/TSR-M6.md)): model quality, charted-wreck validation, NFR-04/05, usability and rehearsals are open, so `v1.0.0-rc1` was not tagged.

**Security testing (TC-SEC-004 baseline, before Sprint 6 upgrades).** `pip-audit` on the development environment (202 packages) found 12 advisories in 2 packages. The `gdal` 3.12.3 advisories concern the HDF4/HDF-EOS and netCDF drivers, which the API cannot reach because uploads accept only TIFF/PNG/JPEG/XTF magic bytes. `diskcache` 5.6.3 is reached only through developer DVC tooling. `npm audit` found 7 packages with advisories (1 critical, 1 high, 5 moderate). All are development tools (vitest, vite, esbuild) except react-router (moderate, low impact: internal constant links, no SSR). **Sprint 6 results.** After upgrading vite, vitest and react-router-dom, `npm audit` reports 0 vulnerabilities; CI now runs `pip-audit`, `npm audit --audit-level=critical` and a Trivy scan of both images that fails on critical findings. TC-SEC-001 (both `../` and `..\` names stored as `uploads/<survey>/evil.xtf`), TC-SEC-002 (PNG renamed `.xtf` rejected with 422 `CORRUPT_HEADER`) and TC-SEC-003 (413 without writing past the limit) are automated in `test_security.py`; the CLI and Compose files bind to 127.0.0.1 (TC-SEC-005, LAN scan still manual). TC-SEC-006 (no external calls offline) is not run. Details: [TSR-M6](../testing/reports/TSR-M6.md).

### 8.3 Detection performance (Real)

Model `detector/yolo11s-seg-sonar-real@0.1.0`, evaluated on the site-2017 validation split (93 images, 28 cylinders) with `ml/evaluate.py` (101-point AP, IoU 0.5, 200 bootstrap resamples over images) ([EXP-20260913-baseline §5](../../ml/experiments/EXP-20260913-baseline.md)):

| Metric | Value |
|---|---|
| mAP@50 (box) | **0.283** (95% CI 0.174–0.456) |
| mAP@50 (mask) | 0.280 |
| Precision / recall at conf 0.25 | 0.375 / 0.429 |
| Confusion at conf 0.25 | 12 cylinders found, 16 missed, 20 false positives on 93 images |
| Ultralytics' own final-epoch validation (different PR interpolation) | box P 0.343, R 0.393, mAP@50 0.329, mAP@50-95 0.140; mask mAP@50 0.302, mAP@50-95 0.068 |

| Class | Precision | Recall | AP@50 | Objects |
|---|---|---|---|---|
| cylinder | 0.375 | 0.429 | 0.283 | 28 |
| shipwreck, pipe, ghost_net, debris_other | — | — | — | 0 (no training data) |

**Sliced inference (TC-DET-004, Real, validation):** recall at IoU 0.5 rose from 0.43 to 0.50 for all 28 objects. For the 18 small objects (longest side < 32 px) it rose from 0.33 to 0.39 (6 → 7 found). CPU time grew from 0.26 to 1.65 s per image. The small-object gain is a single extra hit, within noise.

**Interpretation:** validation mAP@50 swung between 0.20 and 0.35 over the last ten epochs, because with 28 objects each hit moves AP by several points. This is a pipeline baseline, not a measure of what YOLO11-seg can do on sonar. The frozen test set (TD-08: 120 images, 242 cylinders) was deliberately not used.

- Test-set metrics: **[PENDING: frozen test set TD-08 evaluation of a GPU-trained release candidate — ST-051/ST-055]**
- `shipwreck` + `cylinder` recall: **[PENDING: AI4Shipwrecks conversion — ST-010; GPU training — ST-051]**
- PR curves and confusion figure: **[PENDING: export Fig. 4 from `eval_val/` — ST-116]**

### 8.4 Ghost-net and anomaly detection results

**Detector on the synthetic ghost-net holdout (Synthetic, TD-09: 200 tiles on unseen site-2017 backgrounds, 329 nets).** The baseline detector's ghost-net recall is **0.00**, as expected with no ghost-net training data. 37 nets were detected as `cylinder`, 292 were missed, and there were 158 `cylinder` false positives on 200 images. The synthetic-data model trained on 525 images (250 synthetic ghost-net tiles with 440 nets) completed only epoch 1, whose val mAP@50 of 0.065 says nothing about the hypothesis. **[PENDING: ghost-net holdout recall of the synthetic-data detector — GPU training ST-051; R1 trigger check → ST-055]**

**PatchCore anomaly model (normals Real, positives Synthetic).** On held-out site 2017: 171 real normal tiles against 400 synthetic positives (ghost-net holdout plus synthetic pipes) ([EXP-20260913-patchcore §5](../../ml/experiments/EXP-20260913-patchcore.md)):

| Metric | Value |
|---|---|
| Tile AUROC | **0.957** |
| Recall at tile threshold (p99 of normals, 3.380) | 0.74 |
| False-alarm rate on held-out normals | 1.2% |
| Training time (CPU) | 3.7 min |

Two cautions apply. The positives are synthetic, so real-world recall is unknown. Pipe tiles come from the generator's train split, whose backgrounds are not restricted to the held-out site, so the ghost-net holdout is the cleaner test. On the real USGS Klein 3900 line, the memory bank contains no Klein seabed, so anomaly scores there are out of distribution and not trustworthy.

**Demo asset A3 (Synthetic net on real seabed, fictional track).** Default models found 19 detections in 7 s. The only detection within 5 m of the net was a `cylinder` at 15.2% confidence (`hidden` tier), 2.6 m from the true position. The other 18 were seabed ripples and water-column edges 15–40 m away, all low confidence ([demo README](../../demo/README.md)). The demo therefore shows pipeline and geotagging on a synthetic target, not ghost-net detection.

**Real ghost-net samples:** none. **[PENDING: real ghost-net SSS samples from NIOT/WWF/GhostNetZero (PRD Q6)]**

### 8.5 False-positive reduction

The FP/km² target needs contact-free survey lines (TD-11), which do not exist, so the before/after comparison has not been run. **[PENDING: FP/km² detector-only vs. full scoring on TD-11 — TC-CONF-009]** What has been measured is ranking quality on Real validation detections of the CPU baseline ([EXP-20260913-scoring §5.1–5.2](../../ml/experiments/EXP-20260913-scoring.md)):

| Measurement (Real, val, 137 detections / 20 TP on 42 images) | Value |
|---|---|
| AUROC, detector score alone | 0.692 |
| AUROC, LightGBM FP filter (out of fold) | **0.747** |
| AP over 28 objects, detector score alone | 0.246 |
| AP, fused with configured weights (0.45 / 0.15 / 0.15 / 0.15 / 0.10) | **0.251** |
| AP, fused with best grid weights (detector 0.20, shadow 0.00, FP filter 0.55) | 0.278 |

The top SHAP features were ring texture similarity (0.88), detector score (0.54), FFT peak ratio (0.39), ripple FFT peak (0.36) and GLCM homogeneity (0.34). Texture and context features matter more than geometry at this stage. The grid search dropped the shadow weight to 0, but the shadow side and altitude are unknown on these tiles, and with 20 positives the gain is within noise, so the configured weights were kept. The shadow unit tests pass on synthetic data: an object with a shadow beats a shadow-only patch by ≥ 0.3 (TC-CONF-004), and a 1 m synthetic object's height is estimated within ±30% on both sides (TC-CONF-006). **[PENDING: AC-08 on 50 curated shadow/rock false positives — TD-13 / TC-CONF-005]**

**Ablation table**

| Configuration | mAP@50 | Ghost-net recall | FP/km² | ECE |
|---|---|---|---|---|
| Detector only (real data) | 0.283 (95% CI 0.174–0.456), val, Real | 0.00 (TD-09, Synthetic) | **[PENDING: TD-11 — TC-CONF-009]** | — (identity calibrator) |
| + synthetic data | **[PENDING: GPU training — ST-051]** | **[PENDING: GPU training — ST-051]** | **[PENDING: TD-11 — TC-CONF-009]** | **[PENDING: GPU training — ST-051]** |
| + SAHI | **[PENDING: mAP with SAHI — ST-052 rerun on GPU model]**¹ | **[PENDING: GPU training — ST-051]** | **[PENDING: TD-11 — TC-CONF-009]** | — |
| + shadow check | **[PENDING: GPU training — ST-051]** | **[PENDING: GPU training — ST-051]** | **[PENDING: TD-11 — TC-CONF-009]** | — |
| + FP filter | **[PENDING: GPU training — ST-051]**² | **[PENDING: GPU training — ST-051]** | **[PENDING: TD-11 — TC-CONF-009]** | — |
| + calibration (full system) | **[PENDING: TD-08 release candidate — ST-051]** | **[PENDING: GPU training — ST-051]** | **[PENDING: TD-11 — TC-CONF-009]** | 0.048 (95% CI 0.027–0.080)³ |

¹ SAHI was compared by recall only: 0.43 → 0.50 (all objects) on validation (TC-DET-004).
² FP-filter AUROC 0.747 vs. 0.692 for the detector score, and fused AP 0.251 vs. 0.246 (CPU-baseline tooling run, EXP-20260913-scoring). These are ranking metrics on validation detections, not mAP@50.
³ ECE of the fused score after isotonic calibration on the calib split, out of fold, CPU-baseline tooling run (EXP-20260913-scoring). Refit required on the GPU-trained detector.

### 8.6 Calibration results (Real, CPU-baseline tooling)

Calib split (site 2021): 402 detections, 33 true positives, on 48 images. ECE of the fused score was **0.144 before** and **0.048 after** isotonic calibration, out of fold (95% CI 0.027–0.080), which meets the ≤ 0.10 target as tooling evidence (TC-CONF-008).

| Bin | Detections | Mean predicted | Observed |
|---|---|---|---|
| 0.0–0.1 | 288 | 0.048 | 0.052 |
| 0.1–0.2 | 77 | 0.132 | 0.234 |
| 0.2–0.3 | 29 | 0.217 | 0.000 |
| 0.3–0.4 | 6 | 0.342 | 0.000 |
| 0.9–1.0 | 2 | 1.000 | 0.000 |

The low ECE mostly reflects a calibrator that is honest about a weak detector. Only about 8% of baseline detections are true, so almost every calibrated confidence is below 40 and falls in the `hidden` tier. The two detections in the top bin are false positives that the isotonic fit on other folds mapped to 1.0, a sign of too little data at high scores (D-M4-02). On the real USGS line, all 414 detections were `hidden` (Section 8.9). Reliability diagram: **[PENDING: export Fig. 5 — ST-116]**. Refit: **[PENDING: calibrator refit on GPU-trained detector, ECE on TD-08 — ST-051/ST-064]**

### 8.7 Geolocation accuracy

**Synthetic and reference checks (all pass):**

| Check | Result | Test |
|---|---|---|
| Pixel → lat/lon, straight and curved golden tracks, both sides | < 0.05 m | TC-GEO-001…003 |
| Degree vs. UTM copies of the same track | < 0.1 m | TC-ING-007, TC-ING-008 |
| Circular heading smoothing 358°…2° | → 0° | TC-GEO-004 |
| (0, 0) fix plus 500 m jump interpolated | < 5 cm, `GPS_INTERPOLATED` | TC-GEO-005 |
| End to end after S2–S7 on curved TD-01 targets | within 0.15 m | ST-042 |
| GeoTIFF pixel centres vs. rasterio | < 1 µm | TC-ING-009 |
| Layback: 100 m cable, 20 m depth | 97.98 m astern, `LAYBACK_ESTIMATED` | TC-GEO-009 |
| Heading uncertainty term at 50 m range, 2° | 1.745 m | TC-GEO-010 |
| Mosaic GCP residual, curved synthetic track | 0.20 m mean, 0.32 m max | TC-GEO-011 |
| Two synthetic lines merged | `n_views = 2`, persistence 0.75 | TC-GEO-013 |

**Real data:** the XTF reader agrees with pyxtf on positions, heading and slant range for 10 pings in each of the 4 USGS lines, and all tracks lie within the survey's metadata bounding box. On demo asset A3 (synthetic target, self-consistent idealised geometry), the nearest detection was 2.6 m from the true position. This is not a real-world accuracy figure.

**Charted-wreck error (median, max) and reciprocal-line offsets:** **[PENDING: survey over a charted wreck and validation report — ST-037 / TC-GEO-012]**

### 8.8 Robustness results

`scripts/robustness_suite.py` (ST-111, [robustness report](../testing/reports/ROBUSTNESS_2026-09-14.md)) runs eight variants of a synthetic line with three targets through the CLI and `run_pipeline` using the rule-based detector. Seven fault variants (10% zeroed pings with a truncated record, 30 s GPS gap, ±10° roll, no altitude, heavy speckle, truncation) complete with schema-valid reports, CLI exit 0, the expected warnings (15 ranged `DROPOUT` events, 18 `HIGH_MOTION` events) and all three targets; a corrupt header fails with `CORRUPT_HEADER` and exit 1. The suite exposed and fixed two defects: a GPS gap across a chunk border collapsed pings and lost targets (now interpolated over the whole line before chunking), and zeroed pings saturated gain normalisation (now excluded from the statistics). Chunk retry with `CHUNK_SKIPPED` and `CPU_FALLBACK` are unit-tested. Component tests from earlier sprints:

- Truncated XTF final records are recovered with `TRUNCATED_FILE` (reader; TC-ING-012 automated).
- Dropout detection finds ≥ 95% of injected zeroed or frozen pings; gaps ≤ 3 pings are inpainted and longer ones masked (TC-PRE-008).
- Motion flags are set exactly on pings over threshold, with yaw rate wrapping at 360° (TC-PRE-009).
- The dropout penalty lowers the fused score, and the `DROPOUT` flag is set when rows overlap a dropout (TC-CONF-007 scoring rule). An end-to-end fixture with a target inside a dropout is still missing (D-M4-04).
- A failing job emits `error` and ends `failed` (TC-WS-006).

Detection metrics under injected noise: **[PENDING: TD-08 with injected faults — TC-DET-008]**

### 8.9 Performance

Measured on the dev laptop (i5-13420H, 16 GB, Windows 11, CPU only), mostly while other development work was running. Sprint 6 benchmarks with `scripts/benchmark.py` ([benchmark report](../testing/reports/BENCHMARK_2026-09-14.md)), ONNX Runtime on CPU with the default pipeline:

| Benchmark | Synthetic 1 km (3 runs) | USGS Klein 3900, 0.444 km (1 run) | Target |
|---|---|---|---|
| Seconds per km (NFR-02) | 53.9 (median) | 240.5 | ≤ 300 |
| First detection (NFR-04) | 53.8 s | 106.8 s | ≤ 15 s — **fail** |
| Largest progress gap (NFR-05) | 12.0 s | 60.7 s | ≤ 5 s — **fail** |
| Peak memory (NFR-07) | 985 MB | 1,027 MB | ≤ 8 GB |

NFR-04 and NFR-05 fail because detections are sent only after all chunks are merged and progress once per chunk. Earlier measurements:

| Measurement | Result | Source |
|---|---|---|
| Detector latency per 640 px tile, idle CPU: PyTorch → ONNX Runtime | 169.9 → 149.6 ms (about 12% faster) | EXP-20260914-onnx |
| Same, with other work running | 224.6 → 194.4 ms | EXP-20260914-onnx |
| ONNX parity on 93 validation tiles (TC-EDGE-001) | 38/38 matched, 0 score mismatches, 0 extra | EXP-20260914-onnx |
| Full `sonarsentinel detect` (ONNX + SAHI, PatchCore, FP filter, calibrator, chips, mosaic, JSON/CSV) on a 0.444 km USGS Klein 3900 line (33 MB) | 97.5 s (102 s wall clock) ≈ **220 s per km**; 414 detections, all `hidden` | EXP-20260914-onnx; TC-PERF-002 indicative |
| Earlier Sprint 3 run of `detect` on a real USGS line (PyTorch, before scoring stage) | 192 s | TODO, M3 exit |
| SAHI vs. full image per validation image (CPU) | 1.65 s vs. 0.26 s | EXP-20260913-baseline |
| Reading a 2.0 GB synthetic XTF | 6 s; peak private memory 91 MB; peak working set 2.1 GB | ST-026 |
| Feature extraction per detection | median < 5 ms | ST-061 |
| Dashboard filter update, 2,000 detections (jsdom) | < 100 ms | TC-UI-004 |
| Demo A3 image + nav CSV end to end | 7 s, 19 detections | demo README |
| Model sizes | `best.pt` 19.6 MB; `best.onnx` 38.7 MiB | Model card; EXP-20260914-onnx |
| Training / fitting (CPU) | detector 0.80 h (20 epochs); PatchCore 3.7 min; FP filter + fusion + calibration 39 s; ONNX export 6 s | Experiment logs |

- TC-PERF-002 extrapolates one 0.444 km line to 1 km on a busy laptop. The formal check requires a 1 km reference line on an idle 8-core CPU; ADR-019 §8 substitutes a labelled synthetic 1 km line.
- NFR-06 (FP32 ≤ 25 MB): the PyTorch weights meet it; the ONNX export is larger.
- NFR-01 GPU timing: **[PENDING: GPU workstation — ST-112 / TC-PERF-001]**
- NFR-03 Jetson real-time factor and INT8 impact: **[PENDING: Jetson hardware — ST-101 / TC-PERF-003, TC-DET-009]**
- NFR-04 and NFR-05 fail (table above); NFR-07 measured on the benchmark lines, not on a full 2 GB pipeline run. Map frame rate with 2,000 markers still needs a real browser.

### 8.10 Usability evaluation

No usability test has been run. The protocol ([Test Plan §6.7](../testing/TEST_PLAN.md)) uses ≥ 3 new users on four tasks (upload and start, find and copy a detection, hide detections below 60%, download CSV) plus a review task. Targets are ≥ 80% task success, median ≤ 5 min and SUS ≥ 70 (TC-USE-001), plus 20 review items in ≤ 3 min (TC-USE-002).

- Task success, times, SUS and feedback: **[PENDING: usability test with ≥ 3 new users — ST-113 / TC-USE-001]**
- Analyst time saved vs. manual review: **[PENDING: timed comparison — ST-113]**
- Accessibility (axe, screen reader): **[PENDING: TC-UI-010 manual check]**

### 8.11 Comparison with targets

| PRD §11 metric | Target | Achieved | Data | Status |
|---|---|---|---|---|
| Detection mAP@50 (real test set, all known classes) | ≥ 0.70 | 0.283 (95% CI 0.174–0.456) on **val**, `cylinder` only | Real | **Not met** (CPU baseline); test set **[PENDING: TD-08 — ST-051]** |
| Recall on `shipwreck` + `cylinder` | ≥ 0.85 | `cylinder` 0.429 at conf 0.25 (val); `shipwreck` no data | Real | **Not met**; **[PENDING: ST-010, ST-051]** |
| Ghost-net recall (synthetic holdout) | ≥ 0.80 | 0.00 (detector without ghost-net data) | Synthetic | **Not met**; **[PENDING: GPU training — ST-051]** |
| FP per km² after filtering | ≥ 50% reduction | Not measured; FP-filter AUROC 0.747 vs. 0.692 (val) | Real | **[PENDING: TD-11 — TC-CONF-009]** |
| Calibration ECE | ≤ 0.10 | 0.048 (95% CI 0.027–0.080) on calib, out of fold | Real | **Met as tooling evidence**; refit needed |
| Geolocation error vs. charted wrecks | Median ≤ 10 m | Synthetic golden < 0.05 m; real not measured | Synthetic | **[PENDING: ST-037 / TC-GEO-012]** |
| Processing speed NFR-01 (GPU) | ≤ 60 s per km | Not measured (no GPU) | — | **[PENDING: GPU workstation — TC-PERF-001]** |
| Processing speed NFR-02 (CPU) | ≤ 5 min per km | 240.5 s per km (0.444 km real line); 53.9 s on a synthetic 1 km line | Real + Synthetic | **Pass** (real line extrapolated; busy laptop) |
| Processing speed NFR-03 (edge) | ≥ 1× acquisition (target ≥ 5×) | Not measured | — | **[PENDING: ST-101]** |
| Analyst time saved | ≥ 70% | Not measured | — | **[PENDING: ST-113]** |
| Usability: first report downloaded | ≤ 5 min | Not measured | — | **[PENDING: ST-113 / TC-USE-001]** |

---

## Chapter 9 — Discussion

### 9.1 Interpretation of results

The **software path is complete and well tested**. A raw XTF, GeoTIFF or image with navigation becomes a schema-valid report with positions, dimensions, calibrated confidences and quality flags, streamed live to a dashboard and exported in four formats. AC-01 to AC-04 pass at API and component level, and ONNX Runtime reproduces PyTorch exactly. The **models are not yet good enough** to judge the approach. The detector saw 118 real cylinders for 20 CPU epochs and has never seen a ghost net, wreck, pipe or debris item, so its 0.283 validation mAP@50 and 0.00 ghost-net recall measure the training budget, not the architecture. The scoring stage behaves as designed on weak inputs. The learned filter ranks true positives better than the detector score (AUROC 0.747 vs. 0.692), and the calibrator reports low confidences for a detector that is mostly wrong. That is correct behaviour, but it means real surveys currently produce almost only `hidden` detections. PatchCore's 0.957 tile AUROC is encouraging for the "unknown object" safety net, but it was measured against synthetic positives on the same sonar family as its memory bank.

### 9.2 Limitations

- **CPU-only baselines.** No model has been trained on a GPU. The schedule (20 epochs, batch 8) is a tenth of the design schedule (200 epochs, batch 16).
- **Tiny training set.** 118 real cylinders from two sites of one sonar (Marine Sonic on a Gavia AUV); one class; NOMBO objects unreviewed and partly unlabelled background.
- **No real ghost-net data.** All ghost-net evidence is synthetic, and the generator's realism has not been rated. Synthetic results cannot show transfer to real nets (risk R1 in PRD §14).
- **One real survey.** Only USGS Grand Bay 2015 (Klein 3900, shallow estuary) was used for real XTF work. Its altitude records are invalid, it has no charted wreck, and PatchCore has no Klein seabed in its memory bank.
- **Mostly `hidden` detections on real seabed.** With the CPU-baseline calibrator, all 414 detections on the real line and the demo net fall in the `hidden` tier.
- **Scoring artefacts fitted on few positives.** 20 TPs for the FP filter and fusion weights, 33 for the calibrator. The top reliability bin holds 2 false positives.
- **Positioning assumptions.** Layback ignores the along-track time lag and cable sag. Uncertainty defaults are generic, not equipment-specific. The D2 background resolution of 0.10 m/px is assumed, not measured.
- **Hardware not tested.** No GPU workstation, Jetson, Docker host or real browser has been used. Throughput is extrapolated from a shorter line on a busy laptop.
- **Engineering deviations.** A single thread worker instead of process workers; the multi-line mosaic keeps only the last line (D-M5-02); cancelled jobs have no downloadable report (D-M5-03); undo does not reverse a reclassification (D-M5-04); validation uploads large files twice (D-M4-03).

### 9.3 Threats to validity

- **Dataset size.** With 28 validation objects, one hit or miss moves AP by several points (CI 0.174–0.456), and the SAHI small-object gain is a single object.
- **Test-set representativeness.** Validation, calibration and test are single sites of one sonar and one object type. Indian coastal seabeds and survey sonars are not represented (risk R2).
- **Synthetic backgrounds and splits.** The Datasets guide records that synthetic training tiles use backgrounds from sites 2010, 2015, 2018 and 2021, which include the test site (2015) and the calib site (2021). The leakage check (site membership of real images and thumbnail correlation) passed, but reusing background pixels from those sites in training should be checked before test or calibration results on 2015/2021 are reported.
- **Chart position accuracy.** When ST-037 runs, charted wreck positions carry their own errors, which older records can put at tens of metres (Datasets D9). Chart quality attributes must be reported with the error.
- **Measurement conditions.** Latency and throughput were measured with other applications running. ADR-019 §8 addresses this with medians of three runs in separate processes.
- **Metric implementation.** `ml/evaluate.py` and Ultralytics interpolate PR curves differently (0.283 vs. 0.329 mAP@50 on the same weights). The project reports `evaluate.py` values consistently.

### 9.4 Ethical, safety and environmental considerations

SonarSentinel supports human review. It does not take autonomous action, and tiers and the review queue keep an analyst in the loop. Outputs from NOAA-derived data carry a "not for navigation" notice, and reports are not IHO chart products. Victim images are excluded, as are datasets without licences. Mine-like objects are training targets, but the system is not a mine-countermeasure tool. Environmentally, the aim is to cut dive time and speed up removal of ghost gear. A false sense of coverage is the main safety risk, so missed detections and low confidences must be communicated as clearly as positive results, which is why `hidden` detections remain available via the slider. AGPL-3.0 keeps modified network deployments open. ADR-013 says the licence must be revisited before any NIOT production deployment.

### 9.5 Lessons learned

- **Build the thin slice early.** A rule-based stand-in detector and identity calibrator let CI, the mock API and the dashboard progress before any model existed.
- **Real files break assumptions that synthetic tests pass.** The Klein data exposed the port-order and altitude problems.
- **Label evidence honestly.** Separating tooling evidence (ADR-017 §7) from model quality kept the gate decisions (G3, G4 No-go) credible.
- **Hardware is a schedule risk.** A 16 GB CPU laptop could not finish a 525-image training run while other work was running. GPU access (Kaggle/Colab, Developer Setup §9) should have been arranged before Sprint 3.
- **Data dependencies move slowest.** Items needing external data, people or permissions (AI4Shipwrecks, charted wreck, labelling, NIOT samples) were carried through up to six phases while code stories closed in hours.

---

## Chapter 10 — Conclusion and Future Work

### 10.1 Summary of achievements against objectives

| Goal | Achieved | Open |
|---|---|---|
| G1 Detect and localise debris with high recall | End-to-end detection, segmentation, sliced inference, merging and geotagging; CPU-baseline detector val mAP@50 0.283 | GPU-trained multi-class detector **[PENDING: ST-051]** |
| G2 Ghost nets without real examples | Synthetic generator (2,000 + 200 tiles), PatchCore tile AUROC 0.957 against synthetic positives, `unknown_anomaly` path | Synthetic-trained detector recall **[PENDING: ST-051]**; realism **[PENDING: ST-018]**; real samples |
| G3 Fewer false positives, trustworthy confidence | Shadow score, 36 features, LightGBM filter (AUROC 0.747), fusion, isotonic calibration (ECE 0.048, tooling), tiers and breakdown | FP/km² **[PENDING: TC-CONF-009]**; AC-08 **[PENDING: TD-13]**; refit on GPU model |
| G4 Exact location, dimensions, class in structured formats | WGS84 6 dp, footprint, dimensions, depth, layback, uncertainty; JSON/CSV/GeoJSON/KML; synthetic geotagging < 0.05 m | Charted-wreck error **[PENDING: ST-037]**; viewer checks (AC-07) |
| G5 Upload and watch detections live | Upload, WebSocket streaming with resume, live map, filters, drawer, review queue, history and settings, exports; 69 frontend tests | Browser frame rate, screenshots, usability **[PENDING: ST-113]** |
| G6 Efficient edge operation without cloud | ONNX parity 38/38; 240 s per km on laptop CPU; Docker images built and scanned in CI; watch mode with compact alerts; offline MBTiles basemap | Jetson **[PENDING: ST-101]**; NFR-04/05 streaming fixes; GPU timing |

### 10.2 Impact for MoES/NIOT and disaster management

For NIOT, SonarSentinel offers an open, auditable pipeline that runs on existing workstations without cloud services. It turns raw survey logs into ranked, georeferenced contact lists that load directly into QGIS, Google Earth and chart software. After cyclones or floods, port and disaster authorities could get a hazard summary within minutes of a survey line instead of after manual review. That impact depends on retraining with representative data and on the geolocation and usability validation still pending. With the current CPU-baseline models, results should be treated as leads for expert review only.

### 10.3 Future work

1. **Complete model training on GPU:** the synthetic ablation, the small-object variant if ghost-net recall is low, the mask refiner, and refitting of the FP filter and calibrator. Then evaluate once on the frozen test set.
2. **NIOT data validation:** fine-tune and validate on survey logs from Indian waters and the sonar models NIOT uses (PRD Q1, Q2), including domain adaptation of the PatchCore memory bank per sonar family.
3. **Real ghost-net dataset:** obtain and label real samples (NIOT, WWF/GhostNetZero, MARELITT), feed confirmed detections from the label store back into training, and publish a benchmark if licences allow.
4. **Geolocation validation:** charted-wreck surveys and reciprocal lines; the along-track time lag in layback correction.
5. **Adaptive AUV missions:** automatic re-survey of anomalies using the edge watch mode and compact alerts.
6. **Change detection** between repeat surveys ("new debris since last survey").
7. **Multibeam fusion** with bathymetry and backscatter.
8. **More formats:** EdgeTech JSF, Lowrance SL2/SL3 (ST-025) and Humminbird via PINGMapper.
9. **Deployment:** TensorRT/OpenVINO INT8 on target devices, PostGIS for a central archive, and authentication and roles.

---

## References

IEEE style. References [1]–[3], [8], [11] and [19]–[24] were verified against primary records on 2026-09-13 ([Literature Review](../research/LITERATURE_REVIEW.md#references)). The others are standard method references whose page numbers must be spot-checked before submission. **[PENDING: verify references 4–7, 9, 10, 12–18 and 25–35 — ST-116]**

[1] G. Macfadyen, T. Huntington, and R. Cappell, *Abandoned, Lost or Otherwise Discarded Fishing Gear*, UNEP Regional Seas Reports and Studies No. 185; FAO Fisheries and Aquaculture Technical Paper No. 523. Rome, Italy: UNEP/FAO, 2009.

[2] K. Richardson, B. D. Hardesty, and C. Wilcox, "Estimates of fishing gear loss rates at a global scale: A literature review and meta-analysis," *Fish and Fisheries*, vol. 20, no. 6, pp. 1218–1231, 2019, doi: 10.1111/faf.12407.

[3] Z. Miao *et al.*, "GhostNetZero: AI for detecting marine ghost nets," Microsoft AI for Good Lab, Sep. 2025. Preprint: *EcoEvoRxiv*, 2025, doi: 10.32942/X2S061.

[4] P. Blondel, *The Handbook of Sidescan Sonar*. Springer/Praxis, 2009.

[5] X. Lurton, *An Introduction to Underwater Acoustics: Principles and Applications*, 2nd ed. Springer, 2010.

[6] J.-S. Lee, "Digital image enhancement and noise filtering by use of local statistics," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 2, no. 2, 1980.

[7] V. S. Frost, J. A. Stiles, K. S. Shanmugan, and J. C. Holtzman, "A model for radar images and its application to adaptive digital filtering of multiplicative noise," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 4, no. 2, 1982.

[8] S. Reed, Y. Petillot, and J. Bell, "An automatic approach to the detection and extraction of mine features in sidescan sonar," *IEEE J. Ocean. Eng.*, vol. 28, no. 1, pp. 90–105, Jan. 2003, doi: 10.1109/JOE.2002.808199.

[9] R. M. Haralick, K. Shanmugam, and I. Dinstein, "Textural features for image classification," *IEEE Trans. Syst., Man, Cybern.*, vol. SMC-3, no. 6, 1973.

[10] G. Ke *et al.*, "LightGBM: A highly efficient gradient boosting decision tree," in *Proc. NeurIPS*, 2017.

[11] Y. Steiniger, D. Kraus, and T. Meisen, "Survey on deep learning based computer vision for sonar imagery," *Eng. Appl. Artif. Intell.*, vol. 114, Art. no. 105157, Sep. 2022, doi: 10.1016/j.engappai.2022.105157.

[12] J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, "You only look once: Unified, real-time object detection," in *Proc. IEEE/CVF CVPR*, 2016.

[13] Ultralytics, "YOLO11 documentation and software." [Online]. Available: https://docs.ultralytics.com

[14] S. Ren, K. He, R. Girshick, and J. Sun, "Faster R-CNN: Towards real-time object detection with region proposal networks," in *Proc. NeurIPS*, 2015.

[15] K. He, G. Gkioxari, P. Dollár, and R. Girshick, "Mask R-CNN," in *Proc. IEEE ICCV*, 2017.

[16] O. Ronneberger, P. Fischer, and T. Brox, "U-Net: Convolutional networks for biomedical image segmentation," in *Proc. MICCAI*, 2015.

[17] A. Kirillov *et al.*, "Segment anything," in *Proc. IEEE/CVF ICCV*, 2023.

[18] F. C. Akyon, S. O. Altinuc, and A. Temizel, "Slicing aided hyper inference and fine-tuning for small object detection," in *Proc. IEEE ICIP*, 2022.

[19] G. Huo, Z. Wu, and J. Li, "Underwater object classification in sidescan sonar images using deep transfer learning and semisynthetic training data," *IEEE Access*, vol. 8, pp. 47407–47418, 2020, doi: 10.1109/ACCESS.2020.2978880.

[20] A. V. Sethuraman *et al.*, "Machine learning for shipwreck segmentation from side scan sonar imagery: Dataset and benchmark," *Int. J. Robot. Res.*, vol. 44, no. 3, pp. 341–354, Mar. 2025, doi: 10.1177/02783649241266853.

[21] A. V. Sethuraman and K. A. Skinner, "STARS: Zero-shot sim-to-real transfer for segmentation of shipwrecks in sonar imagery," in *Proc. 34th BMVC*, Aberdeen, UK, Nov. 2023, paper 0606.

[22] S. Kamal Basha and A. Nambiar, "S3Simulator: A benchmarking side scan sonar simulator dataset for underwater image analysis," in *Pattern Recognition (ICPR 2024)*, LNCS vol. 15316. Cham, Switzerland: Springer, 2025, pp. 219–235, doi: 10.1007/978-3-031-78444-6_15.

[23] N. Pessanha Santos, R. Moura, G. Sampaio Torgal, V. Lobo, and M. de Castro Neto, "Side-scan sonar imaging data of underwater vehicles for mine detection," *Data in Brief*, vol. 53, Art. no. 110132, 2024, doi: 10.1016/j.dib.2024.110132.

[24] D. Singh and M. Valdenegro-Toro, "The marine debris dataset for forward-looking sonar semantic segmentation," in *Proc. IEEE/CVF ICCVW*, 2021, pp. 3734–3742, doi: 10.1109/ICCVW54120.2021.00417.

[25] K. Roth, L. Pemula, J. Zepeda, B. Schölkopf, T. Brox, and P. Gehler, "Towards total recall in industrial anomaly detection," in *Proc. IEEE/CVF CVPR*, 2022.

[26] K. Batzner, L. Heckler, and R. König, "EfficientAD: Accurate visual anomaly detection at millisecond-level latencies," in *Proc. IEEE/CVF WACV*, 2024.

[27] S. Akcay, D. Ameln, A. Vaidya, B. Lakshmanan, N. Ahuja, and U. Genc, "Anomalib: A deep learning library for anomaly detection," in *Proc. IEEE ICIP*, 2022.

[28] C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in *Proc. ICML*, 2017.

[29] B. Zadrozny and C. Elkan, "Transforming classifier scores into accurate multiclass probability estimates," in *Proc. ACM SIGKDD*, 2002.

[30] A. Niculescu-Mizil and R. Caruana, "Predicting good probabilities with supervised learning," in *Proc. ICML*, 2005.

[31] S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in *Proc. NeurIPS*, 2017.

[32] M. Ester, H.-P. Kriegel, J. Sander, and X. Xu, "A density-based algorithm for discovering clusters in large spatial databases with noise," in *Proc. KDD*, 1996.

[33] "pyxtf — Python library for reading and writing XTF files." [Online]. Available: https://github.com/oysstu/pyxtf

[34] "PINGMapper — open-source software for georeferencing and mapping recreational-grade side-scan sonar." [Online]. Available: https://github.com/CameronBodine/PINGMapper

[35] U.S. Geological Survey, Grand Bay 2015 side-scan sonar data release (Klein 3900), doi: 10.5066/P9374DKQ. **[PENDING: full author list and title from the release record]**

---

## Appendices

| Appendix | Content | Source |
|---|---|---|
| A | Full functional and non-functional requirements | [PRD](../PRD.md) §6–7 |
| B | API specification summary | [05-api-specification](../architecture/05-api-specification.md) |
| C | Report JSON schema and example report | [06-data-models](../architecture/06-data-models.md) |
| D | Test case list and traceability matrix | [TEST_CASES](../testing/TEST_CASES.md) |
| E | Model cards (final models) | Draft: [yolo11s-seg-sonar-real@0.1.0](../../ml/experiments/model_card_yolo11s-seg-sonar-real-0.1.0.md); `models/*/model_card.md` for final models **[PENDING: final model cards after GPU training — ST-051]** |
| F | Annotation guidelines | [ANNOTATION_GUIDELINES](../data/ANNOTATION_GUIDELINES.md) |
| G | User manual (condensed) | [USER_MANUAL](../guides/USER_MANUAL.md), verified against the Sprint 6 build (ST-114); screenshots pending |
| H | Dataset licences and third-party software licences | [LICENSES_AND_COMPLIANCE](../legal/LICENSES_AND_COMPLIANCE.md) |
| I | Team contributions *(who did what, by role and module)* | Project Plan RACI + git history. Roles and module ownership as in the front-matter table and [Project Plan §6](../planning/PROJECT_PLAN.md#6-team-roles-and-responsibilities). **[PENDING: named contributions per member]** |
| J | Glossary | [PRD §18](../PRD.md#18-glossary) |

---

## Report quality checklist

- [ ] Every number in the report comes from a recorded test run or reference (link or appendix). *Draft: numbers taken only from TSR-M4, TSR-M5, the dependency scan, experiment logs, the model card, the manifest statistics, the CHANGELOG, TODO evidence notes and the demo README; re-check after the pending results are filled in.*
- [x] Synthetic vs. real results clearly separated. *Every Chapter 8 table is labelled Real or Synthetic.*
- [ ] Figures have captions, units, and sources; diagrams readable in print. *Figures not yet exported.*
- [x] Limitations stated honestly. *Chapter 9.2–9.3; team review still needed.*
- [ ] No sensitive data (restricted survey locations, human remains) in figures. *Check when figures are exported.*
- [ ] References verified and consistently formatted. *[4]–[7], [9], [10], [12]–[18], [25]–[35] pending verification.*
- [ ] Proofread by at least two team members
- [ ] Exported to PDF with embedded fonts
