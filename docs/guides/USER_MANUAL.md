# SonarSentinel — User Manual

| | |
|---|---|
| **Version** | v1.0 (release-candidate draft) · 2026-09-14 |
| **Audience** | Marine analysts, survey operators, recovery team leads |
| **Owner** | Frontend Engineer (R5) with PM (R6) |

> This manual describes the Sprint 6 build (checked against the implementation for ST-114). Screenshots will be added from the running dashboard on real survey data. Features marked **(not in this release)** are planned but not built.

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
9. [Reviewing detections](#9-reviewing-detections)
10. [Waterfall viewer (not in this release)](#10-waterfall-viewer-not-in-this-release)
11. [Downloading reports](#11-downloading-reports)
12. [History and settings](#12-history-and-settings)
13. [Command-line use](#13-command-line-use)
14. [On-board edge use](#14-on-board-edge-use)
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

> **Important:** SonarSentinel is a decision-support tool. Always have a qualified person verify high-impact decisions (e.g. dive operations, navigation warnings). The current detector is an early baseline: it was trained on few real objects and no real ghost nets, so treat every detection as a lead to check, not a finding.

## 2. Key concepts

| Concept | Meaning |
|---|---|
| **Detection** | One object found by the system |
| **Class** | Ghost net `<>` diamond · Shipwreck `/\` triangle · Pipe `==` bar · Cylinder `()` circle · Other debris `[]` square · Unknown anomaly `??` dashed hexagon |
| **Confidence (0–100%)** | Calibrated estimate that the detection is a real man-made object of that class. About 80% means roughly 8 in 10 such detections are correct on the calibration data |
| **Alert tier** | **HAZARD** ≥ 80% · **REVIEW** 50–79% · **ANOMALY** 30–49% with an unusual-seabed signal · hidden below that |
| **Track** | The path of the sonar during the survey. Red hatched = missing data; amber dashed = heavy motion |
| **Uncertainty (± m)** | Estimated horizontal position error (1 σ). The object is likely within this radius |
| **Port / starboard** | Left / right side of the sonar's direction of travel |
| **Ping** | One sonar pulse; one row of the sonar image |

## 3. Getting started

1. Open the dashboard in Chrome, Firefox or Edge: `http://localhost:8080` for a Docker installation, `http://localhost:5173` for a development setup, or the address given by your administrator.
2. The top bar shows **Upload · Live Map · Review · Reports · History · Settings**.
3. An **Offline — local tiles** badge means the map uses locally stored map tiles (your operator must install a tile file and you must choose *Offline* in Settings). Everything else works the same.
4. If you see "Backend not reachable", ask your operator to check the service ([Operations Runbook](OPERATIONS_RUNBOOK.md)).

## 4. Preparing your data

| You have | Use it like this | GPS result |
|---|---|---|
| **`.xtf` file** from the sonar system | Upload directly | ✅ Positions from the file |
| **GeoTIFF sonar mosaic** | Upload directly | ✅ Positions from the image's georeferencing |
| **PNG/JPG waterfall image + navigation CSV** | Upload both | ✅ Positions from the CSV |
| **PNG/JPG image only** | Upload and choose *Continue without GPS* | ❌ Pixel positions only |
| `.jsf`, `.sl2`, `.sl3` | **Not in this release** — export to `.xtf` from the acquisition software | — |

**Navigation CSV:** download the template from the Upload screen. Required columns: `ping`, `slant_range_m`, and either `lat, lon` or `easting, northing` (with the UTM zone). Optional: `heading_deg` (otherwise estimated from the track and flagged `HEADING_FROM_COG`), `time_utc`, `altitude_m`, `sensor_depth_m`, `speed_mps`, `roll_deg`, `pitch_deg`. Rows between listed pings are interpolated and flagged `GPS_INTERPOLATED`. Full specification: [Data Models §5](../architecture/06-data-models.md#5-navigation-csv-input-format).

**Tips**
- Upload the original sonar file where possible. Screenshots of vendor software lose resolution and position.
- Files up to **2 GB** each are accepted by default.
- If your coordinates are in UTM metres, know the **UTM zone** (e.g. 44N for Chennai).

## 5. Running an analysis

1. Go to **Upload**.
2. **Drag and drop** your file(s) or click **Browse files**. Each file is checked as soon as it is added.
3. Check each file's status badge:
   - `[ok] GPS found` / `[ok] Georef`: ready.
   - `[!] No GPS`: attach a navigation CSV, or click **Continue without GPS**.
   - `[X]`: file can't be used; the message explains why.
4. *(Optional)* Open **Advanced options** (your choices are remembered on this computer):
   - **Survey name / Project**: for finding it later.
   - **Coordinates**: *Auto-detect* (default), or enter the UTM EPSG code.
   - **Resolution**: 0.10 m/pixel by default.
   - **Layback**: *Auto* estimates the towfish position when the file only has the ship's position; *Off*; or *Manual* with a distance in metres.
   - **Anomaly scan**: keep **on** to look for unknown objects.
   - **Min. shown**: hides detections below this confidence on the map (you can change it later).
5. Click **Start analysis**. The files upload with a progress bar (you can cancel), then you are taken to the **Live Map**.

Several `.xtf` lines of one survey can be uploaded together; the same object seen on more than one line is merged into one detection.

## 6. Using the live map

### 6.1 While processing
- The **progress bar** shows the current stage, the percentage and the estimated time left.
- The **track** grows as data is processed, and **markers** appear as objects are found.
- **Stop** asks for confirmation, then cancels processing; detections found so far stay visible (a report is only produced for completed runs).
- If the connection drops, a **Reconnecting…** banner appears and updates resume without duplicates.

### 6.2 Reading markers
- **Shape and colour = class**. **Solid** = HAZARD · **outline** = REVIEW · **dashed** = ANOMALY.
- Zoomed out, nearby markers are grouped into a numbered cluster; zoom in or click to expand.
- Zoomed in close (level 17 and above), the object's **footprint** is drawn.
- When processing finishes, a **sonar mosaic** of the survey is shown under the markers where one could be produced.
- **Hover** for class and confidence; **click** to open details.

### 6.3 Filters (left panel)
- **Class**: tick or untick classes.
- **Confidence**: drag the slider to set the minimum and maximum (default 30–100%).
- **Alert tier**: HAZARD, REVIEW, ANOMALY and hidden (hidden is off by default).
- **Quality flags** and **review status**: focus on detections with data-quality issues or on pending/confirmed/rejected items.

Filters are part of the page address, so you can bookmark or share a filtered view.

### 6.4 Detection list (right panel)
Sorted by confidence by default; you can also sort by size, class or position along the track. Clicking a row opens the detection.

### 6.5 Warnings
The bottom bar shows the number of warnings (e.g. *DROPOUT*, *HIGH_MOTION*). Open the list and click one to zoom to the affected part of the track. Detections there may be less reliable; consider re-surveying. The bottom bar also has quick downloads for all four report formats.

### Keyboard shortcuts
`F` filters · `L` list · `↑`/`↓` move selection · `Enter` open detail · `Esc` close

## 7. Inspecting a detection

Opening a detection shows the **detail panel**:

| Section | What to look at |
|---|---|
| **Header** | Class, confidence, tier badge, detection ID (click to copy). Use `[<] [>]` to step through the filtered list |
| **Sonar image** | Close-up of the sonar data. Switch overlays: **Mask** (object outline), **Shadow** (area checked for the acoustic shadow), **Anomaly** (heatmap of unusual seabed), **None**. "Preview not generated" means no image was saved for this detection |
| **Location** | Latitude/longitude in decimal degrees and degrees-minutes-seconds, with a **copy** button; depth; **± uncertainty** |
| **Size** | Length × width, area, estimated height above the seabed (from the shadow, "n/a" when no shadow is usable) and orientation |
| **Why N%?** | Bars for each piece of evidence: *Detector* (AI model), *Anomaly* (unusual seabed), *Shadow* (does it cast a shadow like a real object?), *False-positive filter* (shape and texture), *Persistence* (seen on other lines), the *quality penalties*, and the combined score before and after calibration |
| **Sonar reference** | File, side, ping numbers, range and time (pixel box for images without GPS) |
| **Quality flags** | Warnings that affect reliability (see [§16](#16-reference-quality-flags)) |
| **Review** | Confirm, reject (with a reason) or reclassify, with a note |

## 8. How to act on results

| Tier | Suggested action |
|---|---|
| **HAZARD (≥ 80%)** | Quickly check the sonar image; include in the hazard list / recovery plan; share coordinates with the dive or ROV team |
| **REVIEW (50–79%)** | An analyst should look at the sonar image and confirm or reject before acting |
| **ANOMALY (30–49%)** | Something unusual that may not be man-made. Consider a closer re-survey (shorter range, higher frequency) if the area matters |
| **Hidden (< 30%)** | Normally ignore; check only for thorough searches. With the current baseline models most detections on real seabed are hidden |

**Extra care when:**
- The detection has **DROPOUT**, **HIGH_MOTION**, **NEAR_NADIR** or **SURFACE_RETURN_BAND** flags.
- **Uncertainty** is large (e.g. > 10 m). Plan a wider search pattern.
- The class is **ghost net** and there is no analyst confirmation yet.
- **LAYBACK_ESTIMATED** or **HEADING_FROM_COG** flags are present (position may be less accurate).

## 9. Reviewing detections

1. Open **Review** from the top bar and choose the survey (the latest is selected).
2. Choose which tiers to include (default: REVIEW and ANOMALY). The queue starts with the lowest-confidence item.
3. For each item, look at the image, the mini map and the evidence, add a note if useful, then press:
   - `C` **Confirm**: it is a real object of that class.
   - `R` **Reject**, then `1`–`5` for the reason: Rock, Shadow, Ripples, Noise, Other.
   - `K` **Reclassify**, then `1`–`6` for the correct class.
   - `S` skip · `N`/`P` next/previous · `Z` undo the last decision (within 10 s) · `Esc` cancel a choice.
4. The queue moves to the next item automatically. If a decision can't be saved, "Not saved — retrying" appears; use **Retry** if it persists.
5. When the queue is empty, download the updated report. Review decisions appear in every report download and are stored as training labels for future models.

## 10. Waterfall viewer (not in this release)

A scrolling view of the raw sonar data with detection boxes is planned (ST-097) but not built in this release. Use the sonar image close-ups in the detail panel.

## 11. Downloading reports

**Quick download:** buttons in the bottom bar of the Live Map (all detections).
**Full options:** **Reports** page.

| Format | Best for | How to open |
|---|---|---|
| **JSON** | Complete record, integration with other software | Any text editor; programs |
| **CSV** | Spreadsheets, hazard lists | Excel, LibreOffice Calc |
| **GeoJSON** | GIS analysis | QGIS: *Layer → Add Layer → Add Vector Layer* |
| **KML** | Google Earth, sharing with field teams | Google Earth: *File → Open* |

**Scope options:** all detections, current map filters, hazards only, confirmed only. Rejected detections are excluded unless you choose to include them. GeoJSON and KML are not available for images without GPS. While a survey is still processing, the Reports page marks downloads as partial.

**Main CSV columns:** `detection_id, class, confidence, alert_tier, lat, lon, depth_m, uncertainty_m, length_m, width_m, area_m2, height_m, orientation_deg, side, ping_start, ping_end, time_utc, quality_flags, review_status`. Full list: [Data Models §3.1](../architecture/06-data-models.md#31-csv-one-row-per-detection-utf-8-comma-separated-header-row).

**To use positions on a handheld GPS:** open the KML/GeoJSON in QGIS or Google Earth and export to the format your GPS unit supports (e.g. GPX).

## 12. History and settings

- **History:** search past surveys by name or file, filter by project, status and recent dates (7/30/90 days). **Open** shows a survey on the map (and follows it live if it is still running). The **[…]** menu offers **Reports**, **Re-run** (opens Upload with the survey name filled in; add the files again) and **Delete** (after confirmation; running surveys must be stopped first; review labels are kept). Failed surveys show the error code and a **Fix** button that returns to Upload.
- **Settings:** detector model and runtime, minimum detector score, anomaly scan and threshold, confidence tiers (HAZARD must be above REVIEW, REVIEW above ANOMALY), default map confidence, basemap (online or offline — offline only when your operator has installed a tile file), coordinate format, resolution, chunk size, layback and cluster radius. A read-only **System** panel shows storage, upload limit and available runtimes. Changes apply to new analyses only; unsaved changes are protected when you leave the page.

## 13. Command-line use

For batch processing without the dashboard:

```bash
sonarsentinel validate line_07.xtf
sonarsentinel detect line_07.xtf --out results/ --formats json,csv,geojson,kml
sonarsentinel detect harbour_03.png --nav harbour_03_nav.csv --utm-epsg 32644 --out results/
sonarsentinel detect mosaic_A.tif --min-conf 50 --out results/
sonarsentinel watch /acquisition --out /data/results --alerts-min-conf 80   # process new files as they arrive
```

Results are written to `results/<survey_id>/`: `report.json`, `report.csv` (and `report.geojson`/`report.kml` when requested), `chips/` with sonar close-ups and, for geotagged surveys, `mosaic.tif`, `mosaic.png` and `mosaic_bounds.json`.

## 14. On-board edge use

On vessels with an edge computer, run `sonarsentinel watch` on the acquisition folder (or the `docker-compose.edge.yml` service). Each new sonar file is processed once its size stops changing, its report is written to the output folder, and every detection above the alert threshold is printed and appended to `alerts.log` as a compact line (`SS1|survey|detection|class|confidence|lat|lon|size|depth|time`). Processing starts when a file is complete; lines still being recorded are not processed chunk by chunk. A dedicated on-board console screen (S-08) is **not in this release**; full review happens on shore.

## 15. Troubleshooting and FAQ

| Problem / question | What to do |
|---|---|
| My file shows `[X] Unsupported` | Check the file type. Export `.xtf` from your acquisition software if possible |
| `[!] No GPS` for an `.xtf` | The file has no navigation. Attach a navigation CSV or ask the survey team for a file with navigation |
| "Choose a UTM zone" is required | Your file uses metre coordinates without a zone. Enter the UTM EPSG code in Advanced options |
| Processing is very slow | The server may be running without a GPU (reports then carry `CPU_FALLBACK` if a GPU runtime was requested). Ask your operator; smaller files process faster |
| No detections found | Try lowering the confidence filter and ticking *hidden*; check warnings; the area may be clear |
| Objects appear on land or far from the track | Coordinates may be misread (wrong UTM zone, units). Report it to your operator; don't use those positions |
| Many detections on a rocky area | Rocky seabeds cause more false alarms. Focus on HAZARD tier and review others |
| Why is a ghost net only 55%? | Nets are weak sonar reflectors and hard to confirm. Check the image and consider a re-survey |
| Can I trust the depth? | Depth comes from sensor depth + altitude. It is blank if the file lacks these |
| The map is blank | Offline tiles may not cover this area, or the computer has no internet for online tiles; the data is still correct. Switch basemap in Settings |
| "Reconnecting…" banner | Temporary connection loss; results are kept and updates resume automatically |
| Report warning `CHUNK_SKIPPED` | Part of the file could not be processed; the warning lists the ping range. Re-export that part of the survey |

## 16. Reference: quality flags

| Flag | Meaning | Effect |
|---|---|---|
| `DROPOUT` | Part of the object lies on missing sonar data | Lower confidence; verify |
| `HIGH_MOTION` | Vehicle rolled, pitched or turned sharply | Lower confidence; shape and position less reliable |
| `NEAR_NADIR` | Directly below the sonar, where images are distorted | Size/shape less reliable |
| `SURFACE_RETURN_BAND` | In a band affected by sea-surface echoes | Possible false alarm |
| `TILE_EDGE` | Object was cut at the edge of the sonar swath | Size may be underestimated |
| `GPS_INTERPOLATED` | Position estimated between GPS fixes | Larger uncertainty |
| `LAYBACK_ESTIMATED` | Sonar towfish position estimated from cable length | Larger uncertainty along track |
| `HEADING_FROM_COG` | Direction estimated from track, not compass | Larger across-track uncertainty |
| `NO_ALTITUDE_BOTTOM_TRACKED` | Sonar height estimated from the image | Slightly less accurate ranges/sizes |
| `NOT_GEOTAGGED` | No navigation available | Pixel positions only |

Report-level warnings (shown in the warnings list and the report's processing section) include `TRUNCATED_FILE`, `CHUNK_SKIPPED`, `CPU_FALLBACK` and `RULE_BASED_DETECTOR` (the trained model was not available, so a simple rule-based detector was used).

More terms: [PRD Glossary](../PRD.md#18-glossary).
