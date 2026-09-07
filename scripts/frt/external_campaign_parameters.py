#!/usr/bin/env python3
"""Typed, fail-closed parameters for FRT external qualification campaigns.

The authorization envelope stores these parameters, but repository content may
not turn them into commands.  Each check has an exact shape, is bound to the
current 15-case qualification plan, and carries only opaque identifiers,
digests, frozen budgets and secret references.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PLAN = (
    ROOT
    / "client-packs"
    / "frt-g01-g30-platform"
    / "acceptance"
    / "external-qualification-plan.json"
)

CHECK_IDS = (
    "real_source_target_builds",
    "device_matrix",
    "independent_holdout",
    "formal_proof",
    "performance",
    "chaos_dr",
    "penetration_test",
    "production_observation",
    "customer_acceptance",
)

COMMON_KEYS = {
    "schema_version",
    "qualification_plan_sha256",
    "case_ids",
    "adapter_ids",
    "authorization_scope",
    "secret_reference_ids",
}

CHECK_KEYS: dict[str, set[str]] = {
    "real_source_target_builds": {
        "repository_commits",
        "route_ids",
        "startup_probe_ids",
        "cleanup_policy_id",
    },
    "device_matrix": {
        "quality_profile_ids",
        "device_inventory_sha256",
        "approved_baseline_manifest_sha256",
        "assistive_technology_profiles",
        "cleanup_policy_id",
    },
    "independent_holdout": {
        "corpus_manifest_sha256",
        "development_corpus_sha256",
        "case_count",
        "independence_attestation_id",
        "executor_organization_id",
    },
    "formal_proof": {
        "solver_name",
        "solver_version",
        "solver_options",
        "bounds",
        "obligation_ids",
        "counterexample_replay_version",
    },
    "performance": {
        "workload_manifest_sha256",
        "workload_count",
        "samples_per_workload",
        "warmup_samples",
        "budgets_sha256",
        "telemetry_profile_id",
    },
    "chaos_dr": {
        "drill_plan_sha256",
        "scenario_count",
        "rpo_budget_seconds",
        "rto_budget_seconds",
        "fault_injection_profile_id",
        "cleanup_policy_id",
    },
    "penetration_test": {
        "assessment_scope_sha256",
        "target_count",
        "written_authorization_id",
        "tool_profile_ids",
        "manual_test_plan_sha256",
        "retest_required",
    },
    "production_observation": {
        "deployment_artifact_sha256",
        "environment_id",
        "observation_minutes",
        "slo_manifest_sha256",
        "alert_routes_sha256",
        "telemetry_query_profile_id",
        "read_only",
    },
    "customer_acceptance": {
        "organization_count",
        "participant_count",
        "p0_task_count",
        "consent_template_sha256",
        "journey_scope_sha256",
        "facilitator_policy_id",
        "independent_review_id",
        "decision_authority",
    },
}

SCOPE_KEYS = {
    "tenant_id",
    "project_id",
    "environment_id",
    "region",
    "data_classification",
    "network_policy_id",
    "write_root_id",
}
REPOSITORY_COMMIT_KEYS = {
    "repository_id",
    "source_commit",
    "target_commit",
}
DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}(?:[a-f0-9]{24})?$")


def load_plan(plan_path: Path = PLAN) -> dict[str, Any]:
    return json.loads(plan_path.read_text(encoding="utf-8"))


def digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def expected_case_contract(
    check_id: str,
    plan_path: Path = PLAN,
) -> tuple[list[str], list[str]]:
    plan = load_plan(plan_path)
    cases = [
        case
        for case in plan.get("cases", [])
        if isinstance(case, dict) and case.get("external_check_id") == check_id
    ]
    return (
        [str(case.get("case_id")) for case in cases],
        [str(case.get("adapter_id")) for case in cases],
    )


def exact_keys(value: Any, expected: set[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    if set(value) != expected:
        return [
            f"{label} fields must be exact; missing={sorted(expected - set(value))} "
            f"unexpected={sorted(set(value) - expected)}"
        ]
    return []


def validate_digest(value: Any, label: str) -> list[str]:
    if not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value):
        return [f"{label} must be a sha256 digest"]
    return []


def validate_identifier(value: Any, label: str) -> list[str]:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        return [f"{label} must be an opaque identifier"]
    return []


def validate_string_list(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or len(set(value)) != len(value)
        or any(validate_identifier(item, label) for item in value)
    ):
        return [f"{label} must be a unique opaque-identifier array with at least {minimum} item(s)"]
    return []


def validate_integer(value: Any, label: str, minimum: int) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return [f"{label} must be an integer at least {minimum}"]
    return []


def validate_scope(value: Any) -> list[str]:
    failures = exact_keys(value, SCOPE_KEYS, "run_parameters.authorization_scope")
    if not isinstance(value, dict):
        return failures
    for field in SCOPE_KEYS - {"data_classification"}:
        failures.extend(validate_identifier(value.get(field), f"authorization_scope.{field}"))
    if value.get("data_classification") not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL"}:
        failures.append("authorization_scope.data_classification is invalid")
    return failures


def validate_campaign_parameters(
    check_id: str,
    value: Any,
    *,
    plan_path: Path = PLAN,
) -> list[str]:
    if check_id not in CHECK_KEYS:
        return [f"unsupported external check: {check_id}"]
    expected_keys = COMMON_KEYS | CHECK_KEYS[check_id]
    failures = exact_keys(value, expected_keys, f"{check_id} run_parameters")
    if not isinstance(value, dict):
        return failures
    if value.get("schema_version") != 1:
        failures.append("run_parameters.schema_version must be 1")
    failures.extend(validate_digest(value.get("qualification_plan_sha256"), "qualification_plan_sha256"))
    if value.get("qualification_plan_sha256") != digest_file(plan_path):
        failures.append("qualification_plan_sha256 does not bind the current plan bytes")
    expected_cases, expected_adapters = expected_case_contract(check_id, plan_path)
    if value.get("case_ids") != expected_cases:
        failures.append(f"case_ids must exactly equal {expected_cases}")
    if value.get("adapter_ids") != expected_adapters:
        failures.append(f"adapter_ids must exactly equal {expected_adapters}")
    failures.extend(validate_scope(value.get("authorization_scope")))
    secret_refs = value.get("secret_reference_ids")
    if not isinstance(secret_refs, list) or len(set(secret_refs)) != len(secret_refs):
        failures.append("secret_reference_ids must be a unique array")
    elif any(validate_identifier(item, "secret_reference_ids") for item in secret_refs):
        failures.append("secret_reference_ids may contain only opaque identifiers")

    if check_id == "real_source_target_builds":
        repositories = value.get("repository_commits")
        if not isinstance(repositories, list) or not repositories:
            failures.append("repository_commits must be a non-empty array")
        else:
            repository_ids: set[str] = set()
            for index, repository in enumerate(repositories):
                label = f"repository_commits[{index}]"
                failures.extend(exact_keys(repository, REPOSITORY_COMMIT_KEYS, label))
                if not isinstance(repository, dict):
                    continue
                failures.extend(validate_identifier(repository.get("repository_id"), f"{label}.repository_id"))
                repository_id = repository.get("repository_id")
                if isinstance(repository_id, str):
                    if repository_id in repository_ids:
                        failures.append(f"duplicate repository_id: {repository_id}")
                    repository_ids.add(repository_id)
                for field in ("source_commit", "target_commit"):
                    if not isinstance(repository.get(field), str) or not COMMIT_PATTERN.fullmatch(repository[field]):
                        failures.append(f"{label}.{field} must be an exact 40- or 64-hex commit")
        for field in ("route_ids", "startup_probe_ids"):
            failures.extend(validate_string_list(value.get(field), field))
        failures.extend(validate_identifier(value.get("cleanup_policy_id"), "cleanup_policy_id"))

    elif check_id == "device_matrix":
        failures.extend(validate_string_list(value.get("quality_profile_ids"), "quality_profile_ids", minimum=5))
        failures.extend(validate_digest(value.get("device_inventory_sha256"), "device_inventory_sha256"))
        failures.extend(validate_digest(value.get("approved_baseline_manifest_sha256"), "approved_baseline_manifest_sha256"))
        failures.extend(validate_string_list(value.get("assistive_technology_profiles"), "assistive_technology_profiles", minimum=1))
        failures.extend(validate_identifier(value.get("cleanup_policy_id"), "cleanup_policy_id"))

    elif check_id == "independent_holdout":
        for field in ("corpus_manifest_sha256", "development_corpus_sha256"):
            failures.extend(validate_digest(value.get(field), field))
        failures.extend(validate_integer(value.get("case_count"), "case_count", 1))
        failures.extend(validate_identifier(value.get("independence_attestation_id"), "independence_attestation_id"))
        failures.extend(validate_identifier(value.get("executor_organization_id"), "executor_organization_id"))

    elif check_id == "formal_proof":
        for field in ("solver_name", "solver_version", "counterexample_replay_version"):
            failures.extend(validate_identifier(value.get(field), field))
        failures.extend(validate_string_list(value.get("solver_options"), "solver_options"))
        failures.extend(validate_string_list(value.get("obligation_ids"), "obligation_ids"))
        bounds = value.get("bounds")
        if not isinstance(bounds, dict) or not bounds:
            failures.append("bounds must be a non-empty object")
        else:
            for name, bound in bounds.items():
                failures.extend(validate_identifier(name, "bounds key"))
                failures.extend(validate_integer(bound, f"bounds.{name}", 1))

    elif check_id == "performance":
        for field in ("workload_manifest_sha256", "budgets_sha256"):
            failures.extend(validate_digest(value.get(field), field))
        failures.extend(validate_integer(value.get("workload_count"), "workload_count", 1))
        failures.extend(validate_integer(value.get("samples_per_workload"), "samples_per_workload", 5))
        failures.extend(validate_integer(value.get("warmup_samples"), "warmup_samples", 1))
        failures.extend(validate_identifier(value.get("telemetry_profile_id"), "telemetry_profile_id"))

    elif check_id == "chaos_dr":
        failures.extend(validate_digest(value.get("drill_plan_sha256"), "drill_plan_sha256"))
        failures.extend(validate_integer(value.get("scenario_count"), "scenario_count", 1))
        failures.extend(validate_integer(value.get("rpo_budget_seconds"), "rpo_budget_seconds", 0))
        failures.extend(validate_integer(value.get("rto_budget_seconds"), "rto_budget_seconds", 1))
        failures.extend(validate_identifier(value.get("fault_injection_profile_id"), "fault_injection_profile_id"))
        failures.extend(validate_identifier(value.get("cleanup_policy_id"), "cleanup_policy_id"))

    elif check_id == "penetration_test":
        for field in ("assessment_scope_sha256", "manual_test_plan_sha256"):
            failures.extend(validate_digest(value.get(field), field))
        failures.extend(validate_integer(value.get("target_count"), "target_count", 1))
        failures.extend(validate_identifier(value.get("written_authorization_id"), "written_authorization_id"))
        failures.extend(validate_string_list(value.get("tool_profile_ids"), "tool_profile_ids"))
        if value.get("retest_required") is not True:
            failures.append("retest_required must be true")

    elif check_id == "production_observation":
        for field in ("deployment_artifact_sha256", "slo_manifest_sha256", "alert_routes_sha256"):
            failures.extend(validate_digest(value.get(field), field))
        failures.extend(validate_identifier(value.get("environment_id"), "environment_id"))
        failures.extend(validate_integer(value.get("observation_minutes"), "observation_minutes", 60))
        failures.extend(validate_identifier(value.get("telemetry_query_profile_id"), "telemetry_query_profile_id"))
        if value.get("read_only") is not True:
            failures.append("production observation must be read_only")

    elif check_id == "customer_acceptance":
        failures.extend(validate_integer(value.get("organization_count"), "organization_count", 2))
        failures.extend(validate_integer(value.get("participant_count"), "participant_count", 6))
        failures.extend(validate_integer(value.get("p0_task_count"), "p0_task_count", 1))
        for field in ("consent_template_sha256", "journey_scope_sha256"):
            failures.extend(validate_digest(value.get(field), field))
        failures.extend(validate_identifier(value.get("facilitator_policy_id"), "facilitator_policy_id"))
        failures.extend(validate_identifier(value.get("independent_review_id"), "independent_review_id"))
        if value.get("decision_authority") != "CUSTOMER_HUMAN_ONLY":
            failures.append("decision_authority must be CUSTOMER_HUMAN_ONLY")
    return failures


def test_parameters(check_id: str, plan_path: Path = PLAN) -> dict[str, Any]:
    """Build an in-memory test fixture; never use this as external evidence."""

    case_ids, adapter_ids = expected_case_contract(check_id, plan_path)
    digest = "sha256:" + "1" * 64
    common: dict[str, Any] = {
        "schema_version": 1,
        "qualification_plan_sha256": digest_file(plan_path),
        "case_ids": case_ids,
        "adapter_ids": adapter_ids,
        "authorization_scope": {
            "tenant_id": "tenant-test",
            "project_id": "project-test",
            "environment_id": "environment-test",
            "region": "isolated-test-region",
            "data_classification": "INTERNAL",
            "network_policy_id": "network-policy-test",
            "write_root_id": "write-root-test",
        },
        "secret_reference_ids": [],
    }
    specific: dict[str, dict[str, Any]] = {
        "real_source_target_builds": {
            "repository_commits": [{
                "repository_id": "repository-test",
                "source_commit": "a" * 40,
                "target_commit": "b" * 40,
            }],
            "route_ids": ["route-test"],
            "startup_probe_ids": ["startup-test"],
            "cleanup_policy_id": "cleanup-test",
        },
        "device_matrix": {
            "quality_profile_ids": [f"quality-profile-{index}" for index in range(5)],
            "device_inventory_sha256": digest,
            "approved_baseline_manifest_sha256": digest,
            "assistive_technology_profiles": ["at-profile-test"],
            "cleanup_policy_id": "cleanup-test",
        },
        "independent_holdout": {
            "corpus_manifest_sha256": digest,
            "development_corpus_sha256": "sha256:" + "2" * 64,
            "case_count": 1,
            "independence_attestation_id": "attestation-test",
            "executor_organization_id": "executor-org-test",
        },
        "formal_proof": {
            "solver_name": "solver-test",
            "solver_version": "1.0.0",
            "solver_options": ["bounded"],
            "bounds": {"states": 10},
            "obligation_ids": ["obligation-test"],
            "counterexample_replay_version": "1.0.0",
        },
        "performance": {
            "workload_manifest_sha256": digest,
            "workload_count": 1,
            "samples_per_workload": 5,
            "warmup_samples": 1,
            "budgets_sha256": digest,
            "telemetry_profile_id": "telemetry-test",
        },
        "chaos_dr": {
            "drill_plan_sha256": digest,
            "scenario_count": 1,
            "rpo_budget_seconds": 0,
            "rto_budget_seconds": 60,
            "fault_injection_profile_id": "fault-profile-test",
            "cleanup_policy_id": "cleanup-test",
        },
        "penetration_test": {
            "assessment_scope_sha256": digest,
            "target_count": 1,
            "written_authorization_id": "authorization-test",
            "tool_profile_ids": ["tool-profile-test"],
            "manual_test_plan_sha256": digest,
            "retest_required": True,
        },
        "production_observation": {
            "deployment_artifact_sha256": digest,
            "environment_id": "production-test",
            "observation_minutes": 60,
            "slo_manifest_sha256": digest,
            "alert_routes_sha256": digest,
            "telemetry_query_profile_id": "telemetry-query-test",
            "read_only": True,
        },
        "customer_acceptance": {
            "organization_count": 2,
            "participant_count": 6,
            "p0_task_count": 1,
            "consent_template_sha256": digest,
            "journey_scope_sha256": digest,
            "facilitator_policy_id": "facilitator-test",
            "independent_review_id": "review-test",
            "decision_authority": "CUSTOMER_HUMAN_ONLY",
        },
    }
    return {**common, **specific[check_id]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    contract = commands.add_parser("contract")
    contract.add_argument("--check", choices=CHECK_IDS, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--check", choices=CHECK_IDS, required=True)
    validate.add_argument("--parameters", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    case_ids, adapter_ids = expected_case_contract(args.check)
    if args.command == "contract":
        print(json.dumps({
            "schema_version": 1,
            "check_id": args.check,
            "qualification_plan_sha256": digest_file(PLAN),
            "required_fields": sorted(COMMON_KEYS | CHECK_KEYS[args.check]),
            "case_ids": case_ids,
            "adapter_ids": adapter_ids,
            "repository_content_may_select_commands": False,
            "external_state": "NOT_RUN",
            "production_operation_authorized": False,
            "production_certification": "NOT_CERTIFIED",
        }, ensure_ascii=False, indent=2))
        return 0
    parameters = json.loads(args.parameters.read_text(encoding="utf-8"))
    failures = validate_campaign_parameters(args.check, parameters)
    print(json.dumps({
        "check_id": args.check,
        "decision": "PASSED_PARAMETER_CONTRACT" if not failures else "REJECTED",
        "failures": failures,
        "external_state": "NOT_RUN",
        "production_operation_authorized": False,
        "production_certification": "NOT_CERTIFIED",
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
