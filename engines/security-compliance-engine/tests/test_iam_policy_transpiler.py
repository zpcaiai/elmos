"""Unit tests for IamPolicyTranspiler in elmos_security_engine."""

from __future__ import annotations

import unittest

from elmos_security_engine.iam_policy_transpiler import IamPolicyTranspiler


class IamPolicyTranspilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transpiler = IamPolicyTranspiler()

    def test_transpile_spring_security_has_role(self) -> None:
        rule = "hasRole('ROLE_ADMIN')"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertEqual(res.source_framework, "spring-security")
        self.assertEqual(res.target_format, "opa-rego-v1")
        self.assertIn('"ADMIN"', res.rego_policy)
        self.assertIn("default allow = false", res.rego_policy)
        self.assertTrue(res.merkle_receipt.startswith("sha256:"))

    def test_transpile_spring_security_tenant_isolation(self) -> None:
        rule = "hasRole('ROLE_USER') and principal.tenantId == #tenantId"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn("input.user.tenant_id == input.resource.tenant_id", res.rego_policy)
        self.assertIn("Strict Multi-Tenant Principal Resource Isolation", res.verified_invariants)
        self.assertIn("arn:elmos:security:tenant/${aws:PrincipalTag/TenantId}/*", res.iam_statement["Resource"])

    def test_non_escalation_verification(self) -> None:
        rule = "hasRole('ADMIN')"
        res = self.transpiler.transpile_spring_security(rule)
        verdict = self.transpiler.verify_non_escalation(rule, res.rego_policy)
        self.assertEqual(verdict["verdict"], "PROVEN_SAFE_NON_ESCALATION")
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["violations_found"], 0)


if __name__ == "__main__":
    unittest.main()
