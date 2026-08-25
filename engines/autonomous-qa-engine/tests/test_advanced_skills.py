from __future__ import annotations

import copy
import hashlib
import unittest

from elmos_autonomous_qa import advanced_skills as advanced
from elmos_autonomous_qa.contracts import ContractError, digest_json


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scheduler_request() -> dict[str, object]:
    return {
        "tasks": [
            {
                "test_case_id": "TC-P0",
                "priority": "P0",
                "dependency_ids": [],
                "environment_profile": "isolated-python",
                "resources": {"cpu_millis": 500, "memory_mb": 256},
                "estimated_seconds": 10,
            },
            {
                "test_case_id": "TC-P1",
                "priority": "P1",
                "dependency_ids": ["TC-P0"],
                "environment_profile": "isolated-python",
                "resources": {"cpu_millis": 750, "memory_mb": 512},
                "estimated_seconds": 20,
            },
        ],
        "workers": 4,
        "capacity": {
            "cpu_millis": 2_000,
            "memory_mb": 2_048,
            "gpu_count": 0,
            "max_in_flight": 2,
        },
        "backpressure": {"max_queue_depth": 10, "high_watermark": 2},
        "lease_seconds": 60,
        "heartbeat_seconds": 10,
        "checkpoint_interval_seconds": 30,
    }


def oracle_request() -> dict[str, object]:
    return {
        "oracle": {
            "oracle_id": "oracle-latency",
            "dimensions": [
                {
                    "name": "latency-ms",
                    "expected": 100,
                    "comparator": "numeric-absolute",
                    "tolerance": 5,
                    "redact": False,
                },
                {
                    "name": "token",
                    "expected": "secret-value",
                    "comparator": "equal",
                    "redact": True,
                },
            ],
            "provenance": {
                "source_id": "runner-output",
                "source_digest": sha("runner-output"),
                "observed_at": "2026-08-24T08:00:00Z",
                "collector_id": "collector-a",
            },
        },
        "observations": [
            {"name": "latency-ms", "actual": 103},
            {"name": "token", "actual": "secret-value"},
        ],
    }


def flake_attempt(
    attempt_id: str, status: str, *, environment: str = "environment-a"
) -> dict[str, object]:
    return {
        "attempt_id": attempt_id,
        "test_case_id": "TC-FLAKE",
        "status": status,
        "input_digest": sha("input"),
        "environment_digest": sha(environment),
        "time_bucket": "2026-08-24T08",
        "resource_digest": sha("resources"),
        "dependency_digest": sha("dependencies"),
        "seed": 7,
        "order_digest": sha("order"),
        "product_digest": sha("product"),
        "test_digest": sha("test"),
    }


def triage_request() -> dict[str, object]:
    return {
        "failures": [
            {
                "failure_id": "failure-root",
                "test_case_id": "TC-ROOT",
                "fingerprint": "database-unavailable",
                "severity": "MEDIUM",
                "owner": "owner-platform",
                "changed_paths": ["src/database.py"],
                "upstream_failure_ids": [],
                "reproduction_steps": ["prepare fixture", "invoke API", "observe error"],
            },
            {
                "failure_id": "failure-child",
                "test_case_id": "TC-CHILD",
                "fingerprint": "api-timeout",
                "severity": "HIGH",
                "owner": "owner-api",
                "changed_paths": ["src/api.py"],
                "upstream_failure_ids": ["failure-root"],
                "reproduction_steps": ["invoke API"],
            },
        ],
        "changes": [
            {
                "change_id": "change-1",
                "path": "src/database.py",
                "owner": "owner-platform",
            }
        ],
        "history": [
            {
                "history_id": "history-1",
                "fingerprint": "database-unavailable",
                "path": "src/database.py",
                "owner": "owner-platform",
                "resolution": "restore bounded connection pool",
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "failure_ids": ["failure-root"],
                "supporting_evidence_refs": ["evidence-support"],
                "counterevidence_refs": ["evidence-counter"],
                "confidence": 0.75,
            }
        ],
    }


def repair_request() -> dict[str, object]:
    return {
        "defect_id": "defect-1",
        "reproduction": {"status": "REPRODUCED", "evidence_digest": sha("repro")},
        "root_cause_confidence": 0.9,
        "confidence_threshold": 0.8,
        "max_attempts": 3,
        "alternatives": [
            {
                "alternative_id": "alternative-safe",
                "changes": [{"path": "src/service.py", "kind": "logic-fix"}],
                "validation_steps": ["run focused regression", "run full regression"],
                "rollback_steps": ["restore prior content", "revalidate prior state"],
                "estimated_attempts": 1,
            },
            {
                "alternative_id": "alternative-expensive",
                "changes": [{"path": "src/adapter.py", "kind": "adapter-fix"}],
                "validation_steps": ["run adapter contract", "run full regression"],
                "rollback_steps": ["restore adapter", "revalidate prior state"],
                "estimated_attempts": 2,
            },
        ],
    }


def impact_request() -> dict[str, object]:
    body = {
        "graph_id": "graph-1",
        "nodes": [
            {"node_id": "module-1", "kind": "MODULE"},
            {"node_id": "source-1", "kind": "SOURCE"},
            {"node_id": "test-1", "kind": "TEST"},
        ],
        "edges": [
            {
                "source": "module-1",
                "target": "test-1",
                "kind": "COVERS",
                "direction": "source-to-target",
            },
            {
                "source": "source-1",
                "target": "module-1",
                "kind": "GENERATES",
                "direction": "source-to-target",
            },
        ],
    }
    graph = {**body, "graph_digest": digest_json(body)[7:]}
    return {
        "graph": graph,
        "changed_node_ids": ["source-1"],
        "all_test_ids": ["test-1"],
    }


def advanced_testing_request() -> dict[str, object]:
    return {
        "invariants": [
            {
                "invariant_id": "invariant-conservation",
                "statement": "output amount equals input amount",
                "oracle_ref": "oracle-conservation",
            }
        ],
        "generators": [
            {
                "generator_id": "generator-boundary",
                "strategy": "boundary",
                "domain": {"minimum": 0, "maximum": 100},
            }
        ],
        "shrinkers": [
            {
                "shrinker_id": "shrinker-structural",
                "strategy": "structural",
                "preserves_invariant_refs": ["invariant-conservation"],
            }
        ],
        "properties": [
            {
                "property_id": "property-conservation",
                "invariant_refs": ["invariant-conservation"],
                "generator_id": "generator-boundary",
                "shrinker_id": "shrinker-structural",
            }
        ],
        "fuzz_targets": [
            {
                "target_id": "target-parser",
                "path": "src/parser.py",
                "entrypoint": "parse-input",
                "invariant_refs": ["invariant-conservation"],
            }
        ],
        "corpus": [
            {
                "corpus_id": "corpus-holdout",
                "target_id": "target-parser",
                "sha256": sha("corpus"),
                "role": "holdout",
            }
        ],
        "mutation_operators": [
            {
                "operator_id": "operator-boundary",
                "kind": "conditional-boundary",
                "target_id": "target-parser",
            }
        ],
        "survivors": [
            {
                "survivor_id": "survivor-1",
                "operator_id": "operator-boundary",
                "counterexample_digest": sha("counterexample"),
            }
        ],
    }


def report_request() -> dict[str, object]:
    return {
        "requirements": [
            {"requirement_id": "REQ-1", "priority": "P0", "status": "COVERED"}
        ],
        "test_results": [
            {"test_case_id": "TC-1", "test_type": "unit", "status": "PASSED"},
            {
                "test_case_id": "TC-2",
                "test_type": "integration",
                "status": "FAILED",
            },
        ],
        "defects": [
            {"defect_id": "defect-1", "severity": "HIGH", "status": "TRIAGED"}
        ],
        "patches": [
            {"patch_id": "patch-1", "status": "PROPOSED", "risk": "MEDIUM"}
        ],
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "state": "VERIFIED_LOCAL",
                "sha256": sha("evidence"),
            }
        ],
    }


def store_request() -> dict[str, object]:
    event = {
        "sequence": 1,
        "kind": "run-created",
        "payload": {"status": "CREATED"},
        "previous_digest": "0" * 64,
    }
    event["event_digest"] = digest_json(event)[7:]
    return {
        "operation": "rebuild",
        "run_id": "run-1",
        "sequence": 1,
        "expected_version": 4,
        "lease": {
            "owner": "worker-a",
            "epoch": 3,
            "expires_at": "2026-08-24T09:00:00Z",
        },
        "fence_token": 7,
        "state": {"phase": "execution"},
        "events": [event],
    }


def estimate_request() -> dict[str, object]:
    return {
        "tasks": [
            {
                "task_id": "task-a",
                "phase": "generation",
                "dependency_ids": [],
                "estimated_seconds": 10,
                "resource_units": 2,
            },
            {
                "task_id": "task-b",
                "phase": "execution",
                "dependency_ids": ["task-a"],
                "estimated_seconds": 20,
                "resource_units": 1,
            },
        ],
        "parallelism": 2,
        "queue_seconds": 2,
        "retry_probability": 0.25,
        "retry_seconds": 8,
        "repair_seconds": 3,
        "regression_seconds": 4,
        "publish_seconds": 1,
        "pricing": {
            "currency": "USD",
            "observed_at": "2026-08-24T08:00:00Z",
            "unit_price_per_resource_second": 0.01,
        },
        "calibration": [
            {"predicted_seconds": 10, "actual_seconds": 12},
            {"predicted_seconds": 20, "actual_seconds": 18},
            {"predicted_seconds": 30, "actual_seconds": 30},
        ],
    }


def knowledge_request() -> dict[str, object]:
    return {
        "scope": {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "audience": "project-team",
        },
        "version": "v1",
        "sources": [
            {
                "source_id": "source-local",
                "sha256": sha("source"),
                "state": "local-observed",
                "confidence": 0.8,
                "external": False,
            }
        ],
        "rules": [
            {
                "rule_id": "rule-1",
                "condition": "fingerprint equals timeout",
                "recommendation": "inspect bounded dependency latency",
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
            "procedure": ["disable candidate", "restore v0", "re-evaluate holdout"],
        },
        "history": [
            {"version": "v0", "sha256": sha("v0"), "disposition": "active"}
        ],
    }


def authorization_request() -> dict[str, object]:
    return {
        "_runtime_context": {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "actor_id": "executor-a",
            "request_id": "request-a",
            "idempotency_key": None,
        },
        "resource_tenant_id": "tenant-a",
        "action": "repair",
        "evaluation_time": "2026-08-24T08:00:00Z",
        "risk": {
            "paths": ["src/service.py"],
            "semantic_tags": ["behavior-change"],
            "data_classification": "INTERNAL",
        },
        "approvals": [
            {
                "approval_id": "approval-owner",
                "role": "code-owner",
                "actor_id": "owner-a",
                "scope": "repair",
                "expires_at": "2026-09-01T00:00:00Z",
            },
            {
                "approval_id": "approval-qa",
                "role": "qa-reviewer",
                "actor_id": "qa-a",
                "scope": "repair",
                "expires_at": "2026-09-01T00:00:00Z",
            },
        ],
        "exception": None,
        "budget": {"amount": 100, "currency": "USD"},
        "retention": {"days": 90, "legal_hold": False},
        "access_policy": {
            "allowed_roles": ["code-owner", "qa-reviewer"],
            "purpose": "repair-review",
        },
    }


class DistributedSchedulerContractTest(unittest.TestCase):
    def test_positive_plan_has_every_scheduler_safety_contract(self) -> None:
        result = advanced.plan_shards(scheduler_request())
        plan = result["outputs"]["scheduler_plan"]
        self.assertEqual("TC-P0", plan["tasks"][0]["test_case_id"])
        self.assertTrue(plan["fencing"]["stale_worker_results_rejected"])
        self.assertTrue(plan["terminal_completeness"]["one_terminal_result_per_task"])

    def test_negative_dependency_cycle_is_rejected(self) -> None:
        request = scheduler_request()
        request["tasks"][0]["dependency_ids"] = ["TC-P1"]
        with self.assertRaises(ContractError):
            advanced.plan_shards(request)

    def test_external_execution_boundary_remains_not_run(self) -> None:
        result = advanced.plan_shards(scheduler_request())
        self.assertEqual("NOT_RUN", result["outputs"]["execution"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["implementation_state"])


class OracleEvidenceContractTest(unittest.TestCase):
    def test_positive_multidimensional_local_evaluation_and_redaction(self) -> None:
        result = advanced.verify_evidence(oracle_request())
        manifest = result["outputs"]["evidence_manifest"]
        self.assertEqual("PASSED", manifest["local_evaluation"])
        redacted = manifest["dimensions"][1]
        self.assertTrue(redacted["redacted"])
        self.assertNotIn("actual", redacted)

    def test_negative_equal_oracle_cannot_smuggle_tolerance(self) -> None:
        request = oracle_request()
        request["oracle"]["dimensions"][1]["tolerance"] = 0
        with self.assertRaises(ContractError):
            advanced.verify_evidence(request)

    def test_external_signature_and_independent_review_are_not_run(self) -> None:
        request = oracle_request()
        request["signature_valid"] = True
        with self.assertRaises(ContractError):
            advanced.verify_evidence(request)
        result = advanced.verify_evidence(oracle_request())
        self.assertEqual("NOT_RUN", result["outputs"]["signature"])
        self.assertEqual("NOT_RUN", result["outputs"]["independent_verification"])


class FlakeClassificationContractTest(unittest.TestCase):
    def test_positive_stable_dimensions_classify_product_flake(self) -> None:
        request = {
            "attempts": [
                flake_attempt("attempt-1", "FAILED"),
                flake_attempt("attempt-2", "PASSED"),
            ],
            "stability_window": 3,
        }
        result = advanced.classify_flaky(request)
        self.assertEqual(
            "PRODUCT_FLAKE", result["outputs"]["profiles"][0]["classification"]
        )

    def test_negative_duplicate_attempt_is_rejected(self) -> None:
        attempt = flake_attempt("attempt-1", "FAILED")
        with self.assertRaises(ContractError):
            advanced.classify_flaky({"attempts": [attempt, dict(attempt)]})

    def test_external_attempt_execution_and_quarantine_mutation_are_not_run(self) -> None:
        result = advanced.classify_flaky(
            {
                "attempts": [
                    flake_attempt("attempt-1", "FAILED", environment="env-a"),
                    flake_attempt("attempt-2", "PASSED", environment="env-b"),
                ]
            }
        )
        self.assertEqual("NOT_RUN", result["outputs"]["attempt_execution"])
        self.assertFalse(result["outputs"]["automatic_quarantine_mutation"])


class DefectTriageContractTest(unittest.TestCase):
    def test_positive_upstream_cascade_is_visible_but_suppressed(self) -> None:
        result = advanced.triage_defects(triage_request())
        self.assertEqual(["failure-child"], result["outputs"]["suppressed_cascade_failure_ids"])
        defect = result["outputs"]["defects"][0]
        self.assertEqual("HIGH", defect["severity"])
        self.assertEqual(["invoke API"], defect["minimal_reproduction"])

    def test_negative_unknown_upstream_failure_is_rejected(self) -> None:
        request = triage_request()
        request["failures"][1]["upstream_failure_ids"] = ["failure-missing"]
        with self.assertRaises(ContractError):
            advanced.triage_defects(request)

    def test_external_reproduction_and_owner_notification_are_not_run(self) -> None:
        result = advanced.triage_defects(triage_request())
        self.assertEqual("NOT_RUN", result["outputs"]["reproduction_execution"])
        self.assertEqual("NOT_RUN", result["outputs"]["ownership_notification"])


class RepairPlanningContractTest(unittest.TestCase):
    def test_positive_selects_lowest_attempt_safe_alternative(self) -> None:
        result = advanced.plan_repair(repair_request())
        plan = result["outputs"]["repair_plan"]
        self.assertEqual("alternative-safe", plan["selected_alternative_id"])
        self.assertTrue(plan["rollback_required"])

    def test_negative_low_confidence_and_forbidden_change_block_plan(self) -> None:
        request = repair_request()
        request["root_cause_confidence"] = 0.2
        request["alternatives"] = [
            {
                "alternative_id": "alternative-forbidden",
                "changes": [{"path": "tests/test_service.py", "kind": "weaken-test"}],
                "validation_steps": ["run tests"],
                "rollback_steps": ["restore tests"],
                "estimated_attempts": 1,
            }
        ]
        result = advanced.plan_repair(request)
        self.assertEqual("BLOCKED", result["state"])
        self.assertIsNone(result["outputs"]["repair_plan"]["selected_alternative_id"])

    def test_duplicate_canonical_path_in_one_alternative_is_rejected(self) -> None:
        request = repair_request()
        request["alternatives"][0]["changes"].append(
            {"path": "src/service.py", "kind": "adapter-fix"}
        )
        with self.assertRaisesRegex(ContractError, "duplicate path"):
            advanced.plan_repair(request)

    def test_forbidden_kind_is_case_normalized_and_cannot_be_selected(self) -> None:
        request = repair_request()
        request["alternatives"] = [
            {
                "alternative_id": "alternative-forbidden-uppercase",
                "changes": [
                    {"path": "tests/test_service.py", "kind": "WEAKEN-TEST"}
                ],
                "validation_steps": ["run tests"],
                "rollback_steps": ["restore tests"],
                "estimated_attempts": 1,
            }
        ]
        result = advanced.plan_repair(request)
        plan = result["outputs"]["repair_plan"]
        alternative = plan["alternatives"][0]
        self.assertEqual("BLOCKED", result["state"])
        self.assertEqual("weaken-test", alternative["changes"][0]["kind"])
        self.assertEqual(["weaken-test"], alternative["forbidden_changes"])
        self.assertFalse(alternative["eligible"])
        self.assertIsNone(plan["selected_alternative_id"])

    def test_external_patch_validation_and_rollback_are_not_run(self) -> None:
        result = advanced.plan_repair(repair_request())
        self.assertEqual("NOT_RUN", result["outputs"]["patch_application"])
        self.assertEqual("NOT_RUN", result["outputs"]["validation_execution"])
        self.assertFalse(result["outputs"]["merge_authorized"])


class TypedImpactContractTest(unittest.TestCase):
    def test_positive_graph_propagation_finds_candidate_test(self) -> None:
        result = advanced.analyze_impact_contract(impact_request())
        self.assertEqual(["test-1"], result["outputs"]["candidate_impacted_tests"])
        self.assertEqual("FULL_REQUIRED", result["outputs"]["scope"])

    def test_negative_graph_digest_mismatch_is_rejected(self) -> None:
        request = impact_request()
        request["graph"]["graph_digest"] = sha("wrong")
        with self.assertRaises(ContractError):
            advanced.analyze_impact_contract(request)

    def test_caller_graph_receipt_never_narrows_without_trusted_binder(self) -> None:
        request = impact_request()
        request["trusted_graph_receipt"] = {"valid": True, "scope": "candidate"}
        result = advanced.analyze_impact_contract(request)
        self.assertEqual("BLOCKED", result["state"])
        self.assertFalse(result["outputs"]["caller_graph_receipt_accepted"])
        self.assertEqual("NOT_RUN", result["outputs"]["trusted_graph_receipt"])


class AdvancedTestingContractTest(unittest.TestCase):
    def test_positive_plan_binds_all_advanced_testing_components(self) -> None:
        result = advanced.plan_advanced_testing(advanced_testing_request())
        plan = result["outputs"]["advanced_testing_plan"]
        self.assertEqual("generator-boundary", plan["property_plans"][0]["generator"]["generator_id"])
        self.assertEqual(1, len(plan["survivor_regressions"]))

    def test_negative_unknown_property_generator_is_rejected(self) -> None:
        request = advanced_testing_request()
        request["properties"][0]["generator_id"] = "generator-missing"
        with self.assertRaises(ContractError):
            advanced.plan_advanced_testing(request)

    def test_external_engines_and_materialization_are_not_run(self) -> None:
        result = advanced.plan_advanced_testing(advanced_testing_request())
        for field in (
            "property_execution",
            "shrinking_execution",
            "fuzz_execution",
            "mutation_execution",
            "survivor_regression_materialization",
        ):
            self.assertEqual("NOT_RUN", result["outputs"][field])


class StructuredReportContractTest(unittest.TestCase):
    def test_positive_report_contains_json_junit_and_html_models(self) -> None:
        result = advanced.build_report(report_request())
        self.assertEqual({"json", "junit", "html"}, set(result["outputs"]["export_plans"]))
        self.assertEqual(2, result["outputs"]["export_plans"]["junit"]["model"]["tests"])

    def test_negative_duplicate_test_result_is_rejected(self) -> None:
        request = report_request()
        request["test_results"].append(copy.deepcopy(request["test_results"][0]))
        with self.assertRaises(ContractError):
            advanced.build_report(request)

    def test_external_export_publication_and_signature_are_not_run(self) -> None:
        result = advanced.build_report(report_request())
        self.assertFalse(result["outputs"]["files_written"])
        self.assertEqual("NOT_RUN", result["outputs"]["publication"])
        self.assertEqual("NOT_RUN", result["outputs"]["signature"])


class DurableStoreContractTest(unittest.TestCase):
    def test_positive_contract_has_cas_lease_fence_rebuild_and_restore(self) -> None:
        result = advanced.create_checkpoint(store_request())
        contract = result["outputs"]["operation_contract"]
        self.assertEqual(5, contract["compare_and_swap"]["next_version"])
        self.assertTrue(contract["fence"]["stale_token_rejected"])
        self.assertTrue(contract["restore"]["post_restore_verification_required"])

    def test_negative_noncontiguous_event_sequence_is_rejected(self) -> None:
        request = store_request()
        request["events"][0]["sequence"] = 2
        with self.assertRaises(ContractError):
            advanced.create_checkpoint(request)

    def test_caller_store_binder_cannot_claim_persistence(self) -> None:
        request = store_request()
        request["trusted_store_binder"] = {"persisted": True}
        result = advanced.create_checkpoint(request)
        self.assertFalse(result["outputs"]["persisted"])
        self.assertFalse(result["outputs"]["caller_store_binder_accepted"])
        self.assertEqual("NOT_RUN", result["outputs"]["durable_store_adapter"])


class RuntimeCostContractTest(unittest.TestCase):
    def test_positive_estimate_has_critical_path_components_cost_and_calibration(self) -> None:
        result = advanced.estimate_eta_contract(estimate_request())
        estimate = result["outputs"]["estimate"]
        self.assertEqual(["task-a", "task-b"], estimate["dag"]["critical_path"])
        self.assertEqual(42.0, estimate["expected_runtime_seconds"])
        self.assertEqual("CALIBRATED", estimate["calibration"]["status"])
        self.assertGreater(estimate["expected_cost"], 0)

    def test_negative_cyclic_estimate_dag_is_rejected(self) -> None:
        request = estimate_request()
        request["tasks"][0]["dependency_ids"] = ["task-b"]
        with self.assertRaises(ContractError):
            advanced.estimate_eta_contract(request)

    def test_caller_pricing_never_becomes_trusted_or_runtime_evidence(self) -> None:
        request = estimate_request()
        request["trusted_price_receipt"] = {"valid": True}
        with self.assertRaises(ContractError):
            advanced.estimate_eta_contract(request)
        result = advanced.estimate_eta_contract(estimate_request())
        self.assertEqual("NOT_RUN", result["outputs"]["runtime_execution"])
        self.assertEqual("NOT_RUN", result["outputs"]["trusted_price_receipt"])
        self.assertFalse(result["outputs"]["caller_price_assertion_accepted"])


class KnowledgeProposalContractTest(unittest.TestCase):
    def test_positive_local_source_creates_versioned_reversible_proposal(self) -> None:
        result = advanced.propose_learning(knowledge_request())
        proposal = result["outputs"]["proposal"]
        self.assertEqual("v1", proposal["version"])
        self.assertEqual("v0", proposal["rollback"]["previous_version"])
        self.assertFalse(result["outputs"]["enabled"])

    def test_negative_duplicate_source_is_rejected(self) -> None:
        request = knowledge_request()
        request["sources"].append(copy.deepcopy(request["sources"][0]))
        with self.assertRaises(ContractError):
            advanced.propose_learning(request)

    def test_external_source_and_persistence_remain_not_run(self) -> None:
        request = knowledge_request()
        request["sources"][0]["external"] = True
        request["trusted_external_source_receipt"] = {"valid": True}
        result = advanced.propose_learning(request)
        self.assertEqual("BLOCKED", result["state"])
        self.assertFalse(result["outputs"]["caller_source_receipt_accepted"])
        self.assertEqual("NOT_RUN", result["outputs"]["trusted_external_source_receipt"])
        self.assertEqual("NOT_RUN", result["outputs"]["persistence"])


class GovernedAuthorizationContractTest(unittest.TestCase):
    def test_positive_local_matrix_validates_every_governance_dimension(self) -> None:
        result = advanced.authorize_action(authorization_request())
        evaluation = result["outputs"]["evaluation"]
        self.assertEqual("MEDIUM", evaluation["risk_level"])
        self.assertEqual([], evaluation["blockers"])
        self.assertEqual("TRUSTED_POLICY_DECISION_REQUIRED", result["code"])

    def test_negative_expired_exception_is_rejected(self) -> None:
        request = authorization_request()
        request["exception"] = {
            "exception_id": "exception-1",
            "scope": "repair",
            "compensating_controls": ["extra-monitoring"],
            "expires_at": "2026-08-23T00:00:00Z",
            "budget_amount": 10,
        }
        result = advanced.authorize_action(request)
        self.assertEqual("LOCAL_POLICY_VALIDATION_FAILED", result["code"])
        self.assertIn("EXCEPTION_EXPIRED", result["outputs"]["evaluation"]["blockers"])

    def test_caller_policy_receipt_never_authorizes_action(self) -> None:
        request = authorization_request()
        request["trusted_policy_receipt"] = {"allowed": True}
        result = advanced.authorize_action(request)
        self.assertFalse(result["outputs"]["allowed"])
        self.assertFalse(result["outputs"]["caller_policy_receipt_accepted"])
        self.assertEqual("NOT_RUN", result["outputs"]["trusted_policy_receipt"])


class AdvancedOperationRegistryTest(unittest.TestCase):
    def test_registry_has_only_the_twelve_release_blocker_operations(self) -> None:
        self.assertEqual(
            {
                "19-distributed-test-execution",
                "20-test-oracle-evidence",
                "21-flaky-test-control",
                "22-defect-triage-rca",
                "23-repair-planning",
                "26-impact-analysis-regression",
                "27-mutation-property-fuzz-testing",
                "29-reporting-observability",
                "30-checkpoint-resume-idempotency",
                "31-runtime-cost-eta",
                "34-continuous-learning-knowledge-base",
                "35-governance-approval-audit",
            },
            set(advanced.ADVANCED_OPERATION_REGISTRY),
        )

    def test_top_level_unknown_fields_and_incomplete_runtime_context_fail_closed(self) -> None:
        with self.assertRaises(ContractError):
            advanced.plan_shards({**scheduler_request(), "embedded_command": "run"})
        with self.assertRaises(ContractError):
            advanced.plan_shards(
                {
                    **scheduler_request(),
                    "_runtime_context": {"tenant_id": "tenant-a"},
                }
            )


if __name__ == "__main__":
    unittest.main()
