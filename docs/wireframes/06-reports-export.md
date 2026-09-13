# S-06 · Reports & Export

[← Wireframes index](README.md) · **Priority:** P0 (JSON/CSV) · P1 (GeoJSON/KML, scope options) · P2 (PDF) · **Requirements:** FR-UI-07, FR-REP-01…06, US-06, US-12

## Purpose
Produce the structured anomaly report (location, dimensions, classification, confidence) in the format each user needs, with a preview of exactly what will be exported.

## Desktop wireframe

```text
+--------------------------------------------------------------------------------------------------+
| (~) SonarSentinel     Upload     Live Map    Review (5)    [Reports]  History     Settings  (?)  |
+--------------------------------------------------------------------------------------------------+
| REPORTS - Chennai-Port-Line07                   Survey [ SRV-20260913-001 v ]                    |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|  1. FORMAT                                                                                       |
|  +-------------------+  +--------------------+  +--------------------+  +--------------------+   |
|  | (o) JSON          |  | [x] CSV            |  | [x] GeoJSON        |  | [ ] KML            |   |
|  | Full report       |  | Spreadsheet        |  | QGIS / GIS         |  | Google Earth / GPS |   |
|  | + schema v1.0     |  | one row / object   |  | points + footprints|  | placemarks by class|   |
|  +-------------------+  +--------------------+  +--------------------+  +--------------------+   |
|  [ ] PDF summary (map snapshot + hazard table)            P2                                     |
|                                                                                                  |
|  2. SCOPE                                       3. OPTIONS                                       |
|  (o) All detections (7)                         [x] Include score breakdown                      |
|  ( ) Current map filters (5)                    [x] Include track line (GeoJSON/KML)             |
|  ( ) Hazards only (3)                           [ ] Include rejected detections                  |
|  ( ) Confirmed only (2)                         [ ] Include low-confidence (< 30%)               |
|                                                 Coordinates  (o) Decimal degrees  ( ) DMS        |
|                                                                                                  |
|  4. PREVIEW (CSV)                                                             7 rows - 23 columns|
|  +---------------------------------------------------------------------------------------------+ |
|  | detection_id  | class      | conf | tier  | lat      | lon      | L x W (m) | depth| review | |
|  |---------------------------------------------------------------------------------------------| |
|  | ...-001-D0001 | shipwreck  | 91.2 | hazard| 13.083011| 80.308420| 38.0 x 9.0| 17.2 | confirm| |
|  | ...-001-D0003 | ghost_net  | 87.4 | hazard| 13.084120| 80.312750| 6.2 x 3.1 | 18.5 | confirm| |
|  | ...-001-D0004 | pipe       | 82.0 | hazard| 13.083590| 80.310200| 21.0 x 0.6| 17.9 | pending| |
|  | ...-001-D0002 | ghost_net  | 58.3 | review| 13.082870| 80.314410| 3.4 x 2.0 | 18.8 | pending| |
|  | ...                                                                                         | |
|  +---------------------------------------------------------------------------------------------+ |
|                                                                                                  |
|  Files: SRV-20260913-001_report.json, .csv, .geojson                [ Download selected (3) ]    |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
|  PREVIOUS EXPORTS                                                                                |
|  2026-09-13 10:44   CSV - all (7)            analyst-02                      [ Download ]        |
|  2026-09-13 10:43   KML - hazards (3)        analyst-02                      [ Download ]        |
+--------------------------------------------------------------------------------------------------+
```

## Components

| # | Component | Behaviour | Data source |
|---|---|---|---|
| 1 | Survey selector | Defaults to the current survey | `GET /surveys` |
| 2 | Format cards | Multi-select; each card explains who it's for; KML/GeoJSON disabled with a tooltip for non-geotagged surveys | — |
| 3 | Scope | All / current filters (carried from S-02) / hazards / confirmed; counts shown live | `GET /surveys/{id}/detections` |
| 4 | Options | Score breakdown, track line, rejected, low-confidence, coordinate display (DMS only affects CSV display columns; JSON always uses decimal degrees) | — |
| 5 | Preview | First rows of the selected tabular format with horizontal scroll; switch tab per format (CSV / JSON tree / map preview for GeoJSON-KML) | Client-side from detections |
| 6 | Download | Single file, or a `.zip` when more than one format is selected | `GET /surveys/{id}/report?format=…&scope=…` |
| 7 | Previous exports | Audit list with re-download | `REPORT` table |

## Interactions
- Changing scope or options updates preview counts instantly.
- **Download selected** makes one request per format (zipped client-side or server-side).
- Reports always reflect the latest review decisions; the preview shows review status.
- Quick downloads in S-02's status bar use the defaults: all detections, score breakdown on.

## States
- **Processing not finished:** banner "Survey still processing — the report will include detections found so far"; download allowed and marked `partial` in metadata.
- **Not geotagged survey:** CSV/JSON only; lat/lon columns empty, pixel box columns added.

## Acceptance notes
- Downloaded JSON validates against `report-1.0.schema.json`.
- GeoJSON opens in QGIS and KML in Google Earth at the correct positions.
- Values in the preview are byte-identical to the downloaded file.
