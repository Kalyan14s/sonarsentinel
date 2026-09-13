# Performance benchmark — 2026-09-14 (ST-112)

Part of [TSR-M6](TSR-M6.md). Method: [Test Plan §6.5](../TEST_PLAN.md); script [`scripts/benchmark.py`](../../../scripts/benchmark.py) (each run in its own subprocess; memory sampled every 100 ms; timings from `progress` and `detection` events).

## Environment

| Item | Value |
|---|---|
| Machine | Development laptop, Intel i5-13420H (8 cores / 12 threads), 16 GB RAM, Windows 11, **no GPU** |
| Load | Other development work running (not an idle machine) |
| Runtime | ONNX Runtime 1.30 on CPU, `detector/yolo11s-seg-sonar-real@0.1.0` (`best.onnx`), SAHI on, PatchCore, FP filter, isotonic calibrator (default `pipeline.yaml`) |
| Commands | `python scripts/benchmark.py --synthetic-km 1.0 --runs 3 --out bench_synth.json` · `python scripts/benchmark.py --input 15CCT03_SSS_150528201100.xtf --runs 1 --detector auto --out bench_usgs.json` |

## Results

| Metric | Synthetic 1 km line (3 runs) | USGS Grand Bay line, Klein 3900, 0.444 km (1 run) | Target | Status |
|---|---|---|---|---|
| Wall time (median, min–max) | 53.9 s (52.3–61.5) | 106.8 s | — | — |
| Seconds per km (NFR-02, CPU) | 53.9 | **240.5** | ≤ 300 | Pass (real line extrapolated from 0.444 km) |
| First detection event (NFR-04) | 53.8 s | 106.8 s | ≤ 15 s | **Fail** |
| Largest gap between progress events (NFR-05) | 12.0 s | 60.7 s | ≤ 5 s | **Fail** |
| Peak resident memory (NFR-07) | 985 MB | 1,027 MB | ≤ 8 GB | Pass |
| Detections | 47 | 414 (all `hidden`) | — | — |

Stage times (median run): synthetic parse 9.7 s, detect 42.9 s, merge 0.07 s; USGS parse (read + preprocess) 60.7 s, detect 44.0 s, merge 1.1 s.

| Model file (NFR-06) | Size | Target |
|---|---|---|
| Detector `best.pt` (FP32) | 19.6 MB | ≤ 25 MB — pass |
| Detector `best.onnx` | 38.7 MB | — |
| PatchCore memory bank | 4.4 MB | — |
| FP filter (LightGBM) | 0.43 MB | — |
| Calibrator (JSON) | < 0.01 MB | — |

## Findings

1. **NFR-04 and NFR-05 fail by design of the current orchestrator:** `detection` events are sent only after all chunks are merged, and `progress` is sent once per chunk. On the real line the first chunk took 60 s without an update. Fix: emit detections per chunk (with later `detection_update`/`detection_removed` on merge) and report progress inside the preprocessing and detection loops.
2. The earlier Sprint 5 measurement (0.444 km in 97.5 s ≈ 220 s/km, TSR-M5) and this one (240.5 s/km) differ by about 10%, within the variation expected on a busy laptop.
3. The ONNX model was loaded several times during one run (seen in the demo log); caching the session should shorten runs.

## Not measured

- **NFR-01 GPU** (≤ 60 s per km): no GPU available.
- **NFR-03 edge real-time factor** and INT8 impact: no Jetson (ST-101).
- Map frame rate with 2,000 clustered markers: needs a real browser session.
- The formal 1 km real reference line on an idle machine: substituted by the synthetic 1 km line (ADR-019 §8) and the 0.444 km real line.
