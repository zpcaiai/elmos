import unittest
from elmos_mature_platform.economics_profitability_certification_engine import EconomicsProfitabilityCertificationEngine
from elmos_mature_platform.types import RevenueRecord, EconCertLevel

class TestEconomicsProfitabilityCertificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EconomicsProfitabilityCertificationEngine()

    def test_add_revenue_record(self):
        record = RevenueRecord(record_id="1", product_id="prod_1", period="2024-Q1", revenue=100.0, cogs=40.0)
        self.engine.add_revenue_record(record)
        records = self.engine.get_records("prod_1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].gross_profit, 60.0)

    def test_get_records_empty(self):
        self.assertEqual(self.engine.get_records("nonexistent"), [])

    def test_compute_gross_margin_empty(self):
        self.assertEqual(self.engine.compute_gross_margin("nonexistent"), 0.0)

    def test_compute_gross_margin_single(self):
        record = RevenueRecord(record_id="1", product_id="prod_1", period="2024-Q1", revenue=100.0, cogs=40.0)
        self.engine.add_revenue_record(record)
        self.assertEqual(self.engine.compute_gross_margin("prod_1"), 60.0)

    def test_compute_gross_margin_zero_revenue(self):
        record = RevenueRecord(record_id="1", product_id="prod_1", period="2024-Q1", revenue=0.0, cogs=40.0)
        self.engine.add_revenue_record(record)
        self.assertEqual(self.engine.compute_gross_margin("prod_1"), 0.0)

    def test_compute_gross_margin_multiple(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0))
        self.engine.add_revenue_record(RevenueRecord(record_id="2", product_id="prod_1", period="Q2", revenue=200.0, cogs=100.0))
        # Q1: 60%, Q2: 50%, avg: 55%
        self.assertEqual(self.engine.compute_gross_margin("prod_1"), 55.0)

    def test_compute_ltv_cac_ratio_empty(self):
        self.assertEqual(self.engine.compute_ltv_cac_ratio("nonexistent"), 0.0)

    def test_compute_ltv_cac_ratio_zero_cac(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", ltv=1000.0, cac=0.0))
        self.assertEqual(self.engine.compute_ltv_cac_ratio("prod_1"), 0.0)

    def test_compute_ltv_cac_ratio_single(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", ltv=1000.0, cac=250.0))
        self.assertEqual(self.engine.compute_ltv_cac_ratio("prod_1"), 4.0)

    def test_compute_ltv_cac_ratio_multiple(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", ltv=1000.0, cac=250.0))
        self.engine.add_revenue_record(RevenueRecord(record_id="2", product_id="prod_1", period="Q2", ltv=1000.0, cac=500.0))
        # Q1: 4.0, Q2: 2.0, avg: 3.0
        self.assertEqual(self.engine.compute_ltv_cac_ratio("prod_1"), 3.0)

    def test_compute_churn_rate_empty(self):
        self.assertEqual(self.engine.compute_churn_rate("nonexistent"), 0.0)

    def test_compute_churn_rate_zero_customers(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", churn_count=5, customers=0))
        self.assertEqual(self.engine.compute_churn_rate("prod_1"), 0.0)

    def test_compute_churn_rate_single(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", churn_count=5, customers=100))
        self.assertEqual(self.engine.compute_churn_rate("prod_1"), 0.05)

    def test_compute_churn_rate_multiple(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", churn_count=10, customers=100))
        self.engine.add_revenue_record(RevenueRecord(record_id="2", product_id="prod_1", period="Q2", churn_count=20, customers=100))
        # Q1: 0.1, Q2: 0.2, avg: 0.15
        self.assertAlmostEqual(self.engine.compute_churn_rate("prod_1"), 0.15)

    def test_compute_unit_economics_empty(self):
        result = self.engine.compute_unit_economics("nonexistent")
        self.assertFalse(result["positive"])

    def test_compute_unit_economics_zero_customers(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, customers=0))
        result = self.engine.compute_unit_economics("prod_1")
        self.assertFalse(result["positive"])

    def test_compute_unit_economics_positive(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=1000.0, cogs=400.0, customers=10))
        result = self.engine.compute_unit_economics("prod_1")
        self.assertEqual(result["revenue_per_customer"], 100.0)
        self.assertEqual(result["cogs_per_customer"], 40.0)
        self.assertEqual(result["margin_per_customer"], 60.0)
        self.assertTrue(result["positive"])

    def test_compute_unit_economics_negative(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=400.0, cogs=1000.0, customers=10))
        result = self.engine.compute_unit_economics("prod_1")
        self.assertFalse(result["positive"])

    def test_certify_highly_profitable(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=400.0, cac=100.0))
        cert = self.engine.certify_economics("prod_1")
        self.assertEqual(cert.level, EconCertLevel.HIGHLY_PROFITABLE)
        self.assertTrue(cert.certified)

    def test_certify_profitable(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=250.0, cac=100.0))
        cert = self.engine.certify_economics("prod_1")
        self.assertEqual(cert.level, EconCertLevel.PROFITABLE)
        self.assertTrue(cert.certified)

    def test_certify_viable(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=150.0, cac=100.0))
        cert = self.engine.certify_economics("prod_1")
        self.assertEqual(cert.level, EconCertLevel.VIABLE)
        self.assertTrue(cert.certified)

    def test_certify_marginal(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=80.0, cac=100.0))
        cert = self.engine.certify_economics("prod_1")
        self.assertEqual(cert.level, EconCertLevel.MARGINAL)
        self.assertFalse(cert.certified)

    def test_certify_not_viable(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=40.0, cac=100.0))
        cert = self.engine.certify_economics("prod_1")
        self.assertEqual(cert.level, EconCertLevel.NOT_VIABLE)
        self.assertFalse(cert.certified)

    def test_certify_negative_margin_fails(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=140.0, ltv=400.0, cac=100.0))
        cert = self.engine.certify_economics("prod_1")
        self.assertFalse(cert.certified)

    def test_get_certification(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=400.0, cac=100.0))
        self.engine.certify_economics("prod_1")
        cert = self.engine.get_certification("prod_1")
        self.assertIsNotNone(cert)

    def test_get_certification_empty(self):
        self.assertIsNone(self.engine.get_certification("nonexistent"))

    def test_project_profitability_empty(self):
        res = self.engine.project_profitability("nonexistent", 12)
        self.assertEqual(res["projected_revenue"], 0.0)

    def test_project_profitability_zero_months(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0))
        res = self.engine.project_profitability("prod_1", 0)
        self.assertEqual(res["projected_revenue"], 0.0)

    def test_project_profitability_valid(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0))
        res = self.engine.project_profitability("prod_1", 12)
        self.assertEqual(res["projected_revenue"], 1200.0)
        self.assertEqual(res["projected_cogs"], 480.0)
        self.assertEqual(res["projected_profit"], 720.0)

    def test_compare_products(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=400.0, cac=100.0, churn_count=1, customers=10))
        self.engine.add_revenue_record(RevenueRecord(record_id="2", product_id="prod_2", period="Q1", revenue=200.0, cogs=180.0, ltv=150.0, cac=100.0, churn_count=5, customers=10))
        comp = self.engine.compare_products(["prod_1", "prod_2"])
        self.assertIn("prod_1", comp)
        self.assertIn("prod_2", comp)
        self.assertEqual(comp["prod_1"]["gross_margin"], 60.0)
        self.assertEqual(comp["prod_2"]["gross_margin"], 10.0)

    def test_get_economics_report(self):
        self.engine.add_revenue_record(RevenueRecord(record_id="1", product_id="prod_1", period="Q1", revenue=100.0, cogs=40.0, ltv=400.0, cac=100.0))
        self.engine.certify_economics("prod_1")
        rep = self.engine.get_economics_report()
        self.assertEqual(rep["total_products"], 1)
        self.assertIn("prod_1", rep["products"])
        self.assertEqual(rep["products"]["prod_1"]["gross_margin"], 60.0)

if __name__ == '__main__':
    unittest.main()
