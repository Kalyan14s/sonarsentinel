"""Download small test fixtures listed in a manifest and verify their SHA-256 (backlog ST-004).

- Idempotent: files already present with the pinned hash are skipped.
- Checksum mismatch: the file is deleted and the run fails.
- Trust on first use: entries with ``"sha256": null`` are downloaded and their hash printed;
  the run fails unless ``--accept-new`` is given. Pin the printed hash in the manifest.

Large survey data is not fetched here; it is managed with DVC (see the Data Management Plan).

Usage:
    python scripts/fetch_test_data.py [--manifest PATH] [--root PATH] [--accept-new]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "test_data_manifest.json"


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest`` atomically (via a ``.part`` file)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "sonarsentinel-fetch/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as fh:
        while chunk := response.read(1 << 20):
            fh.write(chunk)
    tmp.replace(dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT, help="Base directory for 'dest' paths."
    )
    parser.add_argument(
        "--accept-new", action="store_true", help="Accept entries without a pinned hash."
    )
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    entries = manifest.get("files", [])
    if not entries:
        print("Manifest has no files yet; nothing to fetch.")
        return 0

    failures = 0
    for entry in entries:
        name, url, expected = entry["name"], entry["url"], entry.get("sha256")
        dest = args.root / entry["dest"]
        if dest.exists() and expected and sha256_of(dest) == expected:
            print(f"[skip] {name} (already present)")
            continue
        print(f"[get ] {name} <- {url}")
        try:
            download(url, dest)
        except OSError as exc:
            print(f"[fail] {name}: {exc}")
            failures += 1
            continue
        actual = sha256_of(dest)
        if expected is None:
            print(f"[new ] {name} sha256={actual}")
            if not args.accept_new:
                print("       Pin this hash in the manifest, or re-run with --accept-new.")
                failures += 1
        elif actual != expected:
            print(f"[fail] {name}: sha256 mismatch (expected {expected}, got {actual})")
            dest.unlink()
            failures += 1
        else:
            print(f"[ ok ] {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
