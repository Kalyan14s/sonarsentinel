"""Survey history filters for ``GET /surveys`` (ST-098, ADR-019), shared by the API and the mock.

``from`` and ``to`` accept ISO dates (``2026-09-14``, whole day included) or date-times, compared
with ``created_utc``; ``status`` is a comma-separated list of job statuses; ``q`` matches the survey
name or a source file name, case-insensitively.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sonarsentinel.errors import ValidationError
from sonarsentinel.storage.repository import project_id_for

JOB_STATUSES = ("queued", "running", "completed", "completed_with_warnings", "failed", "cancelled")
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class SurveyFilters:
    q: str | None = None
    project: str | None = None
    statuses: tuple[str, ...] = ()
    created_from: str | None = None  # inclusive, UTC_FORMAT
    created_before: str | None = None  # exclusive, UTC_FORMAT


def _bound(value: str, field: str, *, end: bool) -> str:
    text = value.strip()
    try:
        if len(text) == 10:
            day = date.fromisoformat(text)
            moment = datetime(day.year, day.month, day.day, tzinfo=UTC)
            if end:
                moment += timedelta(days=1)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            moment = moment.astimezone(UTC) if moment.tzinfo else moment.replace(tzinfo=UTC)
            if end:
                moment += timedelta(seconds=1)
    except ValueError as exc:
        raise ValidationError(f"Invalid '{field}' date: {value}", field=field) from exc
    return moment.strftime(UTC_FORMAT)


def parse_survey_filters(
    q: str | None = None,
    project: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> SurveyFilters:
    statuses = tuple(s.strip() for s in (status or "").split(",") if s.strip())
    unknown = [s for s in statuses if s not in JOB_STATUSES]
    if unknown:
        raise ValidationError(
            f"Unknown status: {', '.join(unknown)}", field="status", supported=list(JOB_STATUSES)
        )
    start = _bound(date_from, "from", end=False) if date_from and date_from.strip() else None
    end = _bound(date_to, "to", end=True) if date_to and date_to.strip() else None
    if start is not None and end is not None and start >= end:
        raise ValidationError("'from' must be before 'to'", field="from")
    return SurveyFilters(
        q=(q or "").strip() or None,
        project=(project or "").strip() or None,
        statuses=statuses,
        created_from=start,
        created_before=end,
    )


def survey_matches(summary: dict[str, Any], filters: SurveyFilters) -> bool:
    """Whether a survey summary passes the filters (used by the mock; the API filters in SQL)."""
    if filters.q:
        needle = filters.q.lower()
        names = [str(summary.get("name") or ""), *map(str, summary.get("source_files") or [])]
        if not any(needle in name.lower() for name in names):
            return False
    if filters.project:
        project = summary.get("project")
        if not project or project_id_for(str(project)) != project_id_for(filters.project):
            return False
    if filters.statuses and summary.get("status") not in filters.statuses:
        return False
    created = str(summary.get("created_utc") or "")
    if filters.created_from and created < filters.created_from:
        return False
    return not (filters.created_before and created >= filters.created_before)
