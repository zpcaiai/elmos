from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from json import dumps


class PostingSide(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _currency(value: object) -> str:
    currency = _required_text(value, field="currency").upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError("currency must be a three-letter ASCII code")
    return currency


def _amount(value: object, *, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a decimal") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -6:
        raise ValueError(f"{field} supports at most six fractional digits")
    if amount < 0:
        raise ValueError(f"{field} must be non-negative")
    return amount


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object with string keys")
    return value


def _items(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


@dataclass(frozen=True, slots=True)
class LedgerPosting:
    tenant_id: str
    transaction_id: str
    posting_id: str
    currency: str
    side: PostingSide
    amount: Decimal


@dataclass(frozen=True, slots=True)
class AllocationPool:
    tenant_id: str
    source_id: str
    currency: str
    source_amount: Decimal
    allocations: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class PaymentRefund:
    tenant_id: str
    payment_id: str
    currency: str
    charged_amount: Decimal
    refund_amounts: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class IdempotentEffect:
    tenant_id: str
    operation: str
    idempotency_key: str
    effect_id: str
    payload_digest: str


@dataclass(frozen=True, slots=True)
class InvoiceObservation:
    tenant_id: str
    invoice_id: str
    currency: str
    line_amounts: tuple[Decimal, ...]
    declared_subtotal: Decimal
    tax_amount: Decimal
    declared_total: Decimal


@dataclass(frozen=True, slots=True)
class MoneyInvariantObservation:
    ledger_postings: tuple[LedgerPosting, ...] = ()
    allocation_pools: tuple[AllocationPool, ...] = ()
    payment_refunds: tuple[PaymentRefund, ...] = ()
    idempotent_effects: tuple[IdempotentEffect, ...] = ()
    invoices: tuple[InvoiceObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class InvariantViolation:
    code: str
    entity_key: str
    expected: str
    observed: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class InvariantReport:
    violations: tuple[InvariantViolation, ...]

    @property
    def passed(self) -> bool:
        return not self.violations


def _canonical_decimal(value: Decimal) -> str:
    return format(value, "f")


def _violation(*, code: str, entity_key: str, expected: str, observed: str) -> InvariantViolation:
    canonical = dumps(
        {
            "code": code,
            "entity_key": entity_key,
            "expected": expected,
            "observed": observed,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return InvariantViolation(
        code=code,
        entity_key=entity_key,
        expected=expected,
        observed=observed,
        fingerprint="sha256:" + sha256(canonical.encode()).hexdigest(),
    )


def verify_money_invariants(observation: MoneyInvariantObservation) -> InvariantReport:
    violations: list[InvariantViolation] = []

    ledger: dict[tuple[str, str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    posting_ids: set[tuple[str, str]] = set()
    for posting in observation.ledger_postings:
        posting_key = (posting.tenant_id, posting.posting_id)
        if posting_key in posting_ids:
            violations.append(
                _violation(
                    code="DUPLICATE_LEDGER_POSTING_ID",
                    entity_key="/".join(posting_key),
                    expected="unique posting id within tenant",
                    observed=posting.posting_id,
                )
            )
        posting_ids.add(posting_key)
        totals = ledger[(posting.tenant_id, posting.transaction_id, posting.currency)]
        totals[0 if posting.side is PostingSide.DEBIT else 1] += posting.amount
    for key, (debits, credits) in ledger.items():
        if debits != credits:
            violations.append(
                _violation(
                    code="LEDGER_UNBALANCED",
                    entity_key="/".join(key),
                    expected=_canonical_decimal(debits),
                    observed=_canonical_decimal(credits),
                )
            )

    for pool in observation.allocation_pools:
        allocated = sum(pool.allocations, Decimal(0))
        if allocated != pool.source_amount:
            violations.append(
                _violation(
                    code="ALLOCATION_LEAKAGE",
                    entity_key=f"{pool.tenant_id}/{pool.source_id}/{pool.currency}",
                    expected=_canonical_decimal(pool.source_amount),
                    observed=_canonical_decimal(allocated),
                )
            )

    for payment in observation.payment_refunds:
        refunded = sum(payment.refund_amounts, Decimal(0))
        if refunded > payment.charged_amount:
            violations.append(
                _violation(
                    code="REFUND_EXCEEDS_PAYMENT",
                    entity_key=f"{payment.tenant_id}/{payment.payment_id}/{payment.currency}",
                    expected=f"<= {_canonical_decimal(payment.charged_amount)}",
                    observed=_canonical_decimal(refunded),
                )
            )

    effects: dict[tuple[str, str, str], list[IdempotentEffect]] = defaultdict(list)
    for effect in observation.idempotent_effects:
        effects[(effect.tenant_id, effect.operation, effect.idempotency_key)].append(effect)
    for key, values in effects.items():
        if len(values) > 1:
            effects_observed = ",".join(
                sorted(f"{effect.effect_id}:{effect.payload_digest}" for effect in values)
            )
            violations.append(
                _violation(
                    code="DUPLICATE_IDEMPOTENCY_EFFECT",
                    entity_key="/".join(key),
                    expected="one durable effect",
                    observed=effects_observed,
                )
            )

    for invoice in observation.invoices:
        line_total = sum(invoice.line_amounts, Decimal(0))
        expected_total = line_total + invoice.tax_amount
        if invoice.declared_subtotal != line_total or invoice.declared_total != expected_total:
            violations.append(
                _violation(
                    code="INVOICE_TOTAL_MISMATCH",
                    entity_key=f"{invoice.tenant_id}/{invoice.invoice_id}/{invoice.currency}",
                    expected=(
                        f"subtotal={_canonical_decimal(line_total)};"
                        f"total={_canonical_decimal(expected_total)}"
                    ),
                    observed=(
                        f"subtotal={_canonical_decimal(invoice.declared_subtotal)};"
                        f"total={_canonical_decimal(invoice.declared_total)}"
                    ),
                )
            )

    return InvariantReport(
        violations=tuple(
            sorted(
                violations,
                key=lambda violation: (violation.code, violation.entity_key, violation.fingerprint),
            )
        )
    )


def observation_from_mapping(document: Mapping[str, object]) -> MoneyInvariantObservation:
    ledger_postings: list[LedgerPosting] = []
    for index, value in enumerate(_items(document.get("ledger_postings", []), field="ledger_postings")):
        item = _mapping(value, field=f"ledger_postings[{index}]")
        ledger_postings.append(
            LedgerPosting(
                tenant_id=_required_text(item.get("tenant_id"), field="tenant_id"),
                transaction_id=_required_text(item.get("transaction_id"), field="transaction_id"),
                posting_id=_required_text(item.get("posting_id"), field="posting_id"),
                currency=_currency(item.get("currency")),
                side=PostingSide(_required_text(item.get("side"), field="side")),
                amount=_amount(item.get("amount"), field="amount"),
            )
        )

    allocation_pools: list[AllocationPool] = []
    for index, value in enumerate(_items(document.get("allocation_pools", []), field="allocation_pools")):
        item = _mapping(value, field=f"allocation_pools[{index}]")
        allocations = tuple(
            _amount(amount, field="allocation")
            for amount in _items(item.get("allocations", []), field="allocations")
        )
        allocation_pools.append(
            AllocationPool(
                tenant_id=_required_text(item.get("tenant_id"), field="tenant_id"),
                source_id=_required_text(item.get("source_id"), field="source_id"),
                currency=_currency(item.get("currency")),
                source_amount=_amount(item.get("source_amount"), field="source_amount"),
                allocations=allocations,
            )
        )

    payment_refunds: list[PaymentRefund] = []
    for index, value in enumerate(_items(document.get("payment_refunds", []), field="payment_refunds")):
        item = _mapping(value, field=f"payment_refunds[{index}]")
        refunds = tuple(
            _amount(amount, field="refund_amount")
            for amount in _items(item.get("refund_amounts", []), field="refund_amounts")
        )
        payment_refunds.append(
            PaymentRefund(
                tenant_id=_required_text(item.get("tenant_id"), field="tenant_id"),
                payment_id=_required_text(item.get("payment_id"), field="payment_id"),
                currency=_currency(item.get("currency")),
                charged_amount=_amount(item.get("charged_amount"), field="charged_amount"),
                refund_amounts=refunds,
            )
        )

    idempotent_effects: list[IdempotentEffect] = []
    for index, value in enumerate(
        _items(document.get("idempotent_effects", []), field="idempotent_effects")
    ):
        item = _mapping(value, field=f"idempotent_effects[{index}]")
        idempotent_effects.append(
            IdempotentEffect(
                tenant_id=_required_text(item.get("tenant_id"), field="tenant_id"),
                operation=_required_text(item.get("operation"), field="operation"),
                idempotency_key=_required_text(item.get("idempotency_key"), field="idempotency_key"),
                effect_id=_required_text(item.get("effect_id"), field="effect_id"),
                payload_digest=_required_text(item.get("payload_digest"), field="payload_digest"),
            )
        )

    invoices: list[InvoiceObservation] = []
    for index, value in enumerate(_items(document.get("invoices", []), field="invoices")):
        item = _mapping(value, field=f"invoices[{index}]")
        line_amounts = tuple(
            _amount(amount, field="line_amount")
            for amount in _items(item.get("line_amounts", []), field="line_amounts")
        )
        invoices.append(
            InvoiceObservation(
                tenant_id=_required_text(item.get("tenant_id"), field="tenant_id"),
                invoice_id=_required_text(item.get("invoice_id"), field="invoice_id"),
                currency=_currency(item.get("currency")),
                line_amounts=line_amounts,
                declared_subtotal=_amount(item.get("declared_subtotal"), field="declared_subtotal"),
                tax_amount=_amount(item.get("tax_amount"), field="tax_amount"),
                declared_total=_amount(item.get("declared_total"), field="declared_total"),
            )
        )

    return MoneyInvariantObservation(
        ledger_postings=tuple(ledger_postings),
        allocation_pools=tuple(allocation_pools),
        payment_refunds=tuple(payment_refunds),
        idempotent_effects=tuple(idempotent_effects),
        invoices=tuple(invoices),
    )
