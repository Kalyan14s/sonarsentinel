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
