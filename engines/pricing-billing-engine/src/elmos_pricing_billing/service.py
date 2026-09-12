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
    ContractError,
    CreditNote,
    Currency,
    EntitlementGrant,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LedgerEntry,
    LedgerEntryType,
    MeteringEvent,
    Money,
    QuotaLimit,
    RateCard,
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
        self._idempotency_index: dict[tuple[str, str], LedgerEntry] = {}
        self._quotas: dict[str, QuotaLimit] = {}
        self._invoices: dict[str, Invoice] = {}
        self._credit_notes: dict[str, CreditNote] = {}
        self._entitlements: dict[tuple[str, str], EntitlementGrant] = {}
        self._metering_events: list[MeteringEvent] = []


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
        # Fast O(1) check for idempotent duplicate
        key = (tenant_id, idempotency_key)
        if key in self._idempotency_index:
            return self._idempotency_index[key]

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
        self._idempotency_index[key] = entry
        return entry

    def record_usage_and_settle(
        self,
        event: MeteringEvent,
        cost_credits: Money,
        idempotency_key: str,
    ) -> LedgerEntry:
        key = (event.tenant_id, idempotency_key)
        if key in self._idempotency_index:
            return self._idempotency_index[key]

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
        self._idempotency_index[key] = entry
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

    def set_quota(self, quota: QuotaLimit) -> None:
        self._quotas[quota.tenant_id] = quota

    def get_quota(self, tenant_id: str) -> QuotaLimit | None:
        return self._quotas.get(tenant_id)

    def check_budget_guard(self, tenant_id: str, estimated_cost: Money) -> tuple[bool, str, Money]:
        quota = self._quotas.get(tenant_id)
        if quota is None:
            return True, "NO_QUOTA_DEFINED", estimated_cost

        new_total_spend = quota.current_spend + estimated_cost
        remaining = quota.max_monthly_spend - quota.current_spend

        if new_total_spend > quota.max_monthly_spend:
            if quota.hard_stop_enabled:
                return False, "QUOTA_EXCEEDED_HARD_STOP", remaining
            return True, "QUOTA_EXCEEDED_SOFT_WARNING", remaining

        threshold_amount = quota.max_monthly_spend * (Decimal(str(quota.alert_threshold_pct)) / Decimal("100"))
        if new_total_spend >= threshold_amount:
            return True, "ALERT_THRESHOLD_REACHED", remaining

        return True, "WITHIN_BUDGET", remaining

    def issue_invoice(
        self,
        tenant_id: str,
        period: str,
        lines: Sequence[InvoiceLineItem],
        tax_rate: Decimal = Decimal("0.0"),
    ) -> Invoice:
        if not lines:
            raise ValueError("Invoice must have at least one line item")

        currency = lines[0].unit_price.currency
        subtotal = Money(Decimal("0.0000"), currency)
        for line in lines:
            if line.total.currency != currency:
                raise ContractError(f"Line currency {line.total.currency} does not match invoice currency {currency}")
            subtotal = subtotal + line.total

        tax = subtotal * tax_rate
        total = subtotal + tax

        invoice_id = f"inv-{uuid.uuid4().hex[:12]}"
        invoice = Invoice(
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            period=period,
            status=InvoiceStatus.ISSUED,
            lines=lines,
            subtotal=subtotal,
            tax=tax,
            total=total,
        )
        self._invoices[invoice_id] = invoice
        return invoice

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        return self._invoices.get(invoice_id)

    def pay_invoice(self, invoice_id: str) -> Invoice:
        inv = self._invoices.get(invoice_id)
        if inv is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if inv.status in (InvoiceStatus.PAID, InvoiceStatus.VOID):
            raise ValueError(f"Cannot pay invoice with status {inv.status}")

        paid_inv = Invoice(
            invoice_id=inv.invoice_id,
            tenant_id=inv.tenant_id,
            period=inv.period,
            status=InvoiceStatus.PAID,
            lines=inv.lines,
            subtotal=inv.subtotal,
            tax=inv.tax,
            total=inv.total,
            issued_at=inv.issued_at,
        )
        self._invoices[invoice_id] = paid_inv
        return paid_inv

    def void_invoice(self, invoice_id: str) -> Invoice:
        inv = self._invoices.get(invoice_id)
        if inv is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if inv.status == InvoiceStatus.PAID:
            raise ValueError("Cannot void a paid invoice (issue credit note instead)")

        voided = Invoice(
            invoice_id=inv.invoice_id,
            tenant_id=inv.tenant_id,
            period=inv.period,
            status=InvoiceStatus.VOID,
            lines=inv.lines,
            subtotal=inv.subtotal,
            tax=inv.tax,
            total=inv.total,
            issued_at=inv.issued_at,
        )
        self._invoices[invoice_id] = voided
        return voided

    def issue_credit_note(self, invoice_id: str, amount: Money, reason: str) -> CreditNote:
        inv = self._invoices.get(invoice_id)
        if inv is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if amount.currency != inv.total.currency:
            raise ContractError(f"Credit note currency {amount.currency} does not match invoice {inv.total.currency}")
        if amount > inv.total:
            raise ValueError(f"Credit note amount {amount} exceeds invoice total {inv.total}")

        note_id = f"cn-{uuid.uuid4().hex[:12]}"
        note = CreditNote(
            note_id=note_id,
            invoice_id=invoice_id,
            tenant_id=inv.tenant_id,
            amount=amount,
            reason=reason,
        )
        self._credit_notes[note_id] = note
        return note

    def grant_entitlement(self, grant: EntitlementGrant) -> None:
        self._entitlements[(grant.tenant_id, grant.feature_key)] = grant

    def check_entitlement(self, tenant_id: str, feature_key: str) -> bool:
        grant = self._entitlements.get((tenant_id, feature_key))
        if grant is None:
            return False
        return grant.enabled

    def record_metering_event(self, event: MeteringEvent) -> None:
        self._metering_events.append(event)

    def aggregate_usage(self, tenant_id: str, period: str, rate_card: RateCard | None = None) -> UsageRecord:
        matching = [e for e in self._metering_events if e.tenant_id == tenant_id]
        total_prompt = sum(e.prompt_tokens for e in matching)
        total_completion = sum(e.completion_tokens for e in matching)
        total_seconds = sum(e.runner_seconds for e in matching)

        total_cost = Money(Decimal("0.0000"), Currency.USD)
        if rate_card:
            prompt_cost = rate_card.model_input_token_rate * (Decimal(str(total_prompt)) / Decimal("1000"))
            completion_cost = rate_card.model_output_token_rate * (Decimal(str(total_completion)) / Decimal("1000"))
            runner_cost = rate_card.runner_second_rate * Decimal(str(total_seconds))
            total_cost = prompt_cost + completion_cost + runner_cost

        return UsageRecord(
            record_id=f"use-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            project_id="all",
            period=period,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_runner_seconds=total_seconds,
            total_cost=total_cost,
        )

    def calculate_margin(self, revenue: Money, direct_costs: Money) -> dict[str, Any]:
        if revenue.currency != direct_costs.currency:
            raise ContractError(f"Currency mismatch: revenue {revenue.currency} vs costs {direct_costs.currency}")

        gross_profit = revenue - direct_costs
        if revenue.amount == Decimal("0"):
            margin_pct = Decimal("0.0")
        else:
            margin_pct = (gross_profit.amount / revenue.amount) * Decimal("100")

        return {
            "revenue": str(revenue),
            "direct_costs": str(direct_costs),
            "gross_profit": str(gross_profit),
            "gross_margin_pct": float(margin_pct.quantize(Decimal("0.01"))),
            "is_profitable": gross_profit.amount > Decimal("0"),
        }

