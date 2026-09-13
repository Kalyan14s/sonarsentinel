"""Tests for ST-016 (synthetic ghost-net generator) and ST-015 (grouped splits, leakage check)."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "synth"))

from ghost_net_generator import (  # noqa: E402
    NetParams,
    cast_shadow,
    find_backgrounds,
    generate,
    render_tile,
    sample_params,
)
from make_splits import (  # noqa: E402
    LeakageError,
    assign_sites,
    build,
    cross_split_duplicates,
    thumbnail,
)


def _seafloor(rng: np.random.Generator, size: int = 1024) -> np.ndarray:
    img = rng.gamma(6.0, 15.0, (size, size))
    img[:, size // 2 - 20 : size // 2 + 20] = 5  # dark nadir band
    return np.clip(img, 0, 255).astype(np.uint8)


def _interim(tmp_path: Path, groups: dict[str, int], seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    root = tmp_path / "mine_sss"
    for group, n in groups.items():
        (root / "images" / group).mkdir(parents=True, exist_ok=True)
        (root / "labels" / group).mkdir(parents=True, exist_ok=True)
        for i in range(n):
            cv2.imwrite(str(root / "images" / group / f"{i:04d}_{group}.jpg"), _seafloor(rng, 256))
            label = "2 0.4 0.4 0.5 0.4 0.5 0.5 0.4 0.5\n" if i % 3 == 0 else ""
            (root / "labels" / group / f"{i:04d}_{group}.txt").write_text(label, encoding="utf-8")
    return root


def test_render_tile_mask_shadow_and_params() -> None:
    rng = np.random.default_rng(5)
    bg = _seafloor(rng)
    params = sample_params(rng, 640, 0.1, Path("bg.jpg"), "2018", bg.shape, seed=5)
    params.burial_fraction, params.height_m, params.shadow_length_px = 0.2, 1.0, 20
    params.side, params.reflectivity = "starboard", 100.0
    image, mask = render_tile(bg, params)
    assert image.shape == (640, 640) and image.dtype == np.uint8
    assert mask.sum() > 50
    again, mask2 = render_tile(bg, params)
    assert np.array_equal(image, again) and np.array_equal(mask, mask2)  # deterministic per seed
    ys, xs = np.nonzero(mask)
    right = cast_shadow(mask, 20, +1)
    assert right.any() and np.median(np.nonzero(right)[1]) > np.median(xs)
    record = NetParams(**{k: getattr(params, k) for k in params.__dataclass_fields__})
    assert record.generator_version == "1.0.0"


def test_generate_writes_all_outputs(tmp_path: Path) -> None:
    root = _interim(tmp_path, {"2018": 4, "2017": 3})
    backgrounds = find_backgrounds(root)
    assert {g for _, g in backgrounds} == {"2018", "2017"}
    assert len(backgrounds) == 4  # images 0 and 3 in each group have objects
    summary = generate(backgrounds, tmp_path / "synth", 3, tile_px=128, res_m=0.05)
    assert summary["tiles"] == 3
    split = tmp_path / "synth" / "train"
    for sub, ext in (
        ("images", ".png"),
        ("masks", ".png"),
        ("labels", ".txt"),
        ("params", ".json"),
    ):
        assert len(list((split / sub).glob(f"*{ext}"))) == 3
    params = json.loads(next((split / "params").glob("*.json")).read_text())
    for key in ("seed", "mesh_cm", "burial_fraction", "height_m", "shadow_length_px", "background"):
        assert key in params
    label = next((split / "labels").glob("*.txt")).read_text()
    assert all(line.startswith("3 ") for line in label.splitlines())


def test_assign_sites_keeps_sites_whole() -> None:
    sizes = {"a": 564, "b": 345, "c": 120, "d": 93, "e": 48}
    positives = {"a": 96, "b": 22, "c": 242, "d": 28, "e": 49}
    result = assign_sites(sizes, positives)
    assert set(result) == set(sizes) and set(result.values()) == {"train", "val", "calib", "test"}
    with pytest.raises(ValueError, match="at least 4 sites"):
        assign_sites({"a": 1, "b": 1}, {})


def test_holdout_background_sites_stay_out_of_train() -> None:
    sizes = {"a": 564, "b": 345, "c": 120, "d": 93, "e": 48}
    positives = {"a": 96, "b": 22, "c": 242, "d": 28, "e": 49}
    for blocked in ({"a"}, {"d"}, {"a", "b"}):
        result = assign_sites(sizes, positives, not_train=blocked)
        assert all(result[s] != "train" for s in blocked)
        assert set(result.values()) == {"train", "val", "calib", "test"}
    many = {f"s{i}": 10 + i for i in range(12)}
    greedy = assign_sites(many, {}, not_train={"s11", "s10"})
    assert greedy["s11"] != "train" and greedy["s10"] != "train"


def test_build_splits_manifest_and_leakage(tmp_path: Path) -> None:
    root = _interim(tmp_path, {"2010": 9, "2015": 5, "2017": 4, "2018": 12, "2021": 3}, seed=1)
    synth_root = tmp_path / "ghost_net" / "1.0.0"
    generate(find_backgrounds(root), synth_root, 2, tile_px=96, res_m=0.05)
    manifest = build(
        [root], synth_root, tmp_path / "out", tmp_path / "manifests", "0.0.1", min_correlation=0.97
    )
    splits = manifest["splits"]
    assert {"train", "val", "calib", "test"} <= set(splits)
    real_sites = [s for info in splits.values() for s in info["sites"] if s.startswith("mine_sss")]
    assert len(real_sites) == len(set(real_sites)) == 5
    assert splits["train"]["objects"].get("ghost_net", 0) >= 0
    assert manifest["test_hash_frozen"].startswith("sha256:")
    assert (tmp_path / "manifests" / "sonar-seg-0.0.1.stats.md").exists()
    assert len(list((tmp_path / "out" / "images" / "train").iterdir())) >= 2

    image = next((root / "images" / "2010").glob("*.jpg"))
    copy = root / "images" / "2021" / "dup_2021.jpg"
    copy.write_bytes(image.read_bytes())
    (root / "labels" / "2021" / "dup_2021.txt").write_text("", encoding="utf-8")
    with pytest.raises(LeakageError):
        build([root], None, tmp_path / "out2", tmp_path / "m2", "0.0.2", min_correlation=0.97)


def test_thumbnail_correlation_finds_near_duplicates(tmp_path: Path) -> None:
    rng = np.random.default_rng(2)
    img = _seafloor(rng, 128)
    cv2.imwrite(str(tmp_path / "a.png"), img)
    cv2.imwrite(str(tmp_path / "b.png"), np.clip(img.astype(int) + 3, 0, 255).astype(np.uint8))
    cv2.imwrite(str(tmp_path / "c.png"), _seafloor(rng, 128))  # same layout, different speckle
    a, b, c = (thumbnail(tmp_path / f"{n}.png") for n in "abc")
    assert float(a @ b) / a.size > 0.99
    assert float(a @ c) / a.size < 0.97  # shared nadir band alone doesn't count as a duplicate

    class It:
        def __init__(self, image: Path, split: str) -> None:
            self.image, self.split = image, split

    items = [
        It(tmp_path / "a.png", "train"),
        It(tmp_path / "b.png", "test"),
        It(tmp_path / "c.png", "val"),
    ]
    pairs = cross_split_duplicates(items, 0.97)  # type: ignore[arg-type]
    assert len(pairs) == 1 and pairs[0][0].endswith("a.png")
