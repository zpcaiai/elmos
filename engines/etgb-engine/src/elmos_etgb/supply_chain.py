"""Read-only supply-chain inventory and artifact integrity checks.

This deliberately does not run package managers, build hooks, containers, or
network scanners.  Those require an authorized external evidence provider.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def inspect_tree(root: Path, *, allow_suffixes: tuple[str, ...] = ()) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            errors.append(f"symlink is not permitted: {path.relative_to(root)}")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if allow_suffixes and not relative.endswith(allow_suffixes):
            continue
        files.append({"path": relative, "size": path.stat().st_size, "sha256": _digest(path)})
    return {
        "schema_version": "1.1",
        "valid": not errors,
        "root": str(root),
        "file_count": len(files),
        "files": files,
        "sbom_status": "NOT_RUN",
        "provenance_status": "NOT_RUN",
        "signature_status": "NOT_RUN",
        "external_scan_status": "NOT_RUN",
        "errors": errors,
        "inventory_digest": "sha256:" + hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "interpretation": "Local inventory is engineering evidence and is not independent supply-chain certification.",
    }
