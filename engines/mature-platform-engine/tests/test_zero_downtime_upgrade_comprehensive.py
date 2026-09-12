import unittest
from datetime import datetime
from elmos_mature_platform.types import ZDUpgradeStrategy, ZDUpgradePhase, UpgradeTarget, UpgradeHealthCheck
from elmos_mature_platform.zero_downtime_upgrade_engine import ZeroDowntimeUpgradeEngine

class TestZeroDowntimeUpgradeEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ZeroDowntimeUpgradeEngine()

    def test_01_create_upgrade_success(self):
        target = UpgradeTarget(
            target_id="tgt-1", service_name="web", current_version="v1", target_version="v2",
            strategy=ZDUpgradeStrategy.ROLLING, instances_total=4
        )
        tid = self.engine.create_upgrade(target)
        self.assertEqual(tid, "tgt-1")
        self.assertEqual(self.engine.upgrades["tgt-1"].phase, ZDUpgradePhase.PLANNING)

    def test_02_create_upgrade_duplicate(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        with self.assertRaises(ValueError):
            self.engine.create_upgrade(target)

    def test_03_pre_check_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=4)
        self.engine.create_upgrade(target)
        res = self.engine.pre_check("tgt-1")
        self.assertTrue(res["valid"])
        self.assertEqual(self.engine.upgrades["tgt-1"].phase, ZDUpgradePhase.PRE_CHECK)

    def test_04_pre_check_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.pre_check("invalid")

    def test_05_pre_check_same_version(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v1", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        res = self.engine.pre_check("tgt-1")
        self.assertFalse(res["valid"])
        self.assertEqual(self.engine.upgrades["tgt-1"].phase, ZDUpgradePhase.FAILED)

    def test_06_pre_check_zero_instances(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=0)
        self.engine.create_upgrade(target)
        res = self.engine.pre_check("tgt-1")
        self.assertFalse(res["valid"])

    def test_07_start_upgrade_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=4)
        self.engine.create_upgrade(target)
        upg = self.engine.start_upgrade("tgt-1")
        self.assertEqual(upg.phase, ZDUpgradePhase.DEPLOYING)
        self.assertTrue(upg.started_at)

    def test_08_start_upgrade_fails_pre_check(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v1", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        with self.assertRaises(ValueError):
            self.engine.start_upgrade("tgt-1")

    def test_09_upgrade_instance_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=2)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        upg = self.engine.upgrade_instance("tgt-1", "inst-1")
        self.assertEqual(upg.instances_upgraded, 1)

    def test_10_upgrade_instance_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.upgrade_instance("invalid", "inst-1")

    def test_11_upgrade_instance_wrong_phase(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=2)
        self.engine.create_upgrade(target)
        with self.assertRaises(ValueError):
            self.engine.upgrade_instance("tgt-1", "inst-1")

    def test_12_upgrade_instance_all_upgraded(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=1)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.upgrade_instance("tgt-1", "inst-1")
        with self.assertRaises(ValueError):
            self.engine.upgrade_instance("tgt-1", "inst-2")

    def test_13_record_health_check_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        hc = UpgradeHealthCheck("tgt-1", "inst-1", True)
        self.engine.record_health_check(hc)
        self.assertEqual(len(self.engine.health_checks["tgt-1"]), 1)
        self.assertTrue(self.engine.health_checks["tgt-1"][0].checked_at)

    def test_14_record_health_check_not_found(self):
        hc = UpgradeHealthCheck("tgt-x", "inst-1", True)
        with self.assertRaises(KeyError):
            self.engine.record_health_check(hc)

    def test_15_verify_upgrade_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        res = self.engine.verify_upgrade("tgt-1")
        self.assertTrue(res["verified"])
        self.assertEqual(self.engine.upgrades["tgt-1"].phase, ZDUpgradePhase.VERIFYING)

    def test_16_verify_upgrade_with_failed_checks(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.record_health_check(UpgradeHealthCheck("tgt-1", "inst-1", False))
        res = self.engine.verify_upgrade("tgt-1")
        self.assertFalse(res["verified"])

    def test_17_verify_upgrade_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.verify_upgrade("invalid")

    def test_18_verify_upgrade_wrong_phase(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        with self.assertRaises(ValueError):
            self.engine.verify_upgrade("tgt-1")

    def test_19_complete_upgrade_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=1)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.upgrade_instance("tgt-1", "inst-1")
        self.engine.record_health_check(UpgradeHealthCheck("tgt-1", "inst-1", True))
        upg = self.engine.complete_upgrade("tgt-1")
        self.assertEqual(upg.phase, ZDUpgradePhase.COMPLETED)
        self.assertTrue(upg.completed_at)

    def test_20_complete_upgrade_not_all_upgraded(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=2)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.upgrade_instance("tgt-1", "inst-1")
        with self.assertRaises(ValueError):
            self.engine.complete_upgrade("tgt-1")

    def test_21_complete_upgrade_verify_failed(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=1)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.upgrade_instance("tgt-1", "inst-1")
        self.engine.record_health_check(UpgradeHealthCheck("tgt-1", "inst-1", False))
        with self.assertRaises(ValueError):
            self.engine.complete_upgrade("tgt-1")

    def test_22_rollback_upgrade_success(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        upg = self.engine.rollback_upgrade("tgt-1")
        self.assertEqual(upg.phase, ZDUpgradePhase.ROLLED_BACK)
        self.assertTrue(upg.completed_at)

    def test_23_rollback_upgrade_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.rollback_upgrade("invalid")

    def test_24_rollback_upgrade_wrong_phase(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        with self.assertRaises(ValueError):
            self.engine.rollback_upgrade("tgt-1")

    def test_25_get_upgrade_progress(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=4)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.upgrade_instance("tgt-1", "inst-1")
        self.engine.record_health_check(UpgradeHealthCheck("tgt-1", "inst-1", True))
        
        prog = self.engine.get_upgrade_progress("tgt-1")
        self.assertEqual(prog["instances_total"], 4)
        self.assertEqual(prog["instances_upgraded"], 1)
        self.assertEqual(prog["percent_complete"], 25.0)
        self.assertEqual(prog["healthy_checks"], 1)

    def test_26_get_upgrade_progress_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.get_upgrade_progress("invalid")
            
    def test_27_get_upgrade_report_empty(self):
        rep = self.engine.get_upgrade_report()
        self.assertEqual(rep["total_upgrades"], 0)

    def test_28_get_upgrade_report_stats(self):
        # 1 completed
        t1 = UpgradeTarget("t1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=1)
        self.engine.create_upgrade(t1)
        self.engine.start_upgrade("t1")
        self.engine.upgrade_instance("t1", "i1")
        self.engine.complete_upgrade("t1")
        
        # 1 rolled back
        t2 = UpgradeTarget("t2", "web", "v1", "v2", ZDUpgradeStrategy.BLUE_GREEN)
        self.engine.create_upgrade(t2)
        self.engine.start_upgrade("t2")
        self.engine.rollback_upgrade("t2")
        
        rep = self.engine.get_upgrade_report()
        self.assertEqual(rep["total_upgrades"], 2)
        self.assertEqual(rep["success_rate_pct"], 50.0)
        self.assertEqual(rep["rollback_rate_pct"], 50.0)
        self.assertEqual(rep["by_strategy"][ZDUpgradeStrategy.ROLLING], 1)
        self.assertEqual(rep["by_strategy"][ZDUpgradeStrategy.BLUE_GREEN], 1)

    def test_29_get_upgrade_progress_zero_instances(self):
        t1 = UpgradeTarget("t1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING, instances_total=0)
        self.engine.create_upgrade(t1)
        prog = self.engine.get_upgrade_progress("t1")
        self.assertEqual(prog["percent_complete"], 0)

    def test_30_verify_upgrade_multiple_health_checks(self):
        target = UpgradeTarget("tgt-1", "web", "v1", "v2", ZDUpgradeStrategy.ROLLING)
        self.engine.create_upgrade(target)
        self.engine.start_upgrade("tgt-1")
        self.engine.record_health_check(UpgradeHealthCheck("tgt-1", "inst-1", True))
        self.engine.record_health_check(UpgradeHealthCheck("tgt-1", "inst-1", True))
        res = self.engine.verify_upgrade("tgt-1")
        self.assertTrue(res["verified"])

if __name__ == '__main__':
    unittest.main()
