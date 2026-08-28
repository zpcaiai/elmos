from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from enum import StrEnum
from threading import RLock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .commercial_closure import ExactAmount
from .errors import DomainError, require
from .models import require_aware
from .operations_closure import CertificationState, ExternalExecutionState, canonical_digest

_QUANTUM = Decimal("0.000001")


def _text(value: str, *, field: str) -> str:
    normalized = value.strip()
    require(bool(normalized), "TEXT_REQUIRED", f"{field} is required", field=field)
    return normalized


def _tenant(value: str) -> str:
    normalized = _text(value, field="tenant_id")
    require(normalized != "*", "WILDCARD_TENANT_FORBIDDEN", "wildcard tenant scope is forbidden")
    return normalized


def _decimal(value: Decimal, *, field: str, signed: bool = False, positive: bool = False) -> Decimal:
    require(isinstance(value, Decimal), "DECIMAL_REQUIRED", f"{field} must be Decimal", field=field)
    require(value.is_finite(), "DECIMAL_NOT_FINITE", f"{field} must be finite", field=field)
    try:
        normalized = value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise DomainError("DECIMAL_INVALID", f"{field} cannot be normalized") from exc
    require(normalized == value, "DECIMAL_SCALE_EXCEEDED", f"{field} supports at most six decimals", field=field)
    if positive:
        require(normalized > 0, "DECIMAL_NOT_POSITIVE", f"{field} must be positive", field=field)
    elif not signed:
        require(normalized >= 0, "DECIMAL_NEGATIVE", f"{field} must be non-negative", field=field)
    return normalized


def _same_currency(left: ExactAmount, right: ExactAmount) -> None:
    require(left.currency == right.currency, "CURRENCY_MISMATCH", "amount currencies differ")


class WalletBucket(StrEnum):
    PAID = "PAID"
    PROMOTIONAL = "PROMOTIONAL"
    RESERVED_PAID = "RESERVED_PAID"
    RESERVED_PROMOTIONAL = "RESERVED_PROMOTIONAL"
    CONSUMED = "CONSUMED"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"
    EXTERNAL_FUNDING = "EXTERNAL_FUNDING"
    PROMOTION_EXPENSE = "PROMOTION_EXPENSE"
    ADJUSTMENT_CLEARING = "ADJUSTMENT_CLEARING"


class WalletAction(StrEnum):
    CREDIT = "CREDIT"
    RESERVE = "RESERVE"
    CAPTURE = "CAPTURE"
    RELEASE = "RELEASE"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"
    EXPIRE = "EXPIRE"


class AdjustmentState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"


@dataclass(frozen=True, slots=True)
class WalletPosting:
    posting_id: str
    tenant_id: str
    action: WalletAction
    debit: WalletBucket
    credit: WalletBucket
    amount: ExactAmount
    idempotency_key: str
    reference: str
    reservation_id: str | None
    reason: str
    evidence_ref: str
    requested_by: str
    approved_by: str | None
    occurred_at: datetime
    sequence: int


@dataclass(frozen=True, slots=True)
class ManualAdjustment:
    adjustment_id: str
    tenant_id: str
    bucket: WalletBucket
    signed_amount: Decimal
    currency: str
    reason: str
    evidence_ref: str
    requested_by: str
    approved_by: str | None
    state: AdjustmentState
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class WalletSnapshot:
    tenant_id: str
    currency: str
    paid: Decimal
    promotional: Decimal
    reserved: Decimal
    consumed: Decimal
    refunded: Decimal
    expired: Decimal
    revision: int
    posting_digest: str

    @property
    def available(self) -> Decimal:
        return self.paid + self.promotional


@dataclass(frozen=True, slots=True)
class DayEndBalance:
    tenant_id: str
    currency: str
    as_of: datetime
    snapshot: WalletSnapshot
    debit_total: Decimal
    credit_total: Decimal
    conserved: bool
    source_posting_ids: tuple[str, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class WalletReconciliation:
    day_end_digest: str
    external_reference: str | None
    external_state: ExternalExecutionState
    matched: bool | None
    difference: Decimal | None


@dataclass(frozen=True, slots=True)
class WalletOutboxFact:
    event_id: str
    tenant_id: str
    aggregate_version: int
    idempotency_key: str
    posting_ids: tuple[str, ...]
    payload_digest: str
    created_at: datetime
    publication_state: ExternalExecutionState


class CreditWalletExactnessService:
    """EB-04 local wallet semantics; external settlement remains unexecuted."""

    authority = "LOCAL_REFERENCE_ONLY"
    external_reconciliation = ExternalExecutionState.NOT_RUN
    certification = CertificationState.NOT_CERTIFIED

    _PROJECTED = frozenset(
        {
            WalletBucket.PAID,
            WalletBucket.PROMOTIONAL,
            WalletBucket.RESERVED_PAID,
            WalletBucket.RESERVED_PROMOTIONAL,
            WalletBucket.CONSUMED,
            WalletBucket.REFUNDED,
            WalletBucket.EXPIRED,
        }
    )

    def __init__(self) -> None:
        self._lock = RLock()
        self._postings: list[WalletPosting] = []
        self._outbox: list[WalletOutboxFact] = []
        self._commands: dict[tuple[str, str], tuple[str, object]] = {}
        self._adjustments: dict[tuple[str, str], ManualAdjustment] = {}

    def credit(
        self,
        *,
        tenant_id: str,
        amount: ExactAmount,
        promotional: bool,
        idempotency_key: str,
        reference: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        bucket = WalletBucket.PROMOTIONAL if promotional else WalletBucket.PAID
        source = WalletBucket.PROMOTION_EXPENSE if promotional else WalletBucket.EXTERNAL_FUNDING
        return self._single_command(
            tenant_id=tenant_id,
            command="credit",
            idempotency_key=idempotency_key,
            payload=(amount.canonical, promotional, reference, require_aware(occurred_at, field_name="occurred_at")),
            postings=((source, bucket, amount, None, "CREDIT_GRANTED", reference, "system", None),),
            occurred_at=occurred_at,
        )

    def reserve(
        self,
        *,
        tenant_id: str,
        reservation_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        tenant_id = _tenant(tenant_id)
        reservation_id = _text(reservation_id, field="reservation_id")
        before = self.snapshot(tenant_id=tenant_id, currency=amount.currency, as_of=occurred_at)
        require(before.available >= amount.value, "INSUFFICIENT_AVAILABLE_BALANCE", "reservation exceeds balance")
        promotional = min(before.promotional, amount.value)
        paid = amount.value - promotional
        postings: list[tuple[WalletBucket, WalletBucket, ExactAmount, str | None, str, str, str, str | None]] = []
        if promotional > 0:
            postings.append(
                (
                    WalletBucket.PROMOTIONAL,
                    WalletBucket.RESERVED_PROMOTIONAL,
                    ExactAmount(amount.currency, promotional),
                    reservation_id,
                    "RESERVE_PROMOTIONAL",
                    reservation_id,
                    "system",
                    None,
                )
            )
        if paid > 0:
            postings.append(
                (
                    WalletBucket.PAID,
                    WalletBucket.RESERVED_PAID,
                    ExactAmount(amount.currency, paid),
                    reservation_id,
                    "RESERVE_PAID",
                    reservation_id,
                    "system",
                    None,
                )
            )
        return self._single_command(
            tenant_id=tenant_id,
            command="reserve",
            idempotency_key=idempotency_key,
            payload=(reservation_id, amount.canonical, require_aware(occurred_at, field_name="occurred_at")),
            postings=tuple(postings),
            occurred_at=occurred_at,
        )

    def capture(
        self,
        *,
        tenant_id: str,
        reservation_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        return self._settle_reservation(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            amount=amount,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            capture=True,
        )

    def release(
        self,
        *,
        tenant_id: str,
        reservation_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        return self._settle_reservation(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            amount=amount,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            capture=False,
        )

    def refund(
        self,
        *,
        tenant_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        payment_reference: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        before = self.snapshot(tenant_id=tenant_id, currency=amount.currency, as_of=occurred_at)
        require(before.consumed >= amount.value, "REFUND_EXCEEDS_CONSUMED", "refund exceeds net consumed balance")
        return self._single_command(
            tenant_id=tenant_id,
            command="refund",
            idempotency_key=idempotency_key,
            payload=(amount.canonical, payment_reference, require_aware(occurred_at, field_name="occurred_at")),
            postings=(
                (
                    WalletBucket.CONSUMED,
                    WalletBucket.REFUNDED,
                    amount,
                    None,
                    "REFUND_POSTED",
                    payment_reference,
                    "system",
                    None,
                ),
            ),
            occurred_at=occurred_at,
        )

    def expire_promotional(
        self,
        *,
        tenant_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        grant_reference: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        before = self.snapshot(tenant_id=tenant_id, currency=amount.currency, as_of=occurred_at)
        require(before.promotional >= amount.value, "PROMOTIONAL_EXPIRY_EXCEEDS_BALANCE", "expiry exceeds promo")
        return self._single_command(
            tenant_id=tenant_id,
            command="expire",
            idempotency_key=idempotency_key,
            payload=(amount.canonical, grant_reference, require_aware(occurred_at, field_name="occurred_at")),
            postings=(
                (
                    WalletBucket.PROMOTIONAL,
                    WalletBucket.EXPIRED,
                    amount,
                    None,
                    "PROMOTIONAL_EXPIRED",
                    grant_reference,
                    "system",
                    None,
                ),
            ),
            occurred_at=occurred_at,
        )

    def request_adjustment(
        self,
        *,
        adjustment_id: str,
        tenant_id: str,
        bucket: WalletBucket,
        signed_amount: Decimal,
        currency: str,
        reason: str,
        evidence_ref: str,
        requested_by: str,
        requested_at: datetime,
    ) -> ManualAdjustment:
        require(bucket in {WalletBucket.PAID, WalletBucket.PROMOTIONAL}, "ADJUSTMENT_BUCKET_INVALID", "invalid")
        adjustment = ManualAdjustment(
            _text(adjustment_id, field="adjustment_id"),
            _tenant(tenant_id),
            bucket,
            _decimal(signed_amount, field="signed_amount", signed=True),
            ExactAmount.zero(currency).currency,
            _text(reason, field="reason"),
            _text(evidence_ref, field="evidence_ref"),
            _text(requested_by, field="requested_by"),
            None,
            AdjustmentState.PENDING,
            require_aware(requested_at, field_name="requested_at"),
        )
        require(adjustment.signed_amount != 0, "ADJUSTMENT_ZERO", "adjustment cannot be zero")
        with self._lock:
            key = (adjustment.tenant_id, adjustment.adjustment_id)
            require(key not in self._adjustments, "ADJUSTMENT_EXISTS", "adjustment already exists")
            self._adjustments[key] = adjustment
        return adjustment

    def approve_adjustment(
        self,
        *,
        tenant_id: str,
        adjustment_id: str,
        approved_by: str,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> WalletSnapshot:
        key = (_tenant(tenant_id), _text(adjustment_id, field="adjustment_id"))
        with self._lock:
            try:
                adjustment = self._adjustments[key]
            except KeyError as exc:
                raise DomainError("ADJUSTMENT_NOT_FOUND", "adjustment was not found") from exc
            require(adjustment.state is AdjustmentState.PENDING, "ADJUSTMENT_NOT_PENDING", "adjustment terminal")
            approved_by = _text(approved_by, field="approved_by")
            require(adjustment.requested_by != approved_by, "MAKER_CHECKER_VIOLATION", "self approval forbidden")
            current = self.snapshot(tenant_id=tenant_id, currency=adjustment.currency, as_of=occurred_at)
            available = current.paid if adjustment.bucket is WalletBucket.PAID else current.promotional
            if adjustment.signed_amount < 0:
                require(available >= -adjustment.signed_amount, "ADJUSTMENT_NEGATIVE_BALANCE", "adjustment underflows")
            amount = ExactAmount(adjustment.currency, abs(adjustment.signed_amount))
            debit, credit = (
                (WalletBucket.ADJUSTMENT_CLEARING, adjustment.bucket)
                if adjustment.signed_amount > 0
                else (adjustment.bucket, WalletBucket.ADJUSTMENT_CLEARING)
            )
            result = self._single_command(
                tenant_id=tenant_id,
                command="adjustment",
                idempotency_key=idempotency_key,
                payload=(adjustment_id, approved_by, adjustment.signed_amount, adjustment.evidence_ref),
                postings=(
                    (
                        debit,
                        credit,
                        amount,
                        None,
                        adjustment.reason,
                        adjustment.evidence_ref,
                        adjustment.requested_by,
                        approved_by,
                    ),
                ),
                occurred_at=occurred_at,
            )
            self._adjustments[key] = replace(
                adjustment,
                approved_by=approved_by,
                state=AdjustmentState.APPROVED,
            )
            return result

    def snapshot(self, *, tenant_id: str, currency: str, as_of: datetime) -> WalletSnapshot:
        tenant_id = _tenant(tenant_id)
        currency = ExactAmount.zero(currency).currency
        as_of = require_aware(as_of, field_name="as_of")
        balances = {bucket: Decimal("0.000000") for bucket in self._PROJECTED}
        selected = tuple(
            posting
            for posting in self._postings
            if posting.tenant_id == tenant_id
            and posting.amount.currency == currency
            and posting.occurred_at <= as_of
        )
        for posting in selected:
            if posting.debit in balances:
                balances[posting.debit] -= posting.amount.value
                require(balances[posting.debit] >= 0, "LEDGER_NEGATIVE_PROJECTION", "ledger projection underflow")
            if posting.credit in balances:
                balances[posting.credit] += posting.amount.value
        reserved = balances[WalletBucket.RESERVED_PAID] + balances[WalletBucket.RESERVED_PROMOTIONAL]
        return WalletSnapshot(
            tenant_id,
            currency,
            balances[WalletBucket.PAID],
            balances[WalletBucket.PROMOTIONAL],
            reserved,
            balances[WalletBucket.CONSUMED],
            balances[WalletBucket.REFUNDED],
            balances[WalletBucket.EXPIRED],
            len(selected),
            canonical_digest(tuple(posting.posting_id for posting in selected)),
        )

    def day_end(self, *, tenant_id: str, currency: str, as_of: datetime) -> DayEndBalance:
        snapshot = self.snapshot(tenant_id=tenant_id, currency=currency, as_of=as_of)
        selected = tuple(
            posting
            for posting in self._postings
            if posting.tenant_id == snapshot.tenant_id
            and posting.amount.currency == snapshot.currency
            and posting.occurred_at <= as_of
        )
        debit = sum((posting.amount.value for posting in selected), Decimal("0.000000"))
        credit = sum((posting.amount.value for posting in selected), Decimal("0.000000"))
        facts = {
            "tenant": snapshot.tenant_id,
            "currency": snapshot.currency,
            "as_of": require_aware(as_of, field_name="as_of"),
            "snapshot": snapshot,
            "posting_ids": tuple(posting.posting_id for posting in selected),
        }
        return DayEndBalance(
            snapshot.tenant_id,
            snapshot.currency,
            require_aware(as_of, field_name="as_of"),
            snapshot,
            debit,
            credit,
            debit == credit,
            tuple(posting.posting_id for posting in selected),
            canonical_digest(facts),
        )

    @staticmethod
    def reconcile_external(
        day_end: DayEndBalance,
        *,
        external_paid_balance: Decimal | None,
        external_reference: str | None,
        external_state: ExternalExecutionState,
    ) -> WalletReconciliation:
        if external_state is not ExternalExecutionState.EXTERNALLY_VERIFIED:
            return WalletReconciliation(day_end.digest, external_reference, external_state, None, None)
        if external_paid_balance is None:
            raise DomainError("EXTERNAL_BALANCE_REQUIRED", "external balance is required")
        require(bool(external_reference and external_reference.strip()), "EXTERNAL_REFERENCE_REQUIRED", "ref required")
        normalized = _decimal(external_paid_balance, field="external_paid_balance")
        difference = day_end.snapshot.paid - normalized
        return WalletReconciliation(day_end.digest, external_reference, external_state, difference == 0, difference)

    def postings(self, *, tenant_id: str) -> tuple[WalletPosting, ...]:
        tenant_id = _tenant(tenant_id)
        return tuple(posting for posting in self._postings if posting.tenant_id == tenant_id)

    def outbox_facts(self, *, tenant_id: str) -> tuple[WalletOutboxFact, ...]:
        tenant_id = _tenant(tenant_id)
        return tuple(fact for fact in self._outbox if fact.tenant_id == tenant_id)

    def _settle_reservation(
        self,
        *,
        tenant_id: str,
        reservation_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        occurred_at: datetime,
        capture: bool,
    ) -> WalletSnapshot:
        tenant_id = _tenant(tenant_id)
        reservation_id = _text(reservation_id, field="reservation_id")
        reserved_by_bucket = self._reservation_balance(tenant_id, reservation_id, amount.currency, occurred_at)
        total = sum(reserved_by_bucket.values(), Decimal("0.000000"))
        require(total >= amount.value, "RESERVATION_SETTLEMENT_EXCEEDS_OPEN", "settlement exceeds reservation")
        remaining = amount.value
        postings: list[tuple[WalletBucket, WalletBucket, ExactAmount, str | None, str, str, str, str | None]] = []
        for reserved_bucket, available_bucket in (
            (WalletBucket.RESERVED_PROMOTIONAL, WalletBucket.PROMOTIONAL),
            (WalletBucket.RESERVED_PAID, WalletBucket.PAID),
        ):
            part = min(reserved_by_bucket[reserved_bucket], remaining)
            if part > 0:
                postings.append(
                    (
                        reserved_bucket,
                        WalletBucket.CONSUMED if capture else available_bucket,
                        ExactAmount(amount.currency, part),
                        reservation_id,
                        "PARTIAL_CAPTURE" if capture else "RESERVATION_RELEASE",
                        reservation_id,
                        "system",
                        None,
                    )
                )
                remaining -= part
        return self._single_command(
            tenant_id=tenant_id,
            command="capture" if capture else "release",
            idempotency_key=idempotency_key,
            payload=(reservation_id, amount.canonical, require_aware(occurred_at, field_name="occurred_at")),
            postings=tuple(postings),
            occurred_at=occurred_at,
        )

    def _reservation_balance(
        self, tenant_id: str, reservation_id: str, currency: str, as_of: datetime
    ) -> dict[WalletBucket, Decimal]:
        balances = {
            WalletBucket.RESERVED_PAID: Decimal("0.000000"),
            WalletBucket.RESERVED_PROMOTIONAL: Decimal("0.000000"),
        }
        for posting in self._postings:
            if (
                posting.tenant_id != tenant_id
                or posting.reservation_id != reservation_id
                or posting.amount.currency != currency
                or posting.occurred_at > as_of
            ):
                continue
            if posting.credit in balances:
                balances[posting.credit] += posting.amount.value
            if posting.debit in balances:
                balances[posting.debit] -= posting.amount.value
        return balances

    def _single_command(
        self,
        *,
        tenant_id: str,
        command: str,
        idempotency_key: str,
        payload: object,
        postings: tuple[
            tuple[WalletBucket, WalletBucket, ExactAmount, str | None, str, str, str, str | None], ...
        ],
        occurred_at: datetime,
    ) -> WalletSnapshot:
        tenant_id = _tenant(tenant_id)
        idempotency_key = _text(idempotency_key, field="idempotency_key")
        occurred_at = require_aware(occurred_at, field_name="occurred_at")
        require(bool(postings), "WALLET_POSTINGS_REQUIRED", "wallet command requires postings")
        require(
            all(posting[2].value > 0 for posting in postings),
            "WALLET_POSTING_NOT_POSITIVE",
            "wallet postings must be positive",
        )
        fingerprint = canonical_digest((command, payload))
        command_key = (tenant_id, idempotency_key)
        with self._lock:
            prior = self._commands.get(command_key)
            if prior is not None:
                require(prior[0] == fingerprint, "IDEMPOTENCY_PAYLOAD_CONFLICT", "idempotency key reused")
                result = prior[1]
                if not isinstance(result, WalletSnapshot):
                    raise DomainError("COMMAND_RECEIPT_INVALID", "invalid wallet receipt")
                return result
            currency = postings[0][2].currency
            require(
                all(posting[2].currency == currency for posting in postings),
                "CURRENCY_MISMATCH",
                "wallet command currencies differ",
            )
            projected = {bucket: Decimal("0.000000") for bucket in self._PROJECTED}
            for existing in self._postings:
                if (
                    existing.tenant_id != tenant_id
                    or existing.amount.currency != currency
                    or existing.occurred_at > occurred_at
                ):
                    continue
                if existing.debit in projected:
                    projected[existing.debit] -= existing.amount.value
                if existing.credit in projected:
                    projected[existing.credit] += existing.amount.value
            underflow_codes = {
                "reserve": "INSUFFICIENT_AVAILABLE_BALANCE",
                "capture": "RESERVATION_SETTLEMENT_EXCEEDS_OPEN",
                "release": "RESERVATION_SETTLEMENT_EXCEEDS_OPEN",
                "refund": "REFUND_EXCEEDS_CONSUMED",
                "expire": "PROMOTIONAL_EXPIRY_EXCEEDS_BALANCE",
                "adjustment": "ADJUSTMENT_NEGATIVE_BALANCE",
            }
            for debit, credit, amount, *_ in postings:
                if debit in projected:
                    require(
                        projected[debit] >= amount.value,
                        underflow_codes.get(command, "LEDGER_NEGATIVE_PROJECTION"),
                        "wallet command would underflow a projected balance",
                    )
                    projected[debit] -= amount.value
                if credit in projected:
                    projected[credit] += amount.value
            start = len(self._postings)
            try:
                for debit, credit, amount, reservation_id, reason, evidence, requester, approver in postings:
                    require(debit != credit, "DOUBLE_ENTRY_ACCOUNT_COLLISION", "debit and credit must differ")
                    posting = WalletPosting(
                        f"wallet-posting-{len(self._postings) + 1:08d}",
                        tenant_id,
                        WalletAction(command.upper()),
                        debit,
                        credit,
                        amount,
                        idempotency_key,
                        evidence,
                        reservation_id,
                        reason,
                        evidence,
                        requester,
                        approver,
                        occurred_at,
                        len(self._postings) + 1,
                    )
                    self._postings.append(posting)
                result = self.snapshot(tenant_id=tenant_id, currency=currency, as_of=occurred_at)
                command_posting_ids = tuple(
                    posting.posting_id for posting in self._postings[start:]
                )
                self._outbox.append(
                    WalletOutboxFact(
                        f"wallet-outbox-{len(self._outbox) + 1:08d}",
                        tenant_id,
                        result.revision,
                        idempotency_key,
                        command_posting_ids,
                        canonical_digest((command, payload, command_posting_ids)),
                        occurred_at,
                        ExternalExecutionState.NOT_RUN,
                    )
                )
            except Exception:
                del self._postings[start:]
                raise
            self._commands[command_key] = (fingerprint, result)
            return result


class ResourceCategory(StrEnum):
    TOKEN = "TOKEN"  # noqa: S105 - metering resource label, never a credential
    CACHED_TOKEN = "CACHED_TOKEN"  # noqa: S105 - metering resource label
    CPU = "CPU"
    GPU = "GPU"
    BROWSER = "BROWSER"
    TEST = "TEST"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    THIRD_PARTY_TOOL = "THIRD_PARTY_TOOL"


class UsageTreatment(StrEnum):
    USER_BILLABLE = "USER_BILLABLE"
    PLATFORM_ABSORBED = "PLATFORM_ABSORBED"
    FREE = "FREE"
    FAILED_RETRY = "FAILED_RETRY"
    BYOK = "BYOK"


class UsageDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    LATE_REVIEW = "LATE_REVIEW"


class PipelineState(StrEnum):
    ACCEPTED = "ACCEPTED"
    BACKPRESSURE_RETRY = "BACKPRESSURE_RETRY"
    RETRY = "RETRY"
    DEAD_LETTER = "DEAD_LETTER"
    REPLAYED = "REPLAYED"


@dataclass(frozen=True, slots=True)
class RawUsageEvent:
    event_id: str
    source_event_id: str
    tenant_id: str
    task_id: str
    run_id: str
    node_id: str
    category: ResourceCategory
    raw_quantity: Decimal
    raw_unit: str
    provider_id: str
    treatment: UsageTreatment
    event_at: datetime
    received_at: datetime

    def __post_init__(self) -> None:
        for value, field in (
            (self.event_id, "event_id"),
            (self.source_event_id, "source_event_id"),
            (self.task_id, "task_id"),
            (self.run_id, "run_id"),
            (self.node_id, "node_id"),
            (self.raw_unit, "raw_unit"),
            (self.provider_id, "provider_id"),
        ):
            _text(value, field=field)
        _tenant(self.tenant_id)
        _decimal(self.raw_quantity, field="raw_quantity", positive=True)
        object.__setattr__(self, "event_at", require_aware(self.event_at, field_name="event_at"))
        object.__setattr__(self, "received_at", require_aware(self.received_at, field_name="received_at"))


@dataclass(frozen=True, slots=True)
class NormalizationRule:
    version: str
    category: ResourceCategory
    raw_unit: str
    normalized_unit: str
    factor: Decimal
    precision: int

    def __post_init__(self) -> None:
        _text(self.version, field="normalization_version")
        _text(self.raw_unit, field="raw_unit")
        _text(self.normalized_unit, field="normalized_unit")
        _decimal(self.factor, field="factor", positive=True)
        require(0 <= self.precision <= 6, "NORMALIZATION_PRECISION_INVALID", "precision must be 0..6")


@dataclass(frozen=True, slots=True)
class ProviderRate:
    version: str
    provider_id: str
    category: ResourceCategory
    normalized_unit: str
    cost_per_unit: ExactAmount
    effective_from: datetime
    effective_to: datetime

    def __post_init__(self) -> None:
        _text(self.version, field="rate_version")
        _text(self.provider_id, field="provider_id")
        _text(self.normalized_unit, field="normalized_unit")
        object.__setattr__(self, "effective_from", require_aware(self.effective_from, field_name="effective_from"))
        object.__setattr__(self, "effective_to", require_aware(self.effective_to, field_name="effective_to"))
        require(self.effective_to > self.effective_from, "RATE_WINDOW_INVALID", "rate window is invalid")


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    raw: RawUsageEvent
    normalization_version: str
    normalized_quantity: Decimal
    normalized_unit: str
    conversion_factor: Decimal
    precision: int
    rounding_delta: Decimal
    provider_rate_version: str
    internal_cost: ExactAmount
    customer_charge: ExactAmount
    decision: UsageDecision
    correction_of: str | None = None


@dataclass(frozen=True, slots=True)
class UsageAggregate:
    tenant_id: str
    category: ResourceCategory
    normalized_unit: str
    quantity: Decimal
    internal_cost: ExactAmount
    customer_charge: ExactAmount
    detail_event_ids: tuple[str, ...]
    as_of: datetime
    closed_through: datetime | None
    coverage_basis_points: int


@dataclass(frozen=True, slots=True)
class PipelineReceipt:
    source_event_id: str
    state: PipelineState
    attempt: int
    reason: str


@dataclass(frozen=True, slots=True)
class UsageReconciliation:
    tenant_id: str
    period_start: datetime
    period_end: datetime
    provider_state: ExternalExecutionState
    run_evidence_state: ExternalExecutionState
    matched: bool | None
    provider_difference: Decimal | None
    missing_run_ids: tuple[str, ...]


class UsageMeteringExactnessService:
    """EB-05 typed usage normalization and bounded pipeline reference."""

    authority = "LOCAL_REFERENCE_ONLY"
    provider_bill_evidence = ExternalExecutionState.NOT_RUN
    run_evidence = ExternalExecutionState.NOT_RUN
    certification = CertificationState.NOT_CERTIFIED

    def __init__(self, *, queue_capacity: int = 2, maximum_attempts: int = 2) -> None:
        require(queue_capacity > 0 and maximum_attempts > 0, "PIPELINE_BOUNDS_INVALID", "bounds must be positive")
        self._lock = RLock()
        self._queue_capacity = queue_capacity
        self._maximum_attempts = maximum_attempts
        self._rules: dict[tuple[ResourceCategory, str], NormalizationRule] = {}
        self._rates: list[ProviderRate] = []
        self._records: list[NormalizedUsage] = []
        self._source: dict[tuple[str, str], tuple[str, NormalizedUsage]] = {}
        self._commands: dict[tuple[str, str], tuple[str, NormalizedUsage]] = {}
        self._corrections: dict[tuple[str, str], str] = {}
        self._closed_through: dict[str, datetime] = {}
        self._queue: list[tuple[RawUsageEvent, str]] = []
        self._attempts: dict[tuple[str, str], int] = {}
        self._dead_letter: dict[tuple[str, str], tuple[RawUsageEvent, str]] = {}

    def register_rule(self, rule: NormalizationRule) -> None:
        key = (rule.category, rule.raw_unit)
        prior = self._rules.get(key)
        require(prior is None or prior == rule, "NORMALIZATION_RULE_CONFLICT", "rule changed in place")
        self._rules[key] = rule

    def register_rate(self, rate: ProviderRate) -> None:
        require(rate not in self._rates, "RATE_DUPLICATE", "rate already registered")
        self._rates.append(rate)

    def close_through(self, *, tenant_id: str, closed_through: datetime) -> None:
        tenant_id = _tenant(tenant_id)
        closed_through = require_aware(closed_through, field_name="closed_through")
        prior = self._closed_through.get(tenant_id)
        require(prior is None or closed_through >= prior, "CLOSE_REGRESSION", "close cannot move backward")
        self._closed_through[tenant_id] = closed_through

    def ingest(self, event: RawUsageEvent, *, idempotency_key: str) -> NormalizedUsage:
        idempotency_key = _text(idempotency_key, field="idempotency_key")
        fingerprint = canonical_digest(event)
        source_key = (event.tenant_id, event.source_event_id)
        command_key = (event.tenant_id, idempotency_key)
        with self._lock:
            prior_command = self._commands.get(command_key)
            if prior_command is not None:
                require(prior_command[0] == fingerprint, "USAGE_IDEMPOTENCY_CONFLICT", "command payload changed")
                return prior_command[1]
            prior = self._source.get(source_key)
            if prior is not None:
                require(prior[0] == fingerprint, "USAGE_SOURCE_COLLISION", "source event payload changed")
                self._commands[command_key] = prior
                return prior[1]
            rule = self._required_rule(event.category, event.raw_unit)
            rate = self._required_rate(event)
            require(
                rate.normalized_unit == rule.normalized_unit,
                "PROVIDER_RATE_UNIT_MISMATCH",
                "rate and normalization units differ",
            )
            raw_converted = event.raw_quantity * rule.factor
            quantum = Decimal(1).scaleb(-rule.precision)
            normalized = raw_converted.quantize(quantum, rounding=ROUND_HALF_EVEN).quantize(_QUANTUM)
            rounding_delta = normalized - raw_converted
            internal_value = (normalized * rate.cost_per_unit.value).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
            if event.treatment is UsageTreatment.BYOK and event.category in {
                ResourceCategory.TOKEN,
                ResourceCategory.CACHED_TOKEN,
            }:
                internal_value = Decimal("0.000000")
            customer_value = (
                internal_value if event.treatment is UsageTreatment.USER_BILLABLE else Decimal("0.000000")
            )
            closed = self._closed_through.get(event.tenant_id)
            decision = (
                UsageDecision.LATE_REVIEW
                if closed is not None and event.event_at < closed and event.received_at >= closed
                else UsageDecision.ACCEPTED
            )
            record = NormalizedUsage(
                event,
                rule.version,
                normalized,
                rule.normalized_unit,
                rule.factor,
                rule.precision,
                rounding_delta,
                rate.version,
                ExactAmount(rate.cost_per_unit.currency, internal_value),
                ExactAmount(rate.cost_per_unit.currency, customer_value),
                decision,
            )
            self._records.append(record)
            self._source[source_key] = (fingerprint, record)
            self._commands[command_key] = (fingerprint, record)
            return record

    def correct(
        self,
        *,
        tenant_id: str,
        original_source_event_id: str,
        correction: RawUsageEvent,
        idempotency_key: str,
    ) -> NormalizedUsage:
        tenant_id = _tenant(tenant_id)
        require(correction.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "correction is cross-tenant")
        original = self._source.get((tenant_id, _text(original_source_event_id, field="original_source_event_id")))
        if original is None:
            raise DomainError("USAGE_ORIGINAL_NOT_FOUND", "correction source was not found")
        correction_key = (tenant_id, correction.source_event_id)
        prior_correction = self._corrections.get(correction_key)
        require(
            prior_correction is None or prior_correction == original_source_event_id,
            "USAGE_CORRECTION_TARGET_CONFLICT",
            "correction event cannot target a different source",
        )
        normalized = self.ingest(correction, idempotency_key=idempotency_key)
        require(
            normalized.raw.category is original[1].raw.category
            and normalized.normalized_unit == original[1].normalized_unit,
            "USAGE_CORRECTION_DIMENSION_MISMATCH",
            "correction must preserve category and unit",
        )
        require(
            normalized.correction_of in {None, original_source_event_id},
            "USAGE_CORRECTION_TARGET_CONFLICT",
            "correction event cannot target a different source",
        )
        corrected = replace(normalized, correction_of=original_source_event_id)
        for index, record in enumerate(self._records):
            if record.raw.tenant_id == tenant_id and record.raw.source_event_id == correction.source_event_id:
                self._records[index] = corrected
                break
        source_fingerprint = self._source[correction_key][0]
        self._source[correction_key] = (source_fingerprint, corrected)
        self._commands[(tenant_id, _text(idempotency_key, field="idempotency_key"))] = (
            source_fingerprint,
            corrected,
        )
        self._corrections[correction_key] = original_source_event_id
        return corrected

    def aggregate(
        self,
        *,
        tenant_id: str,
        category: ResourceCategory,
        normalized_unit: str,
        as_of: datetime,
    ) -> UsageAggregate:
        tenant_id = _tenant(tenant_id)
        as_of = require_aware(as_of, field_name="as_of")
        records = tuple(
            record
            for record in self._records
            if record.raw.tenant_id == tenant_id
            and record.raw.category is category
            and record.normalized_unit == normalized_unit
            and record.raw.received_at <= as_of
            and record.decision is UsageDecision.ACCEPTED
        )
        superseded = frozenset(
            record.correction_of for record in records if record.correction_of is not None
        )
        effective_records = tuple(
            record for record in records if record.raw.source_event_id not in superseded
        )
        currency = effective_records[0].internal_cost.currency if effective_records else "USD"
        require(
            all(record.internal_cost.currency == currency for record in effective_records),
            "CURRENCY_MISMATCH",
            "usage aggregate currencies differ",
        )
        quantity = sum((record.normalized_quantity for record in effective_records), Decimal("0.000000"))
        internal = sum((record.internal_cost.value for record in effective_records), Decimal("0.000000"))
        charge = sum((record.customer_charge.value for record in effective_records), Decimal("0.000000"))
        total_in_scope = sum(
            1
            for record in self._records
            if record.raw.tenant_id == tenant_id and record.raw.category is category
        )
        coverage = 10_000 if total_in_scope == 0 else len(records) * 10_000 // total_in_scope
        return UsageAggregate(
            tenant_id,
            category,
            normalized_unit,
            quantity,
            ExactAmount(currency, internal),
            ExactAmount(currency, charge),
            tuple(record.raw.event_id for record in records),
            as_of,
            self._closed_through.get(tenant_id),
            coverage,
        )

    def enqueue_pipeline(self, event: RawUsageEvent, *, idempotency_key: str) -> PipelineReceipt:
        """Bounded enqueue surface used to expose backpressure without hidden threads."""

        idempotency_key = _text(idempotency_key, field="idempotency_key")
        key = (event.tenant_id, event.source_event_id)
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt
        if len(self._queue) >= self._queue_capacity:
            return PipelineReceipt(event.source_event_id, PipelineState.BACKPRESSURE_RETRY, attempt, "QUEUE_CAPACITY")
        self._queue.append((event, idempotency_key))
        return PipelineReceipt(event.source_event_id, PipelineState.ACCEPTED, attempt, "QUEUED")

    def process_next_pipeline(self, *, simulate_failure: bool) -> PipelineReceipt:
        require(bool(self._queue), "PIPELINE_QUEUE_EMPTY", "pipeline queue is empty")
        event, idempotency_key = self._queue.pop(0)
        key = (event.tenant_id, event.source_event_id)
        attempt = self._attempts[key]
        if simulate_failure:
            if attempt >= self._maximum_attempts:
                self._dead_letter[key] = (event, idempotency_key)
                return PipelineReceipt(event.source_event_id, PipelineState.DEAD_LETTER, attempt, "MAX_ATTEMPTS")
            return PipelineReceipt(event.source_event_id, PipelineState.RETRY, attempt, "TRANSIENT_FAILURE")
        self.ingest(event, idempotency_key=idempotency_key)
        return PipelineReceipt(event.source_event_id, PipelineState.ACCEPTED, attempt, "INGESTED")

    def submit_pipeline(
        self,
        event: RawUsageEvent,
        *,
        idempotency_key: str,
        simulate_failure: bool,
    ) -> PipelineReceipt:
        queued = self.enqueue_pipeline(event, idempotency_key=idempotency_key)
        if queued.state is PipelineState.BACKPRESSURE_RETRY:
            return queued
        return self.process_next_pipeline(simulate_failure=simulate_failure)

    def replay_dead_letter(self, *, tenant_id: str, source_event_id: str) -> PipelineReceipt:
        key = (_tenant(tenant_id), _text(source_event_id, field="source_event_id"))
        try:
            event, idempotency_key = self._dead_letter.pop(key)
        except KeyError as exc:
            raise DomainError("DEAD_LETTER_NOT_FOUND", "dead-letter event was not found") from exc
        self.ingest(event, idempotency_key=idempotency_key)
        self._attempts[key] += 1
        return PipelineReceipt(source_event_id, PipelineState.REPLAYED, self._attempts[key], "REPLAYED")

    def reconcile_period(
        self,
        *,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
        provider_bill: ExactAmount | None,
        provider_state: ExternalExecutionState,
        evidenced_run_ids: frozenset[str],
        run_evidence_state: ExternalExecutionState,
    ) -> UsageReconciliation:
        tenant_id = _tenant(tenant_id)
        period_start = require_aware(period_start, field_name="period_start")
        period_end = require_aware(period_end, field_name="period_end")
        require(period_end > period_start, "RECONCILIATION_PERIOD_INVALID", "period is invalid")
        records = tuple(
            record
            for record in self._records
            if record.raw.tenant_id == tenant_id and period_start <= record.raw.event_at < period_end
        )
        missing_runs = tuple(sorted({record.raw.run_id for record in records} - evidenced_run_ids))
        if (
            provider_state is not ExternalExecutionState.EXTERNALLY_VERIFIED
            or run_evidence_state is not ExternalExecutionState.EXTERNALLY_VERIFIED
        ):
            return UsageReconciliation(
                tenant_id,
                period_start,
                period_end,
                provider_state,
                run_evidence_state,
                None,
                None,
                missing_runs,
            )
        if provider_bill is None:
            raise DomainError("PROVIDER_BILL_REQUIRED", "verified provider bill is required")
        if records:
            require(
                all(record.internal_cost.currency == records[0].internal_cost.currency for record in records),
                "CURRENCY_MISMATCH",
                "usage reconciliation currencies differ",
            )
            require(
                provider_bill.currency == records[0].internal_cost.currency,
                "CURRENCY_MISMATCH",
                "provider bill currency differs",
            )
        internal = sum((record.internal_cost.value for record in records), Decimal("0.000000"))
        difference = internal - provider_bill.value
        return UsageReconciliation(
            tenant_id,
            period_start,
            period_end,
            provider_state,
            run_evidence_state,
            difference == 0 and not missing_runs,
            difference,
            missing_runs,
        )

    def _required_rule(self, category: ResourceCategory, raw_unit: str) -> NormalizationRule:
        try:
            return self._rules[(category, raw_unit)]
        except KeyError as exc:
            raise DomainError("NORMALIZATION_RULE_NOT_FOUND", "normalization rule was not found") from exc

    def _required_rate(self, event: RawUsageEvent) -> ProviderRate:
        matches = tuple(
            rate
            for rate in self._rates
            if rate.provider_id == event.provider_id
            and rate.category is event.category
            and rate.effective_from <= event.event_at < rate.effective_to
        )
        require(len(matches) == 1, "PROVIDER_RATE_AMBIGUOUS", "exactly one event-time rate is required")
        return matches[0]


class BillingCadence(StrEnum):
    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"


class SubscriptionState(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class InvoiceState(StrEnum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"
    VOID = "VOID"
    REPLACED = "REPLACED"


class InvoiceLineKind(StrEnum):
    PLAN = "PLAN"
    SEAT = "SEAT"
    USAGE = "USAGE"
    PROJECT = "PROJECT"
    DISCOUNT = "DISCOUNT"
    TAX = "TAX"
    ADJUSTMENT = "ADJUSTMENT"


class LineDirection(StrEnum):
    CHARGE = "CHARGE"
    CREDIT = "CREDIT"


class AccountingEventKind(StrEnum):
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    DEFERRED_REVENUE = "DEFERRED_REVENUE"
    REVENUE_RECOGNIZED = "REVENUE_RECOGNIZED"


@dataclass(frozen=True, slots=True)
class Subscription:
    subscription_id: str
    tenant_id: str
    plan_id: str
    cadence: BillingCadence
    state: SubscriptionState
    seats: int
    period_start: datetime
    period_end: datetime
    timezone: str
    revision: int


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    line_id: str
    kind: InvoiceLineKind
    direction: LineDirection
    amount: ExactAmount
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.line_id, field="line_id")
        require(bool(self.source_refs), "INVOICE_LINE_LINEAGE_REQUIRED", "invoice line requires source refs")

    @property
    def signed_value(self) -> Decimal:
        return self.amount.value if self.direction is LineDirection.CHARGE else -self.amount.value


@dataclass(frozen=True, slots=True)
class InvoiceInputSnapshot:
    price_digest: str
    tax_digest: str
    contract_digest: str
    usage_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, field in (
            (self.price_digest, "price_digest"),
            (self.tax_digest, "tax_digest"),
            (self.contract_digest, "contract_digest"),
            (self.usage_digest, "usage_digest"),
        ):
            normalized = _text(value, field=field)
            require(
                normalized.upper() not in {"UNKNOWN", "NOT_RUN", "UNRESOLVED"},
                "INVOICE_INPUT_UNKNOWN",
                f"{field} is unresolved",
                field=field,
            )
        object.__setattr__(self, "created_at", require_aware(self.created_at, field_name="created_at"))


@dataclass(frozen=True, slots=True)
class Invoice:
    invoice_id: str
    tenant_id: str
    subscription_id: str
    state: InvoiceState
    revision: int
    lines: tuple[InvoiceLine, ...]
    inputs: InvoiceInputSnapshot
    total: ExactAmount
    period_start: datetime
    period_end: datetime
    finalized_at: datetime | None
    correction_of: str | None


@dataclass(frozen=True, slots=True)
class EnterpriseCreditTerms:
    tenant_id: str
    net_days: int
    credit_limit: ExactAmount
    outstanding: ExactAmount


@dataclass(frozen=True, slots=True)
class RenewalReceipt:
    subscription_id: str
    cycle_id: str
    renewal_charge: ExactAmount
    included_credit: Decimal
    charge_idempotency_key: str
    credit_idempotency_key: str
    local_only: bool


@dataclass(frozen=True, slots=True)
class DunningCase:
    case_id: str
    tenant_id: str
    invoice_id: str
    failed_payment_ref: str
    attempt: int
    next_attempt_at: datetime
    state: str


@dataclass(frozen=True, slots=True)
class AccountingEvent:
    event_id: str
    tenant_id: str
    invoice_id: str
    kind: AccountingEventKind
    amount: ExactAmount
    occurred_at: datetime
    source_refs: tuple[str, ...]


class SubscriptionInvoicingExactnessService:
    """EB-09 local subscription/invoice state machines without payment or tax authority."""

    authority = "LOCAL_REFERENCE_ONLY"
    tax_engine = ExternalExecutionState.NOT_RUN
    payment_provider = ExternalExecutionState.NOT_RUN
    accounting_system = ExternalExecutionState.NOT_RUN
    certification = CertificationState.NOT_CERTIFIED

    def __init__(self) -> None:
        self._lock = RLock()
        self._subscriptions: dict[tuple[str, str], Subscription] = {}
        self._subscription_commands: dict[tuple[str, str], tuple[str, Subscription]] = {}
        self._invoice_history: dict[tuple[str, str], list[Invoice]] = {}
        self._renewals: dict[tuple[str, str], tuple[str, RenewalReceipt]] = {}
        self._credit_terms: dict[str, EnterpriseCreditTerms] = {}
        self._dunning: dict[tuple[str, str], DunningCase] = {}
        self._accounting: list[AccountingEvent] = []

    def create_subscription(self, subscription: Subscription, *, idempotency_key: str) -> Subscription:
        _tenant(subscription.tenant_id)
        _text(subscription.subscription_id, field="subscription_id")
        require(subscription.seats > 0, "SUBSCRIPTION_SEATS_INVALID", "seats must be positive")
        require(subscription.period_end > subscription.period_start, "SUBSCRIPTION_PERIOD_INVALID", "period invalid")
        try:
            ZoneInfo(subscription.timezone)
        except ZoneInfoNotFoundError as exc:
            raise DomainError("TIMEZONE_UNKNOWN", "billing timezone is unknown") from exc
        return self._subscription_command(
            tenant_id=subscription.tenant_id,
            idempotency_key=idempotency_key,
            fingerprint=canonical_digest(("create", subscription)),
            apply=lambda: self._insert_subscription(subscription),
        )

    def transition(
        self,
        *,
        tenant_id: str,
        subscription_id: str,
        target: SubscriptionState,
        seats: int | None,
        plan_id: str | None,
        idempotency_key: str,
        effective_at: datetime,
    ) -> Subscription:
        tenant_id = _tenant(tenant_id)
        key = (tenant_id, _text(subscription_id, field="subscription_id"))
        current = self._subscriptions.get(key)
        if current is None:
            raise DomainError("SUBSCRIPTION_NOT_FOUND", "subscription not found")
        allowed = {
            SubscriptionState.TRIAL: {SubscriptionState.ACTIVE, SubscriptionState.CANCELLED},
            SubscriptionState.ACTIVE: {SubscriptionState.ACTIVE, SubscriptionState.PAUSED, SubscriptionState.CANCELLED},
            SubscriptionState.PAUSED: {SubscriptionState.ACTIVE, SubscriptionState.CANCELLED},
            SubscriptionState.CANCELLED: {SubscriptionState.ACTIVE},
        }
        require(target in allowed[current.state], "SUBSCRIPTION_TRANSITION_INVALID", "invalid lifecycle transition")
        next_seats = current.seats if seats is None else seats
        require(next_seats > 0, "SUBSCRIPTION_SEATS_INVALID", "seats must be positive")
        effective_at = require_aware(effective_at, field_name="effective_at")
        fingerprint = canonical_digest((target, next_seats, plan_id, effective_at))

        def apply() -> Subscription:
            updated = replace(
                current,
                plan_id=current.plan_id if plan_id is None else _text(plan_id, field="plan_id"),
                state=target,
                seats=next_seats,
                revision=current.revision + 1,
            )
            self._subscriptions[key] = updated
            return updated

        return self._subscription_command(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            apply=apply,
        )

    @staticmethod
    def next_period_boundary(start: datetime, *, cadence: BillingCadence, timezone: str) -> datetime:
        start = require_aware(start, field_name="period_start")
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise DomainError("TIMEZONE_UNKNOWN", "billing timezone is unknown") from exc
        local = start.astimezone(zone)
        months = 1 if cadence is BillingCadence.MONTHLY else 12
        absolute_month = local.year * 12 + local.month - 1 + months
        year, month_index = divmod(absolute_month, 12)
        month = month_index + 1
        day = min(local.day, calendar.monthrange(year, month)[1])
        return local.replace(year=year, month=month, day=day).astimezone(UTC)

    def create_draft(
        self,
        *,
        invoice_id: str,
        tenant_id: str,
        subscription_id: str,
        lines: tuple[InvoiceLine, ...],
        inputs: InvoiceInputSnapshot,
        period_start: datetime,
        period_end: datetime,
    ) -> Invoice:
        tenant_id = _tenant(tenant_id)
        invoice_id = _text(invoice_id, field="invoice_id")
        require(bool(lines), "INVOICE_LINES_REQUIRED", "invoice requires lines")
        require(len({line.kind for line in lines}) >= 1, "INVOICE_LINE_KIND_REQUIRED", "typed lines required")
        total = self._invoice_total(lines)
        invoice = Invoice(
            invoice_id,
            tenant_id,
            _text(subscription_id, field="subscription_id"),
            InvoiceState.DRAFT,
            1,
            lines,
            inputs,
            total,
            require_aware(period_start, field_name="period_start"),
            require_aware(period_end, field_name="period_end"),
            None,
            None,
        )
        require(invoice.period_end > invoice.period_start, "INVOICE_PERIOD_INVALID", "invoice period invalid")
        key = (tenant_id, invoice_id)
        require(key not in self._invoice_history, "INVOICE_EXISTS", "invoice already exists")
        self._invoice_history[key] = [invoice]
        return invoice

    def recalculate_draft(self, *, tenant_id: str, invoice_id: str, lines: tuple[InvoiceLine, ...]) -> Invoice:
        current = self.invoice(tenant_id=tenant_id, invoice_id=invoice_id)
        require(current.state is InvoiceState.DRAFT, "FINAL_INVOICE_IMMUTABLE", "final invoice cannot recalculate")
        updated = replace(current, revision=current.revision + 1, lines=lines, total=self._invoice_total(lines))
        self._invoice_history[(current.tenant_id, current.invoice_id)].append(updated)
        return updated

    def finalize(self, *, tenant_id: str, invoice_id: str, finalized_at: datetime) -> Invoice:
        current = self.invoice(tenant_id=tenant_id, invoice_id=invoice_id)
        require(current.state is InvoiceState.DRAFT, "INVOICE_NOT_DRAFT", "only draft invoices finalize")
        for digest in (
            current.inputs.price_digest,
            current.inputs.tax_digest,
            current.inputs.contract_digest,
            current.inputs.usage_digest,
        ):
            _text(digest, field="input_digest")
        terms = self._credit_terms.get(current.tenant_id)
        if terms is not None:
            _same_currency(terms.outstanding, current.total)
            require(
                terms.outstanding.value + current.total.value <= terms.credit_limit.value,
                "ENTERPRISE_CREDIT_LIMIT_EXCEEDED",
                "invoice exceeds enterprise credit limit",
            )
            self._credit_terms[current.tenant_id] = replace(
                terms,
                outstanding=terms.outstanding.add(current.total),
            )
        finalized_at = require_aware(finalized_at, field_name="finalized_at")
        final = replace(
            current,
            state=InvoiceState.FINALIZED,
            revision=current.revision + 1,
            finalized_at=finalized_at,
        )
        self._invoice_history[(current.tenant_id, current.invoice_id)].append(final)
        self._emit_accounting(final, AccountingEventKind.ACCOUNTS_RECEIVABLE, final.total, finalized_at)
        self._emit_accounting(final, AccountingEventKind.DEFERRED_REVENUE, final.total, finalized_at)
        return final

    def credit_note(
        self,
        *,
        tenant_id: str,
        original_invoice_id: str,
        credit_note_id: str,
        amount: ExactAmount,
        occurred_at: datetime,
    ) -> Invoice:
        original = self.invoice(tenant_id=tenant_id, invoice_id=original_invoice_id)
        require(original.state is InvoiceState.FINALIZED, "INVOICE_NOT_FINAL", "credit note requires final invoice")
        _same_currency(original.total, amount)
        require(amount.value <= original.total.value, "CREDIT_NOTE_EXCEEDS_INVOICE", "credit exceeds invoice")
        occurred_at = require_aware(occurred_at, field_name="occurred_at")
        line = InvoiceLine(
            "credit-line",
            InvoiceLineKind.ADJUSTMENT,
            LineDirection.CREDIT,
            amount,
            (original.invoice_id,),
        )
        credit_note_id = _text(credit_note_id, field="credit_note_id")
        key = (original.tenant_id, credit_note_id)
        require(key not in self._invoice_history, "INVOICE_EXISTS", "invoice already exists")
        corrected = Invoice(
            credit_note_id,
            original.tenant_id,
            original.subscription_id,
            InvoiceState.FINALIZED,
            1,
            (line,),
            original.inputs,
            amount,
            original.period_start,
            original.period_end,
            occurred_at,
            original.invoice_id,
        )
        self._invoice_history[key] = [corrected]
        return corrected

    def replacement_invoice(
        self,
        *,
        tenant_id: str,
        original_invoice_id: str,
        replacement_invoice_id: str,
        lines: tuple[InvoiceLine, ...],
        inputs: InvoiceInputSnapshot,
        occurred_at: datetime,
    ) -> Invoice:
        original = self.invoice(tenant_id=tenant_id, invoice_id=original_invoice_id)
        require(original.state is InvoiceState.FINALIZED, "INVOICE_NOT_FINAL", "replacement requires final invoice")
        occurred_at = require_aware(occurred_at, field_name="occurred_at")
        replaced = replace(
            original,
            state=InvoiceState.REPLACED,
            revision=original.revision + 1,
            finalized_at=occurred_at,
        )
        self._invoice_history[(original.tenant_id, original.invoice_id)].append(replaced)
        draft = self.create_draft(
            invoice_id=replacement_invoice_id,
            tenant_id=original.tenant_id,
            subscription_id=original.subscription_id,
            lines=lines,
            inputs=inputs,
            period_start=original.period_start,
            period_end=original.period_end,
        )
        replacement = replace(draft, correction_of=original.invoice_id)
        self._invoice_history[(replacement.tenant_id, replacement.invoice_id)][-1] = replacement
        return replacement

    def void(self, *, tenant_id: str, invoice_id: str, occurred_at: datetime) -> Invoice:
        current = self.invoice(tenant_id=tenant_id, invoice_id=invoice_id)
        require(current.state is InvoiceState.FINALIZED, "INVOICE_NOT_FINAL", "only final invoice may void")
        voided = replace(
            current,
            state=InvoiceState.VOID,
            revision=current.revision + 1,
            finalized_at=require_aware(occurred_at, field_name="occurred_at"),
        )
        self._invoice_history[(current.tenant_id, current.invoice_id)].append(voided)
        return voided

    def renewal(
        self,
        *,
        tenant_id: str,
        subscription_id: str,
        cycle_id: str,
        renewal_charge: ExactAmount,
        included_credit: Decimal,
        charge_idempotency_key: str,
        credit_idempotency_key: str,
    ) -> RenewalReceipt:
        tenant_id = _tenant(tenant_id)
        subscription_id = _text(subscription_id, field="subscription_id")
        subscription = self._subscriptions.get((tenant_id, subscription_id))
        if subscription is None:
            raise DomainError("SUBSCRIPTION_NOT_FOUND", "subscription not found")
        require(
            subscription.state is SubscriptionState.ACTIVE,
            "SUBSCRIPTION_NOT_ACTIVE",
            "renewal requires active state",
        )
        included_credit = _decimal(included_credit, field="included_credit")
        require(charge_idempotency_key != credit_idempotency_key, "RENEWAL_KEYS_COLLIDE", "keys must be distinct")
        fingerprint = canonical_digest(
            (
                subscription_id,
                cycle_id,
                renewal_charge.canonical,
                included_credit,
                charge_idempotency_key,
                credit_idempotency_key,
            )
        )
        key = (tenant_id, _text(cycle_id, field="cycle_id"))
        prior = self._renewals.get(key)
        if prior is not None:
            require(prior[0] == fingerprint, "RENEWAL_IDEMPOTENCY_CONFLICT", "renewal cycle payload changed")
            return prior[1]
        receipt = RenewalReceipt(
            subscription_id,
            cycle_id,
            renewal_charge,
            included_credit,
            _text(charge_idempotency_key, field="charge_idempotency_key"),
            _text(credit_idempotency_key, field="credit_idempotency_key"),
            True,
        )
        self._renewals[key] = (fingerprint, receipt)
        return receipt

    def set_credit_terms(self, terms: EnterpriseCreditTerms) -> EnterpriseCreditTerms:
        _tenant(terms.tenant_id)
        require(terms.net_days > 0, "PAYMENT_TERMS_INVALID", "net days must be positive")
        _same_currency(terms.credit_limit, terms.outstanding)
        require(
            terms.outstanding.value <= terms.credit_limit.value,
            "CREDIT_LIMIT_INVALID",
            "outstanding exceeds limit",
        )
        self._credit_terms[terms.tenant_id] = terms
        return terms

    def fail_payment(
        self,
        *,
        tenant_id: str,
        invoice_id: str,
        payment_reference: str,
        failed_at: datetime,
        next_attempt_at: datetime,
    ) -> DunningCase:
        invoice = self.invoice(tenant_id=tenant_id, invoice_id=invoice_id)
        require(invoice.state is InvoiceState.FINALIZED, "INVOICE_NOT_FINAL", "dunning requires final invoice")
        failed_at = require_aware(failed_at, field_name="failed_at")
        next_attempt_at = require_aware(next_attempt_at, field_name="next_attempt_at")
        require(next_attempt_at > failed_at, "DUNNING_SCHEDULE_INVALID", "retry must follow failure")
        key = (invoice.tenant_id, _text(payment_reference, field="payment_reference"))
        prior = self._dunning.get(key)
        attempt = 1 if prior is None else prior.attempt + 1
        case = DunningCase(
            f"dunning-{len(self._dunning) + 1:08d}",
            invoice.tenant_id,
            invoice.invoice_id,
            payment_reference,
            attempt,
            next_attempt_at,
            "RETRY_SCHEDULED",
        )
        self._dunning[key] = case
        return case

    def recognize_revenue(
        self, *, tenant_id: str, invoice_id: str, amount: ExactAmount, occurred_at: datetime
    ) -> AccountingEvent:
        invoice = self.invoice(tenant_id=tenant_id, invoice_id=invoice_id)
        require(invoice.state is InvoiceState.FINALIZED, "INVOICE_NOT_FINAL", "recognition requires final invoice")
        _same_currency(invoice.total, amount)
        recognized = sum(
            (
                event.amount.value
                for event in self._accounting
                if event.tenant_id == invoice.tenant_id
                and event.invoice_id == invoice.invoice_id
                and event.kind is AccountingEventKind.REVENUE_RECOGNIZED
            ),
            Decimal("0.000000"),
        )
        require(
            recognized + amount.value <= invoice.total.value,
            "REVENUE_OVER_RECOGNITION",
            "recognition exceeds total",
        )
        return self._emit_accounting(invoice, AccountingEventKind.REVENUE_RECOGNIZED, amount, occurred_at)

    def invoice(self, *, tenant_id: str, invoice_id: str) -> Invoice:
        key = (_tenant(tenant_id), _text(invoice_id, field="invoice_id"))
        history = self._invoice_history.get(key)
        if not history:
            raise DomainError("INVOICE_NOT_FOUND", "invoice was not found")
        return history[-1]

    def invoice_history(self, *, tenant_id: str, invoice_id: str) -> tuple[Invoice, ...]:
        key = (_tenant(tenant_id), _text(invoice_id, field="invoice_id"))
        self.invoice(tenant_id=key[0], invoice_id=key[1])
        return tuple(self._invoice_history[key])

    def accounting_events(self, *, tenant_id: str, invoice_id: str) -> tuple[AccountingEvent, ...]:
        return tuple(
            event
            for event in self._accounting
            if event.tenant_id == _tenant(tenant_id) and event.invoice_id == invoice_id
        )

    def _insert_subscription(self, subscription: Subscription) -> Subscription:
        key = (subscription.tenant_id, subscription.subscription_id)
        require(key not in self._subscriptions, "SUBSCRIPTION_EXISTS", "subscription already exists")
        self._subscriptions[key] = subscription
        return subscription

    def _subscription_command(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        fingerprint: str,
        apply: Callable[[], Subscription],
    ) -> Subscription:
        key = (_tenant(tenant_id), _text(idempotency_key, field="idempotency_key"))
        prior = self._subscription_commands.get(key)
        if prior is not None:
            require(prior[0] == fingerprint, "SUBSCRIPTION_IDEMPOTENCY_CONFLICT", "command payload changed")
            return prior[1]
        result = apply()
        require(isinstance(result, Subscription), "SUBSCRIPTION_RESULT_INVALID", "invalid result")
        self._subscription_commands[key] = (fingerprint, result)
        return result

    @staticmethod
    def _invoice_total(lines: tuple[InvoiceLine, ...]) -> ExactAmount:
        require(bool(lines), "INVOICE_LINES_REQUIRED", "invoice requires lines")
        currency = lines[0].amount.currency
        require(
            all(line.amount.currency == currency for line in lines),
            "CURRENCY_MISMATCH",
            "invoice currencies differ",
        )
        total = sum((line.signed_value for line in lines), Decimal("0.000000"))
        require(total >= 0, "INVOICE_TOTAL_NEGATIVE", "invoice total cannot be negative")
        return ExactAmount(currency, total)

    def _emit_accounting(
        self, invoice: Invoice, kind: AccountingEventKind, amount: ExactAmount, occurred_at: datetime
    ) -> AccountingEvent:
        event = AccountingEvent(
            f"accounting-event-{len(self._accounting) + 1:08d}",
            invoice.tenant_id,
            invoice.invoice_id,
            kind,
            amount,
            require_aware(occurred_at, field_name="occurred_at"),
            (invoice.invoice_id, invoice.inputs.price_digest, invoice.inputs.contract_digest),
        )
        self._accounting.append(event)
        return event


class AnalysisFactState(StrEnum):
    POSTED = "POSTED"
    PENDING = "PENDING"
    ESTIMATED = "ESTIMATED"
    RECOGNIZED = "RECOGNIZED"


class AnalysisFactSource(StrEnum):
    LEDGER = "LEDGER"
    INVOICE = "INVOICE"
    PAYMENT = "PAYMENT"
    USAGE = "USAGE"


class AnalysisFactKind(StrEnum):
    REVENUE = "REVENUE"
    COST = "COST"
    REFUND = "REFUND"


class CostDriver(StrEnum):
    CACHE = "CACHE"
    ROUTING = "ROUTING"
    RETRY = "RETRY"
    TESTING = "TESTING"
    AUTO_REPAIR = "AUTO_REPAIR"


class MarginAlertKind(StrEnum):
    LOSS = "LOSS"
    MARGIN_DECLINE = "MARGIN_DECLINE"
    RATE_DRIFT = "RATE_DRIFT"
    REFUND_ANOMALY = "REFUND_ANOMALY"


class SuggestionState(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED_FOR_PRICE_BOOK_REVIEW = "APPROVED_FOR_PRICE_BOOK_REVIEW"


@dataclass(frozen=True, slots=True)
class AnalysisDimensions:
    task_id: str
    project_id: str
    tenant_id: str
    plan_id: str
    model_id: str
    provider_id: str
    period_start: datetime
    period_end: datetime

    def __post_init__(self) -> None:
        for value, field in (
            (self.task_id, "task_id"),
            (self.project_id, "project_id"),
            (self.plan_id, "plan_id"),
            (self.model_id, "model_id"),
            (self.provider_id, "provider_id"),
        ):
            _text(value, field=field)
        _tenant(self.tenant_id)
        object.__setattr__(self, "period_start", require_aware(self.period_start, field_name="period_start"))
        object.__setattr__(self, "period_end", require_aware(self.period_end, field_name="period_end"))
        require(self.period_end > self.period_start, "FACT_PERIOD_INVALID", "period invalid")


@dataclass(frozen=True, slots=True)
class AnalysisFact:
    fact_id: str
    tenant_id: str
    source: AnalysisFactSource
    source_fact_id: str
    state: AnalysisFactState
    kind: AnalysisFactKind
    amount: ExactAmount
    dimensions: AnalysisDimensions
    occurred_at: datetime
    driver: CostDriver | None = None

    def __post_init__(self) -> None:
        _text(self.fact_id, field="fact_id")
        _tenant(self.tenant_id)
        _text(self.source_fact_id, field="source_fact_id")
        require(self.dimensions.tenant_id == self.tenant_id, "TENANT_ISOLATION_VIOLATION", "dimension mismatch")
        object.__setattr__(self, "occurred_at", require_aware(self.occurred_at, field_name="occurred_at"))


@dataclass(frozen=True, slots=True)
class AllocationRule:
    rule_id: str
    version: int
    weights: tuple[tuple[str, Decimal], ...]
    effective_from: datetime

    def __post_init__(self) -> None:
        _text(self.rule_id, field="rule_id")
        require(self.version > 0, "ALLOCATION_VERSION_INVALID", "version must be positive")
        require(bool(self.weights), "ALLOCATION_WEIGHTS_REQUIRED", "allocation weights are required")
        for target, _ in self.weights:
            _text(target, field="allocation_target")
        require(len(self.weights) == len({key for key, _ in self.weights}), "ALLOCATION_TARGET_DUPLICATE", "duplicate")
        normalized = tuple(_decimal(weight, field="allocation_weight") for _, weight in self.weights)
        require(
            sum(normalized, Decimal("0.000000")) == Decimal("1.000000"),
            "ALLOCATION_NOT_CONSERVING",
            "weights must sum to one",
        )
        object.__setattr__(self, "effective_from", require_aware(self.effective_from, field_name="effective_from"))


@dataclass(frozen=True, slots=True)
class AllocatedFact:
    source_fact_id: str
    rule_id: str
    rule_version: int
    target: str
    amount: ExactAmount


@dataclass(frozen=True, slots=True)
class MarginReport:
    tenant_id: str
    as_of: datetime
    closed_through: datetime | None
    coverage_basis_points: int
    revenue: Decimal
    cost: Decimal
    refund: Decimal
    gross_margin: Decimal
    fact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EstimateVariance:
    estimate_id: str
    p50: ExactAmount
    p80: ExactAmount
    p90: ExactAmount
    actual: ExactAmount
    variance_to_p50: Decimal
    variance_to_p80: Decimal
    variance_to_p90: Decimal


@dataclass(frozen=True, slots=True)
class MarginAlert:
    alert_id: str
    tenant_id: str
    kind: MarginAlertKind
    observed: Decimal
    threshold: Decimal
    as_of: datetime
    source_fact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PriceSuggestion:
    suggestion_id: str
    tenant_id: str
    proposed_by: str
    approved_by: str | None
    state: SuggestionState
    proposed_rate: ExactAmount
    reason: str
    evidence_digest: str


class CostMarginExactnessService:
    """EB-13 append-only fact analytics; it cannot mutate transaction sources or price books."""

    authority = "READ_ONLY_LOCAL_ANALYTICS"
    external_financial_evidence = ExternalExecutionState.NOT_RUN
    price_book_write_authority = False
    certification = CertificationState.NOT_CERTIFIED

    def __init__(self) -> None:
        self._lock = RLock()
        self._facts: dict[tuple[str, str], AnalysisFact] = {}
        self._rules: dict[tuple[str, int], AllocationRule] = {}
        self._closed_through: dict[str, datetime] = {}
        self._alerts: list[MarginAlert] = []
        self._suggestions: dict[tuple[str, str], PriceSuggestion] = {}

    def append_fact(self, fact: AnalysisFact) -> AnalysisFact:
        _tenant(fact.tenant_id)
        require(fact.dimensions.tenant_id == fact.tenant_id, "TENANT_ISOLATION_VIOLATION", "dimension mismatch")
        require(fact.dimensions.period_end > fact.dimensions.period_start, "FACT_PERIOD_INVALID", "period invalid")
        _text(fact.source_fact_id, field="source_fact_id")
        key = (fact.tenant_id, _text(fact.fact_id, field="fact_id"))
        with self._lock:
            prior = self._facts.get(key)
            require(prior is None or prior == fact, "ANALYSIS_FACT_IMMUTABLE", "fact changed in place")
            self._facts[key] = fact
        return fact

    def register_allocation_rule(self, rule: AllocationRule) -> AllocationRule:
        key = (rule.rule_id, rule.version)
        prior = self._rules.get(key)
        require(prior is None or prior == rule, "ALLOCATION_RULE_IMMUTABLE", "allocation rule changed")
        versions = tuple(version for rule_id, version in self._rules if rule_id == rule.rule_id)
        require(rule.version == len(versions) + 1, "ALLOCATION_VERSION_SEQUENCE", "versions must be contiguous")
        self._rules[key] = rule
        return rule

    def allocate(self, *, tenant_id: str, fact_id: str, rule_id: str, version: int) -> tuple[AllocatedFact, ...]:
        fact = self._required_fact(tenant_id, fact_id)
        try:
            rule = self._rules[(rule_id, version)]
        except KeyError as exc:
            raise DomainError("ALLOCATION_RULE_NOT_FOUND", "allocation rule was not found") from exc
        require(rule.effective_from <= fact.occurred_at, "ALLOCATION_RULE_NOT_EFFECTIVE", "rule is not effective")
        remaining = fact.amount.value
        rows: list[AllocatedFact] = []
        for index, (target, weight) in enumerate(rule.weights):
            value = (
                remaining
                if index == len(rule.weights) - 1
                else (fact.amount.value * weight).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
            )
            remaining -= value
            rows.append(
                AllocatedFact(
                    fact.fact_id,
                    rule.rule_id,
                    rule.version,
                    target,
                    ExactAmount(fact.amount.currency, value),
                )
            )
        require(
            sum((row.amount.value for row in rows), Decimal("0.000000")) == fact.amount.value,
            "ALLOCATION_CONSERVATION_FAILED",
            "allocated amount changed total",
        )
        return tuple(rows)

    def close_through(self, *, tenant_id: str, closed_through: datetime) -> None:
        tenant_id = _tenant(tenant_id)
        closed_through = require_aware(closed_through, field_name="closed_through")
        prior = self._closed_through.get(tenant_id)
        require(prior is None or closed_through >= prior, "CLOSE_REGRESSION", "close cannot move backward")
        self._closed_through[tenant_id] = closed_through

    def margin(
        self,
        *,
        tenant_id: str,
        as_of: datetime,
        dimensions: AnalysisDimensions | None = None,
    ) -> MarginReport:
        tenant_id = _tenant(tenant_id)
        as_of = require_aware(as_of, field_name="as_of")
        selected = tuple(
            fact
            for (fact_tenant, _), fact in self._facts.items()
            if fact_tenant == tenant_id
            and fact.occurred_at <= as_of
            and (dimensions is None or fact.dimensions == dimensions)
        )
        currency = selected[0].amount.currency if selected else "USD"
        require(
            all(fact.amount.currency == currency for fact in selected),
            "CURRENCY_MISMATCH",
            "report currencies differ",
        )
        eligible = tuple(
            fact
            for fact in selected
            if fact.state in {AnalysisFactState.POSTED, AnalysisFactState.RECOGNIZED}
        )
        revenue = sum(
            (fact.amount.value for fact in eligible if fact.kind is AnalysisFactKind.REVENUE), Decimal("0.000000")
        )
        cost = sum((fact.amount.value for fact in eligible if fact.kind is AnalysisFactKind.COST), Decimal("0.000000"))
        refund = sum(
            (fact.amount.value for fact in eligible if fact.kind is AnalysisFactKind.REFUND), Decimal("0.000000")
        )
        coverage = 10_000 if not selected else len(eligible) * 10_000 // len(selected)
        return MarginReport(
            tenant_id,
            as_of,
            self._closed_through.get(tenant_id),
            coverage,
            revenue,
            cost,
            refund,
            revenue - cost - refund,
            tuple(sorted(fact.fact_id for fact in eligible)),
        )

    @staticmethod
    def estimate_variance(
        *, estimate_id: str, p50: ExactAmount, p80: ExactAmount, p90: ExactAmount, actual: ExactAmount
    ) -> EstimateVariance:
        _same_currency(p50, p80)
        _same_currency(p50, p90)
        _same_currency(p50, actual)
        require(p50.value <= p80.value <= p90.value, "ESTIMATE_PERCENTILES_INVALID", "percentiles not monotonic")
        return EstimateVariance(
            _text(estimate_id, field="estimate_id"),
            p50,
            p80,
            p90,
            actual,
            actual.value - p50.value,
            actual.value - p80.value,
            actual.value - p90.value,
        )

    def driver_impacts(self, *, tenant_id: str, as_of: datetime) -> dict[CostDriver, Decimal]:
        reportable = tuple(
            fact
            for (fact_tenant, _), fact in self._facts.items()
            if fact_tenant == _tenant(tenant_id)
            and fact.occurred_at <= require_aware(as_of, field_name="as_of")
            and fact.kind is AnalysisFactKind.COST
            and fact.driver is not None
            and fact.state in {AnalysisFactState.POSTED, AnalysisFactState.RECOGNIZED}
        )
        return {
            driver: sum(
                (fact.amount.value for fact in reportable if fact.driver is driver),
                Decimal("0.000000"),
            )
            for driver in CostDriver
        }

    def evaluate_alerts(
        self,
        *,
        report: MarginReport,
        previous_margin: Decimal,
        rate_drift: Decimal,
        refund_ratio: Decimal,
        decline_threshold: Decimal,
        drift_threshold: Decimal,
        refund_threshold: Decimal,
    ) -> tuple[MarginAlert, ...]:
        values = tuple(
            _decimal(value, field="alert_input", signed=True)
            for value in (
                previous_margin,
                rate_drift,
                refund_ratio,
                decline_threshold,
                drift_threshold,
                refund_threshold,
            )
        )
        previous_margin, rate_drift, refund_ratio, decline_threshold, drift_threshold, refund_threshold = values
        require(refund_ratio >= 0, "REFUND_RATIO_NEGATIVE", "refund ratio cannot be negative")
        require(
            decline_threshold >= 0 and drift_threshold >= 0 and refund_threshold >= 0,
            "ALERT_THRESHOLD_NEGATIVE",
            "alert thresholds cannot be negative",
        )
        candidates: list[tuple[MarginAlertKind, Decimal, Decimal]] = []
        if report.gross_margin < 0:
            candidates.append((MarginAlertKind.LOSS, report.gross_margin, Decimal("0.000000")))
        if previous_margin - report.gross_margin > decline_threshold:
            candidates.append(
                (
                    MarginAlertKind.MARGIN_DECLINE,
                    previous_margin - report.gross_margin,
                    decline_threshold,
                )
            )
        if abs(rate_drift) > drift_threshold:
            candidates.append((MarginAlertKind.RATE_DRIFT, rate_drift, drift_threshold))
        if refund_ratio > refund_threshold:
            candidates.append((MarginAlertKind.REFUND_ANOMALY, refund_ratio, refund_threshold))
        alerts = tuple(
            MarginAlert(
                f"margin-alert-{len(self._alerts) + index + 1:08d}",
                report.tenant_id,
                kind,
                observed,
                threshold,
                report.as_of,
                report.fact_ids,
            )
            for index, (kind, observed, threshold) in enumerate(candidates)
        )
        self._alerts.extend(alerts)
        return alerts

    def propose_price(
        self,
        *,
        suggestion_id: str,
        tenant_id: str,
        proposed_rate: ExactAmount,
        proposed_by: str,
        reason: str,
        evidence_digest: str,
    ) -> PriceSuggestion:
        suggestion = PriceSuggestion(
            _text(suggestion_id, field="suggestion_id"),
            _tenant(tenant_id),
            _text(proposed_by, field="proposed_by"),
            None,
            SuggestionState.PENDING_APPROVAL,
            proposed_rate,
            _text(reason, field="reason"),
            _text(evidence_digest, field="evidence_digest"),
        )
        key = (suggestion.tenant_id, suggestion.suggestion_id)
        require(key not in self._suggestions, "PRICE_SUGGESTION_EXISTS", "suggestion exists")
        self._suggestions[key] = suggestion
        return suggestion

    def approve_price_suggestion(
        self, *, tenant_id: str, suggestion_id: str, approved_by: str
    ) -> PriceSuggestion:
        key = (_tenant(tenant_id), _text(suggestion_id, field="suggestion_id"))
        try:
            current = self._suggestions[key]
        except KeyError as exc:
            raise DomainError("PRICE_SUGGESTION_NOT_FOUND", "suggestion was not found") from exc
        approved_by = _text(approved_by, field="approved_by")
        require(current.proposed_by != approved_by, "MAKER_CHECKER_VIOLATION", "self approval forbidden")
        approved = replace(
            current,
            approved_by=approved_by,
            state=SuggestionState.APPROVED_FOR_PRICE_BOOK_REVIEW,
        )
        self._suggestions[key] = approved
        return approved

    def _required_fact(self, tenant_id: str, fact_id: str) -> AnalysisFact:
        try:
            return self._facts[(_tenant(tenant_id), _text(fact_id, field="fact_id"))]
        except KeyError as exc:
            raise DomainError("ANALYSIS_FACT_NOT_FOUND", "analysis fact was not found") from exc
