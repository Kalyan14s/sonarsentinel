"""ST-015: site-grouped train/val/calib/test splits, dataset manifest, leakage check, stats report.

Policy (docs/data/DATA_MANAGEMENT_PLAN.md §5): every site (dataset + survey group) lives in exactly
one split; targets are train 70% · val 10% · calib 5% · test 15% of images; synthetic tiles go to
train only, and the synthetic holdout stays a separate split. A leakage check fails the build if a
site appears in two splits or if near-duplicate images (64 × 64 thumbnail correlation of at least
``--min-correlation``)
cross splits. The test split's hash is recorded so it can be frozen.

Outputs: ``data/processed/sonar-seg/{images,labels}/<split>/``,
``data/manifests/sonar-seg-<v>.json``, ``data/manifests/sonar-seg-<v>.stats.md`` and
``ml/datasets/sonar-seg.yaml``.

    python ml/datasets/make_splits.py --real data/interim/mine_sss \
        --synthetic data/synthetic/ghost_net/1.0.0 --version 0.1.0
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from yolo_seg import CLASS_IDS

SPLITS = ("train", "val", "calib", "test")
TARGETS = {"train": 0.70, "val": 0.10, "calib": 0.05, "test": 0.15}
NAMES = {v: k for k, v in CLASS_IDS.items()}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}


class LeakageError(RuntimeError):
    """A site or near-duplicate image appears in more than one split."""


@dataclass
class Item:
    image: Path
    label: Path
    dataset: str
    site: str
    objects: Counter[str] = field(default_factory=Counter)
    box_sizes: list[tuple[float, float]] = field(default_factory=list)
    split: str = ""


def read_label(path: Path) -> tuple[Counter[str], list[tuple[float, float]]]:
    """Class counts and normalised polygon bounding-box sizes from a YOLO-seg label file."""
    counts: Counter[str] = Counter()
    sizes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        counts[NAMES[int(parts[0])]] += 1
        xs = [float(v) for v in parts[1::2]]
        ys = [float(v) for v in parts[2::2]]
        sizes.append((max(xs) - min(xs), max(ys) - min(ys)))
    return counts, sizes


def collect(root: Path, dataset: str, site_from: str = "parent") -> list[Item]:
    """Pair ``images/**`` with ``labels/**``; site = ``dataset:<image parent folder>``."""
    items = []
    for image in sorted((root / "images").rglob("*")):
        if image.suffix.lower() not in IMAGE_EXT:
            continue
        rel = image.relative_to(root / "images")
        label = (root / "labels" / rel).with_suffix(".txt")
        if not label.exists():
            continue
        counts, sizes = read_label(label)
        group = rel.parts[0] if site_from == "parent" and len(rel.parts) > 1 else "all"
        items.append(Item(image, label, dataset, f"{dataset}:{group}", counts, sizes))
    return items


def assign_sites(
    site_sizes: dict[str, int],
    site_positives: dict[str, int],
    targets: dict[str, float] = TARGETS,
    not_train: set[str] | None = None,
) -> dict[str, str]:
    """Assign whole sites to splits, closest to the target fractions.

    Exhaustive search for up to 9 sites (every split non-empty, penalty when val or test has no
    positive objects); greedy largest-deficit assignment beyond that. Sites in ``not_train``
    (e.g. backgrounds of the synthetic holdout) are never put in train.
    """
    blocked = not_train or set()
    sites = sorted(site_sizes, key=lambda s: -site_sizes[s])
    total = sum(site_sizes.values())
    splits = list(targets)
    if len(sites) < len(splits):
        raise ValueError(f"Need at least {len(splits)} sites for grouped splits, got {len(sites)}")

    def cost(assignment: tuple[str, ...]) -> float:
        amount = Counter()
        positives = Counter()
        for site, split in zip(sites, assignment, strict=True):
            if split == "train" and site in blocked:
                return math_inf
            amount[split] += site_sizes[site]
            positives[split] += site_positives.get(site, 0)
        if any(amount[s] == 0 for s in splits):
            return math_inf
        value = sum((amount[s] / total - targets[s]) ** 2 for s in splits)
        return value + sum(1.0 for s in ("val", "test") if positives[s] == 0)

    if len(sites) <= 9:
        best = min(itertools.product(splits, repeat=len(sites)), key=cost)
        return dict(zip(sites, best, strict=True))
    amount = Counter()
    result = {}
    for i, site in enumerate(sites):
        allowed = [s for s in splits if not (s == "train" and site in blocked)]
        split = (
            splits[i]
            if i < len(splits) and splits[i] in allowed
            else max(allowed, key=lambda s: targets[s] - amount[s] / total)
        )
        result[site] = split
        amount[split] += site_sizes[site]
    return result


math_inf = float("inf")


def thumbnail(path: Path, size: int = 64) -> np.ndarray:
    """Grayscale ``size`` × ``size`` thumbnail, zero mean and unit variance, flattened."""
    import cv2

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    small = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    small -= small.mean()
    return (small / (small.std() + 1e-6)).ravel()


def cross_split_duplicates(
    items: list[Item], min_correlation: float = 0.97
) -> list[tuple[str, str, float]]:
    """Image pairs in different splits whose 64 × 64 thumbnails correlate ≥ ``min_correlation``.

    Perceptual hashes (dHash) don't work on side-scan waterfalls: every image shares the nadir
    layout, so unrelated images from different surveys hash within a few bits. On the mine-SSS
    set the highest cross-survey thumbnail correlation is 0.93, while re-encoded copies are ≈ 1.0.
    """
    vectors = np.stack([thumbnail(it.image) for it in items])
    split_ids = np.array([SPLITS.index(it.split) if it.split in SPLITS else -1 for it in items])
    found = []
    for i in range(len(items)):
        corr = vectors[i + 1 :] @ vectors[i] / vectors.shape[1]
        hits = (corr >= min_correlation) & (split_ids[i + 1 :] != split_ids[i])
        for j in np.flatnonzero(hits):
            k = i + 1 + int(j)
            pair = (items[i].image.as_posix(), items[k].image.as_posix(), round(float(corr[j]), 4))
            found.append(pair)
    return found


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(
    real_roots: list[Path],
    synthetic_root: Path | None,
    out: Path,
    manifests: Path,
    version: str,
    min_correlation: float = 0.97,
    link: bool = True,
    not_train: tuple[str, ...] = (),
) -> dict[str, Any]:
    real: list[Item] = []
    for root in real_roots:
        real += collect(root, root.name)
    sizes = Counter(it.site for it in real)
    positives = Counter()
    for it in real:
        positives[it.site] += sum(it.objects.values())
    assignment = assign_sites(dict(sizes), dict(positives), not_train=set(not_train))
    for it in real:
        it.split = assignment[it.site]

    site_splits = defaultdict(set)
    for it in real:
        site_splits[it.site].add(it.split)
    overlap = sorted(s for s, v in site_splits.items() if len(v) > 1)
    duplicates = cross_split_duplicates(real, min_correlation)
    leakage = {
        "site_overlap": overlap,
        "near_duplicates": duplicates,
        "min_correlation": min_correlation,
    }
    if overlap or duplicates:
        raise LeakageError(json.dumps(leakage, indent=2)[:2000])

    synthetic: list[Item] = []
    if synthetic_root is not None:
        for split_dir, split in (("train", "train"), ("holdout", "synthetic_holdout")):
            if (synthetic_root / split_dir).exists():
                dataset = f"synthetic_{synthetic_root.parent.name}"
                for it in collect(synthetic_root / split_dir, dataset, site_from="none"):
                    it.split = split
                    it.site = f"{it.dataset}:{split}"
                    synthetic.append(it)

    files = []
    for it in real + synthetic:
        name = f"{it.dataset}_{it.site.split(':')[-1]}_{it.image.stem}"
        for kind, src, suffix in (
            ("images", it.image, it.image.suffix),
            ("labels", it.label, ".txt"),
        ):
            dst = out / kind / it.split / f"{name}{suffix}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                try:
                    if not link:
                        raise OSError
                    dst.hardlink_to(src)
                except OSError:
                    shutil.copy2(src, dst)
        files.append(
            {
                "image": f"images/{it.split}/{name}{it.image.suffix}",
                "label": f"labels/{it.split}/{name}.txt",
                "sha256": sha256(it.image),
                "split": it.split,
                "site": it.site,
                "dataset": it.dataset,
                "objects": dict(it.objects),
            }
        )

    splits: dict[str, Any] = {}
    for split in sorted({f["split"] for f in files}):
        subset = [f for f in files if f["split"] == split]
        objects: Counter[str] = Counter()
        for f in subset:
            objects.update(f["objects"])
        digest = hashlib.sha256("".join(sorted(f["sha256"] for f in subset)).encode()).hexdigest()
        splits[split] = {
            "sites": sorted({f["site"] for f in subset}),
            "images": len(subset),
            "objects": dict(objects),
            "hash": f"sha256:{digest}",
        }
    manifest = {
        "name": "sonar-seg",
        "version": version,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classes": {str(v): k for k, v in CLASS_IDS.items()},
        "policy": {"targets": TARGETS, "grouping": "site = dataset:survey group"},
        "splits": splits,
        "test_hash_frozen": splits.get("test", {}).get("hash"),
        "leakage_check": leakage | {"passed": True},
        "files": files,
    }
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / f"sonar-seg-{version}.json").write_text(json.dumps(manifest, indent=1), "utf-8")
    (manifests / f"sonar-seg-{version}.stats.md").write_text(
        stats_report(manifest, real + synthetic), "utf-8"
    )
    return manifest


def stats_report(manifest: dict[str, Any], items: list[Item]) -> str:
    lines = [
        f"# sonar-seg {manifest['version']} — dataset statistics",
        "",
        f"Generated {manifest['created_utc']} by `ml/datasets/make_splits.py`.",
        "",
        "## Images and objects per split",
        "",
        "| Split | Sites | Images | " + " | ".join(CLASS_IDS) + " |",
        "|---|---|---|" + "---|" * len(CLASS_IDS),
    ]
    for split, info in manifest["splits"].items():
        counts = " | ".join(str(info["objects"].get(c, 0)) for c in CLASS_IDS)
        lines.append(f"| {split} | {len(info['sites'])} | {info['images']} | {counts} |")
    lines += ["", "## Per site", "", "| Site | Split | Images | Objects |", "|---|---|---|---|"]
    per_site: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        per_site[it.site].append(it)
    for site, group in sorted(per_site.items()):
        objs = sum(sum(it.objects.values()) for it in group)
        lines.append(f"| {site} | {group[0].split} | {len(group)} | {objs} |")
    lines += [
        "",
        "## Object sizes (fraction of image side, polygon bounding box)",
        "",
        "| Class | n | median width | median height | p90 longest side |",
        "|---|---|---|---|---|",
    ]
    by_class: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for it in items:
        classes = [c for c, n in it.objects.items() for _ in range(n)]
        for cls, size in zip(classes, it.box_sizes, strict=False):
            by_class[cls].append(size)
    for cls, sizes in sorted(by_class.items()):
        arr = np.array(sizes)
        width, height = np.median(arr[:, 0]), np.median(arr[:, 1])
        longest = np.percentile(arr.max(axis=1), 90)
        lines.append(f"| {cls} | {len(arr)} | {width:.3f} | {height:.3f} | {longest:.3f} |")
    lines += [
        "",
        "## Leakage check",
        "",
        f"Passed: no site in more than one split; no cross-split image pairs at or above "
        f"thumbnail correlation {manifest['leakage_check']['min_correlation']}.",
        "",
        f"Test split hash (frozen): `{manifest['test_hash_frozen']}`",
        "",
    ]
    return "\n".join(lines)


def write_yaml(path: Path, data_root: Path) -> None:
    names = "\n".join(f"  {v}: {k}" for k, v in CLASS_IDS.items())
    path.write_text(
        f"# Ultralytics dataset config, generated by make_splits.py\npath: {data_root.as_posix()}\n"
        f"train: images/train\nval: images/val\ntest: images/test\nnames:\n{names}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--real", type=Path, nargs="+", default=[Path("data/interim/mine_sss")])
    parser.add_argument("--synthetic", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("data/processed/sonar-seg"))
    parser.add_argument("--manifests", type=Path, default=Path("data/manifests"))
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--min-correlation", type=float, default=0.97)
    parser.add_argument(
        "--not-train",
        nargs="*",
        default=["mine_sss:2017"],
        help="Sites kept out of train, e.g. backgrounds of the synthetic holdout",
    )
    args = parser.parse_args()
    manifest = build(
        args.real,
        args.synthetic,
        args.out,
        args.manifests,
        args.version,
        args.min_correlation,
        not_train=tuple(args.not_train),
    )
    write_yaml(Path(__file__).with_name("sonar-seg.yaml"), args.out)
    print(json.dumps(manifest["splits"], indent=2))


if __name__ == "__main__":
    main()
