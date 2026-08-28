#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--output", type=Path, default=Path("reports/etgb-evidence.tar.gz"))
    args = parser.parse_args()
    files = sorted(p for p in args.reports.rglob("*") if p.is_file() and p != args.output)
    manifest = {str(p): sha256(p) for p in files}
    manifest_path = args.reports / "EVIDENCE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with tarfile.open(args.output, "w:gz") as tar:
        for p in files + [manifest_path]:
            tar.add(p, arcname=p.relative_to(args.reports.parent))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
