#!/usr/bin/env python3
"""Refresh mirrors, checksums, and ZIP/TAR.GZ archives."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
ZIP_PATH = PARENT / f"{ROOT.name}.zip"
TGZ_PATH = PARENT / f"{ROOT.name}.tar.gz"


def refresh_mirror(destination: Path) -> None:
    source = ROOT / "skills"
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def write_checksums() -> None:
    lines: list[str] = []
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "CHECKSUMS.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    (ROOT / "CHECKSUMS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_archives() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    if TGZ_PATH.exists():
        TGZ_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            arcname = (Path(ROOT.name) / path.relative_to(ROOT)).as_posix()
            if path.is_dir():
                continue
            archive.write(path, arcname)

    with tarfile.open(TGZ_PATH, "w:gz", compresslevel=9) as archive:
        archive.add(ROOT, arcname=ROOT.name, recursive=True)


def main() -> int:
    refresh_mirror(ROOT / ".agents" / "skills")
    refresh_mirror(ROOT / ".claude" / "skills")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_package.py")])
    if result.returncode:
        return result.returncode
    write_checksums()
    # Validate again after the checksum file was created; mirrors are unaffected.
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_package.py")])
    if result.returncode:
        return result.returncode
    build_archives()
    print(f"Built: {ZIP_PATH}")
    print(f"Built: {TGZ_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
