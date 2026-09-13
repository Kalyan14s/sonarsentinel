# Dataset Licence Register

Operational register of every dataset used for training, evaluation or demos. Required by the [Data Management Plan](../../docs/data/DATA_MANAGEMENT_PLAN.md) and the [Datasets checklist](../../docs/data/DATASETS.md#8-data-quality-checklist-per-dataset). The analysis behind each entry is in [Licences & Compliance §3](../../docs/legal/LICENSES_AND_COMPLIANCE.md#3-datasets-and-data-sources).

**Rule:** a dataset may enter a manifest only if its status here is ✅ or ⚠ (within the stated limits). A model inherits the most restrictive terms of its training sources.

**Status:** ✅ usable · ⚠ usable with restrictions · ❓ unconfirmed (research use only, no redistribution) · ❌ excluded

| ID | Dataset | Licence / terms | Status | Checked (date, by) | Evidence | Allowed use | Required attribution |
|---|---|---|---|---|---|---|---|
| D1 | AI4Shipwrecks (Deep Blue Data, DOI 10.7302/dmf4-x492) | CC BY 4.0 | ✅ | 2026-09-13, Deep Blue record JSON (`rights_license`) | https://deepblue.lib.umich.edu/data/concern/data_sets/8623hz41x.json → `http://creativecommons.org/licenses/by/4.0/` | Train, evaluate, demo, redistribute with attribution | Sethuraman et al., IJRR 44(3), 2025, doi:10.1177/02783649241266853; dataset DOI 10.7302/dmf4-x492 |
| D2 | Side-scan sonar imaging for mine detection (Figshare 24574879 v2) | CC BY 4.0 | ✅ | 2026-09-13, Figshare API | https://api.figshare.com/v2/articles/24574879 | Train, evaluate, demo, redistribute with attribution | Pessanha Santos et al., Data in Brief 53, 2024, doi:10.1016/j.dib.2024.110132 |
| D3 | SeabedObjects-KLSG (huoguanying) | README: academic use; no LICENSE file | ⚠ | 2026-09-13, repository README | github.com/huoguanying/SeabedObjects-Ship-and-Airplane-dataset | Academic research only; no redistribution; not in commercial models; **victim images excluded** | Huo, Wu & Li, IEEE Access 8, 2020, doi:10.1109/ACCESS.2020.2978880 |
| D3b | SeabedObjects-KLSG-II (HHUCzCz) | None | ❌ | 2026-09-13 | Repository contains no licence or terms | Excluded | — |
| D4 | S3Simulator | None published | ❌ | 2026-09-13 | No LICENSE in NambiarAthira/S3Simulator | Excluded unless written permission (see §Permissions) | Kamal Basha & Nambiar, ICPR 2024 |
| D5 | SonarSentinel synthetic data | Project (AGPL-3.0); backgrounds inherit source terms | ✅ | 2026-09-13 | — | Per background source | — |
| D6/D7 | NOAA NCEI / OCS hydrographic surveys, InPort | Free, no restrictions; "Not to be used for navigation"; no warranty | ✅ | 2026-09-13, NCEI pages + survey metadata | ncei.noaa.gov/products/seafloor-mapping | Train, infer, demo; show not-for-navigation notice; check external-source records | Credit NOAA NCEI / OCS; survey ID |
| D8 | USGS ScienceBase releases | Mostly public domain; proprietary parts per metadata | ✅ | 2026-09-13, ScienceBase record text | sciencebase.gov | Per release after metadata check | Release DOI; credit USGS |
| D9 | NOAA charted wrecks (ENC / wrecks & obstructions) | NOAA public data | ✅ | 2026-09-13 | — | Ground truth for geolocation validation | Credit NOAA |
| D10 | GhostNetZero / WWF / NIOT samples | Per written agreement | — | — | Agreement file (restricted storage) | Per agreement | Per agreement |

## Per-survey entries (NOAA / USGS)

Add one row per downloaded survey or release (details in its `PROVENANCE.yaml`).

| Survey / release ID | Source | Terms checked | External-source or proprietary parts? | Added by | Date |
|---|---|---|---|---|---|
| | | | | | |

## Permissions log

| Dataset | Requested from | Date requested | Response | Terms granted | Evidence location |
|---|---|---|---|---|---|
| D4 S3Simulator | Authors ([draft](../../docs/communications/OUTREACH_DRAFTS.md#4-s3simulator-authors--dataset-permission-optional)) | | | | |
| D1 AI4Shipwrecks | Deep Blue record check | 2026-09-13 | Record states CC BY 4.0 | CC BY 4.0 (no permission needed) | Deep Blue record JSON `rights_license` |
| D10 ghost-net samples | GhostNetZero / WWF ([draft](../../docs/communications/OUTREACH_DRAFTS.md#3-wwf-germany--ghostnetzero--ghost-net-sample-access-prd-q6)) | | | | |
