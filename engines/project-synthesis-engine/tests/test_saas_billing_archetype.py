"""Unit and integration tests for Industrial SaaS Billing & Metered Usage Archetype."""

import datetime as dt
from decimal import Decimal

import pytest

from elmos_project_synthesis.domain_archetypes.saas_billing_archetype import (
    BillingInterval,
    InvoiceAggregate,
    InvoiceFinalizedError,
    InvoiceStatus,
    ProrationEngine,
    SubscriptionAggregate,
    SubscriptionPlanAggregate,
    SubscriptionStatus,
    TierBracket,
    TieredPricingCalculator,
    UsageAggregationType,
    UsageEvent,
    UsageMeterAggregate,
)


def test_tier_bracket_validation_and_graduated_pricing():
    brackets = [
        TierBracket(Decimal("0"), Decimal("100"), Decimal("0.10"), Decimal("0.00")),  # 0-100 @ $0.10
        TierBracket(Decimal("100"), Decimal("500"), Decimal("0.08"), Decimal("0.00")),  # 101-500 @ $0.08
        TierBracket(Decimal("500"), None, Decimal("0.05"), Decimal("10.00")),  # 500+ @ $0.05 + $10 flat
    ]

    calc = TieredPricingCalculator()

    # 50 units: 50 * 0.10 = $5.00
    p50 = calc.calculate_graduated_price(Decimal("50"), brackets)
    assert p50 == Decimal("5.00")

    # 250 units: (100 * 0.10) + (150 * 0.08) = 10.00 + 12.00 = $22.00
    p250 = calc.calculate_graduated_price(Decimal("250"), brackets)
    assert p250 == Decimal("22.00")

    # 600 units: (100 * 0.10) + (400 * 0.08) + (100 * 0.05) + 10.00 = 10 + 32 + 5 + 10 = $57.00
    p600 = calc.calculate_graduated_price(Decimal("600"), brackets)
    assert p600 == Decimal("57.00")


def test_usage_meter_deduplication_and_window_aggregation():
    meter = UsageMeterAggregate(
        meter_id="meter-api-calls",
        tenant_id="t-saas",
        subscription_id="sub-101",
        metric_name="api_calls",
        aggregation_type=UsageAggregationType.SUM,
    )

    t0 = dt.datetime.now(dt.UTC)
    ev1 = UsageEvent("e1", "t-saas", "sub-101", "api_calls", Decimal("10"), t0, "dedup-key-1")
    ev2 = UsageEvent("e2", "t-saas", "sub-101", "api_calls", Decimal("25"), t0 + dt.timedelta(minutes=1), "dedup-key-2")
    ev_dup = UsageEvent(
        "e3", "t-saas", "sub-101", "api_calls", Decimal("10"), t0 + dt.timedelta(minutes=2), "dedup-key-1"
    )

    assert meter.ingest_event(ev1) is True
    assert meter.ingest_event(ev2) is True
    assert meter.ingest_event(ev_dup) is False  # Duplicate rejected!

    total_usage = meter.calculate_window_usage(t0 - dt.timedelta(seconds=1), t0 + dt.timedelta(hours=1))
    assert total_usage == Decimal("35")


def test_subscription_state_machine_and_proration():
    plan_starter = SubscriptionPlanAggregate(
        "p-start", "STARTER", "Starter Plan", Decimal("100.00"), "USD", BillingInterval.MONTHLY
    )
    plan_pro = SubscriptionPlanAggregate("p-pro", "PRO", "Pro Plan", Decimal("300.00"), "USD", BillingInterval.MONTHLY)

    sub = SubscriptionAggregate(
        subscription_id="sub-abc",
        tenant_id="tenant-1",
        customer_id="cust-1",
        plan=plan_starter,
        status=SubscriptionStatus.ACTIVE,
    )

    # State transitions
    sub.mark_past_due()
    assert sub.status == SubscriptionStatus.PAST_DUE
    sub.activate()
    assert sub.status == SubscriptionStatus.ACTIVE

    # Proration calculation: 30 day month, changing on day 15
    now = dt.datetime.now(dt.UTC)
    t_start = now - dt.timedelta(days=15)
    t_end = now + dt.timedelta(days=15)

    credit, charge, net = ProrationEngine.calculate_proration_delta(
        old_plan_fee=plan_starter.base_fee,
        new_plan_fee=plan_pro.base_fee,
        period_start=t_start,
        period_end=t_end,
        change_timestamp=now,
    )

    # 50% remaining: credit = $50.00, charge = $150.00, net payable = $100.00
    assert credit.quantize(Decimal("1.00")) == Decimal("50.00")
    assert charge.quantize(Decimal("1.00")) == Decimal("150.00")
    assert net.quantize(Decimal("1.00")) == Decimal("100.00")


def test_invoice_aggregate_calculations_and_lifecycle():
    inv = InvoiceAggregate(
        invoice_id="inv-2026-001",
        tenant_id="tenant-saas",
        customer_id="cust-101",
        subscription_id="sub-101",
        invoice_number="INV-0001",
        currency="USD",
        tax_rate=Decimal("0.10"),  # 10% tax
    )

    inv.add_line("Pro Plan Monthly Base", Decimal("1"), Decimal("300.00"))
    inv.add_line("Extra API Calls Overage", Decimal("1000"), Decimal("0.05"))  # $50.00
    inv.add_line("Proration Credit", Decimal("1"), Decimal("-50.00"), is_proration=True)

    # Subtotal: 300 + 50 - 50 = $300.00
    assert inv.subtotal == Decimal("300.00")
    # Tax: 300 * 0.10 = $30.00
    assert inv.tax_amount == Decimal("30.00")
    # Total: $330.00
    assert inv.total_amount == Decimal("330.00")
    assert inv.balance_due == Decimal("330.00")

    inv.finalize()
    assert inv.status == InvoiceStatus.FINALIZED

    # Attempting to add line after finalization fails
    with pytest.raises(InvoiceFinalizedError):
        inv.add_line("Late Fee", Decimal("1"), Decimal("10.00"))

    # Record partial and full payments
    inv.record_payment(Decimal("200.00"), "tx-pay-1")
    assert inv.amount_paid == Decimal("200.00")
    assert inv.balance_due == Decimal("130.00")
    assert inv.status == InvoiceStatus.FINALIZED

    inv.record_payment(Decimal("130.00"), "tx-pay-2")
    assert inv.amount_paid == Decimal("330.00")
    assert inv.balance_due == Decimal("0.00")
    assert inv.status == InvoiceStatus.PAID
