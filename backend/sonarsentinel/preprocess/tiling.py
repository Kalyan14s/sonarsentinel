"""Tiling with overlap and exact tile ↔ chunk coordinates (ST-046, stage S7).

Tiles are ``size`` × ``size`` squares stepping ``size × (1 − overlap)``; the last tile in each
direction is aligned to the image edge so the whole image is covered. Images smaller than a tile
give one tile padded with zeros. Tiles that are mostly masked (water column, dropouts) are skipped.
See ``docs/architecture/02-data-pipeline.md`` S7.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.errors import ValidationError


@dataclass(frozen=True)
class Tile:
    """A tile's position in its chunk image."""

    index: int
    row: int
    col: int
    size: int

    def to_chunk(self, y: int, x: int) -> tuple[int, int]:
        """Tile pixel ``(y, x)`` → chunk ``(row, col)``."""
        return self.row + y, self.col + x

    def from_chunk(self, row: int, col: int) -> tuple[int, int]:
        """Chunk ``(row, col)`` → tile pixel ``(y, x)``."""
        return row - self.row, col - self.col

    def contains(self, row: int, col: int) -> bool:
        return self.row <= row < self.row + self.size and self.col <= col < self.col + self.size


def tile_starts(length: int, size: int, overlap: float) -> list[int]:
    """Start offsets along one axis."""
    if size <= 0 or not 0 <= overlap < 1:
        raise ValidationError("Need size > 0 and 0 <= overlap < 1", size=size, overlap=overlap)
    if length <= size:
        return [0]
    step = max(1, round(size * (1 - overlap)))
    starts = list(range(0, length - size + 1, step))
    if starts[-1] + size < length:
        starts.append(length - size)
    return starts


def tile_grid(height: int, width: int, size: int = 640, overlap: float = 0.25) -> list[Tile]:
    """All tiles covering a ``height`` × ``width`` image, row by row."""
    return [
        Tile(i, r, c, size)
        for i, (r, c) in enumerate(
            (r, c)
            for r in tile_starts(height, size, overlap)
            for c in tile_starts(width, size, overlap)
        )
    ]


def extract_tile(image: npt.NDArray[Any], tile: Tile) -> npt.NDArray[Any]:
    """Cut a tile (any trailing channel axes kept), zero-padded where it extends past the image."""
    out = np.zeros((tile.size, tile.size, *image.shape[2:]), dtype=image.dtype)
    part = image[tile.row : tile.row + tile.size, tile.col : tile.col + tile.size]
    out[: part.shape[0], : part.shape[1]] = part
    return out


def iter_tiles(
    image: npt.NDArray[Any],
    *,
    mask: npt.NDArray[np.bool_] | None = None,
    size: int = 640,
    overlap: float = 0.25,
    skip_if_masked_fraction_gt: float = 0.8,
) -> Iterator[tuple[Tile, npt.NDArray[Any]]]:
    """Yield ``(tile, pixels)``, skipping tiles whose masked (or padded) fraction is too high."""
    height, width = image.shape[:2]
    for tile in tile_grid(height, width, size, overlap):
        if mask is not None:
            valid = ~extract_tile(np.asarray(mask, dtype=bool), tile)
            inside = np.zeros((tile.size, tile.size), dtype=bool)
            inside[: height - tile.row, : width - tile.col] = True
            if 1.0 - float((valid & inside).mean()) > skip_if_masked_fraction_gt:
                continue
        yield tile, extract_tile(image, tile)


def row_col_mask(
    shape: tuple[int, int],
    rows: npt.ArrayLike | None = None,
    cols: npt.ArrayLike | None = None,
) -> npt.NDArray[np.bool_]:
    """2-D mask from per-row flags (e.g. dropouts) and per-column flags (e.g. near nadir)."""
    mask = np.zeros(shape, dtype=bool)
    if rows is not None:
        mask |= np.asarray(rows, dtype=bool)[:, None]
    if cols is not None:
        mask |= np.asarray(cols, dtype=bool)[None, :]
    return mask
