# SonarSentinel — Operations Runbook

| | |
|---|---|
| **Version** | v1.0 (release-candidate draft) · 2026-09-14 |
| **Audience** | Operators and administrators of shore workstations and edge devices |
| **Owner** | Integration & Edge Lead (R6) |

**Related:** [Deployment](../architecture/07-deployment.md) · [Developer Setup](DEVELOPER_SETUP.md) · [User Manual](USER_MANUAL.md) · [Security Policy](../../SECURITY.md)

> Commands assume the Docker Compose deployment in `docker/` (see [docker/README.md](../../docker/README.md)). Paths, service names and variables were checked against the Sprint 6 implementation (ST-114). The images are built and scanned in CI; they have not been run on a GPU host or a Jetson yet.

---

## 1. Service overview

| Component | Container / process | Port | Health check | Data |
|---|---|---|---|---|
| Frontend (nginx) | `frontend` | 8080 | `GET http://localhost:8080/` | — |
| Backend API + worker | `backend` | 8000 | `GET http://localhost:8000/api/v1/health` | `/data` volume |
| Database | SQLite file `/data/sonarsentinel.db` | — | Opened at startup | `/data` (host `data/api/`) |
| Models | Read-only volume | — | `models_loaded` in health | `/models` (host `models/`) |
| Offline tiles (optional) | MBTiles served by the backend at `/api/v1/tiles/{z}/{x}/{y}.png` | — | `offline_tiles` in health | `/tiles/basemap.mbtiles` (host `tiles/`) |
| Edge runner (vessel) | `edge` (`sonarsentinel watch`, [docker-compose.edge.yml](../../docker/docker-compose.edge.yml)) | — | `docker compose -f docker/docker-compose.edge.yml ps`, `alerts.log` | `/data/results` (host `data/edge/results/`) |

**Data folder layout** (`SS_DATA_DIR`, `/data` in the container):

```text
sonarsentinel.db              survey, job and detection records
uploads/<survey_id>/          uploaded input files
results/<survey_id>/          report.*, chips/, mosaic.*, job.log.jsonl
work/<survey_id>/             temporary files; deleted after a job unless SS_KEEP_WORK_FILES=true
labels/                       review decisions (training labels; kept when a survey is deleted)
```

## 2. Deploy (first install)

1. Check hardware and OS prerequisites ([Deployment §2](../architecture/07-deployment.md#2-hardware-recommendations)).
2. Install Docker (and the NVIDIA Container Toolkit for GPU on Linux).
3. Copy the release bundle: `docker/`, `models/`, optional `tiles/basemap.mbtiles`.
4. Create the host folders mounted by Compose (the backend creates the subfolders itself):
   ```bash
   mkdir -p data/api models tiles
   ```
5. Adjust the `environment:` block of `docker/docker-compose.yml` if needed. The application does not read a `.env` file; `.env.example` lists the same variables for running outside Docker.

   | Variable | Default | Effect |
   |---|---|---|
   | `SS_CONFIG` | `backend/configs/pipeline.yaml` | Pipeline YAML |
   | `SS_DATA_DIR` | `<repo>/data/api` | Data folder (layout above) |
   | `SS_MODELS_DIR` | unset (paths as in `pipeline.yaml`) | Base folder for relative model paths (a leading `models/` is dropped) |
   | `SS_RUNTIME` | `auto` | `auto`, `torch`, `onnxruntime`, `cuda` or `tensorrt`; an unavailable GPU runtime falls back to CPU with a `CPU_FALLBACK` warning |
   | `SS_MAX_UPLOAD_GB` | `2` | Upload size limit per file |
   | `SS_OFFLINE_TILES` | unset | MBTiles basemap served to the dashboard |
   | `SS_KEEP_WORK_FILES` | `false` | Keep `work/` files for debugging |
   | `SS_JOB_TIMEOUT_S` | `3600` | A job running longer fails with `JOB_TIMEOUT`; 0 disables the limit |
   | `SS_WORKERS` | `1` | Only 1 is supported |
   | `SS_LOG_LEVEL` | `INFO` | Log level |

   Invalid values stop the backend at startup with a message naming the variable.
6. Start (add `-f docker/docker-compose.gpu.yml` on a Linux host with the NVIDIA Container Toolkit):
   ```bash
   docker compose -f docker/docker-compose.yml up -d --build
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

> Stopping the backend while a job runs cancels that job. Check for running jobs in the dashboard History first, or via `GET /api/v1/surveys?status=queued,running`.

## 4. Smoke test (after install, upgrade or restart)

- [ ] `curl http://localhost:8000/api/v1/health` → `status: ok`, `models_loaded: true`, expected `runtime` (`onnxruntime`/`torch` on CPU; `cuda`/`tensorrt` on GPU hosts)
- [ ] Dashboard loads at `http://localhost:8080`
- [ ] Upload the demo survey `demo/harbour_synthetic.png` with `demo/harbour_synthetic.csv` (lat/lon navigation; see [demo/README.md](../../demo/README.md))
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
3. Set the model path in **Settings** (applies to new jobs) or in `pipeline.yaml` (restart the backend).
4. Run the smoke test and compare results on the sample survey with the previous model.
5. **Rollback:** select the previous version and restart. Old versions are never deleted from `models/`.

> Reports record model versions, so earlier reports stay traceable after a model change.

## 6. Routine operations

| Frequency | Task |
|---|---|
| Daily (when in use) | Check health; check disk space (warn < 20% free); review failed jobs |
| Weekly | Back up database, results and label store; clean `data/work`; check logs for recurring warnings |
| Per survey campaign | Pre-download offline tiles for the area; verify sample survey; archive raw uploads afterwards |
| Monthly | Apply OS and Docker updates (after testing); run `pip-audit`, `npm audit` and an image scan (CI runs Trivy on every push); test a restore |

## 7. Monitoring

| Signal | Where | Threshold / action |
|---|---|---|
| Service health | `/api/v1/health` | Not `ok` → §10 playbook P2 |
| Disk space on data volume | `df -h` / Explorer | < 20% free → clean work files, archive uploads |
| Job failures | Dashboard History, job logs | > 2 failures/day of the same code → investigate |
| Processing speed | Job `stage_timings_ms` | 3× slower than baseline → check GPU/runtime (P6) |
| GPU temperature/memory | `nvidia-smi` / `tegrastats` | Sustained > 85 °C or OOM → reduce batch/model, improve cooling |
| Metrics | `/metrics` (Prometheus) is **not in this release** | Use health, job logs and `scripts/benchmark.py` |

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
tar -czf backup-$(date +%Y%m%d).tar.gz data/api/sonarsentinel.db data/api/results data/api/labels docker backend/configs
# 3) Start again
docker compose -f docker/docker-compose.yml start backend
```
- Raw uploads (`data/api/uploads`) are large: archive them to external storage per campaign instead of daily.
- Keep 3 copies on 2 media types, 1 off-site ([Data Management Plan §9](../data/DATA_MANAGEMENT_PLAN.md#9-backup-and-retention)).
- Production PostgreSQL (future): use `pg_dump` nightly.

### 8.2 Restore
1. `docker compose … down`
2. Extract the backup over `data/api/`, `docker/` and `backend/configs`.
3. `docker compose … up -d` and run the smoke test.

## 9. Storage cleanup

| Folder | Safe to delete? | How |
|---|---|---|
| `data/api/work/` | Yes (not while jobs run) | Delete contents |
| `data/api/results/<survey>/` | Only with the survey | *Delete* in History (or `DELETE /api/v1/surveys/{id}`) removes results, uploads and work files |
| `data/api/uploads/<survey>` | After archiving, if reports suffice | Archive, then delete the survey |
| `models/` old versions | **No** (reports reference them) | Move to archive storage if space is critical |
| `data/api/labels/` | **No** (training data; kept when surveys are deleted) | Back up only |

## 10. Troubleshooting playbooks

| # | Symptom | Checks | Fix |
|---|---|---|---|
| P1 | Dashboard doesn't load | `docker compose ps`; frontend logs; port 8080 in use? | Restart frontend; free the port; check firewall |
| P2 | Health not `ok` / "Backend not reachable" | Backend logs; `models_loaded`; disk full? | Fix missing model path in `.env`; free disk; restart backend |
| P3 | Job stuck in `queued` | Worker running? Another long job? | Wait or cancel the long job; restart the backend if the worker crashed (jobs left running are marked failed at startup). `SS_JOB_TIMEOUT_S` limits job length |
| P4 | Job failed `CORRUPT_HEADER` / `UNSUPPORTED_FORMAT` | File type, size, partial copy | Re-copy the file from source (checksum); export fresh XTF |
| P5 | Job needs `CRS_REQUIRED` | File uses projected coordinates | Re-run with the correct UTM zone |
| P6 | Processing very slow | Health `runtime` shows CPU; `CPU_FALLBACK` warning; `nvidia-smi` | Fix GPU visibility (driver, NVIDIA Container Toolkit); use TensorRT engine on Jetson |
| P7 | Out of memory / container killed; `CHUNK_SKIPPED` warnings | `docker stats`; file size; chunk size | Reduce the chunk size in Settings; increase Docker/WSL memory; close other apps |
| P8 | Map shows "Reconnecting…" repeatedly | Reverse proxy WebSocket config; network | Enable WebSocket upgrade headers in the proxy; check timeouts |
| P9 | Detections in wrong place (on land, mirrored side) | Report flags; survey CRS; `NavUnits`; heading; layback | Re-run with the correct UTM zone/layback setting; if still wrong, **stop using positions**, open an S1 bug with the file |
| P10 | Too many false alarms | Seabed type; tier filter; model version | Focus on HAZARD tier; send examples for review; consider a newer model |
| P11 | Offline map blank | `offline_tiles` in health; `SS_OFFLINE_TILES` path; basemap set to *Offline* in Settings; tile coverage/zoom | Mount an MBTiles file covering the area and zoom range (rendered by the team, not bulk-downloaded from OSM) |
| P12 | Disk full | `df -h` | §9 cleanup; archive uploads |
| P13 | GPU not detected in Docker | `docker run --gpus all nvidia/cuda:… nvidia-smi` | Install/repair NVIDIA Container Toolkit (Linux) or update Docker Desktop/WSL and drivers (Windows) |

When opening a bug, include: survey ID, job ID, `job.log.jsonl`, health output, version, and (if allowed) the input file or its header dump.

## 11. Edge device operations

> Sprint 6 provides watch mode (`sonarsentinel watch`, [edge/README.md](../../edge/README.md)): new files in the acquisition folder are processed once their size has been stable for `--stable-seconds`, state is kept in the results folder so restarts don't reprocess files, and detections above `--alerts-min-conf` are printed and appended to `alerts.log` as `SS1|…` lines (≤ 256 bytes). TensorRT builds, the edge console (S-08) and chunk-by-chunk processing of a line still being recorded are **not in this release**; no Jetson has been tested.

### 11.1 Before deployment
- [ ] TensorRT engine built **on this device** for the current model version (not yet possible, ST-101)
- [ ] Benchmark run: `python scripts/benchmark.py` on the reference file; real-time factor ≥ 1.5×
- [ ] Acquisition folder mounted read-only; results disk has ≥ 50% free space
- [ ] Clock synchronised (UTC) with the vessel's navigation system
- [ ] Thresholds and alert link settings verified; test alert sent
- [ ] Power and cooling verified during a 30-minute run

### 11.2 During the survey
- Check the edge container is running and `alerts.log` is growing as lines are completed.
- Note hazard alert detection IDs in the survey log.
- If processing falls behind acquisition: switch to the ONNX runtime or continue and process on shore.
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

- The Compose files bind ports to `127.0.0.1`; change this only when LAN access is needed, and put a reverse proxy with HTTPS in front when shared. The API has no authentication in this release.
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
