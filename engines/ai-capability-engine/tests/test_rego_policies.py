"""Tests for Rego policy evaluation and compliance gates."""

from __future__ import annotations

import unittest
from elmos_ai_capability.policies import PolicyEngine


class RegoPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = PolicyEngine()

    def test_43_policies_present(self) -> None:
        pols = self.engine.list_policies()
        self.assertEqual(len(pols), 43)
        self.assertIn("no_ambient_authority", pols)
        self.assertIn("tenant_isolation", pols)
        self.assertIn("egress_dlp", pols)

    def test_no_ambient_authority_denies_unauthenticated(self) -> None:
        res = self.engine.evaluate_policy("no_ambient_authority", {"authenticated": False})
        self.assertEqual(res.decision, "DENY")
        self.assertFalse(res.passed)

    def test_tenant_isolation_denies_cross_tenant(self) -> None:
        res = self.engine.evaluate_policy("tenant_isolation", {"request_tenant": "t1", "resource_tenant": "t2"})
        self.assertEqual(res.decision, "DENY")
        self.assertFalse(res.passed)

    def test_validate_all_policies(self) -> None:
        results = self.engine.validate_all_policies()
        self.assertEqual(len(results), 43)
        for name, res in results.items():
            self.assertEqual(res.decision, "ALLOW", f"Policy {name} failed default valid context")


if __name__ == "__main__":
    unittest.main()
