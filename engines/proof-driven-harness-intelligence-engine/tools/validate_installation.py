#!/usr/bin/env python3
"""Validate the installed PDHI v1 package without executing source ZIP code."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENGINE_SOURCE = ENGINE_ROOT / "src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_pdhi.canonical import strict_json_loads  # noqa: E402
from elmos_pdhi.certification import CertificationEvaluator, ReadinessState  # noqa: E402
from elmos_pdhi.contracts import CertificationLevel  # noqa: E402
from elmos_pdhi.errors import AmbiguousCapabilityError  # noqa: E402
from elmos_pdhi.registry import (  # noqa: E402
    ARCHIVE_SHA256,
    CAPABILITY_OCCURRENCES,
    CAPABILITY_REGISTRY,
    SKILL_REGISTRY,
    resolve_operation,
)
from elmos_pdhi.runtime import RUNTIME_BINDINGS, RuntimeRegistry  # noqa: E402


INTEGRATION_ROOT = ENGINE_ROOT / "integration/v1"
ARCHIVE = REPOSITORY_ROOT / "skills/subskills/sub/elmos-proof-driven-harness-intelligence-v1.0.0.zip"
WRAPPER_ROOTS = (REPOSITORY_ROOT / ".agents/skills", REPOSITORY_ROOT / "agent-skills/runtime")
SCHEMA_NAMES = (
    "agent-task.schema.json",
    "proof-carrying-agent-result.schema.json",
    "patch-transaction.schema.json",
    "evidence-record.schema.json",
    "durable-job-state.schema.json",
    "rule-ir.schema.json",
    "skill-manifest.schema.json",
    "certification-bundle.schema.json",
)


class InstallationValidationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise InstallationValidationError(f"required regular file is missing or unsafe: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Mapping[str, Any]:
    value = strict_json_loads(path.read_bytes(), source=str(path))
    if not isinstance(value, dict):
        raise InstallationValidationError(f"expected JSON object: {path}")
    return value


def _validate_integration_tree() -> Mapping[str, Any]:
    receipt = _json(INTEGRATION_ROOT / "integration-receipt.json")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise InstallationValidationError("integration receipt has no output inventory")
    actual: dict[str, str] = {}
    for relative, expected_digest in outputs.items():
        if not isinstance(relative, str) or not isinstance(expected_digest, str):
            raise InstallationValidationError("integration output inventory is malformed")
        candidate = INTEGRATION_ROOT / relative
        digest = _sha256(candidate)
        if digest != expected_digest:
            raise InstallationValidationError(f"integration output digest drift: {relative}")
        actual[relative] = digest
    boundary = _json(INTEGRATION_ROOT / "UNTRUSTED-SOURCE-BOUNDARY.json")
    if boundary.get("instructions_executed") is not False or boundary.get("archive_code_executed") is not False:
        raise InstallationValidationError("untrusted-source execution boundary drifted")
    return {
        "receipt_digest": receipt.get("receipt_digest"),
        "verified_output_count": len(actual),
    }


def _validate_wrappers() -> Mapping[str, Any]:
    file_count = 0
    for name, descriptor in SKILL_REGISTRY.items():
        left = WRAPPER_ROOTS[0] / name
        right = WRAPPER_ROOTS[1] / name
        for relative in ("SKILL.md", "compiled-contract.json", "agents/openai.yaml"):
            left_digest = _sha256(left / relative)
            right_digest = _sha256(right / relative)
            if left_digest != right_digest:
                raise InstallationValidationError(f"dual-root wrapper drift: {name}/{relative}")
            file_count += 2
        contract = _json(left / "compiled-contract.json")
        skill_contract = contract.get("skill")
        status = contract.get("status")
        if not isinstance(skill_contract, dict) or skill_contract.get("id") != descriptor.skill_id or skill_contract.get("name") != name:
            raise InstallationValidationError(f"wrapper identity drift: {name}")
        if not isinstance(status, dict) or status.get("external_evidence") != "NOT_RUN" or status.get("certification") != "NOT_CERTIFIED":
            raise InstallationValidationError(f"wrapper evidence boundary drift: {name}")
    return {"skill_count": len(SKILL_REGISTRY), "verified_file_count": file_count}


def _validate_schemas() -> Mapping[str, Any]:
    root = ENGINE_ROOT / "schemas/pdhi-v1"
    digests: dict[str, str] = {}
    for name in SCHEMA_NAMES:
        path = root / name
        schema = _json(path)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise InstallationValidationError(f"schema dialect drift: {name}")
        digests[name] = _sha256(path)
    return {"schema_count": len(digests), "digests": digests}


def validate() -> Mapping[str, Any]:
    if _sha256(ARCHIVE) != ARCHIVE_SHA256:
        raise InstallationValidationError("pinned archive digest drifted")
    if len(SKILL_REGISTRY) != 12 or len(CAPABILITY_REGISTRY) != 260 or len(CAPABILITY_OCCURRENCES) != 262:
        raise InstallationValidationError("source registry cardinality drifted")
    if set(RUNTIME_BINDINGS) != set(CAPABILITY_REGISTRY):
        raise InstallationValidationError("runtime capability coverage drifted")
    for ambiguous in ("phase-model-handoff", "steer-agent"):
        try:
            resolve_operation(ambiguous)
        except AmbiguousCapabilityError:
            pass
        else:
            raise InstallationValidationError(f"ambiguous operation resolved without owner: {ambiguous}")
    runtime_manifest = RuntimeRegistry().manifest()
    if runtime_manifest["source_task_id_count"] != 0 or runtime_manifest["source_dependency_edge_count"] != 0:
        raise InstallationValidationError("repository runtime invented source tasks or dependency edges")
    no_evidence = CertificationEvaluator().evaluate(
        project_id="pdhi-installation",
        job_id="pdhi-installation",
        source_revision="sha256:" + "1" * 64,
        target_revision="sha256:" + "2" * 64,
        target_level=CertificationLevel.E0,
        claims=(),
    )
    if no_evidence.readiness is not ReadinessState.BLOCKED or no_evidence.certification_status != "NOT_CERTIFIED":
        raise InstallationValidationError("empty certification evidence did not fail closed")
    result = {
        "status": "PASS",
        "package": "elmos-proof-driven-harness-intelligence@1.0.0",
        "archive_sha256": ARCHIVE_SHA256,
        "skill_count": len(SKILL_REGISTRY),
        "canonical_capability_count": len(CAPABILITY_REGISTRY),
        "source_occurrence_count": len(CAPABILITY_OCCURRENCES),
        "runtime_counts": runtime_manifest["runtime_counts"],
        "integration": _validate_integration_tree(),
        "wrappers": _validate_wrappers(),
        "schemas": _validate_schemas(),
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        result = validate()
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
