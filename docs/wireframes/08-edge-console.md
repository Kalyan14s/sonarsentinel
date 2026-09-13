# S-08 · Edge Console (On-board)

[← Wireframes index](README.md) · **Priority:** P2 · **Requirements:** FR-UI-15, FR-OPS-06, NFR-03, US-11

## Purpose
A minimal, glanceable status and alert screen for a small display on the survey vessel or AUV support station (e.g. a 7" touchscreen next to the sonar operator). It confirms the edge runner is keeping up with acquisition and shows high-confidence hazards immediately.

**Design constraints:** high contrast (readable in sunlight and at night; dark theme by default), large touch targets (≥ 48 px), no map tiles required, works fully offline, low CPU/GPU overhead.

## Wireframe — 7" landscape (≈ 1024 × 600)

```text
+----------------------------------------------------------------------+
| SONARSENTINEL EDGE        [ok] RUNNING      GPU 61C  12 W  05:17:40Z |
+----------------------------------------------------------------------+
| NOW PROCESSING                    | THROUGHPUT                       |
| line_07.xtf                       | 6.4x real time                   |
| ping 10,466 (live, growing file)  | lag behind sonar: 1.2 s          |
| [##################.....]  76%    | INT8 TensorRT - 38 tiles/s       |
+-----------------------------------+----------------------------------+
| HAZARD ALERTS (>= 80%)                               sent: 3/3       |
+----------------------------------------------------------------------+
|                                                                      |
|  <> GHOST NET           87%     13.08412 N  80.31275 E     05:17:21  |
|    6.2 x 3.1 m - stbd 23.7 m - depth 18.5 m             [ Mark ]     |
|                                                                      |
+----------------------------------------------------------------------+
|  == PIPE                82%     13.08359 N  80.31020 E     05:14:02  |
|    21.0 x 0.6 m - port 31.2 m - depth 17.9 m            [ Mark ]     |
+----------------------------------------------------------------------+
|  /\ SHIPWRECK           91%     13.08301 N  80.30842 E     05:12:47  |
|    38.0 x 9.0 m - port 18.4 m - depth 17.2 m            [ Mark ]     |
+----------------------------------------------------------------------+
| TRACK                                                                |
| S...........................<>........==/\..............>            |
| [!] DROPOUT 05:15:10-05:15:16                                        |
+----------------------------------------------------------------------+
| [ Pause ]   [ Review count: 3 ]   [ Export to USB ]   [ Settings ]   |
+----------------------------------------------------------------------+
```

## Wireframe — alert pop-up (new hazard)

```text
+--------------------------------------------------+
|                                                  |
|          !!  NEW HAZARD DETECTED  !!             |
|                                                  |
|    <> GHOST NET                   87%            |
|    13.084120 N   80.312750 E                     |
|    Starboard 23.7 m - 6.2 x 3.1 m                |
|                                                  |
|    [ Acknowledge ]      [ Mark waypoint ]        |
|                                                  |
+--------------------------------------------------+
```

## Compact alert message (low-bandwidth link)

Sent for each hazard when a satellite/acoustic/radio link is configured (≤ 256 bytes):

```text
SS1|SRV-20260913-001|D0003|ghost_net|87|13.08412|80.31275|6.2x3.1|18.5|2026-09-12T05:17:21Z
```

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Status bar | Running / paused / error; GPU temperature and power; UTC clock | Edge runner health (`tegrastats`) |
| 2 | Now processing | Current file, ping, live/growing indicator, progress | Edge runner events |
| 3 | Throughput | Real-time factor (processing speed ÷ acquisition speed), lag, runtime, tiles/s; turns amber if < 1.5×, red if < 1× | Edge runner metrics |
| 4 | Hazard alerts | Only `hazard` tier; newest first; large type; `[ Mark ]` sends the position to the navigation system as a waypoint (NMEA/file export, if integrated) | Edge `detection` events |
| 5 | Track strip | Schematic along-track strip with hazard symbols and quality warnings; no basemap needed | Track + quality events |
| 6 | Actions | Pause / resume processing, count of items for later review on shore, export results to USB, settings (thresholds, alert link) | Edge runner API |
| 7 | New-hazard pop-up | Appears for new hazards; optional audible beep; must be acknowledged | `detection` event |

## States

| State | Display |
|---|---|
| Idle (no files) | "Waiting for sonar data in /acquisition" with a pulsing dot (static if reduced motion) |
| Falling behind (< 1×) | Red throughput panel: "Falling behind — switch to faster model?" [ Yes ] |
| Overheating / throttling | Amber status: "Thermal throttling — performance reduced" |
| Link down | Alerts marked "queued (3)"; sent automatically when the link returns |
| Error | Red status with code; last good results remain visible; [ Restart runner ] |

## Acceptance notes
- A new hazard appears on the console within 5 s of its ping being processed.
- All text readable from 1 m; minimum 18 px body text, 28 px for alert class and confidence.
- The console uses < 5% CPU on the Jetson while idle and doesn't reduce detection throughput by more than 5%.
