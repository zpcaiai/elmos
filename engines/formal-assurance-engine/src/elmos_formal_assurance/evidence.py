from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any, Iterable

from .canonical import digest_bytes, digest_value, validate_digest


class EvidenceError(ValueError):
    """Raised when evidence is unsafe, mutable or inconsistent."""


def _regular_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(metadata.st_mode)


def _confined(path: Path, root: Path) -> Path:
    root = root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    candidate = candidate.absolute()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise EvidenceError(f"evidence path escapes bundle root: {path}") from exc
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise EvidenceError(f"evidence path contains symlink: {current}")
    return candidate


def build_manifest(files: Iterable[Path], base_dir: Path) -> dict[str, Any]:
    root = base_dir.resolve(strict=True)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for original in sorted(files, key=lambda item: item.as_posix()):
        path = _confined(original, root)
        if not _regular_file(path):
            raise EvidenceError(f"evidence entry is not a regular file: {original}")
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            raise EvidenceError(f"duplicate evidence path: {relative}")
        seen.add(relative)
        data = path.read_bytes()
        entries.append(
            {"path": relative, "sha256": digest_bytes(data), "sizeBytes": len(data)}
        )
    unsigned = {"format": "elmos-proof-evidence-bundle/v1", "files": entries}
    return {**unsigned, "manifestSha256": digest_value(unsigned)}


def verify_manifest(manifest: dict[str, Any], base_dir: Path) -> list[str]:
    errors: list[str] = []
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != "elmos-proof-evidence-bundle/v1"
    ):
        return ["invalid evidence manifest format"]
    unsigned = {
        key: value for key, value in manifest.items() if key != "manifestSha256"
    }
    try:
        expected_manifest_hash = validate_digest(
            manifest.get("manifestSha256"), "manifestSha256"
        )
    except ValueError as exc:
        errors.append(str(exc))
        expected_manifest_hash = None
    if expected_manifest_hash != digest_value(unsigned):
        errors.append("manifest hash mismatch")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return errors + ["evidence manifest files must be an array"]
    root = base_dir.resolve(strict=True)
    seen: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not entry.get("path")
        ):
            errors.append("invalid evidence file entry")
            continue
        relative = entry["path"]
        if relative in seen:
            errors.append(f"duplicate evidence path: {relative}")
            continue
        seen.add(relative)
        try:
            path = _confined(root / relative, root)
        except EvidenceError as exc:
            errors.append(str(exc))
            continue
        if not _regular_file(path):
            errors.append(f"missing or non-regular file: {relative}")
            continue
        data = path.read_bytes()
        try:
            expected = validate_digest(entry.get("sha256"), f"{relative}.sha256")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if expected != digest_bytes(data):
            errors.append(f"sha256 mismatch: {relative}")
        if (
            not isinstance(entry.get("sizeBytes"), int)
            or isinstance(entry.get("sizeBytes"), bool)
            or entry["sizeBytes"] < 0
        ):
            errors.append(f"invalid size: {relative}")
        elif entry["sizeBytes"] != len(data):
            errors.append(f"size mismatch: {relative}")
    return errors


def write_manifest(base_dir: Path, output: Path) -> dict[str, Any]:
    root = base_dir.resolve(strict=True)
    target = _confined(output, root)
    files = [path for path in root.rglob("*") if path != target and _regular_file(path)]
    manifest = build_manifest(files, root)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return manifest
