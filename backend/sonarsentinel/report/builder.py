"""Report assembly for schema ``report-1.0`` (``docs/architecture/06-data-models.md``)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

import pandas as pd

REPORT_VERSION = "1.0"


def iso_utc(value: Any) -> str | None:
    """ISO 8601 UTC string with hundredths of a second (``2026-09-12T05:17:21.50Z``), or None."""
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return str(ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4]) + "Z"


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def alert_tier(
    confidence: float,
    tiers: dict[str, float],
    anomaly_score: float | None = None,
    anomaly_threshold: float = 0.5,
) -> str:
    """``hazard`` / ``review`` / ``anomaly`` / ``hidden`` from calibrated confidence (0–100).

    ``anomaly`` needs confidence in the anomaly band **and** an anomaly score ≥ τ
    (``anomaly.threshold``; ``docs/architecture/03-ml-models.md`` §5, ADR-017 §4).
    """
    if confidence >= tiers["hazard"]:
        return "hazard"
    if confidence >= tiers["review"]:
        return "review"
    if (
        anomaly_score is not None
        and anomaly_score >= anomaly_threshold
        and confidence >= tiers["anomaly"]
    ):
        return "anomaly"
    return "hidden"


def build_report(
    *,
    survey: dict[str, Any],
    processing: dict[str, Any],
    detections: list[dict[str, Any]],
    generated_utc: str | None = None,
) -> dict[str, Any]:
    """Wrap the sections and compute the summary counts."""
    return {
        "report_version": REPORT_VERSION,
        "generated_utc": generated_utc or now_utc(),
        "survey": survey,
        "processing": processing,
        "summary": {
            "total_detections": len(detections),
            "by_class": dict(sorted(Counter(d["class"] for d in detections).items())),
            "by_tier": dict(sorted(Counter(d["alert_tier"] for d in detections).items())),
        },
        "detections": detections,
    }
