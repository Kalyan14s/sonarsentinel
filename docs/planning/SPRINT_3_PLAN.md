# Sprint 3 Plan — Models & Thin Slice

| | |
|---|---|
| **Sprint** | S3 · 2026-10-05 → 2026-10-09 (illustrative dates, see [Project Plan](PROJECT_PLAN.md)); started early on 2026-09-13 |
| **Milestone / gate** | **M3** (Models & thin slice) · **G2** (thin slice: `sonarsentinel detect sample.xtf` produces a schema-valid report; integration test in CI) |
| **Sprint goal** | *First trained detector and anomaly model, and one command that turns a sonar file into a schema-valid report, with the API and dashboard skeletons ready for Sprint 4.* |
| **Capacity** | 6 people; committed **49 points** (backlog allocation) |

**Related:** [Product Backlog](PRODUCT_BACKLOG.md) · [TODO Phase 4](../../TODO.md#phase-4--sprint-3--models--thin-slice) · [ML Models](../architecture/03-ml-models.md) · [API](../architecture/05-api-specification.md) · [Sprint 2 plan](SPRINT_2_PLAN.md)

---

## 1. Committed stories

| Story | Title | Pts | Owner | Acceptance (short) | Tests |
|---|---|---|---|---|---|
| ST-017 | Synthetic pipe and cylinder generators | 5 | R2 | 1,000 tiles each; visual review | — |
| ST-018 | Synthetic realism review | 2 | R2 | ≥ 70% rated plausible | people |
| ST-050 | Baseline YOLO11s-seg on real data | 5 | R1 | Metrics logged; model card draft | TC-DET-001 (partial) |
| ST-051 | Synthetic data + augmentations; ablation | 5 | R1 | Ablation table in experiment log | TC-DET-003 (partial) |
| ST-052 | SAHI sliced inference | 3 | R1 | Small-object recall sliced ≥ non-sliced | TC-DET-004 |
| ST-053 | PatchCore + `unknown_anomaly` | 5 | R1 | AUROC reported; anomalies with heatmap | TC-DET-005 |
| ST-057 | `ml/evaluate.py` | 3 | R1 | Runs on any registry model | — |
| ST-033 | Measurements | 3 | R3 | Rectangle measured within 1 px | TC-GEO-006…008 |
| ST-054 | Merge/dedupe across tiles and chunks | 3 | R4 | No duplicates on overlap fixture | TC-DET-006 |
| ST-074 | CLI `detect`, `validate`, `serve` | 3 | R4 | API spec §5 commands work | TC-REP-008 |
| ST-075 | `pipeline.py` orchestrator | 5 | R4 | Same input + config ⇒ identical report | TC-REP-005, TC-REP-006 |
| ST-080 | FastAPI skeleton | 2 | R4 | `/docs` lists endpoints | TC-API-008 |
| ST-087 | Mock API server | 2 | R4 | Frontend runs against mock with events | TC-API-004…007 (mock) |
| ST-090 | App shell, routing, tokens, API types | 3 | R5 | Navigation per wireframes; class tokens | frontend unit tests |
| ST-110 | Integration test: XTF → schema-valid report | 3 | R6 | < 5 min in CI | TC-REP-001 |
| | **Total** | **49** | | | |

## 2. Constraints and decisions

- **No CUDA GPU on the development machine** (Intel i5-13420H, 16 GB RAM). Sprint 3 models are **short CPU baselines**; schedules and wall-clock times are recorded in the experiment logs. Full 200-epoch training moves to a GPU (Kaggle/Colab or lab machine) before Gate G3.
- **Thin slice without trained weights:** the pipeline ships a transparent rule-based `classical-bright-target@0.1.0` detector so the CLI, CI integration test and mock fixtures work everywhere; reports name the detector, so it can't be mistaken for YOLO11-seg.
- **PatchCore implemented directly in PyTorch** (paper algorithm, ResNet-18 features) instead of anomalib, whose releases pin torch/lightning versions that conflict with the installed torch.
- **Windows OpenMP clash** (conda NumPy/SciPy + pip PyTorch): training scripts set `KMP_DUPLICATE_LIB_OK=TRUE`.

## 3. Exit criteria (M3 / G2)

- [ ] YOLO11-seg and PatchCore trained; baseline metrics recorded (experiment logs + model card draft)
- [ ] `sonarsentinel detect sample.xtf` gives schema-valid JSON/CSV; integration test green in CI
- [ ] API skeleton and mock server running; dashboard shell builds against the mock

## 4. Risks this sprint

| Risk | Trigger | Response |
|---|---|---|
| CPU-only training too slow or too weak | Baseline mAP@50 far below target after the short schedule | Record as CPU baseline; schedule GPU training; don't tune thresholds on it |
| Tiny real training set (~100 positive images, one class) | Validation metrics swing between runs | Report bootstrap CIs; add AI4Shipwrecks (ST-010) and NOMBO review (ST-011) |
| Synthetic ghost nets unrealistic | Realism review < 70% plausible (ST-018) | Tune generator; keep synthetic ≤ 40% once real positives exist |
| R1 trigger: ghost-net recall < 0.60 on the synthetic holdout | Measured after ST-051 | Schedule ST-055 small-object variant in Sprint 4 |
