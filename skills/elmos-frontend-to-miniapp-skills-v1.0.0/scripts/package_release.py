#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import tarfile
import zipfile
from pathlib import Path

from common import package_root


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_zip(root: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            arc = f"{root.name}/{path.relative_to(root).as_posix()}"
            info = zipfile.ZipInfo.from_file(path, arcname=arc)
            info.compress_type = zipfile.ZIP_DEFLATED
            if os.access(path, os.X_OK):
                info.external_attr = (0o100755 & 0xFFFF) << 16
            with path.open("rb") as fh:
                zf.writestr(info, fh.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def create_tar(root: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz", compresslevel=9) as tf:
        tf.add(root, arcname=root.name, recursive=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    output_dir = (args.output_dir or root.parent).resolve()
    zip_path = output_dir / f"{root.name}.zip"
    tar_path = output_dir / f"{root.name}.tar.gz"
    create_zip(root, zip_path)
    create_tar(root, tar_path)
    for path in [zip_path, tar_path]:
        (Path(str(path) + ".sha256")).write_text(f"{sha256(path)}  {path.name}\n", encoding="utf-8")
        print(f"{path} {sha256(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
