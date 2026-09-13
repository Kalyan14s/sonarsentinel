"""ST-112 benchmark helpers (scripts/benchmark.py): statistics, event timing, sizes, table."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from benchmark import (  # noqa: E402
    event_metrics,
    file_size_mb,
    markdown_table,
    seconds_per_km,
    summary_stats,
)


def test_summary_stats() -> None:
    assert summary_stats([3.0, 1.0, 2.0]) == {"median": 2.0, "min": 1.0, "max": 3.0}
    assert summary_stats([]) == {"median": None, "min": None, "max": None}


def test_event_metrics_first_detection_gaps_and_stages() -> None:
    events = [
        {"type": "progress", "t": 0.0, "stage": "validate"},
        {"type": "progress", "t": 1.0, "stage": "parse"},
        {"type": "progress", "t": 4.0, "stage": "detect"},
        {"type": "warning", "t": 6.0, "stage": None},
        {"type": "progress", "t": 9.0, "stage": "detect"},
        {"type": "progress", "t": 10.0, "stage": "merge"},
        {"type": "detection", "t": 10.5, "stage": None},
        {"type": "progress", "t": 11.0, "stage": "report"},
        {"type": "done", "t": 12.0, "stage": None},
    ]
    metrics = event_metrics(events)
    assert metrics["first_detection_s"] == 10.5
    assert metrics["max_progress_gap_s"] == 5.0
    assert metrics["stage_s"] == {
        "validate": 1.0,
        "parse": 3.0,
        "detect": 6.0,
        "merge": 1.0,
        "report": 1.0,
    }
    assert metrics["progress_events"] == 6
    assert event_metrics([])["first_detection_s"] is None


def test_seconds_per_km_and_sizes(tmp_path: Path) -> None:
    assert seconds_per_km(220.0, 1.0) == 220.0
    assert seconds_per_km(97.5, 0.444) == pytest.approx(219.6, abs=0.1)
    assert seconds_per_km(None, 1.0) is None and seconds_per_km(10.0, None) is None
    (tmp_path / "a.bin").write_bytes(b"x" * 2**20)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.bin").write_bytes(b"x" * 2**19)
    assert file_size_mb(tmp_path / "a.bin") == 1.0
    assert file_size_mb(tmp_path) == 1.5
    assert file_size_mb(tmp_path / "missing") is None


def test_markdown_table_lists_targets() -> None:
    result = {
        "runs": 3,
        "wall_s": {"median": 200.0, "min": 190.0, "max": 210.0},
        "track_length_km": 1.0,
        "s_per_km": 200.0,
        "first_detection_s": 180.0,
        "max_progress_gap_s": 40.0,
        "peak_rss_mb": 2048.0,
        "detections": 12,
        "runtime": "onnxruntime-cpu",
        "detector": "yolo@0.1.0",
        "model_sizes_mb": {"detector_pt": 19.6},
        "stage_s": {"detect": 150.0},
    }
    table = markdown_table(result)
    assert "| Seconds per km (median) | 200.0 | ≤ 300 |" in table
    assert "| Model size: detector_pt (MB) | 19.6 | FP32 ≤ 25 |" in table
    assert "| detect | 150.0 |" in table
