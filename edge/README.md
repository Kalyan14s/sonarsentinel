# edge

On-board processing for survey vessels and AUV support boats. Design: [07-deployment §4](../docs/architecture/07-deployment.md#4-edge-deployment-jetson) · [03-ml-models §11](../docs/architecture/03-ml-models.md#11-edge-optimisation).

| Capability | Status |
|---|---|
| ONNX export + ONNX Runtime CPU path (ST-100) | Done: `ml/export_onnx.py`, `detection.runtime: auto` ([EXP-20260914-onnx](../ml/experiments/EXP-20260914-onnx.md)) |
| `watch` mode (ST-103) | Done: `sonarsentinel watch`, `backend/sonarsentinel/edge/watch.py` |
| Container for the runner | `docker/docker-compose.edge.yml` (CPU image) |
| TensorRT FP16/INT8 on Jetson (ST-101) | Not done: needs a Jetson device |

## `sonarsentinel watch`

```bash
sonarsentinel watch /acquisition --out /data/results --no-mosaic --alerts-min-conf 80
sonarsentinel watch ./incoming --out ./results --once --stable-seconds 0   # process what is there and exit
```

- Polls the folder every `--interval` seconds (default 5); no file-system event library is needed.
- Processes `.xtf`, `.tif/.tiff`, and `.png/.jpg` images that have a `<stem>_nav.csv` next to them.
- A file is taken once its modification time is `--stable-seconds` old (default 10), i.e. the sonar software has closed it.
- Each file is processed once. The state is kept in `<out>/.watch_state.json` (path, size, mtime, survey ID, status, error), so a restart does not reprocess; a file that changes later is processed again; a failing file is recorded and skipped until it changes.
- Reports (`--formats`, default `json,csv`) and chips go to `<out>/<survey_id>/`.
- Every detection with confidence ≥ `--alerts-min-conf` prints one alert line of at most 256 bytes and appends it to `<out>/alerts.log`:

  ```text
  SS1|SRV-20260914-001|D0007|ghost_net|91|13.084123|80.312756|8.0x4.0|18.2|2026-09-14T05:17:21.50Z
  ```

- `--runtime auto|torch|cuda|onnxruntime|tensorrt` sets `detection.runtime`; when `cuda`/`tensorrt` is requested but no GPU is available the detector falls back to the CPU and reports `CPU_FALLBACK`. `--no-anomaly` and `--no-mosaic` save time on small devices.
- Ctrl+C stops cleanly.

**Not implemented:** tailing a file that is still being written, chunk by chunk (07 §4). Files are processed after they are closed, so alerts arrive per line, not per chunk.
