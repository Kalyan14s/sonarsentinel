# SonarSentinel — Test Cases & Traceability

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Owner** | R6 (maintainer); module owners write and execute cases in their area |
| **Status** | Living document — add a case for every new requirement or bug fix |

**Related:** [Test Plan](TEST_PLAN.md) (levels, test data TD-xx, environments) · [PRD](../PRD.md)

**Columns:** **Lvl** = U unit · C component · I integration · A API · UI · E2E · M ML evaluation · S system · UAT. **Auto** = automated (✔) or manual (✋). **Pri** follows the requirement priority.

---

## 1. Ingestion (TC-ING)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-ING-001 | Reject unsupported extension | FR-ING-05 | `scan.bmp` | Validate/upload | `415 UNSUPPORTED_FORMAT` with filename in details | A | ✔ | P0 |
| TC-ING-002 | Reject corrupt XTF header | FR-ING-05 | TD-05 | Validate | `422 CORRUPT_HEADER`; no job created | C | ✔ | P0 |
| TC-ING-003 | Reject oversize file | FR-ING-01, 05 | Dummy > limit | Upload with limit set to 10 MB | `413 FILE_TOO_LARGE`; upload stream aborted | A | ✔ | P0 |
| TC-ING-004 | Invalid navigation CSV | FR-ING-03, 05 | CSV without `lat` | Validate with image | `400 NAV_CSV_INVALID` listing missing columns | A | ✔ | P0 |
| TC-ING-005 | Parse synthetic XTF exactly | FR-ING-01, 06, 08 | TD-01 | Read to `SonarLog` | Ping count, channels, samples and every nav field equal generated values | C | ✔ | P0 |
| TC-ING-006 | Parse public XTF variants | FR-ING-01, 06 | TD-02 | Read each file; compare 10 pings with reference viewer | No errors; nav values match; plausible ranges | C | ✔/✋ | P0 |
| TC-ING-007 | Detect coordinate units | FR-ING-07 | TD-01 (NavUnits 3 and 0) | Read both | Geographic accepted; projected without EPSG → `CRS_REQUIRED` | C | ✔ | P0 |
| TC-ING-008 | UTM override equivalence | FR-ING-07 | TD-01 lat/lon + UTM copies | Process both | Detection positions differ < 0.1 m | I | ✔ | P0 |
| TC-ING-009 | GeoTIFF reader | FR-ING-02 | TD-03 | Read; convert 5 pixels | Matches rasterio/QGIS within 1 pixel | C | ✔ | P0 |
| TC-ING-010 | Image + sparse nav CSV | FR-ING-03 | TD-04 sparse | Process | Positions interpolated; `GPS_INTERPOLATED` flag | I | ✔ | P0 |
| TC-ING-011 | Image without navigation | FR-ING-04 | TD-06 | Process with `allow_no_gps` | lat/lon `null`; `pixel_bbox` present; `NOT_GEOTAGGED` | I | ✔ | P0 |
| TC-ING-012 | Truncated XTF | NFR-08 | TD-05 truncated | Process | Valid pings processed; `TRUNCATED_FILE` warning; job `completed_with_warnings` | I | ✔ | P0 |
| TC-ING-013 | JSF / SL2 / SL3 parsing | FR-ING-09 | Sample files | Read | Valid `SonarLog` per format | C | ✔ | P1 |
| TC-ING-014 | Batch upload of multiple lines | FR-ING-10 | 2 × TD-01 lines | Upload together | One survey; both tracks; cross-line merge applied | I | ✔ | P1 |

## 2. Preprocessing (TC-PRE)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-PRE-001 | Bottom tracking accuracy | FR-PRE-01 | TD-01 (altitude removed) | Run bottom tracking | Estimated altitude within 10% of true | C | ✔ | P0 |
| TC-PRE-002 | Water column masked | FR-PRE-01 | TD-01 with object placed in water column | Full pipeline | No detection inside water-column mask | I | ✔ | P0 |
| TC-PRE-003 | Slant-range correction | FR-PRE-02 | TD-01 object at 20 m ground range | Correct | Object at column `nadir ± 200 px` (±1 px) | C | ✔ | P0 |
| TC-PRE-004 | Along-track resampling | FR-PRE-07 | TD-01 with variable speed | Resample | 5 m object spans 50 ± 1 rows everywhere | C | ✔ | P0 |
| TC-PRE-005 | Across-track gain flatness | FR-PRE-03 | TD-02 | Normalise | Column-mean profile within ±10% of median | C | ✔ | P0 |
| TC-PRE-006 | Per-side balance | FR-PRE-03 | TD-07 roll imbalance | Normalise | Port/stbd medians within 5% | C | ✔ | P0 |
| TC-PRE-007 | 3-channel input contract | FR-PRE-04 | Any tile | Convert | Shape `(H, W, 3)` uint8; identical function imported by training and inference | U | ✔ | P0 |
| TC-PRE-008 | Dropout handling | FR-PRE-05 | TD-07 zeroed pings | Detect & fill | ≥ 95% injected dropouts found; gaps ≤ 3 inpainted; longer masked | C | ✔ | P0 |
| TC-PRE-009 | Motion flags | FR-PRE-06 | TD-07 roll ±10° segment | Flag | Flags exactly on pings over threshold | U | ✔ | P0 |
| TC-PRE-010 | Tiling round trip | FR-PRE-08 | Synthetic image | Tile → reassemble coordinates | Exact coordinate round trip; 25% overlap; masked tiles skipped | U | ✔ | P0 |
| TC-PRE-011 | Chunk boundary object | FR-PRE-08, FR-DET-04 | TD-01 object spanning chunk boundary | Full pipeline | Detected exactly once | I | ✔ | P0 |
| TC-PRE-012 | Surface-return band mask | FR-PRE-09 | Shallow-water sample | Mask | Band at slant range ≈ sensor depth | C | ✔ | P1 |

## 3. Geotagging (TC-GEO)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-GEO-001 | Straight-track golden positions | FR-GEO-01 | TD-01 straight | `pixel_to_latlon` for known objects | Error < 0.05 m | U | ✔ | P0 |
| TC-GEO-002 | Curved-track golden positions | FR-GEO-01 | TD-01 curved | Same | Error < 0.05 m | U | ✔ | P0 |
| TC-GEO-003 | Port vs. starboard direction | FR-GEO-01 | Heading 0° track | Objects each side | Starboard east of track, port west | U | ✔ | P0 |
| TC-GEO-004 | Heading wrap-around smoothing | FR-GEO-04 | Headings 358°, 359°, 0°, 1°, 2° | Smooth | Output ≈ 0° (not 180°) | U | ✔ | P0 |
| TC-GEO-005 | Invalid fixes | FR-GEO-04 | Nav with (0,0) and 500 m jump | Clean | Fixes interpolated; `GPS_INTERPOLATED` | U | ✔ | P0 |
| TC-GEO-006 | Measurements | FR-GEO-03 | Synthetic 6.2 × 3.1 m rectangle at 12° | Measure | Length/width ±0.1 m; area ±5%; orientation ±2° | U | ✔ | P0 |
| TC-GEO-007 | Footprint polygon | FR-GEO-02 | As above | Build footprint | 4 corners, clockwise, contains centroid | U | ✔ | P0 |
| TC-GEO-008 | Depth output | FR-GEO-08 | Nav with/without depth | Compute | depth = sensor depth + altitude; `null` if missing | U | ✔ | P0 |
| TC-GEO-009 | Layback correction | FR-GEO-05 | Cable 100 m, fish depth 20 m | Correct | Fish ≈ 98.0 m astern (+ antenna offset); flag set | U | ✔ | P1 |
| TC-GEO-010 | Uncertainty budget | FR-GEO-06 | Config defaults | Compute | RSS of terms; e.g. 50 m range, 2° heading term ≈ 1.75 m | U | ✔ | P1 |
| TC-GEO-011 | Mosaic alignment | FR-GEO-07 | TD-02 | Build mosaic; overlay track and detections | GCP residual < 1 m; visual alignment in QGIS | C | ✔/✋ | P1 |
| TC-GEO-012 | Charted-wreck accuracy | PRD §11 | TD-10 | Full pipeline; compare with chart | Median error reported; target ≤ 10 m | S | ✋ | P0 |
| TC-GEO-013 | Cross-line merge | FR-DET-05 | Two TD-01 lines over same object | Process batch | Merged detection; `n_views = 2`; position averaged | I | ✔ | P1 |
| TC-GEO-014 | Decimal and DMS formatting | FR-GEO-01, FR-UI-06 | 13.084120, 80.312750 | Format | `13.084120` / `13° 05' 02.83" N`; `80° 18' 45.90" E` | U | ✔ | P0 |

## 4. Detection models (TC-DET)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-DET-001 | Detection quality | FR-DET-01, PRD §11 | TD-08 | `ml/evaluate.py` | mAP@50 ≥ 0.70 (with 95% CI) | M | ✔ | P0 |
| TC-DET-002 | Key-class recall | FR-DET-01 | TD-08 | Evaluate at review threshold | `shipwreck`, `cylinder` recall ≥ 0.85 | M | ✔ | P0 |
| TC-DET-003 | Ghost-net recall | AC-05 | TD-09 | Evaluate | Recall ≥ 0.80; precision reported | M | ✔ | P0 |
| TC-DET-004 | Sliced inference benefit | FR-DET-02 | Val objects < 2 m | Sliced vs. non-sliced | Small-object recall sliced ≥ non-sliced | M | ✔ | P0 |
| TC-DET-005 | Unknown anomaly output | FR-DET-03, AC-05 | Tile with novel synthetic object class | Pipeline | `unknown_anomaly` with heatmap; AUROC reported on normal vs. debris tiles | I/M | ✔ | P0 |
| TC-DET-006 | Tile overlap dedupe | FR-DET-04 | Object in overlap of 4 tiles | Pipeline | Exactly one detection | I | ✔ | P0 |
| TC-DET-007 | Model version recorded | FR-DET-07 | Any run | Inspect report | `model_version` and `processing.models` populated | I | ✔ | P0 |
| TC-DET-008 | Robustness of metrics | PRD §11 | TD-08 + injected faults | Evaluate | mAP@50 drop ≤ 5 points | M | ✔ | P0 |
| TC-DET-009 | Quantisation degradation | AC-09 | TD-08 | FP32 vs. INT8 | Drop ≤ 3 mAP points | M | ✔ | P1 |
| TC-DET-010 | Mask refiner gain | FR-DET-06 | TD-09 masks | With/without refiner | Mask IoU improves | M | ✔ | P1 |

## 5. Confidence scoring (TC-CONF)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-CONF-001 | Confidence range | FR-CONF-04 | Any report | Check all detections | 0 ≤ confidence ≤ 100 | U/I | ✔ | P0 |
| TC-CONF-002 | Tier boundaries | FR-CONF-05 | Scores 79.9, 80.0, 50.0, 49.9 (anomaly ≥ τ and < τ), 29.9 | Assign tiers | review, hazard, review, anomaly / hidden, hidden | U | ✔ | P0 |
| TC-CONF-003 | Fusion consistency | FR-CONF-03, 06 | Detection with breakdown | Recompute fused from weights/penalties | Equal within 1e-6; breakdown present | U | ✔ | P0 |
| TC-CONF-004 | Shadow score discriminates | FR-CONF-01 | Synthetic object with shadow vs. shadow-only patch | Score both | Object score > patch score by ≥ 0.3 | U | ✔ | P0 |
| TC-CONF-005 | Shadow/rock demotion | AC-08 | TD-13 | Pipeline with scoring | ≥ 50% demoted below `review` | M | ✔ | P0 |
| TC-CONF-006 | Height estimate | FR-CONF-07 | Synthetic 1 m tall object, known altitude | Estimate | Within ±30% | U | ✔ | P1 |
| TC-CONF-007 | Quality penalties | FR-CONF-08 | Detection overlapping dropout | Score | `DROPOUT` flag; penalty applied; lower confidence than the same object on clean data | I | ✔ | P0 |
| TC-CONF-008 | Calibration | FR-CONF-04 | Calibration split | Reliability diagram | ECE ≤ 0.10 | M | ✔ | P0 |
| TC-CONF-009 | False positives per km² | PRD §11 | TD-11 | Detector-only vs. full scoring | ≥ 50% reduction | S | ✔ | P0 |
| TC-CONF-010 | FP filter quality | FR-CONF-02 | Validation detections | Evaluate LightGBM | AUROC reported; SHAP summary produced | M | ✔ | P1 |

## 6. Reporting & CLI (TC-REP)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-REP-001 | JSON schema validity | FR-REP-01, AC-07 | Reports from TD-01/02/04/06 | Validate with `report-1.0.schema.json` | All valid | I | ✔ | P0 |
| TC-REP-002 | CSV ↔ JSON consistency | FR-REP-02, AC-01 | TD-02 report | Compare row by `detection_id` | Identical values (6-decimal coordinates) | I | ✔ | P0 |
| TC-REP-003 | GeoJSON correctness | FR-REP-04, AC-07 | TD-02 | Validate RFC 7946; load in QGIS | `[lon, lat]` order; features at correct positions | I | ✔/✋ | P1 |
| TC-REP-004 | KML correctness | FR-REP-04, AC-07 | TD-02 | Open in Google Earth | Placemarks at correct positions; class folders/styles | S | ✋ | P1 |
| TC-REP-005 | Report metadata | FR-REP-03, NFR-16 | Any | Inspect | Versions, config hash, duration, quality; summary counts equal detections | I | ✔ | P0 |
| TC-REP-006 | Determinism | NFR-16 | TD-01 twice | Diff reports excluding `generated_utc`, `duration_s` | Identical | I | ✔ | P0 |
| TC-REP-007 | Filtered export scope | FR-REP-05 | Survey with 7 detections | Export `scope=filtered` with min_conf 60 | Only matching rows | A | ✔ | P1 |
| TC-REP-008 | CLI end to end | FR-OPS-01 | TD-01 | `sonarsentinel detect … --formats json,csv` | Exit code 0; files created; schema valid | I | ✔ | P0 |
| TC-REP-009 | Detection chips | FR-UI-06 | TD-02 | Generate | One chip per detection; overlays mask/shadow/anomaly | C | ✔ | P0 |

## 7. API (TC-API)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-API-001 | Create survey | FR-ING-01 | TD-01 | `POST /surveys` | `202` with `survey_id`, `job_id`, `ws_url` | A | ✔ | P0 |
| TC-API-002 | Validate files | FR-ING-05, FR-UI-01 | TD-01, TD-06 | `POST /surveys/validate` | Metadata; `has_navigation`; warnings for TD-06 | A | ✔ | P0 |
| TC-API-003 | Error model | API spec §4 | Invalid requests | Trigger 400/404/409/413/415/422 | Correct status and `error.code` shape | A | ✔ | P0 |
| TC-API-004 | Detection filters | FR-UI-04 | Seeded survey | Query `class`, `min_conf`, `tier`, `bbox`, `sort`, `limit/offset` | Correct subsets, order and totals | A | ✔ | P0 |
| TC-API-005 | Review update | FR-UI-10 | Seeded detection | `PATCH` confirmed/rejected/reclassified; invalid value | Updated; review row + label record; invalid → `400` | A | ✔ | P1 |
| TC-API-006 | Cancel job | FR-UI-02 | Running and finished jobs | `POST /jobs/{id}/cancel` | Running → `cancelled` within one chunk; finished → `409` | A | ✔ | P0 |
| TC-API-007 | Report download | FR-UI-07 | Completed survey | `GET …/report?format=json/csv/geojson/kml` | Correct content type and `Content-Disposition` | A | ✔ | P0 |
| TC-API-008 | Health | — | Running service | `GET /health` | Version, GPU, runtime, models loaded | A | ✔ | P0 |
| TC-API-009 | Contract conformance | API spec | OpenAPI | schemathesis run | No schema violations or 5xx | A | ✔ | P0 |

## 8. WebSocket streaming (TC-WS)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-WS-001 | Event sequence | FR-UI-02 | TD-01 | Subscribe; process | `progress` → `track`/`detection` … → `done`; `seq` strictly increasing | A | ✔ | P0 |
| TC-WS-002 | Progress interval | NFR-05 | TD-02 | Measure gaps | ≤ 5 s between progress events | A | ✔ | P0 |
| TC-WS-003 | First detection latency | NFR-04 | TD-01 object in first chunk | Measure | ≤ 15 s from job start | S | ✔ | P0 |
| TC-WS-004 | Reconnect and replay | ADR-008 | TD-02 | Drop connection mid-job; `resume after_seq` | Missed events replayed; no duplicates | A | ✔ | P0 |
| TC-WS-005 | Merge updates | FR-DET-04 | TD-01 chunk-boundary object | Observe events | `detection_update` / `detection_removed` emitted correctly | A | ✔ | P0 |
| TC-WS-006 | Failure event | NFR-08 | Model file missing | Start job | `error` event with code; job `failed` | A | ✔ | P0 |

## 9. Dashboard UI (TC-UI)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-UI-001 | Upload validation badges | FR-UI-01 | TD-01, TD-06, `.bmp` | Drop files | `[ok] GPS found`, `[!] No GPS`, `[X] Unsupported` | UI/E2E | ✔ | P0 |
| TC-UI-002 | Start button rules | FR-UI-01 | TD-06 | Try to start without CSV/confirmation | Disabled until CSV attached or "Continue without GPS" | UI | ✔ | P0 |
| TC-UI-003 | Live markers and track | FR-UI-02, 03 | TD-02 | Start analysis | Track grows; markers appear before completion; counts update | E2E | ✔ | P0 |
| TC-UI-004 | Filter performance | FR-UI-04 | TD-14 | Move confidence slider; toggle classes | Map + list update < 100 ms | UI | ✔ | P0 |
| TC-UI-005 | Detail matches exports | FR-UI-06, AC-01 | TD-02 | Open detection; compare with CSV row | All shown values identical | E2E | ✔ | P0 |
| TC-UI-006 | Copy coordinates | FR-UI-06 | Any detection | Click copy | Clipboard `13.084120, 80.312750` format; toast | UI | ✔ | P0 |
| TC-UI-007 | Quality warnings | FR-UI-08 | TD-07 | View map; click warning | Segments styled; zooms to affected range | E2E | ✔ | P0 |
| TC-UI-008 | Report downloads | FR-UI-07, AC-07 | Completed survey | Click JSON/CSV (GeoJSON/KML) | Files downloaded and valid | E2E | ✔ | P0 |
| TC-UI-009 | Not-geotagged view | AC-02 | TD-06 | Process without GPS | Pixel image view; banner; no lat/lon shown | E2E | ✔ | P0 |
| TC-UI-010 | Accessibility basics | NFR-14 | Main screens | Keyboard-only run; axe scan; screen reader spot check | No critical axe issues; all actions reachable; marker labels read correctly | UI/✋ | ✔/✋ | P0 |
| TC-UI-011 | Review queue shortcuts | FR-UI-10 | 20 pending items | Use C/R/K/N/P/Z | Actions applied; undo works; auto-advance | E2E | ✔ | P1 |
| TC-UI-012 | Offline basemap | FR-UI-14, AC-10 | MBTiles, network off | Use app | Map tiles load locally; offline badge | S | ✋ | P1 |
| TC-UI-013 | Responsive layout | Wireframes | Phone viewport 390 px | Upload + map + detail | Layout per phone wireframes; no horizontal scroll | UI | ✔ | P1 |
| TC-UI-014 | Connection loss UX | ADR-008 | Kill WS mid-job | Observe | "Reconnecting…" banner; resumes; no duplicate markers | E2E | ✔ | P0 |

## 10. End-to-end acceptance (TC-E2E)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-E2E-001 | Geotagged XTF flow | AC-01 | TD-02 | Upload → watch → open detail → download CSV | AC-01 conditions all met | E2E | ✔ | P0 |
| TC-E2E-002 | Image + nav CSV flow | AC-03 | TD-04 | Upload image + CSV → download | Geotagged detections; interpolation flag where applicable | E2E | ✔ | P0 |
| TC-E2E-003 | Image-only flow | AC-02 | TD-06 | Upload → continue without GPS | AC-02 conditions all met | E2E | ✔ | P0 |
| TC-E2E-004 | Fresh Docker install | NFR-10 | Clean machine | Follow Developer Setup / compose | First report produced; setup ≤ 15 min excluding downloads | S | ✋ | P1 |
| TC-E2E-005 | Offline full flow | AC-10 | TD-02, network off | AC-01 steps | Passes with no external requests | S | ✋ | P1 |

## 11. Performance (TC-PERF)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-PERF-001 | Workstation GPU throughput | NFR-01 | 1 km reference line | `benchmark.py` × 3 | Median ≤ 60 s | S | ✔ | P0 |
| TC-PERF-002 | CPU-only throughput | NFR-02 | Same | ONNX CPU runtime × 3 | Median ≤ 5 min | S | ✔ | P0 |
| TC-PERF-003 | Edge real-time factor | NFR-03 | Same on Jetson | TensorRT runtime, 30 min | ≥ 1× acquisition rate (target ≥ 5×) | S | ✔ | P1 |
| TC-PERF-004 | Memory on large file | NFR-07 | TD-12 | Monitor RSS | Peak ≤ 8 GB | S | ✔ | P0 |
| TC-PERF-005 | Map rendering | Wireframe S-02 | TD-14 | Pan/zoom profile | ≥ 30 fps with clustering | UI | ✋ | P0 |
| TC-PERF-006 | Model footprint | NFR-06 | Exported models | Check sizes | FP32 ≤ 25 MB; INT8 ≤ 10 MB | S | ✔ | P1 |

## 12. Robustness (TC-ROB)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-ROB-001 | Dropouts + truncation | AC-06 | TD-07 (10% zeroed) + TD-05 truncated | Process | Completes; warnings list ping ranges; affected detections flagged with reduced confidence | S | ✔ | P0 |
| TC-ROB-002 | GPS gap | FR-GEO-04 | TD-07 30 s GPS gap | Process | Positions interpolated; flags; uncertainty increased | S | ✔ | P0 |
| TC-ROB-003 | Heavy motion | FR-PRE-06 | TD-07 roll ±10° | Process | `HIGH_MOTION` flags and penalties; track segment styled | S | ✔ | P0 |
| TC-ROB-004 | Missing altitude | FR-PRE-01 | TD-07 no altitude | Process | Bottom tracking used; survey flag | S | ✔ | P0 |
| TC-ROB-005 | GPU unavailable | 02-data-pipeline §5 | Hide GPU | Process | CPU fallback; `CPU_FALLBACK` warning; correct results | S | ✔ | P0 |
| TC-ROB-006 | Chunk failure | 02-data-pipeline §5 | Inject exception in chunk 2 | Process | Retry once; then `CHUNK_SKIPPED` with range; job completes with warnings | S | ✔ | P0 |

## 13. Security (TC-SEC)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-SEC-001 | Path traversal filename | NFR-11 | Filename `../../evil.xtf` | Upload | Stored under survey folder with sanitised name | A | ✔ | P0 |
| TC-SEC-002 | Extension spoofing | NFR-11 | PNG renamed `.xtf` | Validate | Rejected by magic-byte/header check | A | ✔ | P0 |
| TC-SEC-003 | Large upload streaming | NFR-11 | 3 GB stream | Upload | Rejected at limit without loading into memory | A | ✔ | P0 |
| TC-SEC-004 | Dependency vulnerabilities | NFR-11 | Lock files, images | pip-audit, npm audit, image scan | No unresolved critical vulnerabilities | S | ✔ | P0 |
| TC-SEC-005 | Default bind address | NFR-11 | Default config | Start service; scan from LAN | Not reachable from other hosts unless configured | S | ✋ | P0 |
| TC-SEC-006 | No external calls offline | NFR-09, 11 | Offline config | Monitor network during AC-01 | Zero external requests | S | ✋ | P1 |

## 14. Edge (TC-EDGE)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-EDGE-001 | ONNX parity | FR-OPS-03 | 100 val tiles | PyTorch vs. ONNX Runtime | Matched box IoU ≥ 0.95; score diff ≤ 0.02 | C | ✔ | P1 |
| TC-EDGE-002 | TensorRT build and run | FR-OPS-03 | Jetson | Build engine; run pipeline on TD-01 | Report valid; matches CPU results within tolerance | S | ✋ | P1 |
| TC-EDGE-003 | Watch mode | — | Copy file into watched folder | Observe | Processed once, report written | S | ✔ | P1 |
| TC-EDGE-004 | Long-run stability | NFR-03 | 2 h continuous | Monitor | No crash/memory growth; throughput stable; thermal state logged | S | ✋ | P1 |

## 15. Usability (TC-USE)

| ID | Title | Refs | Data | Steps | Expected result | Lvl | Auto | Pri |
|---|---|---|---|---|---|---|---|---|
| TC-USE-001 | First-time user flow | NFR-13 | TD-02 | Test Plan §6.7 tasks 1–4 with ≥ 3 users | ≥ 80% task success; median ≤ 5 min; SUS ≥ 70 | UAT | ✋ | P0 |
| TC-USE-002 | Review speed | FR-UI-10 | 20 pending items | Analyst uses keyboard | ≤ 3 min for 20 items | UAT | ✋ | P1 |

---

## 16. Traceability matrix

### 16.1 Functional requirements → test cases

| Requirement | Test cases |
|---|---|
| FR-ING-01 | TC-ING-003, 005, 006; TC-API-001 |
| FR-ING-02 | TC-ING-009 |
| FR-ING-03 | TC-ING-004, 010; TC-E2E-002 |
| FR-ING-04 | TC-ING-011; TC-E2E-003 |
| FR-ING-05 | TC-ING-001…004; TC-API-002 |
| FR-ING-06 | TC-ING-005, 006 |
| FR-ING-07 | TC-ING-007, 008 |
| FR-ING-08 | TC-ING-005 |
| FR-ING-09 | TC-ING-013 |
| FR-ING-10 | TC-ING-014 |
| FR-PRE-01 | TC-PRE-001, 002; TC-ROB-004 |
| FR-PRE-02 | TC-PRE-003 |
| FR-PRE-03 | TC-PRE-005, 006 |
| FR-PRE-04 | TC-PRE-007 |
| FR-PRE-05 | TC-PRE-008; TC-ROB-001 |
| FR-PRE-06 | TC-PRE-009; TC-ROB-003 |
| FR-PRE-07 | TC-PRE-004 |
| FR-PRE-08 | TC-PRE-010, 011 |
| FR-PRE-09 | TC-PRE-012 |
| FR-DET-01 | TC-DET-001, 002 |
| FR-DET-02 | TC-DET-004 |
| FR-DET-03 | TC-DET-005 |
| FR-DET-04 | TC-DET-006; TC-PRE-011; TC-WS-005 |
| FR-DET-05 | TC-GEO-013 |
| FR-DET-06 | TC-DET-010 |
| FR-DET-07 | TC-DET-007 |
| FR-CONF-01 | TC-CONF-004, 005 |
| FR-CONF-02 | TC-CONF-010 |
| FR-CONF-03 | TC-CONF-003 |
| FR-CONF-04 | TC-CONF-001, 008 |
| FR-CONF-05 | TC-CONF-002 |
| FR-CONF-06 | TC-CONF-003 |
| FR-CONF-07 | TC-CONF-006 |
| FR-CONF-08 | TC-CONF-007; TC-ROB-001 |
| FR-GEO-01 | TC-GEO-001, 002, 003, 014 |
| FR-GEO-02 | TC-GEO-007 |
| FR-GEO-03 | TC-GEO-006 |
| FR-GEO-04 | TC-GEO-004, 005; TC-ROB-002 |
| FR-GEO-05 | TC-GEO-009 |
| FR-GEO-06 | TC-GEO-010 |
| FR-GEO-07 | TC-GEO-011 |
| FR-GEO-08 | TC-GEO-008 |
| FR-REP-01 | TC-REP-001 |
| FR-REP-02 | TC-REP-002 |
| FR-REP-03 | TC-REP-005 |
| FR-REP-04 | TC-REP-003, 004 |
| FR-REP-05 | TC-REP-007 |
| FR-UI-01 | TC-UI-001, 002 |
| FR-UI-02 | TC-UI-003; TC-WS-001; TC-API-006 |
| FR-UI-03 | TC-UI-003; TC-PERF-005 |
| FR-UI-04 | TC-UI-004; TC-API-004 |
| FR-UI-05 | TC-UI-004 |
| FR-UI-06 | TC-UI-005, 006; TC-REP-009; TC-GEO-014 |
| FR-UI-07 | TC-UI-008; TC-API-007 |
| FR-UI-08 | TC-UI-007 |
| FR-UI-10 | TC-UI-011; TC-API-005; TC-USE-002 |
| FR-UI-14 | TC-UI-012 |
| FR-OPS-01 | TC-REP-008 |
| FR-OPS-03 | TC-EDGE-001, 002; TC-DET-009 |

*FR-UI-09, 11, 12, 13, 15 and FR-OPS-02, 04…06 get test cases when their stories enter a sprint.*

### 16.2 Non-functional requirements → test cases

| NFR | Test cases |
|---|---|
| NFR-01 / 02 / 03 | TC-PERF-001 / 002 / 003 |
| NFR-04 / 05 | TC-WS-003 / TC-WS-002 |
| NFR-06 | TC-PERF-006 |
| NFR-07 | TC-PERF-004 |
| NFR-08 | TC-ING-012; TC-WS-006; TC-ROB-001…006 |
| NFR-09 | TC-E2E-005; TC-SEC-006 |
| NFR-10 | TC-E2E-004 |
| NFR-11 | TC-SEC-001…006 |
| NFR-13 | TC-USE-001 |
| NFR-14 | TC-UI-010 |
| NFR-15 | CI coverage gate |
| NFR-16 | TC-REP-005, 006 |
| NFR-18 | TC-REP-002, 003, 004 |

### 16.3 Acceptance criteria → test cases

| AC | Test cases |
|---|---|
| AC-01 | TC-E2E-001, TC-REP-002, TC-UI-005 |
| AC-02 | TC-E2E-003, TC-ING-011, TC-UI-009 |
| AC-03 | TC-E2E-002, TC-ING-010 |
| AC-04 | TC-CONF-001, 002; TC-UI-004 |
| AC-05 | TC-DET-003, 005 |
| AC-06 | TC-ROB-001 |
| AC-07 | TC-REP-001, 003, 004; TC-UI-008 |
| AC-08 | TC-CONF-005 |
| AC-09 | TC-DET-009, TC-PERF-003 |
| AC-10 | TC-E2E-005, TC-UI-012 |
