# S-03 · Detection Detail

[← Wireframes index](README.md) · **Priority:** P0 (review actions P1) · **Requirements:** FR-UI-06, FR-CONF-06, FR-GEO-01…08, US-03, US-04, US-09

## Purpose
Show everything needed to trust and act on one detection: the sonar evidence, exact location, size, why the confidence is what it is, data-quality flags, and review actions.

Opens as a **right-side drawer over S-02** (desktop) or a **full-height bottom sheet** (phone).

## Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     [Live Map]  Review (5)    Reports    History     Settings  (?)  |
+----------------------------------------------+---------------------------------------------------+
|                                              | < Back to list         D3 of 7   [<] [>]      [X] |
|                                              |                                                   |
|                                              | <> GHOST NET         87%   [ HAZARD ]             |
|           . - - - .                          | SRV-20260913-001-D0003                            |
|         .           .                        | +----------------------------------+              |
|        .     <>D3    .                       | | .:.:.:.:.:.:.:.:.:.:.:.:.:.:.    | 256x256      |
|         .           .                        | | .:.:+ - - - - - - +.:.:.:.:.:    |  0.10 m/px   |
|           ' - - - '                          | | .:.:| #=#=#=# ##  |  .:.:.:      |              |
|       +/- 4.2 m circle                       | | .:.:| =#=#=#=#=#= | shadow ->    | near->far    |
|                                              | | .:.:+ - - - - - - +.:.:.:.:.:    |              |
|  S..........................>                | | .:.:.:.:.:.:.:.:.:.:.:.:.:.:.    |              |
|                                              | +----------------------------------+              |
|                                              | Overlay: (o) Mask ( ) Shadow ( ) Anomaly ( ) Off  |
|                                              | [ Open in waterfall ]   [ Zoom map to object ]    |
|                                              +---------------------------------------------------+
|                                              | LOCATION (WGS84)                                  |
|                                              | Lat   13.084120 N   13 05' 02.83" N       [copy]  |
|                                              | Lon   80.312750 E   80 18' 45.90" E       [copy]  |
|                                              | Depth 18.5 m         Uncertainty +/- 4.2 m        |
|                                              +---------------------------------------------------+
|                                              | SIZE                                              |
|                                              | 6.2 m x 3.1 m  Area 14.8 m2     Height ~0.4 m     |
|                                              | Orientation 12 deg from N                         |
|                                              +---------------------------------------------------+
|                                              | WHY 87%?                                          |
|                                              | Detector              [########..]  0.81          |
|                                              | Anomaly               [#########.]  0.92          |
|                                              | Shadow check          [######....]  0.64          |
|                                              | False-positive filter [########..]  0.88          |
|                                              | Seen in other lines   [#####.....]  0.50 (1 view) |
|                                              | Quality penalties     none                        |
|                                              | Fused 0.78  ->  calibrated 87%                    |
|                                              +---------------------------------------------------+
|                                              | SONAR REFERENCE                                   |
|                                              | line_07.xtf - starboard - pings 10,398-10,466     |
|                                              | Ground range 23.7 m - 2026-09-12 05:17:21 UTC     |
|                                              | Quality flags: none                               |
|                                              +---------------------------------------------------+
|                                              | REVIEW                                            |
|                                              | [ Confirm C ]  [ Reject R ]  [ Reclassify K v ]   |
|                                              | Note [                                        ]   |
+----------------------------------------------+---------------------------------------------------+
```

## Variant — detection with quality flags and low confidence

```text
+--------------------------------------------------+
| ?? UNKNOWN ANOMALY            41%   [ ANOMALY ]  |
| [!] DROPOUT   [!] HIGH_MOTION                    |
| Penalties: dropout -0.20, motion -0.10           |
| "Data quality is poor here. Consider             |
|  re-surveying this area."                        |
+--------------------------------------------------+
```

## Variant — not geotagged input

```text
+--------------------------------------------------+
| LOCATION                                         |
| [!] No GPS for this image                        |
| Pixel box  x 1204-1266, y 830-861                |
| [ Attach navigation CSV and re-run ]             |
+--------------------------------------------------+
```

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Header | Class icon + label, confidence %, tier badge, full ID (click to copy), previous/next in current filtered order | `GET /detections/{id}` |
| 2 | Sonar chip | 256×256 crop; overlay toggle: mask outline, shadow region, anomaly heatmap, none; click to enlarge (1:1 and 2×) | `GET /detections/{id}/chip.png?overlay=…` |
| 3 | Location | Decimal degrees (6 dp) and DMS; copy buttons (copies "13.084120, 80.312750"); depth; uncertainty (also drawn as a circle on the map) | Detection `position` |
| 4 | Size | Length × width, area, estimated height (shown as "n/a" if the shadow is unusable), orientation | Detection `dimensions` |
| 5 | Why this confidence | Bars for each score component, penalties, fused → calibrated; info icon explains each factor in plain words | Detection `scores` |
| 6 | Sonar reference | File, side, ping range, ground range, time; "Open in waterfall" → S-04 at this ping | Detection `sonar_ref` |
| 7 | Quality flags | Badges with tooltips (e.g. DROPOUT: "Part of this object lies on missing sonar data") | Detection `quality_flags` |
| 8 | Review (P1) | Confirm / Reject / Reclassify dropdown (6 classes) + note; shows reviewer and time after action | `PATCH /detections/{id}` |

## Interactions

| Action | Result |
|---|---|
| `[<]` / `[>]` or `↑/↓` | Previous/next detection in the current filtered and sorted list; map follows |
| Overlay radio | Swaps chip image; remembers choice for the session |
| Copy coordinates | Toast "Copied 13.084120, 80.312750" |
| Confirm | Badge "Confirmed by analyst-02"; marker gains a check mark; moves to next pending item if "auto-advance" is on |
| Reject | Asks for an optional reason (Rock / Shadow / Ripple / Noise / Other); marker greyed out and excluded from default exports |
| Reclassify | Choose new class; marker icon changes; report shows `review.status = reclassified` |
| `Esc` / `[X]` | Close drawer; selection cleared |

## States
- **Loading:** skeleton blocks for chip and fields; header shows class/confidence from the list immediately.
- **Chip unavailable:** placeholder "Preview not generated" + [Retry].
- **Review failed:** inline error; buttons re-enabled; nothing lost.

## Acceptance notes
- All PRD §9 minimum fields are visible without scrolling on a 1080p display, except the score breakdown and review sections.
- DD and DMS values always match the exported CSV/JSON exactly.
