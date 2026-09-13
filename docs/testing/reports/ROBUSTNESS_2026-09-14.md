# Robustness suite — 2026-09-14 (ST-111)

Part of [TSR-M6](TSR-M6.md). Method: [Test Plan §6.4](../TEST_PLAN.md) (AC-06, TC-ROB-001…004, TC-ING-012); script [`scripts/robustness_suite.py`](../../../scripts/robustness_suite.py); automated in `backend/tests/test_robustness.py`.

## Set-up

- One synthetic XTF line (TD-01 generator, 1,400 pings) with 3 known targets, plus the TD-05/TD-07 fault variants now produced by `backend/tests/tools/make_synthetic_xtf.py` (zeroed pings, GPS gap, roll, missing altitude, speckle).
- Each variant runs through the CLI (`sonarsentinel detect`) and through `run_pipeline`; reports are validated against `report-1.0`.
- Detector: rule-based (`RULE_BASED_DETECTOR`), so the suite tests pipeline behaviour under faults, not detection quality of the trained model.
- Command: `python scripts/robustness_suite.py --out robustness.json`.

## Results

| Variant | Status | Schema valid | CLI exit | Report warnings | Ranged warning events | Detection flags | Targets kept |
|---|---|---|---|---|---|---|---|
| clean | completed_with_warnings¹ | yes | 0 | `RULE_BASED_DETECTOR` | 0 | — | 3/3 |
| 10% zeroed pings + truncated final record (AC-06) | completed_with_warnings | yes | 0 | `DROPOUT`, `TRUNCATED_FILE` | 15 | — | 3/3 |
| 30 s GPS gap | completed_with_warnings | yes | 0 | `GPS_INTERPOLATED` | 0 | `GPS_INTERPOLATED` ×1 | 3/3 |
| ±10° roll | completed_with_warnings | yes | 0 | `HIGH_MOTION` | 18 | `HIGH_MOTION` ×2 | 3/3 |
| No altitude | completed_with_warnings | yes | 0 | `NO_ALTITUDE_BOTTOM_TRACKED` | 0 | `NO_ALTITUDE_BOTTOM_TRACKED` ×3 | 3/3 |
| Heavy speckle | completed_with_warnings | yes | 0 | — | 0 | — | 3/3 |
| Truncated | completed_with_warnings | yes | 0 | `TRUNCATED_FILE` | 0 | — | 3/3 |
| Corrupt header | **failed** `CORRUPT_HEADER` | — | 1 | — | — | — | clean failure |

¹ `completed_with_warnings` in every variant because the rule-based detector itself adds a warning.

Also covered by unit tests: chunk retry — a chunk that raises twice is skipped with a `CHUNK_SKIPPED` warning event carrying its ping range, and the job still completes; `CPU_FALLBACK` when `cuda`/`tensorrt` is requested without a GPU.

**AC-06: pass** on synthetic faults (valid report, warnings with ranges, no crash, all targets kept).

## Defects found and fixed during the suite

| Defect | Cause | Fix |
|---|---|---|
| Targets vanished when a GPS gap crossed a chunk border | Each chunk held the last good fix through the gap, collapsing those pings into about one image row | Missing positions are interpolated over the whole line before chunking; detections on them get `GPS_INTERPOLATED` |
| Targets lost in chunks with zeroed pings | Zero rows skewed gain normalisation and saturated the chunk | Masked rows are excluded from gain statistics, then zeroed again |
| `DROPOUT` missing next to a gap | Flag only covered rows inside the mask | Flag and penalty also cover detections within `local_std_window` (7 rows) of a masked gap |

## Open

- Detection metrics under injected faults on the frozen test set (TC-DET-008) need the GPU-trained detector.
- Position uncertainty has no GPS-gap term: interpolated positions get the same `uncertainty_m` as clean ones.
- Real files with genuine dropouts/motion were only exercised through the component tests on the USGS lines.
