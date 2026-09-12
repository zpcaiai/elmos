"""Comprehensive unit tests for IamPolicyTranspiler in elmos_security_engine."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_security_engine.iam_policy_transpiler import IamPolicyTranspiler, PolicyTranspileResult


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

    def test_transpile_spring_security_has_any_role(self) -> None:
        rule = "hasAnyRole('ROLE_ADMIN', 'ROLE_MANAGER', 'AUDITOR')"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn('"ADMIN"', res.rego_policy)
        self.assertIn('"MANAGER"', res.rego_policy)
        self.assertIn('"AUDITOR"', res.rego_policy)
        self.assertEqual(res.iam_statement["Condition"]["StringEquals"]["elmos:UserRole"], ["ADMIN", "MANAGER", "AUDITOR"])

    def test_transpile_spring_security_has_authority(self) -> None:
        rule = "hasAuthority('USER_READ')"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn('"USER_READ"', res.rego_policy)
        self.assertIn("elmos:user:read", res.iam_statement["Action"])

    def test_transpile_spring_security_has_any_authority(self) -> None:
        rule = "hasAnyAuthority('DOC_READ', 'DOC_WRITE')"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn('"DOC_READ"', res.rego_policy)
        self.assertIn('"DOC_WRITE"', res.rego_policy)
        self.assertIn("elmos:doc:read", res.iam_statement["Action"])
        self.assertIn("elmos:doc:write", res.iam_statement["Action"])

    def test_transpile_spring_security_tenant_isolation(self) -> None:
        rule = "hasRole('ROLE_USER') and principal.tenantId == #tenantId"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn("input.user.tenant_id == input.resource.tenant_id", res.rego_policy)
        self.assertIn("Strict Multi-Tenant Principal Resource Isolation", res.verified_invariants)
        self.assertIn("arn:elmos:security:tenant/${aws:PrincipalTag/TenantId}/*", res.iam_statement["Resource"])

    def test_transpile_spring_security_permit_all(self) -> None:
        rule = "permitAll()"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn("allow { true }", res.rego_policy)
        self.assertEqual(res.iam_statement["Effect"], "Allow")

    def test_transpile_spring_security_deny_all(self) -> None:
        rule = "denyAll()"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertEqual(res.iam_statement["Effect"], "Deny")
        self.assertIn("Explicit Absolute Deny Enforcement", res.verified_invariants)

    def test_transpile_spring_security_is_authenticated(self) -> None:
        rule = "isAuthenticated()"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn("input.user.authenticated == true", res.rego_policy)

    def test_transpile_spring_security_is_anonymous(self) -> None:
        rule = "isAnonymous()"
        res = self.transpiler.transpile_spring_security(rule)
        self.assertIn("not input.user.authenticated", res.rego_policy)

    def test_transpile_shiro_permission_wildcard(self) -> None:
        rule = "document:read,write:doc123"
        res = self.transpiler.transpile_shiro_permission(rule)
        self.assertEqual(res.source_framework, "apache-shiro")
        self.assertIn('input.action.domain == "document"', res.rego_policy)
        self.assertIn('"read"', res.rego_policy)
        self.assertIn('"write"', res.rego_policy)
        self.assertIn('"doc123"', res.rego_policy)
        self.assertEqual(res.iam_statement["Action"], ["elmos:document:read", "elmos:document:write"])
        self.assertEqual(res.iam_statement["Resource"], "arn:elmos:document:::doc123")

    def test_transpile_shiro_permission_all_actions(self) -> None:
        rule = "printer:*"
        res = self.transpiler.transpile_shiro_permission(rule)
        self.assertIn('input.action.domain == "printer"', res.rego_policy)
        self.assertEqual(res.iam_statement["Action"], "elmos:printer:*")
        self.assertEqual(res.iam_statement["Resource"], "*")

    def test_transpile_rbac_matrix(self) -> None:
        matrix = {
            "Admin": ["create", "read", "update", "delete"],
            "Viewer": ["read"],
            "Editor": ["read", "update"],
        }
        res = self.transpiler.transpile_rbac_matrix(matrix)
        self.assertEqual(res.source_framework, "rbac-matrix")
        self.assertIn('"Admin": ["create", "delete", "read", "update"]', res.rego_policy)
        self.assertIn('"Viewer": ["read"]', res.rego_policy)
        self.assertIn("role_permissions[role]", res.rego_policy)
        self.assertIn("RBAC Matrix Soundness and Completeness", res.verified_invariants)

    def test_non_escalation_verification_safe(self) -> None:
        rule = "hasRole('ADMIN')"
        res = self.transpiler.transpile_spring_security(rule)
        verdict = self.transpiler.verify_non_escalation(rule, res.rego_policy)
        self.assertEqual(verdict["verdict"], "PROVEN_SAFE_NON_ESCALATION")
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["violations_found"], 0)
        self.assertTrue(verdict["checks"]["default_deny"])

    def test_non_escalation_verification_detects_tenant_leak(self) -> None:
        source_rule = "hasRole('USER') and principal.tenantId == #tenantId"
        # Simulate target Rego where tenant check was stripped (escalation!)
        escalated_rego = """
package elmos.authz
default allow = false
allow {
    some role in ["USER"]
    role in input.user.roles
}
"""
        verdict = self.transpiler.verify_non_escalation(source_rule, escalated_rego)
        self.assertEqual(verdict["verdict"], "UNPROVEN_POTENTIAL_ESCALATION")
        self.assertEqual(verdict["status"], "FAIL")
        self.assertFalse(verdict["checks"]["tenant_isolation_preserved"])

    def test_non_escalation_verification_detects_missing_default_deny(self) -> None:
        source_rule = "hasRole('ADMIN')"
        # Target without default deny = false
        insecure_rego = """
package elmos.authz
allow {
    some role in ["ADMIN"]
    role in input.user.roles
}
"""
        verdict = self.transpiler.verify_non_escalation(source_rule, insecure_rego)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertFalse(verdict["checks"]["default_deny"])

    def test_non_escalation_verification_detects_unconditional_allow(self) -> None:
        source_rule = "hasRole('ADMIN')"
        # Target allows unconditionally
        insecure_rego = """
package elmos.authz
default allow = false
allow { true }
"""
        verdict = self.transpiler.verify_non_escalation(source_rule, insecure_rego)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertFalse(verdict["checks"]["no_unconditional_escalation"])


if __name__ == "__main__":
    unittest.main()
