"""ST-026 / NFR-07 benchmark: peak memory while reading a large XTF into memory-mapped arrays.

Generates a synthetic XTF of about ``--size-gb`` (in a separate process, so generation doesn't
count), then reads it with ``read_xtf(work_dir=...)``, touches every chunk, and reports peak memory.

    python scripts/bench_xtf_memory.py --path <scratch>/big.xtf --size-gb 2
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))


def generate(path: Path, size_gb: float, samples: int) -> None:
    from pyxtf import XTFPingChanHeader, XTFPingHeader
    from tools.make_synthetic_xtf import write_synthetic_xtf

    record = ctypes.sizeof(XTFPingHeader) + 2 * (ctypes.sizeof(XTFPingChanHeader) + 2 * samples)
    n_pings = int(size_gb * 1024**3 / record)
    write_synthetic_xtf(path, n_pings=n_pings, samples_per_side=samples, step_m=0.1)


def peak_memory_mb() -> dict[str, float]:
    import psutil

    info = psutil.Process().memory_info()
    mb = 1024**2
    if sys.platform == "win32":
        return {
            "peak_working_set_mb": info.peak_wset / mb,
            "peak_private_mb": info.peak_pagefile / mb,
        }
    import resource

    return {"peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--size-gb", type=float, default=2.0)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args()

    if args.generate_only:
        generate(args.path, args.size_gb, args.samples)
        return
    if not args.path.exists():
        started = time.perf_counter()
        cmd = [sys.executable, __file__, "--path", str(args.path), "--size-gb", str(args.size_gb),
               "--samples", str(args.samples), "--generate-only"]  # fmt: skip
        subprocess.run(cmd, check=True)
        print(f"generated {args.path} in {time.perf_counter() - started:.0f} s")

    from sonarsentinel.ingest.chunking import iter_chunks
    from sonarsentinel.ingest.xtf_reader import read_xtf

    baseline = peak_memory_mb()
    with tempfile.TemporaryDirectory() as work:
        started = time.perf_counter()
        log = read_xtf(args.path, work_dir=work)
        read_s = time.perf_counter() - started
        checksum = 0
        for _, chunk in iter_chunks(log, size=2000, overlap=200):
            assert chunk.port is not None and chunk.starboard is not None
            checksum += int(chunk.port[:, ::97].sum()) + int(chunk.starboard[:, ::97].sum())
        result = {
            "file_gb": round(args.path.stat().st_size / 1024**3, 3),
            "pings": log.n_pings,
            "samples_per_channel": log.sonar.samples_per_channel,
            "read_s": round(read_s, 1),
            "total_s": round(time.perf_counter() - started, 1),
            "baseline": {k: round(v) for k, v in baseline.items()},
            "peak": {k: round(v) for k, v in peak_memory_mb().items()},
            "chunk_checksum": checksum,
        }
        del log, chunk
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
