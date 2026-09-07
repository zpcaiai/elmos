#!/usr/bin/env python3
"""Build deterministic ZIP/TAR.GZ archives and SHA-256 manifests."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import tarfile
import zipfile

EXCLUDE_NAMES = {"__pycache__", ".git", ".venv", ".pytest_cache", "dist"}


def package_files(root: Path):
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if any(part in EXCLUDE_NAMES for part in path.parts):
            continue
        if path.is_file() and not path.name.endswith(".pyc"):
            yield path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_file_manifest(root: Path) -> Path:
    target = root / "dist-manifests" / "package-file-manifest.json"
    rows = []
    for path in package_files(root):
        if path == target:
            continue
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    payload = {
        "schemaVersion": "elmos.package-file-manifest/v1",
        "package": root.name,
        "fileCountExcludingThisManifest": len(rows),
        "files": rows,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def build_zip(root: Path, output: Path) -> None:
    prefix = root.name
    timestamp = (2026, 8, 19, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in package_files(root):
            rel = f"{prefix}/{path.relative_to(root).as_posix()}"
            info = zipfile.ZipInfo(rel, timestamp)
            mode = path.stat().st_mode
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())


def build_tar_gz(root: Path, output: Path) -> None:
    prefix = root.name
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as archive:
                for path in package_files(root):
                    arcname = f"{prefix}/{path.relative_to(root).as_posix()}"
                    info = archive.gettarinfo(str(path), arcname=arcname)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = (args.output_dir or root.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    write_file_manifest(root)
    zip_path = output_dir / f"{root.name}.zip"
    tar_path = output_dir / f"{root.name}.tar.gz"
    sums_path = output_dir / f"{root.name}-SHA256SUMS.txt"
    for path in [zip_path, tar_path, sums_path]:
        if path.exists():
            path.unlink()

    build_zip(root, zip_path)
    build_tar_gz(root, tar_path)
    sums_path.write_text(
        f"{sha256(zip_path)}  {zip_path.name}\n{sha256(tar_path)}  {tar_path.name}\n",
        encoding="utf-8",
    )
    print(zip_path)
    print(tar_path)
    print(sums_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
