"""Unit tests for PricingBillingService double-entry ledger, settlements, and reconciliation."""

from __future__ import annotations

from decimal import Decimal
import unittest

from elmos_pricing_billing.domain import (
    Currency,
    MeteringEvent,
    Money,
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


if __name__ == "__main__":
    unittest.main()
