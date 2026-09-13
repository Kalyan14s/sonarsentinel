# S-01 · Upload / New Analysis

[← Wireframes index](README.md) · **Priority:** P0 · **Requirements:** FR-UI-01, FR-ING-01…07, US-01, US-07

## Purpose
Let the user add sonar logs, see immediately whether each file is usable (and whether it has GPS), attach navigation for plain images, set options and start processing.

## Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     [Upload]   Live Map    Review (5)    Reports    History     Settings  (?)  |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|  NEW SURVEY ANALYSIS                                                                             |
|  Upload a raw side-scan sonar log. Detections will appear on the map as they are found.          |
|                                                                                                  |
|  +----------------------------------------------------------+  +-------------------------------+ |
|  |                                                          |  | SUPPORTED INPUTS              | |
|  |                          /\                              |  |                               | |
|  |                         /  \                             |  | [ok]   .xtf   GPS in pings    | |
|  |                          ||                              |  | [ok]   .tif   GeoTIFF mosaic  | |
|  |             Drag & drop sonar files here                 |  | [ok]   .png / .jpg + nav .csv | |
|  |                 or  [ Browse files ]                     |  | [beta] .jsf  .sl2  .sl3       | |
|  |                                                          |  |                               | |
|  |    .xtf  .tif  .png  .jpg  .csv    (max 2 GB per file)   |  | [ Download nav CSV template ] | |
|  |                                                          |  | [ Try a sample survey ]       | |
|  +----------------------------------------------------------+  +-------------------------------+ |
|                                                                                                  |
|  FILES (3)                                                                                       |
|  +---------------------------------------------------------------------------------------------+ |
|  | [x] line_07.xtf    1.4 GB   XTF - EdgeTech 4200 - 2 ch - 18,240 pings   [ok] GPS found  [X] | |
|  | [x] mosaic_A.tif   220 MB   GeoTIFF - EPSG:32644 - 0.10 m/px            [ok] Georef     [X] | |
|  | [x] harbour_03.png 8 MB     Image - 3200 x 1600 px                      [!] No GPS      [X] | |
|  |    `-- Attach navigation CSV:  [ Choose .csv ]   or   [ Continue without GPS ]              | |
|  +---------------------------------------------------------------------------------------------+ |
|                                                                                                  |
|  v Advanced options                                                                              |
|  +---------------------------------------------------------------------------------------------+ |
|  | Survey name [ Chennai-Port-Line07     ]      Project   [ NIOT-Cleanup-2026       ]          | |
|  | Coordinates (o) Auto-detect  ( ) UTM zone [ 44N v ]    Resolution  [ 0.10 m v ]             | |
|  | Layback     (o) Auto  ( ) Off  ( ) Manual [    ] m     Model       [ yolo11s-seg v1.2 v ]   | |
|  | Anomaly scan[x] Scan for ghost nets and unknown objectsMin. shown  [ 30 % ]                 | |
|  +---------------------------------------------------------------------------------------------+ |
|                                                                                                  |
|                                                               [ Cancel ]   [ > Start analysis ]  |
+--------------------------------------------------------------------------------------------------+
```

## Phone wireframe (< 600 px)

```text
+------------------------------------------+
| (~) SonarSentinel                    [=] |
+------------------------------------------+
| NEW SURVEY ANALYSIS                      |
| +--------------------------------------+ |
| |             /\                       | |
| |     Tap to choose files              | |
| |    .xtf .tif .png .jpg .csv          | |
| +--------------------------------------+ |
| line_07.xtf           [ok] GPS       [X] |
| harbour_03.png        [!] No GPS     [X] |
|   [ Attach nav CSV ]                     |
| > Advanced options                       |
|                                          |
| [ > Start analysis                     ] |
+------------------------------------------+
```

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Drop zone | Drag & drop or browse; multiple files; highlights on drag-over | — |
| 2 | Supported inputs panel | Static help; template download; sample survey loads a bundled NOAA-derived demo file | Static asset |
| 3 | File list row | Name, size, detected format, sonar info, GPS status badge, remove button | `POST /surveys/validate` |
| 4 | Nav CSV attach | Shown only for files without navigation; validates columns inline | `POST /surveys/validate` |
| 5 | Advanced options | Collapsed by default (remembers last state); defaults from Settings | `GET /settings` |
| 6 | Start analysis | Disabled until ≥ 1 valid file and every no-GPS file has a nav CSV or "Continue without GPS" | `POST /surveys` → navigate to S-02 |

## Interactions

1. The user drops files and each row shows a spinner while `POST /surveys/validate` runs (header-only read; fast).
2. The row updates with a badge: `[ok] GPS found`, `[ok] Georef`, `[!] No GPS`, or `[X] Unsupported` (red, with the reason).
3. For `[!] No GPS`: attach a CSV (validated immediately) or explicitly choose **Continue without GPS**, which sets `allow_no_gps=true` and shows the note "Results will have pixel coordinates only".
4. For projected coordinates with unknown CRS, the UTM zone selector becomes required and is highlighted.
5. **Start analysis** uploads with a progress bar per file, then redirects to **S-02 Live Map** with the `job_id`.

## States

| State | Display |
|---|---|
| Empty | Drop zone only; Start disabled |
| Validating | Row spinner "Reading header…" |
| Uploading | Per-file progress bar + total; Cancel available |
| Invalid file | Red row: "`.bmp` is not supported — use .xtf, .tif, .png, .jpg" |
| Too large | Red row: "2.6 GB exceeds the 2 GB limit (change in Settings)" |
| Nav CSV invalid | Inline list of missing columns + template link |
| Server offline | Banner: "Backend not reachable — check that the service is running" + Retry |

## Acceptance notes
- Validation feedback appears within 2 s for a 2 GB `.xtf` (header-only read).
- A first-time user can start an analysis without opening Advanced options.
