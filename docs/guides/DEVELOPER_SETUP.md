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

### 3.1 Create the conda environment *(planned file: `backend/environment.yml`)*

```yaml
name: sonarsentinel
channels: [conda-forge]
dependencies:
  - python=3.11
  - gdal
  - rasterio
  - pyproj
  - shapely
  - numpy
  - scipy
  - pandas
  - scikit-image
  - scikit-learn
  - lightgbm
  - pip
  - pip:
      - pyxtf
      - opencv-python-headless
      - ultralytics
      - sahi
      - anomalib
      - onnxruntime
      - fastapi
      - "uvicorn[standard]"
      - sqlalchemy
      - pydantic-settings
      - typer
      - python-multipart
      - pytest
      - pytest-cov
      - hypothesis
      - httpx
      - schemathesis
      - jsonschema
      - ruff
      - mypy
      - pre-commit
      - dvc
```

```bash
conda env create -f backend/environment.yml
conda activate sonarsentinel
```

### 3.2 Install PyTorch correctly (GPU or CPU)
Install PyTorch **before** relying on Ultralytics/anomalib, so a CPU-only build isn't pulled in by accident:

1. Open https://pytorch.org/get-started/locally/ and select your OS, `pip`, Python and CUDA version (or CPU).
2. Run the command it shows inside the activated environment.
3. Verify:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

> Pin exact versions of `torch`, `ultralytics`, `anomalib` and `lightning` in `backend/requirements-lock.txt` once a working combination is found. anomalib is sensitive to torch/lightning versions.

### 3.3 Install the package and hooks *(planned)*

```bash
pip install -e "backend[dev]"
pre-commit install
sonarsentinel --help
```

### 3.4 Verify geospatial and sonar libraries

```bash
python -c "import rasterio, pyproj, osgeo.gdal as g, cv2, pyxtf, ultralytics; print('GDAL', g.__version__, 'OpenCV', cv2.__version__)"
```

## 4. Test data and tests

```bash
python scripts/fetch_test_data.py          # (planned) downloads small public fixtures with checksums
python tests/tools/make_synthetic_xtf.py   # (planned) generates TD-01 synthetic survey

ruff check . && ruff format --check .
mypy backend/sonarsentinel
pytest -q --cov=sonarsentinel
```

## 5. Run the backend

```bash
# copy and edit environment settings
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env

sonarsentinel serve --host 127.0.0.1 --port 8000 --reload
# API docs: http://127.0.0.1:8000/docs
```

**`.env.example`** *(planned)*
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

**CLI example:**
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
