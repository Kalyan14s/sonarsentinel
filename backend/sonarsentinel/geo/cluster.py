"""Cross-line clustering and persistence (ST-038, FR-DET-05).

The same object seen on several survey lines should be reported once. Detections of the same class
whose positions lie within ``geo.cluster_radius_m`` (default 5 m) are linked; with
``min_samples = 1`` DBSCAN reduces to connected components of that "within radius" graph, which is
implemented here directly (no scikit-learn dependency). A component is merged only when it spans at
least two source files — duplicates within one line are already removed by the chunk/tile merge.

The kept detection is the most confident member (ties: lowest ``detection_id``). Its position
becomes the member mean, ``n_views`` the number of distinct source files, and
``scores.persistence`` is ``1 − 0.5 ** n_views`` (0.50 for one view, 0.75 for two). Confidence and
the fused score are not recomputed here; the scoring step does that with the new persistence.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

EARTH_RADIUS_M = 6_371_008.8


@dataclass
class ClusterResult:
    """Detections after merging, and ``removed_id → kept_id`` for merged-away detections."""

    detections: list[dict[str, Any]]
    removed: dict[str, str] = field(default_factory=dict)


def persistence_score(n_views: int) -> float:
    """``1 − 0.5 ** n_views``: 0.5 for a single view, approaching 1 with repeated sightings."""
    return round(1.0 - 0.5 ** max(int(n_views), 0), 4)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (mean Earth radius; < 0.5% error at 5 m scales)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _position(det: dict[str, Any]) -> tuple[float, float] | None:
    pos = det.get("position") or {}
    lat, lon = pos.get("lat"), pos.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _source(det: dict[str, Any]) -> str | None:
    ref = det.get("sonar_ref") or {}
    value = ref.get("source_file")
    return str(value) if value is not None else None


def _components(points: list[tuple[float, float]], radius_m: float) -> list[list[int]]:
    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Cheap pre-filter in degrees before the exact distance (1° latitude ≈ 111 km).
    lat_tol = radius_m / 111_000.0 * 1.01
    order = sorted(range(len(points)), key=lambda k: points[k][0])
    for a_pos, a in enumerate(order):
        lat_a, lon_a = points[a]
        lon_tol = lat_tol / max(math.cos(math.radians(lat_a)), 1e-6)
        for b in order[a_pos + 1 :]:
            lat_b, lon_b = points[b]
            if lat_b - lat_a > lat_tol:
                break
            if abs(lon_b - lon_a) > lon_tol:
                continue
            if haversine_m(lat_a, lon_a, lat_b, lon_b) <= radius_m:
                parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def cluster_detections(detections: list[dict[str, Any]], *, radius_m: float = 5.0) -> ClusterResult:
    """Merge same-class detections within ``radius_m`` seen on ≥ 2 source files.

    Input dictionaries follow report schema 1.0 and are not modified. Output keeps the input order
    of the surviving detections; every detection gets ``n_views`` and ``scores.persistence``.
    """
    out = [copy.deepcopy(d) for d in detections]
    removed: dict[str, str] = {}
    drop: set[int] = set()

    by_class: dict[str, list[int]] = {}
    for i, det in enumerate(out):
        if _position(det) is not None:
            by_class.setdefault(str(det.get("class")), []).append(i)

    for members in by_class.values():
        points = [_position(out[i]) for i in members]
        for group in _components([p for p in points if p is not None], radius_m):
            indices = [members[g] for g in group]
            sources = {_source(out[i]) for i in indices}
            if len(indices) < 2 or len(sources) < 2:
                continue
            keep = min(
                indices,
                key=lambda i: (
                    -float(out[i].get("confidence") or 0.0),
                    str(out[i]["detection_id"]),
                ),
            )
            coords = [p for p in (_position(out[i]) for i in indices) if p is not None]
            position = dict(out[keep].get("position") or {})
            position["lat"] = round(sum(c[0] for c in coords) / len(coords), 6)
            position["lon"] = round(sum(c[1] for c in coords) / len(coords), 6)
            out[keep]["position"] = position
            out[keep]["n_views"] = len(sources)
            for i in indices:
                if i != keep:
                    drop.add(i)
                    removed[str(out[i]["detection_id"])] = str(out[keep]["detection_id"])

    result = []
    for i, det in enumerate(out):
        if i in drop:
            continue
        n_views = int(det.get("n_views") or 1)
        det["n_views"] = n_views
        scores = dict(det.get("scores") or {})
        scores["persistence"] = persistence_score(n_views)
        det["scores"] = scores
        result.append(det)
    return ClusterResult(result, removed)
