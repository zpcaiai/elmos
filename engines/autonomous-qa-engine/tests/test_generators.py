from __future__ import annotations

import unittest

from elmos_autonomous_qa import generators
from elmos_autonomous_qa.contracts import ContractError


REQUIREMENTS = [
    {
        "requirement_id": "REQ-1",
        "title": "Preserve the governed behavior",
        "statement": "The governed behavior follows its exact contract.",
        "acceptance_criteria": ["The observable result and side effects match the contract."],
        "priority": "P0",
        "required": True,
        "risk_tags": ["critical"],
    }
]


class DomainGeneratorTest(unittest.TestCase):
    def assert_external_boundary(self, result: dict) -> None:
        self.assertEqual("PARTIAL", result["state"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["implementation_state"])
        self.assertEqual("LOCAL_EXECUTED", result["outputs"]["dsl_generation"])
        self.assertEqual("NOT_RUN", result["outputs"]["native_source_generation"])
        self.assertEqual("NOT_RUN", result["outputs"]["materialization"])
        self.assertEqual("NOT_RUN", result["outputs"]["runner_execution"])
        self.assertTrue(result["outputs"]["test_cases"])

    def test_06_functional_generation_models_rules_boundaries_states_permissions_and_retries(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "business_rules": [{"rule_id": "rule-1", "assertion": "balance never becomes negative", "requirement_refs": ["REQ-1"]}],
            "boundaries": [{"field_id": "amount", "data_type": "decimal", "minimum": "0.01", "maximum": "999.99", "nullable": False, "enum": []}],
            "state_models": [{"state_model_id": "order", "states": ["draft", "paid"], "transitions": [{"from": "draft", "to": "paid", "event": "pay", "allowed": True}]}],
            "roles": [{"role_id": "owner", "allowed_actions": ["read"], "denied_actions": ["admin"]}],
            "operations": [{"operation_id": "pay", "side_effect": True, "idempotency_required": True, "concurrency_required": True}],
        }
        result = dict(generators.generate_functional_tests(payload))
        self.assert_external_boundary(result)
        self.assertFalse(result["outputs"]["blockers"])
        actions = {case["steps"][0]["action"] for case in result["outputs"]["test_cases"]}
        self.assertIn("invoke-concurrently", actions)
        self.assertIn("attempt-illegal-transition", actions)
        with self.assertRaises(ContractError):
            generators.generate_functional_tests({**payload, "state_models": [{"state_model_id": "order", "states": ["draft"], "transitions": [{"from": "draft", "to": "missing", "event": "pay"}]}]})

    def test_07_api_generation_parses_operations_and_detects_breaking_changes(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "api_operations": [{"operation_id": "create-order", "protocol": "rest", "request_fields": ["amount"], "required_request_fields": ["amount"], "previous_required_request_fields": [], "response_fields": ["id"], "previous_response_fields": ["id", "legacy"], "content_types": ["application/json"], "security_schemes": ["oauth2"], "side_effects": ["order-created"]}],
            "consumer_contracts": [{"consumer_id": "checkout", "version": "1.0", "operation_refs": ["create-order"]}],
        }
        result = dict(generators.plan_api_contract_tests(payload))
        self.assert_external_boundary(result)
        kinds = {finding["kind"] for finding in result["outputs"]["breaking_change_findings"]}
        self.assertEqual({"REQUEST_FIELD_NEWLY_REQUIRED", "RESPONSE_FIELD_REMOVED"}, kinds)
        self.assertEqual("NOT_RUN", result["outputs"]["provider_consumer_execution"])
        with self.assertRaises(ContractError):
            generators.plan_api_contract_tests({**payload, "api_operations": [{"operation_id": "x", "protocol": "soap"}]})

    def test_08_database_generation_models_constraints_migrations_and_detail_reconciliation(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "tables": [{"table_id": "orders", "columns": [{"column_id": "id", "data_type": "uuid", "nullable": False, "primary_key": True, "unique": True, "checks": []}], "foreign_keys": [], "business_invariants": ["amount >= 0"]}],
            "migrations": [{"migration_id": "migration-1", "source_version": "1", "target_version": "2", "idempotency_strategy": "version-ledger", "rollback_declared": True}],
        }
        result = dict(generators.plan_database_tests(payload))
        self.assert_external_boundary(result)
        self.assertIn("row-detail", result["outputs"]["reconciliation_dimensions"])
        self.assertFalse(result["outputs"]["production_writes_authorized"])
        with self.assertRaises(ContractError):
            generators.plan_database_tests({**payload, "tables": [{"table_id": "orders", "columns": []}]})

    def test_09_message_generation_models_delivery_compensation_and_dst(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "messages": [{"message_id": "order-created", "destination": "orders", "schema_version": "1", "delivery_semantics": "at-least-once", "ordering_key": "order-id", "deduplication_window_seconds": 60, "retry_limit": 3, "dead_letter_declared": True}],
            "workflows": [{"workflow_id": "checkout", "steps": [{"step_id": "reserve", "timeout_seconds": 5, "compensation": "release", "compensation_idempotent": True}]}],
            "schedules": [{"schedule_id": "daily-close", "timezone": "Asia/Shanghai", "cron": "0 0 * * *", "dst_policy": "explicit"}],
        }
        result = dict(generators.plan_message_workflow_tests(payload))
        self.assert_external_boundary(result)
        self.assertTrue(result["outputs"]["time_domains_separated"])
        self.assertEqual("NOT_RUN", result["outputs"]["broker_execution"])
        with self.assertRaises(ContractError):
            generators.plan_message_workflow_tests({**payload, "messages": [{"message_id": "x", "destination": "q", "schema_version": "1", "delivery_semantics": "at-least-once", "retry_limit": True, "dead_letter_declared": False}]})

    def test_10_ui_generation_enforces_stable_locators_and_observable_waits(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "journeys": [{"journey_id": "checkout", "role": "buyer", "tenant": "tenant-a", "isolated_test_data": True, "steps": [{"step_id": "submit", "action": "click", "locator": "role=button[name=Submit]", "wait_for": "order confirmation is visible", "observable": "confirmation appears", "backend_effect": "one order exists"}]}],
            "support_matrix": [{"browser": "chromium", "version": "exact-image", "device": "desktop", "os": "linux"}],
        }
        result = dict(generators.plan_ui_e2e_tests(payload))
        self.assert_external_boundary(result)
        self.assertEqual("ACCESSIBLE_ROLE_LABEL_OR_STABLE_TEST_ID", result["outputs"]["locator_policy"])
        self.assertEqual("NOT_RUN", result["outputs"]["browser_device_execution"])
        broken = {**payload, "journeys": [{**payload["journeys"][0], "steps": [{**payload["journeys"][0]["steps"][0], "locator": "/html/body/div"}]}]}
        with self.assertRaises(ContractError):
            generators.plan_ui_e2e_tests(broken)

    def test_11_visual_generation_binds_baselines_and_never_auto_accepts(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "visual_targets": [{"target_id": "home", "viewports": ["1280x720"], "themes": ["light"], "locales": ["en-US"], "content_lengths": ["long"], "semantic_masks": ["clock"]}],
            "baselines": [{"baseline_id": "home-light", "sha256": "a" * 64, "commit": "abc123", "browser_image": "sha256:image", "font_manifest": "sha256:fonts"}],
        }
        result = dict(generators.plan_visual_responsive_tests(payload))
        self.assert_external_boundary(result)
        self.assertFalse(result["outputs"]["baseline_auto_accept"])
        self.assertEqual("NOT_RUN", result["outputs"]["baseline_mutation"])
        with self.assertRaises(ContractError):
            generators.plan_visual_responsive_tests({**payload, "baselines": [{**payload["baselines"][0], "sha256": "bad"}]})

    def test_12_accessibility_generation_combines_rules_journeys_and_real_engine_matrix(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "accessibility_targets": [{"target_id": "checkout", "roles": ["form"], "keyboard_path": ["email", "submit"], "dynamic_updates": ["error-summary"], "components": ["dialog"]}],
            "compatibility_matrix": [{"browser": "firefox", "engine": "gecko", "device": "desktop", "os": "linux", "fallback": "show an explicit unsupported notice"}],
        }
        result = dict(generators.plan_accessibility_compatibility_tests(payload))
        self.assert_external_boundary(result)
        self.assertFalse(result["outputs"]["automated_scan_is_sufficient"])
        self.assertEqual("NOT_RUN", result["outputs"]["browser_device_execution"])
        with self.assertRaises(ContractError):
            generators.plan_accessibility_compatibility_tests({**payload, "accessibility_targets": [{"target_id": "x", "keyboard_path": []}]})

    def test_13_performance_generation_keeps_tail_errors_and_environment_identity(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "performance_scenarios": [{"scenario_id": "checkout", "arrival_rate_per_second": 10, "concurrency": 5, "think_time_seconds": 0.1, "data_scale": "10k-orders", "warmup_seconds": 30, "steady_state_seconds": 120}],
            "slo_budgets": [{"metric": "latency", "percentile": "p99", "maximum": 500, "unit": "ms", "regression_percent": 5}],
            "environment": {"environment_id": "perf-a", "image_digest": "sha256:image", "data_digest": "sha256:data"},
        }
        result = dict(generators.plan_performance_baseline_tests(payload))
        self.assert_external_boundary(result)
        self.assertIn("p99", result["outputs"]["required_metrics"])
        self.assertFalse(result["outputs"]["environment"]["load_generator_capacity_verified"])
        with self.assertRaises(ContractError):
            generators.plan_performance_baseline_tests({**payload, "performance_scenarios": [{**payload["performance_scenarios"][0], "concurrency": float("nan")}]})

    def test_14_load_generation_preserves_distinct_phases_and_soak_wall_time(self) -> None:
        phases = [{"phase_id": f"phase-{kind}", "phase_type": kind, "duration_seconds": 60, "arrival_curve": ["10/s"], "stop_conditions": ["error-rate > 5%"], "resource_profile": "small"} for kind in ("load", "stress", "spike", "soak", "capacity", "recovery")]
        payload = {
            "requirements": REQUIREMENTS,
            "workload_phases": phases,
            "capacity_profiles": [{"profile_id": "small", "replicas": 2, "cpu": "2", "memory": "4Gi", "cost_basis": "usd-hour"}],
        }
        result = dict(generators.plan_load_stress_spike_soak_tests(payload))
        self.assert_external_boundary(result)
        self.assertFalse(result["outputs"]["blockers"])
        self.assertEqual("NOT_RUN", result["outputs"]["load_runner_execution"])
        broken_phases = [dict(item) for item in phases]
        broken_phases[3]["parallel_time_compression"] = True
        with self.assertRaises(ContractError):
            generators.plan_load_stress_spike_soak_tests({**payload, "workload_phases": broken_phases})

    def test_15_security_generation_requires_authorized_scope_and_inert_execution(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "trust_boundaries": [{"boundary_id": "public-api", "source_zone": "internet", "target_zone": "service", "data_classes": ["confidential"], "required_controls": ["authentication"]}],
            "threats": [{"threat_id": "cross-tenant", "entrypoint": "get-order", "category": "authorization", "authorized_scope": True, "expected_control": "resource ownership is enforced"}],
            "authorization_pairs": [{"resource_id": "order-1", "owner_tenant": "tenant-a", "allowed_role": "owner", "denied_role": "viewer", "foreign_tenant": "tenant-b"}],
        }
        result = dict(generators.plan_security_abuse_tests(payload))
        self.assert_external_boundary(result)
        self.assertEqual("NOT_RUN", result["outputs"]["active_attack_execution"])
        self.assertFalse(result["outputs"]["plaintext_secret_or_personal_data_retained"])
        with self.assertRaises(ContractError):
            generators.plan_security_abuse_tests({**payload, "threats": [{**payload["threats"][0], "authorized_scope": False}]})

    def test_16_resilience_generation_requires_blast_radius_abort_and_rollback(self) -> None:
        payload = {
            "requirements": REQUIREMENTS,
            "steady_state": [{"invariant_id": "orders-conserved", "assertion": "accepted orders equal durable orders", "measurement": "order-count", "tolerance": 0}],
            "experiments": [{"experiment_id": "dependency-timeout", "environment": "isolated-qa", "fault_type": "latency", "target": "payments", "blast_radius": "one isolated tenant", "abort_conditions": ["error budget exhausted"], "rollback_steps": ["remove latency fault"], "rto_seconds": 30, "rpo_seconds": 0}],
            "dependencies": [{"dependency_id": "payments", "timeout_ms": 1000, "retry_limit": 2, "circuit_breaker": True, "fallback": "reject without side effect"}],
        }
        result = dict(generators.plan_resilience_chaos_recovery_tests(payload))
        self.assert_external_boundary(result)
        self.assertFalse(result["outputs"]["production_execution_authorized"])
        self.assertEqual("NOT_RUN", result["outputs"]["chaos_execution"])
        with self.assertRaises(ContractError):
            generators.plan_resilience_chaos_recovery_tests({**payload, "experiments": [{**payload["experiments"][0], "environment": "production"}]})

    def test_each_domain_uses_distinct_semantic_actions_instead_of_profile_labels(self) -> None:
        minimal = {"requirements": REQUIREMENTS}
        operations = (
            generators.generate_functional_tests,
            generators.plan_api_contract_tests,
            generators.plan_database_tests,
            generators.plan_message_workflow_tests,
            generators.plan_ui_e2e_tests,
            generators.plan_visual_responsive_tests,
            generators.plan_accessibility_compatibility_tests,
            generators.plan_performance_baseline_tests,
            generators.plan_load_stress_spike_soak_tests,
            generators.plan_security_abuse_tests,
            generators.plan_resilience_chaos_recovery_tests,
        )
        action_sets = [
            frozenset(case["steps"][0]["action"] for case in operation(minimal)["outputs"]["test_cases"])
            for operation in operations
        ]
        self.assertEqual(len(action_sets), len(set(action_sets)))

    def test_every_domain_rejects_unknown_top_level_fields_and_partial_runtime_context(self) -> None:
        operations = (
            generators.generate_functional_tests,
            generators.plan_api_contract_tests,
            generators.plan_database_tests,
            generators.plan_message_workflow_tests,
            generators.plan_ui_e2e_tests,
            generators.plan_visual_responsive_tests,
            generators.plan_accessibility_compatibility_tests,
            generators.plan_performance_baseline_tests,
            generators.plan_load_stress_spike_soak_tests,
            generators.plan_security_abuse_tests,
            generators.plan_resilience_chaos_recovery_tests,
        )
        for operation in operations:
            with self.subTest(operation=operation.__name__), self.assertRaises(
                ContractError
            ):
                operation({"requirements": REQUIREMENTS, "embedded_command": "run"})
            with self.subTest(
                context=operation.__name__
            ), self.assertRaises(ContractError):
                operation(
                    {
                        "requirements": REQUIREMENTS,
                        "_runtime_context": {"tenant_id": "tenant-a"},
                    }
                )


if __name__ == "__main__":
    unittest.main()
