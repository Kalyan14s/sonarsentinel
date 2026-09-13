"""ST-016: synthetic ghost-net generator v1 (docs/architecture/03-ml-models.md §4).

Pipeline per tile: regular mesh → elastic crumple → irregular clump envelope → optional ropes and
floats → partial burial → acoustic render (weak highlight × Rayleigh speckle) → shadow cast to the
far-range side (length ``h·r/(H − h)``) → blend onto a real object-free seafloor crop. Each tile
gets a PNG, a binary mask, a YOLO-seg label (class 3 ``ghost_net``) and ``*.params.json`` with the
generator version, seed and every parameter.

Backgrounds are object-free mine-SSS images (``convert_mine_sss.py`` output, empty label files)
grouped by survey year. Groups passed with ``--holdout-groups`` are used **only** for the
holdout set (docs/data/DATA_MANAGEMENT_PLAN.md §5), never for training tiles.

**Assumption:** the pixel size of the background images isn't published; ``--res-m`` (default
0.10 m, the pipeline ground resolution) converts metres to pixels and is stored per tile.

    python ml/synth/ghost_net_generator.py --backgrounds data/interim/mine_sss \
        --out data/synthetic/ghost_net --count 2000 --holdout-count 200 --holdout-groups 2017
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "datasets"))
from yolo_seg import CLASS_IDS, format_polygon, mask_to_polygons  # noqa: E402

GENERATOR_VERSION = "1.0.0"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@dataclass
class NetParams:
    """All random choices for one tile (saved as ``*.params.json``)."""

    seed: int
    tile_px: int
    res_m: float
    background: str
    background_group: str
    crop_xy: tuple[int, int]
    side: str
    center_xy: tuple[int, int]
    mesh_cm: float
    crumple_px: float
    clump_length_m: float
    clump_width_m: float
    clump_angle_deg: float
    reflectivity: float
    burial_fraction: float
    height_m: float
    altitude_m: float
    ground_range_m: float
    shadow_length_px: int
    shadow_factor: float
    n_ropes: int
    n_floats: int
    generator_version: str = GENERATOR_VERSION


def find_backgrounds(interim: Path) -> list[tuple[Path, str]]:
    """Object-free images from ``convert_mine_sss.py`` output: ``(image, group)``."""
    found = []
    for image in sorted((interim / "images").rglob("*")):
        if image.suffix.lower() not in IMAGE_EXT:
            continue
        group = image.parent.name
        label = interim / "labels" / group / f"{image.stem}.txt"
        if label.exists() and not label.read_text(encoding="utf-8").strip():
            found.append((image, group))
    return found


def _smooth_noise(rng: np.random.Generator, shape: tuple[int, int], sigma: float) -> np.ndarray:
    import cv2

    noise = rng.standard_normal(shape).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), sigma)
    return (noise - noise.mean()) / (noise.std() + 1e-6)


def mesh_texture(
    rng: np.random.Generator, size: int, mesh_px: float, angle_deg: float
) -> np.ndarray:
    """Net mesh intensity in [0, 1]: grid lines when resolvable, fibrous texture otherwise."""
    import cv2

    if mesh_px >= 2.0:
        y, x = np.mgrid[0:size, 0:size].astype(np.float32)
        phase_x, phase_y = rng.uniform(0, mesh_px, 2)
        lines_x = ((x + phase_x) % mesh_px) < 1.2  # twine about one pixel wide
        lines_y = ((y + phase_y) % mesh_px) < 1.2
        grid = (lines_x | lines_y).astype(np.float32)
    else:
        grid = (rng.random((size, size)) < 0.35).astype(np.float32)
        grid = cv2.GaussianBlur(grid, (0, 0), 0.7)
        grid /= max(float(grid.max()), 1e-6)
    rotation = cv2.getRotationMatrix2D((size / 2, size / 2), angle_deg, 1.0)
    return cv2.warpAffine(
        grid.astype(np.float32), rotation, (size, size), borderMode=cv2.BORDER_WRAP
    )


def crumple(rng: np.random.Generator, image: np.ndarray, amplitude_px: float) -> np.ndarray:
    """Elastic distortion with smooth random displacement fields."""
    import cv2

    h, w = image.shape
    dx = _smooth_noise(rng, (h, w), 8.0) * amplitude_px
    dy = _smooth_noise(rng, (h, w), 8.0) * amplitude_px
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return cv2.remap(image, x + dx, y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def clump_envelope(
    rng: np.random.Generator,
    size: int,
    center: tuple[int, int],
    length_px: float,
    width_px: float,
    angle_deg: float,
) -> np.ndarray:
    """Irregular blob: a rotated ellipse with a noisy boundary."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    a = math.radians(angle_deg)
    u = (x - center[0]) * math.cos(a) + (y - center[1]) * math.sin(a)
    v = -(x - center[0]) * math.sin(a) + (y - center[1]) * math.cos(a)
    radius = np.sqrt((u / max(length_px / 2, 1)) ** 2 + (v / max(width_px / 2, 1)) ** 2)
    wobble = _smooth_noise(rng, (size, size), max(3.0, min(length_px, width_px) / 4)) * 0.25
    return (radius + wobble) < 1.0


def add_ropes_and_floats(
    rng: np.random.Generator, envelope: np.ndarray, n_ropes: int, n_floats: int
) -> tuple[np.ndarray, np.ndarray]:
    """Wavy rope lines through the clump and small floats near it (float32 masks in [0, 1])."""
    import cv2

    size = envelope.shape[0]
    ropes = np.zeros(envelope.shape, np.float32)
    floats = np.zeros(envelope.shape, np.float32)
    ys, xs = np.nonzero(envelope)
    if len(xs) == 0:
        return ropes, floats
    for _ in range(n_ropes):
        i = rng.integers(len(xs))
        angle = rng.uniform(0, math.pi)
        length = rng.uniform(0.3, 1.2) * max(np.ptp(xs), np.ptp(ys), 20)
        t = np.linspace(-0.5, 0.5, 40)
        wave = np.sin(t * rng.uniform(3, 9) + rng.uniform(0, 6)) * rng.uniform(2, 8)
        px = xs[i] + t * length * math.cos(angle) - wave * math.sin(angle)
        py = ys[i] + t * length * math.sin(angle) + wave * math.cos(angle)
        points = np.stack([px, py], axis=1).clip(0, size - 1).astype(np.int32)
        cv2.polylines(ropes, [points], False, 1.0, int(rng.integers(1, 3)))
    for _ in range(n_floats):
        i = rng.integers(len(xs))
        cv2.circle(floats, (int(xs[i]), int(ys[i])), int(rng.integers(2, 5)), 1.0, -1)
    return ropes, floats


def cast_shadow(obj: np.ndarray, length_px: int, direction: int) -> np.ndarray:
    """Pixels within ``length_px`` of the object on the far-range side (+1 right, -1 left)."""
    shadow = np.zeros_like(obj, dtype=bool)
    if length_px <= 0:
        return shadow
    for step in range(1, length_px + 1):
        if direction > 0:
            shadow[:, step:] |= obj[:, :-step]
        else:
            shadow[:, :-step] |= obj[:, step:]
    return shadow & ~obj


def sample_params(
    rng: np.random.Generator,
    tile_px: int,
    res_m: float,
    background: Path,
    group: str,
    image_shape: tuple[int, int],
    seed: int,
) -> NetParams:
    h, w = image_shape
    crop_x = int(rng.integers(0, max(w - tile_px, 0) + 1))
    crop_y = int(rng.integers(0, max(h - tile_px, 0) + 1))
    length_m = float(rng.uniform(1.0, min(15.0, 0.6 * tile_px * res_m)))
    width_m = float(rng.uniform(0.3, 1.0) * length_m)
    margin = int(length_m / res_m / 2) + 8
    cx = int(rng.integers(margin, max(margin + 1, tile_px - margin)))
    cy = int(rng.integers(margin, max(margin + 1, tile_px - margin)))
    side = "starboard" if crop_x + cx >= w / 2 else "port"  # nadir at the image centre
    altitude = float(rng.uniform(5.0, 20.0))
    height = float(rng.uniform(0.0, 1.5))
    ground_range = float(max(abs(crop_x + cx - w / 2) * res_m, 5.0))
    shadow_px = int(round(height * ground_range / max(altitude - height, 0.5) / res_m))
    return NetParams(
        seed=seed,
        tile_px=tile_px,
        res_m=res_m,
        background=background.as_posix(),
        background_group=group,
        crop_xy=(crop_x, crop_y),
        side=side,
        center_xy=(cx, cy),
        mesh_cm=float(rng.uniform(5.0, 30.0)),
        crumple_px=float(rng.uniform(6.0, 15.0)),
        clump_length_m=length_m,
        clump_width_m=width_m,
        clump_angle_deg=float(rng.uniform(0, 180)),
        reflectivity=float(rng.uniform(30, 120)),
        burial_fraction=float(rng.uniform(0.0, 0.6)),
        height_m=height,
        altitude_m=altitude,
        ground_range_m=ground_range,
        shadow_length_px=min(shadow_px, tile_px // 3),
        shadow_factor=float(rng.uniform(0.25, 0.6)),
        n_ropes=int(rng.integers(0, 4)),
        n_floats=int(rng.integers(0, 6)),
    )


def render_tile(background: np.ndarray, p: NetParams) -> tuple[np.ndarray, np.ndarray]:
    """Render one synthetic tile; returns ``(image uint8, label mask bool)``."""
    rng = np.random.default_rng(p.seed + 1)
    size = p.tile_px
    bg = np.zeros((size, size), np.float32)
    crop = background[p.crop_xy[1] : p.crop_xy[1] + size, p.crop_xy[0] : p.crop_xy[0] + size]
    bg[: crop.shape[0], : crop.shape[1]] = crop

    mesh = mesh_texture(rng, size, p.mesh_cm / 100.0 / p.res_m, p.clump_angle_deg)
    mesh = crumple(rng, mesh, p.crumple_px)
    envelope = clump_envelope(
        rng,
        size,
        p.center_xy,
        p.clump_length_m / p.res_m,
        p.clump_width_m / p.res_m,
        p.clump_angle_deg,
    )
    ropes, floats = add_ropes_and_floats(rng, envelope, p.n_ropes, p.n_floats)

    burial_noise = _smooth_noise(rng, (size, size), 6.0)
    inside = burial_noise[envelope]
    threshold = np.quantile(inside, p.burial_fraction) if inside.size else 0.0
    visible_net = envelope & (burial_noise >= threshold)

    speckle = rng.rayleigh(1.0 / math.sqrt(math.pi / 2), (size, size)).astype(np.float32)
    highlight = p.reflectivity * (0.4 + 0.6 * mesh) * visible_net
    highlight += 1.5 * p.reflectivity * ropes + 2.5 * p.reflectivity * floats
    highlight *= speckle

    obj = visible_net | (ropes > 0) | (floats > 0)
    shadow = cast_shadow(obj, p.shadow_length_px, +1 if p.side == "starboard" else -1)
    bg[shadow] *= p.shadow_factor
    image = np.clip(bg + highlight, 0, 255).astype(np.uint8)
    return image, obj


def generate(
    backgrounds: list[tuple[Path, str]],
    out: Path,
    count: int,
    *,
    seed: int = 0,
    tile_px: int = 640,
    res_m: float = 0.10,
    split: str = "train",
) -> dict[str, Any]:
    """Write ``count`` tiles under ``out/split``; returns a summary."""
    import cv2

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
        bg = cache[path]
        params = sample_params(rng, tile_px, res_m, path, group, bg.shape, tile_seed)
        image, mask = render_tile(bg, params)
        polygons = mask_to_polygons(mask, min_area_px=9)
        name = f"ghostnet_{split}_{i:05d}"
        cv2.imwrite(str(out / split / "images" / f"{name}.png"), image)
        cv2.imwrite(str(out / split / "masks" / f"{name}.png"), mask.astype(np.uint8) * 255)
        lines = [format_polygon(CLASS_IDS["ghost_net"], poly) for poly in polygons]
        (out / split / "labels" / f"{name}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        record = asdict(params) | {"mask_pixels": int(mask.sum()), "polygons": len(polygons)}
        (out / split / "params" / f"{name}.params.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        polygons_total += len(polygons)
    groups = sorted({g for _, g in backgrounds})
    return {"split": split, "tiles": count, "polygons": polygons_total, "background_groups": groups}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backgrounds", type=Path, default=Path("data/interim/mine_sss"))
    parser.add_argument(
        "--out", type=Path, default=Path(f"data/synthetic/ghost_net/{GENERATOR_VERSION}")
    )
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--holdout-count", type=int, default=200)
    parser.add_argument("--holdout-groups", nargs="*", default=["2017"])
    parser.add_argument("--tile-px", type=int, default=640)
    parser.add_argument("--res-m", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    all_backgrounds = find_backgrounds(args.backgrounds)
    holdout = [b for b in all_backgrounds if b[1] in set(args.holdout_groups)]
    train = [b for b in all_backgrounds if b[1] not in set(args.holdout_groups)]
    summaries = [
        generate(
            train,
            args.out,
            args.count,
            seed=args.seed,
            tile_px=args.tile_px,
            res_m=args.res_m,
            split="train",
        ),
    ]
    if args.holdout_count and holdout:
        summaries.append(
            generate(
                holdout,
                args.out,
                args.holdout_count,
                seed=args.seed + 1,
                tile_px=args.tile_px,
                res_m=args.res_m,
                split="holdout",
            )
        )
    (args.out / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
