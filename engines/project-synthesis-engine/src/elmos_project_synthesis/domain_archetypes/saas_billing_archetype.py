"""Industrial SaaS Subscription & Metered Usage Billing Platform Archetype Engine.

Provides multi-cycle subscription lifecycles, tiered/graduated usage metering,
sub-cent precision proration calculation, and multi-currency invoice generation.
"""

from __future__ import annotations

import datetime as dt
import enum
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Any

# ==============================================================================
# 1. Enums and Value Objects
# ==============================================================================


class BillingInterval(enum.StrEnum):
    """Frequency of recurring subscription billing cycles."""

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class SubscriptionStatus(enum.StrEnum):
    """SaaS subscription lifecycle states."""

    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    PAUSED = "PAUSED"
    CANCELED = "CANCELED"
    UNPAID = "UNPAID"


class UsageAggregationType(enum.StrEnum):
    """Strategy for aggregating high-frequency usage events over a billing window."""

    SUM = "SUM"  # Total cumulative consumption (e.g. API requests, gigabytes transferred)
    MAX = "MAX"  # High-water peak mark (e.g. peak concurrent storage, peak memory)
    LAST = "LAST"  # Most recent gauge value at period close (e.g. active seat count)
    UNIQUE_COUNT = "UNIQUE_COUNT"  # Cardinality of unique identifiers (e.g. active daily unique users)


class PricingModel(enum.StrEnum):
    """Pricing strategy applied to plan base and usage components."""

    FLAT_FEE = "FLAT_FEE"
    PER_UNIT = "PER_UNIT"
    TIERED_VOLUME = "TIERED_VOLUME"  # Whole volume priced at single tier bracket
    TIERED_GRADUATED = "TIERED_GRADUATED"  # Graduated brackets (marginal tax bracket style)


class InvoiceStatus(enum.StrEnum):
    """Invoice lifecycle states conforming to enterprise billing requirements."""

    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"
    PAID = "PAID"
    VOID = "VOID"
    UNCOLLECTIBLE = "UNCOLLECTIBLE"


@dataclass(frozen=True)
class TierBracket:
    """Bracket specification for volume and graduated tiered pricing."""

    start_qty: Decimal
    end_qty: Decimal | None  # None represents unbounded infinity (last bracket)
    unit_price: Decimal
    flat_fee: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        if self.start_qty < Decimal("0"):
            raise ValueError("Bracket start_qty cannot be negative")
        if self.end_qty is not None and self.end_qty <= self.start_qty:
            raise ValueError(f"Bracket end_qty {self.end_qty} must exceed start_qty {self.start_qty}")


@dataclass(frozen=True)
class UsageEvent:
    """Raw immutable usage telemetry event ingested from microservices."""

    event_id: str
    tenant_id: str
    subscription_id: str
    metric_name: str
    quantity: Decimal
    timestamp: dt.datetime
    deduplication_key: str

    def __post_init__(self) -> None:
        if self.quantity < Decimal("0"):
            raise ValueError("Usage quantity cannot be negative")


# ==============================================================================
# 2. Aggregates and Invariants
# ==============================================================================


class BillingDomainError(Exception):
    """Base domain exception for SaaS billing operations."""

    pass


class InvalidSubscriptionTransitionError(BillingDomainError):
    """Raised on illegal state machine transitions."""

    pass


class InvoiceFinalizedError(BillingDomainError):
    """Raised when attempting to modify a finalized or paid invoice."""

    pass


@dataclass
class SubscriptionPlanAggregate:
    """SaaS subscription catalog plan definition."""

    plan_id: str
    code: str
    name: str
    base_fee: Decimal
    currency: str
    interval: BillingInterval
    included_units: dict[str, Decimal] = field(default_factory=dict)
    tier_brackets: dict[str, list[TierBracket]] = field(default_factory=dict)
    active: bool = True
    version: int = 1


@dataclass
class UsageMeterAggregate:
    """Aggregates incoming usage streams with deduplication windowing."""

    meter_id: str
    tenant_id: str
    subscription_id: str
    metric_name: str
    aggregation_type: UsageAggregationType
    processed_dedup_keys: set[str] = field(default_factory=set)
    events: list[UsageEvent] = field(default_factory=list)
    version: int = 1

    def ingest_event(self, event: UsageEvent) -> bool:
        """Idempotently ingest a usage event; returns True if accepted, False if duplicate."""
        if event.deduplication_key in self.processed_dedup_keys:
            return False

        self.processed_dedup_keys.add(event.deduplication_key)
        self.events.append(event)
        self.version += 1
        return True

    def calculate_window_usage(self, start_time: dt.datetime, end_time: dt.datetime) -> Decimal:
        """Compute the billable metric aggregation within the billing cycle window."""
        window_events = [e for e in self.events if start_time <= e.timestamp <= end_time]
        if not window_events:
            return Decimal("0")

        if self.aggregation_type == UsageAggregationType.SUM:
            return sum((e.quantity for e in window_events), Decimal("0"))
        elif self.aggregation_type == UsageAggregationType.MAX:
            return max(e.quantity for e in window_events)
        elif self.aggregation_type == UsageAggregationType.LAST:
            sorted_events = sorted(window_events, key=lambda e: e.timestamp)
            return sorted_events[-1].quantity
        elif self.aggregation_type == UsageAggregationType.UNIQUE_COUNT:
            # Assumes event_id or dedup_key reflects identity
            return Decimal(len({e.deduplication_key for e in window_events}))

        return Decimal("0")


@dataclass
class SubscriptionAggregate:
    """Core tenant subscription aggregate root."""

    subscription_id: str
    tenant_id: str
    customer_id: str
    plan: SubscriptionPlanAggregate
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    current_period_start: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    current_period_end: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC) + dt.timedelta(days=30))
    cancel_at_period_end: bool = False
    active_seats: int = 1
    version: int = 1
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    def activate_trial(self, trial_days: int = 14) -> None:
        self.status = SubscriptionStatus.TRIALING
        self.current_period_end = self.current_period_start + dt.timedelta(days=trial_days)
        self.version += 1

    def activate(self) -> None:
        if self.status in (SubscriptionStatus.CANCELED,):
            raise InvalidSubscriptionTransitionError(f"Cannot reactivate canceled subscription {self.subscription_id}")
        self.status = SubscriptionStatus.ACTIVE
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def mark_past_due(self) -> None:
        if self.status != SubscriptionStatus.ACTIVE:
            raise InvalidSubscriptionTransitionError(f"Cannot mark past due from {self.status}")
        self.status = SubscriptionStatus.PAST_DUE
        self.version += 1

    def cancel_immediately(self) -> None:
        self.status = SubscriptionStatus.CANCELED
        self.version += 1
        self.updated_at = dt.datetime.now(dt.UTC)

    def set_cancel_at_period_end(self, cancel: bool) -> None:
        self.cancel_at_period_end = cancel
        self.version += 1


@dataclass
class InvoiceLineItem:
    """Detailed debit or credit item on a customer invoice."""

    line_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    currency: str
    is_proration: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvoiceAggregate:
    """Customer billing invoice aggregate root."""

    invoice_id: str
    tenant_id: str
    customer_id: str
    subscription_id: str
    invoice_number: str
    currency: str
    status: InvoiceStatus = InvoiceStatus.DRAFT
    due_date: dt.date = field(default_factory=lambda: dt.date.today() + dt.timedelta(days=14))
    line_items: list[InvoiceLineItem] = field(default_factory=list)
    tax_rate: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    amount_paid: Decimal = Decimal("0.00")
    version: int = 1
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    finalized_at: dt.datetime | None = None

    def add_line(
        self,
        description: str,
        quantity: Decimal,
        unit_price: Decimal,
        is_proration: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> InvoiceLineItem:
        if self.status != InvoiceStatus.DRAFT:
            raise InvoiceFinalizedError(f"Cannot add lines to invoice in status {self.status}")

        total_amount = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line = InvoiceLineItem(
            line_id=f"{self.invoice_id}-L{len(self.line_items) + 1:03d}",
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            amount=total_amount,
            currency=self.currency,
            is_proration=is_proration,
            metadata=metadata or {},
        )
        self.line_items.append(line)
        self.version += 1
        return line

    @property
    def subtotal(self) -> Decimal:
        return sum((item.amount for item in self.line_items), Decimal("0.00"))

    @property
    def tax_amount(self) -> Decimal:
        taxable_base = max(Decimal("0.00"), self.subtotal - self.discount_amount)
        return (taxable_base * self.tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def total_amount(self) -> Decimal:
        return max(Decimal("0.00"), self.subtotal - self.discount_amount + self.tax_amount)

    @property
    def balance_due(self) -> Decimal:
        return max(Decimal("0.00"), self.total_amount - self.amount_paid)

    def finalize(self) -> None:
        if self.status != InvoiceStatus.DRAFT:
            raise InvoiceFinalizedError(f"Invoice already finalized (current: {self.status})")
        if not self.line_items:
            raise BillingDomainError("Cannot finalize empty invoice")

        self.status = InvoiceStatus.FINALIZED
        self.finalized_at = dt.datetime.now(dt.UTC)
        self.version += 1

    def record_payment(self, payment_amount: Decimal, transaction_id: str) -> None:
        if self.status not in (InvoiceStatus.FINALIZED, InvoiceStatus.DRAFT):
            raise BillingDomainError(f"Cannot apply payment to invoice in status {self.status}")

        self.amount_paid += payment_amount
        if self.balance_due == Decimal("0.00"):
            self.status = InvoiceStatus.PAID
        self.version += 1


# ==============================================================================
# 3. Domain Services: Proration Engine & Graduated Pricing
# ==============================================================================


class ProrationEngine:
    """Calculates exact sub-cent proration credits and charges for mid-cycle plan changes."""

    @staticmethod
    def calculate_proration_delta(
        old_plan_fee: Decimal,
        new_plan_fee: Decimal,
        period_start: dt.datetime,
        period_end: dt.datetime,
        change_timestamp: dt.datetime,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Returns: (unused_old_credit, new_charge_remaining, net_adjustment)."""
        total_duration = (period_end - period_start).total_seconds()
        remaining_duration = (period_end - change_timestamp).total_seconds()

        if total_duration <= 0 or remaining_duration <= 0:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

        ratio = Decimal(str(remaining_duration)) / Decimal(str(total_duration))

        unused_old_credit = (old_plan_fee * ratio).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
        new_charge_remaining = (new_plan_fee * ratio).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
        net_adjustment = (new_charge_remaining - unused_old_credit).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        return unused_old_credit, new_charge_remaining, net_adjustment


class TieredPricingCalculator:
    """Computes volume and graduated tier price curves."""

    @staticmethod
    def calculate_graduated_price(units: Decimal, brackets: Sequence[TierBracket]) -> Decimal:
        """Calculate total price across progressive marginal brackets."""
        if units <= Decimal("0"):
            return Decimal("0.00")

        total = Decimal("0.00")
        for bracket in brackets:
            if units <= bracket.start_qty:
                continue

            bracket_top = bracket.end_qty if bracket.end_qty is not None else units
            billable_in_bracket = min(units, bracket_top) - bracket.start_qty

            if billable_in_bracket > Decimal("0"):
                total += (billable_in_bracket * bracket.unit_price) + bracket.flat_fee

            if bracket.end_qty is not None and units <= bracket.end_qty:
                break

        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
