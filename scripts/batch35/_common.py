#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path, PurePosixPath

GATE_OUTPUT_REFS = {
    "certification/gate-report.md",
    "certification/gate-result.json",
}


def load(path):
    def reject_non_finite(value: str):
        raise ValueError(f"non-finite JSON number is forbidden: {value}")

    return json.loads(Path(path).read_text(), parse_constant=reject_non_finite)


def write(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2) + "\n")


def real_files(path):
    root = Path(path)
    return [
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file()
        and candidate.name not in {".gitkeep", "README.md"}
        and candidate.stat().st_size > 0
    ]


def local_ref_path(pack, ref):
    if not isinstance(ref, str) or not ref:
        return None
    logical = PurePosixPath(ref)
    if logical.is_absolute() or not logical.parts or ".." in logical.parts:
        return None
    try:
        root = Path(pack).resolve(strict=True)
        current = root
        for part in logical.parts:
            current = current / part
            if current.is_symlink():
                return None
        resolved = current.resolve(strict=True)
        if root not in (resolved, *resolved.parents):
            return None
        if not stat.S_ISREG(resolved.stat().st_mode):
            return None
        return resolved
    except (OSError, ValueError):
        return None


def resolve_ref(pack, ref):
    return isinstance(ref, str) and (
        ref.startswith(("http://", "https://")) or local_ref_path(pack, ref) is not None
    )


def pack_content_digest(pack):
    """Digest the complete regular-file pack snapshot, excluding gate outputs."""

    root = Path(pack).resolve(strict=True)
    digest = hashlib.sha256()
    for candidate in sorted(root.rglob("*"), key=lambda path: path.as_posix()):
        relative = candidate.relative_to(root).as_posix()
        if relative in GATE_OUTPUT_REFS:
            continue
        if candidate.is_symlink():
            raise ValueError(f"pack snapshot contains a symlink: {relative}")
        mode = candidate.stat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"pack snapshot contains a non-regular file: {relative}")
        payload = candidate.read_bytes()
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def repository_binding_records(pack):
    """Load immutable copies of the repository binding records declared by a pack."""

    evidence_path = local_ref_path(pack, "certification/evidence.json")
    if evidence_path is None:
        return []
    evidence = load(evidence_path)
    refs = evidence.get("repository_binding_records", [])
    if not isinstance(refs, list):
        raise TypeError("repository_binding_records must be an array")
    records = []
    for ref in refs:
        record_path = local_ref_path(pack, ref)
        if record_path is None:
            raise ValueError(f"repository binding record is missing or unsafe: {ref}")
        record = load(record_path)
        if not isinstance(record, dict):
            raise TypeError(f"repository binding record is not an object: {ref}")
        records.append((ref, record))
    return records


def repository_files_digest(records, repository_root):
    """Digest and independently verify the live files named by binding records."""

    digest = hashlib.sha256()
    errors = []
    for record_ref, record in records:
        bindings = record.get("repository_bindings")
        if not isinstance(bindings, list) or not bindings:
            errors.append(f"repository_bindings must be non-empty: {record_ref}")
            continue
        for binding in bindings:
            if not isinstance(binding, dict):
                errors.append(f"repository binding is not an object: {record_ref}")
                continue
            path = binding.get("path")
            resolved = local_ref_path(repository_root, path)
            if resolved is None:
                errors.append(f"repository binding path is missing or unsafe: {path}")
                continue
            payload = resolved.read_bytes()
            actual = "sha256:" + hashlib.sha256(payload).hexdigest()
            if (
                isinstance(binding.get("byte_size"), bool)
                or binding.get("byte_size") != len(payload)
            ):
                errors.append(f"repository binding byte_size mismatch: {path}")
            if binding.get("sha256") != actual:
                errors.append(f"repository binding sha256 mismatch: {path}")
            for value in (record_ref, binding.get("role", ""), path):
                encoded = str(value).encode("utf-8")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return "sha256:" + digest.hexdigest(), errors


def evaluated_pack_digest(pack_digest, repository_digest):
    payload = f"batch35-evaluated-pack-v1\n{pack_digest}\n{repository_digest}\n"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
