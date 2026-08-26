from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from json import dumps
from typing import Any

from .errors import DomainError, require
from .money import Money, checked_i64, normalize_currency, require_non_negative, require_positive
from .registry import LocalImplementationState


def require_aware(value: datetime, *, field_name: str) -> datetime:
    require(value.tzinfo is not None, "TIMEZONE_REQUIRED", f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_value(value: Any) -> Any:
    if value is None or type(value) in {bool, int} or isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return require_aware(value, field_name="canonical_datetime").isoformat()
    if isinstance(value, list | tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        require(
            all(type(key) is str for key in value),
            "CANONICAL_MAPPING_KEY_INVALID",
            "canonical mapping keys must be strings",
        )
        return {key: _canonical_value(item) for key, item in value.items()}
    raise DomainError("CANONICAL_VALUE_UNSUPPORTED", "value is not deterministic JSON data")


def canonical_digest(value: Any) -> str:
    canonical = _canonical_value(value)
    return sha256(dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PriceBookState(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class PlanState(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"


class LedgerKind(StrEnum):
    OPENING = "OPENING"
    CREDIT = "CREDIT"
    RESERVE = "RESERVE"
    CAPTURE = "CAPTURE"
    RELEASE = "RELEASE"
    REFUND = "REFUND"
    REVERSAL = "REVERSAL"


class PostingSide(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class QuoteState(StrEnum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PricingModel(StrEnum):
    FIXED = "FIXED"
    CAPPED = "CAPPED"


class ChangeOrderState(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SubscriptionState(StrEnum):
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class InvoiceState(StrEnum):
    OPEN = "OPEN"
    PAID = "PAID"
    VOID = "VOID"


class ProviderPaymentState(StrEnum):
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class RefundState(StrEnum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    EXECUTED_LOCAL = "EXECUTED_LOCAL"
    REVERSED = "REVERSED"
    REJECTED = "REJECTED"


class DisputeState(StrEnum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"
    WITHDRAWN = "WITHDRAWN"


class WorkState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ReadinessState(StrEnum):
    DECLARED = "DECLARED"
    LOCAL_EXECUTED = "LOCAL_EXECUTED"


class ExternalEvidenceState(StrEnum):
    NOT_RUN = "NOT_RUN"
    NOT_CERTIFIED = "NOT_CERTIFIED"


class MigrationMode(StrEnum):
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    LOCAL_ONLY = "LOCAL_ONLY"


class ChargeAuthority(StrEnum):
    EXTERNAL_SYSTEM_NOT_INVOKED = "EXTERNAL_SYSTEM_NOT_INVOKED"
    LOCAL_SIMULATION = "LOCAL_SIMULATION"


@dataclass(frozen=True, slots=True)
class PriceEntry:
    sku: str
    currency: str
    unit_rate_micro: int
    provider_rate_micro: int = 0
    minimum_minor: int = 0

    def __post_init__(self) -> None:
        require(bool(self.sku.strip()), "SKU_REQUIRED", "sku is required")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        require_non_negative(self.unit_rate_micro, field="unit_rate_micro")
        require_non_negative(self.provider_rate_micro, field="provider_rate_micro")
        require(
            self.provider_rate_micro <= self.unit_rate_micro,
            "PROVIDER_RATE_EXCEEDS_TOTAL",
            "provider rate cannot exceed total unit rate",
        )
        require_non_negative(self.minimum_minor, field="minimum_minor")


@dataclass(frozen=True, slots=True)
class PriceBook:
    book_id: str
    version: int
    revision: int
    state: PriceBookState
    effective_from: datetime
    effective_to: datetime | None
    entries: tuple[PriceEntry, ...]
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        require(bool(self.book_id.strip()), "PRICE_BOOK_ID_REQUIRED", "book_id is required")
        require_positive(self.version, field="version")
        require_positive(self.revision, field="revision")
        object.__setattr__(self, "effective_from", require_aware(self.effective_from, field_name="effective_from"))
        if self.effective_to is not None:
            normalized_to = require_aware(self.effective_to, field_name="effective_to")
            require(
                normalized_to > self.effective_from,
                "INVALID_EFFECTIVE_WINDOW",
                "effective_to must follow effective_from",
            )
            object.__setattr__(self, "effective_to", normalized_to)
        require(bool(self.entries), "PRICE_ENTRIES_REQUIRED", "price book requires at least one entry")
        require(
            len({entry.sku for entry in self.entries}) == len(self.entries),
            "DUPLICATE_SKU",
            "sku entries must be unique",
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "book_id": self.book_id,
                "version": self.version,
                "revision": self.revision,
                "state": self.state,
                "effective_from": self.effective_from.isoformat(),
                "effective_to": self.effective_to.isoformat() if self.effective_to else None,
                "entries": [
                    {
                        "sku": entry.sku,
                        "currency": entry.currency,
                        "unit_rate_micro": entry.unit_rate_micro,
                        "provider_rate_micro": entry.provider_rate_micro,
                        "minimum_minor": entry.minimum_minor,
                    }
                    for entry in self.entries
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class Entitlement:
    capability: str
    limit_units: int

    def __post_init__(self) -> None:
        require(bool(self.capability.strip()), "CAPABILITY_REQUIRED", "capability is required")
        require_non_negative(self.limit_units, field="limit_units")


@dataclass(frozen=True, slots=True)
class Plan:
    plan_id: str
    version: int
    revision: int
    state: PlanState
    entitlements: tuple[Entitlement, ...]
    concurrency_limit: int

    def __post_init__(self) -> None:
        require(bool(self.plan_id.strip()), "PLAN_ID_REQUIRED", "plan_id is required")
        require_positive(self.version, field="version")
        require_positive(self.revision, field="revision")
        require_positive(self.concurrency_limit, field="concurrency_limit")
        require(
            len({item.capability for item in self.entitlements}) == len(self.entitlements),
            "DUPLICATE_ENTITLEMENT",
            "entitlement capabilities must be unique",
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "plan_id": self.plan_id,
                "version": self.version,
                "revision": self.revision,
                "state": self.state,
                "concurrency_limit": self.concurrency_limit,
                "entitlements": [(item.capability, item.limit_units) for item in self.entitlements],
            }
        )


@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    tenant_id: str
    plan_id: str
    version: int
    digest: str
    activated_at: datetime
    entitlements: tuple[Entitlement, ...]
    concurrency_limit: int

    def __post_init__(self) -> None:
        require(bool(self.tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(self.plan_id.strip()), "PLAN_ID_REQUIRED", "plan_id is required")
        require_positive(self.version, field="version")
        require(bool(self.digest.strip()), "PLAN_DIGEST_REQUIRED", "plan digest is required")
        object.__setattr__(self, "activated_at", require_aware(self.activated_at, field_name="activated_at"))
        require_positive(self.concurrency_limit, field="concurrency_limit")


@dataclass(frozen=True, slots=True)
class Posting:
    account: str
    side: PostingSide
    money: Money

    def __post_init__(self) -> None:
        require(bool(self.account.strip()), "ACCOUNT_REQUIRED", "account is required")
        require_positive(self.money.minor, field="posting_minor")


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    tenant_id: str
    transaction_id: str
    sequence: int
    idempotency_key: str
    kind: LedgerKind
    reference: str
    occurred_at: datetime
    postings: tuple[Posting, ...]
    effect_available_minor: int
    effect_reserved_minor: int
    effect_captured_minor: int
    reversal_of: str | None = None

    def __post_init__(self) -> None:
        require(bool(self.tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(self.transaction_id.strip()), "TRANSACTION_ID_REQUIRED", "transaction_id is required")
        require_positive(self.sequence, field="sequence")
        require(bool(self.idempotency_key.strip()), "IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required")
        object.__setattr__(self, "occurred_at", require_aware(self.occurred_at, field_name="occurred_at"))
        require(len(self.postings) >= 2, "POSTINGS_REQUIRED", "a ledger transaction requires at least two postings")
        checked_i64(self.effect_available_minor, field="effect_available_minor")
        checked_i64(self.effect_reserved_minor, field="effect_reserved_minor")
        checked_i64(self.effect_captured_minor, field="effect_captured_minor")


@dataclass(frozen=True, slots=True)
class WalletBalance:
    tenant_id: str
    currency: str
    available_minor: int
    reserved_minor: int
    captured_minor: int
    transaction_count: int

    def __post_init__(self) -> None:
        require(bool(self.tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        require_non_negative(self.available_minor, field="available_minor")
        require_non_negative(self.reserved_minor, field="reserved_minor")
        require_non_negative(self.captured_minor, field="captured_minor")
        require_non_negative(self.transaction_count, field="transaction_count")


@dataclass(frozen=True, slots=True)
class UsageEvent:
    tenant_id: str
    event_id: str
    sku: str
    quantity_micro: int
    occurred_at: datetime
    byok: bool
    correlation_id: str

    def __post_init__(self) -> None:
        require(bool(self.tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(self.event_id.strip()), "EVENT_ID_REQUIRED", "event_id is required")
        require(bool(self.sku.strip()), "SKU_REQUIRED", "sku is required")
        require_positive(self.quantity_micro, field="quantity_micro")
        object.__setattr__(self, "occurred_at", require_aware(self.occurred_at, field_name="occurred_at"))
        require(bool(self.correlation_id.strip()), "CORRELATION_ID_REQUIRED", "correlation_id is required")


@dataclass(frozen=True, slots=True)
class RatedUsage:
    event: UsageEvent
    price_book_id: str
    price_book_version: int
    price_book_digest: str
    currency: str
    platform_cost_micro: int
    provider_cost_micro: int
    billable_micro: int
    billable_minor: int


@dataclass(frozen=True, slots=True)
class EstimateDistribution:
    p50_minor: int
    p80_minor: int
    p90_minor: int
    machine_eta_seconds: int
    sample_count: int

    def __post_init__(self) -> None:
        require_non_negative(self.p50_minor, field="p50_minor")
        require_non_negative(self.p80_minor, field="p80_minor")
        require_non_negative(self.p90_minor, field="p90_minor")
        require(
            self.p50_minor <= self.p80_minor <= self.p90_minor,
            "INVALID_ESTIMATE_DISTRIBUTION",
            "estimate percentiles must be monotonic",
        )
        require_non_negative(self.machine_eta_seconds, field="machine_eta_seconds")
        require_positive(self.sample_count, field="sample_count")


@dataclass(frozen=True, slots=True)
class Quote:
    quote_id: str
    tenant_id: str
    scope_digest: str
    money: Money
    estimate: EstimateDistribution
    estimate_snapshot_digest: str
    price_book_id: str
    price_book_version: int
    price_book_digest: str
    model_strategy: str
    human_time_reference_seconds: int
    confidence_basis_points: int
    hard_cap_minor: int
    threshold_percents: tuple[int, ...]
    expires_at: datetime
    state: QuoteState
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    reserve_transaction_id: str | None = None
    committed_spend_minor: int = 0


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    projected_minor: int
    hard_cap_minor: int
    crossed_thresholds: tuple[int, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ProjectContract:
    contract_id: str
    tenant_id: str
    model: PricingModel
    scope_digest: str
    currency: str
    fixed_minor: int
    cap_minor: int
    version: int


@dataclass(frozen=True, slots=True)
class ChangeOrder:
    change_id: str
    contract_id: str
    proposed_by: str
    new_scope_digest: str
    delta_minor: int
    state: ChangeOrderState
    decided_by: str | None = None


@dataclass(frozen=True, slots=True)
class Acceptance:
    acceptance_id: str
    contract_id: str
    milestone: str
    accepted_by: str
    accepted_at: datetime
    scope_digest: str


@dataclass(frozen=True, slots=True)
class Subscription:
    subscription_id: str
    tenant_id: str
    plan_snapshot: PlanSnapshot
    state: SubscriptionState
    started_at: datetime


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    line_id: str
    description: str
    money: Money

    def __post_init__(self) -> None:
        require(bool(self.line_id.strip()), "LINE_ID_REQUIRED", "line_id is required")
        require_non_negative(self.money.minor, field="invoice_line_minor")


@dataclass(frozen=True, slots=True)
class Invoice:
    invoice_id: str
    tenant_id: str
    subscription_id: str
    currency: str
    lines: tuple[InvoiceLine, ...]
    issued_at: datetime
    due_at: datetime
    digest: str

    @property
    def total_minor(self) -> int:
        return checked_i64(sum(line.money.minor for line in self.lines), field="invoice_total_minor")


@dataclass(frozen=True, slots=True)
class CreditNote:
    credit_note_id: str
    invoice_id: str
    money: Money
    reason: str
    issued_at: datetime


@dataclass(frozen=True, slots=True)
class DunningEvent:
    event_id: str
    invoice_id: str
    sequence: int
    state: SubscriptionState
    occurred_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    provider: str
    provider_event_id: str
    tenant_id: str
    payment_reference: str
    state: ProviderPaymentState
    payload_digest: str
    received_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    reconciliation_id: str
    tenant_id: str
    reference: str
    currency: str
    ledger_minor: int
    invoice_minor: int
    provider_minor: int
    bank_minor: int
    matched: bool
    suspense_id: str | None


@dataclass(frozen=True, slots=True)
class RefundRequest:
    refund_id: str
    tenant_id: str
    payment_reference: str
    money: Money
    requested_by: str
    reason: str
    state: RefundState
    approved_by: str | None = None
    ledger_transaction_id: str | None = None


@dataclass(frozen=True, slots=True)
class DisputeCase:
    dispute_id: str
    tenant_id: str
    payment_reference: str
    money: Money
    opened_by: str
    reason: str
    state: DisputeState
    decided_by: str | None = None


@dataclass(frozen=True, slots=True)
class EnterpriseAgreement:
    agreement_id: str
    tenant_id: str
    currency: str
    committed_minor: int
    credit_limit_minor: int
    byok_secret_ref: str | None
    sla_credit_cap_minor: int

    def __post_init__(self) -> None:
        require(bool(self.agreement_id.strip()), "AGREEMENT_ID_REQUIRED", "agreement_id is required")
        require(bool(self.tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        require_non_negative(self.committed_minor, field="committed_minor")
        require_non_negative(self.credit_limit_minor, field="credit_limit_minor")
        require_non_negative(self.sla_credit_cap_minor, field="sla_credit_cap_minor")


@dataclass(frozen=True, slots=True)
class MarginView:
    currency: str
    revenue_minor: int
    provider_cost_minor: int
    runner_cost_minor: int
    support_cost_minor: int
    margin_minor: int
    margin_basis_points: int | None


@dataclass(frozen=True, slots=True)
class AdminSnapshot:
    tenant_id: str
    currency: str
    available_minor: int
    reserved_minor: int
    captured_minor: int
    rated_usage_count: int
    suspense_count: int
    work_item_count: int
    kill_switch_enabled: bool


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    tenant_id: str
    principal_id: str
    role: str
    action: str
    reason: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    sequence: int
    tenant_id: str
    correlation_id: str
    actor: str
    action: str
    outcome: str
    occurred_at: datetime
    details_digest: str


@dataclass(frozen=True, slots=True)
class WorkItem:
    work_id: str
    tenant_id: str
    correlation_id: str
    operation: str
    state: WorkState
    attempt: int
    replay_of: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    comparison_id: str
    tenant_id: str
    reference: str
    external_minor: int
    simulated_minor: int
    matched: bool


@dataclass(frozen=True, slots=True)
class ChargeDecision:
    tenant_id: str
    mode: MigrationMode
    authority: ChargeAuthority
    simulation_only: bool


@dataclass(frozen=True, slots=True)
class QualificationReport:
    readiness: ReadinessState
    handler_results: tuple[tuple[str, LocalImplementationState], ...]
    external_evidence: tuple[tuple[str, ExternalEvidenceState], ...]
    limitations: tuple[str, ...] = field(default_factory=tuple)
