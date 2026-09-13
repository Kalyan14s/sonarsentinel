"""Detection chips with overlays (ST-073, ADR-017 §8).

Each detection gets a ``chip_size_px`` square PNG crop of the ground-range image in four
variants: ``mask`` (outline, the default chip), ``shadow`` (shadow search band), ``anomaly``
(PatchCore heatmap blend) and ``none``. Chips are written while the chunk image is in memory
under a temporary key and renamed to the final detection ID once IDs are assigned.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt

OVERLAYS = ("mask", "shadow", "anomaly", "none")
MASK_COLOUR = (0, 215, 255)  # BGR amber
SHADOW_COLOUR = (255, 200, 0)  # BGR cyan


def chip_filename(key: str, overlay: str) -> str:
    """``<key>.png`` for the mask overlay (the default chip), ``<key>_<overlay>.png`` otherwise."""
    return f"{key}.png" if overlay == "mask" else f"{key}_{overlay}.png"


def chip_url(detection_id: str) -> str:
    return f"/api/v1/detections/{detection_id}/chip.png"


def _window(
    box: tuple[int, int, int, int], shape: tuple[int, int], size_px: int
) -> tuple[int, int, int]:
    """Square crop ``(row0, col0, side)`` centred on the box, at least ``size_px`` wide."""
    x1, y1, x2, y2 = box
    side = int(max(size_px, 1.25 * (x2 - x1), 1.25 * (y2 - y1)))
    side = min(side, max(shape))
    row0 = int(np.clip((y1 + y2) // 2 - side // 2, 0, max(shape[0] - side, 0)))
    col0 = int(np.clip((x1 + x2) // 2 - side // 2, 0, max(shape[1] - side, 0)))
    return row0, col0, side


def render_chip(
    image: npt.NDArray[np.uint8],
    box: tuple[int, int, int, int],
    mask: npt.NDArray[np.bool_],
    *,
    overlay: str = "mask",
    size_px: int = 256,
    heat: npt.NDArray[np.float32] | None = None,
    heat_scale: float = 1.0,
    shadow_band: tuple[int, int, int, int] | None = None,
) -> npt.NDArray[np.uint8]:
    """BGR chip of shape ``(size_px, size_px, 3)``."""
    import cv2

    if overlay not in OVERLAYS:
        raise ValueError(f"Unknown overlay: {overlay}")
    x1, y1, x2, y2 = box
    row0, col0, side = _window(box, image.shape, size_px)
    crop = image[row0 : row0 + side, col0 : col0 + side]
    canvas = np.zeros((side, side), dtype=np.uint8)
    canvas[: crop.shape[0], : crop.shape[1]] = crop
    bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

    if overlay == "anomaly" and heat is not None:
        full = np.zeros((side, side), dtype=np.float32)
        part = heat[row0 : row0 + side, col0 : col0 + side]
        full[: part.shape[0], : part.shape[1]] = part
        level = np.clip(full / max(heat_scale, 1e-6) * 255.0, 0, 255).astype(np.uint8)
        colour = cv2.applyColorMap(level, cv2.COLORMAP_JET)
        weight = (level[..., None] > 0).astype(np.float32) * 0.45
        bgr = (bgr * (1.0 - weight) + colour * weight).astype(np.uint8)

    if overlay in ("mask", "shadow"):
        local = np.zeros((side, side), dtype=np.uint8)
        ly1, lx1 = y1 - row0, x1 - col0
        sub = mask[max(0, -ly1) :, max(0, -lx1) :].astype(np.uint8)
        ly1, lx1 = max(ly1, 0), max(lx1, 0)
        h = min(sub.shape[0], side - ly1)
        w = min(sub.shape[1], side - lx1)
        if h > 0 and w > 0:
            local[ly1 : ly1 + h, lx1 : lx1 + w] = sub[:h, :w]
        contours, _ = cv2.findContours(local, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(bgr, contours, -1, MASK_COLOUR, 1)
    if overlay == "shadow" and shadow_band is not None:
        bx1, by1, bx2, by2 = shadow_band
        cv2.rectangle(
            bgr, (bx1 - col0, by1 - row0), (bx2 - col0 - 1, by2 - row0 - 1), SHADOW_COLOUR, 1
        )

    if side != size_px:
        bgr = cv2.resize(bgr, (size_px, size_px), interpolation=cv2.INTER_AREA)
    return np.asarray(bgr, dtype=np.uint8)


def write_chips(
    out_dir: str | Path,
    key: str,
    image: npt.NDArray[np.uint8],
    box: tuple[int, int, int, int],
    mask: npt.NDArray[np.bool_],
    *,
    size_px: int = 256,
    heat: npt.NDArray[np.float32] | None = None,
    heat_scale: float = 1.0,
    shadow_band: tuple[int, int, int, int] | None = None,
) -> list[Path]:
    """Write all overlay variants under ``out_dir`` with the file stem ``key``."""
    import cv2

    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for overlay in OVERLAYS:
        chip = render_chip(
            image,
            box,
            mask,
            overlay=overlay,
            size_px=size_px,
            heat=heat,
            heat_scale=heat_scale,
            shadow_band=shadow_band,
        )
        path = folder / chip_filename(key, overlay)
        if not cv2.imwrite(str(path), chip):
            raise OSError(f"Could not write chip {path}")
        paths.append(path)
    return paths


def rename_chips(out_dir: str | Path, old_key: str, new_key: str) -> bool:
    """Move a detection's chips from ``old_key`` to ``new_key``; False if none exist."""
    folder = Path(out_dir)
    moved = False
    for overlay in OVERLAYS:
        source = folder / chip_filename(old_key, overlay)
        if source.exists():
            source.replace(folder / chip_filename(new_key, overlay))
            moved = True
    return moved


def remove_chips(out_dir: str | Path, key: str) -> None:
    folder = Path(out_dir)
    for overlay in OVERLAYS:
        (folder / chip_filename(key, overlay)).unlink(missing_ok=True)
