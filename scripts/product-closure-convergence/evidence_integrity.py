#!/usr/bin/env python3
"""Shared fail-closed evidence checks for product closure readiness gates."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^sha256:([0-9a-f]{64})$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_descriptor(value: Any, evidence_root: Path, label: str) -> tuple[bool, str]:
    if not isinstance(value, dict):
        return False, f"{label} must be a file descriptor"
    relative = value.get("path")
    claimed_digest = value.get("sha256")
    claimed_bytes = value.get("bytes")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return False, f"{label}.path must be a non-empty relative path"
    match = SHA256.fullmatch(claimed_digest) if isinstance(claimed_digest, str) else None
    if match is None:
        return False, f"{label}.sha256 must be a canonical sha256 digest"
    if not isinstance(claimed_bytes, int) or isinstance(claimed_bytes, bool) or claimed_bytes <= 0:
        return False, f"{label}.bytes must be a positive integer"
    root = evidence_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return False, f"{label}.path escapes the evidence root"
    if not path.is_file():
        return False, f"{label}.path does not exist"
    if path.stat().st_size != claimed_bytes:
        return False, f"{label}.bytes does not match the evidence file"
    if file_sha256(path) != match.group(1):
        return False, f"{label}.sha256 does not match the evidence file"
    return True, ""


def verify_independent_record(
    value: Any,
    evidence_root: Path,
    label: str,
    *,
    organization_required: bool,
) -> tuple[bool, str]:
    if not isinstance(value, dict):
        return False, f"{label} must be an object"
    required_text = ["executor_id", "verifier_id", "authorization_ref"]
    if organization_required:
        required_text.append("organization_id")
    for field in required_text:
        if not isinstance(value.get(field), str) or not value[field].strip():
            return False, f"{label}.{field} is required"
    if value.get("executor_id") == value.get("verifier_id"):
        return False, f"{label} executor and verifier must be different"
    if value.get("independent") is not True:
        return False, f"{label} must be independently verified"
    if value.get("accepted") is not True:
        return False, f"{label} must be accepted"
    if value.get("authorized_real_execution") is not True:
        return False, f"{label} must bind authorized real execution"
    return verify_file_descriptor(value.get("evidence_file"), evidence_root, f"{label}.evidence_file")
