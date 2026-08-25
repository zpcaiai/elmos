#!/usr/bin/env python3
"""Render/check the exact OpenAPI top-level input-field contract.

The runtime registry remains the authority.  This tool emits a Draft 2020-12
conditional schema so every documented Skill/operation pair rejects unknown or
missing top-level input fields exactly as the runtime and checked-in SDKs do.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))

from elmos_multimodal_intake.canonical import canonical_json  # noqa: E402
from elmos_multimodal_intake.operation_registry import (  # noqa: E402
    OPERATION_REGISTRY,
    OPERATION_REGISTRY_DIGEST,
)


TARGETS = (
    ENGINE_ROOT / "openapi" / "operation-input-contracts.schema.json",
    ENGINE_ROOT
    / "src"
    / "elmos_multimodal_intake"
    / "_data"
    / "openapi"
    / "operation-input-contracts.schema.json",
)


def schema_document() -> dict[str, Any]:
    clauses: list[dict[str, Any]] = []
    for (skill, operation), spec in sorted(OPERATION_REGISTRY.items()):
        input_schema: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {field: {} for field in sorted(spec.input_fields)},
        }
        if spec.required_input_fields:
            input_schema["required"] = sorted(spec.required_input_fields)
        clauses.append(
            {
                "if": {
                    "required": ["skill", "operation"],
                    "properties": {
                        "skill": {"const": skill},
                        "operation": {"const": operation},
                    },
                },
                "then": {
                    "required": ["input"],
                    "properties": {"input": input_schema},
                },
            }
        )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.local/schemas/multimodal-operation-input-contracts-v1.schema.json",
        "title": "ELMOS multimodal exact operation input fields",
        "type": "object",
        "x-elmos-operation-count": len(OPERATION_REGISTRY),
        "x-elmos-operation-registry-digest": OPERATION_REGISTRY_DIGEST,
        "allOf": clauses,
    }


def rendered_bytes() -> bytes:
    document = schema_document()
    # The repository's canonical encoder rejects non-finite and unsafe JSON;
    # pretty formatting keeps the generated contract reviewable.
    canonical_json(document)
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def write_target(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = rendered_bytes()
    if args.write:
        for target in TARGETS:
            write_target(target, data)
    else:
        for target in TARGETS:
            if not target.is_file() or target.read_bytes() != data:
                raise SystemExit(f"operation input schema drift: {target}")
    print(
        json.dumps(
            {
                "operation_count": len(OPERATION_REGISTRY),
                "sha256": hashlib.sha256(data).hexdigest(),
                "targets": [str(path.relative_to(REPOSITORY_ROOT)) for path in TARGETS],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
