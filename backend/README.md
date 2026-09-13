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
sonarsentinel detect line_07.xtf --out results/ --formats json,csv   # report + chips in results/<survey_id>/
sonarsentinel detect harbour_03.png --nav harbour_03_nav.csv --utm-epsg 32644
sonarsentinel detect harbour_03.png --allow-no-gps     # image without navigation: NOT_GEOTAGGED
sonarsentinel serve --port 8000                        # API: health, models, surveys/validate, surveys, jobs, /docs
sonarsentinel serve --mock --port 8001                 # mock API with a canned survey for the dashboard
```

`detect --detector auto` (default) uses the trained YOLO11-seg weights configured in
`configs/pipeline.yaml` when they exist and the ML packages are installed; otherwise it uses the
rule-based stand-in `classical-bright-target@0.1.0` and the report carries a `RULE_BASED_DETECTOR`
warning. The PatchCore anomaly model, the LightGBM FP filter and the isotonic calibrator are used
when their files exist (`--no-anomaly` skips PatchCore); without them confidence is the fused score.

The API stores uploads, results and its SQLite database under `SONARSENTINEL_DATA_DIR`
(default `data/api/`, git-ignored). `POST /api/v1/surveys` queues a job; follow it with
`GET /api/v1/jobs/{job_id}` and cancel it with `POST /api/v1/jobs/{job_id}/cancel`.

## Package layout

| Module | Contents |
|---|---|
| `ingest/` | Validators, XTF / GeoTIFF / image + navigation readers, chunking (`SonarLog` contract) |
| `geo/` | Units/CRS, pixel → WGS84, navigation cleaning, layback, measurements, cross-line clustering, track export |
| `preprocess/` | Bottom tracking, gain, slant-range correction, dropouts, motion flags, 3-channel input, tiling, `ProcessedChunk` |
| `detect/` | Detector interface, rule-based stand-in, YOLO11-seg adapter (+ SAHI), PatchCore, merge/dedupe |
| `scoring/` | Shadow score and height, shape/texture features, fusion, isotonic calibrator, FP filter |
| `report/` | Report JSON Schema 1.0, report builder, JSON/CSV export, detection chips |
| `storage/` | SQLAlchemy models, migrations and repository (SQLite) |
| `jobs/` | Job manager and background worker with cancellation |
| `api/` | FastAPI app (health, models, uploads, jobs) and mock server |
| `pipeline.py` | Orchestrator: `run_pipeline` (one file) and `run_survey` (several lines) with job events |

**Status (Sprint 4):** scoring with calibrated confidence, chips, layback, cross-line clustering, upload API, jobs and storage work end to end. Model quality is still a CPU baseline ([TSR-M4](../docs/testing/reports/TSR-M4.md)).
