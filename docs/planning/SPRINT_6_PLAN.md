# Sprint 6 Plan — Hardening, Validation, Edge & Demo

| | |
|---|---|
| **Sprint** | S6 · 2026-10-26 → 2026-10-30 (illustrative dates, see [Project Plan](PROJECT_PLAN.md)); started early on 2026-09-14 |
| **Milestone / gate** | **M6** · **G5** (release candidate, [Test Plan §8.2](../testing/TEST_PLAN.md#82-release-candidate-m6-exit-criteria)) |
| **Sprint goal** | *A hardened, measured and deployable build: robustness and security tests automated, benchmarks recorded, Docker and edge watch mode available, P1 screens for review, history and settings, and documentation that matches the software.* |
| **Capacity** | 6 people; committed **56 points** (backlog allocation) plus 35 items carried over from Phase 6 |

**Related:** [Product Backlog](PRODUCT_BACKLOG.md) · [TODO Phase 7](../../TODO.md#phase-7--sprint-6--hardening-validation-edge--demo) · [Deployment](../architecture/07-deployment.md) · [Test Plan](../testing/TEST_PLAN.md) · [Sprint 5 plan](SPRINT_5_PLAN.md)

---

## 1. Committed stories

| Story | Title | Pts | Owner | Acceptance (short) | Tests | Can finish without people/hardware/data? |
|---|---|---|---|---|---|---|
| ST-037 | Charted-wreck geolocation validation | 3 | R3 | Error measured and documented | TC-GEO-012 | **No** — tooling only; needs a survey over a charted wreck (ST-013) |
| ST-111 | Robustness suite | 3 | R6 | All robustness TCs pass (AC-06) | TC-ROB-001…006, TC-ING-012 | Yes (TC-DET-008 needs TD-08) |
| ST-112 | Performance benchmarks | 3 | R6 | Results table in test report | TC-PERF-001…006, TC-WS-002/003 | CPU, memory, latency yes; GPU and Jetson rows need hardware |
| ST-113 | Usability test ≥ 3 users | 2 | R5 | Findings + fixes logged | TC-USE-001/002 | **No** — people |
| ST-005 | Docker images + compose | 5 | R6 | `docker compose up` → :8080 healthy | TC-E2E-004 | Images built and scanned in CI (no Docker on the dev laptop); fresh-install timing manual |
| ST-101 | TensorRT on Jetson | 5 | R6 | INT8 drop ≤ 3 mAP points | TC-EDGE-002/004, TC-DET-009 | **No** — Jetson hardware (waiver) |
| ST-103 ⭐ | Edge `watch` mode | 5 | R6 | New file processed automatically | TC-EDGE-003 | Yes |
| ST-096 | Review queue (S-05) | 5 | R5 | 20 items in ≤ 3 min | TC-UI-011, TC-USE-002 | Yes (timed user run manual) |
| ST-097 ⭐ | Waterfall viewer (S-04) | 8 | R5 | Smooth scroll on 20k pings | — | **Dropped this sprint** (stretch; needs stored per-ping imagery) |
| ST-098 | History + settings (S-07) | 5 | R5 | CRUD per wireframe | new UI tests | Yes |
| ST-099 | Offline basemap | 3 | R5 | AC-10 passes | TC-UI-012, TC-E2E-005 | Serving and switching yes; demo-region MBTiles and network-off run manual |
| ST-025 ⭐ | JSF + SL2/SL3 readers | 5 | R2 | One sample per format → `SonarLog` | TC-ING-013 | **Dropped this sprint** (stretch; no sample files) |
| ST-114 | Verify User Manual and Runbook | 2 | R6 | All commands/screens checked | — | Yes |
| ST-115 | Deck + demo script; 3 rehearsals | 3 | R6 | Timed; backup video | — | Metrics yes where measured; rehearsals and video need people |
| ST-116 | Final project report | 5 | R6 | Sections complete with measured results | — | Draft yes; GPU/wreck/usability results pending |
| | **Total** | **62** | | | | |

Other tasks: TC-SEC-001…006 and dependency/image scans; replace `<placeholder>` metrics; licence compliance checklist; backup video A6 and second laptop; TSR-M6; tag `v1.0.0-rc1`; documentation check.

## 2. Decisions made at planning (recorded in ADR-019)

1. **Environment variables** from 07 §6 are honoured: `SS_CONFIG`, `SS_DATA_DIR` (`SONARSENTINEL_DATA_DIR` stays as an alias), `SS_MODELS_DIR`, `SS_RUNTIME`, `SS_MAX_UPLOAD_GB`, `SS_OFFLINE_TILES`, `SS_KEEP_WORK_FILES`, `SS_LOG_LEVEL`, `SS_WORKERS` (1 supported), `SS_JOB_TIMEOUT_S`.
2. **Failure handling:** a failing chunk is retried once, then skipped with `CHUNK_SKIPPED`; an unavailable accelerator (`tensorrt`, `cuda`) falls back to ONNX Runtime or PyTorch CPU with `CPU_FALLBACK`; jobs over the time limit fail with `JOB_TIMEOUT`.
3. **Settings** are one JSON document (`GET/PUT /api/v1/settings`) stored in the data folder and applied to new jobs only.
4. **Offline tiles** are served from an MBTiles file at `/api/v1/tiles/{z}/{x}/{y}.png`; tiles must be rendered by the team (OSM tile policy forbids bulk downloads).
5. **Survey delete** refuses queued/running jobs and keeps the label store.
6. **Watch mode** polls the folder, processes each file once after its size is stable, remembers state across restarts and prints compact alert lines; tailing growing files is not implemented.
7. **Benchmarks** run `scripts/benchmark.py` three times per input in separate processes and report medians, first-detection latency, progress gaps, peak memory and model sizes; a synthetic 1 km line stands in for the missing reference line.
8. **Stretch stories ST-097 and ST-025 are dropped** this sprint; ST-101 needs a Jetson and ST-037 a charted-wreck survey.
9. **No `v1.0.0-rc1` tag** until TSR-M6 recommends Go: a release-candidate tag on a build that fails its gate would mislead.

## 3. Constraints

- CPU-only development laptop (i5-13420H, 16 GB), no Docker, no GPU, no Jetson.
- No survey over a charted wreck, no labelled real test set (TD-08), no contact-free lines (TD-11), no curated false positives (TD-13).
- People-dependent items: usability test, rehearsals, backup video, screenshots, P0 freeze.

## 4. Exit criteria (M6 / G5)

- [ ] [Test Plan §8.2](../testing/TEST_PLAN.md#82-release-candidate-m6-exit-criteria) release-candidate criteria met
- [ ] Demo rehearsed 3× (including one simulated failure)

**Result (2026-09-14, [TSR-M6](../testing/reports/TSR-M6.md)): G5 No-go; no release-candidate tag.** Done without people or hardware: ST-005, ST-096, ST-098, ST-099, ST-103, ST-111, ST-112 (CPU rows), ST-114, security scans and TC-SEC-001…003, TSR-M6. Open: ST-037 (charted-wreck survey), ST-101 (Jetson), ST-113 (users), ST-115 rehearsals and video, ST-116 final report markers, GPU-trained models, NFR-04/05 streaming fixes. ST-097 and ST-025 were dropped.

## 5. Risks this sprint

| Risk | Trigger | Response |
|---|---|---|
| Docker images fail to build | CI `docker` job fails | Fix in CI iterations; keep the conda install path documented |
| Major frontend upgrades break tests | vite/vitest/react-router upgrade fails build | Pin to the newest version that passes and record remaining advisories |
| Benchmarks on a shared laptop are noisy | Run-to-run spread > 20% | Report median of 3 and spread; repeat on an idle machine |
| G5 cannot pass | AC-05/AC-08/geolocation/GPU items open | Honest TSR-M6 with waivers; no release-candidate tag |
