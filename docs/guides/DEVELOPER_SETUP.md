# SonarSentinel — Developer Setup Guide

| | |
|---|---|
| **Version** | v1.0 · 2026-09-13 |
| **Owner** | Integration & Edge Lead (R6) |
| **Applies to** | Windows 10/11, Ubuntu 22.04+, NVIDIA Jetson (JetPack 6) |

**Related:** [Contributing](../../CONTRIBUTING.md) · [Deployment](../architecture/07-deployment.md) · [Operations Runbook](OPERATIONS_RUNBOOK.md)

> Commands marked *(planned)* depend on files created in Sprint 0 (ST-001…ST-006). Update this guide in the PR that creates them.

---

## 1. Prerequisites

| Tool | Version | Why | Install |
|---|---|---|---|
| Git | latest | Source control | https://git-scm.com |
| **Miniforge** (conda-forge) | latest | Python env with **GDAL** and geospatial libraries that install cleanly on Windows | https://github.com/conda-forge/miniforge |
| Node.js | current LTS | Frontend (React + Vite) | https://nodejs.org |
| Docker Desktop / Docker Engine | latest | Full-stack runs, deployment testing | https://docs.docker.com |
| NVIDIA driver + GPU (optional) | recent | Training and fast inference | NVIDIA website |
| NVIDIA Container Toolkit (Linux, optional) | latest | GPU inside Docker | NVIDIA docs |
| VS Code (recommended) | latest | Editor | https://code.visualstudio.com |

**Recommended VS Code extensions:** Python, Pylance, Ruff, Mypy Type Checker, ESLint, Prettier, Markdown Preview Mermaid Support, Docker, GitLens.

### ⚠ Windows notes
1. **Don't rely on the `python` shortcut.** If typing `python` opens the Microsoft Store, Python isn't installed. Use the conda environment below, and optionally turn off the store aliases in *Settings → Apps → Advanced app settings → App execution aliases*.
2. **Keep large data and the repo out of OneDrive.** Syncing tens of GB of sonar data and model files through OneDrive is slow and can lock files, and paths with spaces cause tool problems. Clone the code to a local path such as `C:\dev\sonarsentinel`, and keep `data/` on a local or external drive.
3. Enable long paths: `git config --system core.longpaths true` (from an admin terminal).
4. For Docker on Windows, use the WSL 2 backend and give it enough memory (≥ 8 GB) in `.wslconfig`.

## 2. Get the code

```bash
git clone <repository-url> sonarsentinel
cd sonarsentinel
```

## 3. Backend and ML environment

### 3.1 Create the conda environment (`backend/environment.yml`)

The environment holds the core, geospatial and developer tools used from Sprint 0 to Sprint 2. ML packages are added in Sprint 3 (§3.2), which keeps the first setup fast and avoids PyTorch/anomalib version conflicts.

| File | Contents | When |
|---|---|---|
| `backend/environment.yml` | Python 3.11, NumPy/SciPy/pandas, GDAL, rasterio, pyproj, Shapely, PyYAML, Typer, pytest, ruff, mypy, pre-commit; pip: pyxtf, OpenCV (headless), types-PyYAML | Sprint 0 onwards |
| `backend/requirements-ml.txt` | Ultralytics, SAHI, anomalib, LightGBM, scikit-learn, ONNX Runtime | Sprint 3, after PyTorch (§3.2) |
| `backend/pyproject.toml` extras | `[dev]`, `[geo]`, `[api]` | As needed |

```bash
conda env create -f backend/environment.yml
conda activate sonarsentinel
```

> **Windows, Miniforge installed without "Add to PATH":** open the **Miniforge Prompt** from the Start menu, or call conda directly, e.g. `%USERPROFILE%\miniforge3\Scripts\conda.exe run -n sonarsentinel pytest`.

### 3.2 Install PyTorch correctly (GPU or CPU)
Install PyTorch **before** relying on Ultralytics/anomalib, so a CPU-only build isn't pulled in by accident:

1. Open https://pytorch.org/get-started/locally/ and select your OS, `pip`, Python and CUDA version (or CPU).
2. Run the command it shows inside the activated environment.
3. Verify:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

4. Then install the ML packages:

```bash
pip install -r backend/requirements-ml.txt
```

> Pin exact versions of `torch`, `ultralytics`, `anomalib` and `lightning` in `backend/requirements-ml.lock.txt` once a working combination is found. anomalib is sensitive to torch/lightning versions.

**Verified combination (2026-09-13, Windows 11, CPU only):** `torch 2.14.0+cpu`, `torchvision 0.29.0+cpu`, `ultralytics 8.4.150`, `sahi 0.12.6`, `onnxruntime 1.30.0`, `scikit-learn 1.9.1`, `lightgbm 4.7.0`, with NumPy 2.4.6 and OpenCV 5.0 unchanged. CPU wheels:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

- **anomalib is not needed:** PatchCore is implemented in `sonarsentinel/detect/anomaly.py` ([ADR-016](../architecture/08-architecture-decisions.md#adr-016--sprint-3-ml-stack-own-patchcore-rule-based-stand-in-detector-cpu-baselines)).
- **Windows "OMP: Error #15":** conda NumPy/SciPy and pip PyTorch load two OpenMP runtimes. The training scripts set `KMP_DUPLICATE_LIB_OK=TRUE`; set it yourself in a shell that imports both (`$env:KMP_DUPLICATE_LIB_OK="TRUE"` in PowerShell).
- **Training and evaluation (Sprint 3):**

```bash
python ml/datasets/prepare_yolo.py --variant real            # 3-channel YOLO folders from the manifest
python ml/train_detector.py --data data/processed/yolo/0.1.0-real/data.yaml \
    --model models/pretrained/yolo11s-seg.pt --name yolo11s-seg-sonar-real --version 0.1.0 --epochs 20 --batch 8
python ml/evaluate.py --data data/processed/yolo/0.1.0-real --split val \
    --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt --out models/detector/yolo11s-seg-sonar-real/0.1.0/eval_val
python ml/train_anomaly.py --holdout-groups 2017 --version 0.1.0   # PatchCore memory bank + AUROC
python ml/export_onnx.py --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt \
    --data data/processed/yolo/0.1.0-real --split val --images 100   # best.onnx + TC-EDGE-001 parity (needs onnx, onnxslim)
```

### 3.2.1 Frontend (dashboard)

Node.js 22 LTS. From `frontend/`:

```bash
npm ci
npm run dev          # http://localhost:5173, proxies /api and /ws to SONARSENTINEL_API (default :8001)
npm run lint && npm run typecheck && npm test && npm run build
npm run gen:types    # regenerate src/api/report-schema.ts after changing the report JSON Schema
```

For frontend work without the full backend, run the mock API: `sonarsentinel serve --mock --port 8001` (needs `pip install -e "backend[api]"`).

### 3.3 Install the package and hooks

```bash
pip install -e "backend[dev]"
pre-commit install
sonarsentinel --help
```

### 3.4 Verify geospatial and sonar libraries

```bash
python -c "import rasterio, pyproj, cv2, pyxtf; from osgeo import gdal; print('GDAL', gdal.__version__, 'OpenCV', cv2.__version__)"
```

## 4. Test data and tests

```bash
python scripts/fetch_test_data.py          # downloads fixtures listed in scripts/test_data_manifest.json and verifies SHA-256 (manifest is empty until fixtures are chosen)
python tests/tools/make_synthetic_xtf.py   # (planned, Sprint 1) generates the TD-01 synthetic survey

cd backend                                 # pyproject.toml (ruff, mypy, pytest config) lives here; CI runs the same commands
ruff check . ../scripts
ruff format --check . ../scripts
mypy
pytest --cov=sonarsentinel --cov-report=term-missing
```

## 5. Run the backend

```bash
# copy and edit environment settings
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env

sonarsentinel serve --host 127.0.0.1 --port 8000 --reload   # (planned, Sprint 3: ST-080) currently prints "not implemented"
# API docs (once the API exists): http://127.0.0.1:8000/docs
```

**`.env.example`**
```dotenv
SS_CONFIG=backend/configs/pipeline.yaml
SS_DATA_DIR=./data
SS_MODELS_DIR=./models
SS_RUNTIME=auto
SS_MAX_UPLOAD_GB=2
SS_WORKERS=1
SS_LOG_LEVEL=INFO
# SS_OFFLINE_TILES=./tiles/basemap.mbtiles
```

**CLI commands available now (Sprint 0 scaffold):**
```bash
sonarsentinel version                          # package version
sonarsentinel validate line_07.xtf nav.csv     # stage S0: type, size and header checks
sonarsentinel config                           # pipeline_version and config hash
```

**Planned (Sprint 3: ST-074/ST-075):**
```bash
sonarsentinel detect data/samples/line_07.xtf --out results/ --formats json,csv
```

## 6. Run the frontend *(planned)*

```bash
cd frontend
npm ci
npm run api:types      # generate TypeScript types from http://127.0.0.1:8000/openapi.json
npm run dev            # Vite dev server at http://localhost:5173 (proxies /api and /ws to :8000)
```

Frontend without the backend (mock API with sample events):
```bash
npm run mock           # mock server on :8000 from the OpenAPI spec + recorded WebSocket events
npm run dev
```

Frontend tests:
```bash
npm run lint && npm run typecheck && npm test
npx playwright install && npm run e2e
```

## 7. Full stack with Docker *(planned)*

```bash
docker compose -f docker/docker-compose.yml up -d --build
# Dashboard: http://localhost:8080   API: http://localhost:8000/api/v1/health
docker compose -f docker/docker-compose.yml logs -f backend
docker compose -f docker/docker-compose.yml down
```
CPU-only machines: remove the GPU `deploy.resources` block or use `docker-compose.cpu.yml`.

## 8. Data and models

```bash
dvc pull                       # fetch versioned datasets/models you have access to
ls models/detector/            # expected: yolo11s-seg-sonar/<version>/
```
Details: [Data Management Plan](../data/DATA_MANAGEMENT_PLAN.md) and [Datasets](../data/DATASETS.md).

## 9. Training on free cloud GPUs (Kaggle / Colab)

1. Upload the prepared `sonar-seg` dataset (zip) as a private Kaggle dataset or to Google Drive. Don't upload restricted data.
2. In the notebook:
   ```bash
   pip install ultralytics sahi
   git clone <repository-url> && cd sonarsentinel
   python ml/train_detector.py --data /kaggle/input/sonar-seg/sonar-seg.yaml --model yolo11s-seg.pt --epochs 200
   ```
3. Download `best.pt`, `results.csv` and plots; log the run with the [Experiment Log Template](../ml/EXPERIMENT_LOG_TEMPLATE.md).
4. Session time limits apply, so use `patience` and save checkpoints to persistent storage.

## 10. NVIDIA Jetson setup (edge)

1. Flash **JetPack 6.x** (includes CUDA, cuDNN, TensorRT).
2. Prefer NVIDIA's **L4T-based containers** (or NVIDIA's Jetson PyTorch wheels). Don't install desktop CUDA PyTorch wheels on Jetson.
3. Copy the ONNX model and build the engine **on the device**:
   ```bash
   python edge/export_models.py --model models/detector/yolo11s-seg-sonar/1.2.0/best.pt --target tensorrt --half
   python edge/export_models.py --model … --target tensorrt --int8 --calib-data data/processed/sonar-seg/images/calib
   ```
4. Run the benchmark: `python scripts/benchmark.py --runtime tensorrt --input data/samples/reference_1km.xtf`
5. Monitor with `tegrastats`; set the power mode with `nvpmodel` as required.

## 11. Useful commands

| Task | Command |
|---|---|
| Lint + format | `ruff check . --fix && ruff format .` |
| Type check | `mypy backend/sonarsentinel` |
| Unit tests (fast) | `pytest -q -m "not slow"` |
| All tests + coverage | `pytest --cov=sonarsentinel --cov-report=html` |
| Validate a report | `python -m sonarsentinel.report.validate results/report.json` |
| Evaluate a model | `python ml/evaluate.py --model models/detector/… --split test` |
| Generate synthetic nets | `python ml/synth/ghost_net_generator.py --n 2000 --out data/synthetic/ghost_net/1.0.0 --seed 42` |
| Benchmark | `python scripts/benchmark.py --runtime auto` |

## 12. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `python` opens Microsoft Store | No Python on PATH | Activate the conda env; disable App execution aliases |
| `ImportError: DLL load failed` for GDAL/rasterio | Mixed pip and conda GDAL | Recreate env; install GDAL/rasterio **only** from conda-forge |
| `torch.cuda.is_available()` is `False` | CPU wheel installed or driver/CUDA mismatch | Reinstall with the pytorch.org command for your CUDA; update driver |
| Two OpenCV packages conflict | `opencv-python` and `opencv-python-headless` both installed (Ultralytics may add one) | `pip uninstall opencv-python opencv-python-headless -y` then install one (headless for servers) |
| anomalib import errors | Version mismatch with torch/lightning | Use the pinned lock file versions |
| pyxtf can't read a file | XTF variant not supported | Try the alternative pyxtf implementation; open an issue with the file header dump |
| Port 8000/5173 already in use | Another process | Change `--port` or stop the process |
| Docker GPU not visible | NVIDIA Container Toolkit missing (Linux) or WSL GPU support not enabled | Install toolkit; update Docker Desktop and NVIDIA driver |
| Very slow file operations | Repo/data inside OneDrive | Move to a local non-synced folder |
| Out of memory in Docker Desktop | WSL memory limit too low | Increase memory in `.wslconfig`; restart WSL |
