"""Comprehensive test suite for ShowbackChargebackEngine (Batch 44 - Skill 1458)."""

import unittest

from elmos_mature_platform.showback_chargeback_engine import ShowbackChargebackEngine
from elmos_mature_platform.types import (
    ChargebackDispute,
    ChargebackInvoice,
    DepartmentShowbackSummary,
)


class TestShowbackChargebackComprehensive(unittest.TestCase):
    """Rigorous unit testing for ShowbackChargebackEngine."""

    def setUp(self) -> None:
        self.engine = ShowbackChargebackEngine()

    def test_generate_invoice_success(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="inv-101",
            department_id="dept-engineering",
            billing_period="2026-Q1",
            total_amount_usd=1500.0,
            line_items={"compute": 1000.0, "storage": 500.0},
        )
        iid = self.engine.generate_invoice(inv)
        self.assertEqual(iid, "inv-101")
        retrieved = self.engine.get_invoice("inv-101")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.department_id, "dept-engineering")
        self.assertFalse(retrieved.paid)
        self.assertTrue(len(retrieved.issued_at) > 0)

    def test_generate_invoice_auto_calculates_total_from_line_items(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="",
            department_id="dept-data",
            billing_period="2026-03",
            total_amount_usd=0.0,
            line_items={"bigquery": 250.75, "gcs": 149.25},
        )
        iid = self.engine.generate_invoice(inv)
        self.assertTrue(iid.startswith("inv-"))
        self.assertEqual(inv.total_amount_usd, 400.0)

    def test_generate_invoice_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.generate_invoice(
                ChargebackInvoice("inv-neg", "dept", "2026-01", total_amount_usd=-10.0)
            )
        with self.assertRaises(ValueError):
            self.engine.generate_invoice(
                ChargebackInvoice("inv-nodept", "", "2026-01", total_amount_usd=100.0)
            )

    def test_pay_invoice_success(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="inv-pay",
            department_id="dept-sales",
            billing_period="2026-02",
            total_amount_usd=500.0,
        )
        self.engine.generate_invoice(inv)
        paid_inv = self.engine.pay_invoice("inv-pay")
        self.assertTrue(paid_inv.paid)
        self.assertTrue(len(paid_inv.paid_at) > 0)

        # Idempotent re-payment
        paid_again = self.engine.pay_invoice("inv-pay")
        self.assertEqual(paid_again.paid_at, paid_inv.paid_at)

    def test_pay_unknown_invoice_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.pay_invoice("inv-ghost")

    def test_raise_dispute_success(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="inv-disp",
            department_id="dept-marketing",
            billing_period="2026-02",
            total_amount_usd=1000.0,
        )
        self.engine.generate_invoice(inv)

        disp = ChargebackDispute(
            dispute_id="disp-1",
            invoice_id="inv-disp",
            department_id="dept-marketing",
            disputed_amount_usd=200.0,
            reason="Unused VM capacity billed in error",
        )
        did = self.engine.raise_dispute(disp)
        self.assertEqual(did, "disp-1")
        retrieved = self.engine.get_dispute("disp-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, "open")

    def test_raise_dispute_validation_errors(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="inv-bound",
            department_id="dept-a",
            billing_period="2026-01",
            total_amount_usd=300.0,
        )
        self.engine.generate_invoice(inv)

        # Non-positive amount
        with self.assertRaises(ValueError):
            self.engine.raise_dispute(
                ChargebackDispute("d0", "inv-bound", "dept-a", disputed_amount_usd=0.0, reason="zero")
            )
        # Exceeds total
        with self.assertRaises(ValueError):
            self.engine.raise_dispute(
                ChargebackDispute("d1", "inv-bound", "dept-a", disputed_amount_usd=500.0, reason="too much")
            )
        # Non-existent invoice
        with self.assertRaises(ValueError):
            self.engine.raise_dispute(
                ChargebackDispute("d2", "inv-unknown", "dept-a", disputed_amount_usd=50.0, reason="ghost")
            )

    def test_resolve_dispute_approved_adjusts_invoice(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="inv-adj",
            department_id="dept-ops",
            billing_period="2026-03",
            total_amount_usd=1000.0,
        )
        self.engine.generate_invoice(inv)
        disp_id = self.engine.raise_dispute(
            ChargebackDispute("d-adj", "inv-adj", "dept-ops", disputed_amount_usd=300.0, reason="SLA breach")
        )

        resolved = self.engine.resolve_dispute(disp_id, approved=True, notes="Refund credited")
        self.assertEqual(resolved.status, "resolved")
        self.assertEqual(resolved.notes, "Refund credited")
        self.assertTrue(len(resolved.resolved_at) > 0)

        # Invoice should now be 1000 - 300 = 700
        updated_inv = self.engine.get_invoice("inv-adj")
        self.assertEqual(updated_inv.total_amount_usd, 700.0)

    def test_resolve_dispute_rejected_preserves_invoice(self) -> None:
        inv = ChargebackInvoice(
            invoice_id="inv-rej",
            department_id="dept-qa",
            billing_period="2026-03",
            total_amount_usd=800.0,
        )
        self.engine.generate_invoice(inv)
        disp_id = self.engine.raise_dispute(
            ChargebackDispute("d-rej", "inv-rej", "dept-qa", disputed_amount_usd=100.0, reason="Valid charge contested")
        )

        rejected = self.engine.resolve_dispute(disp_id, approved=False, notes="Usage verified legitimate")
        self.assertEqual(rejected.status, "rejected")

        updated_inv = self.engine.get_invoice("inv-rej")
        self.assertEqual(updated_inv.total_amount_usd, 800.0)

    def test_resolve_dispute_already_resolved_raises(self) -> None:
        inv = ChargebackInvoice("i-once", "dept-1", "p", 100.0)
        self.engine.generate_invoice(inv)
        did = self.engine.raise_dispute(ChargebackDispute("d-once", "i-once", "dept-1", 20.0, "reason"))
        self.engine.resolve_dispute(did, approved=True)

        with self.assertRaises(ValueError):
            self.engine.resolve_dispute(did, approved=False)

    def test_get_department_showback(self) -> None:
        self.engine.generate_invoice(
            ChargebackInvoice(
                "inv-d1",
                "dept-fintech",
                "2026-01",
                500.0,
                line_items={"api": 300.0, "db": 200.0},
            )
        )
        self.engine.generate_invoice(
            ChargebackInvoice(
                "inv-d2",
                "dept-fintech",
                "2026-02",
                700.0,
                line_items={"api": 400.0, "db": 300.0},
            )
        )
        self.engine.raise_dispute(
            ChargebackDispute("d-fin", "inv-d2", "dept-fintech", 100.0, "audit")
        )

        summary = self.engine.get_department_showback("dept-fintech")
        self.assertEqual(summary.department_id, "dept-fintech")
        self.assertEqual(summary.total_spend_usd, 1200.0)
        self.assertEqual(summary.invoices_count, 2)
        self.assertEqual(summary.open_disputes_count, 1)
        self.assertEqual(summary.spend_by_category["api"], 700.0)
        self.assertEqual(summary.spend_by_category["db"], 500.0)

    def test_get_chargeback_report(self) -> None:
        self.engine.generate_invoice(ChargebackInvoice("i1", "dept-a", "p1", 1000.0))
        self.engine.generate_invoice(ChargebackInvoice("i2", "dept-b", "p2", 2000.0))
        self.engine.pay_invoice("i1")
        self.engine.raise_dispute(ChargebackDispute("d1", "i2", "dept-b", 500.0, "reason"))

        report = self.engine.get_chargeback_report()
        self.assertEqual(report["total_invoices_count"], 2)
        self.assertEqual(report["paid_invoices_count"], 1)
        self.assertEqual(report["total_invoiced_usd"], 3000.0)
        self.assertEqual(report["total_paid_usd"], 1000.0)
        self.assertEqual(report["total_outstanding_usd"], 2000.0)
        self.assertEqual(report["open_disputes_count"], 1)
        self.assertEqual(report["active_disputed_usd"], 500.0)


if __name__ == "__main__":
    unittest.main()
