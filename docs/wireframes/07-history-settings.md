# S-07 · Survey History & Settings

[← Wireframes index](README.md) · **Priority:** P1 · **Requirements:** FR-UI-11, FR-UI-12, FR-UI-14, US-14

## Part A — Survey History

### Purpose
Find past surveys, see their status and results at a glance, reopen them on the map, or re-download reports.

### Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     Live Map    Review (5)    Reports    [History]   Settings  (?)  |
+--------------------------------------------------------------------------------------------------+
| SURVEY HISTORY                                                            [ + New analysis ]     |
| Search [ name, file, project...   ]  Project [ All v ]  Status [ All v ]  Date [ 30 days v ]     |
+--------------------------------------------------------------------------------------------------+
|  NAME / FILE                DATE (UTC)       STATUS         DETECTIONS        HAZARDS   ACTIONS  |
+--------------------------------------------------------------------------------------------------+
|  Chennai-Port-Line07        2026-09-13       [ok] Done (!2) <>2 /\1 ==1 ()1 []1 ??1  3  [Open]   |
|  line_07.xtf - 1.4 GB       10:41                                                       [...]    |
+--------------------------------------------------------------------------------------------------+
|  Chennai-Port-Line08        2026-09-13       [###.....] 31% <>1                      0  [Open]   |
|  line_08.xtf - 1.2 GB       10:52                                                       [...]    |
+--------------------------------------------------------------------------------------------------+
|  Ennore-Mosaic-A            2026-09-11       [ok] Done      /\2 []4                  2  [Open]   |
|  mosaic_A.tif - 220 MB      16:05                                                       [...]    |
+--------------------------------------------------------------------------------------------------+
|  Harbour-03                 2026-09-10       [X] Failed     CRS_REQUIRED             -  [Fix]    |
|  harbour_03.png - 8 MB      09:12                                                       [...]    |
+--------------------------------------------------------------------------------------------------+
| Showing 4 of 4                                                [...] = Re-run - Reports - Delete  |
+--------------------------------------------------------------------------------------------------+
```

### Components and interactions

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Search & filters | Text search over name, file, project; project, status, date filters | `GET /surveys?q=&project=&status=&from=&to=` |
| 2 | Survey row | Name, file, size, date, status (with warnings count), detections by class icon, hazard count | Same |
| 3 | Open | Opens S-02 with that survey loaded; running jobs reconnect to the WebSocket | — |
| 4 | Row menu `[...]` | Re-run (new job with current models/settings), Reports (S-06), Delete (confirm dialog; removes files) | `POST /surveys` (re-run), `DELETE /surveys/{id}` |
| 5 | Failed row | Shows error code; `[Fix]` reopens S-01 with the file and the relevant field highlighted (e.g. UTM zone) | Job error |

**States:** empty ("No surveys yet" + New analysis), loading skeleton rows, delete in progress (row greyed out).

---

## Part B — Settings

### Purpose
Adjust defaults and thresholds without editing config files. Changes apply to new jobs; existing reports keep the config hash they were produced with.

### Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     Live Map    Review (5)    Reports    History     [Settings](?)  |
+---------------------+----------------------------------------------------------------------------+
| > Detection         | DETECTION & CONFIDENCE                                                     |
|   Processing        |                                                                            |
|   Geo & maps        | Detector model  [ yolo11s-seg-sonar 1.2.0 v ]         [ Model card ]       |
|   System            | Anomaly scan    [x] Enabled   threshold [ 0.50 ]                           |
|   About             | Min. raw score  [ 0.20 ]                                                   |
|                     |                                                                            |
|                     | Alert tiers     Hazard >= [ 80 ]%   Review >= [ 50 ]%   Anomaly >= [ 30 ]% |
|                     |                 0 [====|=====|======|=========] 100                        |
|                     |                                                                            |
|                     | Map filter      Show confidence >= [ 30 ]%                                 |
|                     |                                                                            |
|                     +----------------------------------------------------------------------------+
|                     | PROCESSING                                                                 |
|                     | Resolution      [ 0.10 m v ]                                               |
|                     | Despeckle       [ Lee 5x5 v ]                                              |
|                     | Motion limits   Roll [ 5 ] deg   Pitch [ 5 ] deg   Yaw rate [ 3 ] deg/ping |
|                     | Chunk size      [ 2000 ] pings, overlap [ 200 ]                            |
|                     | Runtime         (o) Auto  ( ) GPU PyTorch  ( ) ONNX CPU  ( ) TensorRT      |
|                     |                                                                            |
|                     +----------------------------------------------------------------------------+
|                     | GEO & MAPS                                                                 |
|                     | Default UTM zone[ Auto v ]      Layback [ Auto v ]                         |
|                     | Basemap         (o) Online OSM  ( ) Offline [ basemap.mbtiles ]            |
|                     | Cluster radius  [ 5 ] m (same object across survey lines)                  |
|                     | Coordinates     (o) Decimal degrees  ( ) DMS                               |
|                     |                                                                            |
|                     +----------------------------------------------------------------------------+
|                     | SYSTEM                                                                     |
|                     | Backend         [ok] v0.3.0 - GPU: RTX 3060 - Runtime: TensorRT            |
|                     | Storage         412 GB free - Max upload [ 2 ] GB                          |
|                     | Work files      [ ] Keep intermediates (debug)                             |
|                     |                                                                            |
|                     |                                   [ Reset to defaults ] [ Save changes ]   |
+---------------------+----------------------------------------------------------------------------+
```

### Components and interactions

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Section nav | Scrolls to section; highlights current | — |
| 2 | Model selector | Lists registry versions with key metrics; "Model card" opens metrics and intended use | `GET /models` |
| 3 | Tier thresholds | Numeric inputs linked to a multi-handle slider; validation keeps Hazard > Review > Anomaly | `GET/PUT /settings` |
| 4 | Processing | Resolution, despeckle, motion limits, chunking, runtime (unavailable runtimes disabled) | Same |
| 5 | Geo & maps | UTM/layback defaults, basemap source with path check, cluster radius, coordinate format | Same |
| 6 | System | Health info, storage, upload limit, keep work files | `GET /health` |
| 7 | Save / Reset | Unsaved-changes guard when leaving the page; toast on save | `PUT /settings` |

**Rules:** threshold changes don't alter existing reports; the S-02 slider is session-only and doesn't change Settings. Access control (P2): only `admin` can change models, runtime and storage.
