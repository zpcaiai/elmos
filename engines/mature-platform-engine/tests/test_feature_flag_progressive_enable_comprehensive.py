import unittest
from elmos_mature_platform.types import (
    ProgressiveFlag,
    ProgressiveFlagStatus,
    FlagRolloutStrategy,
)
from elmos_mature_platform.feature_flag_progressive_enable_engine import FeatureFlagProgressiveEnableEngine

class TestFeatureFlagProgressiveEnableEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FeatureFlagProgressiveEnableEngine()

    def _create_flag(self, flag_id="flag-1"):
        flag = ProgressiveFlag(
            flag_id=flag_id,
            name=f"Test {flag_id}",
            error_rate_threshold=5.0
        )
        self.engine.create_flag(flag)
        return flag

    def test_create_flag(self):
        self._create_flag()
        flag = self.engine._flags["flag-1"]
        self.assertEqual(flag.status, ProgressiveFlagStatus.DISABLED)

    def test_create_duplicate_flag_raises(self):
        self._create_flag()
        with self.assertRaises(ValueError):
            self._create_flag()

    def test_enable_canary(self):
        self._create_flag()
        flag = self.engine.enable_canary("flag-1", ["user1", "user2"])
        self.assertEqual(flag.status, ProgressiveFlagStatus.CANARY)
        self.assertEqual(flag.strategy, FlagRolloutStrategy.USER_LIST)

    def test_enable_canary_invalid_flag(self):
        with self.assertRaises(KeyError):
            self.engine.enable_canary("invalid", ["user1"])

    def test_enable_canary_rolled_back_raises(self):
        self._create_flag()
        self.engine.rollback("flag-1")
        with self.assertRaises(ValueError):
            self.engine.enable_canary("flag-1", ["user1"])

    def test_start_rollout(self):
        self._create_flag()
        flag = self.engine.start_rollout("flag-1", 10.0)
        self.assertEqual(flag.status, ProgressiveFlagStatus.ROLLING)
        self.assertEqual(flag.percentage, 10.0)

    def test_start_rollout_invalid_percentage(self):
        self._create_flag()
        with self.assertRaises(ValueError):
            self.engine.start_rollout("flag-1", 105.0)
        with self.assertRaises(ValueError):
            self.engine.start_rollout("flag-1", -5.0)

    def test_start_rollout_paused_flag(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 10.0)
        self.engine.pause_rollout("flag-1")
        with self.assertRaises(ValueError):
            self.engine.start_rollout("flag-1", 20.0)

    def test_increase_rollout(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 10.0)
        step = self.engine.increase_rollout("flag-1", 20.0)
        flag = self.engine._flags["flag-1"]
        self.assertEqual(flag.percentage, 20.0)
        self.assertEqual(step.from_percentage, 10.0)
        self.assertEqual(step.to_percentage, 20.0)

    def test_increase_rollout_lower_percentage_raises(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 20.0)
        with self.assertRaises(ValueError):
            self.engine.increase_rollout("flag-1", 10.0)

    def test_increase_rollout_not_rolling(self):
        self._create_flag()
        with self.assertRaises(ValueError):
            self.engine.increase_rollout("flag-1", 10.0)

    def test_increase_to_100_fully_enables(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 50.0)
        self.engine.increase_rollout("flag-1", 100.0)
        flag = self.engine._flags["flag-1"]
        self.assertEqual(flag.status, ProgressiveFlagStatus.FULLY_ENABLED)

    def test_fully_enable(self):
        self._create_flag()
        flag = self.engine.fully_enable("flag-1")
        self.assertEqual(flag.status, ProgressiveFlagStatus.FULLY_ENABLED)
        self.assertEqual(flag.percentage, 100.0)

    def test_fully_enable_rolled_back_raises(self):
        self._create_flag()
        self.engine.rollback("flag-1")
        with self.assertRaises(ValueError):
            self.engine.fully_enable("flag-1")

    def test_pause_rollout(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 10.0)
        flag = self.engine.pause_rollout("flag-1")
        self.assertEqual(flag.status, ProgressiveFlagStatus.PAUSED)

    def test_pause_not_rolling(self):
        self._create_flag()
        with self.assertRaises(ValueError):
            self.engine.pause_rollout("flag-1")

    def test_rollback(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 50.0)
        flag = self.engine.rollback("flag-1")
        self.assertEqual(flag.status, ProgressiveFlagStatus.ROLLED_BACK)
        self.assertEqual(flag.percentage, 0.0)

    def test_auto_rollback_check_triggers(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 50.0)
        result = self.engine.auto_rollback_check("flag-1", 6.0)
        self.assertTrue(result)
        flag = self.engine._flags["flag-1"]
        self.assertEqual(flag.status, ProgressiveFlagStatus.ROLLED_BACK)

    def test_auto_rollback_check_no_trigger(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 50.0)
        result = self.engine.auto_rollback_check("flag-1", 3.0)
        self.assertFalse(result)
        flag = self.engine._flags["flag-1"]
        self.assertEqual(flag.status, ProgressiveFlagStatus.ROLLING)

    def test_is_enabled_for_user_disabled(self):
        self._create_flag()
        self.assertFalse(self.engine.is_enabled_for_user("flag-1", "user1"))

    def test_is_enabled_for_user_fully_enabled(self):
        self._create_flag()
        self.engine.fully_enable("flag-1")
        self.assertTrue(self.engine.is_enabled_for_user("flag-1", "user1"))

    def test_is_enabled_for_user_canary(self):
        self._create_flag()
        self.engine.enable_canary("flag-1", ["user1", "user2"])
        self.assertTrue(self.engine.is_enabled_for_user("flag-1", "user1"))
        self.assertFalse(self.engine.is_enabled_for_user("flag-1", "user3"))

    def test_is_enabled_for_user_rolling_deterministic(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 50.0)
        
        # Test deterministic evaluation - same user always gets same result
        res1 = self.engine.is_enabled_for_user("flag-1", "userA")
        res2 = self.engine.is_enabled_for_user("flag-1", "userA")
        self.assertEqual(res1, res2)

    def test_is_enabled_for_user_paused(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 50.0)
        self.engine.pause_rollout("flag-1")
        self.assertFalse(self.engine.is_enabled_for_user("flag-1", "userA"))

    def test_get_rollout_history(self):
        self._create_flag()
        self.engine.start_rollout("flag-1", 10.0)
        self.engine.increase_rollout("flag-1", 20.0)
        history = self.engine.get_rollout_history("flag-1")
        self.assertEqual(len(history), 2)

    def test_get_active_rollouts(self):
        self._create_flag("f1")
        self._create_flag("f2")
        self._create_flag("f3")
        
        self.engine.start_rollout("f1", 10.0)
        self.engine.enable_canary("f2", ["user1"])
        
        active = self.engine.get_active_rollouts()
        self.assertEqual(len(active), 2)

    def test_get_flag_report(self):
        self._create_flag("f1")
        self._create_flag("f2")
        self._create_flag("f3")
        
        self.engine.start_rollout("f1", 20.0)
        self.engine.start_rollout("f2", 40.0)
        self.engine.rollback("f3")
        
        report = self.engine.get_flag_report()
        self.assertEqual(report["total_flags"], 3)
        self.assertEqual(report["avg_rollout_percentage"], 30.0)
        self.assertAlmostEqual(report["rollback_rate_percentage"], 33.33, places=1)

    def test_auto_rollback_check_invalid_flag(self):
        with self.assertRaises(KeyError):
            self.engine.auto_rollback_check("invalid", 10.0)

    def test_is_enabled_for_user_invalid_flag(self):
        self.assertFalse(self.engine.is_enabled_for_user("invalid", "user1"))

    def test_get_rollout_history_invalid_flag(self):
        with self.assertRaises(KeyError):
            self.engine.get_rollout_history("invalid")

if __name__ == '__main__':
    unittest.main()
