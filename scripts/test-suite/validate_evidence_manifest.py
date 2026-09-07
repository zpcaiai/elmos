#!/usr/bin/env python3
"""Validate evidence structure, containment, sizes, and raw-file digests."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import (
    load_json,
    resolve_beneath,
    sha256_file,
    validate_evidence_manifest_shape,
)


def validate_manifest(path: Path, suite_root: Path) -> list[str]:
    try:
        document = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"cannot read evidence manifest: {exc}"]
    errors = validate_evidence_manifest_shape(document)
    for item in document.get("files", []) if isinstance(document, dict) else []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        try:
            raw = resolve_beneath(path.parent, item["path"])
            raw.relative_to(suite_root.resolve())
        except (ValueError, Exception) as exc:  # noqa: BLE001
            errors.append(f"unsafe evidence path {item.get('path')}: {exc}")
            continue
        if raw.stat().st_size != item.get("bytes"):
            errors.append(f"size mismatch: {item['path']}")
        if sha256_file(raw) != item.get("sha256"):
            errors.append(f"digest mismatch: {item['path']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--suite-root")
    args = parser.parse_args()
    path = Path(args.manifest).resolve()
    suite_root = Path(args.suite_root).resolve() if args.suite_root else path.parents[2]
    errors = validate_manifest(path, suite_root)
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: evidence manifest structure and raw-file digests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
