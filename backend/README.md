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
sonarsentinel detect line_07.xtf --out results/ --formats json,csv
sonarsentinel detect harbour_03.png --nav harbour_03_nav.csv --utm-epsg 32644
sonarsentinel detect harbour_03.png --allow-no-gps     # image without navigation: NOT_GEOTAGGED
sonarsentinel serve --port 8000                        # API: /api/v1/health, /api/v1/models, /docs
sonarsentinel serve --mock --port 8001                 # mock API with a canned survey for the dashboard
```

`detect --detector auto` (default) uses the trained YOLO11-seg weights configured in
`configs/pipeline.yaml` when they exist and the ML packages are installed; otherwise it uses the
rule-based stand-in `classical-bright-target@0.1.0` and the report carries a `RULE_BASED_DETECTOR`
warning. The PatchCore anomaly model is used when its folder exists (`--no-anomaly` skips it).

## Package layout

| Module | Contents |
|---|---|
| `ingest/` | Validators, XTF / GeoTIFF / image + navigation readers, chunking (`SonarLog` contract) |
| `geo/` | Units/CRS, pixel → WGS84, navigation cleaning, measurements, track export |
| `preprocess/` | Bottom tracking, gain, slant-range correction, dropouts, motion flags, 3-channel input, tiling, `ProcessedChunk` |
| `detect/` | Detector interface, rule-based stand-in, YOLO11-seg adapter (+ SAHI), PatchCore, merge/dedupe |
| `report/` | Report JSON Schema 1.0, report builder, JSON/CSV export |
| `api/` | FastAPI skeleton and mock server |
| `pipeline.py` | Orchestrator: one file → report, with job events |

**Status (Sprint 3):** thin slice complete — `sonarsentinel detect` produces schema-valid JSON/CSV reports from XTF, GeoTIFF and waterfall images. Scoring is detector score minus quality penalties with an identity calibrator until Sprint 4 (ST-060…065).
