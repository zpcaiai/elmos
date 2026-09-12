import unittest
from datetime import datetime, timezone, timedelta
from elmos_mature_platform.types import (
    FeatureFlag,
    FlagState,
    FlagLifecycleStage,
)
from elmos_mature_platform.feature_flag_governance_engine import FeatureFlagGovernanceEngine

class TestFeatureFlagGovernanceEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FeatureFlagGovernanceEngine()
        self.now_iso = datetime.now(timezone.utc).isoformat()

    def test_create_flag(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", owner="alice", created_at=self.now_iso)
        self.engine.create_flag(flag)
        self.assertIn("f1", self.engine._flags)

    def test_create_duplicate_flag_raises(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        with self.assertRaises(ValueError):
            self.engine.create_flag(flag)

    def test_create_flag_with_missing_dependency_raises(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", dependencies=["dep1"])
        with self.assertRaises(ValueError):
            self.engine.create_flag(flag)

    def test_evaluate_disabled_flag(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertFalse(eval_result.enabled)
        self.assertEqual(eval_result.reason, "disabled")

    def test_evaluate_enabled_flag(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.enable_globally("f1", "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertTrue(eval_result.enabled)
        self.assertEqual(eval_result.reason, "global")

    def test_evaluate_kill_switched_flag(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.kill_switch("f1", "bug", "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertFalse(eval_result.enabled)
        self.assertEqual(eval_result.reason, "kill_switched")

    def test_evaluate_retired_flag(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.retire_flag("f1", "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertFalse(eval_result.enabled)
        self.assertEqual(eval_result.reason, "retired")

    def test_evaluate_targeted_tenant(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.add_targeted_tenant("f1", "tenant_a", "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertTrue(eval_result.enabled)
        self.assertEqual(eval_result.reason, "targeted")
        
        eval_result_b = self.engine.evaluate("f1", "tenant_b")
        self.assertFalse(eval_result_b.enabled)

    def test_add_targeted_tenant_updates_state(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.add_targeted_tenant("f1", "tenant_a", "alice")
        f = self.engine._get_flag("f1")
        self.assertEqual(f.state, FlagState.TENANT_TARGETED)
        self.assertEqual(f.lifecycle, FlagLifecycleStage.TESTING)

    def test_remove_targeted_tenant(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.add_targeted_tenant("f1", "tenant_a", "alice")
        self.engine.remove_targeted_tenant("f1", "tenant_a", "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertFalse(eval_result.enabled)

    def test_percentage_rollout_zero(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.set_percentage_rollout("f1", 0.0, "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertFalse(eval_result.enabled)
        self.assertEqual(eval_result.reason, "percentage_miss")

    def test_percentage_rollout_hundred(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.set_percentage_rollout("f1", 100.0, "alice")
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertTrue(eval_result.enabled)
        self.assertEqual(eval_result.reason, "percentage")

    def test_percentage_rollout_deterministic(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.set_percentage_rollout("f1", 50.0, "alice")
        
        # Test deterministic hash over multiple evaluations
        eval_1 = self.engine.evaluate("f1", "tenant_a")
        eval_2 = self.engine.evaluate("f1", "tenant_a")
        self.assertEqual(eval_1.enabled, eval_2.enabled)

    def test_percentage_rollout_with_targeting(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.set_percentage_rollout("f1", 0.0, "alice")
        self.engine.add_targeted_tenant("f1", "tenant_target", "alice")
        
        eval_target = self.engine.evaluate("f1", "tenant_target")
        self.assertTrue(eval_target.enabled)
        self.assertEqual(eval_target.reason, "targeted")
        
        eval_other = self.engine.evaluate("f1", "tenant_other")
        self.assertFalse(eval_other.enabled)

    def test_dependency_order_enabled(self):
        dep = FeatureFlag(flag_id="dep1", name="Dep 1", description="desc")
        self.engine.create_flag(dep)
        self.engine.enable_globally("dep1", "alice")
        
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", dependencies=["dep1"])
        self.engine.create_flag(flag)
        
        deps_check = self.engine.check_dependency_order("f1")
        self.assertTrue(deps_check["dep1"])
        self.engine.enable_globally("f1", "alice")
        self.assertEqual(self.engine._get_flag("f1").state, FlagState.ENABLED)

    def test_dependency_order_disabled(self):
        dep = FeatureFlag(flag_id="dep1", name="Dep 1", description="desc")
        self.engine.create_flag(dep)
        
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", dependencies=["dep1"])
        self.engine.create_flag(flag)
        
        deps_check = self.engine.check_dependency_order("f1")
        self.assertFalse(deps_check["dep1"])

    def test_cannot_enable_if_dependency_disabled(self):
        dep = FeatureFlag(flag_id="dep1", name="Dep 1", description="desc")
        self.engine.create_flag(dep)
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", dependencies=["dep1"])
        self.engine.create_flag(flag)
        
        with self.assertRaises(ValueError):
            self.engine.enable_globally("f1", "alice")

    def test_cannot_set_rollout_if_dependency_disabled(self):
        dep = FeatureFlag(flag_id="dep1", name="Dep 1", description="desc")
        self.engine.create_flag(dep)
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", dependencies=["dep1"])
        self.engine.create_flag(flag)
        
        with self.assertRaises(ValueError):
            self.engine.set_percentage_rollout("f1", 50.0, "alice")

    def test_cannot_target_tenant_if_dependency_disabled(self):
        dep = FeatureFlag(flag_id="dep1", name="Dep 1", description="desc")
        self.engine.create_flag(dep)
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", dependencies=["dep1"])
        self.engine.create_flag(flag)
        
        with self.assertRaises(ValueError):
            self.engine.add_targeted_tenant("f1", "tenant_a", "alice")

    def test_kill_switch_overrides_everything(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.enable_globally("f1", "alice")
        self.engine.kill_switch("f1", "critical bug", "alice")
        
        eval_result = self.engine.evaluate("f1", "tenant_a")
        self.assertFalse(eval_result.enabled)

    def test_cannot_modify_kill_switched_flag_rollout(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.kill_switch("f1", "critical bug", "alice")
        with self.assertRaises(ValueError):
            self.engine.set_percentage_rollout("f1", 50.0, "alice")

    def test_cannot_modify_kill_switched_flag_target(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.kill_switch("f1", "critical bug", "alice")
        with self.assertRaises(ValueError):
            self.engine.add_targeted_tenant("f1", "tenant_a", "alice")

    def test_cannot_modify_retired_flag_rollout(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.retire_flag("f1", "alice")
        with self.assertRaises(ValueError):
            self.engine.set_percentage_rollout("f1", 50.0, "alice")

    def test_cannot_modify_retired_flag_target(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.retire_flag("f1", "alice")
        with self.assertRaises(ValueError):
            self.engine.add_targeted_tenant("f1", "tenant_a", "alice")

    def test_detect_stale_flags(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", created_at=old_time)
        self.engine.create_flag(flag)
        
        stale = self.engine.detect_stale_flags(self.now_iso)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].flag_id, "f1")

    def test_do_not_detect_fully_enabled_as_stale(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc", created_at=old_time)
        self.engine.create_flag(flag)
        self.engine.enable_globally("f1", "alice")
        
        stale = self.engine.detect_stale_flags(self.now_iso)
        self.assertEqual(len(stale), 0)

    def test_get_audit_trail(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        self.engine.add_targeted_tenant("f1", "tenant_a", "alice")
        self.engine.enable_globally("f1", "alice")
        
        audit = self.engine.get_audit_trail("f1")
        self.assertEqual(len(audit), 3)
        self.assertEqual(audit[0].action, "created")
        self.assertEqual(audit[1].action, "added_targeted_tenant")
        self.assertEqual(audit[2].action, "enabled")

    def test_get_flag_report(self):
        f1 = FeatureFlag(flag_id="f1", name="F1", description="desc")
        f2 = FeatureFlag(flag_id="f2", name="F2", description="desc")
        self.engine.create_flag(f1)
        self.engine.create_flag(f2)
        
        self.engine.enable_globally("f1", "alice")
        self.engine.kill_switch("f2", "bug", "bob")
        
        report = self.engine.get_flag_report()
        self.assertEqual(report["total_flags"], 2)
        self.assertEqual(report["by_state"][FlagState.ENABLED.value], 1)
        self.assertEqual(report["by_state"][FlagState.KILL_SWITCHED.value], 1)
        self.assertEqual(report["kill_switched_count"], 1)

    def test_invalid_percentage_rollout(self):
        flag = FeatureFlag(flag_id="f1", name="Flag 1", description="desc")
        self.engine.create_flag(flag)
        with self.assertRaises(ValueError):
            self.engine.set_percentage_rollout("f1", 150.0, "alice")
        with self.assertRaises(ValueError):
            self.engine.set_percentage_rollout("f1", -10.0, "alice")

    def test_missing_flag_operations(self):
        with self.assertRaises(ValueError):
            self.engine.enable_globally("missing", "alice")
        with self.assertRaises(ValueError):
            self.engine.kill_switch("missing", "reason", "alice")
        with self.assertRaises(ValueError):
            self.engine.retire_flag("missing", "alice")
        with self.assertRaises(ValueError):
            self.engine.get_audit_trail("missing")
        with self.assertRaises(ValueError):
            self.engine._get_flag("missing")

if __name__ == "__main__":
    unittest.main()
