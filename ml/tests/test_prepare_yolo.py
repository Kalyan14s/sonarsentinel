"""prepare_yolo.py: variant selection, background subsampling and 3-channel conversion."""

import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("scipy")

from prepare_yolo import convert, select_files  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from sonarsentinel.preprocess.channels import to_three_channel  # noqa: E402


def _manifest() -> dict:
    files = []
    for i in range(4):
        files.append(
            {
                "image": f"images/train/real_{i}.png",
                "label": f"labels/train/real_{i}.txt",
                "split": "train",
                "dataset": "mine_sss",
                "objects": {"cylinder": 1} if i < 2 else {},
            }
        )
    for i in range(6):
        files.append(
            {
                "image": f"images/train/empty_{i}.png",
                "label": f"labels/train/empty_{i}.txt",
                "split": "train",
                "dataset": "mine_sss",
                "objects": {},
            }
        )
    for i in range(3):
        files.append(
            {
                "image": f"images/train/gn_{i}.png",
                "label": f"labels/train/gn_{i}.txt",
                "split": "train",
                "dataset": "synthetic_ghost_net",
                "objects": {"ghost_net": 2},
            }
        )
    files.append(
        {
            "image": "images/val/v.png",
            "label": "labels/val/v.txt",
            "split": "val",
            "dataset": "mine_sss",
            "objects": {},
        }
    )
    files.append(
        {
            "image": "images/synthetic_holdout/h.png",
            "label": "labels/synthetic_holdout/h.txt",
            "split": "synthetic_holdout",
            "dataset": "synthetic_ghost_net",
            "objects": {"ghost_net": 1},
        }
    )
    return {"version": "0.0.1", "files": files}


def test_select_variants() -> None:
    real = select_files(_manifest(), "real", background_ratio=1.0, synthetic_per_kind=10)
    train = [f for f in real if f["split"] == "train"]
    assert sum(bool(f["objects"]) for f in train) == 2 and len(train) == 4  # 2 positives + 2 empty
    assert not any(f["dataset"].startswith("synthetic") for f in train)
    assert any(f["split"] == "val" for f in real)
    synth = select_files(_manifest(), "real_synth", background_ratio=0.5, synthetic_per_kind=2)
    strain = [f for f in synth if f["split"] == "train"]
    assert sum(f["dataset"] == "synthetic_ghost_net" for f in strain) == 2
    assert sum(not f["objects"] for f in strain) == 2  # 0.5 × 4 positives
    assert any(f["split"] == "synthetic_holdout" for f in synth)
    with pytest.raises(ValueError):
        select_files(_manifest(), "bogus", 1.0, 1)


def test_convert_writes_three_channel_pngs(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    manifest = _manifest()
    rng = np.random.default_rng(0)
    for f in manifest["files"]:
        (processed / f["image"]).parent.mkdir(parents=True, exist_ok=True)
        (processed / f["label"]).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(processed / f["image"]), rng.integers(0, 255, (64, 64), dtype=np.uint8))
        (processed / f["label"]).write_text("")
    files = select_files(manifest, "real_synth", 0.5, 1)
    summary = convert(files, processed, tmp_path / "out")
    assert summary["holdout"]["images"] == 1 and summary["train"]["positive_images"] == 3
    written = cv2.imread(
        str(tmp_path / "out" / "images" / "train" / "real_0.png"), cv2.IMREAD_UNCHANGED
    )
    source = cv2.imread(str(processed / "images/train/real_0.png"), cv2.IMREAD_GRAYSCALE)
    assert written.shape == (64, 64, 3)
    assert np.array_equal(written, to_three_channel(source))  # same function as inference
    yaml = (tmp_path / "out" / "data.yaml").read_text()
    assert "train: images/train" in yaml and "3: ghost_net" in yaml
