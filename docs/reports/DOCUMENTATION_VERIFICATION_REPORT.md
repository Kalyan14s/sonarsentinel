# Documentation Verification Report

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Scope** | Every Markdown document in the repository: root files, `.github/` templates, `docs/**` |
| **Method** | Automated checks (`scripts/docs/verify_docs.ps1` + one-off scans) and a manual cross-document consistency review |
| **Result** | ✅ **PASS after fixes**: 10 issues found and fixed; open items listed in §6 need human action |
| **Next verification** | At every milestone review, and before merging any documentation PR |

**Related:** [Documentation index](../README.md) · [TODO](../../TODO.md) · [CHANGELOG](../../CHANGELOG.md)

---

## 1. Documents in scope

| Set | Documents |
|---|---|
| Root | README, TODO, CONTRIBUTING, SECURITY, CHANGELOG |
| GitHub templates | PR template; bug, feature, data-issue templates |
| Define | Project Idea, PRD, Literature Review |
| Design | Architecture index + 8 docs; Wireframes index + 8 screens |
| Plan | Project Plan, Product Backlog |
| Build | Datasets, Annotation Guidelines, Data Management Plan, Developer Setup, Model Card template, Experiment Log template |
| Verify | Test Plan, Test Cases, this report |
| Deliver | User Manual, Operations Runbook, SIH Presentation, Demo Script, Final Report template, Licences & Compliance |

## 2. Method

### 2.1 Automated checks

| # | Check | How |
|---|---|---|
| A1 | Relative links resolve | Every Markdown link target that isn't http/mailto is resolved against the file location (inline code is ignored) |
| A2 | Anchors exist | `#anchor` compared with GitHub-style slugs of the target document's headings |
| A3 | ID cross-references | Every `FR-`, `NFR-`, `US-`, `AC-`, `TC-`, `ST-`, `EP-`, `ADR-`, `TD-` reference must be defined in its source document (PRD, Test Cases, Backlog, ADRs, Test Plan) |
| A4 | Wireframe frames | In `docs/wireframes`, every ASCII frame line in a `text` block has the same width |
| A5 | API path versioning | No `/api/` path without `v1`; WebSocket paths only under `/ws/jobs/` (one-off scan) |
| A6 | Code vocabulary | Inventory of all `UPPER_SNAKE` codes (flags, errors, env vars), reviewed for typos and duplicates (one-off scan) |
| A7 | Class vocabulary | Scan for non-canonical class names (`tire`, `net`, `wreck`, `ghostnet`, …) used as class IDs (one-off scan) |

A1–A4 are automated in `scripts/docs/verify_docs.ps1`.

### 2.2 Manual consistency review
Canonical values (§5) were compared across all documents that mention them: classes, tiers, fusion weights, preprocessing defaults, API contracts, error and flag codes, NFR targets, success metrics, milestones/gates, backlog points, dataset facts, worked examples and formulas.

## 3. Automated results (final run)

| Check | Result |
|---|---|
| A1 Links | ✅ All relative links resolve |
| A2 Anchors | ✅ All anchors resolve |
| A3 IDs | ✅ No undefined references |
| A4 Wireframe frames | ✅ No width mismatches |
| A5 API paths | ✅ All versioned (`/api/v1`, `/ws/jobs/{job_id}`) |
| A6 Codes | ✅ 10 quality flags, 10 API error codes, 4 job warning codes, 9 env vars: consistent spelling |
| A7 Classes | ✅ Only canonical class IDs; `tyre` appears only as a `debris_other` subtype attribute |

Final-run totals are recorded in §8.

## 4. Issues found and fixed

| # | Severity | Issue | Documents | Fix |
|---|---|---|---|---|
| 1 | Medium | Edge alert message format differed between deployment doc (8 fields) and edge console wireframe (10 fields) | `architecture/07-deployment.md`, `wireframes/08-edge-console.md` | Deployment doc aligned to the 10-field format, with a field legend and link |
| 2 | Medium | Milestone exit criteria disagreed: PRD M3/M4/M5 vs. Project Plan M5 vs. gate G4 (e.g. M5 listed AC-01…03, AC-01…04 and AC-01…05) | `PRD.md` §15, `planning/PROJECT_PLAN.md` §3, §10 | All aligned: M3 includes the CLI thin slice; M4 = ECE + AC-04 + JSON/CSV parts of AC-07; M5 = AC-01…05 + AC-07 |
| 3 | Medium | PRD M4 deliverables included GeoJSON/KML, but the backlog schedules them in Sprint 5 (ST-072) | `PRD.md` §15, `planning/PRODUCT_BACKLOG.md` | PRD M4/M5 deliverables aligned with the backlog |
| 4 | Medium | Review UI captures a reject reason (used for hard-negative mining), but the API and data model had no field for it | `wireframes/03`, `wireframes/05`, `architecture/05`, `architecture/06` | Added `reject_reason` (enum) to `PATCH /detections/{id}`, the detection `review` object and the `REVIEW` entity |
| 5 | Low | `GET /surveys` filters (history screen, runbook) and waterfall tile parameters (S-04) were used but not specified | `architecture/05-api-specification.md`, `wireframes/04`, `wireframes/07`, `guides/OPERATIONS_RUNBOOK.md` | Added API spec §2.3.1 and §2.3.2 |
| 6 | Low (ethics) | Exclusion of drowning-victim images stated in data docs but not in the PRD data table or Project Idea | `PRD.md` §8.1, `PROJECT_IDEA.md` §10 | Exclusion stated in both |
| 7 | Low | `NEAR_NADIR` rule used an unclear formula | `architecture/02-data-pipeline.md` | Rule set to "ground range < 0.3 × altitude" |
| 8 | Low | Review shortcut conflict: `K` meant both *reclassify* and *previous* | `wireframes/README.md` | Next/previous changed to `N`/`P` everywhere |
| 9 | Low | 40 ASCII wireframe overflow/width defects | `wireframes/03–07` | Re-rendered from templates; 0 defects remaining |
| 10 | Low | PRD and Project Idea lacked navigation to the documentation index and TODO | `PRD.md`, `PROJECT_IDEA.md` | Links added |

## 5. Consistency register (verified canonical values)

| Topic | Canonical value | Defined in | Also consistent in |
|---|---|---|---|
| Classes | `shipwreck`, `pipe`, `cylinder`, `ghost_net`, `debris_other` + `unknown_anomaly` (anomaly model only) | PRD §1.3 | 03-ml-models, 06-data-models, Annotation Guidelines, Datasets, wireframes, Test Cases, User Manual |
| Alert tiers | hazard ≥ 80 · review 50–79.9 · anomaly 30–49.9 **and** anomaly ≥ τ · hidden | PRD FR-CONF-05 | 02, 03, 06, wireframes README, User Manual, TC-CONF-002 |
| Fusion | 0.45 detector · 0.15 anomaly · 0.15 shadow · 0.15 FP filter · 0.10 persistence; penalties 0.20 dropout, 0.10 motion | 03-ml-models §7 | 02-data-pipeline (formula + YAML), Test Cases |
| Preprocessing defaults | 0.10 m/px · tiles 640 px, 25% overlap · chunks 2,000 pings / 200 overlap · Lee 5×5 · local std 7×7 · motion 5° / 5° / 3° per ping · inpaint ≤ 3 pings | 02-data-pipeline §6 | PRD FR-PRE, Annotation Guidelines, Runbook, Test Cases |
| Geo output | WGS84, 6 decimals; cross-line cluster radius 5 m | 04-geotagging, 06-data-models | PRD FR-GEO, Test Cases, User Manual |
| Worked example | `SRV-20260913-001-D0003`, ghost_net, 87.4%, 13.084120 N / 80.312750 E (13° 05' 02.83" N, 80° 18' 45.90" E), 6.2 × 3.1 m, 14.8 m², depth 18.5 m, ± 4.2 m, fused 0.78 | 06-data-models §2 | Project Idea, README, PRD §9, 05, wireframes 02/03/08, Test Cases, Demo Script |
| Formulas | ground range √(s² − h²); height h = Ls·H/(r + Ls); shadow Ls = h·r/(H − h); layback √(L² − d²) (e.g. 100 m, 20 m → 97.98 m); heading term r·sin σ (50 m, 2° → 1.75 m) | 04-geotagging | 02, 03, Test Cases |
| API | Base `/api/v1`; WebSocket `/ws/jobs/{job_id}`; job states queued/running/completed/completed_with_warnings/failed/cancelled | 05-api-specification | 01, 07, wireframes, Test Cases, Runbook |
| Error codes | VALIDATION_ERROR, NAV_CSV_INVALID, NOT_FOUND, JOB_NOT_CANCELLABLE, FILE_TOO_LARGE, UNSUPPORTED_FORMAT, CORRUPT_HEADER, CRS_REQUIRED, INTERNAL_ERROR, MODELS_NOT_LOADED | 05 §4 | 02 §5, Test Cases, Runbook |
| Quality flags | DROPOUT, HIGH_MOTION, NEAR_NADIR, SURFACE_RETURN_BAND, TILE_EDGE, GPS_INTERPOLATED, LAYBACK_ESTIMATED, HEADING_FROM_COG, NO_ALTITUDE_BOTTOM_TRACKED, NOT_GEOTAGGED | 06 §2.2 | 02, 04, User Manual, Test Cases |
| NFR targets | 1 km line: ≤ 60 s GPU · ≤ 5 min CPU · ≥ 1× Jetson (target 5×); first detection ≤ 15 s; progress ≤ 5 s; model ≤ 25 MB / INT8 ≤ 10 MB; ≤ 8 GB RAM; upload ≤ 2 GB | PRD §7 | Test Plan, Test Cases, Backlog, Deployment, SIH deck |
| Success metrics | mAP@50 ≥ 0.70 · key-class recall ≥ 0.85 · ghost-net recall ≥ 0.80 (synthetic holdout) · FP/km² −50% · ECE ≤ 0.10 · geo median ≤ 10 m · analyst time −70% · first report ≤ 5 min | PRD §11 | Test Plan, Test Cases, Model Card template, SIH deck, Demo Script |
| Plan | S0–S6; milestones M0–M6 on Fridays 2026-09-18 … 10-30; gates G1–G5 | Project Plan §3, §10 | PRD §15, Backlog, TODO |
| Backlog | 12 epics, 91 stories; points S0 12 · S1 33 · S2 42 · S3 52 · S4 52 · S5 47 (+5 ⭐) · S6 44 (+18 ⭐) | Product Backlog | TODO |
| Dataset facts | AI4Shipwrecks 286 images / 28 wrecks; mine SSS 1,170 images (MILCO/NOMBO); KLSG 385 wreck · 36 victim · 62 airplane · 129 mine · 578 seafloor | Datasets | Project Idea, PRD, Literature Review, SIH deck |
| Roles | R1 ML · R2 Sonar · R3 Geo · R4 Backend · R5 Frontend · R6 Integration/Edge/PM | Project Plan §6 | Backlog, TODO, DMP, Runbook, Demo Script |

## 6. Open items (need human action; can't be verified from the documents alone)

| # | Item | Owner | Tracked in |
|---|---|---|---|
| 1 | Team review and sign-off of PRD and architecture: ✅ **Closed 2026-09-13** on team lead (R6) approval ([PHASE0_REVIEW_SIGNOFF](../planning/PHASE0_REVIEW_SIGNOFF.md)); R1–R5 confirm in Sprint 0 | R6 + all | TODO Phase 0 → Phase 1 |
| 2 | Licences marked **verify**: ✅ **Resolved 2026-09-13, except AI4Shipwrecks.** Confirmed from primary sources. Consequences: react-leaflet (Hippocratic 2.1) dropped for direct Leaflet (ADR-009 amended); SAM 2 approved and SAM 3 excluded (military-use clause); S3Simulator and KLSG-II excluded (no licence); Figshare mine dataset CC BY 4.0; NOAA "not for navigation" notice required. **AI4Shipwrecks licence still open:** the record blocks automated access, so it needs a manual browser check (TODO Phase 1) | R6 | TODO Phase 0 → Phase 1; Licences §2–3 |
| 3 | References marked † in the Literature Review: ✅ **Resolved 2026-09-13.** All 11 project-specific references checked against Crossref and publisher records; 7 corrected (e.g. STARS → BMVC 2023, S3Simulator → ICPR 2024 LNCS 15316); no † remain | R1 | TODO Phase 0 |
| 4 | Project licence decision: ✅ **Resolved 2026-09-13.** AGPL-3.0 ([ADR-013](../architecture/08-architecture-decisions.md#adr-013--project-licence-agpl-30), official [LICENSE](../../LICENSE) text from gnu.org) | Team | TODO Phase 0 |
| 5 | Official SIH template and schedule: ✅ **Resolved 2026-09-13.** SIH 2026 idea template confirmed (≤ 6 slides, PDF only, fixed headings); PS 26057 confirmed on the official list; idea deadline **30 Sept 2026** added as milestone IS (an older PDF says 15 Sept, so **confirm with the SPOC**); finale proposed Dec 2026 | R6 | TODO Phase 0 → Phase 1 |
| 6 | PRD open questions Q1–Q7 (NIOT data, sonar models, report formats, edge hardware, taxonomy, ghost-net samples, datum) | R6, R2, R3 | PRD §16; TODO Phases 1–2 |
| 7 | Commands marked *(planned)* in Developer Setup / README / User Manual must be checked against real code | R6 | ST-114 (Phase 7) |
| 8 | `<placeholder>` metrics in deck, demo script and report must be filled with measured values | R6, R1 | TODO Phase 7 |
| 9 | Library API snippets (Ultralytics, anomalib, SAHI, GDAL) must be checked against pinned versions | R1, R6 | ST-003, ST-050, ST-053 |

## 7. Limitations of this verification

- External facts (dataset licences, current SIH templates, third-party library behaviour) were **not** re-verified online during this check; they are listed as open items.
- Mermaid diagram syntax was reviewed manually but not rendered in a Mermaid engine as part of the automated script. Preview in GitHub or VS Code during review.
- Spelling and grammar weren't checked automatically.
- Heading slugs follow GitHub's algorithm; other Markdown renderers may generate different anchors.

## 8. Re-running verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docs/verify_docs.ps1
```
Exit code `0` = pass; `1` = problems listed as `LINK`, `ANCHOR`, `ID`, or `FRAME` lines.

**Final run for this report.** An earlier run flagged one false positive: a link-like example inside inline code in this report. It was fixed by rewording the text and making the script ignore inline code spans.

| Date | Files | Relative links | Defined IDs | Problems | Run by |
|---|---|---|---|---|---|
| 2026-09-13 | 48 | 373 | 370 | 0 (exit code 0) | Documentation baseline, after fixes #1–#10 |

## 9. Sign-off

| Role | Name | Date | Approved |
|---|---|---|---|
| PM / Integration (R6) | | | ☐ |
| ML Lead (R1) | | | ☐ |
| Geospatial Engineer (R3) | | | ☐ |
| Backend Engineer (R4) | | | ☐ |
| Frontend Engineer (R5) | | | ☐ |
