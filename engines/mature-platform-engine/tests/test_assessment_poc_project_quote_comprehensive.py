"""Comprehensive test suite for AssessmentPocProjectQuoteEngine (Batch 44 - Skill 1466)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.assessment_poc_project_quote_engine import AssessmentPocProjectQuoteEngine
from elmos_mature_platform.types import (
    AssessmentPocQuote,
    ProjectQuoteItem,
    QuoteTier,
)


class TestAssessmentPocProjectQuoteComprehensive(unittest.TestCase):
    """Rigorous unit testing for AssessmentPocProjectQuoteEngine."""

    def setUp(self) -> None:
        self.engine = AssessmentPocProjectQuoteEngine()

    def test_create_quote_success(self) -> None:
        quote = AssessmentPocQuote(
            quote_id="quote-101",
            customer_name="Global Bank Corp",
            project_scope="Core Banking Java to Go Modernization",
            tier=QuoteTier.POC_PILOT,
            estimated_duration_weeks=6,
            items=[
                ProjectQuoteItem(
                    item_id="it-1",
                    name="Architecture Assessment",
                    unit_type="days",
                    quantity=10,
                    unit_rate_usd=1500.0,
                    discount_pct=10.0,
                ),
                ProjectQuoteItem(
                    item_id="it-2",
                    name="Automated Transpiler Setup",
                    unit_type="fixed",
                    quantity=1,
                    unit_rate_usd=10000.0,
                    discount_pct=0.0,
                ),
            ],
        )
        qid = self.engine.create_quote(quote)
        self.assertEqual(qid, "quote-101")
        # it-1: 10 * 1500 * 0.9 = 13500.0
        # it-2: 10000.0
        # Total = 23500.0
        self.assertEqual(quote.total_cost_usd, 23500.0)
        self.assertEqual(quote.status, "draft")

    def test_create_quote_auto_generates_id_and_created_at(self) -> None:
        quote = AssessmentPocQuote(
            quote_id="",
            customer_name="Tech Solutions",
            project_scope="Python 2 to 3 migration",
        )
        qid = self.engine.create_quote(quote)
        self.assertTrue(qid.startswith("quote-"))
        self.assertTrue(len(quote.created_at) > 0)

    def test_create_quote_missing_customer_or_scope_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.create_quote(AssessmentPocQuote(quote_id="1", customer_name="", project_scope="Scope"))
        with self.assertRaises(ValueError):
            self.engine.create_quote(AssessmentPocQuote(quote_id="2", customer_name="Customer", project_scope=""))

    def test_add_item_recalculates_total(self) -> None:
        quote = AssessmentPocQuote(
            quote_id="q-recalc",
            customer_name="Retail Giant",
            project_scope="E-commerce Migration",
            items=[],
        )
        self.engine.create_quote(quote)
        self.assertEqual(quote.total_cost_usd, 0.0)

        item1 = ProjectQuoteItem(
            item_id="",
            name="Discovery",
            unit_type="hours",
            quantity=40,
            unit_rate_usd=200.0,
        )
        updated = self.engine.add_item("q-recalc", item1)
        self.assertEqual(len(updated.items), 1)
        self.assertTrue(updated.items[0].item_id.startswith("qitem-"))
        self.assertEqual(updated.total_cost_usd, 8000.0)

        item2 = ProjectQuoteItem(
            item_id="it-disc",
            name="Testing Phase",
            unit_type="hours",
            quantity=20,
            unit_rate_usd=200.0,
            discount_pct=50.0,  # 20 * 200 * 0.5 = 2000
        )
        updated2 = self.engine.add_item("q-recalc", item2)
        self.assertEqual(len(updated2.items), 2)
        self.assertEqual(updated2.total_cost_usd, 10000.0)

    def test_add_item_nonexistent_quote_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.add_item("missing-quote", ProjectQuoteItem("1", "item", "days", 1, 100))

    def test_update_status_lifecycle(self) -> None:
        quote = AssessmentPocQuote(
            quote_id="q-stat",
            customer_name="Fintech Inc",
            project_scope="Audit",
        )
        self.engine.create_quote(quote)

        q1 = self.engine.update_status("q-stat", "presented")
        self.assertEqual(q1.status, "presented")

        q2 = self.engine.update_status("q-stat", "accepted")
        self.assertEqual(q2.status, "accepted")

    def test_update_status_invalid_raises(self) -> None:
        quote = AssessmentPocQuote(quote_id="q-inv", customer_name="A", project_scope="B")
        self.engine.create_quote(quote)
        with self.assertRaises(ValueError):
            self.engine.update_status("q-inv", "invalid_status_xyz")

    def test_update_status_nonexistent_quote_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.update_status("missing-q", "accepted")

    def test_get_quote(self) -> None:
        quote = AssessmentPocQuote(quote_id="q-get", customer_name="Acme", project_scope="Test")
        self.engine.create_quote(quote)
        self.assertIsNotNone(self.engine.get_quote("q-get"))
        self.assertIsNone(self.engine.get_quote("nonexistent"))

    def test_get_quote_pipeline_report(self) -> None:
        rep_empty = self.engine.get_quote_pipeline_report()
        self.assertEqual(rep_empty["total_quotes"], 0)
        self.assertEqual(rep_empty["total_pipeline_value_usd"], 0.0)
        self.assertEqual(rep_empty["acceptance_rate_pct"], 0.0)

        q1 = AssessmentPocQuote(
            quote_id="q1",
            customer_name="C1",
            project_scope="S1",
            tier=QuoteTier.POC_PILOT,
            items=[ProjectQuoteItem("1", "item", "days", 10, 1000.0)],
        )
        q2 = AssessmentPocQuote(
            quote_id="q2",
            customer_name="C2",
            project_scope="S2",
            tier=QuoteTier.STANDARD_PRODUCTION,
            items=[ProjectQuoteItem("2", "item", "days", 20, 1000.0)],
        )
        self.engine.create_quote(q1)
        self.engine.create_quote(q2)
        self.engine.update_status("q1", "accepted")

        rep = self.engine.get_quote_pipeline_report()
        self.assertEqual(rep["total_quotes"], 2)
        self.assertEqual(rep["total_pipeline_value_usd"], 30000.0)
        self.assertEqual(rep["total_accepted_value_usd"], 10000.0)
        self.assertEqual(rep["acceptance_rate_pct"], 50.0)
        self.assertEqual(rep["quotes_by_tier"][QuoteTier.POC_PILOT.value], 1)
        self.assertEqual(rep["quotes_by_tier"][QuoteTier.STANDARD_PRODUCTION.value], 1)


if __name__ == "__main__":
    unittest.main()
