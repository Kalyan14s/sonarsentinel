# SonarSentinel — Operations Runbook

| | |
|---|---|
| **Version** | v1.0 (pre-release) · 2026-09-13 |
| **Audience** | Operators and administrators of shore workstations and edge devices |
| **Owner** | Integration & Edge Lead (R6) |

**Related:** [Deployment](../architecture/07-deployment.md) · [Developer Setup](DEVELOPER_SETUP.md) · [User Manual](USER_MANUAL.md) · [Security Policy](../../SECURITY.md)

> Commands assume the Docker Compose deployment in `docker/`. Paths and service names must be verified against the implementation (backlog ST-114).

---

## 1. Service overview

| Component | Container / process | Port | Health check | Data |
|---|---|---|---|---|
| Frontend (nginx) | `frontend` | 8080 | `GET http://localhost:8080/` | — |
| Backend API + worker | `backend` | 8000 | `GET http://localhost:8000/api/v1/health` | `/data` volume |
| Database | SQLite file inside `/data/db/sonarsentinel.db` | — | Included in health | `/data/db` |
| Models | Read-only volume | — | `models_loaded` in health | `/models` |
| Offline tiles (optional) | MBTiles served by backend | — | `offline_tiles` in health | `/tiles` |
| Edge runner (vessel) | `edge` | — (8000 if console enabled) | `docker compose ps`, `tegrastats` | `/data/results` |

## 2. Deploy (first install)

1. Check hardware and OS prerequisites ([Deployment §2](../architecture/07-deployment.md#2-hardware-recommendations)).
2. Install Docker (and the NVIDIA Container Toolkit for GPU on Linux).
3. Copy the release bundle: `docker/`, `.env`, `models/`, optional `tiles/`.
4. Create data folders:
   ```bash
   mkdir -p data/db data/uploads data/results data/work labels
   ```
5. Set `.env` values (`SS_MAX_UPLOAD_GB`, `SS_RUNTIME`, `SS_OFFLINE_TILES`, …).
6. Start:
   ```bash
   docker compose -f docker/docker-compose.yml up -d
   ```
7. Run the **smoke test** (§4).

## 3. Start, stop, restart, status

| Action | Command |
|---|---|
| Start | `docker compose -f docker/docker-compose.yml up -d` |
| Stop | `docker compose -f docker/docker-compose.yml stop` |
| Restart backend | `docker compose -f docker/docker-compose.yml restart backend` |
| Status | `docker compose -f docker/docker-compose.yml ps` |
| Logs (follow) | `docker compose -f docker/docker-compose.yml logs -f backend` |
| Remove containers (keeps data) | `docker compose -f docker/docker-compose.yml down` |

> Stopping the backend while a job runs cancels that job. Check for running jobs in the dashboard first, or via `GET /api/v1/surveys?status=running` (P1).

## 4. Smoke test (after install, upgrade or restart)

- [ ] `curl http://localhost:8000/api/v1/health` → `status: ok`, `models_loaded: true`, expected `runtime` (e.g. `tensorrt`/`cuda`/`onnxruntime`)
- [ ] Dashboard loads at `http://localhost:8080`
- [ ] Upload the bundled sample survey (*Try a sample survey* on the Upload screen)
- [ ] Detections appear on the map; the job completes
- [ ] CSV download opens correctly
- [ ] If offline: basemap tiles load with network disconnected

## 5. Upgrade and rollback

### 5.1 Application upgrade
1. Announce downtime; make sure no jobs are running.
2. **Back up** (§8).
3. Pull or load new images: `docker compose -f docker/docker-compose.yml pull` (or `docker load -i sonarsentinel-<version>.tar` offline).
4. Update `.env` and config per the release notes in [CHANGELOG.md](../../CHANGELOG.md).
5. `docker compose -f docker/docker-compose.yml up -d`. Database migrations run on startup.
6. Run the smoke test.

### 5.2 Rollback
1. `docker compose … down`
2. Restore the database backup taken in step 2 (migrations may not be reversible).
3. Set image tags in compose/`.env` to the previous version; `up -d`.
4. Smoke test; record the incident (§11).

### 5.3 Model update / rollback
1. Copy the new model folder into `models/<kind>/<name>/<version>/` (with `model_card.md` and `metrics.json`).
2. Check the model card: metrics ≥ current model and intended use matches.
3. Set the model version in **Settings** (admin) or `pipeline.yaml`, then restart the backend.
4. Run the smoke test and compare results on the sample survey with the previous model.
5. **Rollback:** select the previous version and restart. Old versions are never deleted from `models/`.

> Reports record model versions, so earlier reports stay traceable after a model change.

## 6. Routine operations

| Frequency | Task |
|---|---|
| Daily (when in use) | Check health; check disk space (warn < 20% free); review failed jobs |
| Weekly | Back up database, results and label store; clean `data/work`; check logs for recurring warnings |
| Per survey campaign | Pre-download offline tiles for the area; verify sample survey; archive raw uploads afterwards |
| Monthly | Apply OS and Docker updates (after testing); run dependency/image vulnerability scan; test a restore |

## 7. Monitoring

| Signal | Where | Threshold / action |
|---|---|---|
| Service health | `/api/v1/health` | Not `ok` → §10 playbook P2 |
| Disk space on data volume | `df -h` / Explorer | < 20% free → clean work files, archive uploads |
| Job failures | Dashboard History, job logs | > 2 failures/day of the same code → investigate |
| Processing speed | Job `stage_timings_ms` | 3× slower than baseline → check GPU/runtime (P6) |
| GPU temperature/memory | `nvidia-smi` / `tegrastats` | Sustained > 85 °C or OOM → reduce batch/model, improve cooling |
| Metrics (P1) | `/metrics` (Prometheus) | Dashboards/alerts if Prometheus is deployed |

**Log locations**
- Container logs: `docker compose logs backend`
- Per-job logs: `data/results/<survey_id>/job.log.jsonl`
- nginx logs: `docker compose logs frontend`

## 8. Backup and restore

### 8.1 Back up
```bash
# 1) Stop the backend briefly for a consistent SQLite copy
docker compose -f docker/docker-compose.yml stop backend
# 2) Copy database, results, label store, config
tar -czf backup-$(date +%Y%m%d).tar.gz data/db data/results labels .env backend/configs
# 3) Start again
docker compose -f docker/docker-compose.yml start backend
```
- Raw uploads (`data/uploads`) are large: archive them to external storage per campaign instead of daily.
- Keep 3 copies on 2 media types, 1 off-site ([Data Management Plan §9](../data/DATA_MANAGEMENT_PLAN.md#9-backup-and-retention)).
- Production PostgreSQL (future): use `pg_dump` nightly.

### 8.2 Restore
1. `docker compose … down`
2. Extract the backup over `data/db`, `data/results`, `labels`, `.env`, `backend/configs`.
3. `docker compose … up -d` and run the smoke test.

## 9. Storage cleanup

| Folder | Safe to delete? | How |
|---|---|---|
| `data/work/` | Yes (not while jobs run) | Delete contents |
| `data/results/<survey>/chips` | Only with the survey | Use *Delete survey* in History |
| `data/uploads/<survey>` | After archiving, if reports suffice | Archive, then delete survey or folder |
| `models/` old versions | **No** (reports reference them) | Move to archive storage if space is critical |
| `labels/` | **No** (training data) | Back up only |

## 10. Troubleshooting playbooks

| # | Symptom | Checks | Fix |
|---|---|---|---|
| P1 | Dashboard doesn't load | `docker compose ps`; frontend logs; port 8080 in use? | Restart frontend; free the port; check firewall |
| P2 | Health not `ok` / "Backend not reachable" | Backend logs; `models_loaded`; disk full? | Fix missing model path in `.env`; free disk; restart backend |
| P3 | Job stuck in `queued` | Worker running? Another long job? `SS_WORKERS` | Wait or cancel the long job; restart backend if the worker crashed |
| P4 | Job failed `CORRUPT_HEADER` / `UNSUPPORTED_FORMAT` | File type, size, partial copy | Re-copy the file from source (checksum); export fresh XTF |
| P5 | Job needs `CRS_REQUIRED` | File uses projected coordinates | Re-run with the correct UTM zone |
| P6 | Processing very slow | Health `runtime` shows CPU; `CPU_FALLBACK` warning; `nvidia-smi` | Fix GPU visibility (driver, NVIDIA Container Toolkit); use TensorRT engine on Jetson |
| P7 | Out of memory / container killed | `docker stats`; file size; chunk size | Reduce `pings_per_chunk`; increase Docker/WSL memory; close other apps |
| P8 | Map shows "Reconnecting…" repeatedly | Reverse proxy WebSocket config; network | Enable WebSocket upgrade headers in the proxy; check timeouts |
| P9 | Detections in wrong place (on land, mirrored side) | Report flags; survey CRS; `NavUnits`; heading; layback | Re-run with the correct UTM zone/layback setting; if still wrong, **stop using positions**, open an S1 bug with the file |
| P10 | Too many false alarms | Seabed type; tier filter; model version | Focus on HAZARD tier; send examples for review; consider a newer model |
| P11 | Offline map blank | `offline_tiles` in health; tile coverage/zoom | Load tiles covering the area and zoom range |
| P12 | Disk full | `df -h` | §9 cleanup; archive uploads |
| P13 | GPU not detected in Docker | `docker run --gpus all nvidia/cuda:… nvidia-smi` | Install/repair NVIDIA Container Toolkit (Linux) or update Docker Desktop/WSL and drivers (Windows) |

When opening a bug, include: survey ID, job ID, `job.log.jsonl`, health output, version, and (if allowed) the input file or its header dump.

## 11. Edge device operations

### 11.1 Before deployment
- [ ] TensorRT engine built **on this device** for the current model version
- [ ] Benchmark run: real-time factor ≥ 1.5× on the reference file
- [ ] Acquisition folder mounted read-only; results disk has ≥ 50% free space
- [ ] Clock synchronised (UTC) with the vessel's navigation system
- [ ] Thresholds and alert link settings verified; test alert sent
- [ ] Power and cooling verified during a 30-minute run

### 11.2 During the survey
- Glance at the edge console: status **RUNNING**, throughput green, lag stable.
- Acknowledge hazard alerts; note waypoint IDs in the survey log.
- If throughput turns red: switch to the faster model/FP16 if configured, or continue and process on shore.
- If the device overheats: improve ventilation, lower the power mode, or pause processing (acquisition must not be affected).

### 11.3 After the survey
1. Stop the edge runner; copy `results/` and raw logs to shore storage (checksums).
2. Import into the shore system (upload the raw file; attach the edge report for comparison).
3. Run full processing (anomaly model, mosaic) on shore; review detections.
4. Record any edge issues in the incident log.

## 12. Incident response

| Severity | Examples | Response time | Actions |
|---|---|---|---|
| **SEV-1** | Wrong coordinates delivered to a field team; data loss; security breach | Immediately | Stop using affected outputs; notify stakeholders; preserve logs; fix or roll back |
| **SEV-2** | Service down during a campaign; all jobs failing | Within hours | Restore service (restart, rollback); workaround (CLI) |
| **SEV-3** | Single-file failures; degraded performance | Next working day | Investigate; workaround |

**Steps:** detect → contain (stop use, roll back) → communicate → fix → verify (smoke test) → post-incident review.

**Post-incident review template**
```text
Incident ID / date:
Severity:
What happened (timeline, UTC):
Impact (surveys, outputs, people affected):
Root cause:
What went well / what didn't:
Actions (owner, due date):
```

## 13. Security operations

- Keep the service bound to localhost unless LAN access is needed; put a reverse proxy with HTTPS in front when shared.
- Restrict access to restricted datasets and results ([Data Management Plan §8](../data/DATA_MANAGEMENT_PLAN.md#8-access-control)).
- Store credentials (DVC remotes, future auth secrets) in a password manager or environment files with restricted permissions. Never commit them to git.
- Apply security updates monthly after a test on a non-critical machine.
- Report vulnerabilities as described in [SECURITY.md](../../SECURITY.md).

## 14. Escalation contacts

| Area | Role |
|---|---|
| Service, deployment, edge | Integration & Edge Lead (R6) |
| API, jobs, database | Backend Engineer (R4) |
| Wrong positions / geo issues | Geospatial Engineer (R3) |
| Model quality / false alarms | ML Lead (R1) |
| Sonar file problems | Sonar & Signal Engineer (R2) |
| Dashboard issues | Frontend Engineer (R5) |

*(Fill in names and contact details in the team's private contact sheet, not in this repository.)*
