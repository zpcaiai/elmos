"""Hidden-test and benchmark-integrity boundary checks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .canonical import digest_json


def validate_hidden_test_boundary(public_paths: Iterable[str], hidden_paths: Iterable[str], *, worker_role: str) -> dict[str, object]:
    public = {str(Path(value).as_posix()) for value in public_paths}
    hidden = {str(Path(value).as_posix()) for value in hidden_paths}
    overlap = sorted(public & hidden)
    errors: list[str] = []
    if overlap:
        errors.append("public and hidden partitions overlap")
    if worker_role in {"transform-worker", "generation-worker"} and hidden:
        errors.append("transform/generation workers cannot receive hidden-test paths")
    if worker_role not in {"transform-worker", "generation-worker", "validation-worker", "orchestrator"}:
        errors.append(f"unsupported worker role: {worker_role}")
    return {"valid": not errors, "worker_role": worker_role, "public_count": len(public), "hidden_count": len(hidden), "overlap": overlap, "public_digest": digest_json(sorted(public)), "hidden_digest": digest_json(sorted(hidden)), "errors": errors, "status": "BOUNDARY_VALID" if not errors else "BLOCKED"}
