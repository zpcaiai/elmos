"""Comprehensive test suite for CustomerRouteEditionMarginEngine (Batch 44 - Skill 1467)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.customer_route_edition_margin_engine import CustomerRouteEditionMarginEngine
from elmos_mature_platform.types import (
    CustomerRouteMarginRecord,
    EditionMarginSummary,
    MarginHealthStatus,
)


class TestCustomerRouteEditionMarginComprehensive(unittest.TestCase):
    """Rigorous unit testing for CustomerRouteEditionMarginEngine."""

    def setUp(self) -> None:
        self.engine = CustomerRouteEditionMarginEngine()

    def test_record_project_financials_success(self) -> None:
        rec = CustomerRouteMarginRecord(
            record_id="crm-101",
            customer_id="cust-acme",
            project_id="proj-java2go",
            route_key="java_to_go",
            edition="multitenant_saas",
            contract_revenue_usd=100000.0,
            compute_cogs_usd=5000.0,
            model_cogs_usd=10000.0,
            storage_cogs_usd=1000.0,
            human_cogs_usd=12000.0,
            license_cogs_usd=2000.0,
            target_margin_pct=70.0,
        )
        rid = self.engine.record_project_financials(rec)
        self.assertEqual(rid, "crm-101")
        fetched = self.engine.get_record("crm-101")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.customer_id, "cust-acme")
        self.assertEqual(fetched.contract_revenue_usd, 100000.0)

    def test_record_project_financials_auto_generates_id_and_date(self) -> None:
        rec = CustomerRouteMarginRecord(
            record_id="",
            customer_id="cust-globex",
            project_id="proj-cobol2java",
            route_key="cobol_to_java",
            edition="dedicated_saas",
            contract_revenue_usd=250000.0,
        )
        rid = self.engine.record_project_financials(rec)
        self.assertTrue(rid.startswith("crm-"))
        self.assertTrue(len(rec.recorded_at) > 0)

    def test_record_project_financials_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.record_project_financials(
                CustomerRouteMarginRecord("1", "", "p", "r", "e", 100.0)
            )
        with self.assertRaises(ValueError):
            self.engine.record_project_financials(
                CustomerRouteMarginRecord("2", "c", "", "r", "e", 100.0)
            )
        with self.assertRaises(ValueError):
            self.engine.record_project_financials(
                CustomerRouteMarginRecord("3", "c", "p", "", "e", 100.0)
            )
        with self.assertRaises(ValueError):
            self.engine.record_project_financials(
                CustomerRouteMarginRecord("4", "c", "p", "r", "", 100.0)
            )
        with self.assertRaises(ValueError):
            self.engine.record_project_financials(
                CustomerRouteMarginRecord("5", "c", "p", "r", "e", -50.0)
            )

    def test_calculate_gross_margin_and_health_healthy(self) -> None:
        # 100k revenue, 30k total COGS -> 70k margin (70% -> HEALTHY)
        rec = CustomerRouteMarginRecord(
            record_id="crm-healthy",
            customer_id="c1", project_id="p1", route_key="r1", edition="e1",
            contract_revenue_usd=100000.0,
            compute_cogs_usd=10000.0,
            model_cogs_usd=10000.0,
            human_cogs_usd=10000.0,
        )
        self.engine.record_project_financials(rec)

        res = self.engine.calculate_gross_margin("crm-healthy")
        self.assertEqual(res["contract_revenue_usd"], 100000.0)
        self.assertEqual(res["total_cogs_usd"], 30000.0)
        self.assertEqual(res["gross_margin_usd"], 70000.0)
        self.assertEqual(res["gross_margin_pct"], 70.0)

        health = self.engine.get_margin_health_status("crm-healthy")
        self.assertEqual(health, MarginHealthStatus.HEALTHY)

    def test_calculate_gross_margin_and_health_warning(self) -> None:
        # 100k revenue, 55k COGS -> 45k margin (45% -> WARNING)
        rec = CustomerRouteMarginRecord(
            record_id="crm-warn",
            customer_id="c2", project_id="p2", route_key="r2", edition="e2",
            contract_revenue_usd=100000.0,
            compute_cogs_usd=25000.0,
            human_cogs_usd=30000.0,
        )
        self.engine.record_project_financials(rec)

        res = self.engine.calculate_gross_margin("crm-warn")
        self.assertEqual(res["gross_margin_pct"], 45.0)

        health = self.engine.get_margin_health_status("crm-warn")
        self.assertEqual(health, MarginHealthStatus.WARNING)

    def test_calculate_gross_margin_and_health_critical(self) -> None:
        # 100k revenue, 85k COGS -> 15k margin (15% -> CRITICAL)
        rec = CustomerRouteMarginRecord(
            record_id="crm-crit",
            customer_id="c3", project_id="p3", route_key="r3", edition="e3",
            contract_revenue_usd=100000.0,
            compute_cogs_usd=40000.0,
            human_cogs_usd=45000.0,
        )
        self.engine.record_project_financials(rec)

        res = self.engine.calculate_gross_margin("crm-crit")
        self.assertEqual(res["gross_margin_pct"], 15.0)

        health = self.engine.get_margin_health_status("crm-crit")
        self.assertEqual(health, MarginHealthStatus.CRITICAL)

    def test_calculate_gross_margin_zero_revenue(self) -> None:
        rec = CustomerRouteMarginRecord(
            record_id="crm-zero",
            customer_id="c4", project_id="p4", route_key="r4", edition="e4",
            contract_revenue_usd=0.0,
            compute_cogs_usd=1000.0,
        )
        self.engine.record_project_financials(rec)
        res = self.engine.calculate_gross_margin("crm-zero")
        self.assertEqual(res["gross_margin_usd"], -1000.0)
        self.assertEqual(res["gross_margin_pct"], -100.0)
        self.assertEqual(self.engine.get_margin_health_status("crm-zero"), MarginHealthStatus.CRITICAL)

    def test_calculate_gross_margin_missing_record_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.calculate_gross_margin("missing-id")

    def test_get_margin_by_route(self) -> None:
        r1 = CustomerRouteMarginRecord("1", "c", "p1", "py_to_rust", "saas", 50000.0, compute_cogs_usd=10000.0)
        r2 = CustomerRouteMarginRecord("2", "c", "p2", "py_to_rust", "saas", 50000.0, compute_cogs_usd=10000.0)
        self.engine.record_project_financials(r1)
        self.engine.record_project_financials(r2)

        agg = self.engine.get_margin_by_route("py_to_rust")
        self.assertEqual(agg["project_count"], 2)
        self.assertEqual(agg["total_revenue_usd"], 100000.0)
        self.assertEqual(agg["total_cogs_usd"], 20000.0)
        self.assertEqual(agg["gross_margin_usd"], 80000.0)
        self.assertEqual(agg["gross_margin_pct"], 80.0)

        empty_agg = self.engine.get_margin_by_route("nonexistent_route")
        self.assertEqual(empty_agg["project_count"], 0)
        self.assertEqual(empty_agg["total_revenue_usd"], 0.0)

    def test_get_margin_by_edition(self) -> None:
        r1 = CustomerRouteMarginRecord("1", "c", "p1", "r1", "air_gapped", 200000.0, human_cogs_usd=60000.0)
        self.engine.record_project_financials(r1)

        summary = self.engine.get_margin_by_edition("air_gapped")
        self.assertEqual(summary.edition, "air_gapped")
        self.assertEqual(summary.total_revenue_usd, 200000.0)
        self.assertEqual(summary.total_cogs_usd, 60000.0)
        self.assertEqual(summary.gross_margin_usd, 140000.0)
        self.assertEqual(summary.gross_margin_pct, 70.0)
        self.assertEqual(summary.health_status, MarginHealthStatus.HEALTHY)

    def test_get_fleet_margin_report(self) -> None:
        rep_empty = self.engine.get_fleet_margin_report()
        self.assertEqual(rep_empty["total_projects"], 0)
        self.assertEqual(rep_empty["portfolio_revenue_usd"], 0.0)

        r_h = CustomerRouteMarginRecord("h", "c", "p", "r", "e", 100.0, compute_cogs_usd=20.0)
        r_c = CustomerRouteMarginRecord("c", "c", "p", "r", "e", 100.0, compute_cogs_usd=90.0)
        self.engine.record_project_financials(r_h)
        self.engine.record_project_financials(r_c)

        rep = self.engine.get_fleet_margin_report()
        self.assertEqual(rep["total_projects"], 2)
        self.assertEqual(rep["portfolio_revenue_usd"], 200.0)
        self.assertEqual(rep["portfolio_cogs_usd"], 110.0)
        self.assertEqual(rep["portfolio_gross_margin_usd"], 90.0)
        self.assertEqual(rep["health_distribution"]["healthy"], 1)
        self.assertEqual(rep["health_distribution"]["critical"], 1)


if __name__ == "__main__":
    unittest.main()
