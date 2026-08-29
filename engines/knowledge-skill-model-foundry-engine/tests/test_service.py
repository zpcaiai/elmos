"""Unit tests for top-level FoundryService and ServingGateway."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.service import FoundryService


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FoundryService()
        self.scope = TenantScope(tenant_id="tenant-svc-01", project_id="proj-svc-01")

    def test_serving_gateway_routing_and_cache(self) -> None:
        # Standard routing
        res1 = self.service.serving.route_inference(
            prompt="Write a Python class for financial reconciliation",
            task_complexity="standard",
            tenant_scope=self.scope,
        )
        self.assertEqual(res1["selected_model"], "elmos-private-qwen2.5-coder-32b")
        self.assertFalse(res1["cached"])

        # Cache hit
        res2 = self.service.serving.route_inference(
            prompt="Write a Python class for financial reconciliation",
            task_complexity="standard",
            tenant_scope=self.scope,
        )
        self.assertTrue(res2["cached"])

    def test_serving_circuit_breaker(self) -> None:
        model = "elmos-private-deepseek-v3"
        # Trip circuit breaker
        self.service.serving.record_failure(model)
        self.service.serving.record_failure(model)
        self.service.serving.record_failure(model)

        res = self.service.serving.route_inference(
            prompt="Complex symbolic logic verification",
            task_complexity="critical",
            tenant_scope=self.scope,
        )
        # Should fallback to claude-3-5-sonnet
        self.assertEqual(res["selected_model"], "claude-3-5-sonnet")

        # Recover
        self.service.serving.record_success(model)

    def test_service_execute_skill(self) -> None:
        res = self.service.execute_skill(
            "00-foundation-contracts",
            {"test_key": "test_val"},
            tenant_scope=self.scope,
        )
        self.assertEqual(res.status, "SUCCESS")


if __name__ == "__main__":
    unittest.main()
