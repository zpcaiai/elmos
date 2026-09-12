import unittest
from datetime import datetime, timedelta
from typing import Dict
from elmos_mature_platform.deprecation_removal_engine import DeprecationRemovalEngine
from elmos_mature_platform.types import DeprecatedItem, DeprecationPolicy, DeprecationPhase

class TestDeprecationRemovalEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DeprecationRemovalEngine()
        self.policy = DeprecationPolicy(
            policy_id="std_policy",
            min_notice_days=90,
            max_sunset_days=365,
            require_replacement=True,
            require_migration_guide=True,
            block_removal_with_active_consumers=True
        )
        self.engine.create_policy(self.policy)
        
        # Override _get_current_date for deterministic testing
        self.current_date = "2026-09-11"
        self.engine._get_current_date = lambda: self.current_date
        
    def test_create_policy(self):
        p = DeprecationPolicy(policy_id="p1")
        self.engine.create_policy(p)
        self.assertIn("p1", self.engine.policies)
        
    def test_announce_deprecation(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        item_id = self.engine.announce_deprecation(item)
        self.assertEqual(item_id, "api1")
        self.assertEqual(item.phase, DeprecationPhase.ANNOUNCED)
        self.assertEqual(item.announced_at, self.current_date)
        
    def test_announce_deprecation_already_exists(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        with self.assertRaises(ValueError):
            self.engine.announce_deprecation(item)
            
    def test_deprecate_item(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.deprecate_item("api1")
        self.assertEqual(item.phase, DeprecationPhase.DEPRECATED)
        self.assertEqual(item.deprecated_at, self.current_date)
        
    def test_deprecate_item_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.deprecate_item("nonexistent")
            
    def test_deprecate_item_wrong_phase(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        item.phase = DeprecationPhase.DEPRECATED
        self.engine.items["api1"] = item
        with self.assertRaises(ValueError):
            self.engine.deprecate_item("api1")
            
    def test_schedule_sunset(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.deprecate_item("api1")
        self.engine.schedule_sunset("api1", "2026-12-31")
        self.assertEqual(item.phase, DeprecationPhase.SUNSET)
        self.assertEqual(item.sunset_at, "2026-12-31")
        
    def test_schedule_sunset_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.schedule_sunset("nonexistent", "2026-12-31")
            
    def test_schedule_sunset_wrong_phase(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        with self.assertRaises(ValueError):
            self.engine.schedule_sunset("api1", "2026-12-31")
            
    def test_remove_item(self):
        item = DeprecatedItem(
            item_id="api1", name="API 1", item_type="api",
            replacement="api2", migration_guide_url="http://docs",
            announced_at="2026-01-01" # > 90 days
        )
        self.engine.announce_deprecation(item)
        self.engine.deprecate_item("api1")
        self.engine.schedule_sunset("api1", "2026-12-31")
        self.engine.remove_item("api1", "std_policy")
        self.assertEqual(item.phase, DeprecationPhase.REMOVED)
        self.assertEqual(item.removed_at, self.current_date)
        
    def test_remove_item_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.remove_item("nonexistent", "std_policy")
            
    def test_remove_item_wrong_phase(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        with self.assertRaises(ValueError):
            self.engine.remove_item("api1", "std_policy")
            
    def test_remove_item_validation_fails(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api", announced_at="2026-01-01")
        self.engine.announce_deprecation(item)
        self.engine.deprecate_item("api1")
        self.engine.schedule_sunset("api1", "2026-12-31")
        with self.assertRaisesRegex(ValueError, "Replacement is required"):
            self.engine.remove_item("api1", "std_policy")
            
    def test_record_usage(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.record_usage("api1", "consumerA")
        self.assertEqual(item.usage_count, 1)
        self.assertEqual(item.affected_consumers, ["consumerA"])
        
    def test_record_usage_duplicate_consumer(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.record_usage("api1", "consumerA")
        self.engine.record_usage("api1", "consumerA")
        self.assertEqual(item.usage_count, 2)
        self.assertEqual(item.affected_consumers, ["consumerA"])
        
    def test_record_usage_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_usage("nonexistent", "c1")
            
    def test_get_active_consumers(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.record_usage("api1", "consumerA")
        self.assertEqual(self.engine.get_active_consumers("api1"), ["consumerA"])
        
    def test_get_active_consumers_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_active_consumers("nonexistent")
            
    def test_get_items_by_phase(self):
        item1 = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item1)
        item2 = DeprecatedItem(item_id="api2", name="API 2", item_type="api")
        self.engine.announce_deprecation(item2)
        self.engine.deprecate_item("api2")
        
        announced = self.engine.get_items_by_phase(DeprecationPhase.ANNOUNCED)
        self.assertEqual(len(announced), 1)
        self.assertEqual(announced[0].item_id, "api1")
        
        deprecated = self.engine.get_items_by_phase(DeprecationPhase.DEPRECATED)
        self.assertEqual(len(deprecated), 1)
        self.assertEqual(deprecated[0].item_id, "api2")
        
    def test_get_overdue_items(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.deprecate_item("api1")
        self.engine.schedule_sunset("api1", "2026-08-01") # Past date
        overdue = self.engine.get_overdue_items(self.current_date)
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].item_id, "api1")
        
    def test_get_overdue_items_none(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        self.engine.deprecate_item("api1")
        self.engine.schedule_sunset("api1", "2026-12-01") # Future date
        overdue = self.engine.get_overdue_items(self.current_date)
        self.assertEqual(len(overdue), 0)
        
    def test_validate_removal_ready(self):
        item = DeprecatedItem(
            item_id="api1", name="API 1", item_type="api",
            replacement="api2", migration_guide_url="url",
            announced_at="2026-01-01"
        )
        self.engine.announce_deprecation(item)
        res = self.engine.validate_removal("api1", "std_policy")
        self.assertTrue(res["ready"])
        
    def test_validate_removal_missing_replacement(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        res = self.engine.validate_removal("api1", "std_policy")
        self.assertFalse(res["ready"])
        self.assertIn("Replacement is required but not provided.", res["reasons"])
        
    def test_validate_removal_missing_guide(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api", replacement="api2")
        self.engine.announce_deprecation(item)
        res = self.engine.validate_removal("api1", "std_policy")
        self.assertFalse(res["ready"])
        self.assertIn("Migration guide is required but not provided.", res["reasons"])
        
    def test_validate_removal_has_consumers(self):
        item = DeprecatedItem(
            item_id="api1", name="API 1", item_type="api",
            replacement="api2", migration_guide_url="url",
            announced_at="2026-01-01"
        )
        self.engine.announce_deprecation(item)
        self.engine.record_usage("api1", "c1")
        res = self.engine.validate_removal("api1", "std_policy")
        self.assertFalse(res["ready"])
        self.assertIn("Has 1 active consumers.", res["reasons"])
        
    def test_validate_removal_min_notice(self):
        item = DeprecatedItem(
            item_id="api1", name="API 1", item_type="api",
            replacement="api2", migration_guide_url="url",
            announced_at="2026-09-01" # Only 10 days ago
        )
        self.engine.announce_deprecation(item)
        res = self.engine.validate_removal("api1", "std_policy")
        self.assertFalse(res["ready"])
        self.assertTrue(any("Minimum notice period" in r for r in res["reasons"]))

    def test_validate_removal_item_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.validate_removal("nonexistent", "std_policy")
            
    def test_validate_removal_policy_not_found(self):
        item = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item)
        with self.assertRaises(ValueError):
            self.engine.validate_removal("api1", "nonexistent")

    def test_get_deprecation_report(self):
        item1 = DeprecatedItem(item_id="api1", name="API 1", item_type="api")
        self.engine.announce_deprecation(item1)
        self.engine.record_usage("api1", "c1")
        
        item2 = DeprecatedItem(item_id="api2", name="API 2", item_type="api")
        self.engine.announce_deprecation(item2)
        self.engine.deprecate_item("api2")
        self.engine.schedule_sunset("api2", "2026-08-01")
        
        report = self.engine.get_deprecation_report()
        self.assertEqual(report["total_items"], 2)
        self.assertEqual(report["by_phase"][DeprecationPhase.ANNOUNCED.value], 1)
        self.assertEqual(report["by_phase"][DeprecationPhase.SUNSET.value], 1)
        self.assertEqual(report["overdue_count"], 1)
        self.assertEqual(report["most_impactful"][0]["item_id"], "api1")

    def test_full_lifecycle(self):
        item = DeprecatedItem(
            item_id="api1", name="API 1", item_type="api",
            replacement="api2", migration_guide_url="url",
            announced_at="2026-01-01"
        )
        self.engine.announce_deprecation(item)
        self.assertEqual(item.phase, DeprecationPhase.ANNOUNCED)
        
        self.engine.deprecate_item("api1")
        self.assertEqual(item.phase, DeprecationPhase.DEPRECATED)
        
        self.engine.schedule_sunset("api1", "2026-12-31")
        self.assertEqual(item.phase, DeprecationPhase.SUNSET)
        
        self.engine.remove_item("api1", "std_policy")
        self.assertEqual(item.phase, DeprecationPhase.REMOVED)

if __name__ == "__main__":
    unittest.main()
