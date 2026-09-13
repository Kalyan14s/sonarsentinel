"""Review decisions and the label store (ST-086, ADR-018 §7).

``PATCH /detections/{id}`` accepts ``{review_status, class?, reject_reason?, note?, reviewer?}``.
Every decision other than ``pending`` writes a label record for retraining to
``labels/<yyyy-mm>/<detection_id>/label.json`` together with the detection's mask chip; ``pending``
(undo) removes the label folder but the ``review`` table keeps the history.
"""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sonarsentinel.api.filters import CLASSES, REVIEW_STATUSES
from sonarsentinel.errors import ValidationError

REJECT_REASONS = ("rock", "shadow", "ripples", "noise", "other")
REVIEW_FIELDS = frozenset({"review_status", "class", "reject_reason", "note", "reviewer"})
MAX_NOTE_CHARS = 2000
MAX_REVIEWER_CHARS = 100


@dataclass(frozen=True)
class ReviewDecision:
    status: str
    new_class: str | None = None
    reject_reason: str | None = None
    note: str | None = None
    reviewer: str | None = None


def _text(body: dict[str, Any], key: str, limit: int) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{key} must be a string", field=key)
    if len(value) > limit:
        raise ValidationError(f"{key} is longer than {limit} characters", field=key)
    return value


def parse_review(body: Any, current_class: str) -> ReviewDecision:
    """Validate a review body against the detection's current class (400 on any problem)."""
    if not isinstance(body, dict):
        raise ValidationError("Send the review as a JSON object", field="body")
    unknown = sorted(set(body) - REVIEW_FIELDS)
    if unknown:
        raise ValidationError(
            f"Unknown review field(s): {', '.join(unknown)}",
            field=unknown[0],
            supported=sorted(REVIEW_FIELDS),
        )
    status = body.get("review_status")
    if status not in REVIEW_STATUSES:
        raise ValidationError(
            "review_status must be pending, confirmed, rejected or reclassified",
            field="review_status",
            supported=list(REVIEW_STATUSES),
        )
    reason = _text(body, "reject_reason", 20)
    new_class = _text(body, "class", 40)
    if status == "rejected" and reason not in REJECT_REASONS:
        raise ValidationError(
            "reject_reason is required for a rejection",
            field="reject_reason",
            supported=list(REJECT_REASONS),
        )
    if status == "reclassified":
        if new_class not in CLASSES:
            raise ValidationError(
                "class must be a detection class when reclassifying",
                field="class",
                supported=list(CLASSES),
            )
        if new_class == current_class:
            raise ValidationError(f"The detection is already {current_class}", field="class")
    return ReviewDecision(
        status=str(status),
        new_class=new_class if status == "reclassified" else None,
        reject_reason=reason if status == "rejected" else None,
        note=_text(body, "note", MAX_NOTE_CHARS),
        reviewer=_text(body, "reviewer", MAX_REVIEWER_CHARS),
    )


def apply_review(det: dict[str, Any], decision: ReviewDecision, updated_utc: str) -> dict[str, Any]:
    """Copy of the detection with the new review block (and class when reclassified)."""
    updated = copy.deepcopy(det)
    if decision.new_class is not None:
        updated["class"] = decision.new_class
    updated["review"] = {
        "status": decision.status,
        "reviewer": decision.reviewer,
        "reject_reason": decision.reject_reason,
        "note": decision.note,
        "updated_utc": updated_utc,
    }
    return updated


def label_record(
    before: dict[str, Any], after: dict[str, Any], survey_id: str, created_utc: str
) -> dict[str, Any]:
    """The ``label.json`` content for one review decision."""
    review = after["review"]
    ref = after.get("sonar_ref") or {}
    return {
        "detection_id": after["detection_id"],
        "survey_id": survey_id,
        "verdict": review["status"],
        "class_original": before["class"],
        "class_final": after["class"],
        "reject_reason": review["reject_reason"],
        "reviewer": review["reviewer"],
        "note": review["note"],
        "created_utc": created_utc,
        "model_version": after.get("model_version"),
        "confidence": after.get("confidence"),
        "scores": after.get("scores"),
        "position": after.get("position"),
        "source_file": ref.get("source_file"),
        "ping_start": ref.get("ping_start"),
        "ping_end": ref.get("ping_end"),
    }


def label_folder(root: Path, detection_id: str, created_utc: str) -> Path:
    return root / created_utc[:7] / detection_id


def remove_labels(root: Path, detection_id: str) -> int:
    """Delete every label folder of a detection (any month); returns how many were removed."""
    removed = 0
    if root.is_dir():
        for folder in root.glob(f"*/{detection_id}"):
            if folder.is_dir():
                shutil.rmtree(folder)
                removed += 1
    return removed


def write_label(root: Path, record: dict[str, Any], chip: Path | None) -> Path:
    """Write ``label.json`` (and ``chip.png`` when the chip exists); returns the folder."""
    folder = label_folder(root, record["detection_id"], record["created_utc"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "label.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if chip is not None and chip.is_file():
        shutil.copyfile(chip, folder / "chip.png")
    return folder
