"""End-to-end runtime integration tests for AI Capability Enhancement."""

from __future__ import annotations

from pathlib import Path
import unittest

from elmos_ai_capability.service import AICapabilityService

ROOT = Path(__file__).resolve().parents[2]


class RuntimeServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = AICapabilityService()

    def test_run_skill(self) -> None:
        res = self.service.run_skill("elmos-a2a-v1-agent-card-trust-compiler", {
            "agent_id": "test-agent-1",
            "tenant_id": "tenant-test",
            "project_id": "proj-test",
        })
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("agent-card.json", res.outputs)

    def test_run_golden_route(self) -> None:
        res = self.service.run_golden_route("acp-coding-agent-client")
        self.assertEqual(res.status, "QUALIFIED")

    def test_run_workflow(self) -> None:
        res = self.service.run_workflow("agent-incident-containment")
        self.assertEqual(res.status, "COMPLETED")

    def test_database_migrations_validation(self) -> None:
        results = self.service.validate_database_migrations()
        self.assertEqual(len(results), 20)

    def test_policies_evaluation(self) -> None:
        res = self.service.evaluate_policy("tenant_isolation", {
            "request_tenant": "t1",
            "resource_tenant": "t1",
        })
        self.assertEqual(res.decision, "ALLOW")

    def test_negotiate_capabilities(self) -> None:
        reqs = [{"name": "chat", "critical": True}]
        profiles = [{
            "target": "tgt-1",
            "features": {"chat": "supported"},
            "exactVersion": "1.0.0",
            "adapterDigest": "sha256:111",
        }]
        res = self.service.negotiate_capabilities(reqs, profiles)
        self.assertEqual(res.overall, "SUPPORTED")


if __name__ == "__main__":
    unittest.main()
