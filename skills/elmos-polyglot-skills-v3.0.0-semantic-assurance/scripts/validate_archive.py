#!/usr/bin/env python3
"""Validate ELMOS release archive integrity and inventory."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts


def check_zip(path: Path) -> tuple[int, int]:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"corrupt ZIP member: {bad}")
        names = zf.namelist()
        if not all(safe_name(n) for n in names):
            raise RuntimeError("unsafe ZIP path")
        skills = [n for n in names if "/agent-skills/runtime/" in n and n.endswith("/SKILL.md")]
        if len(skills) != 64:
            raise RuntimeError(f"ZIP expected 64 Skills, found {len(skills)}")
        return len(names), len(skills)


def check_tar(path: Path) -> tuple[int, int]:
    with tarfile.open(path, "r:gz") as tf:
        members = tf.getmembers()
        names = [m.name for m in members]
        if not all(safe_name(n) for n in names):
            raise RuntimeError("unsafe TAR path")
        if any(m.issym() or m.islnk() for m in members):
            raise RuntimeError("release TAR must not contain links")
        skills = [n for n in names if "/agent-skills/runtime/" in n and n.endswith("/SKILL.md")]
        if len(skills) != 64:
            raise RuntimeError(f"TAR expected 64 Skills, found {len(skills)}")
        return len(names), len(skills)


def verify_sums(sums: Path, directory: Path) -> None:
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        path = directory / name.strip()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError(f"checksum mismatch: {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("tar_gz", type=Path)
    parser.add_argument("sums", type=Path)
    args = parser.parse_args()
    zip_stats = check_zip(args.zip)
    tar_stats = check_tar(args.tar_gz)
    verify_sums(args.sums, args.sums.parent)
    print(f"PASS: ZIP entries={zip_stats[0]}, Skills={zip_stats[1]}")
    print(f"PASS: TAR entries={tar_stats[0]}, Skills={tar_stats[1]}")
    print("PASS: SHA-256 checksums")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
