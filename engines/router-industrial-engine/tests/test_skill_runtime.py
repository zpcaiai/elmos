"""Tests for skill_runtime dispatcher and all 14 industrial skills."""

from __future__ import annotations

import unittest

from elmos_router_industrial.domain.errors import RouterBaseError
from elmos_router_industrial.skill_runtime import SKILL_DISPATCH_TABLE, dispatch_skill


class TestSkillRuntime(unittest.TestCase):
    def test_all_14_skills_in_dispatch_table(self):
        expected_skills = [
            "elmos-router-industrial",
            "router-industrial-00-master-orchestrator",
            "router-industrial-01-domain-contracts",
            "router-industrial-02-model-provider-registry",
            "router-industrial-03-policy-and-security",
            "router-industrial-04-routing-engine",
            "router-industrial-05-litellm-gateway",
            "router-industrial-06-native-provider-adapters",
            "router-industrial-07-openrouter-adapter",
            "router-industrial-08-resilience-and-replay",
            "router-industrial-09-cost-rate-limit-accounting",
            "router-industrial-10-observability-and-evals",
            "router-industrial-11-deployment-and-operations",
            "router-industrial-12-certification-and-rollout",
        ]
        for skill_name in expected_skills:
            self.assertIn(skill_name, SKILL_DISPATCH_TABLE)

    def test_dispatch_00_master_orchestrator(self):
        res = dispatch_skill("router-industrial-00-master-orchestrator", {"action": "status"})
        self.assertEqual(res["status"], "OPERATIONAL")
        self.assertIn("feature_flags", res)

    def test_dispatch_01_domain_contracts(self):
        res = dispatch_skill("router-industrial-01-domain-contracts", {"contract_type": "schema_check"})
        self.assertEqual(res["status"], "VALID")
        self.assertEqual(res["validation_errors"], [])

    def test_dispatch_02_model_provider_registry(self):
        res = dispatch_skill("router-industrial-02-model-provider-registry", {"action": "list"})
        self.assertGreater(res["total_deployments"], 0)
        self.assertIn("openai-direct", res["providers"])

    def test_dispatch_03_policy_and_security(self):
        res = dispatch_skill("router-industrial-03-policy-and-security", {"action": "redact", "text": "secret is sk-1234567890abcdef1234567890abcdef"})
        self.assertTrue(res["secrets_detected"])
        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", res["redacted_text"])

    def test_dispatch_04_routing_engine(self):
        res = dispatch_skill("router-industrial-04-routing-engine", {"request": {"task_id": "test-t1", "prompt": "Hello"}})
        self.assertEqual(res["status"], "ROUTED")
        self.assertTrue(res["selected_deployment_id"])

    def test_dispatch_05_litellm_gateway(self):
        res = dispatch_skill("router-industrial-05-litellm-gateway", {"action": "health"})
        self.assertEqual(res["status"], "HEALTHY")

    def test_dispatch_06_native_provider_adapters(self):
        res = dispatch_skill("router-industrial-06-native-provider-adapters", {})
        self.assertEqual(len(res["adapters"]), 3)
        self.assertEqual(res["adapters"][0]["id"], "native-openai")

    def test_dispatch_07_openrouter_adapter(self):
        res = dispatch_skill("router-industrial-07-openrouter-adapter", {"action": "health"})
        self.assertTrue(res["healthy"])

    def test_dispatch_08_resilience_and_replay(self):
        res = dispatch_skill("router-industrial-08-resilience-and-replay", {"action": "test_idempotency"})
        self.assertTrue(res["first_commit"])
        self.assertTrue(res["second_commit_is_duplicate"])

    def test_dispatch_09_cost_rate_limit_accounting(self):
        res = dispatch_skill("router-industrial-09-cost-rate-limit-accounting", {"action": "check_budget"})
        self.assertTrue(res["allowed"])

    def test_dispatch_10_observability_and_evals(self):
        res = dispatch_skill("router-industrial-10-observability-and-evals", {"action": "benchmark"})
        self.assertTrue(res["passed"])

    def test_dispatch_11_deployment_and_operations(self):
        res = dispatch_skill("router-industrial-11-deployment-and-operations", {"action": "readiness"})
        self.assertEqual(res["status"], "READY")

    def test_dispatch_12_certification_and_rollout(self):
        res = dispatch_skill("router-industrial-12-certification-and-rollout", {"phase": "phase_2", "target_ramp": 0.05})
        self.assertEqual(res["certification_status"], "READY_FOR_RAMPING")
        self.assertEqual(res["current_ramp"], 0.05)

    def test_dispatch_root_master_skill(self):
        res = dispatch_skill("elmos-router-industrial", {"action": "status"})
        self.assertEqual(res["status"], "OPERATIONAL")

    def test_dispatch_unknown_skill_raises_error(self):
        with self.assertRaises(RouterBaseError):
            dispatch_skill("unknown-skill")


if __name__ == "__main__":
    unittest.main()
