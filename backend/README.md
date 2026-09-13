# sonarsentinel (backend)

Python package with the SonarSentinel processing pipeline, CLI and API.

- Architecture: [docs/architecture](../docs/architecture/README.md)
- Setup: [Developer Setup](../docs/guides/DEVELOPER_SETUP.md)

```bash
conda env create -f backend/environment.yml
conda activate sonarsentinel
pip install -e "backend[dev,geo,api]"
sonarsentinel --help
cd backend && pytest --cov=sonarsentinel
```

## Commands

```bash
sonarsentinel validate line_07.xtf                     # stage S0: type, size, header
sonarsentinel inspect line_07.xtf                      # read the file, JSON summary (pings, times, track)
sonarsentinel track line_07.xtf --out track.geojson    # track as GeoJSON for QGIS / geojson.io
sonarsentinel detect line_07.xtf --out results/ --formats json,csv,geojson,kml   # report, chips, mosaic in results/<survey_id>/
sonarsentinel detect harbour_03.png --nav harbour_03_nav.csv --utm-epsg 32644
sonarsentinel detect harbour_03.png --allow-no-gps     # image without navigation: NOT_GEOTAGGED
sonarsentinel serve --port 8000                        # API + WebSocket, /docs
sonarsentinel serve --mock --port 8001                 # mock API with a canned survey for the dashboard
```

`detect --detector auto` (default) uses the trained YOLO11-seg weights configured in
`configs/pipeline.yaml` when they exist and the ML packages are installed; with
`detection.runtime: auto` it runs the exported `best.onnx` through ONNX Runtime when present.
Otherwise it uses the rule-based stand-in `classical-bright-target@0.1.0` and the report carries a
`RULE_BASED_DETECTOR` warning. The PatchCore anomaly model, the LightGBM FP filter and the isotonic
calibrator are used when their files exist (`--no-anomaly` skips PatchCore).

## API

The API stores uploads, results, labels and its SQLite database under `SONARSENTINEL_DATA_DIR`
(default `data/api/`, git-ignored). Everything is under `/api/v1` ([API specification](../docs/architecture/05-api-specification.md), ADR-018):

| Endpoint | Purpose |
|---|---|
| `POST /surveys/validate`, `POST /surveys` | Check files; upload and queue a job |
| `GET /jobs/{id}`, `POST /jobs/{id}/cancel` | Job status; cancel (stops within one chunk) |
| `WS /ws/jobs/{id}` | Progress, track, detections, warnings, `done`; resume with `{"type":"resume","after_seq":N}` |
| `GET /surveys`, `GET /surveys/{id}` | Surveys and their report links and mosaic |
| `GET /surveys/{id}/detections` | Filters `class`, `min_conf`, `max_conf`, `tier`, `review_status`, `flags`, `bbox`; `sort`, `limit`, `offset` |
| `GET /surveys/{id}/track`, `/mosaic.png` | Track and quality segments (GeoJSON); georeferenced mosaic |
| `GET /surveys/{id}/report` | `format=json|csv|geojson|kml`, `scope=all|filtered|hazards|confirmed` |
| `GET /detections/{id}`, `/chip.png`, `PATCH /detections/{id}` | Detection, chip overlays, review (label store) |

## Package layout

| Module | Contents |
|---|---|
| `ingest/` | Validators, XTF / GeoTIFF / image + navigation readers, chunking (`SonarLog` contract) |
| `geo/` | Units/CRS, pixel → WGS84, navigation cleaning, layback, measurements, uncertainty, mosaic, cross-line clustering, track export |
| `preprocess/` | Bottom tracking, gain, slant-range correction, dropouts, motion flags, surface-return band, 3-channel input, tiling |
| `detect/` | Detector interface, rule-based stand-in, YOLO11-seg adapter (PyTorch or ONNX, + SAHI), PatchCore, merge/dedupe |
| `scoring/` | Shadow score and height, shape/texture features, fusion, isotonic calibrator, FP filter |
| `report/` | Report JSON Schema 1.0, builder, JSON/CSV/GeoJSON/KML export, detection chips |
| `storage/` | SQLAlchemy models, migrations and repository (SQLite) |
| `jobs/` | Job manager, background worker, event log and listeners |
| `api/` | FastAPI app: uploads, jobs, results, review, WebSocket; shared filters; mock server |
| `pipeline.py` | Orchestrator: `run_pipeline` (one file) and `run_survey` (several lines) with job events |

**Status (Sprint 5):** end to end from upload to live map, review and four export formats; ONNX CPU path measured at ~220 s per km on a laptop. Model quality is still a CPU baseline ([TSR-M4](../docs/testing/reports/TSR-M4.md)).
