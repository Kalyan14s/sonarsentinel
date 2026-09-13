"""Shared pytest setup.

On Windows, importing PyTorch after other native libraries (OpenCV, LightGBM, SciPy) in the same
process can fail with ``WinError 127`` while loading ``torch\\lib\\shm.dll``. Loading torch first,
when it is installed, keeps local full-suite runs independent of test order. CI has no torch, so
this is a no-op there.
"""

import importlib.util
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # conda OpenMP + pip PyTorch (ADR-016)

if importlib.util.find_spec("torch") is not None:
    import torch  # noqa: F401
