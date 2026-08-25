#!/usr/bin/env python3
"""Validate and create a reproducible ZIP distribution."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="ZIP output path")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or root.with_suffix(".zip")

    subprocess.run([sys.executable, str(root / "scripts/validate_skillpack.py"), "--strict-jsonschema"], check=True)
    if output.exists():
        output.unlink()
    # Fixed timestamp improves reproducibility across repeated packaging.
    timestamp = (2026, 8, 20, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            rel = Path(root.name) / path.relative_to(root)
            info = zipfile.ZipInfo(str(rel).replace(os.sep, "/"), timestamp)
            mode = 0o755 if path.parent.name == "scripts" and path.suffix in {".py", ".sh"} else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"Created: {output}")
    print(f"SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
