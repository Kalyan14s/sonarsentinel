import sys
from pathlib import Path

# Dataset scripts are standalone files; make them importable as modules in tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "datasets"))
