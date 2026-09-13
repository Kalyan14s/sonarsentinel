# S-02 · Live Map

[← Wireframes index](README.md) · **Priority:** P0 · **Requirements:** FR-UI-02…05, FR-UI-07, FR-UI-08, FR-UI-13, US-02, US-08, US-16

## Purpose
The main workspace. While processing, the track line grows and detections appear as markers in real time. After processing, it is where users filter, explore and select detections and download reports.

## Desktop wireframe — processing in progress

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     [Live Map]  Review (5)    Reports    History     Settings  (?)  |
+--------------------------------------------------------------------------------------------------+
| Chennai-Port-Line07 - line_07.xtf   [##########..........] 46%  Detecting - ETA 00:22  [ Stop ]  |
+----------------------+---------------------------------------------------+-----------------------+
| FILTERS              | [Street|Satellite|Offline]              [+] [-]   | DETECTIONS (7)        |
|                      |                                                   | Sort: [ Conf. v ]     |
| CLASS                |                                                   +-----------------------+
| [x] <> Ghost net   2 |                                                   | <> Ghost net  D3 87%  |
| [x] /\ Shipwreck   1 |            <>D3                      ??D7         |  HAZARD  6.2 x 3.1 m  |
| [x] == Pipe        1 |    /\D1             ==D4                          |  13.084120, 80.312750 |
| [x] () Cylinder    1 | S....................xxxxxxxx............>        +-----------------------+
| [x] [] Debris      1 |                ()D5          []D6          <>D2   | /\ Shipwreck  D1 91%  |
| [x] ?? Anomaly     1 |                                                   |  HAZARD  38 x 9 m     |
|                      |                                                   |  13.083011, 80.308420 |
| CONFIDENCE           | S = start   > = vessel now                        +-----------------------+
| 30 [==o=======] 100  | xxxx = dropout / high motion                      | == Pipe  D4      82%  |
|                      |                                                   |  HAZARD  21 x 0.6 m   |
| ALERT TIER           |                                                   |  13.083590, 80.310200 |
| [x] Hazard         3 |                                                   +-----------------------+
| [x] Review         3 |                                                   | ?? Anomaly  D7   41%  |
| [x] Anomaly        1 |                                                   |  ANOMALY  2.1 x 1.4 m |
| [ ] Hidden         4 |                                                   |  13.085300, 80.316900 |
|                      |                                                   +-----------------------+
| QUALITY              | LEGEND  <> net  /\ wreck  == pipe                 |  ... 3 more           |
| [ ] Flagged only     |         () cyl  [] debris  ?? anomaly             |                       |
|                      |                                                   |                       |
| LAYERS               |                                                   |                       |
| [x] Track            |                                                   |                       |
| [x] Mosaic  [==--]   |                                                   |                       |
| [x] Footprints       |                                                   |                       |
+----------------------+---------------------------------------------------+-----------------------+
| 7 detections: 3 hazard, 3 review, 1 anomaly   [!] 2 warnings: DROPOUT, HIGH_MOTION [view]        |
| Reports:  [ JSON ]  [ CSV ]  [ GeoJSON ]  [ KML ]             Pointer: 13.084551 N, 80.311902 E  |
+--------------------------------------------------------------------------------------------------+
```

## Desktop — completed state (context bar only)

```text
+--------------------------------------------------------------------------------------------------+
| Chennai-Port-Line07 - line_07.xtf   [ok] Completed in 48.6 s - 2 warnings  [ > Review 3 items ]  |
+--------------------------------------------------------------------------------------------------+
```

## Phone wireframe (< 600 px)

```text
+------------------------------------------+
| (~) SonarSentinel              46%  [=]  |
+------------------------------------------+
| [ Filters v ]               [+] [-]      |
|                                          |
|         <>D3                ??D7         |
|   /\D1          ==D4                     |
| S.....................xxxxx.......>      |
|           ()D5        []D6               |
|                                          |
+------------------------------------------+
|                  -----                   |
| DETECTIONS (7)             [Download v]  |
| <> Ghost net  D3                    87%  |
|    HAZARD  13.084120, 80.312750          |
| /\ Shipwreck  D1                    91%  |
+------------------------------------------+
```
The bottom sheet can be dragged up to full height (list) or down (map only).

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Context bar | Survey name, file, stage + % + ETA, Stop (cancel job); after completion: duration, warnings, "Review n items" | WS `progress`, `done`; `POST /jobs/{id}/cancel` |
| 2 | Filters panel | Class checkboxes with live counts; confidence range slider; tier checkboxes; "flagged only"; changes apply instantly to map, list and filtered export | Client-side over loaded detections |
| 3 | Layers | Track, mosaic (with opacity), footprints (shown from zoom ≥ 17), uncertainty circles | `GET /surveys/{id}/track`, `/mosaic` |
| 4 | Map | Leaflet; basemap switcher; class+tier markers; clustering at low zoom; auto-fit to track on first events (until the user pans) | WS `track`, `detection` |
| 5 | Track line | Grows per chunk; `S` start; `>` current position; dropout (red hatched) and high-motion (amber dashed) segments | WS `track`, `warning` |
| 6 | Detection list | Cards: class icon, ID, confidence, tier badge, size, coordinates; sort by confidence / size / along-track position / class | Loaded detections |
| 7 | Status bar | Summary counts; warnings link; report downloads; pointer coordinates (DD; DMS on hover) | WS `done`; `GET /surveys/{id}/report` |

## Interactions

| Action | Result |
|---|---|
| New `detection` event | Marker drops in with a subtle highlight (no animation if reduced motion); list inserts in sort order; counts update |
| `detection_update` / `detection_removed` | Marker/list row updates or is removed; if the removed item was selected, selection moves to `merged_into` |
| Hover marker | Tooltip: class, confidence, tier |
| Click marker or list card | Selects it; map centres; opens **S-03 Detection Detail** drawer in the right panel |
| Hover list card | Highlights the corresponding marker |
| Click a warning in the status bar | Zooms to the affected track segment and lists ping ranges |
| Drag confidence slider | Markers and cards filter live; URL query string updates (shareable view) |
| Stop | Confirmation dialog: "Stop processing? Detections found so far are kept." |
| Keyboard | `F` focus filters, `L` focus list, `↑/↓` move selection, `Enter` open detail, `Esc` close detail |

## States

| State | Display |
|---|---|
| Connecting | Context bar "Connecting to job…"; map shows basemap only |
| Waiting for first chunk | "Reading sonar log…" with stage name |
| Processing, no detections yet | List: "No detections yet — scanning 18,240 pings" |
| Completed, zero detections | List: "No man-made objects detected above 30% confidence" + [Show low-confidence] |
| Not geotagged input | Map replaced by pixel image view with the same markers; banner "No GPS — coordinates shown in pixels" |
| WebSocket dropped | Banner "Reconnecting…"; resumes with `after_seq` without duplicate markers |
| Job failed | Red banner with error code and message; partial results remain visible |

## Acceptance notes
- The first marker appears within 15 s of the job starting if a detection exists in the first chunk (NFR-04).
- The map stays responsive (≥ 30 fps pan/zoom) with 2,000 markers (clustering enabled).
- Filter changes update map and list within 100 ms for 2,000 detections.
