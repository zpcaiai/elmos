import unittest
from elmos_mature_platform.types import CostCategory, CostLineItem
from elmos_mature_platform.cost_economics_engine import CostEconomicsEngine

class TestCostEconomicsEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CostEconomicsEngine()

    def test_record_and_retrieve_by_tenant(self):
        item = CostLineItem(
            item_id="1", category=CostCategory.COMPUTE, description="AWS EC2",
            quantity=1, unit_price=10.0, total_cost=10.0, tenant_id="tenant_a"
        )
        self.engine.record_cost(item)
        costs = self.engine.get_costs_by_tenant("tenant_a")
        self.assertEqual(len(costs), 1)
        self.assertEqual(costs[0].tenant_id, "tenant_a")

    def test_record_and_retrieve_by_category(self):
        item1 = CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1")
        item2 = CostLineItem("2", CostCategory.STORAGE, "S3", 1, 5.0, 5.0, tenant_id="t1")
        self.engine.record_cost(item1)
        self.engine.record_cost(item2)
        
        costs = self.engine.get_costs_by_category(CostCategory.COMPUTE)
        self.assertEqual(len(costs), 1)
        self.assertEqual(costs[0].category, CostCategory.COMPUTE)

    def test_compute_total_cost_all(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1"))
        self.engine.record_cost(CostLineItem("2", CostCategory.COMPUTE, "EC2", 1, 20.0, 20.0, tenant_id="t2"))
        self.assertEqual(self.engine.compute_total_cost(), 30.0)

    def test_compute_total_cost_filtered_by_tenant(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1"))
        self.engine.record_cost(CostLineItem("2", CostCategory.COMPUTE, "EC2", 1, 20.0, 20.0, tenant_id="t2"))
        self.assertEqual(self.engine.compute_total_cost(tenant_id="t1"), 10.0)

    def test_unit_economics_positive_margin(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 50.0, 50.0, tenant_id="t1"))
        ue = self.engine.compute_unit_economics("per_tenant", 100.0, 1)
        self.assertEqual(ue.cost_per_unit, 50.0)
        self.assertEqual(ue.revenue_per_unit, 100.0)
        self.assertEqual(ue.margin_per_unit, 50.0)
        self.assertEqual(ue.margin_pct, 50.0)
        self.assertEqual(ue.breakeven_units, 0)

    def test_unit_economics_negative_margin(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 150.0, 150.0, tenant_id="t1"))
        ue = self.engine.compute_unit_economics("per_tenant", 100.0, 1)
        self.assertEqual(ue.margin_per_unit, -50.0)
        self.assertEqual(ue.margin_pct, -50.0)

    def test_cost_forecast_baseline_steady(self):
        forecast = self.engine.create_cost_forecast("baseline", 100.0, 0.0, 3)
        self.assertEqual(forecast.projected_monthly_costs, [100.0, 100.0, 100.0])

    def test_cost_forecast_growth_10pct(self):
        forecast = self.engine.create_cost_forecast("growth_10pct", 100.0, 0.1, 3)
        self.assertAlmostEqual(forecast.projected_monthly_costs[0], 100.0)
        self.assertAlmostEqual(forecast.projected_monthly_costs[1], 110.0)
        self.assertAlmostEqual(forecast.projected_monthly_costs[2], 121.0)

    def test_cost_forecast_growth_50pct(self):
        forecast = self.engine.create_cost_forecast("growth_50pct", 100.0, 0.5, 2)
        self.assertEqual(forecast.projected_monthly_costs, [100.0, 150.0])

    def test_roi_computation_positive_payback(self):
        roi = self.engine.compute_roi(1000.0, 100.0, 0.1)
        self.assertEqual(roi.payback_period_months, 10.0)
        self.assertEqual(roi.annual_savings, 1200.0)

    def test_roi_computation_risk_adjusted(self):
        roi = self.engine.compute_roi(1000.0, 100.0, 0.1) # 3600 savings over 3 years
        # risk adjusted savings = 3600 * 0.9 = 3240
        # roi = (3240 - 1000) / 1000 = 2.24 * 100 = 224.0%
        self.assertAlmostEqual(roi.risk_adjusted_roi_pct, 224.0)
        self.assertAlmostEqual(roi.three_year_roi_pct, 260.0)

    def test_budget_setting_and_80pct_warning(self):
        self.engine.set_budget("t1", 100.0)
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 80.0, 80.0, tenant_id="t1"))
        alert = self.engine.check_budget("t1")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.threshold_breached, "80pct_warning")

    def test_budget_setting_and_90pct_critical(self):
        self.engine.set_budget("t1", 100.0)
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 95.0, 95.0, tenant_id="t1"))
        alert = self.engine.check_budget("t1")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.threshold_breached, "90pct_critical")

    def test_budget_100pct_exceeded(self):
        self.engine.set_budget("t1", 100.0)
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 110.0, 110.0, tenant_id="t1"))
        alert = self.engine.check_budget("t1")
        self.assertIsNotNone(alert)
        self.assertEqual(alert.threshold_breached, "100pct_exceeded")
        self.assertEqual(alert.projected_overage, 10.0)

    def test_budget_no_alert(self):
        self.engine.set_budget("t1", 100.0)
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 50.0, 50.0, tenant_id="t1"))
        alert = self.engine.check_budget("t1")
        self.assertIsNone(alert)

    def test_showback_report_by_category(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 50.0, 50.0, tenant_id="t1"))
        self.engine.record_cost(CostLineItem("2", CostCategory.STORAGE, "S3", 1, 20.0, 20.0, tenant_id="t1"))
        report = self.engine.generate_showback_report("t1")
        self.assertEqual(report["total_cost"], 70.0)
        self.assertEqual(report["breakdown"]["compute"], 50.0)
        self.assertEqual(report["breakdown"]["storage"], 20.0)

    def test_chargeback_invoice_generation(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 50.0, 50.0, tenant_id="t1"))
        invoice = self.engine.generate_chargeback_invoice("t1", "2024-01")
        self.assertEqual(invoice["tenant_id"], "t1")
        self.assertEqual(invoice["total_amount"], 50.0)
        self.assertEqual(len(invoice["line_items"]), 1)

    def test_billing_reconciliation_exact_match(self):
        metered = [CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 50.0, 50.0)]
        result = self.engine.reconcile_billing(metered, 50.0)
        self.assertEqual(result["discrepancy"], 0.0)
        self.assertFalse(result["flagged"])

    def test_billing_reconciliation_discrepancy_detected(self):
        metered = [CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 50.0, 50.0)]
        result = self.engine.reconcile_billing(metered, 55.0)
        self.assertEqual(result["discrepancy"], 5.0)
        self.assertEqual(result["discrepancy_pct"], 10.0)
        self.assertTrue(result["flagged"])

    def test_billing_reconciliation_minor_discrepancy_ignored(self):
        metered = [CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 100.0, 100.0)]
        result = self.engine.reconcile_billing(metered, 100.5)
        self.assertEqual(result["discrepancy"], 0.5)
        self.assertEqual(result["discrepancy_pct"], 0.5)
        self.assertFalse(result["flagged"])

    def test_cost_anomaly_spike_detected(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1", timestamp="2024-01-01T00:00:00"))
        self.engine.record_cost(CostLineItem("2", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1", timestamp="2024-01-02T00:00:00"))
        self.engine.record_cost(CostLineItem("3", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1", timestamp="2024-01-03T00:00:00"))
        self.engine.record_cost(CostLineItem("4", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1", timestamp="2024-01-04T00:00:00"))
        self.engine.record_cost(CostLineItem("5", CostCategory.COMPUTE, "EC2", 1, 100.0, 100.0, tenant_id="t1", timestamp="2024-01-05T00:00:00"))
        
        anomalies = self.engine.get_cost_anomalies("t1", std_dev_threshold=1.5)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["date"], "2024-01-05")

    def test_cost_anomaly_normal_variation_ignored(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1", timestamp="2024-01-01T00:00:00"))
        self.engine.record_cost(CostLineItem("2", CostCategory.COMPUTE, "EC2", 1, 11.0, 11.0, tenant_id="t1", timestamp="2024-01-02T00:00:00"))
        self.engine.record_cost(CostLineItem("3", CostCategory.COMPUTE, "EC2", 1, 9.0, 9.0, tenant_id="t1", timestamp="2024-01-03T00:00:00"))
        
        anomalies = self.engine.get_cost_anomalies("t1", std_dev_threshold=2.0)
        self.assertEqual(len(anomalies), 0)

    def test_model_inference_economics(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.MODEL_INFERENCE, "OpenAI GPT-4", 1, 10.0, 10.0))
        self.engine.record_cost(CostLineItem("2", CostCategory.MODEL_INFERENCE, "Anthropic Claude", 1, 15.0, 15.0))
        self.engine.record_cost(CostLineItem("3", CostCategory.COMPUTE, "EC2", 1, 5.0, 5.0))
        
        breakdown = self.engine.get_model_inference_economics()
        self.assertEqual(breakdown["total_inference_cost"], 25.0)
        self.assertEqual(breakdown["provider_breakdown"]["OpenAI"], 10.0)
        self.assertEqual(breakdown["provider_breakdown"]["Anthropic"], 15.0)

    def test_multiple_tenants_isolation(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "EC2", 1, 10.0, 10.0, tenant_id="t1"))
        self.engine.record_cost(CostLineItem("2", CostCategory.COMPUTE, "EC2", 1, 20.0, 20.0, tenant_id="t2"))
        
        t1_costs = self.engine.get_costs_by_tenant("t1")
        self.assertEqual(len(t1_costs), 1)
        self.assertEqual(t1_costs[0].total_cost, 10.0)

    def test_zero_cost_handling(self):
        self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "Free Tier", 1, 0.0, 0.0, tenant_id="t1"))
        self.assertEqual(self.engine.compute_total_cost("t1"), 0.0)

    def test_invalid_negative_cost_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.record_cost(CostLineItem("1", CostCategory.COMPUTE, "Credit", 1, -10.0, -10.0, tenant_id="t1"))

if __name__ == '__main__':
    unittest.main()
