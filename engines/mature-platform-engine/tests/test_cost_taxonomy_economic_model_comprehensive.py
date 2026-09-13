"""Comprehensive test suite for CostTaxonomyEconomicModelEngine (Batch 44 - Skill 1456)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.cost_taxonomy_economic_model_engine import CostTaxonomyEconomicModelEngine
from elmos_mature_platform.types import (
    CostAllocationEntry,
    CostCenterRecord,
    CostTaxonomyType,
    EconomicModelSummary,
)


class TestCostTaxonomyEconomicModelComprehensive(unittest.TestCase):
    """Rigorous unit testing for CostTaxonomyEconomicModelEngine."""

    def setUp(self) -> None:
        self.engine = CostTaxonomyEconomicModelEngine()

    def test_register_cost_center_success(self) -> None:
        cc = CostCenterRecord(
            center_id="cc-cloud-infra",
            name="Cloud Infrastructure & Runtime",
            department="Engineering Operations",
            owner="Alice Director",
            budget_allocated_usd=50000.0,
            budget_spent_usd=0.0,
            is_active=True,
        )
        cid = self.engine.register_cost_center(cc)
        self.assertEqual(cid, "cc-cloud-infra")
        fetched = self.engine.get_cost_center("cc-cloud-infra")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Cloud Infrastructure & Runtime")
        self.assertEqual(fetched.budget_allocated_usd, 50000.0)

    def test_register_cost_center_auto_generates_id_and_created_at(self) -> None:
        cc = CostCenterRecord(
            center_id="",
            name="AI R&D Lab",
            department="Research",
            owner="Dr. Bob",
        )
        cid = self.engine.register_cost_center(cc)
        self.assertTrue(cid.startswith("cc-"))
        self.assertTrue(len(cc.created_at) > 0)

    def test_register_cost_center_missing_name_or_department(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_cost_center(CostCenterRecord("1", "", "Dept", "Owner"))
        with self.assertRaises(ValueError):
            self.engine.register_cost_center(CostCenterRecord("2", "Name", "", "Owner"))

    def test_record_cost_allocation_success(self) -> None:
        cc = CostCenterRecord("cc-app", "Apps", "Dev", "Owner", 10000.0)
        self.engine.register_cost_center(cc)

        entry = CostAllocationEntry(
            entry_id="alloc-1",
            center_id="cc-app",
            taxonomy_type=CostTaxonomyType.COMPUTE,
            amount_usd=2500.0,
            description="AWS EC2 instances for Java migration cluster",
            is_capex=False,
        )
        eid = self.engine.record_cost_allocation(entry)
        self.assertEqual(eid, "alloc-1")
        self.assertEqual(cc.budget_spent_usd, 2500.0)

    def test_record_cost_allocation_auto_generates_id_and_timestamp(self) -> None:
        cc = CostCenterRecord("cc-app2", "Apps", "Dev", "Owner", 10000.0)
        self.engine.register_cost_center(cc)

        entry = CostAllocationEntry(
            entry_id="",
            center_id="cc-app2",
            taxonomy_type=CostTaxonomyType.MODEL_INFERENCE,
            amount_usd=1200.0,
        )
        eid = self.engine.record_cost_allocation(entry)
        self.assertTrue(eid.startswith("alloc-"))
        self.assertTrue(len(entry.timestamp) > 0)

    def test_record_cost_allocation_negative_amount_raises(self) -> None:
        cc = CostCenterRecord("cc-neg", "Apps", "Dev", "Owner", 1000.0)
        self.engine.register_cost_center(cc)
        with self.assertRaises(ValueError):
            self.engine.record_cost_allocation(
                CostAllocationEntry("1", "cc-neg", CostTaxonomyType.COMPUTE, -50.0)
            )

    def test_record_cost_allocation_nonexistent_center_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.record_cost_allocation(
                CostAllocationEntry("1", "missing-cc", CostTaxonomyType.STORAGE, 100.0)
            )

    def test_record_cost_allocation_inactive_center_raises(self) -> None:
        cc = CostCenterRecord("cc-inact", "Decommissioned", "Legacy", "Owner", 0.0, is_active=False)
        self.engine.register_cost_center(cc)
        with self.assertRaises(ValueError) as ctx:
            self.engine.record_cost_allocation(
                CostAllocationEntry("1", "cc-inact", CostTaxonomyType.OPERATIONS_OVERHEAD, 500.0)
            )
        self.assertIn("inactive", str(ctx.exception))

    def test_get_cost_by_taxonomy(self) -> None:
        cc = CostCenterRecord("cc-multi", "Multi", "Dev", "Owner", 50000.0)
        self.engine.register_cost_center(cc)

        self.engine.record_cost_allocation(
            CostAllocationEntry("1", "cc-multi", CostTaxonomyType.COMPUTE, 1000.0)
        )
        self.engine.record_cost_allocation(
            CostAllocationEntry("2", "cc-multi", CostTaxonomyType.COMPUTE, 500.0)
        )
        self.engine.record_cost_allocation(
            CostAllocationEntry("3", "cc-multi", CostTaxonomyType.STORAGE, 300.0)
        )
        self.engine.record_cost_allocation(
            CostAllocationEntry("4", "cc-multi", CostTaxonomyType.HUMAN_ENGINEERING, 5000.0)
        )

        tax = self.engine.get_cost_by_taxonomy()
        self.assertEqual(tax[CostTaxonomyType.COMPUTE.value], 1500.0)
        self.assertEqual(tax[CostTaxonomyType.STORAGE.value], 300.0)
        self.assertEqual(tax[CostTaxonomyType.HUMAN_ENGINEERING.value], 5000.0)
        self.assertEqual(tax[CostTaxonomyType.MODEL_INFERENCE.value], 0.0)

    def test_get_cost_by_center_and_over_budget_check(self) -> None:
        cc = CostCenterRecord("cc-over", "Special Ops", "Dev", "Owner", 2000.0)
        self.engine.register_cost_center(cc)

        self.engine.record_cost_allocation(
            CostAllocationEntry("1", "cc-over", CostTaxonomyType.COMPUTE, 1500.0)
        )
        c_info = self.engine.get_cost_by_center("cc-over")
        self.assertEqual(c_info["budget_spent_usd"], 1500.0)
        self.assertEqual(c_info["remaining_budget_usd"], 500.0)
        self.assertFalse(c_info["is_over_budget"])

        # Push over budget
        self.engine.record_cost_allocation(
            CostAllocationEntry("2", "cc-over", CostTaxonomyType.COMPUTE, 800.0)
        )
        c_info2 = self.engine.get_cost_by_center("cc-over")
        self.assertEqual(c_info2["budget_spent_usd"], 2300.0)
        self.assertEqual(c_info2["remaining_budget_usd"], -300.0)
        self.assertTrue(c_info2["is_over_budget"])

    def test_get_cost_by_center_nonexistent_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.get_cost_by_center("missing-cc")

    def test_compute_economic_model(self) -> None:
        cc1 = CostCenterRecord("c1", "Core", "Platform", "A", 1000.0)
        cc2 = CostCenterRecord("c2", "Lab", "R&D", "B", 500.0)
        self.engine.register_cost_center(cc1)
        self.engine.register_cost_center(cc2)

        # c1: $800 opex
        self.engine.record_cost_allocation(
            CostAllocationEntry("e1", "c1", CostTaxonomyType.COMPUTE, 800.0, is_capex=False)
        )
        # c2: $600 capex (pushes c2 over budget: 600 > 500)
        self.engine.record_cost_allocation(
            CostAllocationEntry("e2", "c2", CostTaxonomyType.LICENSE_TOOLCHAIN, 600.0, is_capex=True)
        )

        model = self.engine.compute_economic_model()
        self.assertEqual(model.total_spend_usd, 1400.0)
        self.assertEqual(model.capex_total_usd, 600.0)
        self.assertEqual(model.opex_total_usd, 800.0)
        self.assertEqual(model.active_centers_count, 2)
        self.assertIn("c2", model.over_budget_centers)
        self.assertNotIn("c1", model.over_budget_centers)

    def test_get_taxonomy_report(self) -> None:
        rep_empty = self.engine.get_taxonomy_report()
        self.assertEqual(rep_empty["total_expenses_recorded"], 0)
        self.assertEqual(rep_empty["total_cost_centers"], 0)
        self.assertEqual(rep_empty["economic_model"]["total_spend_usd"], 0.0)

        cc = CostCenterRecord("c-rep", "Rep", "Dept", "O", 1000.0)
        self.engine.register_cost_center(cc)
        self.engine.record_cost_allocation(
            CostAllocationEntry("1", "c-rep", CostTaxonomyType.NETWORK_EGRESS, 200.0)
        )

        rep = self.engine.get_taxonomy_report()
        self.assertEqual(rep["total_expenses_recorded"], 1)
        self.assertEqual(rep["total_cost_centers"], 1)
        self.assertEqual(rep["economic_model"]["total_spend_usd"], 200.0)


if __name__ == "__main__":
    unittest.main()
