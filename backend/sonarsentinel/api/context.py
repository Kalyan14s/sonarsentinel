"""Runtime state of the real API app: data folder, database and job worker.

The context opens lazily (or at app start-up through the lifespan), so importing
``sonarsentinel.api.main`` has no side effects on disk.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from sonarsentinel.jobs.manager import JobManager
from sonarsentinel.storage.db import Database

GIB = 1024**3
DB_FILENAME = "sonarsentinel.db"
_INIT_LOCK = threading.Lock()


@dataclass
class ApiContext:
    config: dict[str, Any]
    data_dir: Path
    database: Database
    jobs: JobManager
    id_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def max_upload_bytes(self) -> int:
        return int(float(self.config.get("ingest", {}).get("max_upload_gb", 2)) * GIB)

    def close(self) -> None:
        self.jobs.stop()
        self.database.dispose()


def open_context(config: dict[str, Any], data_dir: str | Path) -> ApiContext:
    """Open the database, fail jobs left over from a stopped server and start the worker."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    database = Database(root / DB_FILENAME)
    jobs = JobManager(database, config, root)
    jobs.recover()
    jobs.start()
    return ApiContext(config=config, data_dir=root, database=database, jobs=jobs)


def get_context(app: FastAPI) -> ApiContext:
    context: ApiContext | None = getattr(app.state, "context", None)
    if context is None:
        with _INIT_LOCK:
            context = getattr(app.state, "context", None)
            if context is None:
                context = open_context(app.state.config, app.state.data_dir)
                app.state.context = context
    return context


def close_context(app: FastAPI) -> None:
    context: ApiContext | None = getattr(app.state, "context", None)
    if context is not None:
        context.close()
        app.state.context = None
