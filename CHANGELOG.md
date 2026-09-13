# Changelog

All notable changes to SonarSentinel are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

Categories: **Added** · **Changed** · **Deprecated** · **Removed** · **Fixed** · **Security** · **Models** (model/calibrator releases) · **Data** (dataset manifest versions)

## [Unreleased]

### Added
- Working repository at `C:\dev\sonarsentinel` (git `main`); Phase 0 documentation baseline committed and tagged `docs-baseline-1.0`
- Backend scaffold (ST-001): `sonarsentinel` package with typed errors matching the API error model, config loading and hashing, upload validation (stage S0: extension, size, magic bytes), and CLI (`version`, `validate`, `config`; `detect` and `serve` are placeholders)
- `backend/environment.yml` (core + geo + dev), `backend/requirements-ml.txt` (Sprint 3), `.env.example`, root `ruff.toml`
- CI workflow (ST-002): backend lint, format check, strict mypy, pytest with coverage; documentation checks; frontend job that activates once `frontend/package.json` exists
- `scripts/fetch_test_data.py` with SHA-256 pinning and trust-on-first-use, manifest and tests (ST-004)
- pre-commit hooks: whitespace, end-of-file, YAML/TOML, merge conflicts, large files, ruff (`LICENSE` and deck binaries excluded)
- SIH 2026 idea deck draft (PPTX + PDF) built on the official template: `docs/hackathon/idea-deck/`
- `docs/planning/SPRINT_1_PLAN.md`, `docs/communications/OUTREACH_DRAFTS.md`, `ml/datasets/LICENSES.md` (dataset licence register)
- ADR-014: CSS Modules + CSS custom-property design tokens for the dashboard
- Placeholder READMEs for `frontend/`, `edge/`, `docker/`, `ml/`

### Changed
- Developer Setup: split environment files documented; test commands run from `backend/` (same as CI); commands available now vs planned; note on using conda without PATH
- Docs index lists the Sprint 1 plan, outreach drafts, licence register and idea deck
- README: status, quick start (works today vs planned)

### Notes
- Verified on Windows 11 with Miniforge 26.7.2 (installer SHA-256 matched the GitHub release digest; signature valid) and Python 3.11.16: GDAL 3.12.3, rasterio 1.4.4, pyproj 3.7.2, OpenCV 5.0.0, pyxtf 1.5.0 import correctly
- ruff check and format clean · mypy `--strict` no issues (14 files) · pytest 32 passed, 96% coverage · all pre-commit hooks pass
- Repository published: https://github.com/Kalyan14s/sonarsentinel (public); `main` and tag `docs-baseline-1.0` pushed
- First CI run on GitHub passed: backend (lint, types, tests on Ubuntu), documentation checks, frontend job
- CI job builds the conda environment and runs tests on ubuntu-latest and windows-latest: passing (ST-003)
- Branch protection on `main`: pull request required, 5 required checks, no force pushes or deletion (ST-006)
- 91 backlog stories created as GitHub issues with epic/priority/role labels and sprint milestones S0–S6 + Backlog
- DVC initialised (analytics off, local remote); datasets downloaded with provenance and added to DVC: mine-detection SSS (0.61 GB, MD5 verified), SeabedObjects-KLSG (48 MB). AI4Shipwrecks licence confirmed CC BY 4.0 (automated download blocked, needs browser download); S3Simulator samples kept locally for private evaluation only (no licence)
- Idea deck: team name "Vashishta" on the title slide and team badges (team ID pending)

## [0.2.0] — 2026-09-13 — Phase 0 complete

### Added
- `LICENSE`: official GNU AGPL-3.0 text; project licence decision recorded as ADR-013 (README, CONTRIBUTING and Licences & Compliance updated)
- `docs/planning/PHASE0_REVIEW_SIGNOFF.md`: Phase 0 review checklist, issue log and sign-off record per role
- SIH 2026 facts in the Project Plan, TODO and SIH Presentation: official idea template rules, idea deadline 30 Sept 2026 (milestone IS), team composition rules, finale proposed Dec 2026
- `TODO.md`: master phase-by-phase checklist covering all 91 backlog stories, gates, exit criteria and continuous tasks
- `scripts/docs/verify_docs.ps1`: automated documentation verification (links, anchors, IDs, wireframe frames)
- `docs/reports/DOCUMENTATION_VERIFICATION_REPORT.md`
- API spec: `GET /surveys` query parameters and `GET /surveys/{id}/waterfall` parameters

### Changed
- PRD §15 and Project Plan milestone exit criteria aligned (M3 thin slice, M4 JSON/CSV, M5 AC-01…05 + AC-07)
- Review API and data model: `reject_reason` added for rejected detections
- Literature Review and Datasets: 11 references verified; 7 corrected (full authors, venues, pages, DOIs); STARS is now cited as BMVC 2023 and S3Simulator as ICPR 2024 (LNCS 15316); † markers removed
- TODO: Phase 0 closing items updated; team details moved to Phase 1; SIH idea-submission tasks added to Phase 1
- Licences & Compliance v1.1: all *verify* items checked against primary sources (status column added); AI4Shipwrecks licence still unconfirmed (manual check moved to Phase 1)
- ADR-009 amended: dashboard uses Leaflet directly instead of react-leaflet (Hippocratic License 2.1 is incompatible with AGPL-3.0)
- Annotation Guidelines: SAM 2 (Apache-2.0) specified; SAM 3 excluded (licence prohibits military uses)
- Datasets: licence status per dataset recorded; S3Simulator and SeabedObjects-KLSG-II excluded (no licence); NOAA "not for navigation" notice required
- **Phase 0 closed:** documentation baseline (PRD v1.0, architecture) approved by the team lead (R6); R1–R5 confirmations and the `docs-baseline-1.0` tag moved to Sprint 0

### Fixed
- Edge alert message format in `07-deployment.md` now matches the S-08 wireframe
- Victim-image exclusion stated in PRD §8.1 and Project Idea dataset tables

## [0.1.0] — 2026-09-13 — Documentation baseline

### Added
- Project idea and Product Requirements Document (`docs/PROJECT_IDEA.md`, `docs/PRD.md`)
- Architecture set: system architecture, data pipeline, ML models, geotagging engine, API specification, data models, deployment, architecture decisions (`docs/architecture/`)
- Wireframes for 8 screens with navigation flow and visual language (`docs/wireframes/`)
- Project plan and product backlog (`docs/planning/`)
- Datasets guide, annotation guidelines, data management plan (`docs/data/`)
- Test plan and test cases with traceability matrix (`docs/testing/`)
- Developer setup, user manual, operations runbook (`docs/guides/`)
- Model card and experiment log templates (`docs/ml/`)
- Literature and technology review (`docs/research/`)
- SIH presentation content and demo script with judge Q&A (`docs/hackathon/`)
- Final project report template (`docs/reports/`)
- Licences & compliance (`docs/legal/`), security policy, contributing guide, GitHub issue/PR templates
