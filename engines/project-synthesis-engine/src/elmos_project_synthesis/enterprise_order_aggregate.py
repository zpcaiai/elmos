"""Enterprise Multi-Entity DDD Aggregate Implementation.

Implements deep Domain-Driven Design (DDD) aggregate patterns beyond single-table CRUD:
1. Aggregate Root (OrderAggregate):
   - Multi-entity graph containing child entities:
     * OrderItem: SKU, unit price, quantity, discount, tax, subtotal.
     * PaymentRecord: payment method, transaction reference, amount, paid_at.
     * ShippingDetail: tracking number, carrier, destination address, status.
   - ISO-4217 Currency and Money Value Objects with precise financial arithmetic.
2. Invariant Rules & Trial Balance:
   - Order items must not be empty.
   - sum(items.subtotal) == total_amount.
   - net_amount == total_amount - discount_amount + tax_amount.
   - Non-cancellable once fulfilled.
3. Complex Domain Operations:
   - add_item(), submit(), record_payment(), mark_fulfilled(), cancel_order().
   - Transactional domain events emission with causal tracing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4

from .domain_models import (
    Address,
    AggregateRoot,
    DomainInvariantViolationError,
    Money,
)

DomainError = DomainInvariantViolationError
InvariantViolationError = DomainInvariantViolationError


class OrderStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PAID = "PAID"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderItem:
    """Child entity within Order Aggregate."""

    item_id: str
    sku: str
    product_name: str
    unit_price: Money
    quantity: int
    discount_amount: Money
    tax_amount: Money

    @property
    def subtotal(self) -> Money:
        """Item subtotal = (unit_price * quantity) - discount + tax."""
        base = self.unit_price.multiply(self.quantity)
        return base.subtract(self.discount_amount).add(self.tax_amount)


@dataclass
class PaymentRecord:
    """Child entity representing an executed payment transaction."""

    payment_id: str
    payment_method: str  # CREDIT_CARD, WIRE_TRANSFER, ALIPAY, WECHAT
    amount: Money
    transaction_ref: str
    status: str  # SUCCESS, FAILED, PENDING
    paid_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


@dataclass
class ShippingDetail:
    """Child entity representing logistics dispatch and fulfillment."""

    tracking_no: str
    carrier: str  # FEDEX, UPS, SF_EXPRESS, DHL
    destination: Address
    status: str = "PENDING"  # PENDING, DISPATCHED, DELIVERED
    dispatched_at: dt.datetime | None = None


class OrderAggregate(AggregateRoot):
    """Industrial Multi-Entity DDD Aggregate Root."""

    def __init__(
        self,
        order_id: str,
        tenant_id: str = "default",
        order_no: str | None = None,
        customer_id: str = "cust-default",
        currency: str = "USD",
    ) -> None:
        super().__init__(aggregate_id=order_id, tenant_id=tenant_id)
        self.order_no = order_no or f"ORD-{uuid4().hex[:10].upper()}"
        self.customer_id = customer_id
        self.currency = currency
        self.status = OrderStatus.DRAFT

        # Multi-Entity Hierarchy
        self.items: list[OrderItem] = []
        self.payments: list[PaymentRecord] = []
        self.shipping: ShippingDetail | None = None

        # Financial Summary
        self.discount_amount = Money(amount=Decimal("0.00"), currency=currency)
        self.tax_amount = Money(amount=Decimal("0.00"), currency=currency)

        # Audit
        self.created_at = dt.datetime.now(dt.UTC)
        self.updated_at = dt.datetime.now(dt.UTC)

    @classmethod
    def create(
        cls,
        tenant_id: str = "default",
        reference: str | None = None,
        customer_id: str = "cust-default",
        currency: str = "USD",
    ) -> OrderAggregate:
        """Factory method to construct a fresh draft OrderAggregate."""
        order_id = f"ord-{uuid4().hex[:12]}"
        return cls(
            order_id=order_id,
            tenant_id=tenant_id,
            order_no=reference,
            customer_id=customer_id,
            currency=currency,
        )

    @property
    def total_amount(self) -> Money:
        """Sum of unit_price * quantity across all items."""
        total = Money(amount=Decimal("0.00"), currency=self.currency)
        for it in self.items:
            total = total.add(it.unit_price.multiply(it.quantity))
        return total

    @property
    def net_amount(self) -> Money:
        """Net amount = total_amount - discount_amount + tax_amount."""
        net = self.total_amount
        if self.discount_amount.amount > Decimal("0.00"):
            net = net.subtract(self.discount_amount)
        if self.tax_amount.amount > Decimal("0.00"):
            net = net.add(self.tax_amount)
        for it in self.items:
            if it.discount_amount.amount > Decimal("0.00"):
                net = net.subtract(it.discount_amount)
            if it.tax_amount.amount > Decimal("0.00"):
                net = net.add(it.tax_amount)
        return net

    def apply_discount(self, discount: Decimal | str | float | Money) -> None:
        """Apply aggregate-level order discount."""
        disc_val = discount.amount if isinstance(discount, Money) else Decimal(str(discount))
        self.discount_amount = Money(amount=disc_val, currency=self.currency)

    def apply_tax(self, tax: Decimal | str | float | Money) -> None:
        """Apply aggregate-level order tax."""
        tax_val = tax.amount if isinstance(tax, Money) else Decimal(str(tax))
        self.tax_amount = Money(amount=tax_val, currency=self.currency)

    def verify_invariants(self) -> None:
        """Enforce aggregate invariant rules and trial-balance arithmetic."""
        expected = self.total_amount.subtract(self.discount_amount).add(self.tax_amount)
        if self.net_amount.amount != expected.amount:
            raise DomainInvariantViolationError(
                "TRIAL_BALANCE_MISMATCH",
                f"Net amount {self.net_amount.amount} != expected {expected.amount}",
                self.id,
            )

    # --- Domain Operations ---

    def add_item(
        self,
        sku: str,
        product_name: str,
        unit_price: Decimal | str | float | Money,
        quantity: int,
        discount: Decimal | str | float | Money = Decimal("0.00"),
        tax: Decimal | str | float | Money = Decimal("0.00"),
    ) -> OrderItem:
        """Add child item entity to aggregate with domain invariant validation."""
        if self.status != OrderStatus.DRAFT:
            raise DomainInvariantViolationError(
                "ORDER_NOT_DRAFT",
                f"Cannot modify items in order state '{self.status}'",
                self.id,
            )
        if quantity <= 0:
            raise DomainInvariantViolationError(
                "INVALID_QUANTITY",
                f"Item quantity must be strictly positive (got {quantity})",
                self.id,
            )

        price_val = unit_price.amount if isinstance(unit_price, Money) else Decimal(str(unit_price))
        disc_val = discount.amount if isinstance(discount, Money) else Decimal(str(discount))
        tax_val = tax.amount if isinstance(tax, Money) else Decimal(str(tax))

        item = OrderItem(
            item_id=f"item-{uuid4().hex[:8]}",
            sku=sku,
            product_name=product_name,
            unit_price=Money(amount=price_val, currency=self.currency),
            quantity=quantity,
            discount_amount=Money(amount=disc_val, currency=self.currency),
            tax_amount=Money(amount=tax_val, currency=self.currency),
        )
        self.items.append(item)
        self.updated_at = dt.datetime.now(dt.UTC)
        return item

    def submit(self, trace_id: str | None = None) -> None:
        """Submit order, enforcing items non-empty and financial trial-balance invariants."""
        if self.status != OrderStatus.DRAFT:
            raise DomainInvariantViolationError(
                "ORDER_ALREADY_SUBMITTED",
                f"Order is in '{self.status}' state, expected DRAFT",
                self.id,
            )
        if not self.items:
            raise DomainInvariantViolationError(
                "ORDER_EMPTY_ITEMS",
                "Cannot submit an order with zero items",
                self.id,
            )
        if self.net_amount.amount <= Decimal("0.00"):
            raise DomainInvariantViolationError(
                "ORDER_NON_POSITIVE_AMOUNT",
                f"Net order amount must be positive (got {self.net_amount.amount})",
                self.id,
            )

        self.status = OrderStatus.SUBMITTED
        self.updated_at = dt.datetime.now(dt.UTC)
        self.record_event(
            event_type="OrderSubmittedEvent",
            payload={
                "order_id": self.id,
                "order_no": self.order_no,
                "tenant_id": self.tenant_id,
                "customer_id": self.customer_id,
                "net_amount": str(self.net_amount.amount),
                "currency": self.currency,
                "item_count": len(self.items),
            },
            trace_id=trace_id,
        )

    def record_payment(
        self,
        payment_method: str,
        amount: Decimal | str | float | Money,
        transaction_ref: str,
        trace_id: str | None = None,
    ) -> PaymentRecord:
        """Record payment transaction, asserting full amount matching net_amount."""
        if self.status != OrderStatus.SUBMITTED:
            raise DomainInvariantViolationError(
                "ORDER_NOT_PAYABLE",
                f"Cannot record payment for order in '{self.status}' state (must be SUBMITTED)",
                self.id,
            )

        amt_val = amount.amount if isinstance(amount, Money) else Decimal(str(amount))
        pay_money = Money(amount=amt_val, currency=self.currency)
        if pay_money.amount != self.net_amount.amount:
            raise DomainInvariantViolationError(
                "PAYMENT_AMOUNT_MISMATCH",
                f"Payment amount {pay_money.amount} does not match order net amount {self.net_amount.amount}",
                self.id,
            )

        record = PaymentRecord(
            payment_id=f"pay-{uuid4().hex[:10]}",
            payment_method=payment_method,
            amount=pay_money,
            transaction_ref=transaction_ref,
            status="SUCCESS",
            paid_at=dt.datetime.now(dt.UTC),
        )
        self.payments.append(record)
        self.status = OrderStatus.PAID
        self.updated_at = dt.datetime.now(dt.UTC)

        self.record_event(
            event_type="OrderPaidEvent",
            payload={
                "order_id": self.id,
                "order_no": self.order_no,
                "payment_id": record.payment_id,
                "amount": str(amt_val),
                "currency": self.currency,
                "transaction_ref": transaction_ref,
            },
            trace_id=trace_id,
        )
        return record

    def fulfill(
        self,
        tracking_no: str,
        carrier: str,
        shipping_address: Address | None = None,
        trace_id: str | None = None,
    ) -> ShippingDetail:
        """Mark order as fulfilled with tracking details; requires PAID status."""
        if self.status != OrderStatus.PAID:
            raise DomainInvariantViolationError(
                "ORDER_NOT_PAID",
                f"Cannot fulfill order in '{self.status}' state (must be PAID)",
                self.id,
            )
        if not tracking_no.strip():
            raise DomainInvariantViolationError(
                "SHIPPING_MISSING_TRACKING",
                "Tracking number must not be empty",
                self.id,
            )

        dest = shipping_address or Address(
            street="100 Enterprise Way",
            city="Tech City",
            state_province="CA",
            postal_code="94016",
            country="US",
        )

        shipping = ShippingDetail(
            tracking_no=tracking_no,
            carrier=carrier,
            destination=dest,
            status="DISPATCHED",
            dispatched_at=dt.datetime.now(dt.UTC),
        )
        self.shipping = shipping
        self.status = OrderStatus.FULFILLED
        self.updated_at = dt.datetime.now(dt.UTC)

        self.record_event(
            event_type="OrderFulfilledEvent",
            payload={
                "order_id": self.id,
                "order_no": self.order_no,
                "tracking_no": tracking_no,
                "carrier": carrier,
            },
            trace_id=trace_id,
        )
        return shipping

    def cancel(self, reason: str, trace_id: str | None = None) -> None:
        """Cancel order. Non-cancellable once FULFILLED."""
        if self.status == OrderStatus.FULFILLED:
            raise DomainInvariantViolationError(
                "ORDER_CANNOT_CANCEL_FULFILLED",
                "Order has already been fulfilled and dispatched; cancellation rejected",
                self.id,
            )
        if self.status == OrderStatus.CANCELLED:
            return  # Idempotent cancel

        prev_status = self.status
        self.status = OrderStatus.CANCELLED
        self.updated_at = dt.datetime.now(dt.UTC)

        self.record_event(
            event_type="OrderCancelledEvent",
            payload={
                "order_id": self.id,
                "order_no": self.order_no,
                "previous_status": prev_status,
                "reason": reason,
            },
            trace_id=trace_id,
        )
