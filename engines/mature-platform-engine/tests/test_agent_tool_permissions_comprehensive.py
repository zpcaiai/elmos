import unittest
from elmos_mature_platform.types import (
    ToolDefinition,
    ToolPermissionGrant,
    ToolPermissionLevel,
    PermissionScope
)
from elmos_mature_platform.agent_tool_permissions_engine import AgentToolPermissionsEngine

class TestAgentToolPermissionsComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AgentToolPermissionsEngine()
        self.engine.register_tool(ToolDefinition(
            tool_id="tool_1", name="Tool 1", risk_level="low", requires_approval=False
        ))
        self.engine.register_tool(ToolDefinition(
            tool_id="tool_2", name="Tool 2", risk_level="high", requires_approval=True
        ))
        self.engine.register_tool(ToolDefinition(
            tool_id="tool_3", name="Tool 3", risk_level="critical", requires_approval=True
        ))

    def test_register_tool(self):
        tool = ToolDefinition(tool_id="t4", name="t4")
        res = self.engine.register_tool(tool)
        self.assertEqual(res, "t4")

    def test_grant_permission(self):
        grant = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE)
        self.assertEqual(self.engine.grant_permission(grant), "g1")

    def test_grant_permission_missing_tool(self):
        grant = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="bad", level=ToolPermissionLevel.EXECUTE)
        with self.assertRaises(ValueError):
            self.engine.grant_permission(grant)

    def test_revoke_permission(self):
        grant = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE)
        self.engine.grant_permission(grant)
        revoked = self.engine.revoke_permission("g1", "test")
        self.assertTrue(revoked.revoked)

    def test_revoke_permission_missing(self):
        with self.assertRaises(ValueError):
            self.engine.revoke_permission("g1", "test")

    def test_check_permission_global(self):
        grant = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(grant)
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.GLOBAL)
        self.assertEqual(level, ToolPermissionLevel.EXECUTE)

    def test_check_permission_missing_tool(self):
        with self.assertRaises(ValueError):
            self.engine.check_permission("a1", "bad", PermissionScope.GLOBAL)

    def test_check_permission_deny_wins(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        g2 = ToolPermissionGrant(grant_id="g2", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.DENY, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(g1)
        self.engine.grant_permission(g2)
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.GLOBAL)
        self.assertEqual(level, ToolPermissionLevel.DENY)

    def test_check_permission_narrow_wins(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.READ_ONLY, scope=PermissionScope.ENVIRONMENT, scope_value="prod")
        g2 = ToolPermissionGrant(grant_id="g2", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(g1)
        self.engine.grant_permission(g2)
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.ENVIRONMENT, "prod")
        self.assertEqual(level, ToolPermissionLevel.READ_ONLY)

    def test_check_permission_global_fallback(self):
        g2 = ToolPermissionGrant(grant_id="g2", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(g2)
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.ENVIRONMENT, "prod")
        self.assertEqual(level, ToolPermissionLevel.EXECUTE)

    def test_check_permission_no_grants(self):
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.GLOBAL)
        self.assertEqual(level, ToolPermissionLevel.DENY)

    def test_can_execute_execute(self):
        g = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE)
        self.engine.grant_permission(g)
        self.assertTrue(self.engine.can_execute("a1", "tool_1"))

    def test_can_execute_admin(self):
        g = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.ADMIN)
        self.engine.grant_permission(g)
        self.assertTrue(self.engine.can_execute("a1", "tool_1"))

    def test_can_execute_read_only(self):
        g = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.READ_ONLY)
        self.engine.grant_permission(g)
        self.assertFalse(self.engine.can_execute("a1", "tool_1"))

    def test_can_execute_deny(self):
        g = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.DENY)
        self.engine.grant_permission(g)
        self.assertFalse(self.engine.can_execute("a1", "tool_1"))

    def test_requires_approval_false(self):
        self.assertFalse(self.engine.requires_approval("a1", "tool_1"))

    def test_requires_approval_true_no_admin(self):
        self.assertTrue(self.engine.requires_approval("a1", "tool_2"))

    def test_requires_approval_true_with_admin(self):
        g = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_2", level=ToolPermissionLevel.ADMIN)
        self.engine.grant_permission(g)
        self.assertFalse(self.engine.requires_approval("a1", "tool_2"))

    def test_requires_approval_missing_tool(self):
        with self.assertRaises(ValueError):
            self.engine.requires_approval("a1", "bad")

    def test_get_agent_permissions(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1")
        self.engine.grant_permission(g1)
        res = self.engine.get_agent_permissions("a1")
        self.assertEqual(len(res), 1)

    def test_get_agent_permissions_revoked(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1")
        self.engine.grant_permission(g1)
        self.engine.revoke_permission("g1", "test")
        res = self.engine.get_agent_permissions("a1")
        self.assertEqual(len(res), 0)

    def test_get_tool_grants(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1")
        self.engine.grant_permission(g1)
        res = self.engine.get_tool_grants("tool_1")
        self.assertEqual(len(res), 1)

    def test_get_high_risk_grants(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_2")
        self.engine.grant_permission(g1)
        res = self.engine.get_high_risk_grants()
        self.assertEqual(len(res), 1)

    def test_get_high_risk_grants_revoked(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_2")
        self.engine.grant_permission(g1)
        self.engine.revoke_permission("g1", "test")
        res = self.engine.get_high_risk_grants()
        self.assertEqual(len(res), 0)

    def test_audit_permissions_expired(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", expires_at="2025-01-01")
        self.engine.grant_permission(g1)
        audit = self.engine.audit_permissions()
        self.assertIn("g1", audit["expired_grants"])

    def test_audit_permissions_high_risk_no_cond(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_3")
        self.engine.grant_permission(g1)
        audit = self.engine.audit_permissions()
        self.assertIn("g1", audit["high_risk_grants_without_conditions"])

    def test_audit_permissions_high_risk_with_cond(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_3", conditions=["cond1"])
        self.engine.grant_permission(g1)
        audit = self.engine.audit_permissions()
        self.assertNotIn("g1", audit["high_risk_grants_without_conditions"])

    def test_get_permissions_report(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1")
        self.engine.grant_permission(g1)
        report = self.engine.get_permissions_report()
        self.assertIn("tool_1", report["by_tool"])
        self.assertIn("a1", report["by_agent"])
        self.assertIn("low", report["by_risk_level"])

    def test_get_permissions_report_revoked_excluded(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1")
        self.engine.grant_permission(g1)
        self.engine.revoke_permission("g1", "test")
        report = self.engine.get_permissions_report()
        self.assertNotIn("tool_1", report["by_tool"])

    def test_check_permission_same_scope_level_priority(self):
        # Admin vs Execute
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.ADMIN, scope=PermissionScope.GLOBAL)
        g2 = ToolPermissionGrant(grant_id="g2", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(g1)
        self.engine.grant_permission(g2)
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.GLOBAL)
        self.assertEqual(level, ToolPermissionLevel.ADMIN)

    def test_check_permission_unrelated_revoked(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a1", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(g1)
        self.engine.revoke_permission("g1", "test")
        level = self.engine.check_permission("a1", "tool_1", PermissionScope.GLOBAL)
        self.assertEqual(level, ToolPermissionLevel.DENY)

    def test_can_execute_unrelated_agent(self):
        g1 = ToolPermissionGrant(grant_id="g1", agent_id="a2", tool_id="tool_1", level=ToolPermissionLevel.EXECUTE, scope=PermissionScope.GLOBAL)
        self.engine.grant_permission(g1)
        self.assertFalse(self.engine.can_execute("a1", "tool_1"))

if __name__ == '__main__':
    unittest.main()
