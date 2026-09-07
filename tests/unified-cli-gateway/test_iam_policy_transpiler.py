"""Tests for Enterprise Zero-Trust IAM & Security Policy Transpiler."""

import unittest
from elmos_security_engine.iam_policy_transpiler import IamPolicyTranspiler


class TestIamPolicyTranspiler(unittest.TestCase):
    def setUp(self):
        self.transpiler = IamPolicyTranspiler()

    def test_transpile_spring_security_roles(self):
        rule = "hasRole('ROLE_ADMIN') and hasAuthority('READ_FINANCE')"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertEqual(res.source_framework, "spring-security")
        self.assertIn("package elmos.authz", res.rego_policy)
        self.assertEqual(res.iam_statement["Effect"], "Allow")
        self.assertIn("elmos:read:finance", res.iam_statement["Action"])
        self.assertIn("Least-Privilege Non-Escalation Invariant", res.verified_invariants)
        self.assertTrue(res.merkle_receipt.startswith("sha256:"))

    def test_transpile_spring_security_tenant_isolation(self):
        rule = "hasRole('ROLE_OPERATOR') and #tenantId == principal.tenantId"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn("Strict Multi-Tenant Principal Resource Isolation", res.verified_invariants)
        self.assertIn("input.user.tenant_id == input.resource.tenant_id", res.rego_policy)

    def test_verify_non_escalation_verified(self):
        rule = "hasRole('ROLE_ADMIN')"
        rego = "package elmos.authz\ndefault allow = false\nallow { input.user.roles[_] == 'ADMIN' }"
        v = self.transpiler.verify_non_escalation(rule, rego)
        self.assertEqual(v["verdict"], "PROVEN_SAFE_NON_ESCALATION")
        self.assertEqual(v["violations_found"], 0)

    def test_verify_non_escalation_escalation_detected(self):
        rule = "hasRole('ROLE_USER')"
        rego = "package elmos.authz\nallow { true }"  # Missing default allow = false
        v = self.transpiler.verify_non_escalation(rule, rego)
        self.assertEqual(v["verdict"], "UNPROVEN_POTENTIAL_ESCALATION")
        self.assertGreater(v["violations_found"], 0)


if __name__ == "__main__":
    unittest.main()
