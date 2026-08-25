#!/usr/bin/env python3
"""Create a deterministic ZIP and SHA-256 checksum after validation."""
from __future__ import annotations
import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

EPOCH = (2020, 1, 1, 0, 0, 0)

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/validate_skill_bundle.py"), str(root)], check=True)
    subprocess.run([sys.executable, str(root / "scripts/validate_json_schemas.py"), str(root)], check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"], check=True)

    out = root.parent / f"{root.name}.zip"
    checksum = root.parent / f"{root.name}-SHA256SUMS.txt"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(
            p for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
        ):
            rel = Path(root.name) / path.relative_to(root)
            info = zipfile.ZipInfo(str(rel).replace(os.sep, "/"), EPOCH)
            mode = path.stat().st_mode
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, path.read_bytes())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    print(out)
    print(checksum)
    print(digest)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
