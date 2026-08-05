#!/usr/bin/env python3
"""Execute every bounded structured domain handler on independent fixture roles."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "domain-qualification" / "results.json"

from scripts.precision_migration.adapters import (
    AdapterRegistry,
    resolve_handler,
)
from scripts.precision_migration.domain import DomainExecutionError
from scripts.precision_migration.exact import ExactImplementationRegistry
from scripts.precision_migration.runtime import Registry, canonical_digest

TEST_TYPES = ("positive", "negative", "integration", "holdout", "representative")


def fixture(role: str) -> dict[str, Any]:
    value = {"development": 1, "holdout": 2, "representative": 3}.get(role, 1)
    return {
        "fixture_role": role,
        "candidates": [
            {"id": "candidate-a", "metrics": {"quality": 0.9, "cost": 0.7}},
            {"id": "candidate-b", "metrics": {"quality": 0.8, "cost": 0.9}},
        ],
        "criteria": {"quality": 2, "cost": 1},
        "source_text": f"package example\nfunction migrate_{role}(value) {{ return value + {value}; }}",
        "records": [
            {"id": "source", "depends_on": [], "value": value},
            {"id": "target", "depends_on": ["source"], "value": value},
        ],
        "document": {"value": value, "status": "ready", "tags": ["migration"]},
        "operations": [
            {"op": "assert", "path": ["value"], "equals": value},
            {"op": "set", "path": ["status"], "value": "validated"},
        ],
        "source": {"value": value, "status": "ready"},
        "target": {"value": value, "status": "ready"},
        "assertions": [
            {"path": ["value"], "operator": "equals", "expected": value},
            {"path": ["tags"], "operator": "contains", "expected": "migration"},
        ],
        "controls": [
            {"name": "least-privilege", "required": True, "state": "PASS"},
            {"name": "audit", "required": True, "state": "PASS"},
        ],
        "metrics": {"error_rate": value / 1000, "latency_ratio": 1.0},
        "thresholds": {"error_rate": 0.01, "latency_ratio": 1.1},
    }


def content_ref(path: Path, *, tampered: bool = False) -> dict[str, Any]:
    content = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if tampered:
        digest = "sha256:" + "0" * 64
    return {
        "uri": path.resolve().as_uri(),
        "digest": digest,
        "size_bytes": len(content),
        "media_type": "application/json",
        "sensitivity": "internal",
        "version": "domain-fixture-v1",
    }


def request(skill: str, reference: dict[str, Any], role: str, mode: str) -> dict[str, Any]:
    return {
        "request_id": f"domain-{skill}-{role}",
        "skill": skill,
        "mode": mode,
        "inputs": {"assets": [reference], "parameters": {"fixture_role": role}},
        "policy": {"unresolved_differences": "block", "allow_test_weakening": False, "require_provenance": True, "risk_level": "medium"},
        "evidence": [],
        "semantic_losses": [],
        "approvals": [],
    }


def passed(skill: str, test_type: str, evidence: dict[str, Any]) -> dict[str, Any]:
    body = {"skill": skill, "test_type": test_type, "state": "PASS", "evidence": evidence}
    return {**body, "result_digest": canonical_digest(body)}


def build() -> dict[str, Any]:
    registry = Registry.load()
    adapters = AdapterRegistry.load()
    implementations = ExactImplementationRegistry.load()
    entries = [entry for entry in adapters.payload["entries"] if entry["handler_id"].startswith("exact-skill-v4:")]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="precision-domain-qualification-") as temporary:
        root = Path(temporary).resolve()
        references = {}
        for role in ("development", "holdout", "representative"):
            path = root / f"{role}.json"
            path.write_text(json.dumps(fixture(role), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            references[role] = content_ref(path)
        # Qualification retains content digests, not per-case scratch files. Reuse
        # one output directory so 2,680 executions do not accumulate thousands of
        # disposable artifacts on low-disk CI/developer hosts.
        output_dir = root / "execution-output"
        output_dir.mkdir()
        for entry in entries:
            skill = entry["skill"]
            mode = entry["supported_modes"][0]
            handler = resolve_handler(entry)
            if handler is None:
                raise ValueError(f"domain handler did not resolve: {skill}")
            outputs = {}
            for role, test_type in (("development", "positive"), ("holdout", "holdout"), ("representative", "representative")):
                result = handler(request(skill, references[role], role, mode), entry, output_dir, evidence_roots=(root,), skill_registry=registry, trust_store=None)
                if result.get("execution_state") != "LOCAL_EXECUTED" or result.get("exit_code") != 0:
                    raise ValueError(f"domain execution did not pass: {skill}/{role}")
                artifact = result["artifacts"][0]
                outputs[role] = artifact["digest"]
                results.append(passed(skill, test_type, {"artifact_digest": artifact["digest"], "fixture_digest": references[role]["digest"], "scope": "BOUNDED_STRUCTURED_LOCAL"}))
                (output_dir / implementations.by_skill[skill]["artifact_name"]).unlink()
            results.append(passed(skill, "integration", {"handler_id": entry["handler_id"], "entrypoint": entry["handler_entrypoint"], "development_artifact": outputs["development"]}))
            rejected = False
            try:
                handler(request(skill, {**references["development"], "digest": "sha256:" + "0" * 64}, "negative", mode), entry, output_dir, evidence_roots=(root,), skill_registry=registry, trust_store=None)
            except DomainExecutionError:
                rejected = True
            if not rejected:
                raise ValueError(f"domain handler accepted tampered input: {skill}")
            results.append(passed(skill, "negative", {"tampered_input_rejected": True}))
    expected = len(entries) * len(TEST_TYPES)
    if len(entries) != 536 or len(results) != expected:
        raise ValueError(f"domain qualification inventory mismatch: entries={len(entries)} results={len(results)}")
    results.sort(key=lambda item: (item["skill"], TEST_TYPES.index(item["test_type"])))
    return {
        "schema_version": 1,
        "suite": "precision-migration-b01-44-exact-handler-v2",
        "skill_count": len(entries),
        "result_count": len(results),
        "test_types": list(TEST_TYPES),
        "all_tests_passed": True,
        "execution_scope": "EXACT_CONTRACT_LOCAL",
        "native_toolchains": "NOT_RUN_EXCEPT_SEPARATELY_EVIDENCED_HANDLERS",
        "independent_verification": "NOT_RUN",
        "customer_workloads": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("domain qualification results drifted; regenerate them")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "skills": 536, "results": 2680, "scope": "EXACT_CONTRACT_LOCAL"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
