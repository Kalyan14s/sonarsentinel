# Sprint 2 Plan — Preprocessing & Training Data

| | |
|---|---|
| **Sprint** | S2 · 2026-09-28 → 2026-10-02 (illustrative dates, see [Project Plan](PROJECT_PLAN.md)); started early on 2026-09-13 |
| **Milestone** | **M2** (Preprocessing & training data) |
| **Sprint goal** | *Turn raw sonar logs into clean, normalised, ground-range tiles with quality masks, and prepare the first versioned training dataset, including synthetic ghost nets.* |
| **Capacity** | 6 people; committed **42 points** (backlog allocation) |
| **Branch** | `sprint-2/preprocess-data` |

**Related:** [Product Backlog](PRODUCT_BACKLOG.md) · [TODO Phase 3](../../TODO.md#phase-3--sprint-2--preprocessing--training-data) · [Data Pipeline S2–S7](../architecture/02-data-pipeline.md#3-stage-specifications) · [Test Cases §2](../testing/TEST_CASES.md#2-preprocessing-tc-pre) · [Sprint 1 plan](SPRINT_1_PLAN.md)

---

## 1. Committed stories

| Story | Title | Pts | Owner | Depends on | Acceptance (short) | Tests |
|---|---|---|---|---|---|---|
| ST-032 | Navigation cleaning | 3 | R3 | ST-021 | Heading wrap-around (359°→1°) passes | TC-GEO-004, TC-GEO-005 |
| ST-040 | Bottom tracking + water-column mask | 3 | R2 | ST-021 | Tracked altitude within 10% of recorded | TC-PRE-001 (TC-PRE-002 needs the detector: Sprint 3) |
| ST-041 | Gain normalisation | 3 | R2 | — | Column-mean profile flat within ±10% | TC-PRE-005, TC-PRE-006 |
| ST-042 | Slant-range correction + along-track resampling | 5 | R2 | ST-032, ST-040 | Known-size object correct after resampling | TC-PRE-003, TC-PRE-004 |
| ST-043 | Dropout detection, inpainting, masks | 3 | R2 | — | ≥ 95% injected dropouts detected | TC-PRE-008 |
| ST-044 | Motion flags | 2 | R2 | — | Flags match thresholds | TC-PRE-009 |
| ST-045 | 3-channel input | 2 | R2 | ST-041 | Same function for training and inference | TC-PRE-007 |
| ST-046 | Tiling + chunking with overlap | 3 | R4 | ST-026 | Tile ↔ chunk round trip exact | TC-PRE-010 (TC-PRE-011 needs the detector: Sprint 3) |
| ST-048 | Preprocessing QA notebook | 2 | R2 | ST-040…046 | Reviewed at M2 demo | — |
| ST-014 | Labelling tool + ≥ 100 labelled real tiles | 5 | R2 | ST-013, ST-042 | ≥ 100 tiles, 10% double-labelled | — |
| ST-015 | Site-grouped splits, manifest, stats | 3 | R1 | ST-011 | No site in more than one split | — |
| ST-016 | Synthetic ghost-net generator v1 | 8 | R2 | ST-012 | 2,000 tiles + masks; parameters per tile | — |
| | **Total** | **42** | | | | |

**Carried over from Sprint 1 (re-estimated, not pointed again):** ST-010 (browser download), ST-011 (NOMBO review), ST-013 (more surveys, wreck), Gate G1 approval, PRD Q7 confirmation, SIH team ID and idea PDF upload (deadline 30 Sept), S3Simulator request.

**Needs people, not code:** ST-014 labelling, the annotation calibration session (20 shared tiles), the NOMBO review, the M2 demo and review of the QA notebook, and the SIH portal work.

## 2. Sprint schedule

| Day | Event | Output |
|---|---|---|
| Mon 09-28 | Sprint planning (45 min); SIH deck final check | Owners confirmed |
| Tue 09-29 | Annotation calibration session (20 shared tiles) | Agreement metrics |
| Wed 09-30 | **SIH idea PDF deadline**; integration check: USGS line → ground-range tiles | Tiles viewed in the QA notebook |
| Fri 10-02 | Sprint review = **M2 demo** (before/after preprocessing) + retrospective | Demo notes; retro actions |

## 3. Exit criteria (M2)

- [ ] Preprocessing visually verified (QA notebook reviewed at the M2 demo)
- [ ] Datasets converted; splits pass the leakage check
- [ ] Synthetic ghost-net generator produces tiles + masks
- [ ] TC-PRE-001, 003…010 and TC-GEO-004/005 automated in CI; TC-PRE-002/011 explicitly carried over to Sprint 3 (they need the detector)

## 4. Risks this sprint

| Risk | Trigger | Response |
|---|---|---|
| Recorded altitude unreliable (seen in USGS Grand Bay files: 1–74 m in ~3 m of water) | Bottom tracking disagrees with recorded altitude | Default `bottom_tracking: auto` uses tracked altitude when they disagree; flag `NO_ALTITUDE_BOTTOM_TRACKED` |
| Unknown pixel size of the mine-SSS images | Synthetic object sizes can't be set in metres | Generator takes `--res-m`; record the assumption per tile; revisit when the paper or authors give the range |
| Too few real labelled sites for grouped splits | < 4 sites with labels | Split mine-SSS by survey year (5 groups); add USGS/NOAA sites as labels arrive |
| SIH deadline (30 Sept) competes for time | Deck not uploaded by Tuesday | PM timeboxes deck work; engineering stories unaffected |

## 5. Progress (2026-09-13, branch `sprint-2/preprocess-data`, not yet merged)

| Story | Status | Evidence / what is left |
|---|---|---|
| ST-032 | ✅ Acceptance met | TC-GEO-004, TC-GEO-005 |
| ST-040 | ✅ Acceptance met (synthetic) | TC-PRE-001; real USGS lines track 0.49–1.2 m (recorded altitude invalid, so not a reference) |
| ST-041 | ✅ | TC-PRE-005, TC-PRE-006 |
| ST-042 | ✅ | TC-PRE-003, TC-PRE-004, end-to-end target geotag < 0.15 m |
| ST-043 | ✅ | TC-PRE-008 |
| ST-044 | ✅ | TC-PRE-009 |
| ST-045 | ✅ | TC-PRE-007 |
| ST-046 | ✅ | TC-PRE-010 |
| ST-048 | 🟡 Built | Notebook + QA panels for 3 USGS lines; review at M2 demo |
| ST-015 | ✅ | `sonar-seg@0.1.0`: site-grouped, leakage check passed, test hash frozen |
| ST-016 | ✅ | 2,000 train + 200 holdout tiles with masks and parameters |
| ST-014 | 🔴 Open | Tile export ready (`xtf_to_tiles.py`); labelling needs people and more real surveys |

**Lessons from real data:** recorded altitude can't be trusted (USGS Grand Bay), and a first bottom-tracking rule tuned on synthetic data failed on shallow-water pings in three different ways. Perceptual hashes (dHash) flag unrelated side-scan images as duplicates, so the leakage check uses thumbnail correlation.
