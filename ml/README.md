# ml

Dataset tooling, synthetic data generators, training, calibration and evaluation.

| Path | Purpose | Planned |
|---|---|---|
| `datasets/LICENSES.md` | Dataset licence register (required before any dataset enters a manifest) | ✅ Sprint 0 |
| `datasets/` | Download and conversion scripts, `sonar-seg.yaml` | Sprints 1–2 (ST-010…015) |
| `synth/` | Ghost-net, pipe and cylinder generators | Sprints 2–3 (ST-016…018) |
| `train_detector.py`, `train_anomaly.py`, `train_fp_filter.py`, `calibrate.py`, `evaluate.py` | Training and evaluation | Sprints 3–4 (ST-050…064) |
| `experiments/` | Experiment logs ([template](../docs/ml/EXPERIMENT_LOG_TEMPLATE.md)) | From Sprint 3 |

Datasets and model weights are **never committed**; see the [Data Management Plan](../docs/data/DATA_MANAGEMENT_PLAN.md). ML dependencies: `backend/requirements-ml.txt`.
