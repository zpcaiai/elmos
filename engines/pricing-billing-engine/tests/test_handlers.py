"""Unit tests for all 18 pricing and billing skill handlers."""

from __future__ import annotations

import unittest

from elmos_pricing_billing.handlers import SKILL_REGISTRY, dispatch_skill


class HandlersTests(unittest.TestCase):
    def test_all_18_skills_registered(self) -> None:
        self.assertEqual(len(SKILL_REGISTRY), 18)

    def test_dispatch_all_skills(self) -> None:
        for skill_name in SKILL_REGISTRY:
            req_data = {
                "schema_version": "1.0",
                "request_id": f"req-{skill_name}",
                "tenant_id": "tenant-test",
                "organization_id": "org-test",
                "project_id": "proj-test",
                "actor_id": "test-user",
                "idempotency_key": f"idem-{skill_name}",
                "inputs": {
                    "prompt_tokens": 1500,
                    "completion_tokens": 800,
                    "runner_seconds": 20.0,
                    "max_budget_usd": "50.00",
                    "current_spend_usd": "10.00",
                },
            }
            res = dispatch_skill(skill_name, req_data)
            self.assertEqual(res.status, "SUCCESS", f"Skill {skill_name} failed: {res.error}")
            self.assertTrue(res.evidence_digest.startswith("sha256:"))
            self.assertIn("COMPLETED", str(res.outputs))

    def test_dispatch_unknown_skill_fails_closed(self) -> None:
        req_data = {
            "schema_version": "1.0",
            "request_id": "req-unknown",
            "tenant_id": "tenant-test",
            "organization_id": "org-test",
            "project_id": "proj-test",
            "actor_id": "test-user",
            "idempotency_key": "idem-unknown",
            "inputs": {},
        }
        res = dispatch_skill("elmos-unknown-billing-skill", req_data)
        self.assertEqual(res.status, "BLOCKED")
        self.assertIn("unknown", res.error.lower())


if __name__ == "__main__":
    unittest.main()
