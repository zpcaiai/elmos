from __future__ import annotations

import unittest

from elmos_autonomous_qa.context_skills import (
    build_traceability_graph,
    compile_test_model,
    normalize_specification,
    plan_environment_orchestration,
    plan_risk_coverage,
    prepare_test_data,
)
from elmos_autonomous_qa.contracts import ContractError, digest_json


def structured_requirement() -> dict[str, object]:
    return {
        "requirement_id": "REQ-export",
        "title": "Authorized export",
        "statement": "An authorized operator must export a tenant report.",
        "priority": "P0",
        "required": True,
        "source_refs": ["requirements.md:10"],
        "acceptance_criteria": [
            "Given an authorized tenant operator, the exported report belongs to that tenant."
        ],
        "kind": "REQ",
        "status": "ready",
        "actor": "authorized operator",
        "action": "export",
        "object": "tenant report",
        "preconditions": ["operator is authenticated"],
        "postconditions": ["an export audit event exists"],
        "data_classification": "confidential",
        "business_invariants": ["no cross-tenant rows are exported"],
        "conflict_key": "authorized operator export tenant report",
        "polarity": "require",
    }


def graph_fixture() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes = [
        {
            "node_id": "REQ-export",
            "kind": "REQUIREMENT",
            "label": "Authorized export",
            "required": True,
            "source_refs": ["requirements.md:10"],
        },
        {
            "node_id": "CODE-export",
            "kind": "CODE",
            "label": "export_report",
            "source_refs": ["src/export.py:20"],
        },
        {
            "node_id": "TEST-export",
            "kind": "TEST",
            "label": "test authorized export",
            "required": True,
            "attributes": {"executable": True, "oracle_valid": True},
        },
        {
            "node_id": "FILE-export",
            "kind": "TEST_FILE",
            "label": "tests/test_export.py",
        },
        {
            "node_id": "EVID-export",
            "kind": "EVIDENCE",
            "label": "static trace evidence",
        },
    ]
    edges = [
        {
            "from": "CODE-export",
            "to": "REQ-export",
            "kind": "implements",
            "confidence": 1.0,
            "evidence_refs": ["src/export.py:20"],
            "inferred": False,
        },
        {
            "from": "TEST-export",
            "to": "REQ-export",
            "kind": "verifies",
            "confidence": 1.0,
            "evidence_refs": ["requirements.md:10"],
            "inferred": False,
        },
        {
            "from": "TEST-export",
            "to": "FILE-export",
            "kind": "materialized_as",
            "confidence": 1.0,
            "evidence_refs": ["manifest:artifact-export"],
            "inferred": False,
        },
        {
            "from": "EVID-export",
            "to": "TEST-export",
            "kind": "evidenced_by",
            "confidence": 1.0,
            "evidence_refs": ["evidence:export"],
            "inferred": False,
        },
    ]
    return nodes, edges


def dsl_case() -> dict[str, object]:
    return {
        "test_case_id": "TC-export",
        "title": "authorized export stays tenant scoped",
        "test_type": "functional",
        "priority": "P0",
        "required": True,
        "requirement_refs": ["REQ-export"],
        "preconditions": ["authenticated tenant operator"],
        "steps": [
            {
                "step_id": "invoke-export",
                "action": "invoke-export",
                "input": {"tenant_id": "tenant-a"},
                "side_effect": False,
            }
        ],
        "oracles": [
            {
                "oracle_id": "oracle-tenant",
                "kind": "invariant",
                "assertion": "every exported row has tenant_id tenant-a",
                "source": "requirements.md:10",
            }
        ],
        "evidence_requirements": ["structured-result", "raw-runner-output"],
        "cleanup": [],
        "executor": {
            "adapter_key": "python",
            "capability": "unit",
            "parameters": {},
            "environment_profile": "isolated-local",
        },
        "materialization": {
            "planned_paths": ["tests/test_export.py"],
            "validation_status": "planned",
        },
    }


class SpecificationNormalizationTest(unittest.TestCase):
    def test_structured_specification_is_exact_and_locally_complete(self) -> None:
        result = normalize_specification({"requirements": [structured_requirement()]})
        self.assertEqual("SUCCEEDED", result["state"])
        self.assertEqual("LOCAL_EXECUTED", result["implementation_state"])
        self.assertEqual([], result["outputs"]["conflict_groups"])
        requirement = result["outputs"]["requirements"][0]
        self.assertEqual("authorized operator", requirement["actor"])
        self.assertEqual(["confidential"], [requirement["data_classification"]])
        self.assertEqual("NOT_REQUIRED", result["outputs"]["trusted_semantic_normalization"])

    def test_duplicate_structured_requirement_is_rejected(self) -> None:
        duplicate = structured_requirement()
        with self.assertRaises(ContractError):
            normalize_specification({"requirements": [duplicate, duplicate]})

    def test_natural_text_conflicts_remain_partial_and_externally_unresolved(self) -> None:
        result = normalize_specification(
            {
                "documents": [
                    {
                        "source_id": "product-spec",
                        "source_ref": "product.md",
                        "text": (
                            "The service must allow report export.\n"
                            "The service must not allow report export."
                        ),
                        "priority": "P0",
                        "required": True,
                    }
                ]
            }
        )
        self.assertEqual("PARTIAL", result["state"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["implementation_state"])
        self.assertEqual("NOT_RUN", result["outputs"]["trusted_semantic_normalization"])
        self.assertEqual(1, len(result["outputs"]["conflict_groups"]))
        self.assertTrue(result["outputs"]["blocking_requirement_ids"])


class TraceabilityGraphTest(unittest.TestCase):
    def test_multitype_graph_supports_strict_coverage_query_and_incremental_delta(self) -> None:
        nodes, edges = graph_fixture()
        previous_nodes = [dict(node) for node in nodes if node["node_id"] != "EVID-export"]
        previous_ids = {node["node_id"] for node in previous_nodes}
        previous_edges = [
            dict(edge)
            for edge in edges
            if edge["from"] in previous_ids and edge["to"] in previous_ids
        ]
        result = build_traceability_graph(
            {
                "nodes": nodes,
                "edges": edges,
                "strict_confidence": 0.9,
                "queries": [
                    {
                        "query_id": "query-export",
                        "start_node_id": "REQ-export",
                        "direction": "both",
                        "max_depth": 3,
                    }
                ],
                "previous_graph": {
                    "graph_id": "graph-previous",
                    "nodes": previous_nodes,
                    "edges": previous_edges,
                },
            }
        )
        self.assertEqual("SUCCEEDED", result["state"])
        self.assertEqual(1.0, result["outputs"]["strict_executable_coverage"])
        self.assertIn("EVID-export", result["outputs"]["delta"]["added_node_ids"])
        matches = result["outputs"]["query_results"][0]["matches"]
        self.assertIn("TEST-export", {item["node_id"] for item in matches})

    def test_inferred_edge_without_evidence_is_rejected(self) -> None:
        nodes, edges = graph_fixture()
        edges[0] = {**edges[0], "inferred": True, "evidence_refs": []}
        with self.assertRaises(ContractError):
            build_traceability_graph({"nodes": nodes, "edges": edges})

    def test_low_confidence_or_unmaterialized_evidence_never_counts_as_coverage(self) -> None:
        nodes, edges = graph_fixture()
        edges = [
            {**edge, "confidence": 0.4}
            if edge["kind"] == "verifies"
            else edge
            for edge in edges
            if edge["kind"] != "materialized_as"
        ]
        result = build_traceability_graph({"nodes": nodes, "edges": edges})
        self.assertEqual("PARTIAL", result["state"])
        self.assertEqual(0.0, result["outputs"]["strict_executable_coverage"])
        self.assertEqual(["REQ-export"], result["outputs"]["unmapped_required"])
        self.assertEqual(["TEST-export"], result["outputs"]["unmaterialized_required_tests"])


class RiskCoveragePlanningTest(unittest.TestCase):
    def request(self) -> dict[str, object]:
        return {
            "requirements": [
                {
                    "requirement_id": "REQ-export",
                    "priority": "P0",
                    "required": True,
                    "risk_tags": ["api", "security", "performance"],
                    "business_impact": 5,
                    "change_complexity": 4,
                    "historical_defects": 2,
                    "data_sensitivity": "restricted",
                    "external_dependency": True,
                    "dimensions": {
                        "role": ["owner", "viewer"],
                        "state": ["ready", "expired"],
                    },
                    "estimated_seconds": 5,
                }
            ],
            "support_matrix": {"browser": ["chromium", "webkit"]},
            "budget": {
                "wall_clock_seconds": 100_000,
                "max_compute_seconds": 1_000_000,
                "max_cases": 10_000,
            },
        }

    def test_risk_plan_contains_pairwise_suites_and_execution_evidence_boundary(self) -> None:
        result = plan_risk_coverage(self.request())
        self.assertEqual("SUCCEEDED", result["state"])
        self.assertEqual("CRITICAL", result["outputs"]["risk_records"][0]["risk_band"])
        self.assertEqual(
            {"pr-incremental", "nightly-full", "release-certification"},
            set(result["outputs"]["suites"]),
        )
        self.assertEqual("DETERMINISTIC_PAIRWISE_V1", result["outputs"]["combination_strategy"])
        self.assertEqual("NOT_RUN", result["outputs"]["execution"])
        self.assertFalse(result["outputs"]["required_scope_silently_dropped"])

    def test_required_scope_over_budget_is_retained_and_blocks(self) -> None:
        request = self.request()
        request["budget"] = {
            "wall_clock_seconds": 1,
            "max_compute_seconds": 1,
            "max_cases": 1,
        }
        result = plan_risk_coverage(request)
        self.assertEqual("PARTIAL", result["state"])
        self.assertTrue(result["outputs"]["planned_cases"])
        self.assertGreaterEqual(len(result["outputs"]["blockers"]), 1)

    def test_empty_dimension_is_rejected_instead_of_silently_dropped(self) -> None:
        request = self.request()
        request["requirements"][0]["dimensions"] = {"role": []}
        with self.assertRaises(ContractError):
            plan_risk_coverage(request)


class TestModelCompilationTest(unittest.TestCase):
    def test_v10_migration_builds_source_map_but_keeps_native_work_not_run(self) -> None:
        result = compile_test_model(
            {"dsl_version": "1.0", "target_version": "1.1", "test_cases": [dsl_case()]}
        )
        self.assertEqual("PARTIAL", result["state"])
        self.assertTrue(result["outputs"]["migration"]["performed"])
        self.assertEqual(["tests/test_export.py"], result["outputs"]["source_map"][0]["planned_paths"])
        self.assertEqual("NOT_RUN", result["outputs"]["native_source_generation"])
        self.assertEqual("NOT_RUN", result["outputs"]["native_execution"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["implementation_state"])

    def test_unsupported_dsl_version_is_rejected(self) -> None:
        with self.assertRaises(ContractError):
            compile_test_model({"dsl_version": "0.9", "test_cases": [dsl_case()]})

    def test_trivial_oracle_cannot_enter_a_native_compile_plan(self) -> None:
        case = dsl_case()
        case["oracles"][0]["assertion"] = "true"
        with self.assertRaises(ContractError):
            compile_test_model({"dsl_version": "1.1", "test_cases": [case]})


class TestDataPreparationTest(unittest.TestCase):
    def request(self) -> dict[str, object]:
        return {
            "run_id": "run-export",
            "seed": "stable-seed-v1",
            "lease_seconds": 600,
            "datasets": [
                {
                    "dataset_id": "data-export",
                    "source": "synthetic",
                    "classification": "internal",
                    "row_count": 3,
                    "generator_version": "repository-owned-v1",
                    "schema": [
                        {"name": "record_id", "kind": "uuid"},
                        {"name": "tenant", "kind": "enum", "values": ["tenant-a", "tenant-b"]},
                        {"name": "quantity", "kind": "integer", "minimum": 0, "maximum": 100},
                    ],
                }
            ],
        }

    def test_synthetic_bytes_digest_namespace_and_cleanup_are_deterministic(self) -> None:
        first = prepare_test_data(self.request())
        second = prepare_test_data(self.request())
        self.assertEqual(first, second)
        self.assertEqual("PARTIAL", first["state"])
        dataset = first["outputs"]["datasets"][0]
        self.assertTrue(dataset["content_base64"])
        self.assertRegex(dataset["sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertFalse(dataset["cleanup_plan"]["performed"])
        self.assertEqual("NOT_RUN", first["outputs"]["data_materialization"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", first["implementation_state"])

    def test_production_or_unsanitized_source_is_blocked_without_reading_data(self) -> None:
        request = self.request()
        request["datasets"][0]["source"] = "production"
        result = prepare_test_data(request)
        self.assertEqual("BLOCKED", result["state"])
        self.assertIsNone(result["outputs"]["datasets"][0]["content_base64"])
        self.assertFalse(result["outputs"]["production_data_accessed"])
        self.assertEqual("LOCAL_VALIDATED", result["implementation_state"])

    def test_dataset_row_limit_is_enforced_before_generation(self) -> None:
        request = self.request()
        request["datasets"][0]["row_count"] = 0
        with self.assertRaises(ContractError):
            prepare_test_data(request)


class EnvironmentOrchestrationPlanningTest(unittest.TestCase):
    def request(self) -> dict[str, object]:
        template = {
            "kind": "isolated-test-environment",
            "version": "1",
            "network_default": "deny",
        }
        return {
            "environment_id": "env-export",
            "profile": "isolated-integration",
            "template": template,
            "template_digest": digest_json(template),
            "image_digest": "sha256:" + "1" * 64,
            "config": {"clock": "UTC", "tenant_mode": "isolated"},
            "network_allowlist": ["artifact-mirror.internal:443"],
            "secret_refs": ["secret-ref-test-db"],
            "lease_seconds": 900,
            "resources": [
                {"resource_id": "namespace-export", "kind": "namespace", "version": "v1"},
                {
                    "resource_id": "database-export",
                    "kind": "database",
                    "version": "postgres-18.1",
                    "image_digest": "sha256:" + "2" * 64,
                    "configuration": {"database": "qa_export"},
                },
            ],
        }

    def test_exact_environment_plan_is_digest_bound_and_never_provisions(self) -> None:
        result = plan_environment_orchestration(self.request())
        self.assertEqual("PARTIAL", result["state"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["implementation_state"])
        self.assertEqual("NOT_RUN", result["outputs"]["provisioning"])
        self.assertEqual("NOT_RUN", result["outputs"]["readiness_execution"])
        self.assertEqual("NOT_RUN", result["outputs"]["destroy_execution"])
        self.assertEqual("DENY", result["outputs"]["network_policy"]["default"])
        self.assertFalse(result["outputs"]["production_access_allowed"])
        self.assertEqual(
            ["database-export", "namespace-export"],
            [step["resource_id"] for step in result["outputs"]["destroy_steps"]],
        )

    def test_production_profile_and_unpinned_resource_are_rejected(self) -> None:
        request = self.request()
        request["profile"] = "production"
        with self.assertRaises(ContractError):
            plan_environment_orchestration(request)
        request = self.request()
        request["resources"][1]["version"] = "latest"
        with self.assertRaises(ContractError):
            plan_environment_orchestration(request)

    def test_inline_secret_and_template_digest_drift_are_rejected(self) -> None:
        request = self.request()
        request["config"] = {"database_password": "do-not-accept"}
        with self.assertRaises(ContractError):
            plan_environment_orchestration(request)
        request = self.request()
        request["template_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ContractError):
            plan_environment_orchestration(request)


if __name__ == "__main__":
    unittest.main()
