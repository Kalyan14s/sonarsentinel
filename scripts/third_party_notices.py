"""Generate THIRD_PARTY_NOTICES.md (licence compliance checklist §5).

Python: the runtime dependency closure of the backend (``geo`` and ``api`` extras) plus the ML
stack in ``backend/requirements-ml.txt`` and PyTorch, read from the installed distributions with
``importlib.metadata``. npm: the dashboard's production dependencies (direct and transitive) from
``frontend/package-lock.json``. Data: the dataset register in ``ml/datasets/LICENSES.md``.
Licences that are not clearly permissive or compatible with the project's AGPL-3.0 are flagged
for review.

    python scripts/third_party_notices.py          # writes THIRD_PARTY_NOTICES.md
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "THIRD_PARTY_NOTICES.md"
CHECKLIST = "docs/legal/LICENSES_AND_COMPLIANCE.md#5-compliance-checklist-each-release"

# Tokens of licences that are permissive or compatible with distributing under AGPL-3.0.
COMPATIBLE = (
    "MIT",
    "BSD",
    "APACHE",
    "ISC",
    "PSF",
    "PYTHON SOFTWARE FOUNDATION",
    "UNLICENSE",
    "ZLIB",
    "HPND",
    "CC0",
    "MPL",
    "LGPL",
    "AGPL",
    "GPL-3",
    "GPLV3",
    "GNU GENERAL PUBLIC LICENSE V3",
    "0BSD",
    "BLUEOAK",
    "PUBLIC DOMAIN",
)
REVIEW = ("GPL-2.0-ONLY", "GPLV2 ONLY", "NON-COMMERCIAL", "NC-", "PROPRIETARY", "COMMERCIAL")


def python_roots() -> list[Requirement]:
    project = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text("utf-8"))["project"]
    lines = list(project.get("dependencies", []))
    for extra in ("geo", "api"):
        lines += project.get("optional-dependencies", {}).get(extra, [])
    for raw in (ROOT / "backend" / "requirements-ml.txt").read_text("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            lines.append(line)
    lines += ["torch", "torchvision"]
    return [Requirement(line) for line in lines]


def licence_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    field = (meta.get("License") or "").strip()
    if field and len(field) <= 60 and "\n" not in field and field.upper() != "UNKNOWN":
        return field
    if classifiers:
        return "; ".join(sorted(set(classifiers)))
    return field.splitlines()[0][:60] if field else "UNKNOWN"


def url_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    if meta.get("Home-page"):
        return str(meta["Home-page"])
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return url.strip()
    entries = meta.get_all("Project-URL") or []
    return entries[0].partition(",")[2].strip() if entries else ""


def status_of(licence: str) -> str:
    text = licence.upper()
    if any(token in text for token in REVIEW):
        return "review"
    return "ok" if any(token in text for token in COMPATIBLE) else "review"


def python_closure() -> list[tuple[str, str, str, str, str]]:
    seen: dict[str, tuple[str, str, str, str, str]] = {}
    queue: list[tuple[Requirement, frozenset[str]]] = [
        (r, frozenset(r.extras)) for r in python_roots()
    ]
    while queue:
        requirement, extras = queue.pop()
        key = canonicalize_name(requirement.name)
        try:
            dist = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            if key not in seen:
                seen[key] = (requirement.name, "not installed", "", "", "review")
            continue
        if key in seen and not extras:
            continue
        licence = licence_of(dist)
        seen[key] = (dist.metadata["Name"], dist.version, licence, url_of(dist), status_of(licence))
        for raw in dist.requires or []:
            try:
                child = Requirement(raw)
            except InvalidRequirement:
                continue
            environments = [{"extra": e} for e in extras] or [{"extra": ""}]
            if child.marker and not any(child.marker.evaluate(env) for env in environments):
                continue
            if canonicalize_name(child.name) not in seen:
                queue.append((child, frozenset(child.extras)))
    return sorted(seen.values(), key=lambda row: row[0].lower())


def npm_packages() -> list[tuple[str, str, str, str, str]]:
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text("utf-8"))
    rows = []
    for path, info in lock.get("packages", {}).items():
        if not path or info.get("dev") or info.get("devOptional"):
            continue
        name = path.split("node_modules/")[-1]
        licence = str(info.get("license") or "UNKNOWN")
        url = f"https://www.npmjs.com/package/{name}"
        rows.append((name, str(info.get("version", "")), licence, url, status_of(licence)))
    return sorted(set(rows), key=lambda row: row[0].lower())


def dataset_rows() -> list[str]:
    text = (ROOT / "ml" / "datasets" / "LICENSES.md").read_text("utf-8")
    rows = []
    for line in text.splitlines():
        if re.match(r"^\| D\d", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            attribution = cells[-1] if len(cells) >= 8 else ""
            row = f"| {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {attribution} |"
            rows.append(_rebase_links(row))
    return rows


def _rebase_links(markdown: str) -> str:
    """Rewrite links relative to ``ml/datasets/`` so they work from the repository root."""
    markdown = re.sub(r"\]\(\.\./\.\./", "](", markdown)
    markdown = re.sub(r"\]\(\.\./", "](ml/", markdown)
    return re.sub(r"\]\((?!https?:|#|/|ml/|docs/)([^)]+)\)", r"](ml/datasets/\1)", markdown)


def table(rows: list[tuple[str, str, str, str, str]]) -> list[str]:
    out = ["| Package | Version | Licence | Status | Source |", "|---|---|---|---|---|"]
    for name, version, licence, url, status in rows:
        mark = "ok" if status == "ok" else "**review**"
        link = f"<{url}>" if url else ""
        out.append(f"| {name} | {version} | {licence.replace('|', '/')} | {mark} | {link} |")
    return out


def main() -> None:
    python_rows = python_closure()
    npm_rows = npm_packages()
    flagged = [r for r in python_rows + npm_rows if r[4] != "ok"]
    lines = [
        "# Third-Party Notices",
        "",
        "SonarSentinel is licensed under AGPL-3.0 ([LICENSE](LICENSE)). It uses the third-party "
        "software and data below; their licences and notices apply to those components. "
        "Generated by `scripts/third_party_notices.py` from the installed development environment "
        f"on {datetime.now(UTC).strftime('%Y-%m-%d')} — regenerate before each release "
        f"([Licences & Compliance §5]({CHECKLIST})).",
        "",
        f"**Summary:** {len(python_rows)} Python packages, {len(npm_rows)} npm packages; "
        f"{len(flagged)} flagged for licence review.",
        "",
        "## Flagged for review",
        "",
    ]
    if flagged:
        lines += table(flagged)
    else:
        lines.append("None.")
    lines += [
        "",
        "## Python packages (backend runtime and ML stack)",
        "",
        *table(python_rows),
        "",
        "## npm packages (dashboard production bundle)",
        "",
        *table(npm_rows),
        "",
        "## Datasets and model training sources",
        "",
        "Full register and attribution text: [ml/datasets/LICENSES.md](ml/datasets/LICENSES.md). "
        "Trained models inherit the most restrictive terms of their training sources.",
        "",
        "| ID | Dataset | Licence / terms | Status | Required attribution |",
        "|---|---|---|---|---|",
        *dataset_rows(),
        "",
        "## Other components",
        "",
        "- **GDAL** (bundled in the rasterio wheels, MIT/X) and **PROJ** (bundled in pyproj, MIT).",
        "- **OpenStreetMap** map data © OpenStreetMap contributors, ODbL 1.0; tiles are shown with "
        "attribution in the dashboard. Offline tiles must be rendered by the team, not bulk "
        "downloaded from the OSM tile servers.",
        "- **Ultralytics YOLO11** (AGPL-3.0) and the COCO-pretrained weights `yolo11s-seg.pt`.",
        "- NOAA-derived data: *Not to be used for navigation.*",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"wrote {OUTPUT.name}: {len(python_rows)} Python, {len(npm_rows)} npm, "
        f"{len(flagged)} flagged"
    )
    for name, version, licence, _, _ in flagged:
        print(f"  review: {name} {version} [{licence}]")
    sys.exit(0)


if __name__ == "__main__":
    main()
