#!/usr/bin/env python3
"""Create deterministic installable archives for the mature-product Skills."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def collect(first_batch: int, last_batch: int) -> list[Path]:
    files: set[Path] = set()
    for batch in range(first_batch, last_batch + 1):
        for skill in (ROOT / ".agents" / "skills").glob(f"b{batch}-*"):
            files.update(path for path in skill.rglob("*") if path.is_file())
        for directory in (
            ROOT / "docs" / f"batch{batch}",
            ROOT / "schemas" / f"batch{batch}",
            ROOT / "templates" / f"batch{batch}",
            ROOT / "scripts" / f"batch{batch}",
            ROOT / "tests" / f"batch{batch}",
        ):
            if directory.is_dir():
                files.update(
                    path for path in directory.rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts
                )
        makefile = ROOT / f"Makefile.batch{batch}"
        if makefile.is_file():
            files.add(makefile)
    files.add(ROOT / "AGENTS.md")
    files.add(ROOT / "scripts" / "validate_mature_product_series.py")
    files.add(ROOT / "scripts" / "package_mature_product_series.py")
    if last_batch >= 35:
        files.add(ROOT / "scripts" / "mature_product_toolkit.py")
        files.add(ROOT / "skills" / "generate_mature_product_batches_35_45.py")
        files.add(ROOT / "docs" / "mature-product-batches-35-45-source-manifest.json")
    if first_batch <= 29:
        files.add(ROOT / "docs" / "mature-product-batches-29-34-source-manifest.json")
        files.add(ROOT / "docs" / "mature-product-batches-29-34-verification.md")
        files.add(ROOT / "docs" / "mature-product-batches-29-45-verification.md")
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing archive inputs: {missing}")
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_archive(first_batch: int, last_batch: int, output: Path) -> tuple[int, str]:
    files = collect(first_batch, last_batch)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_lines: list[str] = []
    with zipfile.ZipFile(output, "w") as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            manifest_lines.append(f"{hashlib.sha256(data).hexdigest()}  {relative}")
            zip_entry(archive, relative, data)
        zip_entry(archive, "FILE_MANIFEST.sha256", ("\n".join(manifest_lines) + "\n").encode())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return len(files), digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "mature-product-skills")
    args = parser.parse_args()
    outputs = (
        (35, 45, args.output_dir / "mature-product-batches-35-45.zip"),
        (29, 45, args.output_dir / "mature-product-batches-29-45.zip"),
    )
    for first, last, output in outputs:
        count, digest = build_archive(first, last, output)
        print(f"{output}: files={count + 1} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
