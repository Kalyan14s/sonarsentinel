# sonar-seg 0.1.0 — dataset statistics

Generated 2026-09-13T14:28:27Z by `ml/datasets/make_splits.py`.

## Images and objects per split

| Split | Sites | Images | shipwreck | pipe | cylinder | ghost_net | debris_other |
|---|---|---|---|---|---|---|---|
| calib | 1 | 48 | 0 | 0 | 49 | 0 | 0 |
| synthetic_holdout | 1 | 200 | 0 | 0 | 0 | 329 | 0 |
| test | 1 | 120 | 0 | 0 | 242 | 0 | 0 |
| train | 3 | 2909 | 0 | 0 | 118 | 3433 | 0 |
| val | 1 | 93 | 0 | 0 | 28 | 0 | 0 |

## Per site

| Site | Split | Images | Objects |
|---|---|---|---|
| mine_sss:2010 | train | 345 | 22 |
| mine_sss:2015 | test | 120 | 242 |
| mine_sss:2017 | val | 93 | 28 |
| mine_sss:2018 | train | 564 | 96 |
| mine_sss:2021 | calib | 48 | 49 |
| synthetic_ghost_net:synthetic_holdout | synthetic_holdout | 200 | 329 |
| synthetic_ghost_net:train | train | 2000 | 3433 |

## Object sizes (fraction of image side, polygon bounding box)

| Class | n | median width | median height | p90 longest side |
|---|---|---|---|---|
| cylinder | 437 | 0.045 | 0.025 | 0.081 |
| ghost_net | 3762 | 0.055 | 0.056 | 0.209 |

## Leakage check

Passed: no site in more than one split; no cross-split image pairs at or above thumbnail correlation 0.97.

Test split hash (frozen): `sha256:accc8ae4521ce1784d7f6e6cb0a015537b7c196a49281c6d4c575cd4e71bf61d`
