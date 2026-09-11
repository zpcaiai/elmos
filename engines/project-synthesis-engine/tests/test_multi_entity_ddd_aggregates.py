"""Tests for Multi-Entity DDD Aggregates: Order, OrderItem, Payment, Shipping, and Money Invariants."""

from __future__ import annotations

from decimal import Decimal

import pytest

from elmos_project_synthesis.enterprise_order_aggregate import (
    DomainError,
    InvariantViolationError,
    Money,
    OrderAggregate,
    OrderStatus,
)


def test_money_value_object_precision_and_currency_guard():
    m1 = Money.of("100.50", "USD")
    m2 = Money.of("49.50", "USD")

    res = m1 + m2
    assert res.amount == Decimal("150.00")
    assert res.currency == "USD"

    # Currency mismatch guard
    eur = Money.of("50.00", "EUR")
    with pytest.raises(InvariantViolationError) as exc_info:
        _ = m1 + eur
    assert "Currency mismatch" in str(exc_info.value)


def test_order_aggregate_add_item_and_financial_balance():
    order = OrderAggregate.create(
        tenant_id="tenant-acme",
        reference="ORD-2026-001",
        customer_id="cust-enterprise-99",
        currency="USD",
    )
    assert order.status == OrderStatus.DRAFT
    assert len(order.items) == 0

    # Add items
    order.add_item(sku="SKU-PRO-01", product_name="Cloud Platform License", unit_price="500.00", quantity=2)
    order.add_item(sku="SKU-SUP-01", product_name="24/7 Enterprise Support", unit_price="200.00", quantity=1)

    assert len(order.items) == 2
    assert order.total_amount.amount == Decimal("1200.00")

    # Apply discount and tax
    order.apply_discount("100.00")
    order.apply_tax("88.00")

    # Invariant: net_amount == total - discount + tax (1200 - 100 + 88 = 1188.00)
    assert order.net_amount.amount == Decimal("1188.00")
    order.verify_invariants()


def test_order_lifecycle_state_machine():
    order = OrderAggregate.create(
        tenant_id="tenant-acme",
        reference="ORD-2026-002",
        customer_id="cust-enterprise-99",
    )

    # Submitting with 0 items fails
    with pytest.raises(DomainError) as exc_info:
        order.submit()
    assert "empty" in str(exc_info.value).lower()

    # Add item and submit
    order.add_item(sku="SKU-01", product_name="Widget", unit_price="100.00", quantity=1)
    order.submit()
    assert order.status == OrderStatus.SUBMITTED

    # Cannot fulfill before payment
    with pytest.raises(DomainError):
        order.fulfill(tracking_no="SF123", carrier="SF")

    # Pay order
    order.record_payment(payment_method="CORPORATE_WIRE", amount="100.00", transaction_ref="tx-wire-99")
    assert order.status == OrderStatus.PAID
    assert len(order.payments) == 1

    # Fulfill order
    order.fulfill(tracking_no="SF100998877", carrier="SF_EXPRESS")
    assert order.status == OrderStatus.FULFILLED
    assert order.shipping is not None
    assert order.shipping.tracking_no == "SF100998877"

    # Cannot cancel fulfilled order
    with pytest.raises(DomainError) as cancel_exc:
        order.cancel("Changed mind")
    assert "fulfilled" in str(cancel_exc.value).lower()


def test_order_item_modification_guard_after_submission():
    order = OrderAggregate.create(
        tenant_id="tenant-acme",
        reference="ORD-2026-003",
        customer_id="cust-enterprise-99",
    )
    order.add_item(sku="SKU-01", product_name="Widget", unit_price="50.00", quantity=2)
    order.submit()

    # Cannot add items once submitted
    with pytest.raises(DomainError) as exc_info:
        order.add_item(sku="SKU-02", product_name="Another Widget", unit_price="20.00", quantity=1)
    assert "draft" in str(exc_info.value).lower()
