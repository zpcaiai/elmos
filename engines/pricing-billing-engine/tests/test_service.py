"""Unit tests for PricingBillingService double-entry ledger, settlements, and reconciliation."""

from __future__ import annotations

from decimal import Decimal
import unittest

from elmos_pricing_billing.domain import (
    ContractError,
    Currency,
    EntitlementGrant,
    InvoiceLineItem,
    InvoiceStatus,
    MeteringEvent,
    Money,
    QuotaLimit,
    RateCard,
    ReconciliationStatus,
)
from elmos_pricing_billing.service import PricingBillingService


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PricingBillingService()
        self.tenant_id = "tenant-svc-001"

    def test_deposit_and_idempotency(self) -> None:
        amount = Money(Decimal("5000.0000"), Currency.CREDIT)
        entry1 = self.service.deposit_credits(
            tenant_id=self.tenant_id,
            amount=amount,
            idempotency_key="dep-idem-001",
        )
        self.assertEqual(self.service.get_wallet_balance(self.tenant_id), amount)

        # Re-executing with same idempotency key returns same entry without double credit
        entry2 = self.service.deposit_credits(
            tenant_id=self.tenant_id,
            amount=amount,
            idempotency_key="dep-idem-001",
        )
        self.assertEqual(entry1.entry_id, entry2.entry_id)
        self.assertEqual(self.service.get_wallet_balance(self.tenant_id), amount)

    def test_usage_settlement(self) -> None:
        self.service.deposit_credits(
            tenant_id=self.tenant_id,
            amount=Money(Decimal("1000.0000"), Currency.CREDIT),
            idempotency_key="dep-002",
        )
        event = MeteringEvent(
            event_id="ev-01",
            tenant_id=self.tenant_id,
            project_id="proj-01",
            task_id="task-01",
            model_alias="qwen2.5-coder",
            prompt_tokens=1000,
            completion_tokens=500,
            runner_seconds=10.0,
            storage_bytes=0,
        )
        cost = Money(Decimal("150.0000"), Currency.CREDIT)
        entry = self.service.record_usage_and_settle(event, cost, idempotency_key="task-settle-01")
        self.assertEqual(entry.balance_after, Money(Decimal("850.0000"), Currency.CREDIT))

    def test_insufficient_credits_raises(self) -> None:
        event = MeteringEvent(
            event_id="ev-02",
            tenant_id="tenant-poor",
            project_id="proj-01",
            task_id="task-02",
            model_alias="qwen2.5-coder",
            prompt_tokens=1000,
            completion_tokens=500,
            runner_seconds=10.0,
            storage_bytes=0,
        )
        cost = Money(Decimal("100.0000"), Currency.CREDIT)
        with self.assertRaises(ValueError):
            self.service.record_usage_and_settle(event, cost, idempotency_key="task-settle-02")

    def test_reconciliation(self) -> None:
        self.service.deposit_credits(
            tenant_id=self.tenant_id,
            amount=Money(Decimal("2000.0000"), Currency.CREDIT),
            idempotency_key="dep-003",
        )
        res_balanced = self.service.reconcile_tenant_period(
            tenant_id=self.tenant_id,
            period="2026-08",
            reported_bank_balance=Money(Decimal("2000.0000"), Currency.CREDIT),
        )
        self.assertEqual(res_balanced.status, ReconciliationStatus.BALANCED)

        res_discrepancy = self.service.reconcile_tenant_period(
            tenant_id=self.tenant_id,
            period="2026-08",
            reported_bank_balance=Money(Decimal("1500.0000"), Currency.CREDIT),
        )
        self.assertEqual(res_discrepancy.status, ReconciliationStatus.DISCREPANCY)

    def test_quota_limits_and_budget_guard(self) -> None:
        # 1. No quota defined
        ok, reason, remaining = self.service.check_budget_guard("no-quota-tenant", Money(Decimal("50.00"), Currency.USD))
        self.assertTrue(ok)
        self.assertEqual(reason, "NO_QUOTA_DEFINED")

        # 2. Quota defined with hard stop
        quota = QuotaLimit(
            tenant_id="tenant-budget",
            max_monthly_spend=Money(Decimal("100.0000"), Currency.USD),
            current_spend=Money(Decimal("70.0000"), Currency.USD),
            hard_stop_enabled=True,
            alert_threshold_pct=80.0,
        )
        self.service.set_quota(quota)
        self.assertEqual(self.service.get_quota("tenant-budget"), quota)

        # Within budget (< 80%)
        ok, reason, rem = self.service.check_budget_guard("tenant-budget", Money(Decimal("5.0000"), Currency.USD))
        self.assertTrue(ok)
        self.assertEqual(reason, "WITHIN_BUDGET")

        # Reaches alert threshold (>= 80%)
        ok, reason, rem = self.service.check_budget_guard("tenant-budget", Money(Decimal("12.0000"), Currency.USD))
        self.assertTrue(ok)
        self.assertEqual(reason, "ALERT_THRESHOLD_REACHED")

        # Exceeds quota with hard stop
        ok, reason, rem = self.service.check_budget_guard("tenant-budget", Money(Decimal("35.0000"), Currency.USD))
        self.assertFalse(ok)
        self.assertEqual(reason, "QUOTA_EXCEEDED_HARD_STOP")

        # Quota with soft stop
        soft_quota = QuotaLimit(
            tenant_id="tenant-soft",
            max_monthly_spend=Money(Decimal("100.0000"), Currency.USD),
            current_spend=Money(Decimal("95.0000"), Currency.USD),
            hard_stop_enabled=False,
            alert_threshold_pct=80.0,
        )
        self.service.set_quota(soft_quota)
        ok, reason, rem = self.service.check_budget_guard("tenant-soft", Money(Decimal("10.0000"), Currency.USD))
        self.assertTrue(ok)
        self.assertEqual(reason, "QUOTA_EXCEEDED_SOFT_WARNING")

    def test_invoicing_lifecycle(self) -> None:
        lines = [
            InvoiceLineItem(
                description="Team Plan Base",
                quantity=Decimal("1"),
                unit_price=Money(Decimal("299.0000"), Currency.USD),
                total=Money(Decimal("299.0000"), Currency.USD),
            ),
            InvoiceLineItem(
                description="Extra Compute Runner",
                quantity=Decimal("5"),
                unit_price=Money(Decimal("10.0000"), Currency.USD),
                total=Money(Decimal("50.0000"), Currency.USD),
            ),
        ]
        # Issue invoice with 10% tax
        inv = self.service.issue_invoice(
            tenant_id=self.tenant_id,
            period="2026-08",
            lines=lines,
            tax_rate=Decimal("0.10"),
        )
        self.assertEqual(inv.status, InvoiceStatus.ISSUED)
        self.assertEqual(inv.subtotal, Money(Decimal("349.0000"), Currency.USD))
        self.assertEqual(inv.tax, Money(Decimal("34.9000"), Currency.USD))
        self.assertEqual(inv.total, Money(Decimal("383.9000"), Currency.USD))

        # Retrieve invoice
        retrieved = self.service.get_invoice(inv.invoice_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.invoice_id, inv.invoice_id)

        # Pay invoice
        paid = self.service.pay_invoice(inv.invoice_id)
        self.assertEqual(paid.status, InvoiceStatus.PAID)

        # Paying again raises ValueError
        with self.assertRaises(ValueError):
            self.service.pay_invoice(inv.invoice_id)

        # Voiding paid invoice raises ValueError
        with self.assertRaises(ValueError):
            self.service.void_invoice(inv.invoice_id)

    def test_void_unpaid_invoice(self) -> None:
        lines = [
            InvoiceLineItem(
                description="Draft item",
                quantity=Decimal("1"),
                unit_price=Money(Decimal("100.0000"), Currency.USD),
                total=Money(Decimal("100.0000"), Currency.USD),
            )
        ]
        inv = self.service.issue_invoice(self.tenant_id, "2026-08", lines)
        voided = self.service.void_invoice(inv.invoice_id)
        self.assertEqual(voided.status, InvoiceStatus.VOID)

    def test_invoice_empty_lines_or_mismatched_currency_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.service.issue_invoice(self.tenant_id, "2026-08", [])

        mixed_lines = [
            InvoiceLineItem("USD line", Decimal("1"), Money(Decimal("10.00"), Currency.USD), Money(Decimal("10.00"), Currency.USD)),
            InvoiceLineItem("EUR line", Decimal("1"), Money(Decimal("10.00"), Currency.EUR), Money(Decimal("10.00"), Currency.EUR)),
        ]
        with self.assertRaises(ContractError):
            self.service.issue_invoice(self.tenant_id, "2026-08", mixed_lines)

    def test_credit_note_generation(self) -> None:
        lines = [
            InvoiceLineItem("Service fee", Decimal("1"), Money(Decimal("100.0000"), Currency.USD), Money(Decimal("100.0000"), Currency.USD))
        ]
        inv = self.service.issue_invoice(self.tenant_id, "2026-08", lines)

        # Partial credit note
        note = self.service.issue_credit_note(
            invoice_id=inv.invoice_id,
            amount=Money(Decimal("25.0000"), Currency.USD),
            reason="Service degradation SLA credit",
        )
        self.assertEqual(note.amount, Money(Decimal("25.0000"), Currency.USD))
        self.assertEqual(note.invoice_id, inv.invoice_id)

        # Credit note exceeding invoice raises ValueError
        with self.assertRaises(ValueError):
            self.service.issue_credit_note(
                invoice_id=inv.invoice_id,
                amount=Money(Decimal("200.0000"), Currency.USD),
                reason="Excessive refund",
            )

    def test_entitlements(self) -> None:
        grant = EntitlementGrant(
            grant_id="eg-01",
            tenant_id=self.tenant_id,
            feature_key="byok_keys",
            enabled=True,
            max_concurrency=8,
            valid_until="2027-01-01",
        )
        self.service.grant_entitlement(grant)
        self.assertTrue(self.service.check_entitlement(self.tenant_id, "byok_keys"))
        self.assertFalse(self.service.check_entitlement(self.tenant_id, "unregistered_feature"))

    def test_usage_aggregation_and_rate_card(self) -> None:
        rate_card = RateCard(
            card_id="rc-std",
            version="1.0",
            model_input_token_rate=Money(Decimal("0.0030"), Currency.USD),  # per 1k tokens
            model_output_token_rate=Money(Decimal("0.0150"), Currency.USD),  # per 1k tokens
            runner_second_rate=Money(Decimal("0.0002"), Currency.USD),
            storage_gb_month_rate=Money(Decimal("0.0200"), Currency.USD),
        )
        # Record 2 events for target tenant and 1 for another tenant
        self.service.record_metering_event(
            MeteringEvent("e1", self.tenant_id, "p1", "t1", "claude-3-5-sonnet", 2000, 1000, 10.0, 0)
        )
        self.service.record_metering_event(
            MeteringEvent("e2", self.tenant_id, "p1", "t2", "claude-3-5-sonnet", 3000, 2000, 20.0, 0)
        )
        self.service.record_metering_event(
            MeteringEvent("e3", "other-tenant", "p1", "t3", "claude-3-5-sonnet", 10000, 5000, 50.0, 0)
        )

        record = self.service.aggregate_usage(self.tenant_id, "2026-08", rate_card)
        self.assertEqual(record.total_prompt_tokens, 5000)
        self.assertEqual(record.total_completion_tokens, 3000)
        self.assertEqual(record.total_runner_seconds, 30.0)

        # prompt: 5000/1000 * 0.003 = 0.0150
        # completion: 3000/1000 * 0.015 = 0.0450
        # runner: 30.0 * 0.0002 = 0.0060
        # total: 0.0660
        self.assertEqual(record.total_cost, Money(Decimal("0.0660"), Currency.USD))

    def test_margin_analytics(self) -> None:
        rev = Money(Decimal("1000.0000"), Currency.USD)
        cost = Money(Decimal("250.0000"), Currency.USD)
        margin = self.service.calculate_margin(rev, cost)
        self.assertTrue(margin["is_profitable"])
        self.assertAlmostEqual(margin["gross_margin_pct"], 75.0, places=2)

        # Loss-making
        high_cost = Money(Decimal("1200.0000"), Currency.USD)
        margin_loss = self.service.calculate_margin(rev, high_cost)
        self.assertFalse(margin_loss["is_profitable"])
        self.assertAlmostEqual(margin_loss["gross_margin_pct"], -20.0, places=2)


if __name__ == "__main__":
    unittest.main()

