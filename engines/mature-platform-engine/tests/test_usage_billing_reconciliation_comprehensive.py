"""Comprehensive test suite for UsageBillingReconciliationEngine (B44 - Skill 1473)."""

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    BillingDiscrepancy,
    BillingItemType,
    BillingReconciliationStatement,
    DiscrepancyType,
    InvoiceLineItemRecord,
    MeteredUsageRecord,
)
from elmos_mature_platform.usage_billing_reconciliation_engine import (
    UsageBillingReconciliationEngine,
)


class TestUsageBillingReconciliationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = UsageBillingReconciliationEngine(default_tolerance_usd=0.01)

    def test_initialization(self):
        self.assertEqual(self.engine.default_tolerance_usd, 0.01)
        self.assertEqual(len(self.engine.get_audit_log()), 0)

    def test_record_metered_usage_hash_chaining(self):
        r1 = self.engine.record_metered_usage(
            meter_id="m-01",
            tenant_id="tenant-acme",
            item_type=BillingItemType.TOKEN_INFERENCE,
            quantity=1000.0,
            unit_price_usd=0.002,
        )
        self.assertEqual(r1.subtotal_usd, 2.0)
        self.assertEqual(r1.hash_prev, "genesis-meter-hash-000000")
        self.assertTrue(len(r1.hash_curr) == 64)

        r2 = self.engine.record_metered_usage(
            meter_id="m-02",
            tenant_id="tenant-acme",
            item_type=BillingItemType.RUNNER_EXECUTION,
            quantity=10.0,
            unit_price_usd=0.50,
        )
        self.assertEqual(r2.subtotal_usd, 5.0)
        self.assertEqual(r2.hash_prev, r1.hash_curr)
        self.assertTrue(len(r2.hash_curr) == 64)

    def test_verify_meter_chain_integrity_valid(self):
        for i in range(5):
            self.engine.record_metered_usage(
                meter_id=f"m-{i}",
                tenant_id="tenant-chain",
                item_type=BillingItemType.STORAGE_PERSISTENCE,
                quantity=100.0,
                unit_price_usd=0.05,
            )
        valid, msg = self.engine.verify_meter_chain_integrity("tenant-chain")
        self.assertTrue(valid)
        self.assertIn("verified intact", msg)

    def test_verify_meter_chain_integrity_empty(self):
        valid, msg = self.engine.verify_meter_chain_integrity("empty-tenant")
        self.assertTrue(valid)
        self.assertIn("No records to verify", msg)

    def test_verify_meter_chain_integrity_tampered_payload(self):
        r1 = self.engine.record_metered_usage("m-t1", "t-tamper", BillingItemType.RECIPE_USAGE, 1.0, 10.0)
        r2 = self.engine.record_metered_usage("m-t2", "t-tamper", BillingItemType.RECIPE_USAGE, 2.0, 10.0)

        # Tamper r1 quantity without updating hash
        r1.quantity = 999.0
        valid, msg = self.engine.verify_meter_chain_integrity("t-tamper")
        self.assertFalse(valid)
        self.assertIn("Hash mismatch at index 0", msg)

    def test_verify_meter_chain_integrity_broken_chain(self):
        r1 = self.engine.record_metered_usage("m-b1", "t-broken", BillingItemType.PLATFORM_LICENSE, 1.0, 500.0)
        r2 = self.engine.record_metered_usage("m-b2", "t-broken", BillingItemType.PLATFORM_LICENSE, 1.0, 500.0)

        # Tamper r2 hash_prev link
        r2.hash_prev = "corrupted-prev-link-hash-12345"
        valid, msg = self.engine.verify_meter_chain_integrity("t-broken")
        self.assertFalse(valid)
        self.assertIn("Hash chain broken at index 1", msg)

    def test_record_invoice_line_item(self):
        line = InvoiceLineItemRecord(
            line_id="inv-line-1",
            invoice_id="inv-2026-09",
            item_type=BillingItemType.TOKEN_INFERENCE,
            quantity=5000.0,
            unit_price_usd=0.002,
            total_billed_usd=10.0,
        )
        self.engine.record_invoice_line_item("tenant-inv", "inv-2026-09", line)
        invoices = self.engine._invoices.get("tenant-inv", {})
        self.assertIn("inv-2026-09", invoices)
        self.assertEqual(len(invoices["inv-2026-09"]), 1)

    def test_reconcile_tenant_period_balanced(self):
        # Metered usage: $10 token inference + $5 runner execution = $15
        self.engine.record_metered_usage("m-rec1", "t-bal", BillingItemType.TOKEN_INFERENCE, 5000.0, 0.002)
        self.engine.record_metered_usage("m-rec2", "t-bal", BillingItemType.RUNNER_EXECUTION, 10.0, 0.50)

        # Invoice lines exactly match
        self.engine.record_invoice_line_item(
            "t-bal", "inv-01",
            InvoiceLineItemRecord("l1", "inv-01", BillingItemType.TOKEN_INFERENCE, 5000.0, 0.002, 10.0)
        )
        self.engine.record_invoice_line_item(
            "t-bal", "inv-01",
            InvoiceLineItemRecord("l2", "inv-01", BillingItemType.RUNNER_EXECUTION, 10.0, 0.50, 5.0)
        )

        statement = self.engine.reconcile_tenant_period(
            tenant_id="t-bal",
            period_start="",
            period_end="",
        )
        self.assertTrue(statement.balanced)
        self.assertAlmostEqual(statement.total_metered_usd, 15.0, places=2)
        self.assertAlmostEqual(statement.total_invoiced_usd, 15.0, places=2)
        self.assertAlmostEqual(statement.variance_total_usd, 0.0, places=2)
        self.assertEqual(len(statement.discrepancies), 0)
        self.assertTrue(len(statement.audit_hash) > 0)

    def test_reconcile_tenant_period_overbilling_discrepancy(self):
        # Metered usage: $10.0
        self.engine.record_metered_usage("m-ob", "t-ob", BillingItemType.TOKEN_INFERENCE, 5000.0, 0.002)

        # Invoiced: $15.0 (overbilling by $5.0)
        self.engine.record_invoice_line_item(
            "t-ob", "inv-ob",
            InvoiceLineItemRecord("l-ob", "inv-ob", BillingItemType.TOKEN_INFERENCE, 7500.0, 0.002, 15.0)
        )

        statement = self.engine.reconcile_tenant_period(
            tenant_id="t-ob",
            period_start="",
            period_end="",
        )
        self.assertFalse(statement.balanced)
        self.assertEqual(len(statement.discrepancies), 1)
        disc = statement.discrepancies[0]
        self.assertEqual(disc.discrepancy_type, DiscrepancyType.OVERBILLING)
        self.assertAlmostEqual(disc.variance_usd, 5.0, places=2)
        self.assertAlmostEqual(disc.adjustment_credit_usd, 5.0, places=2)
        self.assertFalse(disc.resolved)

    def test_reconcile_tenant_period_underbilling_discrepancy(self):
        # Metered usage: $20.0
        self.engine.record_metered_usage("m-ub", "t-ub", BillingItemType.RUNNER_EXECUTION, 40.0, 0.50)

        # Invoiced: $12.0 (underbilling by $8.0)
        self.engine.record_invoice_line_item(
            "t-ub", "inv-ub",
            InvoiceLineItemRecord("l-ub", "inv-ub", BillingItemType.RUNNER_EXECUTION, 24.0, 0.50, 12.0)
        )

        statement = self.engine.reconcile_tenant_period(
            tenant_id="t-ub",
            period_start="",
            period_end="",
        )
        self.assertFalse(statement.balanced)
        self.assertEqual(len(statement.discrepancies), 1)
        disc = statement.discrepancies[0]
        self.assertEqual(disc.discrepancy_type, DiscrepancyType.UNDERBILLING)
        self.assertAlmostEqual(disc.variance_usd, -8.0, places=2)
        self.assertEqual(disc.adjustment_credit_usd, 0.0)

    def test_apply_credit_adjustment_success(self):
        # Overbilling setup
        self.engine.record_metered_usage("m-adj", "t-adj", BillingItemType.TOKEN_INFERENCE, 1000.0, 0.002)
        self.engine.record_invoice_line_item(
            "t-adj", "inv-adj",
            InvoiceLineItemRecord("l-adj", "inv-adj", BillingItemType.TOKEN_INFERENCE, 2000.0, 0.002, 4.0)
        )
        stmt = self.engine.reconcile_tenant_period("t-adj", "", "")
        self.assertFalse(stmt.balanced)

        disc_id = stmt.discrepancies[0].discrepancy_id
        res = self.engine.apply_credit_adjustment(stmt.statement_id, disc_id)
        self.assertTrue(res)
        self.assertTrue(stmt.discrepancies[0].resolved)
        self.assertTrue(stmt.balanced)

    def test_apply_credit_adjustment_invalid_ids(self):
        res1 = self.engine.apply_credit_adjustment("unknown-statement", "unknown-disc")
        self.assertFalse(res1)

        # Valid statement, unknown discrepancy
        self.engine.record_metered_usage("m-x", "t-x", BillingItemType.TOKEN_INFERENCE, 10.0, 1.0)
        stmt = self.engine.reconcile_tenant_period("t-x", "", "")
        res2 = self.engine.apply_credit_adjustment(stmt.statement_id, "unknown-disc")
        self.assertFalse(res2)

    def test_get_statement(self):
        self.engine.record_metered_usage("m-get", "t-get", BillingItemType.RECIPE_USAGE, 1.0, 5.0)
        stmt = self.engine.reconcile_tenant_period("t-get", "", "")
        fetched = self.engine.get_statement(stmt.statement_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.statement_id, stmt.statement_id)

    def test_audit_logging(self):
        self.engine.record_metered_usage("m-aud", "t-aud", BillingItemType.TOKEN_INFERENCE, 10.0, 0.01)
        self.engine.record_invoice_line_item(
            "t-aud", "inv-aud",
            InvoiceLineItemRecord("l-aud", "inv-aud", BillingItemType.TOKEN_INFERENCE, 10.0, 0.01, 0.10)
        )
        self.engine.reconcile_tenant_period("t-aud", "", "")

        trail = self.engine.get_audit_log()
        actions = [t["action"] for t in trail]
        self.assertIn("usage_metered", actions)
        self.assertIn("invoice_line_recorded", actions)
        self.assertIn("reconciliation_completed", actions)


if __name__ == "__main__":
    unittest.main()
