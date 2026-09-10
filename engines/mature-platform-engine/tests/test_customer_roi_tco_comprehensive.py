import unittest
import math
from elmos_mature_platform.types import (
    RoiAnalysis, TcoCostItem, ValueItem, CostDriver, ValueDriver, TcoComparison
)
from elmos_mature_platform.customer_roi_tco_engine import CustomerRoiTcoEngine

class TestCustomerRoiTcoEngine(unittest.TestCase):

    def setUp(self):
        self.engine = CustomerRoiTcoEngine()
        self.analysis_id = "test-analysis-1"
        self.analysis = RoiAnalysis(
            analysis_id=self.analysis_id,
            customer_name="Acme Corp",
            period_years=3
        )
        self.engine.create_analysis(self.analysis)

    def test_create_analysis(self):
        self.assertEqual(self.engine._analyses[self.analysis_id].customer_name, "Acme Corp")

    def test_create_analysis_missing_id(self):
        with self.assertRaises(ValueError):
            self.engine.create_analysis(RoiAnalysis(analysis_id="", customer_name="X"))

    def test_add_cost_item(self):
        item = TcoCostItem("c1", CostDriver.LICENSE, "Elmos License", 10000, True)
        self.engine.add_cost_item(self.analysis_id, item)
        self.assertEqual(len(self.engine._cost_items[self.analysis_id]), 1)

    def test_add_cost_item_invalid_analysis(self):
        item = TcoCostItem("c1", CostDriver.LICENSE, "Elmos License", 10000, True)
        with self.assertRaises(KeyError):
            self.engine.add_cost_item("invalid", item)

    def test_add_value_item(self):
        item = ValueItem("v1", ValueDriver.PRODUCTIVITY, "Dev Time Saved", 50000, 0.9, 3)
        self.engine.add_value_item(self.analysis_id, item)
        self.assertEqual(len(self.engine._value_items[self.analysis_id]), 1)

    def test_add_value_item_invalid_analysis(self):
        item = ValueItem("v1", ValueDriver.PRODUCTIVITY, "Dev Time Saved", 50000)
        with self.assertRaises(KeyError):
            self.engine.add_value_item("invalid", item)

    def test_compute_tco_only_recurring(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        tco = self.engine.compute_tco(self.analysis_id)
        self.assertEqual(tco, 300) # 100 * 3

    def test_compute_tco_only_onetime(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.MIGRATION, "M", 500, False))
        tco = self.engine.compute_tco(self.analysis_id)
        self.assertEqual(tco, 500)

    def test_compute_tco_mixed(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c2", CostDriver.MIGRATION, "M", 500, False))
        tco = self.engine.compute_tco(self.analysis_id)
        self.assertEqual(tco, 800) # (100*3) + 500

    def test_compute_tco_invalid_analysis(self):
        with self.assertRaises(KeyError):
            self.engine.compute_tco("invalid")

    def test_compute_roi(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 200))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.total_cost, 300)
        self.assertEqual(analysis.total_value, 600)
        self.assertEqual(analysis.net_value, 300)
        self.assertEqual(analysis.roi_percentage, 100.0)

    def test_compute_roi_zero_cost(self):
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 200))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.roi_percentage, 0.0)

    def test_compute_roi_negative_roi(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 300, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 100))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.total_cost, 900)
        self.assertEqual(analysis.total_value, 300)
        self.assertEqual(analysis.net_value, -600)
        self.assertAlmostEqual(analysis.roi_percentage, -66.666, places=2)

    def test_compute_risk_adjusted_roi(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 200, confidence=0.5))
        ra_roi = self.engine.compute_risk_adjusted_roi(self.analysis_id)
        # Value = 200 * 0.5 * 3 = 300. Cost = 300. Net = 0. ROI = 0%
        self.assertEqual(ra_roi, 0.0)

    def test_compute_risk_adjusted_roi_high_confidence(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 200, confidence=1.0))
        ra_roi = self.engine.compute_risk_adjusted_roi(self.analysis_id)
        self.assertEqual(ra_roi, 100.0)

    def test_compute_risk_adjusted_roi_zero_cost(self):
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 200, confidence=0.5))
        ra_roi = self.engine.compute_risk_adjusted_roi(self.analysis_id)
        self.assertEqual(ra_roi, 0.0)

    def test_compute_payback_period(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 120))
        # Total cost = 300. Annual value = 120 (10/month). Payback = 300 / 10 = 30 months
        payback = self.engine.compute_payback_period(self.analysis_id)
        self.assertEqual(payback, 30.0)

    def test_compute_payback_period_infinite(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        payback = self.engine.compute_payback_period(self.analysis_id)
        self.assertTrue(math.isinf(payback))

    def test_compute_npv(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.MIGRATION, "M", 1000, False))
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c2", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 600, realization_month=1))
        
        # Yr0 CF = -1000
        # Yr1 CF = -100 + 600 = 500 / 1.1 = 454.54
        # Yr2 CF = 500 / 1.21 = 413.22
        # Yr3 CF = 500 / 1.331 = 375.65
        # NPV = -1000 + 454.54 + 413.22 + 375.65 = 243.41
        
        npv = self.engine.compute_npv(self.analysis_id, discount_rate=0.1)
        self.assertAlmostEqual(npv, 243.42, places=1)

    def test_compute_npv_delayed_realization(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.MIGRATION, "M", 1000, False))
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c2", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 600, realization_month=24))
        
        # Yr0 = -1000
        # Yr1 = -100 (value not realized yet, realization=24 so year=1*12=12 < 24)
        # Yr2 = -100 + 600 = 500
        # Yr3 = 500
        npv = self.engine.compute_npv(self.analysis_id, discount_rate=0.1)
        # -1000 - 90.90 + 413.22 + 375.65 = -302.03
        self.assertAlmostEqual(npv, -302.02, places=1)

    def test_compare_tco(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        current_costs = [
            TcoCostItem("c2", CostDriver.LABOR, "Man", 300, True),
            TcoCostItem("c3", CostDriver.INFRASTRUCTURE, "Inf", 200, False)
        ]
        
        comparison = self.engine.compare_tco(self.analysis_id, current_costs)
        # Proposed = 300
        # Current = 300*3 + 200 = 1100
        # Savings = 800. Perc = 800/1100 = 72.7272%
        self.assertEqual(comparison.proposed_tco, 300)
        self.assertEqual(comparison.current_tco, 1100)
        self.assertEqual(comparison.savings, 800)
        self.assertAlmostEqual(comparison.savings_percentage, 72.7272, places=2)

    def test_compare_tco_no_current_costs(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        comparison = self.engine.compare_tco(self.analysis_id, [])
        self.assertEqual(comparison.savings, -300)
        self.assertEqual(comparison.savings_percentage, 0.0)

    def test_get_cost_breakdown(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c2", CostDriver.MIGRATION, "M", 500, False))
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c3", CostDriver.LICENSE, "L2", 50, True))
        
        breakdown = self.engine.get_cost_breakdown(self.analysis_id)
        self.assertEqual(breakdown[CostDriver.LICENSE.value], 450)
        self.assertEqual(breakdown[CostDriver.MIGRATION.value], 500)
        self.assertTrue(CostDriver.LABOR.value not in breakdown)

    def test_get_value_breakdown(self):
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 100))
        self.engine.add_value_item(self.analysis_id, ValueItem("v2", ValueDriver.QUALITY, "Q", 200))
        self.engine.add_value_item(self.analysis_id, ValueItem("v3", ValueDriver.PRODUCTIVITY, "P2", 50))
        
        breakdown = self.engine.get_value_breakdown(self.analysis_id)
        self.assertEqual(breakdown[ValueDriver.PRODUCTIVITY.value], 450) # (100+50)*3
        self.assertEqual(breakdown[ValueDriver.QUALITY.value], 600)
        self.assertTrue(ValueDriver.SPEED.value not in breakdown)

    def test_get_executive_summary(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 200))
        
        summary = self.engine.get_executive_summary(self.analysis_id)
        self.assertEqual(summary["customer_name"], "Acme Corp")
        self.assertEqual(summary["total_tco"], 300)
        self.assertEqual(summary["total_value"], 600)
        self.assertEqual(summary["net_value"], 300)
        self.assertEqual(summary["roi_percentage"], 100.0)
        self.assertEqual(summary["payback_months"], 18.0) # 300 / (200/12) = 18

    def test_get_executive_summary_invalid(self):
        with self.assertRaises(KeyError):
            self.engine.get_executive_summary("invalid")

    def test_add_multiple_analyses(self):
        analysis2 = RoiAnalysis("test-2", "Beta Corp")
        self.engine.create_analysis(analysis2)
        
        self.engine.add_cost_item("test-2", TcoCostItem("c1", CostDriver.LICENSE, "L", 50, True))
        tco1 = self.engine.compute_tco(self.analysis_id)
        tco2 = self.engine.compute_tco("test-2")
        
        self.assertEqual(tco1, 0)
        self.assertEqual(tco2, 150)

    def test_large_numbers(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 1000000000, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 2000000000))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.roi_percentage, 100.0)

    def test_float_precision(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 33.33, True))
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 100.0))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertAlmostEqual(analysis.total_cost, 99.99)
        self.assertAlmostEqual(analysis.total_value, 300.0)
        self.assertAlmostEqual(analysis.roi_percentage, 200.03, places=2)

    def test_empty_analysis(self):
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.total_cost, 0.0)
        self.assertEqual(analysis.total_value, 0.0)
        self.assertEqual(analysis.roi_percentage, 0.0)
        self.assertTrue(math.isinf(analysis.payback_months))
        self.assertEqual(analysis.npv, 0.0)

    def test_only_costs_no_value(self):
        self.engine.add_cost_item(self.analysis_id, TcoCostItem("c1", CostDriver.LICENSE, "L", 100, True))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.total_cost, 300)
        self.assertEqual(analysis.total_value, 0)
        self.assertEqual(analysis.net_value, -300)
        self.assertEqual(analysis.roi_percentage, -100.0)
        self.assertTrue(math.isinf(analysis.payback_months))

    def test_only_value_no_costs(self):
        self.engine.add_value_item(self.analysis_id, ValueItem("v1", ValueDriver.PRODUCTIVITY, "P", 100))
        analysis = self.engine.compute_roi(self.analysis_id)
        self.assertEqual(analysis.total_cost, 0)
        self.assertEqual(analysis.total_value, 300)
        self.assertEqual(analysis.roi_percentage, 0.0)
        self.assertEqual(analysis.payback_months, 0.0)

if __name__ == '__main__':
    unittest.main()
