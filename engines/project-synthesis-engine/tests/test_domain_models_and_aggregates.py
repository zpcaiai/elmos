"""Tests for DDD Domain Models, Value Objects, Aggregates, and Invariants.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import pytest

from elmos_project_synthesis.domain_models import (
    Address,
    AggregateRoot,
    DateRange,
    DomainEvent,
    DomainInvariantViolationError,
    Email,
    GeoLocation,
    InvariantEvaluator,
    InvariantRuleSpec,
    Money,
    Quantity,
)


def test_money_value_object_operations():
    m1 = Money(amount=Decimal("100.50"), currency="USD")
    m2 = Money(amount=Decimal("49.50"), currency="USD")

    res = m1.add(m2)
    assert res.amount == Decimal("150.00")
    assert res.currency == "USD"

    sub = m1.subtract(m2)
    assert sub.amount == Decimal("51.00")

    # Invariant: Frozen / Immutability
    with pytest.raises(Exception):
        m1.amount = Decimal("200.00")  # type: ignore

    # Invariant: Currency mismatch raises DomainInvariantViolationError
    m_eur = Money(amount=Decimal("10.00"), currency="EUR")
    with pytest.raises(DomainInvariantViolationError, match="different currencies"):
        m1.add(m_eur)

    # Invariant: Invalid currency code raises DomainInvariantViolationError
    with pytest.raises(DomainInvariantViolationError, match="currency"):
        Money(amount=Decimal("10.00"), currency="INVALID")

    # Invariant: Insufficient funds
    with pytest.raises(DomainInvariantViolationError, match="Insufficient funds"):
        m2.subtract(m1)


def test_address_and_geolocation_value_objects():
    addr = Address(
        street="100 Enterprise Way",
        city="Shanghai",
        state_province="SH",
        postal_code="200000",
        country="CN",
    )
    assert addr.street == "100 Enterprise Way"
    assert addr.country == "CN"

    geo = GeoLocation(latitude=31.2304, longitude=121.4737)
    assert geo.latitude == 31.2304

    with pytest.raises(DomainInvariantViolationError, match="outside valid range"):
        GeoLocation(latitude=95.0, longitude=0.0)

    with pytest.raises(DomainInvariantViolationError, match="outside valid range"):
        GeoLocation(latitude=0.0, longitude=190.0)


def test_email_quantity_daterange_value_objects():
    valid_email = Email(value="tech-lead@enterprise.org")
    assert valid_email.value == "tech-lead@enterprise.org"

    with pytest.raises(DomainInvariantViolationError, match="Invalid email format"):
        Email(value="not-an-email")

    q1 = Quantity(value=Decimal("5.5"), unit="kg")
    q2 = Quantity(value=Decimal("2.5"), unit="kg")
    assert q1.value == Decimal("5.5")
    assert q2.value == Decimal("2.5")

    start = dt.date(2026, 1, 1)
    end = dt.date(2026, 1, 10)
    dr = DateRange(start_date=start, end_date=end)
    assert dr.contains(dt.date(2026, 1, 5)) is True
    assert dr.contains(dt.date(2026, 1, 15)) is False

    with pytest.raises(DomainInvariantViolationError, match="cannot be after"):
        DateRange(start_date=end, end_date=start)


class SampleOrderAggregate(AggregateRoot):
    def __init__(self, order_id: str, tenant_id: str = "default", total_amount: Decimal = Decimal("0")):
        super().__init__(aggregate_id=order_id, tenant_id=tenant_id)
        self.total_amount = total_amount
        self.status = "DRAFT"


def test_aggregate_root_lifecycle_and_domain_events():
    order = SampleOrderAggregate(
        order_id="ord-001",
        tenant_id="tenant-acme",
        total_amount=Decimal("999.00"),
    )
    assert order.id == "ord-001"
    assert order.tenant_id == "tenant-acme"
    assert order.version == 1
    assert order.has_uncommitted_events() is False

    event = order.record_event(
        event_type="order.created",
        payload={"total": str(order.total_amount)},
    )
    assert order.has_uncommitted_events() is True
    assert event.aggregate_id == "ord-001"
    assert event.event_type == "order.created"
    assert event.payload["total"] == "999.00"

    # Poll uncommitted events
    polled = order.poll_uncommitted_events()
    assert len(polled) == 1
    assert order.has_uncommitted_events() is False


def test_invariant_evaluator_rules():
    rule_min = InvariantRuleSpec(
        rule_id="INV-001",
        description="Minimum order total check",
        target_field="total_amount",
        operator="gte",
        expected_value=Decimal("0.00"),
        error_message="Total amount must be non-negative",
    )
    rule_regex = InvariantRuleSpec(
        rule_id="INV-002",
        description="Customer ID format",
        target_field="customer_id",
        operator="regex",
        expected_value=r"^cust-[0-9]+$",
        error_message="Customer ID must follow format 'cust-###'",
    )

    # Valid evaluation
    order_ok = {"customer_id": "cust-1234", "total_amount": Decimal("100.00")}
    InvariantEvaluator.evaluate(rule_min, order_ok, aggregate_id="ord-1")
    InvariantEvaluator.evaluate(rule_regex, order_ok, aggregate_id="ord-1")

    # Violation: negative amount
    order_bad_amount = {"customer_id": "cust-1234", "total_amount": Decimal("-10.00")}
    with pytest.raises(DomainInvariantViolationError) as exc_info:
        InvariantEvaluator.evaluate(rule_min, order_bad_amount, aggregate_id="ord-2")
    assert exc_info.value.rule_id == "INV-001"
    assert "Total amount must be non-negative" in str(exc_info.value)

    # Violation: regex mismatch
    order_bad_cust = {"customer_id": "bad-customer", "total_amount": Decimal("10.00")}
    with pytest.raises(DomainInvariantViolationError) as exc_info:
        InvariantEvaluator.evaluate(rule_regex, order_bad_cust, aggregate_id="ord-3")
    assert exc_info.value.rule_id == "INV-002"
