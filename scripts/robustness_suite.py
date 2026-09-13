"""ST-111 robustness suite (Test Plan §6.4; AC-06, TC-ROB-001…004, TC-ING-012).

Generates the TD-05 and TD-07 variants of one synthetic line (zeroed pings plus a truncated
final record, a 30 s GPS gap, ±10° roll, no altitude, heavy speckle, truncation, a corrupt
header) and runs each through the CLI (`sonarsentinel detect`) and through `run_pipeline`.
Writes a JSON and a Markdown table with status, warnings, flags, detections and schema validity.

    python scripts/robustness_suite.py --out robustness.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from importlib import resources
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

N_PINGS = 1400
TARGETS = [(250, "starboard", 400), (640, "port", 500), (1100, "starboard", 700)]

VARIANTS: dict[str, dict[str, Any]] = {
    "clean": {},
    "ac06_dropout10_truncated": {"dropout_fraction": 0.10, "truncate": True},
    "gps_gap_30s": {"gps_gap_s": 30.0},
    "roll_10deg": {"roll_deg_amplitude": 10.0},
    "no_altitude": {"write_altitude": False},
    "heavy_speckle": {"speckle_sigma": 0.8},
    "truncated": {"truncate": True},
    "corrupt_header": {"corrupt_header": True},
}

TABLE_COLUMNS = (
    "Variant",
    "Status",
    "Schema valid",
    "CLI exit",
    "Warnings",
    "Ranged warning events",
    "Flags",
    "Detections",
)


def make_variant(folder: Path, name: str, spec: dict[str, Any]) -> Path:
    from tools.make_synthetic_xtf import corrupt_header, truncate, write_synthetic_xtf

    faults = {k: v for k, v in spec.items() if k not in ("truncate", "corrupt_header")}
    raw = folder / f"{name}_raw.xtf"
    write_synthetic_xtf(
        raw,
        n_pings=N_PINGS,
        samples_per_side=1000,
        step_m=0.1,
        targets=TARGETS,
        target_extent=(12, 30),
        **faults,
    )
    path = folder / f"{name}.xtf"
    if spec.get("truncate"):
        truncate(raw, path, drop_bytes=1500)
    elif spec.get("corrupt_header"):
        corrupt_header(raw, path)
    else:
        raw.replace(path)
    return path


def summarize_report(report: dict[str, Any], events: list[dict[str, Any]] | None) -> dict[str, Any]:
    flags = Counter(f for d in report["detections"] for f in d["quality_flags"])
    ranged = [e for e in events or [] if e["type"] == "warning" and "ping_start" in e]
    return {
        "warnings": report["processing"]["quality"]["warnings"],
        "ranged_warning_events": len(ranged),
        "flags": dict(sorted(flags.items())),
        "detections": report["summary"]["total_detections"],
        "dropout_pings": report["processing"]["quality"].get("dropout_pings"),
        "high_motion_pings": report["processing"]["quality"].get("high_motion_pings"),
    }


def table_row(row: dict[str, Any]) -> str:
    status = row["status"] + (f" ({row['error_code']})" if row.get("error_code") else "")
    flags = ", ".join(f"{k} {v}" for k, v in row.get("flags", {}).items()) or "—"
    cells = [
        row["variant"],
        status,
        row.get("schema_valid", "—"),
        row["cli_exit"],
        ", ".join(row.get("warnings", [])) or "—",
        row.get("ranged_warning_events", "—"),
        flags,
        row.get("detections", "—"),
    ]
    return "| " + " | ".join(str(c) for c in cells) + " |"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--detector", default="classical", choices=["classical", "auto", "yolo"])
    parser.add_argument("--out", type=Path, default=Path("robustness.json"))
    args = parser.parse_args()

    import jsonschema
    from sonarsentinel.cli import app, build_detector
    from sonarsentinel.config import load_config
    from sonarsentinel.errors import SonarSentinelError
    from sonarsentinel.pipeline import run_pipeline
    from typer.testing import CliRunner

    schema = json.loads(
        resources.files("sonarsentinel.report")
        .joinpath("schema", "report-1.0.schema.json")
        .read_text("utf-8")
    )
    validator = jsonschema.Draft202012Validator(schema)
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 700, "overlap_pings": 150}
    runner = CliRunner()
    rows: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="ss_rob_") as tmp:
        folder = Path(tmp)
        for name, spec in VARIANTS.items():
            path = make_variant(folder, name, spec)
            row: dict[str, Any] = {"variant": name}

            out = folder / f"out_{name}"
            cli = runner.invoke(
                app,
                ["detect", str(path), "--out", str(out), "--quiet", "--detector", args.detector],
            )
            reports = list(out.glob("*/report.json"))
            row["cli_exit"] = cli.exit_code
            if reports:
                cli_report = json.loads(reports[0].read_text("utf-8"))
                row["cli_schema_valid"] = validator.is_valid(cli_report)
            else:
                row["cli_schema_valid"] = None
                row["cli_error"] = cli.output.strip().splitlines()[-1] if cli.output.strip() else ""

            events: list[dict[str, Any]] = []
            try:
                report = run_pipeline(
                    path,
                    config=cfg,
                    detector=build_detector(args.detector, None, cfg),
                    on_event=events.append,
                )
            except SonarSentinelError as exc:
                row |= {"status": "failed", "error_code": exc.code}
            else:
                done = next(e for e in reversed(events) if e["type"] == "done")
                row |= {"status": done["status"], "schema_valid": validator.is_valid(report)}
                row |= summarize_report(report, events)
            rows.append(row)
            print(json.dumps(row))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"detector": args.detector, "variants": rows}
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "| " + " | ".join(TABLE_COLUMNS) + " |",
        "|" + "---|" * len(TABLE_COLUMNS),
        *(table_row(r) for r in rows),
    ]
    args.out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} and {args.out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
