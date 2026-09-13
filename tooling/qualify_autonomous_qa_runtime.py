#!/usr/bin/env python3
"""Generate or verify the bounded Autonomous QA local execution receipt.

The qualifier invokes every exact repository-owned handler with the reviewed
fixture contract.  A blocked or partial result is valid local execution when
it names the missing trusted binder; it is never promoted to external evidence
or certification.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engines/autonomous-qa-engine"
ENGINE_SRC = ENGINE / "src"
FIXTURE = ENGINE / "tests/test_skill_runtime.py"
RECEIPT = ENGINE / "qualification/local-qualification.json"
RUNTIME_MODULE = ENGINE_SRC / "elmos_autonomous_qa/skill_runtime.py"
IMPORTER = ROOT / "tooling/integrate_autonomous_qa_self_healing_skills.py"

if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_autonomous_qa.skill_runtime import (  # noqa: E402
    SKILL_REGISTRY,
    dispatch_skill,
    validate_skill_registry,
)


class QualificationError(RuntimeError):
    """The local runtime cannot produce an exact bounded receipt."""


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _load_fixtures() -> Any:
    spec = importlib.util.spec_from_file_location(
        "elmos_autonomous_qa_qualification_fixture", FIXTURE
    )
    if spec is None or spec.loader is None:
        raise QualificationError("cannot load the reviewed qualification fixture")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "fixtures", None)) or not callable(
        getattr(module, "request", None)
    ):
        raise QualificationError("qualification fixture API drifted")
    return module


def _runtime_authority() -> tuple[str, str]:
    spec = importlib.util.spec_from_file_location(
        "elmos_autonomous_qa_importer", IMPORTER
    )
    if spec is None or spec.loader is None:
        raise QualificationError("cannot load the repository-owned importer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    snapshot = module.validate_archive(ROOT / module.ARCHIVE_RELATIVE)
    runtime = module.validate_runtime_registry(ROOT, snapshot.skills)
    return runtime.module_sha256, runtime.authority_sha256


def build_receipt() -> dict[str, Any]:
    validate_skill_registry()
    fixture_module = _load_fixtures()
    cases = fixture_module.fixtures()
    expected = {binding.source_id for binding in SKILL_REGISTRY.values()}
    if set(cases) != expected:
        raise QualificationError("fixture inventory does not cover the exact registry")

    results: list[dict[str, Any]] = []
    for binding in SKILL_REGISTRY.values():
        result = dispatch_skill(
            binding.skill,
            fixture_module.request(cases[binding.source_id]),
        )
        if result.get("state") not in {"SUCCEEDED", "PARTIAL", "BLOCKED"}:
            raise QualificationError(f"invalid state for {binding.source_id}")
        if result.get("code") in {
            "REQUEST_CONTRACT_REJECTED",
            "LOCAL_HANDLER_OUTPUT_INVALID",
            "LOCAL_HANDLER_FAILED",
            "LOCAL_OPERATION_COMPLETED",
        }:
            raise QualificationError(f"handler did not execute: {binding.source_id}")
        if (
            result.get("handler_id") != binding.handler_id
            or result.get("operation_id") != binding.operation_id
            or result.get("external_evidence") != "NOT_RUN"
            or result.get("certification") != "NOT_CERTIFIED"
        ):
            raise QualificationError(f"result boundary drifted: {binding.source_id}")
        results.append(
            {
                "ordinal": binding.ordinal,
                "source_id": binding.source_id,
                "skill": binding.skill,
                "handler_id": binding.handler_id,
                "operation_id": binding.operation_id,
                "state": result["state"],
                "code": result["code"],
                "result_digest": result["result_digest"],
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            }
        )

    module_digest, authority_digest = _runtime_authority()
    counts = Counter(item["state"] for item in results)
    document: dict[str, Any] = {
        "schema_version": "elmos.autonomous-qa.local-qualification.v1",
        "scope": "BOUNDED_LOCAL_HANDLER_FIXTURES",
        "runtime_evidence_status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "skill_count": len(results),
        "state_counts": {key: counts.get(key, 0) for key in ("SUCCEEDED", "PARTIAL", "BLOCKED")},
        "runtime_module_sha256": module_digest,
        "runtime_authority_sha256": authority_digest,
        "fixture_sha256": _sha256_file(FIXTURE),
        "qualifier_sha256": _sha256_file(Path(__file__)),
        "external_evidence_status": "NOT_RUN",
        "independent_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "results": results,
    }
    document["qualification_digest"] = _sha256_bytes(_canonical_bytes(document))
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--write", action="store_true")
    operation.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = _canonical_bytes(build_receipt())
    if args.write:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_bytes(expected)
        print(json.dumps({"decision": "LOCAL_QUALIFICATION_RECORDED", "skills": 40}))
        return 0
    if not RECEIPT.is_file() or RECEIPT.read_bytes() != expected:
        print(json.dumps({"decision": "BLOCKED", "reason": "local qualification receipt drifted"}))
        return 1
    print(json.dumps({"decision": "LOCAL_QUALIFICATION_VERIFIED", "skills": 40}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
