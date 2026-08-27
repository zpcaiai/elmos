from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
from .hashing import sha256_bytes, sha256_value

class EvidenceError(ValueError):
    pass

def build_manifest(files: Iterable[Path], base_dir: Path) -> dict:
    entries = []
    for file in sorted(files):
        if not file.is_file():
            continue
        resolved = file.resolve()
        try:
            relative = resolved.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise EvidenceError(f"file escapes bundle root: {file}") from exc
        data = resolved.read_bytes()
        entries.append({
            "path": relative.as_posix(),
            "sha256": sha256_bytes(data),
            "sizeBytes": len(data),
        })
    manifest = {"format": "elmos-proof-evidence-bundle/v1", "files": entries}
    manifest["manifestSha256"] = sha256_value(manifest)
    return manifest

def verify_manifest(manifest: dict, base_dir: Path) -> list[str]:
    errors: list[str] = []
    expected_manifest_hash = manifest.get("manifestSha256")
    unsigned = {k:v for k,v in manifest.items() if k != "manifestSha256"}
    if expected_manifest_hash != sha256_value(unsigned):
        errors.append("manifest hash mismatch")
    for entry in manifest.get("files", []):
        path = (base_dir / entry["path"]).resolve()
        try:
            path.relative_to(base_dir.resolve())
        except ValueError:
            errors.append(f"path escapes bundle root: {entry['path']}")
            continue
        if not path.is_file():
            errors.append(f"missing file: {entry['path']}")
            continue
        data = path.read_bytes()
        if sha256_bytes(data) != entry["sha256"]:
            errors.append(f"sha256 mismatch: {entry['path']}")
        if len(data) != entry["sizeBytes"]:
            errors.append(f"size mismatch: {entry['path']}")
    return errors

def write_manifest(base_dir: Path, output: Path) -> dict:
    files = [p for p in base_dir.rglob("*") if p.is_file() and p.resolve() != output.resolve()]
    manifest = build_manifest(files, base_dir)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
