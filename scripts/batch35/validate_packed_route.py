#!/usr/bin/env python3
"""Replay one packed route's frozen evidence-integrity validation.

This launcher does not build or execute the source/target behavior harnesses and
therefore does not reproduce the native Batch 29 route run.  It does perform
compiler-backed semantic re-lift plus formal replay over the copied,
content-addressed closure artifacts with the frozen Batch 29 validator shipped
beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

REPLAY_SCOPE = "evidence-integrity-and-semantic-closure-only"
NATIVE_REEXECUTION_STATUS = "NOT_RUN"
FROZEN_VALIDATOR_RELATIVE = "certification/replay/scripts/batch29/validate_route.py"
FROZEN_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/formal-equivalence-evidence.schema.json"
)
FROZEN_MODULE_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/module-equivalence-evidence.schema.json"
)
FROZEN_MODULE_CASE_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/module-case-manifest.schema.json"
)
LAUNCHER_RELATIVE = "certification/replay/validate_packed_route.py"
REQUIRED_REPLAY_FILES = {
    LAUNCHER_RELATIVE: "replay-tool",
    FROZEN_VALIDATOR_RELATIVE: "replay-tool",
    FROZEN_SCHEMA_RELATIVE: "replay-schema",
}
MODULE_REPLAY_FILES = {
    FROZEN_MODULE_SCHEMA_RELATIVE: "replay-schema",
    FROZEN_MODULE_CASE_SCHEMA_RELATIVE: "replay-schema",
}


def reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"), parse_constant=reject_non_finite_json
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_route_file(route: Path, relative: str) -> Path:
    if (
        not relative
        or "\\" in relative
        or "://" in relative
        or Path(relative).is_absolute()
        or any(part in {"", ".", ".."} for part in Path(relative).parts)
    ):
        raise ValueError(f"invalid route-relative replay path: {relative}")
    candidate = route / relative
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(route)
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError(f"replay member is not a regular file: {relative}")
    return resolved


def validate_bound_artifact(
    route: Path,
    references: dict[str, dict[str, Any]],
    relative: str,
    role: str,
) -> Path:
    reference = references.get(relative)
    if reference is None or reference.get("role") != role:
        raise ValueError(f"{relative} is not bound as {role}")
    path = resolve_route_file(route, relative)
    if reference.get("sha256") != sha256_file(path):
        raise ValueError(f"{relative} digest mismatch")
    if reference.get("bytes") != path.stat().st_size:
        raise ValueError(f"{relative} byte count mismatch")
    return path


def validate_packed_route(route_arg: Path) -> dict[str, Any]:
    route = route_arg.resolve(strict=True)
    if not route.is_dir():
        raise ValueError(f"route is not a directory: {route_arg}")
    manifest = load_json(route / "route.json")
    certification = load_json(route / "certification" / "certification.json")
    formal_reference = certification.get("formal_equivalence")
    if not isinstance(formal_reference, dict):
        raise ValueError("certification formal_equivalence reference is missing")
    formal_path = resolve_route_file(route, str(formal_reference.get("path", "")))
    formal = load_json(formal_path)
    artifact_refs = formal.get("artifact_refs")
    if not isinstance(artifact_refs, list):
        raise ValueError("formal artifact_refs must be an array")
    references: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for reference in artifact_refs:
        if not isinstance(reference, dict):
            raise ValueError("formal artifact_ref must be an object")
        relative = reference.get("path")
        artifact_id = reference.get("artifact_id")
        if not isinstance(relative, str) or relative in references:
            raise ValueError(f"duplicate or invalid artifact path: {relative}")
        if not isinstance(artifact_id, str) or artifact_id in by_id:
            raise ValueError(f"duplicate or invalid artifact id: {artifact_id}")
        references[relative] = reference
        by_id[artifact_id] = reference

    required_replay_files = dict(REQUIRED_REPLAY_FILES)
    module_reference = certification.get("module_equivalence")
    if module_reference is not None:
        if not isinstance(module_reference, dict):
            raise ValueError("certification module_equivalence reference is invalid")
        required_replay_files.update(MODULE_REPLAY_FILES)
    replay_members = {
        relative: validate_bound_artifact(route, references, relative, role)
        for relative, role in required_replay_files.items()
    }
    if replay_members[LAUNCHER_RELATIVE] != Path(__file__).resolve(strict=True):
        raise ValueError("executed launcher is not the wrapper-bound launcher")

    namespace = runpy.run_path(
        str(replay_members[FROZEN_VALIDATOR_RELATIVE]),
        run_name="elmos_packed_batch29_validate_route",
    )
    validator = namespace.get("validate_formal_equivalence")
    if not callable(validator):
        raise ValueError("frozen Batch 29 formal validator is unavailable")
    _validated, failures = validator(route, manifest, certification)
    if failures:
        raise ValueError("; ".join(str(item) for item in failures))
    if module_reference is not None:
        module_validator = namespace.get("validate_packed_module_equivalence")
        if not callable(module_validator):
            raise ValueError("frozen Batch 29 packed module validator is unavailable")
        _validated_module, module_failures = module_validator(
            route,
            manifest,
            certification,
        )
        if module_failures:
            raise ValueError("; ".join(str(item) for item in module_failures))

    replay = formal.get("formal_proof", {}).get("replay")
    if not isinstance(replay, dict):
        raise ValueError("formal replay record is missing")
    expected_id = replay.get("expected_result_artifact_id")
    expected_digest = replay.get("expected_result_sha256")
    result_reference = by_id.get(expected_id)
    if result_reference is None or result_reference.get("role") != "solver-result":
        raise ValueError("expected replay result is not bound as solver-result")
    result_path = resolve_route_file(route, str(result_reference.get("path", "")))
    if (
        result_reference.get("sha256") != expected_digest
        or sha256_file(result_path) != expected_digest
        or result_reference.get("bytes") != result_path.stat().st_size
    ):
        raise ValueError("expected replay solver-result digest/bytes mismatch")

    return {
        "status": "PASSED",
        "route_key": manifest.get("route_key"),
        "scope": REPLAY_SCOPE,
        "native_route_reexecution": NATIVE_REEXECUTION_STATUS,
        "expected_result_artifact_id": expected_id,
        "expected_result_sha256": expected_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_packed_route(args.route)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "scope": REPLAY_SCOPE,
                    "native_route_reexecution": NATIVE_REEXECUTION_STATUS,
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
