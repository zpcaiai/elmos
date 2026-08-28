from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from threading import RLock

from .errors import DomainError, require
from .models import LedgerKind, LedgerTransaction, Posting, PostingSide, WalletBalance, canonical_digest
from .money import Money, checked_add, checked_i64, require_positive


class LedgerService:
    """Tenant-scoped append-only balanced ledger with deterministic projections."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._transactions: dict[str, list[LedgerTransaction]] = defaultdict(list)
        self._by_id: dict[tuple[str, str], LedgerTransaction] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, LedgerTransaction]] = {}
        self._balances: dict[tuple[str, str], WalletBalance] = {}
        self._reversed: set[tuple[str, str]] = set()

    def opening_balance(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        return self._credit_like(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=LedgerKind.OPENING,
        )

    def credit(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        return self._credit_like(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=LedgerKind.CREDIT,
        )

    def refund(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        return self._credit_like(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=LedgerKind.REFUND,
        )

    def reserve(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        return self._move(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=LedgerKind.RESERVE,
            debit_account="wallet_available",
            credit_account="wallet_reserved",
            available_effect=-money.minor,
            reserved_effect=money.minor,
            captured_effect=0,
            required_bucket="available",
        )

    def capture(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        return self._move(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=LedgerKind.CAPTURE,
            debit_account="wallet_reserved",
            credit_account="usage_captured",
            available_effect=0,
            reserved_effect=-money.minor,
            captured_effect=money.minor,
            required_bucket="reserved",
        )

    def release(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        return self._move(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=LedgerKind.RELEASE,
            debit_account="wallet_reserved",
            credit_account="wallet_available",
            available_effect=money.minor,
            reserved_effect=-money.minor,
            captured_effect=0,
            required_bucket="reserved",
        )

    def reverse(
        self,
        *,
        tenant_id: str,
        transaction_id: str,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> LedgerTransaction:
        with self._lock:
            try:
                target = self._by_id[(tenant_id, transaction_id)]
            except KeyError as exc:
                raise DomainError("TRANSACTION_NOT_FOUND", "ledger transaction was not found for tenant") from exc
            require(
                target.kind is not LedgerKind.REVERSAL, "REVERSAL_OF_REVERSAL_FORBIDDEN", "cannot reverse a reversal"
            )
            fingerprint = self._fingerprint(
                tenant_id=tenant_id,
                kind=LedgerKind.REVERSAL,
                money=target.postings[0].money,
                reference=reference,
                effects=(
                    -target.effect_available_minor,
                    -target.effect_reserved_minor,
                    -target.effect_captured_minor,
                ),
                reversal_of=target.transaction_id,
            )
            existing = self._idempotent_existing(tenant_id, idempotency_key, fingerprint)
            if existing is not None:
                return existing
            require(
                (tenant_id, transaction_id) not in self._reversed,
                "TRANSACTION_ALREADY_REVERSED",
                "ledger transaction was already reversed",
            )
            current = self.balance(tenant_id=tenant_id, currency=target.postings[0].money.currency)
            projected_available = checked_add(
                current.available_minor,
                -target.effect_available_minor,
                field="projected_available_minor",
            )
            projected_reserved = checked_add(
                current.reserved_minor,
                -target.effect_reserved_minor,
                field="projected_reserved_minor",
            )
            projected_captured = checked_add(
                current.captured_minor,
                -target.effect_captured_minor,
                field="projected_captured_minor",
            )
            require(
                projected_available >= 0,
                "REVERSAL_NEGATIVE_AVAILABLE",
                "reversal would make available balance negative",
            )
            require(
                projected_reserved >= 0, "REVERSAL_NEGATIVE_RESERVED", "reversal would make reserved balance negative"
            )
            require(
                projected_captured >= 0, "REVERSAL_NEGATIVE_CAPTURED", "reversal would make captured balance negative"
            )
            postings = tuple(
                Posting(
                    account=posting.account,
                    side=PostingSide.CREDIT if posting.side is PostingSide.DEBIT else PostingSide.DEBIT,
                    money=posting.money,
                )
                for posting in target.postings
            )
            reversed_transaction = self._append_new(
                tenant_id=tenant_id,
                kind=LedgerKind.REVERSAL,
                money=target.postings[0].money,
                idempotency_key=idempotency_key,
                reference=reference,
                occurred_at=occurred_at,
                postings=postings,
                available_effect=-target.effect_available_minor,
                reserved_effect=-target.effect_reserved_minor,
                captured_effect=-target.effect_captured_minor,
                fingerprint=fingerprint,
                reversal_of=target.transaction_id,
            )
            self._reversed.add((tenant_id, transaction_id))
            return reversed_transaction

    def balance(self, *, tenant_id: str, currency: str) -> WalletBalance:
        normalized = Money(currency, 0).currency
        with self._lock:
            return self._balances.get(
                (tenant_id, normalized),
                WalletBalance(
                    tenant_id=tenant_id,
                    currency=normalized,
                    available_minor=0,
                    reserved_minor=0,
                    captured_minor=0,
                    transaction_count=0,
                ),
            )

    def transactions(self, *, tenant_id: str) -> tuple[LedgerTransaction, ...]:
        with self._lock:
            return tuple(self._transactions.get(tenant_id, ()))

    def rebuild(self, *, tenant_id: str, currency: str) -> WalletBalance:
        normalized = Money(currency, 0).currency
        available = reserved = captured = count = 0
        with self._lock:
            for transaction in self._transactions.get(tenant_id, ()):
                if transaction.postings[0].money.currency != normalized:
                    continue
                available = checked_add(available, transaction.effect_available_minor, field="available_minor")
                reserved = checked_add(reserved, transaction.effect_reserved_minor, field="reserved_minor")
                captured = checked_add(captured, transaction.effect_captured_minor, field="captured_minor")
                count = checked_add(count, 1, field="transaction_count")
            return WalletBalance(
                tenant_id=tenant_id,
                currency=normalized,
                available_minor=available,
                reserved_minor=reserved,
                captured_minor=captured,
                transaction_count=count,
            )

    def verify_rebuild(self, *, tenant_id: str, currency: str) -> bool:
        return self.balance(tenant_id=tenant_id, currency=currency) == self.rebuild(
            tenant_id=tenant_id, currency=currency
        )

    def _credit_like(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
        kind: LedgerKind,
    ) -> LedgerTransaction:
        return self._move(
            tenant_id=tenant_id,
            money=money,
            idempotency_key=idempotency_key,
            reference=reference,
            occurred_at=occurred_at,
            kind=kind,
            debit_account="clearing",
            credit_account="wallet_available",
            available_effect=money.minor,
            reserved_effect=0,
            captured_effect=0,
            required_bucket=None,
        )

    def _move(
        self,
        *,
        tenant_id: str,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
        kind: LedgerKind,
        debit_account: str,
        credit_account: str,
        available_effect: int,
        reserved_effect: int,
        captured_effect: int,
        required_bucket: str | None,
    ) -> LedgerTransaction:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(idempotency_key.strip()), "IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required")
        require(bool(reference.strip()), "REFERENCE_REQUIRED", "reference is required")
        require_positive(money.minor, field="money.minor")
        checked_i64(available_effect, field="available_effect")
        checked_i64(reserved_effect, field="reserved_effect")
        checked_i64(captured_effect, field="captured_effect")
        postings = (
            Posting(account=debit_account, side=PostingSide.DEBIT, money=money),
            Posting(account=credit_account, side=PostingSide.CREDIT, money=money),
        )
        fingerprint = self._fingerprint(
            tenant_id=tenant_id,
            kind=kind,
            money=money,
            reference=reference,
            effects=(available_effect, reserved_effect, captured_effect),
        )
        with self._lock:
            existing = self._idempotent_existing(tenant_id, idempotency_key, fingerprint)
            if existing is not None:
                return existing
            current = self.balance(tenant_id=tenant_id, currency=money.currency)
            if required_bucket == "available":
                require(
                    current.available_minor >= money.minor,
                    "INSUFFICIENT_AVAILABLE_BALANCE",
                    "insufficient available balance",
                )
            if required_bucket == "reserved":
                require(
                    current.reserved_minor >= money.minor,
                    "INSUFFICIENT_RESERVED_BALANCE",
                    "insufficient reserved balance",
                )
            return self._append_new(
                tenant_id=tenant_id,
                kind=kind,
                money=money,
                idempotency_key=idempotency_key,
                reference=reference,
                occurred_at=occurred_at,
                postings=postings,
                available_effect=available_effect,
                reserved_effect=reserved_effect,
                captured_effect=captured_effect,
                fingerprint=fingerprint,
            )

    def _append_new(
        self,
        *,
        tenant_id: str,
        kind: LedgerKind,
        money: Money,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
        postings: tuple[Posting, ...],
        available_effect: int,
        reserved_effect: int,
        captured_effect: int,
        fingerprint: str,
        reversal_of: str | None = None,
    ) -> LedgerTransaction:
        self._validate_balanced(postings)
        sequence = checked_add(len(self._transactions.get(tenant_id, ())), 1, field="transaction_sequence")
        transaction = LedgerTransaction(
            tenant_id=tenant_id,
            transaction_id=f"txn:{tenant_id}:{sequence}",
            sequence=sequence,
            idempotency_key=idempotency_key,
            kind=kind,
            reference=reference,
            occurred_at=occurred_at,
            postings=postings,
            effect_available_minor=available_effect,
            effect_reserved_minor=reserved_effect,
            effect_captured_minor=captured_effect,
            reversal_of=reversal_of,
        )
        current = self.balance(tenant_id=tenant_id, currency=money.currency)
        updated = WalletBalance(
            tenant_id=tenant_id,
            currency=money.currency,
            available_minor=checked_add(current.available_minor, available_effect, field="available_minor"),
            reserved_minor=checked_add(current.reserved_minor, reserved_effect, field="reserved_minor"),
            captured_minor=checked_add(current.captured_minor, captured_effect, field="captured_minor"),
            transaction_count=checked_add(current.transaction_count, 1, field="transaction_count"),
        )
        self._transactions[tenant_id].append(transaction)
        self._by_id[(tenant_id, transaction.transaction_id)] = transaction
        self._idempotency[(tenant_id, idempotency_key)] = (fingerprint, transaction)
        self._balances[(tenant_id, money.currency)] = updated
        return transaction

    def _idempotent_existing(self, tenant_id: str, idempotency_key: str, fingerprint: str) -> LedgerTransaction | None:
        existing = self._idempotency.get((tenant_id, idempotency_key))
        if existing is None:
            return None
        require(existing[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "idempotency key was reused with different input")
        return existing[1]

    @staticmethod
    def _validate_balanced(postings: tuple[Posting, ...]) -> None:
        debit: dict[str, int] = defaultdict(int)
        credit: dict[str, int] = defaultdict(int)
        for posting in postings:
            target = debit if posting.side is PostingSide.DEBIT else credit
            target[posting.money.currency] = checked_add(
                target[posting.money.currency],
                posting.money.minor,
                field="posting_total_minor",
            )
        require(debit == credit, "UNBALANCED_TRANSACTION", "debits and credits must balance per currency")

    @staticmethod
    def _fingerprint(
        *,
        tenant_id: str,
        kind: LedgerKind,
        money: Money,
        reference: str,
        effects: tuple[int, int, int],
        reversal_of: str | None = None,
    ) -> str:
        return canonical_digest(
            {
                "tenant_id": tenant_id,
                "kind": kind,
                "currency": money.currency,
                "minor": money.minor,
                "reference": reference,
                "effects": effects,
                "reversal_of": reversal_of,
            }
        )
