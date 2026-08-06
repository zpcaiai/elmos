#!/usr/bin/env python3
"""Fail-closed production-code closure gate for Precision Migration B01-B44.

This gate proves checked-in code, identity, qualification, and conservative
release wiring. It can prepare READY_FOR_EXTERNAL_GATE, but it cannot create
native provider, customer, HSM, canary, production, or certification evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.precision_migration.adapters import AdapterRegistry
from scripts.precision_migration.exact import ExactImplementationRegistry, PROGRAM_OPERATIONS
from scripts.precision_migration.external import ExternalProfileRegistry, scaffold as external_scaffold
from scripts.precision_migration.native import EXTERNAL_NATIVE_ADAPTERS, NATIVE_ADAPTERS
from scripts.precision_migration.orchestration import OrchestratorRegistry, _topological


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "verification-packs" / "precision-migration-b01-44-runtime"
OUTPUT = PACK / "certification" / "production-code-closure.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def build() -> dict[str, Any]:
    failures: list[str] = []
    manifest_path = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
    manifest = load(manifest_path)
    adapters = AdapterRegistry.load()
    exact = ExactImplementationRegistry.load()
    orchestrators = OrchestratorRegistry.load()
    external_profiles = ExternalProfileRegistry.load()
    external_readiness_path = PACK / "external-readiness" / "current.json"
    require(external_readiness_path.is_file(), "checked-in external readiness state is missing", failures)
    if external_readiness_path.is_file():
        require(load(external_readiness_path) == external_scaffold(), "checked-in external readiness state must remain exact NOT_RUN scaffold", failures)

    require(manifest.get("runtime_skill_count") == 632, "installed manifest must contain 632 Runtime Skills", failures)
    require(manifest.get("workspace_skill_count") == 632, "workspace mirror must contain 632 Skills", failures)
    require(manifest.get("maturity_counts") == {"LOCAL_EXECUTED": 632}, "all installed identities must be LOCAL_EXECUTED", failures)
    require(len(adapters.by_skill) == 632, "adapter registry must contain 632 identities", failures)
    handler_errors = adapters.validate_handlers()
    failures.extend(f"adapter: {message}" for message in handler_errors)

    families = Counter(entry["handler_id"].split(":", 1)[0] for entry in adapters.by_skill.values())
    expected_families = {
        "exact-skill-v4": 536,
        "orchestrator-dag-v2": 45,
        "batch29-route-executor-v1": 30,
    }
    for family, count in expected_families.items():
        require(families.get(family) == count, f"handler family {family} must contain {count} entries", failures)

    classified_tools = set(NATIVE_ADAPTERS) | set(EXTERNAL_NATIVE_ADAPTERS)
    exact_entrypoints: set[str] = set()
    exact_programs: set[str] = set()
    for profile in exact.by_handler.values():
        require(profile.get("schema_version") == 2, f"exact profile schema is not v2: {profile.get('skill')}", failures)
        require(str(profile.get("handler_id", "")).startswith("exact-skill-v4:"), f"exact handler is not v4: {profile.get('skill')}", failures)
        require(profile.get("program_version") == "precision-exact-program-v1", f"exact program version is invalid: {profile.get('skill')}", failures)
        program = profile.get("program", [])
        require([step.get("op") for step in program] == list(PROGRAM_OPERATIONS), f"exact program operations are incomplete: {profile.get('skill')}", failures)
        require(set(profile.get("native_tools", [])) <= classified_tools, f"native tool has no fail-closed adapter classification: {profile.get('skill')}", failures)
        exact_entrypoints.add(str(profile.get("handler_entrypoint")))
        exact_programs.add(str(profile.get("implementation_digest")))
    require(len(exact_entrypoints) == 536, "exact handler entrypoints must be unique", failures)
    require(len(exact_programs) == 536, "exact Skill programs must have unique implementation digests", failures)
    require(len(external_profiles.by_skill) == 557, "external execution profiles must cover 557 non-B16 Skills", failures)
    b16_skills = {
        skill for skill, entry in adapters.by_skill.items()
        if str(entry.get("handler_id", "")).startswith("batch29-route-executor-v1:")
    }
    require(
        set(external_profiles.by_skill).isdisjoint(b16_skills)
        and set(external_profiles.by_skill) | b16_skills
        == {skill for skill, entry in adapters.by_skill.items() if entry.get("kind") == "skill"},
        "external profiles and B16 routes must partition all 587 child Skills",
        failures,
    )

    for profile in orchestrators.by_handler.values():
        order = _topological(list(profile["nodes"]), list(profile["edges"]))
        require(len(order) == len(profile["nodes"]), f"orchestrator DAG is incomplete: {profile['skill']}", failures)
        for node in profile["nodes"]:
            require(node in adapters.by_skill, f"orchestrator child is not installed: {profile['skill']}/{node}", failures)

    qualification_files = {
        "contract": PACK / "contract-qualification" / "results.json",
        "exact": PACK / "domain-qualification" / "results.json",
        "orchestrator": PACK / "orchestrator-qualification" / "results.json",
        "b16": PACK / "b16-qualification" / "results.json",
        "b41": PACK / "b41-qualification" / "results.json",
        "specialized": PACK / "specialized-qualification" / "results.json",
    }
    expected_results = {
        "contract": (587, 2935),
        "exact": (536, 2680),
        "orchestrator": (45, 225),
        "b16": (30, 150),
        "b41": (10, 50),
        "specialized": (11, 55),
    }
    qualification_evidence: dict[str, Any] = {}
    for key, path in qualification_files.items():
        payload = load(path)
        skill_count, result_count = expected_results[key]
        observed_skills = payload.get("skill_count", payload.get("orchestrator_count"))
        require(observed_skills == skill_count, f"{key} qualification Skill count drifted", failures)
        require(payload.get("result_count") == result_count, f"{key} qualification result count drifted", failures)
        passed_flag = payload.get("all_contract_tests_passed") if key == "contract" else payload.get("all_tests_passed")
        require(passed_flag is True, f"{key} qualification is not fully passed", failures)
        qualification_evidence[key] = {"digest": digest(path), "skills": skill_count, "results": result_count}

    external_engineering_path = PACK / "external-engineering-qualification" / "results.json"
    external_engineering = load(external_engineering_path)
    require(external_engineering.get("skill_count") == 557, "external engineering Skill count drifted", failures)
    require(external_engineering.get("case_count") == 2785, "external engineering case count drifted", failures)
    require(external_engineering.get("result_count") == 2785, "external engineering result count drifted", failures)
    require(external_engineering.get("actual_handler_invocation_count") == 2785, "external engineering handler invocation count drifted", failures)
    require(external_engineering.get("all_engineering_tests_passed") is True, "external engineering suite is not fully passed", failures)
    require(external_engineering.get("evidence_class") == "LOCAL_ENGINEERING_SIMULATION", "external engineering evidence class is invalid", failures)
    require(external_engineering.get("production_eligible") is False, "external engineering evidence must not be production eligible", failures)
    require(
        external_engineering.get("release_engineering_drill", {}).get("state") == "PASS"
        and external_engineering.get("release_engineering_drill", {}).get("test_count") == 8,
        "external release engineering drill is incomplete",
        failures,
    )
    require(
        external_engineering.get("real_external_state", {}).get("decision") == "NOT_READY"
        and external_engineering.get("real_external_state", {}).get("verified_skill_count") == 0
        and external_engineering.get("real_external_state", {}).get("production_operation_authorized") is False
        and external_engineering.get("real_external_state", {}).get("production_certification") == "NOT_CERTIFIED",
        "external engineering result must preserve the real NOT_READY boundary",
        failures,
    )
    qualification_evidence["external_engineering"] = {
        "digest": digest(external_engineering_path),
        "skills": 557,
        "results": 2785,
        "evidence_class": "LOCAL_ENGINEERING_SIMULATION",
        "production_eligible": False,
    }

    coverage_path = PACK / "coverage" / "coverage-matrix.json"
    coverage = load(coverage_path)
    summaries = coverage.get("summaries", {})
    for dimension in (
        "bounded_domain_positive", "bounded_domain_negative", "bounded_domain_integration",
        "bounded_domain_holdout", "bounded_domain_representative", "local_execution",
    ):
        require(summaries.get(dimension) == {"PASSED": 587}, f"coverage dimension is incomplete: {dimension}", failures)
    require(summaries.get("external_execution_profile") == {"DECLARED": 557, "NOT_APPLICABLE": 30}, "external execution profile coverage is incomplete", failures)
    require(summaries.get("production_workflow_code") == {"PASSED": 587}, "production workflow code coverage is incomplete", failures)
    for dimension in (
        "external_engineering_positive",
        "external_engineering_negative",
        "external_engineering_integration",
        "external_engineering_holdout_fixture",
        "external_engineering_representative_fixture",
    ):
        require(
            summaries.get(dimension) == {"NOT_APPLICABLE": 30, "PASSED": 557},
            f"external engineering coverage is incomplete: {dimension}",
            failures,
        )
    require(summaries.get("external_evidence") == {"NOT_RUN": 587}, "external evidence boundary must remain NOT_RUN", failures)
    require(summaries.get("independent_verification") == {"NOT_RUN": 587}, "independent verification boundary must remain NOT_RUN", failures)

    status = "PASSED" if not failures else "FAILED"
    runtime_code = {
        path: digest(ROOT / path)
        for path in (
            "scripts/precision_migration/adapters.py",
            "scripts/precision_migration/exact.py",
            "scripts/precision_migration/external.py",
            "scripts/precision_migration/generated_handlers.py",
            "scripts/precision_migration/generated_orchestrators.py",
            "scripts/precision_migration/native.py",
            "scripts/precision_migration/orchestration.py",
            "scripts/precision_migration/production_runtime.py",
            "scripts/precision_migration/qualify_external_engineering.py",
            "scripts/precision_migration/runtime.py",
            "scripts/precision_migration/trust.py",
            "tooling/generate_precision_migration_handlers.py",
            "tooling/generate_precision_migration_external_profiles.py",
            "tooling/generate_precision_migration_external_engineering_cases.py",
            "tooling/integrate_precision_migration_batch1_44.py",
        )
    }
    return {
        "schema_version": 1,
        "gate": "precision-migration-b01-44-production-code-closure",
        "status": status,
        "decision": "READY_FOR_EXTERNAL_GATE" if status == "PASSED" else "BLOCKED",
        "production_certification": "NOT_CERTIFIED",
        "production_operation_authorized": False,
        "scope": {
            "runtime_skills": 632,
            "child_skills": 587,
            "orchestrators": 45,
            "exact_programs": 536,
            "specialized_handlers": 51,
        },
        "handler_families": dict(sorted(families.items())),
        "qualification": qualification_evidence,
        "external_workflow_code": {
            "profile_registry_digest": external_profiles.digest,
            "profile_count": len(external_profiles.by_skill),
            "required_skill_stages": list(external_profiles.payload["required_stages"]),
            "required_release_stages": list(external_profiles.payload["release_stages"]),
            "current_evidence_state": external_scaffold()["stage_states"],
            "engineering_simulation": {
                "case_count": 2785,
                "actual_handler_invocation_count": 2785,
                "release_drill_test_count": 8,
                "decision": "PASSED_LOCAL_ENGINEERING_SIMULATION",
                "production_eligible": False,
            },
        },
        "bindings": {
            "installed_manifest": digest(manifest_path),
            "adapter_registry": digest(ROOT / "docs" / "precision-migration-b01-44" / "adapter-registry.json"),
            "exact_registry": digest(ROOT / "docs" / "precision-migration-b01-44" / "handler-implementations.json"),
            "orchestrator_registry": digest(ROOT / "docs" / "precision-migration-b01-44" / "orchestrator-implementations.json"),
            "coverage_matrix": digest(coverage_path),
            "external_execution_profiles": digest(ROOT / "docs" / "precision-migration-b01-44" / "external-execution-profiles.json"),
            "external_engineering_cases": digest(PACK / "external-engineering-qualification" / "cases.json"),
            "external_engineering_results": digest(external_engineering_path),
            "external_readiness": digest(external_readiness_path) if external_readiness_path.is_file() else None,
            "runtime_code": runtime_code,
        },
        "external_boundaries": {
            "native_toolchain_outside_local_evidence": "NOT_RUN",
            "independent_holdout": "NOT_RUN",
            "customer_workloads": "NOT_RUN",
            "production_hsm": "NOT_RUN",
            "authorized_canary_and_rollback": "NOT_RUN",
            "production_evidence": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("production code closure result drifted; regenerate it")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": payload["status"], "decision": payload["decision"], "failures": payload["failures"]}, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
