"""Validate the attached PI Harness archive without executing package files."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "skills/subskills/elmos-pi-harness-architecture-v5.1.0.zip"
MAX_ENTRIES = 2_000
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "" not in path.parts and "\\" not in name


def validate(archive: Path = ARCHIVE) -> dict[str, object]:
    if not archive.is_file():
        raise SystemExit(f"SOURCE_PACKAGE_ABSENT={archive}")
    raw = archive.read_bytes()
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        if len(infos) > MAX_ENTRIES:
            raise SystemExit("archive has too many entries")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise SystemExit("archive contains duplicate member names")
        if any(not _safe_name(name) for name in names):
            raise SystemExit("archive contains an unsafe path")
        total = 0
        for info in infos:
            total += info.file_size
            if info.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                raise SystemExit("archive exceeds configured size limit")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise SystemExit(f"archive contains a symlink member: {info.filename}")
        prefix = "elmos-pi-harness-architecture/"
        manifest_name = prefix + "manifest.json"
        required = {prefix + "SKILL.md", prefix + "README.md", manifest_name}
        if not required.issubset(names):
            raise SystemExit("archive is missing its required package metadata")
        manifest = json.loads(package.read(manifest_name).decode("utf-8"))
        if manifest.get("name") != "elmos-pi-harness-architecture" or manifest.get("version") != "5.1.0":
            raise SystemExit("archive manifest identity does not match the requested package")
    return {
        "archive": str(archive),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "entries": len(names),
        "uncompressed_bytes": total,
        "executed": False,
        "status": "VALIDATED_AS_UNTRUSTED_SOURCE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.archive), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
