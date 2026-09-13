# 08 · Architecture Decision Records (ADRs)

[← Architecture index](README.md)

Format: **Context → Decision → Alternatives considered → Consequences**. Status is *Accepted* unless noted.

---

## ADR-001 · Python backend with FastAPI

- **Context:** The sonar I/O, geospatial and ML ecosystems (pyxtf, GDAL, pyproj, PyTorch, Ultralytics, anomalib) are Python-first. The UI needs live updates.
- **Decision:** One Python package (`sonarsentinel`) for pipeline + API; FastAPI for REST and WebSocket.
- **Alternatives:** Flask (no native async/WebSocket), Django (heavier than needed), Node.js backend (would need a separate Python ML service).
- **Consequences:** One language for backend and ML; automatic OpenAPI docs. CPU-heavy work must run in worker processes, not the async event loop.

## ADR-002 · YOLO11-seg as the primary detector

- **Context:** Needs boxes **and** masks, real-time speed, a small footprint for edge, and easy export to TensorRT/OpenVINO.
- **Decision:** Ultralytics YOLO11s-seg, fine-tuned on 3-channel sonar tiles.
- **Alternatives:** Faster/Mask R-CNN (more accurate on small data but slower and harder to deploy at the edge); U-Net only (no instances or boxes); DETR-family models (need more data, heavier).
- **Consequences:** Fast iteration and one-line exports. Check the Ultralytics AGPL-3.0 licence (or an enterprise licence) before any commercial distribution. Thin structures need a refinement model (ADR-004).

## ADR-003 · Three-channel sonar input (raw · despeckled · local std)

- **Context:** Despeckling removes noise but also removes fine net texture. Pretrained detectors expect 3 channels.
- **Decision:** Stack raw normalised, Lee-despeckled and local standard deviation images as RGB channels.
- **Alternatives:** Grayscale repeated 3× (wastes channels); despeckled only (loses texture); learned denoiser (extra model, less predictable).
- **Consequences:** The model sees both shape and texture and pretrained weights still apply. Preprocessing must be identical in training and inference.

## ADR-004 · Segmentation (not boxes only) for ghost nets and pipes

- **Context:** Nets are irregular and pipes are long and thin, so boxes badly overestimate area and give poor dimensions.
- **Decision:** Masks from YOLO-seg; optional U-Net refinement (P1) for `ghost_net` and `pipe`.
- **Consequences:** Accurate area and footprint; labelling cost goes up, reduced with SAM-assisted annotation.

## ADR-005 · Anomaly detection (PatchCore) plus synthetic data for ghost nets

- **Context:** No public labelled ghost-net SSS dataset exists, and ghost nets are the key hazard.
- **Decision:** (a) Train on synthetic ghost nets rendered onto real seafloor; (b) PatchCore trained on normal seafloor flags unknown objects as `unknown_anomaly`; (c) human review feeds real examples back.
- **Alternatives:** Supervised only (no data); GAN/diffusion-only synthesis (realism hard to control and verify).
- **Consequences:** Safety net for unseen object types. Anomaly false alarms on unusual natural seabed are handled by tiering and review. Synthetic realism must be validated.

## ADR-006 · Physics-aware fusion + isotonic calibration for confidence

- **Context:** Raw detector scores aren't probabilities, and the problem statement requires a meaningful 0–100% confidence and fewer false positives from shadows and rocks.
- **Decision:** Fuse detector, anomaly, shadow-consistency, LightGBM FP-filter and persistence scores with data-quality penalties; calibrate with isotonic regression; expose the breakdown.
- **Alternatives:** Temperature scaling only (ignores physics cues); end-to-end learned confidence (needs much more data, less explainable).
- **Consequences:** Explainable and tunable, and calibration can be measured (ECE). Needs a held-out calibration split and recalibration after retraining.

## ADR-007 · Geotagging from ping-header navigation, not image metadata

- **Context:** Sonar PNG/JPGs rarely carry GPS EXIF; real positions live in sonar file ping headers or GeoTIFF georeferencing.
- **Decision:** Treat `.xtf` (and GeoTIFF) as the primary geotagged inputs; compute per-pixel positions geometrically; accept image + nav CSV as a fallback.
- **Consequences:** Accurate, auditable positions with an uncertainty estimate. Requires handling units, layback and heading. Image-only inputs are explicitly marked `NOT_GEOTAGGED`.

## ADR-008 · Chunked streaming over WebSocket

- **Context:** Logs can be GBs, and users need to see results "in real time".
- **Decision:** Process overlapping ping chunks; push `progress/track/detection/warning/done` events over WebSocket, with replay on reconnect.
- **Alternatives:** Polling (laggy, chatty); Server-Sent Events (fine, but one-way and less flexible for cancel/resume).
- **Consequences:** Bounded memory, live UX, and the same code path works for growing files at the edge. Needs cross-chunk duplicate resolution (`detection_update/removed` events).

## ADR-009 · React + Leaflet for the dashboard

- **Context:** Map-centric UI, offline operation, no API keys.
- **Decision:** React + TypeScript + Vite + **Leaflet used directly** through a thin in-house React wrapper (map, layers, markers via refs/hooks); tiles from MBTiles when offline.
- **Amendment (2026-09-13):** originally react-leaflet. Dropped because react-leaflet v3+ is under the Hippocratic License 2.1, which adds use restrictions incompatible with our AGPL-3.0 licence (ADR-013). Leaflet (BSD-2-Clause) and leaflet.markercluster (MIT) remain.
- **Alternatives:** Mapbox GL / Google Maps (API keys, online dependency); OpenLayers (powerful, steeper learning curve); Streamlit (fast prototype but limited real-time interaction and custom layout).
- **Consequences:** Lightweight and offline-capable. Large mosaics need tiling (COG/tiles) instead of a single image overlay.

## ADR-010 · SQLite for the prototype, PostgreSQL + PostGIS for production

- **Context:** Single-user workstation first; multi-user archive and spatial queries later.
- **Decision:** SQLAlchemy models that work on both; SQLite by default, PostGIS when deployed centrally.
- **Consequences:** Zero-setup prototype; spatial queries in SQLite use bounding-box filters on lat/lon columns until migrated.

## ADR-011 · WGS84 decimal degrees as the output standard

- **Context:** GPS devices, Google Earth, QGIS and most reporting use WGS84.
- **Decision:** All outputs in WGS84 (EPSG:4326), 6 decimals; UI also shows DMS; UTM used internally for metric calculations.
- **Consequences:** Interoperable outputs. Reports that must use another datum need a conversion step (open question Q7 in the PRD).

## ADR-012 · ONNX as the model interchange format for edge

- **Context:** Several runtimes are needed: CPU (ONNX Runtime), NVIDIA (TensorRT), Intel (OpenVINO).
- **Decision:** Export every production model to ONNX; build device-specific engines on the target; `SS_RUNTIME=auto` picks the best available.
- **Consequences:** One export path, many targets. INT8 accuracy must be verified per device (≤ 3 mAP points drop).

## ADR-013 · Project licence: AGPL-3.0

- **Status:** Accepted · 2026-09-13 · decided by the team lead in Phase 0; to be confirmed in the Phase 0 team sign-off
- **Context:** The primary detector (ADR-002) uses Ultralytics YOLO, licensed AGPL-3.0 or under a paid enterprise licence. The project needs a licence before the repository is shared or submitted. Options A–D are in [Licences & Compliance §4](../legal/LICENSES_AND_COMPLIANCE.md#4-project-licence-decision).
- **Decision:** License SonarSentinel under the **GNU Affero General Public License v3.0** (`LICENSE` at the repository root, official text from gnu.org). All contributions are accepted under the same licence.
- **Alternatives:** Apache-2.0 with a permissively licensed detector (Sprint 3 rework and re-evaluation); keeping it private and undecided until the finale; proprietary with an Ultralytics enterprise licence (cost).
- **Consequences:** No rework; compatible with the permissive dependencies. Anyone who distributes SonarSentinel, or lets others use a modified version over a network, must offer the corresponding source under AGPL-3.0. Third-party notices must be kept. **Revisit before any NIOT/production deployment:** if closed-source or permissive distribution is needed, choose an enterprise licence or swap the detector (option B/C).

## ADR-014 · Frontend styling: CSS Modules + CSS custom-property design tokens

- **Status:** Accepted · 2026-09-13 (Phase 1 default; the Frontend Engineer (R5) may revisit before ST-090 starts in Sprint 3)
- **Context:** The dashboard needs consistent class colours and tier styles across map markers, lists and exports ([wireframes §4](../wireframes/README.md#4-visual-language)); light and satellite basemaps need different contrast; offline builds must not depend on external CSS; the team is small.
- **Decision:** Use **CSS Modules** (built into Vite) for component-scoped styles, and **CSS custom properties** in one `tokens.css` for design tokens: class colours, tier styles, spacing, typography. The same token values are exported to TypeScript for Leaflet marker rendering and KML styles.
- **Alternatives:** Tailwind CSS (fast prototyping, but adds a build dependency and class-heavy markup, and tokens are split between config and CSS); CSS-in-JS (runtime cost, more dependencies); a component library such as MUI (heavy, harder to match the map-centric wireframes).
- **Consequences:** No extra styling dependency; tokens usable from CSS and TypeScript; theming (e.g. high-contrast on the edge console) by switching token sets. Utility-class speed is traded for slightly more CSS per component.

## ADR-015 · Report datum and CRS: WGS84 geographic (PRD Q7)

- **Status:** Proposed · 2026-09-13 (Sprint 1) · the Geo Engineer (R3) confirms with NIOT at the next mentor sync; accepted at Gate G1 unless NIOT requires otherwise
- **Context:** PRD Q7 asks which datum/CRS official reports need. Sonar navigation arrives as WGS84 lat/lon (XTF `NavUnits` 3) or projected metres (`NavUnits` 0, usually UTM). Indian and international paper and electronic charts (IHO S-57/S-100 ENCs) are referenced to WGS84, GNSS receivers output WGS84 (or ITRF-aligned realisations within a few centimetres of it), and web maps, GeoJSON (RFC 7946) and KML all require WGS84 longitude/latitude.
- **Decision:** All report coordinates are **WGS84 geographic (EPSG:4326) decimal degrees with 6 decimals** (≈ 0.11 m), `lat`/`lon` keys, plus DMS strings in human-readable exports. `survey.datum` is the constant `"WGS84"` in report schema 1.0. Projected coordinates are only an input (EPSG from the file, the UI or `--utm-epsg`) and an optional *extra* output column (UTM zone of the survey, e.g. EPSG:32643/32644/32645) if NIOT asks for it; they never replace lat/lon.
- **Alternatives:** Everest 1830 / Indian 1975 datum (legacy Survey of India topographic maps; offsets of hundreds of metres from WGS84, so reporting in it would need explicit transformations and risk confusion); UTM-only reports (not usable directly in GeoJSON/KML or chart plotters); ITRF2014 at a survey epoch (centimetre-level differences, below our ≈ 2–10 m position uncertainty).
- **Consequences:** No datum transformation in the pipeline; exports load directly in QGIS, Leaflet and chart software. If NIOT needs a different datum, add an export-time transformation and a `datum` value in a new report version rather than changing 1.0.

## ADR-016 · Sprint 3 ML stack: own PatchCore, rule-based stand-in detector, CPU baselines

- **Status:** Accepted · 2026-09-13 (Sprint 3); revisit when GPU training is available (before Gate G3)
- **Context:** ADR-005 names PatchCore via anomalib. The development machine has no CUDA GPU (Intel i5-13420H, 16 GB). anomalib releases pin specific torch/lightning versions, while the environment already runs PyTorch 2.14 CPU with Ultralytics 8.4. Gate G2 needs `sonarsentinel detect` and a CI integration test that work without model weights. On Windows, conda NumPy/SciPy (Intel OpenMP) and pip PyTorch (LLVM OpenMP) abort training with "OMP: Error #15".
- **Decision:**
  1. Implement **PatchCore directly in PyTorch** (`sonarsentinel/detect/anomaly.py`, `ml/train_anomaly.py`) following Roth et al. (CVPR 2022): ImageNet ResNet-18 layer2+layer3 features, 3×3 neighbourhood pooling, greedy coreset memory bank, nearest-neighbour distance, thresholds from a held-out normal site.
  2. Ship a transparent **rule-based detector** `classical-bright-target@0.1.0` as the default when no trained weights are configured, so the thin slice, CI and mock fixtures run everywhere. Reports always name the detector version.
  3. Train **short CPU baselines** in Sprint 3 and record schedule and wall-clock time in the experiment logs; full schedules (ADR-002, `epochs=200`) run on a GPU before Gate G3.
  4. Set `KMP_DUPLICATE_LIB_OK=TRUE` in the training scripts (documented Intel/LLVM OpenMP workaround).
- **Alternatives:** anomalib in a separate environment (a second env to maintain, version drift); no default detector until a model exists (CI and G2 blocked); a smaller YOLO11n for speed (diverges from ADR-002's model choice).
- **Consequences:** No anomalib dependency; PatchCore code is ~250 lines and tested without downloads. Sprint 3 detection metrics are low-confidence CPU baselines and must not be used to tune thresholds or calibration. The rule-based detector only finds very bright compact objects and labels them `debris_other`.

## ADR-017 · Sprint 4 scoring, storage and job decisions

- **Status:** Accepted · 2026-09-13 (Sprint 4 planning); R1 (scoring) and R4 (backend) review at the Sprint 4 review
- **Context:** The architecture documents specify the fusion formula, tiers and API, but leave gaps: no shadow-score formula, no persistence value for single-view detections, no rule for missing score components, no penalty for `NEAR_NADIR`, no chip storage rule, no cancel response body, and a data model (06 §4) whose `DETECTION` table lacks fields the CSV/JSON reports need. ADR-001 names worker processes; the prototype runs on one CPU laptop. ADR-016 forbids tuning thresholds or calibration on the CPU baseline, yet Sprint 4 must build and test that tooling before GPU models exist.
- **Decision:**
  1. **Shadow score** (`sonarsentinel/scoring/shadow.py`): geometric mean of highlight contrast (object vs. surrounding ring) and far-range shadow darkness, scaled by the fraction of object rows with a shadow run; 0 when the object is not brighter than its surroundings. Height `h = Ls·H / (r + Ls)` ([04 §6](04-geotagging-engine.md)); `height_m` is null without a usable shadow.
  2. **Missing components:** `fused = Σ wᵢ·sᵢ / Σ wᵢ` over the components present (detector, anomaly, shadow, fp_filter, persistence), minus dropout and motion penalties, clipped to [0, 1]. `scores` lists every component used, so TC-CONF-003 can recompute it.
  3. **Persistence** = `1 − 0.5^n_views` (0.50 for one view, 0.75 for two), matching the data-model example.
  4. **`anomaly` tier** requires confidence 30–49.9 **and** an anomaly score ≥ τ (`anomaly.threshold`), for any detection that has an anomaly score.
  5. **`NEAR_NADIR`** and **`TILE_EDGE`** (object cut by the swath edge) are flags without a penalty weight.
  6. **Calibrator** is isotonic regression stored as JSON breakpoints and applied with linear interpolation (no pickle, no scikit-learn at runtime); the **FP filter** is a LightGBM text model used only when `lightgbm` is installed. Both are fitted on the site-held-out splits (FP filter and fusion weights on `val`, calibrator on `calib`).
  7. **Tooling on the CPU baseline:** this ADR narrows ADR-016. Scoring artefacts may be fitted on the CPU baseline to validate the tooling and the pipeline, with versions `0.1.x` and their data size stated in the model card; they must be refitted on the GPU-trained detector before Gate G3 is signed off.
  8. **Chips** are rendered while each chunk is in memory, once per overlay (`mask`, `shadow`, `anomaly`, `none`), and renamed to the final detection IDs under `results/<survey_id>/chips/`.
  9. **Storage:** SQLite through SQLAlchemy 2.0 with the 06 §4 tables plus the full detection JSON per row; schema versions applied by in-app migrations (no Alembic).
  10. **Jobs:** one background worker thread and a FIFO queue; `run_pipeline`/`run_survey` poll `should_cancel` at every progress event (at least once per chunk) and stop with `PipelineCancelled`. Cancelling a queued job returns 200 `cancelled`; a running job 202 `cancelling`; a finished job 409 `JOB_NOT_CANCELLABLE`.
  11. **Multi-file surveys:** `run_survey` processes lines in upload order, renumbers detection IDs across lines, then clusters detections across lines (ST-038) before scoring persistence.
- **Alternatives:** A fixed persistence of 0 for single views (punishes every single-line survey); Alembic migrations (extra dependency for a prototype schema); process workers now (cancellation and event streaming across processes add complexity before Docker packaging, ST-005); pickled scikit-learn calibrators (version-fragile, unsafe to load from untrusted folders).
- **Consequences:** Every score in a report is reproducible from its breakdown and configuration. CPU-baseline calibration and FP-filter numbers are tooling evidence only and are labelled as such in TSR-M4. A CPU-heavy job can slow API responses; revisit the worker model with ST-005 or if health latency exceeds 1 s during a job.

## ADR-018 · Sprint 5 dashboard, streaming, export and edge decisions

- **Status:** Accepted · 2026-09-14 (Sprint 5 planning); R4 (API), R5 (dashboard) and R3 (geo) review at the Sprint 5 review
- **Context:** The API specification (05) defines the WebSocket message types, detection filters and report formats but leaves open the heartbeat and close behaviour, when `done` is sent relative to storing results, the shape of the track "quality segments", the "Confirmed only" export scope and class/size sorting that S-06 and the User Manual offer, the label-store record, whether surface-return detections are flagged or removed, where uncertainty defaults live, and which GDAL binding builds the mosaic. The event buffer (1,000) is also smaller than a 2,000-detection job.
- **Decision:**
  1. **WebSocket `/ws/jobs/{job_id}`:** the client sends `{"type":"resume","after_seq":N}` first and `{"type":"ping"}` every 20 s; the server answers `pong` (no `seq`). Replay uses the in-memory buffer and falls back to `results/<survey_id>/job.log.jsonl`; events with `seq ≤` the last sent are skipped. The server closes with code 1000 after `done` or `error` and with 4404 for an unknown job.
  2. **Terminal events** are emitted by the job manager after reports and database rows are written: `done{status, summary, report_urls{json,csv,geojson,kml}, mosaic}`; failures emit `error{code,message}`. A cancelled job keeps the detections found so far and ends with `done{status:"cancelled"}`.
  3. **Detection queries** accept `class`, `min_conf`, `max_conf`, `tier`, `review_status`, `flags`, `bbox`, `sort ∈ confidence|-confidence|area|-area|ping|-ping|class`, `limit ≤ 5000`, `offset`. One filter module serves the API, the mock and filtered exports; the dashboard filters loaded detections client-side with the same rules.
  4. **Report download** `format=json|csv|geojson|kml`, `scope=all|filtered|hazards|confirmed` (confirmed = confirmed or reclassified), `include_rejected=false` by default; exports are built from the stored detection JSON so review changes appear in them.
  5. **Track endpoint:** a GeoJSON FeatureCollection with the track `LineString` (`segment:"track"`) and one `LineString` per quality event (`segment:"quality"`, `code`, `ping_start`, `ping_end`).
  6. **Label store:** `labels/<yyyy-mm>/<detection_id>/label.json` (verdict, original and final class, reject reason, reviewer, note, time, model version, scores, position, sonar reference) plus the detection chip; `pending` (undo) removes the folder while the REVIEW table keeps the history.
  7. **Surface-return band:** every detection inside the band is flagged `SURFACE_RETURN_BAND`; linear, track-parallel detections in the band are removed only when `preprocess.surface_return_mask` is true.
  8. **Uncertainty defaults** live in `geo.uncertainty` (GNSS 2.0 m, heading 2.0°, altitude 0.5 m, time 0.2 s, estimated-layback fraction 0.10) and feed the 04 §8 root-sum-square budget.
  9. **Mosaic** is built with rasterio's GDAL (GCP thin-plate-spline warp to EPSG:4326), written as GeoTIFF, RGBA PNG and Leaflet bounds; no separate `osgeo.gdal` dependency.
  10. **ONNX runtime:** `detection.runtime: auto` uses `best.onnx` next to the configured weights when ONNX Runtime is installed and falls back to PyTorch; `torch` and `onnxruntime` force one. ONNX is exported at a fixed 640 px input.
- **Alternatives:** Server-sent events instead of WebSockets (no client→server resume message); sending `done` from the pipeline (clients could fetch a report before it exists); server-only filtering in the dashboard (a round trip per slider move, > 100 ms); `simplekml` for KML (extra dependency for a small XML file); GDAL Python bindings for the mosaic (difficult Windows install).
- **Consequences:** Clients can reconnect at any point without losing or duplicating events; exports and the dashboard agree because both read the stored detection JSON and share filter semantics. The "Confirmed" scope and extra sort keys extend API 1.0 compatibly. Removing surface-return detections stays opt-in, so no real object is dropped by default.

## ADR-019 · Sprint 6 hardening, deployment and edge decisions

- **Status:** Accepted · 2026-09-14 (Sprint 6 planning); R6 (QA/DevOps), R4 (API) and R5 (dashboard) review at the Sprint 6 review
- **Context:** The deployment document (07) defines `SS_*` environment variables, Docker images, offline tiles and an edge watch mode, but the backend read only `SONARSENTINEL_DATA_DIR`, the error handling in 02 §5 (chunk retry, CPU fallback) and the per-job timeout promised in SECURITY.md were not implemented, and the API specification has no settings schema, delete semantics or tile endpoint. The development laptop has no Docker, GPU or Jetson, and no survey over a charted wreck exists in the project data.
- **Decision:**
  1. **Environment:** `SS_CONFIG`, `SS_DATA_DIR` (alias `SONARSENTINEL_DATA_DIR`), `SS_MODELS_DIR` (relative model paths resolve against it), `SS_RUNTIME`, `SS_MAX_UPLOAD_GB`, `SS_OFFLINE_TILES`, `SS_KEEP_WORK_FILES`, `SS_LOG_LEVEL`, `SS_WORKERS` (only 1 supported) and `SS_JOB_TIMEOUT_S` (default 3600) are applied at configuration load and app start; invalid values stop start-up with `VALIDATION_ERROR`.
  2. **Failure handling:** an unexpected exception in a chunk is retried once and then the chunk is skipped with a `CHUNK_SKIPPED` warning and ping range (job `completed_with_warnings`); a requested `tensorrt` or `cuda` runtime that is unavailable falls back to ONNX Runtime, then PyTorch CPU, with `CPU_FALLBACK`; a job running longer than the timeout is stopped at its next checkpoint and fails with `JOB_TIMEOUT`.
  3. **Settings:** `GET/PUT /api/v1/settings` exchange one document (detection, anomaly, tiers, map, processing, geo, read-only system); tiers must satisfy hazard > review > anomaly; the document is stored as `settings.json` in the data folder and overlays the pipeline configuration for new jobs only.
  4. **History:** `GET /api/v1/surveys` filters by text, project, status and creation date; `DELETE /api/v1/surveys/{id}` removes a finished survey's rows and files but keeps the label store, and refuses queued or running jobs with 409 `JOB_NOT_CANCELLABLE`.
  5. **Offline basemap:** tiles come from a team-rendered MBTiles file served at `GET /api/v1/tiles/{z}/{x}/{y}.png` (TMS row flip); health reports `offline_tiles`; the dashboard switches source from Settings and shows an offline badge.
  6. **Edge watch mode:** `sonarsentinel watch DIR --out OUT` polls, processes each file once when its size and modification time have been stable for a set time, keeps state in `OUT/.watch_state.json`, and prints alert lines `SS1|survey|detection|class|conf|lat|lon|LxW|depth|UTC` (≤ 256 bytes) for detections above a confidence threshold; tailing growing files chunk by chunk is not implemented.
  7. **Deployment:** CPU image on `python:3.11-slim` with pinned pip wheels (rasterio bundles GDAL), frontend on `nginx:alpine` proxying `/api` and `/ws`, compose files for CPU, GPU override and edge; images are built, smoke-tested and scanned with Trivy in CI because the laptop has no Docker. CI also runs `pip-audit` and `npm audit --audit-level=critical`.
  8. **Benchmarks:** `scripts/benchmark.py` runs each input three times in separate processes and reports medians, per-stage timings, first-detection latency, progress gaps, peak resident memory and model sizes; a synthetic 1 km line stands in for the missing reference line and is labelled as such.
  9. **Scope:** ST-097 (waterfall viewer) and ST-025 (JSF/SL2 readers) are dropped from Sprint 6 as stretch stories; ST-101 (Jetson) and ST-037 (charted wreck) keep their tooling but need hardware and data.
  10. **Release tagging:** `v1.0.0-rc1` is tagged only when TSR-M6 recommends Go.
- **Alternatives:** Filesystem event libraries for watch mode (extra dependency, unreliable on network shares); a conda-based Docker image (larger, slower builds); downloading OpenStreetMap tiles for offline use (forbidden by the tile usage policy); tagging the release candidate for the demo regardless of the gate (misrepresents readiness).
- **Consequences:** The same software runs from conda, Docker and the edge folder watcher with one configuration mechanism; failures degrade gracefully and are visible in reports. Docker correctness is verified only in CI until a machine with Docker is available. Without GPU training, charted-wreck data and user tests, G5 is expected to remain No-go and is documented as such.
