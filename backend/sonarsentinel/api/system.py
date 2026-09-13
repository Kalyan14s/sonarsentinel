"""System information shared by health, models and settings: model list, GPU and runtimes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def gpu_info() -> dict[str, Any]:
    if not importable("torch"):
        return {"available": False, "name": None}
    import torch

    if torch.cuda.is_available():
        return {"available": True, "name": torch.cuda.get_device_name(0)}
    return {"available": False, "name": None}


def detector_weights(config: dict[str, Any]) -> Path:
    weights = Path(str(config["detection"]["model"]))
    return weights if weights.is_absolute() else REPO_ROOT / weights


def list_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detector options: the rule-based stand-in (always) and the configured trained model."""
    from sonarsentinel.detect.classical import BrightTargetDetector

    weights = detector_weights(config)
    return [
        {
            "kind": "detector",
            "id": BrightTargetDetector.model_version,
            "available": True,
            "trained": False,
            "path": None,
        },
        {
            "kind": "detector",
            "id": f"yolo:{weights.parent.name}" if weights.parent.name else "yolo",
            "available": weights.is_file(),
            "trained": True,
            "path": str(weights),
        },
    ]


def detector_runtime(config: dict[str, Any], gpu: dict[str, Any] | None = None) -> str:
    """Runtime the configured detector would use: cuda, onnxruntime, torch or classical.

    ``classical`` without trained weights or Ultralytics; ``cuda`` only when PyTorch sees a GPU
    (and the runtime is ``auto``, ``cuda`` or ``tensorrt``); otherwise ``onnxruntime`` when
    ``best.onnx`` exists and ONNX Runtime is installed, else ``torch``.
    """
    weights = detector_weights(config)
    if not weights.is_file() or not importable("ultralytics"):
        return "classical"
    runtime = str(config.get("detection", {}).get("runtime", "auto"))
    if (
        runtime in ("auto", "cuda", "tensorrt")
        and (gpu if gpu is not None else gpu_info())["available"]
    ):
        return "cuda"
    onnx_ready = weights.with_suffix(".onnx").is_file() and importable("onnxruntime")
    if runtime == "onnxruntime" or (runtime != "torch" and onnx_ready):
        return "onnxruntime"
    return "torch"


def available_runtimes(gpu: dict[str, Any] | None = None) -> list[str]:
    """Detector runtimes that can run on this machine (``auto`` is always offered)."""
    runtimes = ["auto"]
    if importable("torch") and importable("ultralytics"):
        runtimes.append("torch")
    if importable("onnxruntime"):
        runtimes.append("onnxruntime")
    if importable("tensorrt"):
        runtimes.append("tensorrt")
    if (gpu if gpu is not None else gpu_info())["available"]:
        runtimes.append("cuda")
    return runtimes
