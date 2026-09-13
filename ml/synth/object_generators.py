"""ST-017: synthetic pipe and cylinder generators (docs/architecture/03-ml-models.md §2).

Same approach and outputs as the ghost-net generator (backgrounds, far-range shadow, PNG + mask +
YOLO-seg label + ``*.params.json`` per tile):

- **pipe** (class 1): a long, slightly curved strip 0.2–1.5 m wide crossing much of the tile, with a
  bright specular line along it, buried sections (0–50%) and a shadow ∝ diameter.
- **cylinder** (class 2): a drum or barrel 0.6–3 m long and 0.4–1.0 m in diameter at a random
  orientation, bright near side with a specular stripe, shadow ∝ diameter.

    python ml/synth/object_generators.py --kind pipe --count 1000
    python ml/synth/object_generators.py --kind cylinder --count 1000
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "datasets"))
from ghost_net_generator import _smooth_noise, cast_shadow, find_backgrounds  # noqa: E402
from yolo_seg import CLASS_IDS, format_polygon, mask_to_polygons  # noqa: E402

GENERATOR_VERSION = "1.0.0"


@dataclass
class ObjectParams:
    kind: str
    seed: int
    tile_px: int
    res_m: float
    background: str
    background_group: str
    crop_xy: tuple[int, int]
    side: str
    center_xy: tuple[int, int]
    length_m: float
    diameter_m: float
    angle_deg: float
    curvature: float
    burial_fraction: float
    reflectivity: float
    altitude_m: float
    ground_range_m: float
    shadow_length_px: int
    shadow_factor: float
    generator_version: str = GENERATOR_VERSION


def sample_params(
    kind: str,
    rng: np.random.Generator,
    tile_px: int,
    res_m: float,
    background: Path,
    group: str,
    image_shape: tuple[int, int],
    seed: int,
) -> ObjectParams:
    h, w = image_shape
    crop_x = int(rng.integers(0, max(w - tile_px, 0) + 1))
    crop_y = int(rng.integers(0, max(h - tile_px, 0) + 1))
    if kind == "pipe":
        length = float(rng.uniform(0.6, 1.4) * tile_px * res_m)
        diameter = float(rng.uniform(0.2, 1.5))
        curvature = float(rng.uniform(-0.15, 0.15))
        burial = float(rng.uniform(0.0, 0.5))
        margin = 10
    else:
        length = float(rng.uniform(0.6, 3.0))
        diameter = float(rng.uniform(0.4, min(1.0, length)))
        curvature, burial = 0.0, float(rng.uniform(0.0, 0.3))
        margin = int(length / res_m) + 10
    cx = int(rng.integers(margin, max(margin + 1, tile_px - margin)))
    cy = int(rng.integers(margin, max(margin + 1, tile_px - margin)))
    side = "starboard" if crop_x + cx >= w / 2 else "port"
    altitude = float(rng.uniform(5.0, 20.0))
    ground_range = float(max(abs(crop_x + cx - w / 2) * res_m, 5.0))
    height = diameter * (0.5 if kind == "pipe" else 0.9)
    shadow = int(round(height * ground_range / max(altitude - height, 0.5) / res_m))
    return ObjectParams(
        kind=kind,
        seed=seed,
        tile_px=tile_px,
        res_m=res_m,
        background=background.as_posix(),
        background_group=group,
        crop_xy=(crop_x, crop_y),
        side=side,
        center_xy=(cx, cy),
        length_m=length,
        diameter_m=diameter,
        angle_deg=float(rng.uniform(0, 180)),
        curvature=curvature,
        burial_fraction=burial,
        reflectivity=float(rng.uniform(60, 160)),
        altitude_m=altitude,
        ground_range_m=ground_range,
        shadow_length_px=min(shadow, tile_px // 4),
        shadow_factor=float(rng.uniform(0.2, 0.5)),
    )


def _body(p: ObjectParams, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Object mask and a 0–1 cross-section profile (1 on the specular line)."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    a = math.radians(p.angle_deg)
    u = (x - p.center_xy[0]) * math.cos(a) + (y - p.center_xy[1]) * math.sin(a)  # along
    v = -(x - p.center_xy[0]) * math.sin(a) + (y - p.center_xy[1]) * math.cos(a)  # across
    half_len = p.length_m / p.res_m / 2
    v = v - p.curvature * (u**2) / max(half_len, 1.0)  # gentle bend for pipes
    radius = max(p.diameter_m / p.res_m / 2, 1.0)
    mask = (np.abs(u) <= half_len) & (np.abs(v) <= radius)
    profile = np.clip(1.0 - np.abs(v + 0.4 * radius) / radius, 0.0, 1.0)  # bright near-side stripe
    return mask, profile


def render(background: np.ndarray, p: ObjectParams) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(p.seed + 1)
    size = p.tile_px
    bg = np.zeros((size, size), np.float32)
    crop = background[p.crop_xy[1] : p.crop_xy[1] + size, p.crop_xy[0] : p.crop_xy[0] + size]
    bg[: crop.shape[0], : crop.shape[1]] = crop
    body, profile = _body(p, size)
    if p.burial_fraction > 0 and body.any():
        noise = _smooth_noise(rng, (size, size), 12.0)
        cut = np.quantile(noise[body], p.burial_fraction)
        visible = body & (noise >= cut)
    else:
        visible = body
    speckle = rng.rayleigh(1.0 / math.sqrt(math.pi / 2), (size, size)).astype(np.float32)
    highlight = p.reflectivity * (0.35 + 0.65 * profile) * visible * speckle
    shadow = cast_shadow(visible, p.shadow_length_px, +1 if p.side == "starboard" else -1)
    bg[shadow] *= p.shadow_factor
    return np.clip(bg + highlight, 0, 255).astype(np.uint8), visible


def generate(
    kind: str,
    backgrounds: list[tuple[Path, str]],
    out: Path,
    count: int,
    *,
    seed: int = 0,
    tile_px: int = 640,
    res_m: float = 0.10,
    split: str = "train",
) -> dict[str, Any]:
    import cv2

    if kind not in ("pipe", "cylinder"):
        raise ValueError(f"unknown kind {kind}")
    if not backgrounds:
        raise ValueError("No background images")
    for sub in ("images", "masks", "labels", "params"):
        (out / split / sub).mkdir(parents=True, exist_ok=True)
    master = np.random.default_rng(seed)
    cache: dict[Path, np.ndarray] = {}
    polygons_total = 0
    for i in range(count):
        tile_seed = int(master.integers(0, 2**31 - 1))
        rng = np.random.default_rng(tile_seed)
        path, group = backgrounds[int(rng.integers(len(backgrounds)))]
        if path not in cache:
            if len(cache) > 64:
                cache.clear()
            cache[path] = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        params = sample_params(kind, rng, tile_px, res_m, path, group, cache[path].shape, tile_seed)
        image, mask = render(cache[path], params)
        polygons = mask_to_polygons(mask, min_area_px=9, epsilon_px=1.5)
        name = f"{kind}_{split}_{i:05d}"
        cv2.imwrite(str(out / split / "images" / f"{name}.png"), image)
        cv2.imwrite(str(out / split / "masks" / f"{name}.png"), mask.astype(np.uint8) * 255)
        lines = [format_polygon(CLASS_IDS[kind], poly) for poly in polygons]
        (out / split / "labels" / f"{name}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), "utf-8"
        )
        record = asdict(params) | {"mask_pixels": int(mask.sum()), "polygons": len(polygons)}
        (out / split / "params" / f"{name}.params.json").write_text(
            json.dumps(record, indent=2), "utf-8"
        )
        polygons_total += len(polygons)
    return {"kind": kind, "split": split, "tiles": count, "polygons": polygons_total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", choices=["pipe", "cylinder"], required=True)
    parser.add_argument("--backgrounds", type=Path, default=Path("data/interim/mine_sss"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument(
        "--exclude-groups", nargs="*", default=["2017"], help="Holdout background sites"
    )
    parser.add_argument("--seed", type=int, default=2027)
    args = parser.parse_args()
    out = args.out or Path(f"data/synthetic/{args.kind}/{GENERATOR_VERSION}")
    backgrounds = [
        b for b in find_backgrounds(args.backgrounds) if b[1] not in set(args.exclude_groups)
    ]
    summary = generate(args.kind, backgrounds, out, args.count, seed=args.seed)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
