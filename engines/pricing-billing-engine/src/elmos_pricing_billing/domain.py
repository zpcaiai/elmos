"""Domain models and value objects for the ELMOS pricing and billing engine.

All financial and metering computations use exact Decimal arithmetic and
immutable double-entry ledger semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
import enum
import hashlib
import json
import time
import uuid
from typing import Any, Mapping, Sequence


class Currency(str, enum.Enum):
    USD = "USD"
    EUR = "EUR"
    CNY = "CNY"
    CREDIT = "CREDIT"


class BillingPeriod(str, enum.Enum):
    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"
    TASK_ON_DEMAND = "TASK_ON_DEMAND"


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PAID = "PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    VOID = "VOID"


class LedgerEntryType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    PURCHASE = "PURCHASE"
    TASK_RESERVATION = "TASK_RESERVATION"
    TASK_SETTLEMENT = "TASK_SETTLEMENT"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"


class ReconciliationStatus(str, enum.Enum):
    BALANCED = "BALANCED"
    DISCREPANCY = "DISCREPANCY"
    PENDING_SETTLEMENT = "PENDING_SETTLEMENT"


class ContractError(ValueError):
    """Raised when a billing contract invariant is violated."""


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: Currency = Currency.USD

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        # Quantize to 4 decimal places for internal accounting
        quantized = self.amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
        object.__setattr__(self, "amount", quantized)

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ContractError(f"Currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ContractError(f"Currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> "Money":
        dec_factor = Decimal(str(factor))
        return Money(self.amount * dec_factor, self.currency)

    def __str__(self) -> str:
        return f"{self.amount:.4f} {self.currency.value}"


@dataclass(frozen=True)
class TenantScope:
    tenant_id: str
    organization_id: str
    project_id: str
    actor_id: str = "system"

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.organization_id:
            raise ContractError("tenant_id and organization_id are required")


@dataclass(frozen=True)
class PricingTier:
    tier_name: str
    unit_price: Money
    included_units: int
    overage_unit_price: Money


@dataclass(frozen=True)
class RateCard:
    card_id: str
    version: str
    model_input_token_rate: Money  # per 1k tokens
    model_output_token_rate: Money  # per 1k tokens
    runner_second_rate: Money
    storage_gb_month_rate: Money


@dataclass(frozen=True)
class PricingPlan:
    plan_id: str
    name: str
    billing_period: BillingPeriod
    base_fee: Money
    included_credits: Decimal
    rate_card: RateCard


@dataclass(frozen=True)
class MeteringEvent:
    event_id: str
    tenant_id: str
    project_id: str
    task_id: str
    model_alias: str
    prompt_tokens: int
    completion_tokens: int
    runner_seconds: float
    storage_bytes: int
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass(frozen=True)
class UsageRecord:
    record_id: str
    tenant_id: str
    project_id: str
    period: str  # YYYY-MM
    total_prompt_tokens: int
    total_completion_tokens: int
    total_runner_seconds: float
    total_cost: Money


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    tenant_id: str
    entry_type: LedgerEntryType
    amount: Money
    balance_after: Money
    reference_id: str
    idempotency_key: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass(frozen=True)
class QuotaLimit:
    tenant_id: str
    max_monthly_spend: Money
    current_spend: Money
    hard_stop_enabled: bool = True
    alert_threshold_pct: float = 80.0


@dataclass(frozen=True)
class EntitlementGrant:
    grant_id: str
    tenant_id: str
    feature_key: str
    enabled: bool
    max_concurrency: int
    valid_until: str


@dataclass(frozen=True)
class InvoiceLineItem:
    description: str
    quantity: Decimal
    unit_price: Money
    total: Money


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    tenant_id: str
    period: str
    status: InvoiceStatus
    lines: Sequence[InvoiceLineItem]
    subtotal: Money
    tax: Money
    total: Money
    issued_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass(frozen=True)
class CreditNote:
    note_id: str
    invoice_id: str
    tenant_id: str
    amount: Money
    reason: str
    issued_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass(frozen=True)
class ChargeItem:
    charge_id: str
    tenant_id: str
    amount: Money
    payment_method_ref: str
    status: str


@dataclass(frozen=True)
class BillingCycle:
    cycle_id: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class ReconciliationResult:
    reconciliation_id: str
    tenant_id: str
    period: str
    status: ReconciliationStatus
    ledger_balance: Money
    bank_or_gateway_balance: Money
    discrepancy: Money
    verified_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
