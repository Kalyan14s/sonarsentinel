# Sprint 5 Plan — Dashboard (P0 freeze)

| | |
|---|---|
| **Sprint** | S5 · 2026-10-19 → 2026-10-23 (illustrative dates, see [Project Plan](PROJECT_PLAN.md)); started early on 2026-09-14 |
| **Milestone / gate** | **M5** · **G4** (all P0 stories Done; AC-01…AC-05 and AC-07 pass end to end) |
| **Sprint goal** | *An analyst uploads a survey, watches detections stream onto the map, filters and inspects them, reviews them and downloads JSON/CSV/GeoJSON/KML — with every value identical across screen and exports.* |
| **Capacity** | 6 people; committed **56 points** (backlog allocation) plus 25 items carried over from Phase 5 |

**Related:** [Product Backlog](PRODUCT_BACKLOG.md) · [TODO Phase 6](../../TODO.md#phase-6--sprint-5--dashboard-p0-freeze) · [API](../architecture/05-api-specification.md) · [Wireframes](../wireframes/README.md) · [Sprint 4 plan](SPRINT_4_PLAN.md)

---

## 1. Committed stories

| Story | Title | Pts | Owner | Acceptance (short) | Tests | Can finish without people/data? |
|---|---|---|---|---|---|---|
| ST-083 | WebSocket events with `seq` and replay | 5 | R4 | Reconnect replays without duplicates | TC-WS-001…006, TC-UI-014 | Yes |
| ST-084 | Surveys, detections, track, report endpoints | 3 | R4 | Filter params per API spec | TC-API-004, 007, TC-REP-007 | Yes |
| ST-086 | Review `PATCH` + label store | 3 | R4 | Label record written per decision | TC-API-005 | Yes |
| ST-092 | Live map (S-02) | 8 | R5 | AC-01 passes; 2,000 markers smooth | TC-UI-003, 007, 009 | Automated parts yes; frame-rate check on a real browser is manual |
| ST-093 | Filters + detection list | 5 | R5 | Filter update < 100 ms for 2,000 items | TC-UI-004 | Yes |
| ST-094 | Detection detail drawer (S-03) | 5 | R5 | Values match exports exactly | TC-UI-005, 006 | Yes |
| ST-095 | Reports & export screen (S-06) | 3 | R5 | AC-07 downloads work | TC-UI-008 | Yes (QGIS/Google Earth/Excel checks are manual) |
| ST-035 | Position uncertainty budget | 2 | R3 | `uncertainty_m` from config defaults | TC-GEO-010 | Yes |
| ST-036 | GCP-based georeferenced mosaic | 5 | R3 | Aligns with track in Leaflet and QGIS | TC-GEO-011 | Residual test yes; QGIS overlay manual |
| ST-047 | Surface-return band mask | 2 | R2 | Band found on a shallow-water sample | TC-PRE-012 | Synthetic yes; real shallow-water file needed for the AC |
| ST-072 | GeoJSON + KML export | 3 | R3 | Correct positions in QGIS / Google Earth | TC-REP-003, 004 | Structure tests yes; viewer checks manual |
| ST-056 ⭐ | U-Net mask refiner | 5 | R1 | Mask IoU improves on holdout | TC-DET-010 | **No** — needs GPU training (stretch, drop first) |
| ST-100 | ONNX export + ONNX Runtime CPU path | 3 | R6 | CPU run meets NFR-02 | TC-EDGE-001, TC-PERF-002 | Export and parity yes; NFR-02 needs the reference 1 km line |
| | **Total** | **52** | | | | |

Other tasks: automate TC-E2E-001…003, TC-WS-001…006, TC-UI-001…010; demo assets A1–A3; User Manual screenshots; P0 freeze (R6 decision).

## 2. Decisions made at planning (recorded in ADR-018)

1. **WebSocket:** client sends `resume` first and `ping` every 20 s (server `pong` without `seq`); replay from the in-memory buffer, then `job.log.jsonl`; server closes with 1000 after `done`/`error`, 4404 for unknown jobs.
2. **Terminal events come from the job manager after results are stored**, so a client that downloads the report on `done` never races; `done` carries `report_urls` for all four formats; cancelled jobs keep the detections found so far.
3. **Detection filters** add `max_conf`, `review_status`, `flags`, `bbox` and sort values `-area`, `-ping`, `class`; one filter module serves the API, the mock and filtered exports, and the dashboard filters client-side with the same rules.
4. **Report scopes** `all | filtered | hazards | confirmed` (confirmed = confirmed or reclassified), `include_rejected=false` by default.
5. **Track endpoint:** GeoJSON FeatureCollection with the track `LineString` and one `LineString` per quality event.
6. **Label store:** `labels/<yyyy-mm>/<detection_id>/label.json` + chip; undo removes it, the REVIEW table keeps history.
7. **Surface band:** every in-band detection is flagged `SURFACE_RETURN_BAND`; linear track-parallel detections are dropped only when `preprocess.surface_return_mask` is on.
8. **Uncertainty defaults** in `geo.uncertainty` (GNSS 2 m, heading 2°, altitude 0.5 m, time 0.2 s, estimated layback 10%).
9. **Mosaic:** rasterio GCP thin-plate-spline warp to EPSG:4326 (no separate GDAL bindings), PNG + bounds for Leaflet.
10. **ONNX:** `detection.runtime: auto` uses `best.onnx` next to the weights when ONNX Runtime is installed, otherwise PyTorch.

## 3. Constraints

- **Model quality:** AC-05 (ghost-net recall ≥ 80%) needs GPU-trained detectors (carried ST-051); G4 cannot fully pass on the CPU baseline.
- **Demo assets:** A1/A2 need a NOAA charted-wreck XTF and chart; only A3 (synthetic ghost net) can be produced locally.
- **Manual checks:** QGIS, Google Earth, Excel/LibreOffice, screen reader and real-browser frame rate need a person.
- **Offline maps:** the map uses online tiles until ST-099 (Sprint 6).

## 4. Exit criteria (M5 / G4)

- [ ] All P0 stories Done *(Sprint 5 P0 code done; open: ST-092 browser frame-rate check and carried P0 data/labelling items — [TSR-M5](../testing/reports/TSR-M5.md))*
- [ ] AC-01…AC-05 and AC-07 pass end to end *(AC-01…03 at API level and AC-04 pass; AC-05 needs GPU-trained models; AC-07 viewer checks manual)*

## 5. Risks this sprint

| Risk | Trigger | Response |
|---|---|---|
| Dashboard slow with 2,000 markers | Filter > 100 ms or visible jank | Clustering, incremental layer updates, windowed list |
| WebSocket events lost on reconnect | TC-WS-004 or TC-UI-014 fails | Replay from `job.log.jsonl`; dedupe by `seq` and `detection_id` |
| Screen and exports disagree | TC-UI-005 / AC-01 CSV↔JSON mismatch | Exports built from the stored detection JSON; shared DMS formatting tests |
| ONNX results differ from PyTorch | TC-EDGE-001 parity fails | Keep PyTorch as `auto` fallback; export with fixed input size |
