# sonarsentinel (backend)

Python package with the SonarSentinel processing pipeline, CLI and API.

- Architecture: [docs/architecture](../docs/architecture/README.md)
- Setup: [Developer Setup](../docs/guides/DEVELOPER_SETUP.md)

```bash
conda env create -f backend/environment.yml
conda activate sonarsentinel
pip install -e "backend[dev]"
sonarsentinel --help
cd backend && pytest --cov=sonarsentinel
```

**Status (Sprint 0):** package skeleton, typed errors, configuration loading/hashing, upload validation (stage S0) and CLI (`version`, `validate`, `config`). `detect` and `serve` are placeholders until Sprints 3–4.
