# Dependency scan — 2026-09-14 (baseline before Sprint 6 upgrades)

Part of TC-SEC-004 ([Test Cases](../TEST_CASES.md)); the post-upgrade state and CI results are in [TSR-M6](TSR-M6.md).

| Scan | Tool | Scope | Result |
|---|---|---|---|
| Python | `pip-audit` 2.10.1 | Development conda environment `sonarsentinel` (202 packages) | 12 advisories in 2 packages |
| JavaScript | `npm audit` (npm 10.9.3) | `frontend/` lockfile | 7 packages: 1 critical, 1 high, 5 moderate |
| Container images | Trivy | Backend and frontend images | Not run locally (no Docker); added to CI in Sprint 6 |

## Python

| Package | Version | Advisories | Fixed in | Reached by | Assessment |
|---|---|---|---|---|---|
| `gdal` | 3.12.3 (conda-forge) | PYSEC-2026-4, -2153, -2154, -2155, -2156, -2157 (HDF4 / HDF-EOS drivers), PYSEC-2026-193 (netCDF driver) | 3.13.0 – 3.13.1 | `rasterio` in the `geo` extra | Upload validation only accepts TIFF/PNG/JPEG/XTF magic bytes, so the vulnerable HDF4 and netCDF drivers are not reached through the API; a crafted file opened directly with the CLI could reach them. **Action:** upgrade GDAL to ≥ 3.13.1 when conda-forge rasterio supports it; restrict raster opening to the GTiff driver. Docker images use rasterio wheels with their own bundled GDAL, scanned separately in CI. |
| `diskcache` | 5.6.3 | PYSEC-2026-2447 (CVE-2025-69872): pickle deserialisation from a writable cache directory | none | `dvc-data` (DVC data versioning, developer tooling only) | Not part of the runtime package or images; exploitation needs write access to the developer's DVC cache. Accepted for development; monitor for a fix. |

## JavaScript (frontend)

| Package | Severity | Advisory | Direct | Affects the shipped app? | Fix |
|---|---|---|---|---|---|
| `vitest` | critical | GHSA-5xrq-8626-4rwp: file read/execution while the Vitest UI server listens | yes (dev) | No — test runner; the UI server is not used | vitest ≥ 3.2.6 |
| `vitest`, `@vitest/mocker`, `vite-node` | moderate | GHSA-82fw-gwwq-j7x9: path traversal via redirect mock | dev | No | vitest ≥ 4.1.11 |
| `vite` | high | GHSA-fx2h-pf6j-xcff: `server.fs.deny` bypass on Windows alternate paths | yes (dev) | No — development server only (bound to localhost) | vite > 6.4.2 |
| `vite` | moderate | GHSA-4w7w-66w2-5vf9 (optimized deps `.map` traversal), GHSA-v6wh-96g9-6wx3 (launch-editor NTLM hash disclosure) | yes (dev) | No | vite > 6.4.2 |
| `esbuild` | moderate | GHSA-67mh-4wv8-2f99: any website can query the dev server | dev | No | via vite upgrade |
| `react-router`, `react-router-dom` | moderate | GHSA-wrjc-x8rr-h8h6 (open redirect via backslash in `<Link>`/`useNavigate`), GHSA-337j-9hxr-rhxg (SSR hydration) | yes (runtime) | Low — links are internal constant paths; the app does not use SSR | react-router ≥ 7.18.0 |

**Actions (Sprint 6):** upgrade vitest, vite and react-router-dom (major versions), then gate CI on `npm audit --audit-level=critical` and `pip-audit`.
