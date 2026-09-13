# 05 · API Specification

[← Architecture index](README.md)

- **Base URL:** `http://<host>:8000/api/v1`
- **WebSocket:** `ws://<host>:8000/ws/jobs/{job_id}`
- **Format:** JSON (UTF-8); timestamps ISO 8601 UTC; coordinates WGS84 decimal degrees
- **Auth:** none in the prototype (on-premise); token-based roles in P2 (`Authorization: Bearer <token>`)
- **Interactive docs:** FastAPI OpenAPI at `/docs`

## 1. Endpoint summary

| Method | Path | Purpose | Priority |
|---|---|---|---|
| `GET` | `/health` | Service, GPU and model status | P0 |
| `GET` | `/models` | Loaded model versions | P0 |
| `POST` | `/surveys/validate` | Validate files before upload starts processing | P0 |
| `POST` | `/surveys` | Upload file(s) and start a processing job | P0 |
| `GET` | `/surveys` | List surveys (history) | P1 |
| `GET` | `/surveys/{survey_id}` | Survey metadata, summary, job status | P0 |
| `DELETE` | `/surveys/{survey_id}` | Delete survey and files | P1 |
| `GET` | `/surveys/{survey_id}/track` | Track line (GeoJSON LineString) + quality segments | P0 |
| `GET` | `/surveys/{survey_id}/detections` | List/filter detections | P0 |
| `GET` | `/surveys/{survey_id}/report` | Download report (`format=json\|csv\|geojson\|kml`) | P0 |
| `GET` | `/surveys/{survey_id}/mosaic` | Mosaic image URL + bounds | P1 |
| `GET` | `/surveys/{survey_id}/waterfall` | Waterfall tile for ping range | P1 |
| `GET` | `/jobs/{job_id}` | Job status and stage timings | P0 |
| `POST` | `/jobs/{job_id}/cancel` | Cancel a running job | P0 |
| `GET` | `/detections/{detection_id}` | Full detection | P0 |
| `GET` | `/detections/{detection_id}/chip.png` | Sonar chip with overlay (`overlay=mask\|shadow\|anomaly\|none`) | P0 |
| `PATCH` | `/detections/{detection_id}` | Review: confirm / reject / reclassify | P1 |
| `GET` | `/settings` · `PUT` `/settings` | Thresholds, defaults | P1 |
| `WS` | `/ws/jobs/{job_id}` | Live processing events | P0 |

## 2. REST endpoints

### 2.1 `POST /surveys`
Upload and start processing. `multipart/form-data`.

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | file[] | yes | `.xtf`, `.tif`, `.png`, `.jpg` (`.jsf`, `.sl2`, `.sl3` in P1) |
| `nav_csv` | file | no | Navigation CSV for image inputs |
| `options` | JSON string | no | See below |

```json
{
  "name": "Chennai-Port-Line07",
  "project": "NIOT-Cleanup-2026",
  "utm_epsg": "auto",
  "ground_resolution_m": 0.10,
  "apply_layback": "auto",
  "manual_layback_m": null,
  "anomaly_scan": true,
  "image_layout": "port_stbd",
  "allow_no_gps": false,
  "detector_model": "yolo11s-seg-sonar@1.2.0"
}
```

**202 Accepted**
```json
{
  "survey_id": "SRV-20260913-001",
  "job_id": "JOB-20260913-001",
  "status": "queued",
  "ws_url": "/ws/jobs/JOB-20260913-001"
}
```

### 2.2 `POST /surveys/validate`
Same form as above, but nothing is processed.

**200 OK**
```json
{
  "files": [
    {
      "filename": "line_07.xtf", "valid": true, "format": "xtf", "size_bytes": 1503238553,
      "sonar": { "make": "EdgeTech", "model": "4200", "channels": 2 },
      "pings": 18240, "has_navigation": true, "nav_units": "latlon",
      "start_utc": "2026-09-12T05:10:02Z", "end_utc": "2026-09-12T05:19:52Z",
      "warnings": []
    },
    {
      "filename": "harbour_03.png", "valid": true, "format": "image_only", "size_bytes": 8321002,
      "width": 3200, "height": 1600, "has_navigation": false,
      "warnings": ["NO_NAVIGATION: attach a navigation CSV or continue without GPS"]
    }
  ]
}
```

### 2.3 `GET /surveys/{survey_id}`
```json
{
  "survey_id": "SRV-20260913-001",
  "name": "Chennai-Port-Line07",
  "created_utc": "2026-09-13T10:41:30Z",
  "source_files": ["line_07.xtf"],
  "job": { "job_id": "JOB-20260913-001", "status": "completed", "duration_s": 48.6 },
  "bbox": [80.3071, 13.0802, 80.3189, 13.0875],
  "track_length_km": 1.18,
  "summary": {
    "total_detections": 7,
    "by_class": { "ghost_net": 2, "shipwreck": 1, "pipe": 1, "cylinder": 1, "debris_other": 1, "unknown_anomaly": 1 },
    "by_tier": { "hazard": 3, "review": 3, "anomaly": 1 }
  },
  "report_urls": {
    "json": "/api/v1/surveys/SRV-20260913-001/report?format=json",
    "csv": "/api/v1/surveys/SRV-20260913-001/report?format=csv",
    "geojson": "/api/v1/surveys/SRV-20260913-001/report?format=geojson",
    "kml": "/api/v1/surveys/SRV-20260913-001/report?format=kml"
  }
}
```

### 2.3.1 `GET /surveys` (history, P1)

| Query param | Type | Example |
|---|---|---|
| `q` | text | `Chennai` (matches name, file, project) |
| `project` | string | `NIOT-Cleanup-2026` |
| `status` | csv enum | `running,failed` (job status) |
| `from` / `to` | ISO date | `2026-09-01` / `2026-09-30` |
| `limit` / `offset` | int | `50` / `0` |

**200 OK:** `{ "total": 4, "items": [ <Survey summary as §2.3 without report_urls> ] }`

### 2.3.2 `GET /surveys/{survey_id}/waterfall` (P1)

| Query param | Type | Default | Notes |
|---|---|---|---|
| `ping_start` / `ping_end` | int | required | Maximum 2,000 pings per request |
| `channel` | `processed` \| `raw` \| `despeckled` \| `texture` | `processed` | Matches the S-04 channel selector |
| `scale` | number | `1.0` | Downsampling factor for overview zoom levels |

**200 OK:** `image/png` tile with headers `X-Ping-Start`, `X-Ping-End`, `X-Nadir-Col`, `X-Ground-Res-M`. Not available for GeoTIFF inputs (`409 VALIDATION_ERROR`).

### 2.4 `GET /surveys/{survey_id}/detections`

| Query param | Type | Example |
|---|---|---|
| `class` | csv enum | `ghost_net,pipe` |
| `min_conf` / `max_conf` | number | `50` / `100` |
| `tier` | csv enum | `hazard,review` |
| `review_status` | csv enum | `pending` |
| `flags` | csv enum | `DROPOUT` |
| `bbox` | `minLon,minLat,maxLon,maxLat` | `80.30,13.08,80.32,13.09` |
| `sort` | `confidence\|-confidence\|area\|ping` | `-confidence` |
| `limit` / `offset` | int | `100` / `0` |

**200 OK**: `{ "total": 7, "items": [ <Detection>, ... ] }`. Detection object: [06-data-models §2](06-data-models.md#2-detection-object).

### 2.5 `PATCH /detections/{detection_id}` (P1)
```json
{ "review_status": "reclassified", "class": "debris_other", "note": "Tyre cluster, not a net", "reviewer": "analyst-02" }
```
Allowed `review_status`: `confirmed`, `rejected`, `reclassified`, `pending` (`pending` is used for undo).
When `review_status = "rejected"`, `reject_reason` is required: `rock`, `shadow`, `ripples`, `noise`, `other`. It is stored for hard-negative mining.

```json
{ "review_status": "rejected", "reject_reason": "rock", "note": "Boulder cluster", "reviewer": "analyst-02" }
```
**200 OK** returns the updated detection. **400 VALIDATION_ERROR** if `reject_reason` is missing for a rejection.

### 2.6 `GET /surveys/{survey_id}/report`
| Param | Values | Default |
|---|---|---|
| `format` | `json`, `csv`, `geojson`, `kml` | `json` |
| `scope` | `all`, `filtered` (uses the same query params as §2.4), `hazards` | `all` |
| `include_rejected` | `true`, `false` | `false` |

Response: file download with `Content-Disposition: attachment; filename="SRV-20260913-001_report.csv"`.

### 2.7 `GET /jobs/{job_id}`
```json
{
  "job_id": "JOB-20260913-001",
  "status": "running",
  "stage": "detect",
  "percent": 46.0,
  "eta_s": 22,
  "pings_done": 8400,
  "pings_total": 18240,
  "stage_timings_ms": { "validate": 120, "parse": 3900, "preprocess": 7400, "detect": 9100 },
  "warnings": [ { "code": "HIGH_MOTION", "ping_start": 6120, "ping_end": 6660 } ]
}
```

### 2.8 `GET /health`
```json
{ "status": "ok", "version": "0.3.0", "gpu": { "available": true, "name": "NVIDIA RTX 3060" },
  "runtime": "tensorrt", "models_loaded": true, "offline_tiles": true }
```

## 3. WebSocket events — `/ws/jobs/{job_id}`

Server → client messages. Each has `type`, `job_id`, `seq` (monotonic) and `ts`.

| `type` | When | Payload |
|---|---|---|
| `progress` | ≤ every 5 s and at stage changes | `stage`, `percent`, `eta_s`, `pings_done`, `pings_total` |
| `track` | After each chunk | `points: [[lat, lon], …]`, `ping_start`, `ping_end` |
| `detection` | New detection | `detection` (full object) |
| `detection_update` | After cross-chunk/cross-line merge changes a detection | `detection` |
| `detection_removed` | Duplicate removed during merge | `detection_id`, `merged_into` |
| `warning` | Quality event or recoverable error | `code`, `message`, `ping_start`, `ping_end` |
| `done` | Job finished | `status`, `summary`, `report_urls`, `mosaic` |
| `error` | Job failed | `code`, `message` |

```json
{ "type": "progress", "job_id": "JOB-20260913-001", "seq": 41, "ts": "2026-09-13T10:42:01Z",
  "stage": "detect", "percent": 46.0, "eta_s": 22, "pings_done": 8400, "pings_total": 18240 }
```
```json
{ "type": "warning", "job_id": "JOB-20260913-001", "seq": 42, "ts": "2026-09-13T10:42:02Z",
  "code": "DROPOUT", "message": "212 dropout pings masked", "ping_start": 9120, "ping_end": 9332 }
```
```json
{ "type": "done", "job_id": "JOB-20260913-001", "seq": 97, "ts": "2026-09-13T10:42:19Z",
  "status": "completed_with_warnings",
  "summary": { "total_detections": 7, "by_tier": { "hazard": 3, "review": 3, "anomaly": 1 } },
  "report_urls": { "json": "/api/v1/surveys/SRV-20260913-001/report?format=json" },
  "mosaic": { "url": "/files/SRV-20260913-001/mosaic.png", "bounds": [[13.0802, 80.3071], [13.0875, 80.3189]] } }
```

**Client → server:** `{ "type": "ping" }` keep-alive; `{ "type": "resume", "after_seq": 40 }` to replay missed events after reconnecting. The server keeps the last 1,000 events per job.

## 4. Error model

All errors use this shape:

```json
{ "error": { "code": "UNSUPPORTED_FORMAT", "message": "File type .bmp is not supported", "details": { "filename": "scan.bmp" } } }
```

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad parameter or options JSON |
| 400 | `NAV_CSV_INVALID` | Missing required nav CSV columns |
| 404 | `NOT_FOUND` | Survey / job / detection doesn't exist |
| 409 | `JOB_NOT_CANCELLABLE` | Job already finished |
| 413 | `FILE_TOO_LARGE` | Exceeds `max_upload_gb` |
| 415 | `UNSUPPORTED_FORMAT` | File type not supported |
| 422 | `CORRUPT_HEADER` | File can't be parsed |
| 422 | `CRS_REQUIRED` | Projected coordinates without known EPSG |
| 500 | `INTERNAL_ERROR` | Unexpected failure (see logs with `job_id`) |
| 503 | `MODELS_NOT_LOADED` | Model files missing or failed to load |

## 5. CLI equivalent

```text
sonarsentinel detect line_07.xtf --out results/ --formats json,csv,geojson,kml
sonarsentinel detect harbour_03.png --nav harbour_03_nav.csv --utm-epsg 32644 --out results/
sonarsentinel detect mosaic_A.tif --min-conf 50 --no-anomaly
sonarsentinel validate line_07.xtf
sonarsentinel serve --host 0.0.0.0 --port 8000
```
