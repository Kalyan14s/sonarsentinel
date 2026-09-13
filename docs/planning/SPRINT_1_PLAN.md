# Sprint 1 Plan — Ingest & Geotagging

| | |
|---|---|
| **Sprint** | S1 · 2026-09-21 → 2026-09-25 (illustrative dates, see [Project Plan](PROJECT_PLAN.md)) |
| **Milestone / gate** | **M1** (Ingest & Geo) · **G1** (API and report contracts frozen) |
| **Sprint goal** | *Read real sonar logs and place them correctly on a map, with contracts frozen so frontend and backend can work in parallel.* |
| **Capacity** | 6 people; committed **33 points** (backlog allocation) |
| **Status** | Planned in Sprint 0 (2026-09-13); confirm owners at Monday planning |

**Related:** [Product Backlog](PRODUCT_BACKLOG.md) · [TODO Phase 2](../../TODO.md#phase-2--sprint-1--ingest--geotagging) · [Test Cases](../testing/TEST_CASES.md) · [Contributing (Definition of Done)](../../CONTRIBUTING.md#7-definition-of-done-stories)

---

## 1. Committed stories

| Story | Title | Pts | Owner | Depends on | Acceptance (short) | Tests |
|---|---|---|---|---|---|---|
| ST-020 | `SonarLog` contract, validators, error types | 3 | R2 | Scaffold (Sprint 0) | Typed dataclasses; coded errors | TC-ING-001, TC-ING-002, TC-ING-003, TC-ING-004 |
| ST-021 | XTF reader: channels, per-ping nav, units | 5 | R2 | ST-020, ST-013 | 3 public files parse; nav matches a reference viewer on 10 pings | TC-ING-005, TC-ING-006 |
| ST-022 | GeoTIFF reader with CRS/transform | 2 | R3 | ST-020 | Pixel → lat/lon within 1 pixel of QGIS | TC-ING-009 |
| ST-023 | Image + navigation CSV reader | 3 | R2 | ST-020 | Template CSV works; sparse rows set `GPS_INTERPOLATED` | TC-ING-010 |
| ST-024 | Image-only path (`NOT_GEOTAGGED`) | 1 | R2 | ST-023 | Null lat/lon, pixel boxes | TC-ING-011 |
| ST-026 | Memory-mapped chunked reading | 3 | R4 | ST-021 | 2 GB file with peak RAM ≤ 8 GB | TC-PERF-004 (partial) |
| ST-030 | Units/CRS detection, UTM ↔ WGS84 | 2 | R3 | — | Degree and UTM copies agree < 0.1 m | TC-ING-007, TC-ING-008 |
| ST-031 | `pixel_to_latlon` + golden tests | 3 | R3 | ST-030 | Golden error < 0.05 m | TC-GEO-001, TC-GEO-002, TC-GEO-003 |
| ST-010 | AI4Shipwrecks → YOLO-seg | 3 | R1 | Dataset download (licence confirmed CC BY 4.0) | 20 random overlays correct | — |
| ST-011 | Mine SSS dataset: MILCO → cylinder; NOMBO review | 3 | R1 | — | Mapping table; visual check | — |
| ST-012 | KLSG normal seafloor pool (victim images excluded) | 2 | R1 | — | ≥ 500 normal tiles | — |
| ST-013 | ≥ 3 NOAA/USGS XTF surveys incl. a charted wreck | 3 | R3 | — | Provenance + ground-truth files | — |
| | **Total** | **33** | | | | |

**Also this sprint (not pointed):**
- Freeze the API spec and report schema v1.0 and agree the mock-server approach (**Gate G1**, Wednesday) — R4 + R3
- Synthetic XTF generator for test data TD-01 (supports ST-021/031 tests) — R2
- Answer PRD Q7 (datum/CRS for official reports) — R3
- **SIH 2026:** idea PDF uploaded by **Thu 2026-09-25** (official deadline 30 Sept); R6 and R5 reserve about 1 day for it

## 2. Sprint schedule

| Day | Event | Output |
|---|---|---|
| Mon 09-21 | Sprint planning (45 min): confirm owners, split any story > 5 pts | Board updated |
| Mon–Fri | Daily stand-up (15 min) | Blockers raised same day |
| Wed 09-23 | Integration check (30 min): XTF track on a map; **G1 contract freeze** | API spec + schema tagged `contracts-1.0` |
| Thu 09-24 | SIH idea deck final review; export PDF | Upload by team leader (target 09-25) |
| Fri 09-25 | Sprint review = **M1 demo** (45 min) + retrospective (20 min) | Demo recording; retro actions |
| Fri 09-25 | Weekly status report ([format](PROJECT_PLAN.md#weekly-status-report-posted-every-friday)) | Posted to team channel |

## 3. Exit criteria (M1 / G1)

- [ ] A NOAA XTF survey track plots correctly on a map (lat/lon sanity-checked against the survey metadata)
- [ ] Georef golden tests pass with error < 0.05 m in CI
- [ ] TC-ING-001…012 and TC-GEO-001…008 automated in CI (or explicitly carried over)
- [ ] API spec + report schema approved and tagged (G1)
- [ ] Every committed story meets the Definition of Done, or is carried over with a reason

## 4. Risks this sprint

| Risk | Trigger | Response |
|---|---|---|
| R3 XTF variants break the parser | Any sample file fails to parse by Wednesday | Try the other pyxtf implementation; adapter per variant; carry ST-026 over if needed |
| Data downloads late (ST-013) | No XTF with navigation by Tuesday | Use the synthetic TD-01 survey for ST-021/031 tests; keep ST-013 open |
| ~~AI4Shipwrecks licence unconfirmed~~ | Resolved 2026-09-13: CC BY 4.0 (Deep Blue record) | No action needed; cite dataset and paper |
| SIH idea deadline competes for time | Deck not final by Thursday | PM timeboxes deck work; engineering stories unaffected |

## 5. Carry-over rules

Unfinished stories are re-estimated at the next planning, not silently rolled over. P0 stories take priority in Sprint 2; P1/stretch items are dropped first ([Backlog §4](PRODUCT_BACKLOG.md#4-backlog-grooming-rules)).

## 6. Progress (2026-09-13, branch `sprint-1/ingest-geo`, not yet merged)

| Story | Status | Evidence / what is left |
|---|---|---|
| ST-020 | ✅ Acceptance met | Contract 1.0; TC-ING-001…004 automated |
| ST-021 | ✅ Acceptance met | Synthetic TD-01 exact; 4 USGS Klein 3900 lines match pyxtf's parser on 10 pings each (TC-ING-006); port order detection fixed for real data |
| ST-022 | ✅ Acceptance met | TC-ING-009 |
| ST-023 | ✅ Acceptance met | TC-ING-004, 010 |
| ST-024 | ✅ Acceptance met (reader + schema) | TC-ING-011 reader part; end-to-end in TC-E2E-003 |
| ST-026 | ✅ Acceptance met | 2.0 GB XTF: 6 s, peak private memory 91 MB, working set 2.1 GB (`scripts/bench_xtf_memory.py`) |
| ST-030 | ✅ Acceptance met | TC-ING-007, 008 |
| ST-031 | ✅ Acceptance met | TC-GEO-001…003 < 0.05 m |
| ST-010 | 🟡 Converter ready | Browser download from Deep Blue, then run and check overlays |
| ST-011 | 🟡 Converted | NOMBO review of 231 crops by R1 |
| ST-012 | ✅ Acceptance met | 1,687 tiles from object-free D2 images (KLSG repo has no seafloor images) |
| ST-013 | 🟡 1 of 3 surveys | USGS Grand Bay 2015: 4 lines in DVC with provenance; still need 2 surveys, a second sonar model and a charted wreck |
| G1 | 🟡 Prepared | Report schema 1.0 + tests; needs approval, mock-server decision and tag |
| PRD Q7 | 🟡 Proposed | ADR-015 (WGS84); confirm with NIOT |
