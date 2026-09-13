"""ST-017: pipe and cylinder generators."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synth"))

from object_generators import generate, render, sample_params  # noqa: E402


def _background(tmp_path: Path) -> Path:
    rng = np.random.default_rng(0)
    root = tmp_path / "mine_sss"
    (root / "images" / "2018").mkdir(parents=True)
    (root / "labels" / "2018").mkdir(parents=True)
    for i in range(2):
        img = np.clip(rng.gamma(6.0, 15.0, (256, 256)), 0, 255).astype(np.uint8)
        cv2.imwrite(str(root / "images" / "2018" / f"{i:04d}_2018.jpg"), img)
        (root / "labels" / "2018" / f"{i:04d}_2018.txt").write_text("")
    return root


@pytest.mark.parametrize(("kind", "cls"), [("pipe", "1"), ("cylinder", "2")])
def test_generate_tiles(tmp_path: Path, kind: str, cls: str) -> None:
    from ghost_net_generator import find_backgrounds

    backgrounds = find_backgrounds(_background(tmp_path))
    summary = generate(kind, backgrounds, tmp_path / kind, 4, tile_px=160, res_m=0.05)
    assert summary["tiles"] == 4 and summary["polygons"] >= 4
    split = tmp_path / kind / "train"
    for label in (split / "labels").glob("*.txt"):
        assert all(line.split()[0] == cls for line in label.read_text().splitlines())
    params = json.loads(next((split / "params").glob("*.json")).read_text())
    assert params["kind"] == kind and params["generator_version"] == "1.0.0"


def test_pipe_is_long_and_cylinder_is_compact() -> None:
    rng = np.random.default_rng(3)
    bg = np.full((640, 640), 100, np.uint8)
    pipe = sample_params("pipe", rng, 640, 0.1, Path("bg"), "g", bg.shape, 3)
    pipe.burial_fraction = 0.0
    _, pipe_mask = render(bg, pipe)
    cyl = sample_params("cylinder", rng, 640, 0.1, Path("bg"), "g", bg.shape, 4)
    cyl.burial_fraction = 0.0
    image, cyl_mask = render(bg, cyl)
    ys, xs = np.nonzero(pipe_mask)
    assert max(np.ptp(xs), np.ptp(ys)) > 200  # tens of metres
    ys, xs = np.nonzero(cyl_mask)
    assert max(np.ptp(xs), np.ptp(ys)) <= cyl.length_m / 0.1 + 2
    assert image[cyl_mask].mean() > 100  # brighter than the flat background
    with pytest.raises(ValueError):
        generate("tyre", [], Path("x"), 1)
