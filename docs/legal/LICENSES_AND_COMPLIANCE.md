# SonarSentinel — Licences & Compliance

| | |
|---|---|
| **Version** | v1.1 · 2026-09-13 |
| **Owner** | PM (R6) with ML Lead (R1); review with mentor / institution before any public or commercial release |
| **Status** | Living document |
| **Licence check** | 2026-09-13: items previously marked *verify* checked against primary sources (LICENSE files, PyPI/npm metadata, dataset records). AI4Shipwrecks confirmed as CC BY 4.0 from its Deep Blue record, so no dataset licence item remains open. |

> **Not legal advice.** Licences change between versions. Before each release, **check the licence in the exact version you ship** (package metadata / repository `LICENSE` file) and update this document.
>
> **Status column:** ✅ confirmed from a primary source on 2026-09-13 · ◻ standard licence of a widely used package (not re-checked; confirm at release) · ⚠ use with restrictions · ❌ don't use · ❓ not confirmed

**Related:** [Datasets](../data/DATASETS.md) · [Data Management Plan](../data/DATA_MANAGEMENT_PLAN.md) · [Architecture Decisions](../architecture/08-architecture-decisions.md)

---

## 1. Summary of key obligations

| # | Topic | What it means for us | Action |
|---|---|---|---|
| 1 | **Project licence is AGPL-3.0** ([ADR-013](../architecture/08-architecture-decisions.md#adr-013--project-licence-agpl-30)), matching Ultralytics YOLO (AGPL-3.0 / Enterprise) | Anyone who distributes SonarSentinel, or lets others use a modified version over a network, must offer the corresponding source under AGPL-3.0. We can't add dependencies whose terms place **further restrictions** on users (AGPL §10) | Keep `LICENSE`; ship source with releases; screen new dependencies against this rule |
| 2 | **react-leaflet is Hippocratic License 2.1** (v3.0.0 and later, including current 5.x) | Not OSI-approved; adds human-rights use conditions that are incompatible with AGPL-3.0's "no further restrictions" rule | ❌ **Don't use react-leaflet.** Use Leaflet (BSD-2-Clause) directly via a thin in-house React wrapper ([ADR-009](../architecture/08-architecture-decisions.md#adr-009--react--leaflet-for-the-dashboard)) |
| 3 | **SAM 3 uses the "SAM License"** (prohibits military/warfare, ITAR-controlled uses, reverse engineering; gated weights; Meta can terminate) | Our training data includes mine-detection imagery, so SAM 3's use restrictions are a real risk | ❌ Don't use SAM 3. ✅ Use **SAM 2** (Apache-2.0) or SAM 1 (Apache-2.0) for annotation assistance |
| 4 | **Datasets without a licence** (S3Simulator; SeabedObjects-KLSG-II) | No licence means all rights are reserved | ❌ Excluded unless the authors grant written permission |
| 5 | **Academic-use-only dataset** (SeabedObjects-KLSG, huoguanying repository) | Models trained on it aren't suitable for commercial use | Track training sources in model cards; retrain without it for any commercial use |
| 6 | **NOAA survey data: "Not to be used for navigation"** disclaimer in survey metadata | Outputs derived from NOAA data must not be presented as navigation-grade | Show a "Not for navigation" notice in reports/dashboard when NOAA-derived data is used; keep NOAA attribution |
| 7 | **OpenStreetMap** | OSM data is ODbL 1.0 (attribution required). The public tile servers **forbid bulk downloading and offline use** | Show "© OpenStreetMap contributors"; build offline tiles from OSM data ourselves or use a provider that allows offline use; never pre-seed from tile.openstreetmap.org |
| 8 | **NVIDIA TensorRT / JetPack** | Proprietary NVIDIA licence terms | Don't redistribute NVIDIA binaries outside NVIDIA's terms; build engines on target devices |
| 9 | **Restricted / partner data** | Use only under written terms; no redistribution | See [DMP §7–8](../data/DATA_MANAGEMENT_PLAN.md#7-sensitive-data-and-ethics) |
| 10 | **Attribution notices** | Permissive licences require keeping copyright/licence notices; Apache-2.0 requires carrying NOTICE files; CC BY 4.0 data requires attribution | Generate `THIRD_PARTY_NOTICES.txt` in release builds (e.g. `pip-licenses`, `license-checker`); cite datasets |

## 2. Third-party software

### 2.1 Backend, ML and geospatial (Python)

| Component | Use | Licence | Status | Notes |
|---|---|---|---|---|
| Python | Runtime | PSF License | ◻ | |
| PyTorch / torchvision | Deep learning | BSD-3-Clause | ◻ | Pretrained weights may carry terms from their training data (see anomalib row) |
| **Ultralytics** | YOLO11-seg training/inference/export | **AGPL-3.0** / paid Enterprise | ✅ | Matches project licence (ADR-013) |
| SAHI | Sliced inference | MIT | ◻ | |
| anomalib | PatchCore / EfficientAD | Apache-2.0 | ✅ | Repo moved to `open-edge-platform/anomalib`. **Backbone weights:** timm `wide_resnet50_2.tv_in1k` card states BSD-3-Clause, but ImageNet's own terms limit use to non-commercial research/education; whether trained weights inherit that is legally unsettled, so review before commercial use |
| Lightning | anomalib dependency | Apache-2.0 | ◻ | |
| LightGBM | FP filter | MIT | ◻ | |
| scikit-learn | Calibration, clustering | BSD-3-Clause | ◻ | |
| NumPy / SciPy / pandas / scikit-image | Numerics, images | BSD-3-Clause | ◻ | |
| OpenCV (4.5.0+) | Image processing | Apache-2.0 | ✅ | 4.4.0 and earlier were BSD-3-Clause |
| GDAL / PROJ | Raster I/O, projections | MIT-style | ◻ | Some optional GDAL drivers have other licences; use conda-forge builds |
| rasterio | GeoTIFF I/O | BSD-3-Clause | ◻ | |
| pyproj | Coordinate transforms | MIT | ◻ | |
| Shapely | Geometry | BSD-3-Clause | ◻ | |
| **pyxtf** | XTF reading | MIT | ✅ | **We use the PyPI `pyxtf` package = `oysstu/pyxtf`** (v1.5.0, 2026-04-14). The separate `pktrigg/pyxtf` is also MIT |
| sllib (P1) | Lowrance logs | MIT | ✅ | `opensounder/python-sllib`; last release 0.2.3 (2021), so it looks unmaintained; pin and vendor-test |
| PINGMapper (P2) | Humminbird logs | MIT | ✅ | |
| FastAPI / Starlette | API | MIT / BSD-3-Clause | ◻ | |
| Uvicorn | ASGI server | BSD-3-Clause | ◻ | |
| SQLAlchemy | ORM | MIT | ◻ | |
| Pydantic / pydantic-settings | Config & validation | MIT | ◻ | |
| Typer | CLI | MIT | ◻ | |
| ONNX / ONNX Runtime | Model export / CPU inference | Apache-2.0 / MIT | ◻ | |
| OpenVINO | Intel inference | Apache-2.0 | ◻ | |
| NVIDIA TensorRT, CUDA, cuDNN, JetPack | GPU/edge inference | NVIDIA proprietary | ⚠ | Not redistributed by us |
| DVC | Data versioning | Apache-2.0 | ◻ | |
| pytest | Testing | MIT | ◻ | Dev-only |
| hypothesis | Property testing | MPL-2.0 | ✅ | Dev-only |
| schemathesis | API contract testing | MIT | ✅ | Dev-only |
| ruff / mypy / pre-commit | Tooling | MIT | ◻ | Dev-only |

### 2.2 Frontend (JavaScript/TypeScript)

| Component | Use | Licence | Status | Notes |
|---|---|---|---|---|
| React | UI | MIT | ◻ | |
| Vite | Build | MIT | ◻ | |
| **Leaflet** | Maps | BSD-2-Clause | ◻ | Used **directly** through our own React wrapper component |
| react-leaflet | React bindings for Leaflet | **Hippocratic License 2.1** (v3+); MIT only for v2.x and earlier | ❌ | **Don't use** (see §1 row 2). v2.x is outdated and unmaintained, so don't downgrade to it either |
| leaflet.markercluster | Marker clustering | MIT | ✅ | v1.5.3 |
| TanStack Query | Server state | MIT | ◻ | |
| Zustand | Client state | MIT | ◻ | |
| openapi-typescript | API types | MIT | ◻ | Dev-only |
| Vitest / Testing Library | Tests | MIT | ◻ | Dev-only |
| Playwright | E2E tests | Apache-2.0 | ◻ | Dev-only |
| nginx (container) | Static serving | BSD-2-Clause | ◻ | |

### 2.3 Tools used during development

| Tool | Licence | Status | Notes |
|---|---|---|---|
| CVAT (community) | MIT | ✅ | Its `/serverless` functions may pull third-party models under separate (sometimes non-commercial) licences; bundled FFmpeg is LGPL/GPL. Self-hosted tool only; not shipped with SonarSentinel |
| Label Studio (community) | Apache-2.0 | ✅ | Enterprise edition terms not reviewed |
| **SAM 2** (facebookresearch/sam2) | Apache-2.0 (code + checkpoints) | ✅ | **Approved** for annotation assist. `cc_torch` component BSD-3-Clause; demo fonts SIL OFL 1.1 |
| SAM 1 (segment-anything) | Apache-2.0 (code + weights) | ✅ | Allowed. The SA-1B dataset has its own research licence and isn't used |
| SAM 3 / 3.1 (facebookresearch/sam3) | SAM License (custom, non-OSI; gated weights) | ❌ | **Don't use:** prohibits military/warfare and ITAR-controlled uses |
| QGIS | GPL-2.0+ | ◻ | External tool only; not bundled |
| Google Earth | Google terms | ◻ | External viewer only |

## 3. Datasets and data sources

| ID | Source | Terms | Status | Allowed use in this project | Attribution |
|---|---|---|---|---|---|
| D1 | AI4Shipwrecks (Univ. of Michigan, Deep Blue Data, DOI 10.7302/dmf4-x492) | **CC BY 4.0**: `rights_license` in the Deep Blue record JSON (checked 2026-09-13) | ✅ | Training, evaluation, demo, redistribution with attribution | Sethuraman et al., IJRR 2025; dataset DOI 10.7302/dmf4-x492 |
| D2 | Side-scan sonar imaging for mine detection (Figshare, v2, 2024-01-17) | **CC BY 4.0** | ✅ | Training, evaluation, demo, redistribution with attribution; commercial use allowed | Pessanha Santos et al., Data in Brief 2024; Figshare DOI 10.6084/m9.figshare.24574879 |
| D3 | SeabedObjects-KLSG (`huoguanying/SeabedObjects-Ship-and-Airplane-dataset`) | README: "can be used for academic purpose"; no LICENSE file | ⚠ | Academic research only; **not** in commercial models; no redistribution; victim images excluded | Huo, Wu & Li, IEEE Access 2020 |
| D3b | SeabedObjects-KLSG-II (`HHUCzCz/-SeabedObjects-KLSG--II`) | No licence, no terms (repo holds one sample image) | ❌ | **Excluded** (all rights reserved) | — |
| D4 | S3Simulator (`NambiarAthira/S3Simulator`; paper link `bashakamal/S3Simulator` is 404) | No licence for dataset/repo; README asks for citation only; paper is CC BY 4.0 but that doesn't cover the data | ❌ | **Excluded unless written permission** is obtained from the authors | Kamal Basha & Nambiar, ICPR 2024 |
| D5 | Our synthetic data | Ours (AGPL project); backgrounds inherit source terms | ✅ | Per background source | — |
| D6/D7/D9 | NOAA NCEI / Office of Coast Survey hydrographic surveys, InPort, charts | NCEI: data "free to the public with no restrictions". NOS survey metadata adds **"Not to be used for navigation"** and a no-warranty/no-liability clause. External-source data may carry restrictions, so check each record's metadata | ✅ | Training, inference, demo; show the not-for-navigation notice | Credit NOAA NCEI / OCS |
| D8 | USGS ScienceBase data releases | Mostly U.S. public domain; releases "may contain proprietary data as noted in the individual metadata records" (permission needed for those parts); credit requested | ✅ | Training, inference, demo; check each release's metadata | Cite release DOI; credit USGS |
| D10 | GhostNetZero / WWF / NIOT | Per written agreement only | — | Validation (unless the agreement allows training) | Per agreement |
| — | OpenStreetMap data | ODbL 1.0 (data after Sept 2012) | ✅ | Basemap data | "© OpenStreetMap contributors", data under ODbL |
| — | OpenStreetMap tile servers (tile.openstreetmap.org) | Tile usage policy: **no bulk downloading, no offline use**; honour caching (≥ 7 days); visible attribution; valid User-Agent and Referer | ⚠ | Online viewing only; offline tiles must come from our own rendering of OSM data or a provider that allows offline use | Visible attribution |

**Rule:** a model's allowed use is the **most restrictive** term among its training sources. Record training sources in each [model card](../ml/MODEL_CARD_TEMPLATE.md).

## 4. Project licence decision

> **✅ Decision (2026-09-13): Option A — AGPL-3.0.** Recorded as [ADR-013](../architecture/08-architecture-decisions.md#adr-013--project-licence-agpl-30). The official licence text is in [`LICENSE`](../../LICENSE). Revisit before any NIOT/production deployment that needs closed-source or permissive distribution (options B/C).

**Decision owner:** team + mentor. **Deadline:** before any public repository release or hand-over.

| Option | When it fits | Implications |
|---|---|---|
| **A. AGPL-3.0 for the whole project** ✅ chosen | Open-source release; keep Ultralytics | Source of modifications must be provided to network users; compatible with permissive dependencies; excludes dependencies with extra use restrictions (e.g. Hippocratic License, SAM License) |
| B. Apache-2.0 + swap detector | Permissive licence wanted (e.g. easier adoption by agencies/companies) | Replace Ultralytics with a permissively licensed detector/segmenter (e.g. torchvision models, Detectron2, MMDetection; check each licence); re-run evaluation |
| C. Proprietary/internal + Ultralytics Enterprise | Closed NIOT/commercial deployment | Obtain an enterprise licence; keep attribution for permissive components |
| D. Undecided (hackathon phase) | During SIH | Keep the repository private or clearly state AGPL obligations; don't mix incompatible code |

## 5. Compliance checklist (each release)

- [x] Project licence decided and `LICENSE` file present (AGPL-3.0, 2026-09-13)
- [ ] `THIRD_PARTY_NOTICES.txt` generated for Python and npm dependencies (exact versions)
- [ ] ◻ entries re-checked for the exact shipped versions *(AI4Shipwrecks licence confirmed: CC BY 4.0)*
- [ ] `react-leaflet` absent from `package.json` / lock file; SAM 3 not used anywhere
- [ ] Excluded datasets (D3b, D4) absent from all manifests unless permission is recorded
- [ ] Model cards list training sources and resulting use restrictions
- [ ] No academic-only-trained model in a commercial build
- [ ] Map attribution visible in the dashboard; offline tiles obtained in compliance with provider terms
- [ ] "Not for navigation" notice shown when NOAA-derived data is used
- [ ] No restricted/partner data, credentials or sensitive locations in the repository, deck, or demo recording
- [ ] Dataset and paper citations included in docs, deck and final report

## 6. Other compliance considerations

| Area | Consideration |
|---|---|
| **Data security / sensitivity** | Hydrographic and seabed data around ports and strategic areas may be sensitive under national rules. Default to on-premise processing and follow NIOT/MoES guidance on sharing |
| **Protected wreck sites** | Some wrecks are heritage sites or war graves; avoid publicising precise coordinates beyond public charts |
| **Human remains** | Excluded from datasets and outputs ([DMP §7](../data/DATA_MANAGEMENT_PLAN.md#7-sensitive-data-and-ethics)) |
| **Export controls** | Sonar and underwater technologies can fall under export-control regimes in some jurisdictions. Consult the institution before sharing software or models with foreign entities |
| **SIH intellectual property** | SIH 2026 guidelines: a winning idea's IP is shared equally with the problem-statement organisation or by mutual agreement. Confirm this is compatible with AGPL-3.0 distribution with the mentor/SPOC before the finale |
| **Responsible AI** | Human-in-the-loop for high-impact decisions; honest reporting of limitations; explainable scores |
