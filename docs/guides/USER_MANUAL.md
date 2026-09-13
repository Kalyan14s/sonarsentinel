# SonarSentinel — User Manual

| | |
|---|---|
| **Version** | v1.0 (pre-release) · 2026-09-13 |
| **Audience** | Marine analysts, survey operators, recovery team leads |
| **Owner** | Frontend Engineer (R5) with PM (R6) |

> This manual describes the planned behaviour defined in the [wireframes](../wireframes/README.md). Screenshots will be added once the dashboard is built (Milestone M5). Features marked **(P1)** or **(P2)** may not be in the first release.

---

## Contents
1. [What SonarSentinel does](#1-what-sonarsentinel-does)
2. [Key concepts](#2-key-concepts)
3. [Getting started](#3-getting-started)
4. [Preparing your data](#4-preparing-your-data)
5. [Running an analysis](#5-running-an-analysis)
6. [Using the live map](#6-using-the-live-map)
7. [Inspecting a detection](#7-inspecting-a-detection)
8. [How to act on results](#8-how-to-act-on-results)
9. [Reviewing detections (P1)](#9-reviewing-detections-p1)
10. [Waterfall viewer (P1)](#10-waterfall-viewer-p1)
11. [Downloading reports](#11-downloading-reports)
12. [History and settings (P1)](#12-history-and-settings-p1)
13. [Command-line use](#13-command-line-use)
14. [On-board edge console (P2)](#14-on-board-edge-console-p2)
15. [Troubleshooting and FAQ](#15-troubleshooting-and-faq)
16. [Reference: quality flags](#16-reference-quality-flags)

---

## 1. What SonarSentinel does

SonarSentinel reads side-scan sonar survey data and automatically finds **man-made objects** on the seafloor: ghost nets, shipwrecks, pipes, cylinders and other debris. It also flags **unknown anomalies**. For each object it gives:

- **Where it is**: latitude/longitude (WGS84), depth and a position uncertainty
- **What it probably is**: class and a **confidence percentage**
- **How big it is**: length, width, area, estimated height
- **Why it was flagged**: the evidence behind the confidence
- **Data-quality warnings**: e.g. missing sonar pings or heavy vehicle motion

Results appear on a map while the file is processing and can be downloaded as JSON, CSV, GeoJSON or KML.

> **Important:** SonarSentinel is a decision-support tool. Always have a qualified person verify high-impact decisions (e.g. dive operations, navigation warnings), especially for ghost nets, which the model has mostly learned from simulated examples.

## 2. Key concepts

| Concept | Meaning |
|---|---|
| **Detection** | One object found by the system |
| **Class** | Ghost net `<>` diamond · Shipwreck `/\` triangle · Pipe `==` bar · Cylinder `()` circle · Other debris `[]` square · Unknown anomaly `??` dashed hexagon |
| **Confidence (0–100%)** | Calibrated estimate that the detection is a real man-made object of that class. About 80% means roughly 8 in 10 such detections are correct on our validation data |
| **Alert tier** | **HAZARD** ≥ 80% · **REVIEW** 50–79% · **ANOMALY** 30–49% with an unusual-seabed signal · hidden below that |
| **Track** | The path of the sonar during the survey. Red hatched = missing data; amber dashed = heavy motion |
| **Uncertainty (± m)** | Estimated horizontal position error. The object is very likely within this radius |
| **Port / starboard** | Left / right side of the sonar's direction of travel |
| **Ping** | One sonar pulse; one row of the sonar image |

## 3. Getting started

1. Open the dashboard in Chrome, Firefox or Edge: `http://localhost:8080` (or the address given by your administrator).
2. The top bar shows **Upload · Live Map · Review · Reports · History · Settings**.
3. An **Offline — local tiles** badge means the map is using locally stored map tiles. Everything still works.
4. If you see "Backend not reachable", ask your operator to check the service ([Operations Runbook](OPERATIONS_RUNBOOK.md)).

## 4. Preparing your data

| You have | Use it like this | GPS result |
|---|---|---|
| **`.xtf` file** from the sonar system | Upload directly | ✅ Positions from the file |
| **GeoTIFF sonar mosaic** | Upload directly | ✅ Positions from the image's georeferencing |
| **PNG/JPG waterfall image + navigation CSV** | Upload both | ✅ Positions from the CSV |
| **PNG/JPG image only** | Upload and choose *Continue without GPS* | ❌ Pixel positions only |
| `.jsf`, `.sl2`, `.sl3` (P1) | Upload directly | ✅ Positions from the file |

**Navigation CSV:** download the template from the Upload screen. Required columns: `ping, lat, lon, heading_deg, slant_range_m`. Optional: `altitude_m, sensor_depth_m, time_utc, roll_deg, pitch_deg`. Full specification: [Data Models §5](../architecture/06-data-models.md#5-navigation-csv-input-format).

**Tips**
- Upload the original sonar file where possible. Screenshots of vendor software lose resolution and position.
- Files up to **2 GB** each are accepted by default.
- If your coordinates are in UTM metres, know the **UTM zone** (e.g. 44N for Chennai).

## 5. Running an analysis

1. Go to **Upload**.
2. **Drag and drop** your file(s) or click **Browse files**.
3. Check each file's status badge:
   - `[ok] GPS found` / `[ok] Georef`: ready.
   - `[!] No GPS`: attach a navigation CSV, or click **Continue without GPS**.
   - `[X]`: file can't be used; the message explains why.
4. *(Optional)* Open **Advanced options**:
   - **Survey name / Project**: for finding it later.
   - **Coordinates**: *Auto-detect* (default), or pick a UTM zone.
   - **Resolution**: 0.10 m/pixel by default.
   - **Layback**: *Auto* uses the file's towfish data.
   - **Anomaly scan**: keep **on** to look for ghost nets and unknown objects.
   - **Min. shown**: hides detections below this confidence on the map (you can change it later).
5. Click **Start analysis**. You are taken to the **Live Map**.

## 6. Using the live map

### 6.1 While processing
- The **progress bar** shows the stage (Reading → Cleaning → Detecting → Scoring → Geotagging → Report), percentage and time left.
- The **track** grows as data is processed, and **markers** appear as objects are found.
- **Stop** cancels processing but keeps what was found so far.

### 6.2 Reading markers
- **Shape and colour = class**. **Solid** = HAZARD · **outline** = REVIEW · **dashed** = ANOMALY.
- Zoomed out, nearby markers are grouped into a numbered cluster; zoom in or click to expand.
- Zoomed in close, the object's **footprint** (outline and size) is drawn.
- **Hover** for class and confidence; **click** to open details.

### 6.3 Filters and layers (left panel)
- **Class**: tick or untick classes.
- **Confidence**: drag the slider to set the minimum and maximum.
- **Alert tier** and **Flagged only**: focus on specific tiers or detections with data-quality issues.
- **Layers**: track, sonar mosaic (with opacity) (P1), footprints.

### 6.4 Detection list (right panel)
Sorted by confidence by default; you can also sort by size, class or position along the track. Clicking a card selects it on the map.

### 6.5 Warnings
The bottom bar shows warning counts (e.g. *DROPOUT*, *HIGH_MOTION*). Click **view** to zoom to the affected part of the track. Detections there may be less reliable; consider re-surveying.

### Keyboard shortcuts
`F` filters · `L` list · `↑`/`↓` move selection · `Enter` open detail · `Esc` close

## 7. Inspecting a detection

Clicking a detection opens the **detail panel**:

| Section | What to look at |
|---|---|
| **Header** | Class, confidence, tier badge, detection ID. Use `[<] [>]` to step through detections |
| **Sonar image** | Close-up of the sonar data. Switch overlays: **Mask** (object outline), **Shadow** (the acoustic shadow used as evidence), **Anomaly** (heatmap of unusual seabed), **Off** |
| **Location** | Latitude/longitude in decimal degrees and degrees-minutes-seconds, with **copy** buttons; depth; **± uncertainty** (also drawn as a circle on the map) |
| **Size** | Length × width, area, estimated height above the seabed (from the shadow) and orientation |
| **Why this confidence** | Bars for each piece of evidence: *Detector* (AI model), *Anomaly* (unusual seabed), *Shadow check* (does it cast a shadow like a real object?), *False-positive filter* (shape and texture), *Seen in other lines*, and any *Quality penalties* |
| **Sonar reference** | File, side, ping numbers, range and time. **Open in waterfall** (P1) shows the raw sonar |
| **Quality flags** | Warnings that affect reliability (see [§16](#16-reference-quality-flags)) |
| **Review** (P1) | Confirm, reject or reclassify, with a note |

## 8. How to act on results

| Tier | Suggested action |
|---|---|
| **HAZARD (≥ 80%)** | Quickly check the sonar image; include in the hazard list / recovery plan; share coordinates with the dive or ROV team |
| **REVIEW (50–79%)** | An analyst should look at the sonar image and confirm or reject before acting |
| **ANOMALY (30–49%)** | Something unusual that may not be man-made. Consider a closer re-survey (shorter range, higher frequency) if the area matters |
| **Hidden (< 30%)** | Normally ignore; check only for thorough searches |

**Extra care when:**
- The detection has **DROPOUT**, **HIGH_MOTION** or **NEAR_NADIR** flags.
- **Uncertainty** is large (e.g. > 10 m). Plan a wider search pattern.
- The class is **ghost net** and there is no analyst confirmation yet.
- **LAYBACK_ESTIMATED** or **HEADING_FROM_COG** flags are present (position may be less accurate).

## 9. Reviewing detections (P1)

1. Open **Review** from the top bar (the number shows pending items).
2. Choose which tiers to include (default: REVIEW and ANOMALY).
3. For each item, look at the image and evidence, then press:
   - `C` **Confirm**: it is a real object of that class.
   - `R` **Reject**: choose a reason (Rock, Shadow, Ripples, Noise, Other).
   - `K` **Reclassify**: choose the correct class.
   - `S` skip · `N`/`P` next/previous · `Z` undo (within 10 s).
4. Review decisions update the reports and help improve future models.

## 10. Waterfall viewer (P1)

Shows the sonar data as a scrolling image (port on the left, starboard on the right).
- Scroll along the survey; `Ctrl` + scroll to zoom.
- Detection boxes and data-quality bands are drawn on top.
- The mini map shows where you are; the timeline at the bottom shows all detections.
- **Channel** switches between Processed, Raw, Despeckled and Texture views. **Gain/Contrast/Palette** change only the display, not the results.

## 11. Downloading reports

**Quick download:** buttons in the bottom bar of the Live Map.
**Full options:** **Reports** page.

| Format | Best for | How to open |
|---|---|---|
| **JSON** | Complete record, integration with other software | Any text editor; programs |
| **CSV** | Spreadsheets, hazard lists | Excel, LibreOffice Calc |
| **GeoJSON** (P1) | GIS analysis | QGIS: *Layer → Add Layer → Add Vector Layer* |
| **KML** (P1) | Google Earth, sharing with field teams | Google Earth: *File → Open* |

**Scope options:** all detections, current map filters, hazards only, confirmed only. Rejected detections are excluded unless you choose to include them.

**Main CSV columns:** `detection_id, class, confidence, alert_tier, lat, lon, depth_m, uncertainty_m, length_m, width_m, area_m2, height_m, orientation_deg, side, ping_start, ping_end, time_utc, quality_flags, review_status`. Full list: [Data Models §3.1](../architecture/06-data-models.md#31-csv-one-row-per-detection-utf-8-comma-separated-header-row).

**To use positions on a handheld GPS:** open the KML/GeoJSON in QGIS or Google Earth and export to the format your GPS unit supports (e.g. GPX).

## 12. History and settings (P1)

- **History:** search past surveys; **Open** shows them on the map; the **[…]** menu lets you re-run with current settings, go to reports, or delete. Failed surveys show the reason and a **Fix** button.
- **Settings:** default confidence tiers, anomaly scan, resolution, UTM zone, layback, basemap (online/offline) and coordinate format. Changes apply to new analyses only. Some settings may need administrator rights.

## 13. Command-line use

For batch processing without the dashboard:

```bash
sonarsentinel validate line_07.xtf
sonarsentinel detect line_07.xtf --out results/ --formats json,csv,geojson,kml
sonarsentinel detect harbour_03.png --nav harbour_03_nav.csv --utm-epsg 32644 --out results/
sonarsentinel detect mosaic_A.tif --min-conf 50
```

Results are written to the `--out` folder: `report.json`, `report.csv`, and `chips/` with sonar image close-ups.

## 14. On-board edge console (P2)

On vessels with an edge computer, a simplified screen shows:
- Processing status and whether it is **keeping up** with the sonar (real-time factor)
- **Hazard alerts** (≥ 80%) with position and size; **Mark** sends the position as a waypoint if integrated
- Data-quality warnings along the track

When a new hazard pops up, press **Acknowledge**. Full review happens later on shore.

## 15. Troubleshooting and FAQ

| Problem / question | What to do |
|---|---|
| My file shows `[X] Unsupported` | Check the file type. Export `.xtf` from your acquisition software if possible |
| `[!] No GPS` for an `.xtf` | The file has no navigation. Attach a navigation CSV or ask the survey team for a file with navigation |
| "Choose a UTM zone" is required | Your file uses metre coordinates without a zone. Select the correct UTM zone |
| Processing is very slow | The server may be running without a GPU. Ask your operator; smaller files process faster |
| No detections found | Try lowering the confidence filter; check warnings; the area may be clear |
| Objects appear on land or far from the track | Coordinates may be misread (wrong UTM zone, units). Report it to your operator; don't use those positions |
| Many detections on a rocky area | Rocky seabeds cause more false alarms. Focus on HAZARD tier and review others |
| Why is a ghost net only 55%? | Nets are weak sonar reflectors and hard to confirm. Check the image and consider a re-survey |
| Can I trust the depth? | Depth comes from sensor depth + altitude. It is blank if the file lacks these |
| The map is blank | Offline tiles may not cover this area; the data is still correct. Switch basemap in Settings |
| "Reconnecting…" banner | Temporary connection loss; results are kept and updates resume automatically |

## 16. Reference: quality flags

| Flag | Meaning | Effect |
|---|---|---|
| `DROPOUT` | Part of the object lies on missing sonar data | Lower confidence; verify |
| `HIGH_MOTION` | Vehicle rolled, pitched or turned sharply | Shape and position less reliable |
| `NEAR_NADIR` | Directly below the sonar, where images are distorted | Size/shape less reliable |
| `SURFACE_RETURN_BAND` | In a band affected by sea-surface echoes | Possible false alarm |
| `TILE_EDGE` | Object was cut at an image boundary | Size may be underestimated |
| `GPS_INTERPOLATED` | Position estimated between GPS fixes | Larger uncertainty |
| `LAYBACK_ESTIMATED` | Sonar towfish position estimated from cable length | Larger uncertainty along track |
| `HEADING_FROM_COG` | Direction estimated from track, not compass | Larger across-track uncertainty |
| `NO_ALTITUDE_BOTTOM_TRACKED` | Sonar height estimated from the image | Slightly less accurate ranges/sizes |
| `NOT_GEOTAGGED` | No navigation available | Pixel positions only |

More terms: [PRD Glossary](../PRD.md#18-glossary).
