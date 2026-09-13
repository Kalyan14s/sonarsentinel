"""Regenerate the mock API fixtures (ST-087) from a real pipeline run.

Runs the pipeline on a synthetic XTF survey (test data TD-01 with extended targets), records the
job events, then **varies classes and confidences** so the dashboard has every class and tier to
render. The survey is named ``MOCK …`` and its project ``mock-fixture`` so it is never mistaken for
real results. Output: ``backend/sonarsentinel/api/fixtures/mock_report.json`` and
``mock_events.json``.

    python scripts/make_mock_fixtures.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.pipeline import run_pipeline  # noqa: E402
from sonarsentinel.report.builder import alert_tier  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

CLASSES = ["ghost_net", "shipwreck", "pipe", "cylinder", "debris_other", "ghost_net", "cylinder"]
CONFIDENCES = [91.5, 84.2, 72.8, 63.0, 55.4, 44.9, 27.3]


def main() -> None:
    out = ROOT / "backend" / "sonarsentinel" / "api" / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        targets = [
            (250 + 280 * i, "starboard" if i % 2 == 0 else "port", 350 + 60 * i) for i in range(7)
        ]
        survey = write_synthetic_xtf(
            Path(tmp) / "mock_line.xtf",
            n_pings=2300,
            samples_per_side=1000,
            step_m=0.1,
            track="curved",
            targets=targets,
            target_extent=(12, 30),
        )
        config = load_config()
        events: list[dict] = []
        report = run_pipeline(
            survey.path,
            config=config,
            on_event=events.append,
            survey_id="SRV-20260912-900",
            survey_name="MOCK Chennai line 07",
        )

    tiers = config["scoring"]["tiers"]
    report["survey"]["project"] = "mock-fixture"
    by_id = {}
    for i, det in enumerate(report["detections"]):
        det["class"] = CLASSES[i % len(CLASSES)]
        det["confidence"] = CONFIDENCES[i % len(CONFIDENCES)]
        det["alert_tier"] = alert_tier(
            det["confidence"], tiers, anomaly_score=0.6 if det["confidence"] < 50 else None
        )
        det["scores"]["fused"] = round(det["confidence"] / 100, 4)
        by_id[det["detection_id"]] = det
    from collections import Counter

    report["summary"] = {
        "total_detections": len(report["detections"]),
        "by_class": dict(sorted(Counter(d["class"] for d in report["detections"]).items())),
        "by_tier": dict(sorted(Counter(d["alert_tier"] for d in report["detections"]).items())),
    }
    for event in events:
        if event["type"] == "detection":
            event["detection"] = by_id[event["detection"]["detection_id"]]
        if event["type"] == "done":
            event["summary"] = report["summary"]
    (out / "mock_report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    (out / "mock_events.json").write_text(json.dumps(events, indent=1) + "\n", encoding="utf-8")
    print(f"{len(report['detections'])} detections, {len(events)} events -> {out}")


if __name__ == "__main__":
    main()
