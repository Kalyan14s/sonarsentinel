# 01 · System Architecture

[← Architecture index](README.md)

## 1. System context (C4 level 1)

Who and what interacts with SonarSentinel.

```mermaid
flowchart LR
    operator["Survey Operator<br/>vessel / AUV team"]
    analyst["Marine Analyst<br/>NIOT scientist"]
    recovery["Recovery Team<br/>divers · ROV · NGO"]
    authority["Port / Disaster Authority"]

    sonar["Side-Scan Sonar + GNSS<br/>towfish or AUV"]
    system(["SonarSentinel"])
    gis["GIS tools<br/>QGIS · Google Earth"]
    tiles["Basemap tiles<br/>online or offline MBTiles"]

    sonar -- ".xtf / .jsf / GeoTIFF" --> system
    operator -- "uploads logs, monitors" --> system
    analyst -- "reviews, exports" --> system
    system -- "hazard locations (KML/CSV)" --> recovery
    system -- "prioritised hazard reports" --> authority
    system -- "GeoJSON / KML" --> gis
    tiles --> system
```

## 2. Containers (C4 level 2)

```mermaid
flowchart TB
    subgraph Client["Client"]
        UI["Web Dashboard<br/>React + TypeScript + Leaflet"]
        CLI["CLI<br/>sonarsentinel detect"]
        EDGEUI["Edge Console (P2)<br/>minimal status UI"]
    end

    subgraph Backend["Backend · Python 3.11"]
        API["API Service<br/>FastAPI · REST + WebSocket"]
        JOBS["Job Manager<br/>queue · workers · events"]
        PIPE["Processing Core<br/>sonarsentinel package"]
        RT["Model Runtime<br/>PyTorch · ONNX Runtime · TensorRT"]
    end

    subgraph Storage["Storage"]
        DB[("Metadata DB<br/>SQLite → PostgreSQL/PostGIS")]
        FS[("File Store<br/>uploads · tiles · chips · mosaics · reports")]
        REG[("Model Registry<br/>weights · calibrators · model cards")]
        MAP[("Tile Cache<br/>offline basemap MBTiles")]
    end

    UI <-->|"HTTP + WebSocket"| API
    EDGEUI <-->|"HTTP + WebSocket"| API
    CLI --> PIPE
    API --> JOBS
    JOBS --> PIPE
    PIPE --> RT
    RT --> REG
    PIPE --> DB
    PIPE --> FS
    API --> DB
    API --> FS
    API --> MAP
```

| Container | Technology | Responsibility |
|---|---|---|
| Web Dashboard | React, TypeScript, Vite, Leaflet (used directly via a thin React wrapper; ADR-009) | Upload, live map, filters, detail, review, downloads |
| CLI | Python (Typer) | Headless batch processing; scripting; edge runs |
| API Service | FastAPI, Uvicorn | REST endpoints, file upload, WebSocket event streaming, static files (chips, reports, mosaics) |
| Job Manager | asyncio worker pool (prototype) → Redis + RQ/Celery (scale-out) | Queue jobs, run pipeline per chunk, publish events, cancellation |
| Processing Core | NumPy, OpenCV, SciPy, pyxtf, GDAL, pyproj | Ingest → preprocess → detect → score → geotag → report |
| Model Runtime | PyTorch (dev), ONNX Runtime (CPU), TensorRT (Jetson), OpenVINO (Intel) | Run detector, anomaly model, FP filter, calibrator |
| Metadata DB | SQLite (prototype), PostgreSQL + PostGIS (production) | Surveys, jobs, detections, reviews, track, quality events |
| File Store | Local filesystem (volume) | Raw uploads, intermediate tiles, detection chips, mosaics, reports |
| Model Registry | Versioned folder (`models/<id>/<version>/`) | Model weights, calibrators, model cards, metrics |

## 3. Components of the Processing Core (C4 level 3)

```mermaid
flowchart LR
    subgraph ingest["ingest/"]
        I1["xtf_reader"]
        I2["geotiff_reader"]
        I3["image_nav_reader"]
        I4["jsf_reader · sl_reader (P1)"]
        I0["validators"]
    end

    subgraph preprocess["preprocess/"]
        P1["nav_clean"]
        P2["bottom_track"]
        P3["gain"]
        P4["slant_range"]
        P5["resample"]
        P6["quality_masks<br/>dropout · motion · surface"]
        P7["despeckle · to_3ch"]
        P8["tiling · chunking"]
    end

    subgraph detect["detect/"]
        D1["yolo_detector + SAHI"]
        D2["anomaly_patchcore"]
        D3["mask_refiner (P1)"]
        D4["merge · dedupe"]
    end

    subgraph scoring["scoring/"]
        S1["shadow"]
        S2["features"]
        S3["fp_filter"]
        S4["fusion"]
        S5["calibration · tiers"]
    end

    subgraph geo["geo/"]
        G1["units · crs"]
        G2["layback"]
        G3["georef<br/>pixel → lat/lon"]
        G4["measure<br/>footprint · dims"]
        G5["mosaic"]
        G6["cluster (cross-line)"]
    end

    subgraph report["report/"]
        R1["schema"]
        R2["json · csv"]
        R3["geojson · kml"]
    end

    ingest --> preprocess --> detect --> scoring --> geo --> report
    G1 -. used by .-> P1
    G3 -. used by .-> S1
```

## 4. Main flow: upload → live map → report

```mermaid
sequenceDiagram
    actor U as Analyst
    participant UI as Dashboard
    participant API as FastAPI
    participant J as Job Worker
    participant P as Processing Core
    participant S as DB + File Store

    U->>UI: Drop line_07.xtf, click Start analysis
    UI->>API: POST /api/v1/surveys (multipart)
    API->>S: store upload, create survey + job (queued)
    API-->>UI: 202 Accepted {survey_id, job_id}
    UI->>API: open WS /ws/jobs/{job_id}
    API->>J: enqueue job

    J->>P: validate + parse header
    P-->>J: SonarLog metadata (pings, channels, nav present)
    J-->>UI: event progress(stage=parse)

    loop each chunk (2,000 pings, 200 overlap)
        J->>P: preprocess → tiles → detect → score → geotag
        P->>S: save detections, chips, track segment, quality events
        J-->>UI: event track(points)
        J-->>UI: event detection(...) × n
        J-->>UI: event warning(DROPOUT / HIGH_MOTION)
        J-->>UI: event progress(percent, eta)
    end

    J->>P: cross-chunk merge, cross-line clustering, mosaic
    P->>S: write report.json/.csv/.geojson/.kml
    J-->>UI: event done(summary, report_urls)

    U->>UI: Click detection marker
    UI->>API: GET /api/v1/detections/{id}
    API-->>UI: detection + chip_url
    U->>UI: Download CSV
    UI->>API: GET /api/v1/surveys/{id}/report?format=csv
    API-->>UI: report.csv
```

## 5. Review flow (P1)

```mermaid
sequenceDiagram
    actor A as Analyst
    participant UI as Review Queue
    participant API as FastAPI
    participant S as DB
    participant L as Label Store

    UI->>API: GET /api/v1/surveys/{id}/detections?tier=review&review_status=pending
    API-->>UI: detections[]
    A->>UI: Press C (confirm) / R (reject) / K (reclassify)
    UI->>API: PATCH /api/v1/detections/{id} {review_status, class, note}
    API->>S: update detection + insert review row
    API->>L: append labelled sample (chip, mask, class, verdict)
    API-->>UI: 200 updated detection
    Note over S,L: Reports regenerate on next export<br/>Label store feeds the retraining pipeline
```

## 6. Job lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running: worker picks up
    running --> completed: all stages done
    running --> completed_with_warnings: done, quality warnings
    running --> failed: unrecoverable error
    queued --> cancelled: user cancels
    running --> cancelled: user cancels
    completed --> [*]
    completed_with_warnings --> [*]
    failed --> [*]
    cancelled --> [*]
```

Stages reported in progress events: `validate → parse → preprocess → detect → score → geotag → merge → report`.

## 7. Deployment modes

| Mode | Where | What runs | Notes |
|---|---|---|---|
| **Shore workstation** | Lab / office / ship's lab laptop | Full stack: dashboard + API + worker + all models | Default for analysts |
| **On-board edge** | AUV payload computer / Jetson on vessel | CLI/edge runner with detector + shadow check + geotag; optional minimal API + edge console | Anomaly model and mosaic can be deferred to shore |
| **Central server** (future) | NIOT data centre | Scaled API + Redis queue + multiple GPU workers + PostGIS | Multi-user, survey archive |

Details: [07-deployment.md](07-deployment.md).

## 8. Repository layout

```text
marine-debris/
├── docs/
│   ├── PROJECT_IDEA.md
│   ├── PRD.md
│   ├── architecture/
│   └── wireframes/
├── backend/
│   ├── sonarsentinel/
│   │   ├── ingest/        # xtf_reader.py, geotiff_reader.py, image_nav_reader.py, validators.py
│   │   ├── preprocess/    # nav_clean.py, bottom_track.py, gain.py, slant_range.py, resample.py,
│   │   │                  # quality_masks.py, despeckle.py, tiling.py
│   │   ├── detect/        # yolo_detector.py, anomaly_patchcore.py, mask_refiner.py, merge.py
│   │   ├── scoring/       # shadow.py, features.py, fp_filter.py, fusion.py, calibration.py
│   │   ├── geo/           # units.py, layback.py, georef.py, measure.py, mosaic.py, cluster.py
│   │   ├── report/        # schema.py, export_json.py, export_csv.py, export_geojson.py, export_kml.py
│   │   ├── api/           # main.py, routes_surveys.py, routes_detections.py, ws.py
│   │   ├── jobs/          # manager.py, worker.py, events.py
│   │   ├── storage/       # db.py, orm.py, files.py
│   │   ├── config.py
│   │   ├── pipeline.py    # orchestrates stages per chunk
│   │   └── cli.py
│   ├── configs/pipeline.yaml
│   └── tests/             # unit + integration (sample XTF fixtures)
├── ml/
│   ├── datasets/          # download + convert scripts, LICENSES.md
│   ├── synth/             # ghost_net_generator.py, pipe_generator.py
│   ├── train_detector.py
│   ├── train_anomaly.py
│   ├── train_fp_filter.py
│   ├── calibrate.py
│   ├── evaluate.py
│   └── notebooks/
├── frontend/
│   └── src/               # pages/, components/, map/, api/, store/, styles/
├── edge/                  # export_models.py, trt_runner.py, edge_console/
├── models/                # versioned weights (git-ignored; release assets / DVC)
├── data/                  # local datasets and uploads (git-ignored)
└── docker/                # Dockerfile.backend, Dockerfile.frontend, docker-compose.yml, docker-compose.edge.yml
```

## 9. Cross-cutting concerns

| Concern | Approach |
|---|---|
| Configuration | Single `pipeline.yaml` + env vars; config hash stored per job |
| Logging | Structured JSON logs (job_id, stage, chunk, duration_ms) |
| Errors | Typed exceptions per stage → job warnings or failure; see [API error model](05-api-specification.md#4-error-model) |
| Performance | Chunked streaming, batched tile inference, memory-mapped arrays, GPU when available |
| Testing | Unit tests per stage; golden-file tests for georef; integration test on a small public XTF |
| Versioning | Semantic versions for pipeline, models and report schema (`report_version`) |
