#!/usr/bin/env python3
"""Create or verify deterministic, content-addressed local evidence manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath


def _safe_file(root: Path, relative: str) -> Path:
    logical = PurePosixPath(relative)
    if logical.is_absolute() or not logical.parts or ".." in logical.parts:
        raise ValueError(f"unsafe evidence path: {relative}")
    path = root.joinpath(*logical.parts)
    if path.is_symlink():
        raise ValueError(f"evidence path must not be a symlink: {relative}")
    resolved = path.resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if resolved_root not in (resolved, *resolved.parents):
        raise ValueError(f"evidence path escapes root: {relative}")
    if not resolved.is_file():
        raise ValueError(f"evidence path is not a regular file: {relative}")
    return resolved


def _entry(root: Path, relative: str) -> dict[str, object]:
    path = _safe_file(root, relative)
    content = path.read_bytes()
    return {
        "path": PurePosixPath(relative).as_posix(),
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def build(root: Path, manifest_path: Path, includes: list[str]) -> None:
    relative_manifest = manifest_path.resolve(strict=False).relative_to(root.resolve(strict=True)).as_posix()
    normalized = sorted(set(PurePosixPath(item).as_posix() for item in includes))
    if len(normalized) != len(includes):
        raise ValueError("evidence include paths must be unique")
    if relative_manifest in normalized:
        raise ValueError("evidence manifest cannot include itself")
    manifest = {
        "schema_version": 1,
        "algorithm": "sha256",
        "entries": [_entry(root, item) for item in normalized],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def verify(root: Path, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot load evidence manifest: {exc}"]
    if manifest.get("schema_version") != 1:
        errors.append("evidence manifest schema_version must be 1")
    if manifest.get("algorithm") != "sha256":
        errors.append("evidence manifest algorithm must be sha256")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        return [*errors, "evidence manifest entries must be a non-empty list"]
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(paths) != len(entries) or any(not isinstance(path, str) for path in paths):
        return [*errors, "every evidence entry must have a string path"]
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        errors.append("evidence entries must have unique paths in lexical order")
    for item in entries:
        relative = item["path"]
        try:
            expected = _entry(root, relative)
        except Exception as exc:
            errors.append(str(exc))
            continue
        if item.get("byte_size") != expected["byte_size"]:
            errors.append(f"evidence byte_size mismatch: {relative}")
        if item.get("sha256") != expected["sha256"]:
            errors.append(f"evidence sha256 mismatch: {relative}")
    return errors


def verify_repository_bindings(repository_root: Path, record_path: Path) -> list[str]:
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot load repository binding record: {exc}"]
    bindings = record.get("repository_bindings")
    if not isinstance(bindings, list) or not bindings:
        return [f"repository_bindings must be non-empty: {record_path}"]
    errors: list[str] = []
    paths = [item.get("path") for item in bindings if isinstance(item, dict)]
    if len(paths) != len(bindings) or any(not isinstance(path, str) for path in paths):
        return [f"every repository binding must have a string path: {record_path}"]
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        errors.append(f"repository bindings must have unique paths in lexical order: {record_path}")
    for item in bindings:
        try:
            expected = _entry(repository_root, item["path"])
        except Exception as exc:
            errors.append(str(exc))
            continue
        if item.get("byte_size") != expected["byte_size"]:
            errors.append(f"repository binding byte_size mismatch: {item['path']}")
        expected_digest = "sha256:" + str(expected["sha256"])
        if item.get("sha256") != expected_digest:
            errors.append(f"repository binding sha256 mismatch: {item['path']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("manifest")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--binding-record", action="append", type=Path, default=[])
    args = parser.parse_args()
    root = Path(args.root)
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        if args.write:
            if not args.include:
                raise ValueError("--write requires at least one --include")
            build(root, manifest_path, args.include)
        elif args.include:
            raise ValueError("--include is only valid with --write")
        errors = verify(root, manifest_path)
        if args.binding_record and not args.repository_root:
            errors.append("--binding-record requires --repository-root")
        elif args.repository_root:
            for record in args.binding_record:
                errors.extend(verify_repository_bindings(args.repository_root, record))
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {os.path.relpath(manifest_path, root)} ({len(json.loads(manifest_path.read_text())['entries'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
