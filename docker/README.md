# docker

Container images and Compose files for the shore workstation and the edge runner (ST-005, ST-103). Design: [07-deployment §3–4](../docs/architecture/07-deployment.md#3-docker-compose-shore-workstation).

| File | Purpose |
|---|---|
| `Dockerfile.backend` | API, job worker, CLI and `watch` (Python 3.11 slim, CPU PyTorch by default, non-root `sonar` user, healthcheck) |
| `Dockerfile.frontend` | Dashboard built with Node 22, served by nginx |
| `nginx.conf` | Serves the dashboard; proxies `/api` and `/ws` (WebSocket upgrade) to `backend:8000`; 2 GB uploads |
| `docker-compose.yml` | Shore workstation: backend + frontend |
| `docker-compose.gpu.yml` | NVIDIA override (CUDA PyTorch wheels, GPU reservation) |
| `docker-compose.edge.yml` | Edge runner: `sonarsentinel watch /acquisition` |
| `../backend/requirements-docker.txt` | Pinned Python stack for the backend image |

## Shore workstation

```bash
# from the repository root
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps        # backend should become "healthy"
```

- Dashboard: http://localhost:8080 · API and OpenAPI docs: http://localhost:8000/docs
- Ports are bound to `127.0.0.1` so the services are not reachable from the LAN by default (TC-SEC-005). Change to `"8080:80"` deliberately if other machines must connect.
- GPU: `docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d --build` (NVIDIA Container Toolkit; set `TORCH_INDEX` to the CUDA wheel index that matches your driver).

## Volumes

| Host | Container | Contents |
|---|---|---|
| `data/api/` | `/data` | Uploads, results, labels, `sonarsentinel.db` |
| `models/` | `/models` (read-only) | Model registry as in the repository (`models/detector/...`, `models/anomaly/...`) |
| `tiles/` | `/tiles` (read-only) | Offline basemap `basemap.mbtiles` (ST-099) |

The image runs as UID 1000. On Linux hosts give that UID write access to `data/api/` (`sudo chown -R 1000 data/api`).

## Environment

`SS_CONFIG`, `SS_DATA_DIR`, `SS_MODELS_DIR`, `SS_RUNTIME`, `SS_MAX_UPLOAD_GB`, `SS_WORKERS`, `SS_OFFLINE_TILES`, `SS_KEEP_WORK_FILES`, `SS_LOG_LEVEL` follow [07-deployment §6](../docs/architecture/07-deployment.md#6-configuration-and-environment). `SONARSENTINEL_DATA_DIR` is also set, because the API reads it for the data folder.

## Edge runner

```bash
ACQUISITION_DIR=/mnt/sonar docker compose -f docker/docker-compose.edge.yml up -d --build
tail -f data/edge/results/alerts.log
```

Files in `/acquisition` (read-only) are processed once when they have not changed for 10 s; see [edge/README.md](../edge/README.md).

## Verification

Docker is not installed on the development laptop, so the images are built, smoke-tested (`/api/v1/health`) and scanned with Trivy in CI (`.github/workflows/ci.yml`, job *Docker images*). The fresh-install check TC-E2E-004 (clean machine → first report in ≤ 15 min, excluding downloads) is manual.
