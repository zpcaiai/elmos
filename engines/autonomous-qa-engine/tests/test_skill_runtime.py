from __future__ import annotations

import hashlib
from dataclasses import replace
from types import MappingProxyType
import unittest
from typing import Any
from unittest.mock import patch

import elmos_autonomous_qa.skill_runtime as skill_runtime_module
from elmos_autonomous_qa.skill_runtime import (
    SKILL_REGISTRY,
    SkillRuntimeError,
    dispatch_skill,
    phase_execution_plan,
    validate_skill_registry,
)
from elmos_autonomous_qa.contracts import (
    ContractError,
    HandlerOutputError,
    RuntimeRequest,
    digest_json,
    normalize_result,
    require_exact_text,
    require_text,
    strict_json,
)


def sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


REQUIREMENT = {
    "requirement_id": "REQ-1",
    "kind": "functional",
    "title": "Addition is correct",
    "statement": "The sum equals the two inputs added together.",
    "priority": "P0",
    "required": True,
    "source_refs": ["requirements.md:1"],
    "acceptance_criteria": ["For inputs 1 and 2, the result equals 3."],
    "status": "ready",
}


def request(inputs: dict[str, Any], *, mutating: bool = True) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": "request-1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "inputs": inputs,
    }
    if mutating:
        value["actor_id"] = "actor-a"
        value["idempotency_key"] = "idempotency-1"
    return value


def fixtures() -> dict[str, dict[str, Any]]:
    dsl_case: dict[str, Any] = {
        "test_case_id": "TC-1",
        "title": "adds two values",
        "test_type": "functional",
        "priority": "P0",
        "required": True,
        "requirement_refs": ["REQ-1"],
        "preconditions": [],
        "steps": [
            {
                "step_id": "step-1",
                "action": "invoke",
                "input": {"left": 1, "right": 2},
                "side_effect": False,
            }
        ],
        "oracles": [
            {
                "oracle_id": "oracle-1",
                "kind": "value",
                "assertion": "result equals 3",
            }
        ],
        "evidence_requirements": ["structured-result"],
        "cleanup": [],
        "executor": {
            "adapter_key": "python",
            "capability": "unit",
            "parameters": {},
            "environment_profile": "isolated-local",
        },
        "materialization": {
            "planned_paths": ["tests/test_add.py"],
            "validation_status": "planned",
        },
    }
    graph_nodes: list[dict[str, Any]] = [
        {
            "node_id": "REQ-1",
            "kind": "REQUIREMENT",
            "label": "Addition is correct",
            "required": True,
        },
        {
            "node_id": "TC-1",
            "kind": "TEST",
            "label": "adds two values",
            "required": True,
            "attributes": {"executable": True, "oracle_valid": True},
        },
        {
            "node_id": "FILE-1",
            "kind": "TEST_FILE",
            "label": "tests/test_add.py",
        },
    ]
    graph_edges: list[dict[str, Any]] = [
        {
            "from": "TC-1",
            "to": "REQ-1",
            "kind": "verifies",
            "confidence": 1.0,
            "evidence_refs": ["requirements.md:1"],
            "inferred": False,
        },
        {
            "from": "TC-1",
            "to": "FILE-1",
            "kind": "materialized_as",
            "confidence": 1.0,
            "evidence_refs": ["manifest:artifact-1"],
            "inferred": False,
        },
    ]
    environment_template = {"provider": "local", "version": "1.0"}
    rebuild_event: dict[str, Any] = {
        "sequence": 1,
        "kind": "run-created",
        "payload": {"status": "CREATED"},
        "previous_digest": "0" * 64,
    }
    rebuild_event["event_digest"] = digest_json(rebuild_event)[7:]
    impact_report: dict[str, Any] = {
        "full_regression_required": False,
        "impacted_tests": ["TC-1"],
        "unknown_paths": [],
    }
    impact_report["report_digest"] = digest_json(impact_report)
    repair_plan = {
        "defect_id": "defect-1",
        "risk_level": "R1",
        "candidate_paths": ["src/add.py"],
        "approval": "POLICY_GATES_REQUIRED",
    }
    repair_plan_digest = digest_json(repair_plan)
    generated = {binding.source_id: {"requirements": [REQUIREMENT]} for binding in SKILL_REGISTRY.values() if 6 <= binding.ordinal <= 16}
    generated.update(
        {
            "00-qa-control-plane": {
                "operation": "create",
                "run_id": "run-1",
                "mode": "generate",
                "payload": {"source_snapshot_digest": sha("snapshot")},
            },
            "01-project-context-ingestion": {
                "operation": "snapshot",
                "required_paths": ["requirements.md"],
            },
            "02-spec-normalization": {"requirements": [REQUIREMENT]},
            "03-requirement-traceability-graph": {
                "nodes": graph_nodes,
                "edges": graph_edges,
            },
            "04-risk-coverage-planning": {
                "requirements": [
                    {
                        "requirement_id": "REQ-1",
                        "priority": "P0",
                        "required": True,
                        "risk_tags": ["security"],
                        "business_impact": 5,
                        "change_complexity": 2,
                        "historical_defects": 1,
                        "data_sensitivity": "restricted",
                        "external_dependency": False,
                        "estimated_seconds": 5,
                    }
                ],
                "budget": {
                    "wall_clock_seconds": 1000,
                    "max_compute_seconds": 10_000,
                    "max_cases": 1000,
                },
            },
            "05-test-model-dsl": {
                "dsl_version": "1.1",
                "test_cases": [dsl_case],
            },
            "17-test-data-management": {
                "run_id": "run-1",
                "seed": "stable-seed",
                "lease_seconds": 600,
                "datasets": [
                    {
                        "dataset_id": "data-1",
                        "source": "synthetic",
                        "classification": "internal",
                        "row_count": 2,
                        "schema": [
                            {"name": "record_id", "kind": "string", "nullable": False}
                        ],
                    }
                ],
            },
            "18-environment-orchestration": {
                "environment_id": "environment-1",
                "profile": "local-isolated",
                "template": environment_template,
                "template_digest": digest_json(environment_template),
                "image_digest": sha("environment-image"),
                "config": {"clock": "fixed"},
                "resources": [
                    {
                        "resource_id": "namespace-1",
                        "kind": "namespace",
                        "version": "1.0",
                    }
                ],
                "lease_seconds": 600,
            },
            "19-distributed-test-execution": {
                "tasks": [
                    {
                        "test_case_id": "TC-1",
                        "priority": "P0",
                        "dependency_ids": [],
                        "environment_profile": "local-isolated",
                        "resources": {"cpu_millis": 500, "memory_mb": 256},
                        "estimated_seconds": 10,
                    }
                ],
                "workers": 1,
                "capacity": {
                    "cpu_millis": 1000,
                    "memory_mb": 1024,
                    "gpu_count": 0,
                    "max_in_flight": 1,
                },
                "backpressure": {"max_queue_depth": 10, "high_watermark": 8},
                "lease_seconds": 60,
                "heartbeat_seconds": 10,
                "checkpoint_interval_seconds": 30,
            },
            "20-test-oracle-evidence": {
                "oracle": {
                    "oracle_id": "oracle-1",
                    "dimensions": [
                        {
                            "name": "result",
                            "expected": 3,
                            "comparator": "equal",
                            "redact": False,
                        }
                    ],
                    "provenance": {
                        "source_id": "runner-output",
                        "source_digest": sha("runner-output"),
                        "observed_at": "2026-08-24T08:00:00Z",
                        "collector_id": "collector-1",
                    },
                },
                "observations": [{"name": "result", "actual": 3}],
            },
            "21-flaky-test-control": {
                "attempts": [
                    {
                        "attempt_id": "attempt-1",
                        "test_case_id": "TC-1",
                        "status": "PASSED",
                        "input_digest": sha("input"),
                        "environment_digest": sha("environment"),
                        "time_bucket": "2026-08-24T08",
                        "resource_digest": sha("resources"),
                        "dependency_digest": sha("dependencies"),
                        "seed": 7,
                        "order_digest": sha("order"),
                        "product_digest": sha("product"),
                        "test_digest": sha("test"),
                    }
                ]
            },
            "22-defect-triage-rca": {
                "failures": [
                    {
                        "failure_id": "failure-1",
                        "test_case_id": "TC-1",
                        "fingerprint": "wrong-result",
                        "severity": "HIGH",
                        "owner": "owner-1",
                        "changed_paths": ["src/add.py"],
                        "upstream_failure_ids": [],
                        "reproduction_steps": ["invoke add", "observe result"],
                    }
                ],
                "hypotheses": [
                    {
                        "hypothesis_id": "hypothesis-1",
                        "failure_ids": ["failure-1"],
                        "supporting_evidence_refs": ["evidence-1"],
                        "counterevidence_refs": [],
                        "confidence": 0.9,
                    }
                ],
            },
            "23-repair-planning": {
                "defect_id": "defect-1",
                "reproduction": {
                    "status": "REPRODUCED",
                    "evidence_digest": sha("reproduction"),
                },
                "root_cause_confidence": 0.9,
                "confidence_threshold": 0.8,
                "max_attempts": 3,
                "alternatives": [
                    {
                        "alternative_id": "alternative-1",
                        "changes": [{"path": "src/add.py", "kind": "logic-fix"}],
                        "validation_steps": ["run focused test"],
                        "rollback_steps": ["restore previous content"],
                        "estimated_attempts": 1,
                    }
                ],
            },
            "24-safe-code-auto-fix": {
                "diff": "--- a/src/add.py\n+++ b/src/add.py\n@@ -1 +1 @@\n-pass\n+return left + right\n",
                "candidate_paths": ["src/add.py"],
                "semantic_tags": ["pure-function"],
                "repair_plan": repair_plan,
                "repair_plan_digest": repair_plan_digest,
                "isolated_worktree": True,
                "sandboxed": True,
                "approvals": [],
            },
            "25-test-self-healing": {"before": "assert value == 3", "after": "assert value == 3", "reason": "stable locator only", "business_oracle_changed": False},
            "26-impact-analysis-regression": {
                "graph": {
                    "graph_id": "graph-1",
                    "nodes": [
                        {"node_id": "TC-1", "kind": "TEST"},
                        {"node_id": "source-1", "kind": "SOURCE"},
                    ],
                    "edges": [
                        {
                            "source": "source-1",
                            "target": "TC-1",
                            "kind": "GENERATES",
                            "direction": "source-to-target",
                        }
                    ],
                    "graph_digest": digest_json(
                        {
                            "graph_id": "graph-1",
                            "nodes": [
                                {"node_id": "TC-1", "kind": "TEST"},
                                {"node_id": "source-1", "kind": "SOURCE"},
                            ],
                            "edges": [
                                {
                                    "source": "source-1",
                                    "target": "TC-1",
                                    "kind": "GENERATES",
                                    "direction": "source-to-target",
                                }
                            ],
                        }
                    ),
                },
                "changed_node_ids": ["source-1"],
                "all_test_ids": ["TC-1"],
            },
            "27-mutation-property-fuzz-testing": {
                "invariants": [
                    {
                        "invariant_id": "invariant-1",
                        "statement": "addition conserves value",
                        "oracle_ref": "oracle-1",
                    }
                ],
                "generators": [
                    {
                        "generator_id": "generator-1",
                        "strategy": "boundary",
                        "domain": {"minimum": 0, "maximum": 100},
                    }
                ],
                "shrinkers": [
                    {
                        "shrinker_id": "shrinker-1",
                        "strategy": "structural",
                        "preserves_invariant_refs": ["invariant-1"],
                    }
                ],
                "properties": [
                    {
                        "property_id": "property-1",
                        "invariant_refs": ["invariant-1"],
                        "generator_id": "generator-1",
                        "shrinker_id": "shrinker-1",
                    }
                ],
                "fuzz_targets": [
                    {
                        "target_id": "target-1",
                        "path": "src/add.py",
                        "entrypoint": "add",
                        "invariant_refs": ["invariant-1"],
                    }
                ],
                "corpus": [
                    {
                        "corpus_id": "corpus-1",
                        "target_id": "target-1",
                        "sha256": sha("corpus"),
                        "role": "holdout",
                    }
                ],
                "mutation_operators": [
                    {
                        "operator_id": "operator-1",
                        "kind": "conditional-boundary",
                        "target_id": "target-1",
                    }
                ],
                "survivors": [],
            },
            "28-quality-gate-release-certification": {
                "mode": "verify",
                "requirements": [REQUIREMENT],
                "tests": [
                    {
                        "test_case_id": "TC-1",
                        "status": "PASSED",
                        "required": True,
                        "requirement_refs": ["REQ-1"],
                        "risk_refs": [],
                        "materialized_ref": "artifact-1",
                        "build_status": "PASSED",
                        "discovery_status": "PASSED",
                    }
                ],
                "output": {
                    "project_output_manifest_ref": "manifest-project",
                    "test_artifact_manifest_ref": "manifest-tests",
                    "bundles": ["project-with-tests", "tests-only", "qa-evidence"],
                    "materialized_artifact_refs": ["artifact-1"],
                    "all_artifacts_have_sha256": True,
                    "bundle_checksums_match": True,
                    "tamper_detected": False,
                    "test_targets_build": True,
                    "generated_tests_discoverable": True,
                    "replay_entrypoint_present": True,
                    "untracked_generated_files": False,
                    "secrets_detected": False,
                    "unsafe_symlink_detected": False,
                    "partial_output_available": True,
                },
                "security": {
                    "unresolved_critical_findings": 0,
                    "unresolved_high_findings": 0,
                    "production_credentials_used": False,
                    "permissions_broadened": False,
                    "security_controls_disabled": False,
                    "direct_main_write": False,
                    "direct_production_write": False,
                },
                "certification": {
                    "project_manifest_signed": True,
                    "evidence_manifest_signed": True,
                    "signatures_valid": True,
                    "signer_trusted": True,
                    "evidence_digests_valid": True,
                    "authorization_valid": True,
                    "independent_corpus": True,
                    "independent_evidence": True,
                    "external_validation_completed": True,
                    "executor_id": "executor-a",
                    "verifier_id": "verifier-b",
                    "signer_id": "signer-c",
                },
                "run_succeeded": True,
            },
            "29-reporting-observability": {
                "requirements": [
                    {"requirement_id": "REQ-1", "priority": "P0", "status": "COVERED"}
                ],
                "test_results": [
                    {"test_case_id": "TC-1", "test_type": "functional", "status": "PASSED"}
                ],
                "defects": [],
                "patches": [],
                "evidence": [],
            },
            "30-checkpoint-resume-idempotency": {
                "operation": "rebuild",
                "run_id": "run-1",
                "sequence": 1,
                "expected_version": 1,
                "lease": {
                    "owner": "worker-1",
                    "epoch": 1,
                    "expires_at": "2026-08-24T09:00:00Z",
                },
                "fence_token": 1,
                "state": {"phase": "planning"},
                "events": [rebuild_event],
            },
            "31-runtime-cost-eta": {
                "tasks": [
                    {
                        "task_id": "task-1",
                        "phase": "generation",
                        "dependency_ids": [],
                        "estimated_seconds": 10,
                        "resource_units": 1,
                    }
                ],
                "parallelism": 1,
                "pricing": {
                    "currency": "USD",
                    "observed_at": "2026-08-24T08:00:00Z",
                    "unit_price_per_resource_second": 0.01,
                },
            },
            "32-multilanguage-adapter-sdk": {"operation": "list"},
            "33-ci-cd-pr-integration": {"event": "pull-request", "changed_nodes": ["src/add.py"], "impact_report": impact_report},
            "34-continuous-learning-knowledge-base": {
                "scope": {
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "audience": "project-team",
                },
                "version": "v1",
                "sources": [
                    {
                        "source_id": "source-1",
                        "sha256": sha("learning-source"),
                        "state": "local-observed",
                        "confidence": 0.8,
                        "external": False,
                    }
                ],
                "rules": [
                    {
                        "rule_id": "rule-1",
                        "condition": "fingerprint equals boundary-error",
                        "recommendation": "inspect the exact boundary contract",
                    }
                ],
                "metrics": [
                    {
                        "name": "triage-precision",
                        "baseline": 0.7,
                        "target": 0.8,
                        "direction": "increase",
                    }
                ],
                "rollback": {
                    "previous_version": "v0",
                    "trigger": "precision falls below baseline",
                    "procedure": ["disable candidate", "restore v0"],
                },
                "history": [],
            },
            "35-governance-approval-audit": {
                "resource_tenant_id": "tenant-a",
                "action": "repair",
                "evaluation_time": "2026-08-24T08:00:00Z",
                "risk": {
                    "paths": ["src/add.py"],
                    "semantic_tags": ["behavior-change"],
                    "data_classification": "INTERNAL",
                },
                "approvals": [],
                "exception": None,
                "budget": {"amount": 100, "currency": "USD"},
                "retention": {"days": 90, "legal_hold": False},
                "access_policy": {
                    "allowed_roles": ["code-owner"],
                    "purpose": "repair-review",
                },
            },
            "36-project-output-contract": {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "revision_id": "revision-1",
                "run_id": "run-1",
                "run_mode": "generate",
                "source_snapshot_digest": "a" * 64,
                "output_mode": "sidecar",
                "adapter_key": "python",
                "test_cases": [
                    {
                        "test_case_id": "TC-1",
                        "test_type": "functional",
                        "required": True,
                        "requirement_refs": ["REQ-1"],
                    }
                ],
                "retention_policy": {
                    "policy_id": "retention-1",
                    "classification": "standard",
                    "retention_days": 30,
                    "legal_hold": False,
                    "deletion_mode": "two-phase",
                },
                "permission_policy": {
                    "policy_id": "permission-1",
                    "owner_principals": ["qa-owner"],
                    "reader_principals": ["qa-reviewer"],
                    "writer_principals": ["qa-owner"],
                    "publisher_service": "ArtifactPublisher",
                },
                "secret_policy": {
                    "scan_required": True,
                    "inline_secrets_allowed": False,
                    "allowed_secret_refs": ["secret-ref:qa-runtime"],
                    "redaction_required": True,
                },
            },
            "37-test-source-materialization": {
                "suite_id": "suite-python",
                "adapter_key": "python",
                "test_cases": [dsl_case],
                "fixture_records": [],
                "mock_records": [],
                "synthetic_data_records": [],
                "config": {"runtime_profile": "isolated-local"},
                "existing_paths": [],
            },
            "38-project-output-bundle-publishing": {
                "session_id": "delivery-session-1"
            },
            "39-output-versioning-retention": {"action": "candidates"},
        }
    )
    return generated


class SkillRuntimeTest(unittest.TestCase):
    def test_registry_binds_exactly_forty_unique_handlers(self) -> None:
        validate_skill_registry()
        bindings = list(SKILL_REGISTRY.values())
        self.assertEqual(len(bindings), 40)
        self.assertEqual(sorted(item.ordinal for item in bindings), list(range(40)))
        self.assertEqual(len({item.handler_id for item in bindings}), 40)
        self.assertEqual(len({id(item.handler) for item in bindings}), 40)
        self.assertTrue(all(item.skill.startswith("autonomous-qa-") for item in bindings))
        self.assertIsInstance(SKILL_REGISTRY, MappingProxyType)
        with self.assertRaises(TypeError):
            SKILL_REGISTRY["autonomous-qa-injected"] = bindings[0]  # type: ignore[index]

    def test_handler_output_may_not_default_to_success(self) -> None:
        parsed = RuntimeRequest.parse(request({"value": 1}, mutating=False))
        with self.assertRaises(HandlerOutputError):
            normalize_result(
                skill="autonomous-qa-test",
                source_id="test-source",
                handler_id="execute_test",
                operation_id="tests.execute",
                phase="test",
                mutating=False,
                request=parsed,
                operation={"outputs": {}},
            )

    def test_handler_output_unknown_fields_fail_closed(self) -> None:
        parsed = RuntimeRequest.parse(request({"value": 1}, mutating=False))
        with self.assertRaises(HandlerOutputError):
            normalize_result(
                skill="autonomous-qa-test",
                source_id="test-source",
                handler_id="execute-test",
                operation_id="tests.execute",
                phase="test",
                mutating=False,
                request=parsed,
                operation={
                    "state": "SUCCEEDED",
                    "code": "DONE",
                    "outputs": {},
                    "implementation_state": "LOCAL_EXECUTED",
                    "caller_certified": True,
                },
            )

    def test_runtime_context_is_reserved_and_cannot_be_caller_overridden(self) -> None:
        payload = request(
            {
                "requirements": [REQUIREMENT],
                "_runtime_context": {
                    "tenant_id": "foreign-tenant",
                    "project_id": "foreign-project",
                },
            },
            mutating=False,
        )
        result = dispatch_skill("02-spec-normalization", payload)
        self.assertEqual("BLOCKED", result["state"])
        self.assertEqual("REQUEST_CONTRACT_REJECTED", result["code"])
        self.assertEqual("EXACT_NORMALIZED", result["outputs"]["request_binding"])
        self.assertEqual(result["request_digest"], result["outputs"]["rejected_request_digest"])

    def test_all_forty_handlers_execute_meaningful_local_contracts(self) -> None:
        cases = fixtures()
        self.assertEqual(set(cases), {item.source_id for item in SKILL_REGISTRY.values()})
        for binding in SKILL_REGISTRY.values():
            with self.subTest(skill=binding.skill):
                result = dispatch_skill(binding.skill, request(cases[binding.source_id]))
                self.assertIn(result["state"], {"SUCCEEDED", "PARTIAL", "BLOCKED"})
                self.assertNotEqual(result["code"], "REQUEST_CONTRACT_REJECTED")
                self.assertNotEqual(result["code"], "LOCAL_HANDLER_OUTPUT_INVALID")
                self.assertNotEqual(result["code"], "LOCAL_HANDLER_FAILED")
                self.assertNotEqual(result["code"], "LOCAL_OPERATION_COMPLETED")
                self.assertEqual(result["external_evidence"], "NOT_RUN")
                self.assertEqual(result["certification"], "NOT_CERTIFIED")
                self.assertEqual(result["handler_id"], binding.handler_id)
                self.assertEqual(result["skill"], binding.skill)
                self.assertEqual(result["phase"], binding.phase)
                self.assertEqual(result["source_id"], binding.source_id)
                self.assertEqual(result["operation_id"], binding.operation_id)
                self.assertIs(result["mutating"], binding.mutating)

    def test_text_contract_rejects_c1_and_bidi_format_controls(self) -> None:
        for value in (
            "visible\u0085text",
            "visible\u202etext",
            "visible\u2028text",
            "visible\u2029text",
        ):
            with self.subTest(value=value), self.assertRaises(ContractError):
                require_text(value, "value")
            with self.subTest(exact=value), self.assertRaises(ContractError):
                require_exact_text(value, "value", maximum=128)
            with self.subTest(nested=value), self.assertRaises(ContractError):
                strict_json({"nested": value}, "payload")
            with self.subTest(key=value), self.assertRaises(ContractError):
                strict_json({value: "nested"}, "payload")
        invalid_key = "\ud800"
        with self.assertRaises(ContractError):
            strict_json({invalid_key: "input"}, "payload")
        with self.assertRaises(HandlerOutputError):
            strict_json({invalid_key: "output"}, "payload", output=True)

    def test_unknown_skill_is_rejected_and_extra_fields_fail_closed(self) -> None:
        with self.assertRaises(SkillRuntimeError):
            dispatch_skill("autonomous-qa-does-not-exist", request({}))
        for invalid in ([], {}, 7):
            with self.subTest(invalid=invalid), self.assertRaises(SkillRuntimeError):
                dispatch_skill(invalid, request({}))  # type: ignore[arg-type]
        malformed = request({"requirements": [REQUIREMENT]})
        malformed["embedded_command"] = "run source scripts"
        result = dispatch_skill("02-spec-normalization", malformed)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "REQUEST_CONTRACT_REJECTED")
        self.assertEqual(result["outputs"]["request_binding"], "RAW_CANONICAL")
        self.assertEqual(
            result["outputs"]["rejected_request_digest"], digest_json(malformed)
        )
        mixed_keys = request({"requirements": [REQUIREMENT]})
        mixed_keys[1] = "invalid"  # type: ignore[index]
        result = dispatch_skill("02-spec-normalization", mixed_keys)
        self.assertEqual("REQUEST_CONTRACT_REJECTED", result["code"])

    def test_handler_rejection_preserves_the_exact_normalized_request_binding(self) -> None:
        payload = request({"requirements": [REQUIREMENT]}, mutating=False)
        payload["policy"] = {"trusted_binding": False}
        result = dispatch_skill("02-spec-normalization", payload)
        self.assertEqual("BLOCKED", result["state"])
        self.assertEqual("request-1", result["request_id"])
        self.assertEqual("tenant-a", result["tenant_id"])
        self.assertEqual("project-a", result["project_id"])
        self.assertEqual("EXACT_NORMALIZED", result["outputs"]["request_binding"])
        self.assertEqual(
            result["request_digest"],
            result["outputs"]["rejected_request_digest"],
        )

    def test_internal_handler_failure_preserves_the_parsed_request_binding(self) -> None:
        alias = "autonomous-qa-02-spec-normalization"
        binding = SKILL_REGISTRY[alias]

        def fail(_: RuntimeRequest) -> dict[str, Any]:
            raise RuntimeError("provider detail must not escape")

        patched_registry = MappingProxyType(
            {**SKILL_REGISTRY, alias: replace(binding, handler=fail)}
        )
        payload = request({"requirements": [REQUIREMENT]}, mutating=False)
        with patch.object(
            skill_runtime_module, "SKILL_REGISTRY", patched_registry
        ):
            result = dispatch_skill(alias, payload)
        self.assertEqual("FAILED", result["state"])
        self.assertEqual("request-1", result["request_id"])
        self.assertEqual("tenant-a", result["tenant_id"])
        self.assertEqual("project-a", result["project_id"])
        self.assertEqual("EXACT_NORMALIZED", result["outputs"]["request_binding"])
        self.assertEqual(
            result["request_digest"], result["outputs"]["failed_request_digest"]
        )

    def test_invalid_handler_output_is_a_bound_internal_failure(self) -> None:
        alias = "autonomous-qa-02-spec-normalization"
        binding = SKILL_REGISTRY[alias]

        def invalid(_: RuntimeRequest) -> dict[str, Any]:
            return {}

        patched_registry = MappingProxyType(
            {**SKILL_REGISTRY, alias: replace(binding, handler=invalid)}
        )
        with patch.object(
            skill_runtime_module, "SKILL_REGISTRY", patched_registry
        ):
            result = dispatch_skill(
                alias,
                request({"requirements": [REQUIREMENT]}, mutating=False),
            )
        self.assertEqual("FAILED", result["state"])
        self.assertEqual("LOCAL_HANDLER_OUTPUT_INVALID", result["code"])
        self.assertEqual("EXACT_NORMALIZED", result["outputs"]["request_binding"])
        self.assertEqual(
            result["request_digest"], result["outputs"]["failed_request_digest"]
        )

    def test_mutating_skill_requires_actor_and_idempotency(self) -> None:
        result = dispatch_skill(
            "24-safe-code-auto-fix",
            request(fixtures()["24-safe-code-auto-fix"], mutating=False),
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(result["outputs"].get("execution_performed", False))

    def test_auto_fix_cannot_weaken_tests_or_authorize_merge(self) -> None:
        payload = dict(fixtures()["24-safe-code-auto-fix"])
        payload["diff"] = (
            "--- a/src/add.py\n+++ b/src/add.py\n@@ -1 +1 @@\n"
            "-pass\n+pytest.mark.skip(reason='make green')\n"
        )
        result = dispatch_skill("24-safe-code-auto-fix", request(payload))
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("pytest.mark.skip", result["outputs"]["findings"])
        self.assertFalse(result["outputs"]["merge_authorized"])

    def test_local_gate_never_claims_certification(self) -> None:
        result = dispatch_skill(
            "28-quality-gate-release-certification",
            request(fixtures()["28-quality-gate-release-certification"]),
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(result["outputs"]["caller_certification_assertions_accepted"])
        self.assertEqual(result["outputs"]["trusted_external_receipt"], "NOT_RUN")
        self.assertFalse(result["outputs"]["certified"])
        self.assertEqual(result["certification"], "NOT_CERTIFIED")

    def test_runtime_phase_plan_is_acyclic(self) -> None:
        plan = phase_execution_plan()
        self.assertEqual(len(plan), len(set(plan)))
        self.assertLess(plan.index("context"), plan.index("generation"))
        self.assertLess(plan.index("materialization"), plan.index("execution"))
        self.assertLess(plan.index("reporting"), plan.index("publishing"))


if __name__ == "__main__":
    unittest.main()
