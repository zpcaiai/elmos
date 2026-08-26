from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.ledger import LedgerService
from elmos_pricing_billing.models import LedgerKind
from elmos_pricing_billing.money import Money

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_ledger_reserve_partial_capture_release_credit_refund_and_rebuild() -> None:
    ledger = LedgerService()
    ledger.opening_balance(
        tenant_id="tenant-a",
        money=Money("USD", 1_000),
        idempotency_key="opening",
        reference="opening",
        occurred_at=NOW,
    )
    reserve = ledger.reserve(
        tenant_id="tenant-a",
        money=Money("USD", 600),
        idempotency_key="reserve",
        reference="quote",
        occurred_at=NOW,
    )
    ledger.capture(
        tenant_id="tenant-a",
        money=Money("USD", 250),
        idempotency_key="capture",
        reference="usage",
        occurred_at=NOW,
    )
    ledger.release(
        tenant_id="tenant-a",
        money=Money("USD", 350),
        idempotency_key="release",
        reference="quote-close",
        occurred_at=NOW,
    )
    credit = ledger.credit(
        tenant_id="tenant-a",
        money=Money("USD", 100),
        idempotency_key="credit",
        reference="promo",
        occurred_at=NOW,
    )
    refund = ledger.refund(
        tenant_id="tenant-a",
        money=Money("USD", 50),
        idempotency_key="refund",
        reference="payment",
        occurred_at=NOW,
    )

    balance = ledger.balance(tenant_id="tenant-a", currency="USD")
    assert balance.available_minor == 900
    assert balance.reserved_minor == 0
    assert balance.captured_minor == 250
    assert balance.transaction_count == 6
    assert ledger.verify_rebuild(tenant_id="tenant-a", currency="USD")
    assert reserve.kind is LedgerKind.RESERVE
    assert all(
        sum(posting.money.minor for posting in transaction.postings if posting.side == "DEBIT")
        == sum(posting.money.minor for posting in transaction.postings if posting.side == "CREDIT")
        for transaction in ledger.transactions(tenant_id="tenant-a")
    )

    ledger.reverse(
        tenant_id="tenant-a",
        transaction_id=credit.transaction_id,
        idempotency_key="reverse-credit",
        reference="promo-reversal",
        occurred_at=NOW,
    )
    ledger.reverse(
        tenant_id="tenant-a",
        transaction_id=refund.transaction_id,
        idempotency_key="reverse-refund",
        reference="refund-reversal",
        occurred_at=NOW,
    )
    assert ledger.balance(tenant_id="tenant-a", currency="USD").available_minor == 750
    assert ledger.verify_rebuild(tenant_id="tenant-a", currency="USD")


def test_ledger_idempotency_is_stable_and_conflicts_fail() -> None:
    ledger = LedgerService()
    first = ledger.credit(
        tenant_id="tenant",
        money=Money("USD", 100),
        idempotency_key="same",
        reference="credit",
        occurred_at=NOW,
    )
    repeated = ledger.credit(
        tenant_id="tenant",
        money=Money("USD", 100),
        idempotency_key="same",
        reference="credit",
        occurred_at=NOW,
    )
    assert first is repeated
    assert len(ledger.transactions(tenant_id="tenant")) == 1
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        ledger.credit(
            tenant_id="tenant",
            money=Money("USD", 101),
            idempotency_key="same",
            reference="credit",
            occurred_at=NOW,
        )


def test_property_style_many_partial_reserve_capture_release_sequences_rebuild() -> None:
    for amount in range(1, 80):
        ledger = LedgerService()
        ledger.opening_balance(
            tenant_id="tenant",
            money=Money("USD", amount * 3),
            idempotency_key="opening",
            reference="opening",
            occurred_at=NOW,
        )
        ledger.reserve(
            tenant_id="tenant",
            money=Money("USD", amount * 2),
            idempotency_key="reserve",
            reference="quote",
            occurred_at=NOW,
        )
        ledger.capture(
            tenant_id="tenant",
            money=Money("USD", amount),
            idempotency_key="capture",
            reference="usage",
            occurred_at=NOW,
        )
        ledger.release(
            tenant_id="tenant",
            money=Money("USD", amount),
            idempotency_key="release",
            reference="quote",
            occurred_at=NOW,
        )
        balance = ledger.balance(tenant_id="tenant", currency="USD")
        assert (balance.available_minor, balance.reserved_minor, balance.captured_minor) == (amount * 2, 0, amount)
        assert ledger.verify_rebuild(tenant_id="tenant", currency="USD")


def test_atomic_concurrent_reservations_never_overspend() -> None:
    ledger = LedgerService()
    ledger.opening_balance(
        tenant_id="tenant",
        money=Money("USD", 100),
        idempotency_key="opening",
        reference="opening",
        occurred_at=NOW,
    )

    def reserve(index: int) -> str:
        try:
            ledger.reserve(
                tenant_id="tenant",
                money=Money("USD", 1),
                idempotency_key=f"reserve-{index}",
                reference=f"quote-{index}",
                occurred_at=NOW,
            )
            return "OK"
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=32) as pool:
        outcomes = tuple(pool.map(reserve, range(200)))
    assert outcomes.count("OK") == 100
    assert outcomes.count("INSUFFICIENT_AVAILABLE_BALANCE") == 100
    balance = ledger.balance(tenant_id="tenant", currency="USD")
    assert (balance.available_minor, balance.reserved_minor) == (0, 100)
    assert ledger.verify_rebuild(tenant_id="tenant", currency="USD")


def test_ledger_negative_and_cross_tenant_operations_fail_closed() -> None:
    ledger = LedgerService()
    with pytest.raises(DomainError, match="POSITIVE_VALUE_REQUIRED"):
        ledger.credit(
            tenant_id="tenant",
            money=Money("USD", -1),
            idempotency_key="negative",
            reference="bad",
            occurred_at=NOW,
        )
    transaction = ledger.credit(
        tenant_id="tenant-a",
        money=Money("USD", 100),
        idempotency_key="credit",
        reference="credit",
        occurred_at=NOW,
    )
    with pytest.raises(DomainError, match="TRANSACTION_NOT_FOUND"):
        ledger.reverse(
            tenant_id="tenant-b",
            transaction_id=transaction.transaction_id,
            idempotency_key="cross-tenant",
            reference="bad",
            occurred_at=NOW,
        )
