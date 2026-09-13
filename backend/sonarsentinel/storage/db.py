"""Engine, sessions and schema migrations for the SQLite database (ST-085).

Migrations are an ordered list applied at start-up and recorded in ``schema_version``, so opening
an existing database is idempotent. Add a new ``(number, description, function)`` entry for every
schema change; never edit an applied one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from sonarsentinel.report.builder import now_utc
from sonarsentinel.storage.models import Base

Migration = tuple[int, str, Callable[[Connection], None]]


def _initial_schema(conn: Connection) -> None:
    Base.metadata.create_all(conn)


MIGRATIONS: list[Migration] = [
    (
        1,
        "Initial schema: 06-data-models section 6 plus job progress and detection_json",
        _initial_schema,
    ),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


def make_engine(path: str | Path) -> Engine:
    """SQLite engine usable from the API threads and the job worker thread."""
    engine = create_engine(
        f"sqlite:///{Path(path)}", connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def schema_version(conn: Connection) -> int:
    """Highest applied migration (creates the bookkeeping table if needed)."""
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_utc TEXT NOT NULL)"
        )
    )
    value = conn.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
    return int(value or 0)


def migrate(engine: Engine) -> int:
    """Apply pending migrations in order in one transaction; returns the schema version."""
    with engine.begin() as conn:
        version = schema_version(conn)
        for number, description, apply in MIGRATIONS:
            if number <= version:
                continue
            apply(conn)
            conn.execute(
                text(
                    "INSERT INTO schema_version (version, description, applied_utc) "
                    "VALUES (:version, :description, :applied)"
                ),
                {"version": number, "description": description, "applied": now_utc()},
            )
            version = number
    return version


class Database:
    """One SQLite file: engine, migrations and a session factory."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = make_engine(self.path)
        self.version = migrate(self.engine)
        self.sessions: sessionmaker[Session] = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.sessions()

    def dispose(self) -> None:
        self.engine.dispose()
