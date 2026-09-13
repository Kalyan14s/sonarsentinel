"""Chunked access to long sonar logs (ST-026).

Chunks overlap so detections near a boundary are seen whole in at least one chunk; the merge stage
(ST-054) removes duplicates. Channel slices are views, so memory-mapped arrays stay on disk.
See ``docs/architecture/02-data-pipeline.md`` §4.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from sonarsentinel.errors import ValidationError
from sonarsentinel.ingest.models import SonarLog


def chunk_ranges(n_pings: int, size: int = 2000, overlap: int = 200) -> list[tuple[int, int]]:
    """Return ``(start, stop)`` ping ranges covering ``n_pings`` with the given overlap."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValidationError("Need size > 0 and 0 <= overlap < size", size=size, overlap=overlap)
    if n_pings <= 0:
        return []
    step = size - overlap
    ranges = []
    start = 0
    while True:
        stop = min(start + size, n_pings)
        ranges.append((start, stop))
        if stop >= n_pings:
            return ranges
        start += step


def slice_log(log: SonarLog, start: int, stop: int) -> SonarLog:
    """A view of pings ``start:stop``; ``nav['ping']`` keeps the original ping numbers."""
    return replace(
        log,
        nav=log.nav.iloc[start:stop].reset_index(drop=True),
        port=None if log.port is None else log.port[start:stop],
        starboard=None if log.starboard is None else log.starboard[start:stop],
        image=None if log.image is None else log.image[start:stop],
        warnings=list(log.warnings),
    )


def iter_chunks(
    log: SonarLog, size: int = 2000, overlap: int = 200
) -> Iterator[tuple[int, SonarLog]]:
    """Yield ``(ping_offset, chunk)`` for each overlapping chunk of a waterfall log."""
    for start, stop in chunk_ranges(log.n_pings, size, overlap):
        yield start, slice_log(log, start, stop)
