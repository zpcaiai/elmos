"""Service orchestrator for the ELMOS Pricing & Billing Engine.

Manages metering, double-entry wallet balance, budget guards, invoicing, and reconciliation.
"""

from __future__ import annotations

from decimal import Decimal
import time
import uuid
from typing import Any, Mapping, Sequence

from .contracts import (
    RequestContract,
    ResultContract,
    canonical_json,
    digest_json,
)
from .domain import (
    Currency,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LedgerEntry,
    LedgerEntryType,
    MeteringEvent,
    Money,
    QuotaLimit,
    ReconciliationResult,
    ReconciliationStatus,
    TenantScope,
    UsageRecord,
)
from .handlers import SKILL_REGISTRY, dispatch_skill


class PricingBillingService:
    """Enterprise service orchestrator for pricing, metering, and billing operations."""

    def __init__(self) -> None:
        self._wallets: dict[str, Money] = {}  # tenant_id -> balance
        self._ledger: list[LedgerEntry] = []
        self._quotas: dict[str, QuotaLimit] = {}
        self._invoices: dict[str, Invoice] = {}

    def dispatch(self, skill_name: str, request_data: Mapping[str, Any]) -> ResultContract:
        return dispatch_skill(skill_name, request_data)

    def get_wallet_balance(self, tenant_id: str) -> Money:
        return self._wallets.get(tenant_id, Money(Decimal("0.0000"), Currency.CREDIT))

    def deposit_credits(
        self,
        tenant_id: str,
        amount: Money,
        idempotency_key: str,
        reference_id: str = "",
    ) -> LedgerEntry:
        # Check for idempotent duplicate
        for entry in self._ledger:
            if entry.tenant_id == tenant_id and entry.idempotency_key == idempotency_key:
                return entry

        current = self.get_wallet_balance(tenant_id)
        new_balance = current + amount
        self._wallets[tenant_id] = new_balance

        entry = LedgerEntry(
            entry_id=f"ledg-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            entry_type=LedgerEntryType.DEPOSIT,
            amount=amount,
            balance_after=new_balance,
            reference_id=reference_id or f"dep-{int(time.time())}",
            idempotency_key=idempotency_key,
        )
        self._ledger.append(entry)
        return entry

    def record_usage_and_settle(
        self,
        event: MeteringEvent,
        cost_credits: Money,
        idempotency_key: str,
    ) -> LedgerEntry:
        for entry in self._ledger:
            if entry.tenant_id == event.tenant_id and entry.idempotency_key == idempotency_key:
                return entry

        current = self.get_wallet_balance(event.tenant_id)
        if current.amount < cost_credits.amount:
            raise ValueError(f"Insufficient credits for tenant {event.tenant_id}: {current} < {cost_credits}")

        new_balance = current - cost_credits
        self._wallets[event.tenant_id] = new_balance

        entry = LedgerEntry(
            entry_id=f"ledg-{uuid.uuid4().hex[:12]}",
            tenant_id=event.tenant_id,
            entry_type=LedgerEntryType.TASK_SETTLEMENT,
            amount=cost_credits,
            balance_after=new_balance,
            reference_id=event.task_id,
            idempotency_key=idempotency_key,
        )
        self._ledger.append(entry)
        return entry

    def reconcile_tenant_period(
        self,
        tenant_id: str,
        period: str,
        reported_bank_balance: Money,
    ) -> ReconciliationResult:
        current_balance = self.get_wallet_balance(tenant_id)
        discrepancy = current_balance - reported_bank_balance
        status = ReconciliationStatus.BALANCED if discrepancy.amount == Decimal("0.0000") else ReconciliationStatus.DISCREPANCY

        return ReconciliationResult(
            reconciliation_id=f"rec-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            period=period,
            status=status,
            ledger_balance=current_balance,
            bank_or_gateway_balance=reported_bank_balance,
            discrepancy=discrepancy,
        )
