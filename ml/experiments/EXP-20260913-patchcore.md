# EXP-20260913-patchcore

| | |
|---|---|
| **Owner role** | R1 |
| **Date(s)** | 2026-09-13 |
| **Backlog story** | ST-053 |
| **Status** | done |
| **Git commit** | Sprint 3 commit on `main` (after `4237954`) |
| **Model kind** | anomaly |

## 1. Hypothesis
A PatchCore memory bank of ResNet-18 patch features from object-free seafloor separates tiles with man-made objects from normal seabed on a **held-out site** with tile AUROC ≥ 0.90, so it can flag objects the detector has no class for (`unknown_anomaly`).

## 2. Baseline
None: first anomaly model.

## 3. What changed
First run. PatchCore is implemented in `sonarsentinel/detect/anomaly.py` instead of anomalib ([ADR-016](../../docs/architecture/08-architecture-decisions.md)).

## 4. Setup

| Item | Value |
|---|---|
| Normal pool | `data/processed/anomaly/normal` (1,687 tiles of 256 px, mine-SSS D2, object-free images; ST-012) |
| Memory-bank tiles | 600, sampled from sites other than 2017 |
| Evaluation normals | 171 tiles from held-out site 2017 |
| Evaluation positives | 400 tiles: synthetic ghost-net holdout (backgrounds from site 2017) + synthetic pipes (`pipe@1.0.0` train split) |
| Model | ResNet-18 (torchvision ImageNet weights), layer2 + layer3 features, 3×3 neighbourhood pooling |
| Key hyperparameters | input 256 px · 150,000 sampled patches · greedy coreset 3,000 (128-d random projection) · kNN distance · Gaussian σ = 4 on the heatmap |
| Thresholds | tile: p99 of held-out normal scores; pixel: p99.9 of held-out normal heatmaps |
| Seed | 0 |
| Hardware | Intel i5-13420H, 16 GB RAM, CPU only |
| Software | torch 2.14.0+cpu · torchvision 0.29.0+cpu |
| Wall-clock time | 3.7 min |

**Command**
```bash
python ml/train_anomaly.py --holdout-groups 2017 --name patchcore-seafloor --version 0.1.0
```

## 5. Results (held-out site)

| Metric | Value |
|---|---|
| Tile AUROC | **0.957** |
| Tile threshold (p99 normal) | 3.380 |
| Recall at tile threshold | 0.74 |
| False-alarm rate on held-out normals | 1.2% |
| Pixel threshold (p99.9 normal) | 2.947 |

**Artifacts:** `models/anomaly/patchcore-seafloor/0.1.0/` — `memory_bank.pt`, `model.json`, `metrics.json`.

## 6. Observations
- Positives are synthetic only; no real object tiles were in the evaluation, so real-world recall is unknown.
- Pipe tiles come from the generator's train split, whose backgrounds are not restricted to the held-out site; the ghost-net holdout is the cleaner test.
- The pipeline (`sonarsentinel detect`) loads the model and turns heatmap regions outside detector boxes into `unknown_anomaly` detections. It ran end to end on a USGS Klein 3900 line; the memory bank holds no Klein seabed, so that sonar's texture is itself out of distribution and scores there are not trustworthy yet.

## 7. Decision
- [x] **Adopt**: `anomaly/patchcore-seafloor@0.1.0`, configured in `backend/configs/pipeline.yaml`

## 8. Next steps
1. Evaluate on real objects: MILCO cylinders from the calib/test sites, AI4Shipwrecks wrecks once ST-010 lands.
2. Add seabed from each supported sonar (USGS Klein lines, later NIOT data) to the memory bank, or keep one bank per sonar family.
3. Tune the anomaly weight and thresholds on the calib split during fusion (ST-063).
