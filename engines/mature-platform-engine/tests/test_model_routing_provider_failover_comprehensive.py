"""Comprehensive test suite for ModelRoutingProviderFailoverEngine (Batch 42 - Skill 1425)."""

import unittest

from elmos_mature_platform.model_routing_provider_failover_engine import (
    ModelRoutingProviderFailoverEngine,
)
from elmos_mature_platform.types import (
    ModelProviderEndpoint,
    ModelProviderType,
    ProviderCircuitState,
)


class TestModelRoutingProviderFailoverComprehensive(unittest.TestCase):
    """Rigorous tests covering model endpoint registration, priority routing, circuit breakers, and failover."""

    def setUp(self) -> None:
        self.engine = ModelRoutingProviderFailoverEngine()

    def test_register_provider_success(self) -> None:
        p = ModelProviderEndpoint(
            provider_id="ep-openai-gpt4o",
            provider_type=ModelProviderType.OPENAI,
            model_name="gpt-4o",
            cost_per_1k_tokens=0.005,
            avg_latency_ms=300.0,
            priority=1,
        )
        pid = self.engine.register_provider(p)
        self.assertEqual(pid, "ep-openai-gpt4o")

        retrieved = self.engine.get_provider(pid)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.circuit_state, ProviderCircuitState.CLOSED)

    def test_register_provider_missing_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_provider(
                ModelProviderEndpoint(
                    provider_id="",
                    provider_type=ModelProviderType.GEMINI,
                    model_name="",
                )
            )

    def test_circuit_breaker_tripping_on_consecutive_failures(self) -> None:
        p = ModelProviderEndpoint(
            provider_id="ep-anthropic-claude",
            provider_type=ModelProviderType.ANTHROPIC,
            model_name="claude-3-7-sonnet",
        )
        self.engine.register_provider(p)

        # 2 failures do not open the circuit
        self.engine.record_call_result("ep-anthropic-claude", success=False)
        self.engine.record_call_result("ep-anthropic-claude", success=False)
        self.assertEqual(p.circuit_state, ProviderCircuitState.CLOSED)

        # 3rd failure trips the circuit to OPEN
        self.engine.record_call_result("ep-anthropic-claude", success=False)
        self.assertEqual(p.circuit_state, ProviderCircuitState.OPEN)

    def test_reset_circuit_and_half_open_recovery(self) -> None:
        p = ModelProviderEndpoint(
            provider_id="ep-gemini-pro",
            provider_type=ModelProviderType.GEMINI,
            model_name="gemini-1.5-pro",
        )
        self.engine.register_provider(p)

        for _ in range(3):
            self.engine.record_call_result("ep-gemini-pro", success=False)
        self.assertEqual(p.circuit_state, ProviderCircuitState.OPEN)

        # Reset to HALF_OPEN
        self.engine.reset_circuit("ep-gemini-pro")
        self.assertEqual(p.circuit_state, ProviderCircuitState.HALF_OPEN)

        # Success in HALF_OPEN recovers to CLOSED
        self.engine.record_call_result("ep-gemini-pro", success=True, latency_ms=200.0)
        self.assertEqual(p.circuit_state, ProviderCircuitState.CLOSED)

    def test_route_model_call_priority_and_failover_chain(self) -> None:
        # Primary: cheap, priority 1
        self.engine.register_provider(
            ModelProviderEndpoint(
                provider_id="ep-primary",
                provider_type=ModelProviderType.OPENAI,
                model_name="gpt-4o-mini",
                priority=1,
                cost_per_1k_tokens=0.001,
            )
        )
        # Secondary: backup, priority 2
        self.engine.register_provider(
            ModelProviderEndpoint(
                provider_id="ep-backup",
                provider_type=ModelProviderType.DEEPSEEK,
                model_name="deepseek-coder",
                priority=2,
                cost_per_1k_tokens=0.002,
            )
        )

        decision = self.engine.route_model_call("code_refactoring")
        self.assertEqual(decision.selected_provider_id, "ep-primary")
        self.assertEqual(decision.fallback_chain, ["ep-backup"])

        # Trip primary circuit
        for _ in range(3):
            self.engine.record_call_result("ep-primary", success=False)

        # Re-route should automatically failover to backup
        decision2 = self.engine.route_model_call("code_refactoring")
        self.assertEqual(decision2.selected_provider_id, "ep-backup")
        self.assertEqual(decision2.fallback_chain, [])

    def test_all_endpoints_down_raises_runtime_error(self) -> None:
        self.engine.register_provider(
            ModelProviderEndpoint(
                provider_id="ep-only",
                provider_type=ModelProviderType.LOCAL_AIRGAP,
                model_name="llama-3",
            )
        )
        for _ in range(3):
            self.engine.record_call_result("ep-only", success=False)

        with self.assertRaises(RuntimeError):
            self.engine.route_model_call("general_query")

    def test_routing_report(self) -> None:
        self.engine.register_provider(
            ModelProviderEndpoint(
                provider_id="p1", provider_type=ModelProviderType.OPENAI, model_name="m1"
            )
        )
        self.engine.register_provider(
            ModelProviderEndpoint(
                provider_id="p2", provider_type=ModelProviderType.GEMINI, model_name="m2"
            )
        )
        rep = self.engine.get_routing_report()
        self.assertEqual(rep["total_providers"], 2)
        self.assertEqual(rep["open_circuits_count"], 0)


if __name__ == "__main__":
    unittest.main()
