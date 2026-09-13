# Sprint 4 Plan — Scoring, Reports & API

| | |
|---|---|
| **Sprint** | S4 · 2026-10-12 → 2026-10-16 (illustrative dates, see [Project Plan](PROJECT_PLAN.md)); started early on 2026-09-13 |
| **Milestone / gate** | **M4** (Scoring, reports & API) · **G3** (model quality) |
| **Sprint goal** | *Every detection carries an explainable, calibrated confidence and a chip; surveys can be uploaded through the API and processed by real background jobs.* |
| **Capacity** | 6 people; committed **46 points** (backlog allocation) plus 20 items carried over from Phase 4 |

**Related:** [Product Backlog](PRODUCT_BACKLOG.md) · [TODO Phase 5](../../TODO.md#phase-5--sprint-4--scoring-reports--api) · [ML Models §5](../architecture/03-ml-models.md) · [API](../architecture/05-api-specification.md) · [Data models](../architecture/06-data-models.md) · [Sprint 3 plan](SPRINT_3_PLAN.md)

---

## 1. Committed stories

| Story | Title | Pts | Owner | Acceptance (short) | Tests | Can finish without people/data? |
|---|---|---|---|---|---|---|
| ST-055 | Small-object variant (1024 / P2) | 5 | R1 | Decision recorded with metrics | — | **No** — waits for ST-051 (GPU or ≥ 6 GB free RAM) |
| ST-060 | Shadow consistency score + height | 5 | R1 | ≥ 50% of shadow-only FPs demoted (AC-08) | TC-CONF-004…006 | Code and synthetic tests yes; AC-08 needs 50 curated FPs (TD-13) |
| ST-061 | Shape/texture features | 3 | R1 | < 5 ms per detection | — | Yes |
| ST-062 | LightGBM FP filter | 3 | R1 | AUROC reported; SHAP summary | TC-CONF-010 | Tooling yes; meaningful numbers need labelled real detections |
| ST-063 | Fusion + weight tuning | 3 | R1 | AP(fused) ≥ AP(detector) | TC-CONF-003 | Tooling yes; tuning on the CPU baseline is indicative only |
| ST-064 | Isotonic calibration, reliability, ECE | 3 | R1 | ECE ≤ 0.10 on calibration split | TC-CONF-008 | Tooling yes; the calib split has 49 objects |
| ST-065 | Alert tiers, penalties, flags | 2 | R1 | TC-CONF tests pass | TC-CONF-001, 002, 007 | Yes |
| ST-034 | Layback correction | 3 | R3 | Unit tests; `LAYBACK_ESTIMATED` | TC-GEO-009 | Yes |
| ST-038 | Cross-line clustering + persistence | 3 | R3 | Same object on 2 lines merged, `n_views = 2` | TC-GEO-013 | Yes (synthetic overlapping lines) |
| ST-070 | JSON Schema + JSON export | 3 | R4 | Exports validate in CI | TC-REP-001, 005, 006 | Yes (mostly done in Sprint 3) |
| ST-071 | CSV export | 1 | R4 | Opens correctly in Excel/LibreOffice | TC-REP-002 | Automated parts yes; the spreadsheet check is manual |
| ST-073 | Detection chips with overlays | 2 | R4 | One chip per detection; overlay variants | TC-REP-009 | Yes |
| ST-081 | `POST /surveys/validate`, `POST /surveys` | 3 | R4 | TC-API upload tests pass | TC-API-001…003 | Yes |
| ST-082 | Job manager, worker, cancel, status | 5 | R4 | Cancel stops within one chunk | TC-API-006 | Yes |
| ST-085 | SQLite storage layer | 3 | R4 | Migrations run; ER model implemented | — | Yes |
| ST-091 | Upload screen (S-01) | 5 | R5 | Wireframe states implemented | TC-UI-001, 002 (automated in S5) | Yes |
| | **Total** | **52** | | | | |

## 2. Decisions made at planning (recorded in ADR-017)

The architecture documents leave these open; the choices below are provisional and can be revisited by R1/R4 at the sprint review.

1. **Shadow score:** highlight contrast × far-range shadow darkness × ordering, 0–1, from the processed ground-range image; height `h = Ls·H / (r + Ls)` ([04 §6](../architecture/04-geotagging-engine.md)); `height_m` null when no usable shadow.
2. **Missing score components:** fused = Σ wᵢ·sᵢ over the components present ÷ Σ wᵢ of those components, minus penalties, clipped to [0, 1]. The breakdown in `scores` lets anyone recompute it (TC-CONF-003).
3. **Persistence:** `1 − 0.5^n_views` (0.50 for one view, 0.75 for two), matching the data-model example.
4. **`anomaly` tier:** confidence 30–49.9 **and** anomaly score ≥ τ (`anomaly.threshold`), for every detection with an anomaly score, not only `unknown_anomaly`.
5. **`NEAR_NADIR`, `TILE_EDGE`:** flags only, no penalty weight (none is specified in the fusion formula).
6. **Calibration data:** the site-held-out `calib` split (site 2021), never the validation split used for fusion tuning.
7. **Chips:** rendered once at the end of the job for every overlay (`mask`, `shadow`, `anomaly`, `none`) under `results/<survey_id>/chips/`.
8. **Storage:** SQLite via SQLAlchemy 2.0; tables per the ER model plus the full detection JSON (the CSV/JSON need fields the ER table lacks); versioned in-app migrations (no Alembic dependency).
9. **Jobs:** one background worker thread and a queue for the prototype; the pipeline releases the GIL in NumPy/OpenCV/PyTorch. Process workers (ADR-001) return with ST-005 Docker packaging if CPU contention shows up.
10. **Multi-file surveys:** `run_survey` processes lines in upload order, renumbers detection IDs across lines and then clusters across lines (ST-038).

## 3. Constraints

- **No CUDA GPU; RAM shared with other applications.** The ST-051 ablation could not run (EXP-20260913-synth), so ST-055 stays blocked. G3's model-quality criterion (≥ 80% of PRD targets: mAP@50 ≥ 0.56, ghost-net recall ≥ 0.64) cannot be met by the CPU baseline (val mAP@50 0.283).
- **Labelled data:** FP filter, fusion weights and calibration are fitted on the mine-SSS splits with the CPU baseline. The numbers validate the tooling, not the model; they are refitted when GPU-trained detectors and real labels (ST-014, TD-11, TD-13) arrive.
- **CI has no torch/ultralytics:** API and job tests use the rule-based detector on synthetic XTF.

## 4. Exit criteria (M4 / G3)

- [ ] ECE ≤ 0.10 on the calibration split; AC-04 (confidence and tier parts); JSON/CSV parts of AC-07 *(ECE 0.048 ✓, AC-04 confidence/tier ✓, JSON ✓; CSV spreadsheet check open — [TSR-M4](../testing/reports/TSR-M4.md))*
- [ ] Model metrics ≥ 80% of PRD targets — **not met** on the CPU baseline (val mAP@50 0.283); see §3
- [x] Upload API and jobs run the real pipeline *(TC-API-001, 006 on synthetic XTF)*

## 5. Risks this sprint

| Risk | Trigger | Response |
|---|---|---|
| Calibration fitted on too few objects | ECE CI wider than ±0.05 or calib split < 100 detections | Report the CI; refit when ST-014 labels land |
| Scoring changes break report determinism | TC-REP-006 fails | Seed every random step; keep features deterministic |
| Background thread starves the API on CPU | Health endpoint latency > 1 s during a job | Lower worker priority or switch to a process worker |
| Shadow score unreliable on real data | AC-08 < 50% on TD-13 | Keep the shadow weight at 0.15 or lower it after tuning; needs TD-13 |
