"""Detection filters, sorting and export scopes (ADR-018 §3–4).

One implementation serves ``GET /surveys/{id}/detections``, ``scope=filtered`` report exports and
the mock server, so the dashboard, the API and downloaded files always select the same detections.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from sonarsentinel.errors import ValidationError

CLASSES = ("shipwreck", "pipe", "cylinder", "ghost_net", "debris_other", "unknown_anomaly")
TIERS = ("hazard", "review", "anomaly", "hidden")
REVIEW_STATUSES = ("pending", "confirmed", "rejected", "reclassified")
QUALITY_FLAGS = (
    "DROPOUT",
    "HIGH_MOTION",
    "NEAR_NADIR",
    "SURFACE_RETURN_BAND",
    "TILE_EDGE",
    "GPS_INTERPOLATED",
    "LAYBACK_ESTIMATED",
    "HEADING_FROM_COG",
    "NO_ALTITUDE_BOTTOM_TRACKED",
    "NOT_GEOTAGGED",
)
SORTS = ("confidence", "-confidence", "area", "-area", "ping", "-ping", "class")
SCOPES = ("all", "filtered", "hazards", "confirmed")
DEFAULT_SORT = "-confidence"
MAX_LIMIT = 5000

Detection = dict[str, Any]


@dataclass(frozen=True)
class DetectionQuery:
    """Parsed query parameters; ``None`` means "no restriction"."""

    classes: frozenset[str] | None = None
    min_conf: float | None = None
    max_conf: float | None = None
    tiers: frozenset[str] | None = None
    review_statuses: frozenset[str] | None = None
    flags: frozenset[str] | None = None
    bbox: tuple[float, float, float, float] | None = None
    include_rejected: bool = True
    sort: str = DEFAULT_SORT


def _csv(name: str, value: str | None, allowed: Iterable[str]) -> frozenset[str] | None:
    if value is None:
        return None
    items = frozenset(v.strip() for v in value.split(",") if v.strip())
    if not items:
        return None
    allowed_set = set(allowed)
    unknown = sorted(items - allowed_set)
    if unknown:
        raise ValidationError(
            f"Unknown {name}: {', '.join(unknown)}", field=name, supported=sorted(allowed_set)
        )
    return items


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """``minLon,minLat,maxLon,maxLat`` → tuple; 400 for anything else."""
    if value is None or not value.strip():
        return None
    message = "bbox must be minLon,minLat,maxLon,maxLat"
    try:
        parts = [float(v) for v in value.split(",")]
    except ValueError as exc:
        raise ValidationError(message, field="bbox", bbox=value) from exc
    if len(parts) != 4 or parts[0] > parts[2] or parts[1] > parts[3]:
        raise ValidationError(message, field="bbox", bbox=value)
    return parts[0], parts[1], parts[2], parts[3]


def _confidence(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if not 0.0 <= float(value) <= 100.0:
        raise ValidationError(f"{name} must be between 0 and 100", field=name, value=value)
    return float(value)


def parse_query(
    *,
    cls: str | None = None,
    min_conf: float | None = None,
    max_conf: float | None = None,
    tier: str | None = None,
    review_status: str | None = None,
    flags: str | None = None,
    bbox: str | None = None,
    include_rejected: bool = True,
    sort: str | None = None,
) -> DetectionQuery:
    """Validate the detection query parameters of API spec §2.4 (ADR-018 §3)."""
    low = _confidence("min_conf", min_conf)
    high = _confidence("max_conf", max_conf)
    if low is not None and high is not None and low > high:
        raise ValidationError("min_conf must not exceed max_conf", field="min_conf")
    order = sort or DEFAULT_SORT
    if order not in SORTS:
        raise ValidationError(f"Unknown sort: {order}", field="sort", supported=list(SORTS))
    return DetectionQuery(
        classes=_csv("class", cls, CLASSES),
        min_conf=low,
        max_conf=high,
        tiers=_csv("tier", tier, TIERS),
        review_statuses=_csv("review_status", review_status, REVIEW_STATUSES),
        flags=_csv("flags", flags, QUALITY_FLAGS),
        bbox=parse_bbox(bbox),
        include_rejected=include_rejected,
        sort=order,
    )


def review_status(det: Detection) -> str:
    return str((det.get("review") or {}).get("status", "pending"))


def matches(det: Detection, query: DetectionQuery) -> bool:
    """True when the detection passes every restriction of ``query``."""
    confidence = float(det["confidence"])
    status = review_status(det)
    if query.classes is not None and det["class"] not in query.classes:
        return False
    if query.min_conf is not None and confidence < query.min_conf:
        return False
    if query.max_conf is not None and confidence > query.max_conf:
        return False
    if query.tiers is not None and det["alert_tier"] not in query.tiers:
        return False
    if query.review_statuses is not None and status not in query.review_statuses:
        return False
    if query.flags is not None and not query.flags & set(det.get("quality_flags") or []):
        return False
    if not query.include_rejected and status == "rejected":
        return False
    if query.bbox is not None:
        position = det.get("position") or {}
        lat, lon = position.get("lat"), position.get("lon")
        if lat is None or lon is None:
            return False
        min_lon, min_lat, max_lon, max_lat = query.bbox
        if not (min_lon <= float(lon) <= max_lon and min_lat <= float(lat) <= max_lat):
            return False
    return True


def _sort_key(order: str) -> Callable[[Detection], tuple[Any, ...]]:
    """Sort key with ``detection_id`` as tie-breaker so results are deterministic."""
    field = order.lstrip("-")
    sign = -1.0 if order.startswith("-") else 1.0
    if field == "class":
        return lambda d: (d["class"], d["detection_id"])
    if field == "confidence":
        return lambda d: (sign * float(d["confidence"]), d["detection_id"])
    if field == "area":
        return lambda d: (
            sign * float((d.get("dimensions") or {}).get("area_m2") or 0.0),
            d["detection_id"],
        )
    return lambda d: (
        sign * float((d.get("sonar_ref") or {}).get("ping_start") or 0),
        d["detection_id"],
    )


def filter_detections(items: Iterable[Detection], query: DetectionQuery) -> list[Detection]:
    """Matching detections in their original order."""
    return [d for d in items if matches(d, query)]


def query_detections(items: Iterable[Detection], query: DetectionQuery) -> list[Detection]:
    """Matching detections sorted by ``query.sort``."""
    return sorted(filter_detections(items, query), key=_sort_key(query.sort))


def select_scope(
    items: Iterable[Detection],
    scope: str,
    query: DetectionQuery | None = None,
    *,
    include_rejected: bool = False,
) -> list[Detection]:
    """Detections for a report export (ADR-018 §4), in their original order."""
    if scope not in SCOPES:
        raise ValidationError(f"Unknown scope: {scope}", field="scope", supported=list(SCOPES))
    if scope == "filtered":
        base = replace(query or DetectionQuery(), include_rejected=include_rejected)
        return filter_detections(items, base)
    selected = list(items)
    if scope == "hazards":
        selected = [d for d in selected if d["alert_tier"] == "hazard"]
    elif scope == "confirmed":
        selected = [d for d in selected if review_status(d) in ("confirmed", "reclassified")]
    if not include_rejected:
        selected = [d for d in selected if review_status(d) != "rejected"]
    return selected


def summarize(items: Iterable[Detection]) -> dict[str, Any]:
    """Report ``summary`` block for a list of detections."""
    detections = list(items)
    return {
        "total_detections": len(detections),
        "by_class": dict(sorted(Counter(d["class"] for d in detections).items())),
        "by_tier": dict(sorted(Counter(d["alert_tier"] for d in detections).items())),
    }
