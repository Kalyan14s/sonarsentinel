"""ADR-018 §3–4 detection filters and export scopes against a separate reference (TC-API-004)."""

from __future__ import annotations

import random
from typing import Any

import pytest

from sonarsentinel.api.filters import (
    CLASSES,
    TIERS,
    parse_query,
    query_detections,
    select_scope,
    summarize,
)
from sonarsentinel.errors import ValidationError

FLAGS = ("DROPOUT", "HIGH_MOTION", "NEAR_NADIR", "NOT_GEOTAGGED")
STATUSES = ("pending", "confirmed", "rejected", "reclassified")


def _items(n: int = 300, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    items = []
    for i in range(n):
        geotagged = rng.random() > 0.1
        items.append(
            {
                "detection_id": f"SRV-20260913-001-D{i + 1:04d}",
                "class": rng.choice(CLASSES),
                "confidence": round(rng.uniform(0, 100), 1),
                "alert_tier": rng.choice(TIERS),
                "position": {
                    "lat": round(13.0 + rng.random() * 0.01, 6) if geotagged else None,
                    "lon": round(80.0 + rng.random() * 0.01, 6) if geotagged else None,
                },
                "dimensions": {"area_m2": rng.choice([None, round(rng.uniform(0.1, 50), 2)])},
                "sonar_ref": {"ping_start": rng.randint(0, 5000)},
                "quality_flags": rng.sample(FLAGS, rng.randint(0, 2)),
                "review": {"status": rng.choice(STATUSES)},
            }
        )
    return items


def _reference(items: list[dict[str, Any]], p: dict[str, Any]) -> list[str]:
    """Plain restatement of API spec §2.4 used to check the shared module."""
    out = []
    for d in items:
        status = d["review"]["status"]
        if "class" in p and d["class"] not in p["class"].split(","):
            continue
        if "min_conf" in p and d["confidence"] < p["min_conf"]:
            continue
        if "max_conf" in p and d["confidence"] > p["max_conf"]:
            continue
        if "tier" in p and d["alert_tier"] not in p["tier"].split(","):
            continue
        if "review_status" in p and status not in p["review_status"].split(","):
            continue
        if "flags" in p and not set(p["flags"].split(",")) & set(d["quality_flags"]):
            continue
        if not p.get("include_rejected", True) and status == "rejected":
            continue
        if "bbox" in p:
            x1, y1, x2, y2 = (float(v) for v in p["bbox"].split(","))
            lat, lon = d["position"]["lat"], d["position"]["lon"]
            if lat is None or not (x1 <= lon <= x2 and y1 <= lat <= y2):
                continue
        out.append(d)
    sort = p.get("sort", "-confidence")
    field, reverse = sort.lstrip("-"), sort.startswith("-")

    def value(d: dict[str, Any]) -> float:
        if field == "confidence":
            return float(d["confidence"])
        if field == "area":
            return float(d["dimensions"]["area_m2"] or 0.0)
        return float(d["sonar_ref"]["ping_start"] or 0)

    if field == "class":
        out.sort(key=lambda d: (d["class"], d["detection_id"]))
    else:
        out.sort(key=lambda d: d["detection_id"])
        out.sort(key=value, reverse=reverse)
    return [d["detection_id"] for d in out]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"sort": "confidence"},
        {"sort": "-area"},
        {"sort": "ping"},
        {"sort": "class"},
        {"class": "ghost_net,pipe", "min_conf": 40.0},
        {"tier": "hazard", "max_conf": 90.0},
        {"review_status": "confirmed,reclassified"},
        {"flags": "DROPOUT,NEAR_NADIR", "include_rejected": False},
        {"bbox": "80.002,13.002,80.008,13.009", "sort": "-ping"},
        {"min_conf": 20.0, "max_conf": 60.0, "tier": "review,anomaly", "class": "cylinder"},
    ],
)
def test_query_matches_reference(params: dict[str, Any]) -> None:
    items = _items()
    query = parse_query(
        cls=params.get("class"),
        min_conf=params.get("min_conf"),
        max_conf=params.get("max_conf"),
        tier=params.get("tier"),
        review_status=params.get("review_status"),
        flags=params.get("flags"),
        bbox=params.get("bbox"),
        include_rejected=params.get("include_rejected", True),
        sort=params.get("sort"),
    )
    got = [d["detection_id"] for d in query_detections(items, query)]
    assert got == _reference(items, params)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cls": "whale"},
        {"tier": "urgent"},
        {"review_status": "maybe"},
        {"flags": "LOUD"},
        {"sort": "size"},
        {"bbox": "80,13,79,14"},
        {"bbox": "1,2,3"},
        {"bbox": "a,b,c,d"},
        {"min_conf": 120.0},
        {"min_conf": 60.0, "max_conf": 50.0},
    ],
)
def test_invalid_parameters_are_400(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as info:
        parse_query(**kwargs)
    assert info.value.http_status == 400 and info.value.code == "VALIDATION_ERROR"


def test_export_scopes() -> None:
    """TC-REP-007 (module level): filtered, hazards, confirmed; rejected left out by default."""
    items = _items()
    ids = {d["detection_id"] for d in items}
    everything = select_scope(items, "all", include_rejected=True)
    assert [d["detection_id"] for d in everything] == [d["detection_id"] for d in items]
    default = select_scope(items, "all")
    assert all(d["review"]["status"] != "rejected" for d in default)
    filtered = select_scope(items, "filtered", parse_query(min_conf=60.0))
    assert filtered and all(
        d["confidence"] >= 60 and d["review"]["status"] != "rejected" for d in filtered
    )
    assert [d["detection_id"] for d in filtered] == [
        d["detection_id"]
        for d in items
        if d["confidence"] >= 60 and d["review"]["status"] != "rejected"
    ]
    hazards = select_scope(items, "hazards", include_rejected=True)
    assert hazards and all(d["alert_tier"] == "hazard" for d in hazards)
    confirmed = select_scope(items, "confirmed")
    assert confirmed and {d["review"]["status"] for d in confirmed} <= {"confirmed", "reclassified"}
    assert {d["detection_id"] for d in confirmed} <= ids
    with pytest.raises(ValidationError):
        select_scope(items, "everything")


def test_summary_counts() -> None:
    items = _items(50)
    summary = summarize(items)
    assert summary["total_detections"] == 50
    assert sum(summary["by_class"].values()) == 50 and sum(summary["by_tier"].values()) == 50
    assert list(summary["by_class"]) == sorted(summary["by_class"])
