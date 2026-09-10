import unittest
from datetime import datetime, timezone, timedelta
from typing import List

from elmos_mature_platform.types import (
    CurationItem,
    CurationPolicy,
    CurationAction,
    ContentCategory
)
from elmos_mature_platform.human_curation_governance_engine import HumanCurationGovernanceEngine

class TestHumanCurationGovernanceEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HumanCurationGovernanceEngine()
        
    def _create_item(self, item_id: str, category: ContentCategory, quality: float, created_at: str = "") -> CurationItem:
        return CurationItem(
            item_id=item_id,
            category=category,
            title=f"Test {item_id}",
            quality_score=quality,
            created_at=created_at
        )
        
    def _create_policy(self, category: ContentCategory, auto_approve_threshold: float, require_human: bool) -> CurationPolicy:
        return CurationPolicy(
            policy_id=f"pol_{category.value}",
            name=f"{category.value} Policy",
            category=category,
            auto_approve_threshold=auto_approve_threshold,
            require_human_review=require_human
        )

    def test_01_submit_valid_item(self):
        item = self._create_item("item1", ContentCategory.KNOWLEDGE, 0.8)
        res = self.engine.submit_item(item)
        self.assertEqual(res, "item1")
        self.assertEqual(len(self.engine._items), 1)

    def test_02_submit_invalid_quality_high(self):
        item = self._create_item("item2", ContentCategory.KNOWLEDGE, 1.5)
        with self.assertRaises(ValueError):
            self.engine.submit_item(item)

    def test_03_submit_invalid_quality_low(self):
        item = self._create_item("item3", ContentCategory.KNOWLEDGE, -0.5)
        with self.assertRaises(ValueError):
            self.engine.submit_item(item)

    def test_04_submit_generates_created_at(self):
        item = self._create_item("item4", ContentCategory.KNOWLEDGE, 0.5)
        self.engine.submit_item(item)
        self.assertTrue(bool(self.engine._items["item4"].created_at))

    def test_05_set_policy(self):
        pol = self._create_policy(ContentCategory.RECIPE, 0.9, True)
        res = self.engine.set_policy(pol)
        self.assertEqual(res, "pol_recipe")
        self.assertIn(ContentCategory.RECIPE, self.engine._policies)

    def test_06_auto_curate_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.auto_curate("nonexistent")

    def test_07_auto_curate_already_approved(self):
        item = self._create_item("item_app", ContentCategory.KNOWLEDGE, 0.9)
        item.action = CurationAction.APPROVE
        self.engine.submit_item(item)
        with self.assertRaises(ValueError):
            self.engine.auto_curate("item_app")

    def test_08_auto_curate_no_policy(self):
        item = self._create_item("item_nopol", ContentCategory.RULE, 0.9)
        self.engine.submit_item(item)
        with self.assertRaises(ValueError):
            self.engine.auto_curate("item_nopol")

    def test_09_auto_curate_requires_human(self):
        item = self._create_item("item_hum", ContentCategory.RULE, 0.95)
        self.engine.submit_item(item)
        pol = self._create_policy(ContentCategory.RULE, 0.9, True)
        self.engine.set_policy(pol)
        with self.assertRaises(ValueError):
            self.engine.auto_curate("item_hum")

    def test_10_auto_curate_low_quality(self):
        item = self._create_item("item_lowq", ContentCategory.PATTERN, 0.8)
        self.engine.submit_item(item)
        pol = self._create_policy(ContentCategory.PATTERN, 0.9, False)
        self.engine.set_policy(pol)
        with self.assertRaises(ValueError):
            self.engine.auto_curate("item_lowq")

    def test_11_auto_curate_success(self):
        item = self._create_item("item_auto", ContentCategory.PATTERN, 0.95)
        self.engine.submit_item(item)
        pol = self._create_policy(ContentCategory.PATTERN, 0.9, False)
        self.engine.set_policy(pol)
        res = self.engine.auto_curate("item_auto")
        self.assertEqual(res.action, CurationAction.APPROVE)
        self.assertEqual(res.curator, "system_auto")

    def test_12_curate_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.curate("nonexistent", "alice", CurationAction.APPROVE, "Looks good")

    def test_13_curate_already_approved(self):
        item = self._create_item("item_app2", ContentCategory.KNOWLEDGE, 0.8)
        item.action = CurationAction.APPROVE
        self.engine.submit_item(item)
        with self.assertRaises(ValueError):
            self.engine.curate("item_app2", "alice", CurationAction.REJECT, "Changed my mind")

    def test_14_curate_success(self):
        item = self._create_item("item_cur", ContentCategory.KNOWLEDGE, 0.7)
        self.engine.submit_item(item)
        res = self.engine.curate("item_cur", "bob", CurationAction.APPROVE, "LGTM")
        self.assertEqual(res.action, CurationAction.APPROVE)
        self.assertEqual(res.curator, "bob")
        self.assertEqual(res.review_notes, "LGTM")
        self.assertTrue(bool(res.curated_at))

    def test_15_curate_reject(self):
        item = self._create_item("item_rej", ContentCategory.KNOWLEDGE, 0.3)
        self.engine.submit_item(item)
        res = self.engine.curate("item_rej", "charlie", CurationAction.REJECT, "Too poor quality")
        self.assertEqual(res.action, CurationAction.REJECT)

    def test_16_flag_conflict_missing_source(self):
        item2 = self._create_item("c_target", ContentCategory.KNOWLEDGE, 0.5)
        self.engine.submit_item(item2)
        with self.assertRaises(KeyError):
            self.engine.flag_conflict("c_src", "c_target")

    def test_17_flag_conflict_missing_target(self):
        item1 = self._create_item("c_src", ContentCategory.KNOWLEDGE, 0.5)
        self.engine.submit_item(item1)
        with self.assertRaises(KeyError):
            self.engine.flag_conflict("c_src", "c_target")

    def test_18_flag_conflict_success(self):
        item1 = self._create_item("c_src1", ContentCategory.KNOWLEDGE, 0.5)
        item2 = self._create_item("c_target1", ContentCategory.KNOWLEDGE, 0.6)
        self.engine.submit_item(item1)
        self.engine.submit_item(item2)
        res = self.engine.flag_conflict("c_src1", "c_target1")
        self.assertEqual(res.action, CurationAction.FLAG)
        self.assertIn("c_target1", res.conflicts_with)

    def test_19_resolve_conflict_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.resolve_conflict("nonexistent", "Fixed")

    def test_20_resolve_conflict_success(self):
        item1 = self._create_item("c_src2", ContentCategory.KNOWLEDGE, 0.5)
        item2 = self._create_item("c_target2", ContentCategory.KNOWLEDGE, 0.6)
        self.engine.submit_item(item1)
        self.engine.submit_item(item2)
        self.engine.flag_conflict("c_src2", "c_target2")
        res = self.engine.resolve_conflict("c_src2", "Combined items")
        self.assertEqual(res.action, CurationAction.DEFER)
        self.assertEqual(len(res.conflicts_with), 0)

    def test_21_auto_curate_conflict(self):
        item1 = self._create_item("ac_conf", ContentCategory.PATTERN, 0.95)
        item2 = self._create_item("ac_conf2", ContentCategory.PATTERN, 0.95)
        self.engine.submit_item(item1)
        self.engine.submit_item(item2)
        self.engine.flag_conflict("ac_conf", "ac_conf2")
        pol = self._create_policy(ContentCategory.PATTERN, 0.9, False)
        self.engine.set_policy(pol)
        with self.assertRaises(ValueError):
            self.engine.auto_curate("ac_conf")

    def test_22_human_curate_approve_conflict(self):
        item1 = self._create_item("hc_conf", ContentCategory.PATTERN, 0.8)
        item2 = self._create_item("hc_conf2", ContentCategory.PATTERN, 0.8)
        self.engine.submit_item(item1)
        self.engine.submit_item(item2)
        self.engine.flag_conflict("hc_conf", "hc_conf2")
        with self.assertRaises(ValueError):
            self.engine.curate("hc_conf", "alice", CurationAction.APPROVE, "I want to approve")

    def test_23_human_curate_reject_conflict_allowed(self):
        item1 = self._create_item("hc_conf_r", ContentCategory.PATTERN, 0.8)
        item2 = self._create_item("hc_conf2_r", ContentCategory.PATTERN, 0.8)
        self.engine.submit_item(item1)
        self.engine.submit_item(item2)
        self.engine.flag_conflict("hc_conf_r", "hc_conf2_r")
        res = self.engine.curate("hc_conf_r", "alice", CurationAction.REJECT, "Rejecting conflict")
        self.assertEqual(res.action, CurationAction.REJECT)

    def test_24_get_pending_items_all(self):
        self.engine.submit_item(self._create_item("p1", ContentCategory.KNOWLEDGE, 0.5))
        self.engine.submit_item(self._create_item("p2", ContentCategory.RECIPE, 0.5))
        i3 = self._create_item("p3", ContentCategory.RULE, 0.5)
        i3.action = CurationAction.APPROVE
        self.engine.submit_item(i3)
        pending = self.engine.get_pending_items()
        self.assertEqual(len(pending), 2)

    def test_25_get_pending_items_by_category(self):
        self.engine.submit_item(self._create_item("p4", ContentCategory.KNOWLEDGE, 0.5))
        self.engine.submit_item(self._create_item("p5", ContentCategory.RECIPE, 0.5))
        pending = self.engine.get_pending_items(ContentCategory.RECIPE.value)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].item_id, "p5")

    def test_26_get_quality_distribution(self):
        self.engine.submit_item(self._create_item("q1", ContentCategory.KNOWLEDGE, 0.1))
        self.engine.submit_item(self._create_item("q2", ContentCategory.KNOWLEDGE, 0.3))
        self.engine.submit_item(self._create_item("q3", ContentCategory.KNOWLEDGE, 0.9))
        self.engine.submit_item(self._create_item("q4", ContentCategory.RECIPE, 0.5))
        dist = self.engine.get_quality_distribution()
        self.assertEqual(dist[ContentCategory.KNOWLEDGE.value]["0.0-0.2"], 1)
        self.assertEqual(dist[ContentCategory.KNOWLEDGE.value]["0.2-0.4"], 1)
        self.assertEqual(dist[ContentCategory.KNOWLEDGE.value]["0.8-1.0"], 1)
        self.assertEqual(dist[ContentCategory.RECIPE.value]["0.4-0.6"], 1)

    def test_27_get_curator_stats(self):
        self.engine.submit_item(self._create_item("cs1", ContentCategory.KNOWLEDGE, 0.5))
        self.engine.submit_item(self._create_item("cs2", ContentCategory.KNOWLEDGE, 0.5))
        self.engine.submit_item(self._create_item("cs3", ContentCategory.KNOWLEDGE, 0.5))
        self.engine.curate("cs1", "alice", CurationAction.APPROVE, "")
        self.engine.curate("cs2", "alice", CurationAction.REJECT, "")
        self.engine.curate("cs3", "bob", CurationAction.APPROVE, "")
        stats = self.engine.get_curator_stats()
        self.assertEqual(stats["alice"]["reviewed"], 2)
        self.assertEqual(stats["alice"]["approved"], 1)
        self.assertEqual(stats["alice"]["ratio"], 0.5)
        self.assertEqual(stats["bob"]["reviewed"], 1)
        self.assertEqual(stats["bob"]["ratio"], 1.0)

    def test_28_get_stale_items(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        self.engine.submit_item(self._create_item("st1", ContentCategory.KNOWLEDGE, 0.5, created_at=old_date))
        self.engine.submit_item(self._create_item("st2", ContentCategory.KNOWLEDGE, 0.5))  # new
        i3 = self._create_item("st3", ContentCategory.KNOWLEDGE, 0.5, created_at=old_date)
        i3.action = CurationAction.APPROVE
        self.engine.submit_item(i3)
        stale = self.engine.get_stale_items(5)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].item_id, "st1")

    def test_29_get_governance_report(self):
        self.engine.submit_item(self._create_item("gr1", ContentCategory.KNOWLEDGE, 0.5))
        self.engine.submit_item(self._create_item("gr2", ContentCategory.RECIPE, 0.5))
        self.engine.curate("gr1", "alice", CurationAction.APPROVE, "")
        self.engine.flag_conflict("gr2", "gr1")
        
        rep = self.engine.get_governance_report()
        self.assertEqual(rep["total_items"], 2)
        self.assertEqual(rep["by_category"][ContentCategory.KNOWLEDGE.value], 1)
        self.assertEqual(rep["by_category"][ContentCategory.RECIPE.value], 1)
        self.assertEqual(rep["by_action"][CurationAction.APPROVE.value], 1)
        self.assertEqual(rep["by_action"][CurationAction.FLAG.value], 1)
        self.assertEqual(rep["auto_vs_human"]["human"], 1)
        self.assertEqual(rep["conflicts"], 1)

if __name__ == '__main__':
    unittest.main()
