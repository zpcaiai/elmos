from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from threading import RLock

from .errors import DomainError, require
from .models import canonical_digest, require_aware
from .money import (
    checked_add,
    checked_i64,
    checked_mul,
    normalize_currency,
    require_non_negative,
    require_positive,
    round_half_up_div,
)


def _required_text(value: str, *, field: str) -> str:
    require(bool(value.strip()), "TEXT_REQUIRED", f"{field} is required", field=field)
    return value


def _required_tenant(value: str) -> str:
    _required_text(value, field="tenant_id")
    require(value != "*", "WILDCARD_TENANT_FORBIDDEN", "wildcard tenant scope is forbidden")
    return value


def _checked_sum(values: tuple[int, ...], *, field: str) -> int:
    result = 0
    for value in values:
        result = checked_add(result, value, field=field)
    return result


def _scale_basis_points(amount: int, basis_points: int, *, field: str) -> int:
    require_non_negative(amount, field=field)
    require_non_negative(basis_points, field=f"{field}_basis_points")
    numerator = checked_mul(amount, basis_points, field=f"{field}_numerator")
    return round_half_up_div(numerator, 10_000)


def _stable_bucket(value: str) -> int:
    _required_text(value, field="bucket_subject")
    return int.from_bytes(sha256(value.encode()).digest()[:8], "big") % 10_000


_MONEY_QUANTUM = Decimal("0.000001")


def _exact_decimal(value: Decimal, *, field: str, positive: bool = False) -> Decimal:
    require(isinstance(value, Decimal), "DECIMAL_REQUIRED", f"{field} must be Decimal", field=field)
    require(value.is_finite(), "DECIMAL_NOT_FINITE", f"{field} must be finite", field=field)
    try:
        normalized = value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise DomainError("DECIMAL_INVALID", f"{field} cannot be normalized") from exc
    require(normalized == value, "DECIMAL_SCALE_EXCEEDED", f"{field} supports at most six decimals", field=field)
    if positive:
        require(normalized > 0, "AMOUNT_NOT_POSITIVE", f"{field} must be positive", field=field)
    else:
        require(normalized >= 0, "AMOUNT_NEGATIVE", f"{field} must be non-negative", field=field)
    return normalized


@dataclass(frozen=True, slots=True)
class ExactAmount:
    """Exact six-decimal commercial amount; binary floating point is never accepted."""

    currency: str
    value: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        object.__setattr__(self, "value", _exact_decimal(self.value, field="amount"))

    @classmethod
    def zero(cls, currency: str) -> ExactAmount:
        return cls(currency, Decimal("0.000000"))

    def add(self, other: ExactAmount) -> ExactAmount:
        self._same_currency(other)
        return ExactAmount(self.currency, self.value + other.value)

    def subtract(self, other: ExactAmount) -> ExactAmount:
        self._same_currency(other)
        require(self.value >= other.value, "AMOUNT_UNDERFLOW", "amount subtraction would be negative")
        return ExactAmount(self.currency, self.value - other.value)

    def scale(self, factor: Decimal) -> ExactAmount:
        normalized_factor = _exact_decimal(factor, field="factor")
        scaled = (self.value * normalized_factor).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        return ExactAmount(self.currency, scaled)

    def minimum(self, other: ExactAmount) -> ExactAmount:
        self._same_currency(other)
        return self if self.value <= other.value else other

    def _same_currency(self, other: ExactAmount) -> None:
        require(self.currency == other.currency, "CURRENCY_MISMATCH", "commercial amounts use different currencies")

    @property
    def canonical(self) -> str:
        return f"{self.currency}:{self.value:.6f}"


class BillingRoute(StrEnum):
    SUBSCRIPTION = "SUBSCRIPTION"
    PREPAID_EXECUTION_CREDITS = "PREPAID_EXECUTION_CREDITS"
    ACTUAL_USAGE = "ACTUAL_USAGE"
    CAPPED_PROJECT = "CAPPED_PROJECT"
    FIXED_PROJECT = "FIXED_PROJECT"
    ENTERPRISE_ANNUAL = "ENTERPRISE_ANNUAL"


class RateComponentKind(StrEnum):
    MODEL = "MODEL"
    SANDBOX = "SANDBOX"
    TEST = "TEST"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    ORCHESTRATION = "ORCHESTRATION"


class ModelFunding(StrEnum):
    MANAGED = "MANAGED"
    BYOK = "BYOK"


class CommercialRecordState(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class RateComponent:
    kind: RateComponentKind
    unit_name: str
    managed_rate_micro: int
    byok_rate_micro: int

    def __post_init__(self) -> None:
        _required_text(self.unit_name, field="unit_name")
        require_non_negative(self.managed_rate_micro, field="managed_rate_micro")
        require_non_negative(self.byok_rate_micro, field="byok_rate_micro")
        if self.kind is RateComponentKind.MODEL:
            require(
                self.byok_rate_micro == 0,
                "BYOK_MODEL_RATE_MUST_BE_ZERO",
                "BYOK cannot bill a managed-model component",
            )


@dataclass(frozen=True, slots=True)
class TaskBillingRule:
    task_kind: str
    route: BillingRoute

    def __post_init__(self) -> None:
        _required_text(self.task_kind, field="task_kind")


@dataclass(frozen=True, slots=True)
class ProjectSkuContract:
    sku_id: str
    input_contract_digest: str
    output_contract_digest: str
    maximum_scope_units: int
    acceptance_policy_digest: str
    included_revision_rounds: int

    def __post_init__(self) -> None:
        _required_text(self.sku_id, field="sku_id")
        _required_text(self.input_contract_digest, field="input_contract_digest")
        _required_text(self.output_contract_digest, field="output_contract_digest")
        require_positive(self.maximum_scope_units, field="maximum_scope_units")
        _required_text(self.acceptance_policy_digest, field="acceptance_policy_digest")
        require_non_negative(self.included_revision_rounds, field="included_revision_rounds")

    def validate_delivery(self, *, input_digest: str, output_digest: str, scope_units: int) -> None:
        require(input_digest == self.input_contract_digest, "SKU_INPUT_CONTRACT_MISMATCH", "input is outside SKU")
        require(output_digest == self.output_contract_digest, "SKU_OUTPUT_CONTRACT_MISMATCH", "output is outside SKU")
        require_non_negative(scope_units, field="scope_units")
        require(scope_units <= self.maximum_scope_units, "SKU_SCOPE_LIMIT_EXCEEDED", "scope exceeds SKU limit")


@dataclass(frozen=True, slots=True)
class PriceProductVersion:
    tenant_id: str
    book_id: str
    version: int
    currency: str
    effective_from: datetime
    effective_to: datetime | None
    state: CommercialRecordState
    created_by: str
    approved_by: str | None
    rate_components: tuple[RateComponent, ...]
    billing_rules: tuple[TaskBillingRule, ...]
    project_skus: tuple[ProjectSkuContract, ...]
    example_only: bool
    impact_targets: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.book_id, field="book_id")
        require_positive(self.version, field="version")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        object.__setattr__(self, "effective_from", require_aware(self.effective_from, field_name="effective_from"))
        if self.effective_to is not None:
            normalized_to = require_aware(self.effective_to, field_name="effective_to")
            require(normalized_to > self.effective_from, "PRICE_WINDOW_INVALID", "effective_to must follow start")
            object.__setattr__(self, "effective_to", normalized_to)
        _required_text(self.created_by, field="created_by")
        require(
            {item.kind for item in self.rate_components} == set(RateComponentKind),
            "RATE_COMPONENT_COVERAGE_INCOMPLETE",
            "all six independent rate components are required",
        )
        require(
            len({item.kind for item in self.rate_components}) == len(self.rate_components),
            "DUPLICATE_RATE_COMPONENT",
            "rate components must be unique",
        )
        require(
            len({item.task_kind for item in self.billing_rules}) == len(self.billing_rules),
            "DUPLICATE_BILLING_RULE",
            "task billing rules must be deterministic",
        )
        require(
            len({item.sku_id for item in self.project_skus}) == len(self.project_skus),
            "DUPLICATE_PROJECT_SKU",
            "project SKU identities must be unique",
        )
        require(bool(self.impact_targets), "IMPACT_ANALYSIS_REQUIRED", "downstream impact targets are required")
        require(
            all(bool(target.strip()) for target in self.impact_targets),
            "IMPACT_TARGET_INVALID",
            "impact targets cannot be blank",
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "book_id": self.book_id,
                "version": self.version,
                "currency": self.currency,
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
                "state": self.state,
                "created_by": self.created_by,
                "approved_by": self.approved_by,
                "rate_components": [
                    (item.kind, item.unit_name, item.managed_rate_micro, item.byok_rate_micro)
                    for item in self.rate_components
                ],
                "billing_rules": [(item.task_kind, item.route) for item in self.billing_rules],
                "project_skus": [
                    (
                        item.sku_id,
                        item.input_contract_digest,
                        item.output_contract_digest,
                        item.maximum_scope_units,
                        item.acceptance_policy_digest,
                        item.included_revision_rounds,
                    )
                    for item in self.project_skus
                ],
                "example_only": self.example_only,
                "impact_targets": self.impact_targets,
            }
        )


@dataclass(frozen=True, slots=True)
class PricePresentation:
    currency: str
    customer_amount_minor: int
    execution_credit_units: int
    raw_token_units_cost_detail: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        require_non_negative(self.customer_amount_minor, field="customer_amount_minor")
        require_non_negative(self.execution_credit_units, field="execution_credit_units")
        require_non_negative(self.raw_token_units_cost_detail, field="raw_token_units_cost_detail")


@dataclass(frozen=True, slots=True)
class PriceExperiment:
    tenant_id: str
    experiment_id: str
    book_id: str
    control_version: int
    variant_version: int
    allocation_basis_points: int
    active: bool
    revision: int

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.experiment_id, field="experiment_id")
        _required_text(self.book_id, field="book_id")
        require_positive(self.control_version, field="control_version")
        require_positive(self.variant_version, field="variant_version")
        require(
            0 <= self.allocation_basis_points <= 10_000,
            "EXPERIMENT_ALLOCATION_INVALID",
            "allocation must be in 0..10000 basis points",
        )
        checked_i64(self.allocation_basis_points, field="allocation_basis_points")
        require_positive(self.revision, field="revision")


@dataclass(frozen=True, slots=True)
class CommercialAuditEvent:
    tenant_id: str
    sequence: int
    aggregate_type: str
    aggregate_id: str
    action: str
    actor: str
    occurred_at: datetime
    before_digest: str | None
    after_digest: str
    impact_targets: tuple[str, ...]


class PricingProductClosureService:
    """Tenant-bound, version-explicit local pricing model; never a charging authority."""

    authority = "LOCAL_REFERENCE_ONLY"
    external_side_effects = False

    def __init__(self) -> None:
        self._lock = RLock()
        self._versions: dict[tuple[str, str, int], PriceProductVersion] = {}
        self._experiments: dict[tuple[str, str], PriceExperiment] = {}
        self._audit: list[CommercialAuditEvent] = []
        self._sequence: dict[str, int] = {}

    def create_version(
        self,
        *,
        tenant_id: str,
        book_id: str,
        version: int,
        currency: str,
        effective_from: datetime,
        effective_to: datetime | None,
        created_by: str,
        rate_components: tuple[RateComponent, ...],
        billing_rules: tuple[TaskBillingRule, ...],
        project_skus: tuple[ProjectSkuContract, ...],
        example_only: bool,
        impact_targets: tuple[str, ...],
        occurred_at: datetime,
    ) -> PriceProductVersion:
        _required_tenant(tenant_id)
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            key = (tenant_id, book_id, version)
            require(key not in self._versions, "PRICE_VERSION_EXISTS", "price version already exists")
            earlier = self.history(tenant_id=tenant_id, book_id=book_id)
            require(version == len(earlier) + 1, "PRICE_VERSION_SEQUENCE_INVALID", "versions must be contiguous")
            draft = PriceProductVersion(
                tenant_id=tenant_id,
                book_id=book_id,
                version=version,
                currency=currency,
                effective_from=effective_from,
                effective_to=effective_to,
                state=CommercialRecordState.DRAFT,
                created_by=created_by,
                approved_by=None,
                rate_components=rate_components,
                billing_rules=billing_rules,
                project_skus=project_skus,
                example_only=example_only,
                impact_targets=impact_targets,
            )
            before = earlier[-1].digest if earlier else None
            self._versions[key] = draft
            self._record_audit(
                tenant_id=tenant_id,
                aggregate_type="PRICE_BOOK",
                aggregate_id=f"{book_id}:{version}",
                action="CREATE_VERSION",
                actor=created_by,
                occurred_at=normalized_at,
                before_digest=before,
                after_digest=draft.digest,
                impact_targets=impact_targets,
            )
            return draft

    def approve(
        self,
        *,
        tenant_id: str,
        book_id: str,
        version: int,
        expected_digest: str,
        approved_by: str,
        explicit_example_authorization: bool,
        occurred_at: datetime,
    ) -> PriceProductVersion:
        _required_text(approved_by, field="approved_by")
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            current = self._required_version(tenant_id, book_id, version)
            if current.state is CommercialRecordState.APPROVED:
                require(current.approved_by == approved_by, "APPROVAL_CONFLICT", "version has another approver")
                return current
            require(current.state is CommercialRecordState.DRAFT, "PRICE_VERSION_NOT_DRAFT", "only drafts approve")
            require(current.digest == expected_digest, "STALE_PRICE_VERSION", "price version digest changed")
            require(current.created_by != approved_by, "MAKER_CHECKER_VIOLATION", "creator cannot approve")
            require(
                not current.example_only or explicit_example_authorization,
                "EXAMPLE_PRICE_PRODUCTION_FORBIDDEN",
                "example pricing requires explicit approval",
            )
            approved = replace(current, state=CommercialRecordState.APPROVED, approved_by=approved_by)
            self._versions[(tenant_id, book_id, version)] = approved
            self._record_audit(
                tenant_id=tenant_id,
                aggregate_type="PRICE_BOOK",
                aggregate_id=f"{book_id}:{version}",
                action="APPROVE_VERSION",
                actor=approved_by,
                occurred_at=normalized_at,
                before_digest=current.digest,
                after_digest=approved.digest,
                impact_targets=current.impact_targets,
            )
            return approved

    def resolve_route(self, *, tenant_id: str, book_id: str, version: int, task_kind: str) -> BillingRoute:
        current = self._required_approved(tenant_id, book_id, version)
        matches = tuple(rule.route for rule in current.billing_rules if rule.task_kind == task_kind)
        require(len(matches) == 1, "TASK_BILLING_ROUTE_NOT_FOUND", "task kind has no deterministic route")
        return matches[0]

    def rate_component(
        self,
        *,
        tenant_id: str,
        book_id: str,
        version: int,
        kind: RateComponentKind,
        funding: ModelFunding,
    ) -> int:
        current = self._required_approved(tenant_id, book_id, version)
        component = next(item for item in current.rate_components if item.kind is kind)
        return component.managed_rate_micro if funding is ModelFunding.MANAGED else component.byok_rate_micro

    def present_price(
        self,
        *,
        tenant_id: str,
        book_id: str,
        version: int,
        customer_amount_minor: int,
        execution_credit_units: int,
        raw_token_units: int,
    ) -> PricePresentation:
        self._required_approved(tenant_id, book_id, version)
        return PricePresentation(
            currency=self._required_version(tenant_id, book_id, version).currency,
            customer_amount_minor=customer_amount_minor,
            execution_credit_units=execution_credit_units,
            raw_token_units_cost_detail=raw_token_units,
        )

    def configure_experiment(
        self,
        *,
        tenant_id: str,
        experiment_id: str,
        book_id: str,
        control_version: int,
        variant_version: int,
        allocation_basis_points: int,
        actor: str,
        occurred_at: datetime,
    ) -> PriceExperiment:
        self._required_approved(tenant_id, book_id, control_version)
        self._required_approved(tenant_id, book_id, variant_version)
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            key = (tenant_id, experiment_id)
            require(key not in self._experiments, "PRICE_EXPERIMENT_EXISTS", "experiment already exists")
            experiment = PriceExperiment(
                tenant_id=tenant_id,
                experiment_id=experiment_id,
                book_id=book_id,
                control_version=control_version,
                variant_version=variant_version,
                allocation_basis_points=allocation_basis_points,
                active=True,
                revision=1,
            )
            self._experiments[key] = experiment
            self._record_audit(
                tenant_id=tenant_id,
                aggregate_type="PRICE_EXPERIMENT",
                aggregate_id=experiment_id,
                action="CONFIGURE",
                actor=actor,
                occurred_at=normalized_at,
                before_digest=None,
                after_digest=canonical_digest(
                    {
                        "control_version": control_version,
                        "variant_version": variant_version,
                        "allocation_basis_points": allocation_basis_points,
                    }
                ),
                impact_targets=("new-price-bindings",),
            )
            return experiment

    def assign_experiment(self, *, tenant_id: str, experiment_id: str, subject_key: str) -> int:
        try:
            experiment = self._experiments[(tenant_id, experiment_id)]
        except KeyError as exc:
            if any(key[1] == experiment_id for key in self._experiments):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "experiment belongs to another tenant") from exc
            raise DomainError("PRICE_EXPERIMENT_NOT_FOUND", "experiment was not found") from exc
        if not experiment.active:
            return experiment.control_version
        return (
            experiment.variant_version
            if _stable_bucket(subject_key) < experiment.allocation_basis_points
            else experiment.control_version
        )

    def rollback_experiment(
        self,
        *,
        tenant_id: str,
        experiment_id: str,
        actor: str,
        occurred_at: datetime,
    ) -> PriceExperiment:
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            current = self._experiments.get((tenant_id, experiment_id))
            if current is None:
                raise DomainError("PRICE_EXPERIMENT_NOT_FOUND", "experiment was not found")
            if not current.active:
                return current
            rolled_back = replace(current, active=False, revision=checked_add(current.revision, 1, field="revision"))
            self._experiments[(tenant_id, experiment_id)] = rolled_back
            self._record_audit(
                tenant_id=tenant_id,
                aggregate_type="PRICE_EXPERIMENT",
                aggregate_id=experiment_id,
                action="ROLLBACK",
                actor=actor,
                occurred_at=normalized_at,
                before_digest=canonical_digest({"active": True, "revision": current.revision}),
                after_digest=canonical_digest({"active": False, "revision": rolled_back.revision}),
                impact_targets=("new-price-bindings",),
            )
            return rolled_back

    def history(self, *, tenant_id: str, book_id: str) -> tuple[PriceProductVersion, ...]:
        _required_tenant(tenant_id)
        return tuple(
            version
            for key, version in sorted(self._versions.items(), key=lambda item: item[0][2])
            if key[0] == tenant_id and key[1] == book_id
        )

    def audit_events(self, *, tenant_id: str) -> tuple[CommercialAuditEvent, ...]:
        _required_tenant(tenant_id)
        return tuple(event for event in self._audit if event.tenant_id == tenant_id)

    def _required_approved(self, tenant_id: str, book_id: str, version: int) -> PriceProductVersion:
        current = self._required_version(tenant_id, book_id, version)
        require(current.state is CommercialRecordState.APPROVED, "PRICE_VERSION_NOT_APPROVED", "version not approved")
        return current

    def _required_version(self, tenant_id: str, book_id: str, version: int) -> PriceProductVersion:
        _required_tenant(tenant_id)
        try:
            return self._versions[(tenant_id, book_id, version)]
        except KeyError as exc:
            if any(key[1:] == (book_id, version) for key in self._versions):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "price version belongs to another tenant") from exc
            raise DomainError("PRICE_VERSION_NOT_FOUND", "price version was not found") from exc

    def _record_audit(
        self,
        *,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        action: str,
        actor: str,
        occurred_at: datetime,
        before_digest: str | None,
        after_digest: str,
        impact_targets: tuple[str, ...],
    ) -> None:
        sequence = checked_add(self._sequence.get(tenant_id, 0), 1, field="audit_sequence")
        self._sequence[tenant_id] = sequence
        self._audit.append(
            CommercialAuditEvent(
                tenant_id=tenant_id,
                sequence=sequence,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                action=action,
                actor=_required_text(actor, field="actor"),
                occurred_at=occurred_at,
                before_digest=before_digest,
                after_digest=after_digest,
                impact_targets=impact_targets,
            )
        )


class PlanTier(StrEnum):
    FREE = "FREE"
    PRO = "PRO"
    BUILDER = "BUILDER"
    TEAM = "TEAM"
    ENTERPRISE = "ENTERPRISE"


class PlanLifecycleState(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class PlanTransition(StrEnum):
    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"
    CANCEL = "CANCEL"
    PAUSE = "PAUSE"
    RESTART = "RESTART"
    END_TRIAL = "END_TRIAL"


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    tenant_id: str
    plan_id: str
    version: int
    tier: PlanTier
    seat_limit: int
    concurrent_task_limit: int
    model_tier: str
    retention_days: int
    storage_bytes: int
    features: tuple[str, ...]
    paid_credit_minor: int
    promotional_credit_minor: int
    published_at: datetime

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.plan_id, field="plan_id")
        require_positive(self.version, field="version")
        require_non_negative(self.seat_limit, field="seat_limit")
        require_positive(self.concurrent_task_limit, field="concurrent_task_limit")
        _required_text(self.model_tier, field="model_tier")
        require_non_negative(self.retention_days, field="retention_days")
        require_non_negative(self.storage_bytes, field="storage_bytes")
        require(len(set(self.features)) == len(self.features), "DUPLICATE_FEATURE", "features must be unique")
        require(all(bool(item.strip()) for item in self.features), "FEATURE_INVALID", "features cannot be blank")
        require_non_negative(self.paid_credit_minor, field="paid_credit_minor")
        require_non_negative(self.promotional_credit_minor, field="promotional_credit_minor")
        object.__setattr__(self, "published_at", require_aware(self.published_at, field_name="published_at"))

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "plan_id": self.plan_id,
                "version": self.version,
                "tier": self.tier,
                "seat_limit": self.seat_limit,
                "concurrent_task_limit": self.concurrent_task_limit,
                "model_tier": self.model_tier,
                "retention_days": self.retention_days,
                "storage_bytes": self.storage_bytes,
                "features": self.features,
                "paid_credit_minor": self.paid_credit_minor,
                "promotional_credit_minor": self.promotional_credit_minor,
                "published_at": self.published_at,
            }
        )


@dataclass(frozen=True, slots=True)
class EnterprisePlanOverride:
    tenant_id: str
    override_id: str
    version: int
    base_plan_id: str
    additional_features: tuple[str, ...]
    seat_limit: int
    concurrent_task_limit: int
    priority: int
    created_by: str
    effective_from: datetime

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.override_id, field="override_id")
        require_positive(self.version, field="version")
        _required_text(self.base_plan_id, field="base_plan_id")
        require_non_negative(self.seat_limit, field="seat_limit")
        require_positive(self.concurrent_task_limit, field="concurrent_task_limit")
        require_positive(self.priority, field="priority")
        _required_text(self.created_by, field="created_by")
        object.__setattr__(self, "effective_from", require_aware(self.effective_from, field_name="effective_from"))


@dataclass(frozen=True, slots=True)
class SubscriptionEntitlementSnapshot:
    tenant_id: str
    subscription_id: str
    plan_id: str
    plan_version: int
    plan_digest: str
    lifecycle_state: PlanLifecycleState
    features: tuple[str, ...]
    seat_limit: int
    concurrent_task_limit: int
    model_tier: str
    retention_days: int
    storage_bytes: int
    paid_credit_minor: int
    promotional_credit_minor: int
    enterprise_override_id: str | None
    enterprise_override_version: int | None
    sequence: int


@dataclass(frozen=True, slots=True)
class PlanVersionEvent:
    tenant_id: str
    plan_id: str
    from_version: int
    to_version: int
    event_digest: str


@dataclass(frozen=True, slots=True)
class EntitlementDecision:
    tenant_id: str
    subscription_id: str
    capability: str
    allowed: bool
    reason: str
    snapshot_sequence: int


@dataclass(frozen=True, slots=True)
class PlanEntitlementAuditEvent:
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    action: str
    actor: str
    revision: int
    occurred_at: datetime
    state_digest: str


class PlanEntitlementClosureService:
    """Unified local entitlement API with exact cache invalidation and atomic leases."""

    authority = "LOCAL_REFERENCE_ONLY"

    def __init__(self) -> None:
        self._lock = RLock()
        self._plans: dict[tuple[str, str, int], PlanDefinition] = {}
        self._overrides: dict[tuple[str, str, int], EnterprisePlanOverride] = {}
        self._subscriptions: dict[str, SubscriptionEntitlementSnapshot] = {}
        self._transitions: dict[tuple[str, str], tuple[str, SubscriptionEntitlementSnapshot]] = {}
        self._cache: dict[tuple[str, str], SubscriptionEntitlementSnapshot] = {}
        self._active_leases: dict[tuple[str, str], set[str]] = {}
        self._snapshot_history: dict[tuple[str, str], list[SubscriptionEntitlementSnapshot]] = {}
        self._audit: list[PlanEntitlementAuditEvent] = []

    def publish_plan(self, definition: PlanDefinition) -> PlanDefinition:
        with self._lock:
            key = (definition.tenant_id, definition.plan_id, definition.version)
            existing = self._plans.get(key)
            if existing is not None:
                require(existing.digest == definition.digest, "PLAN_VERSION_CONFLICT", "plan version changed")
                return existing
            history = self.plan_history(tenant_id=definition.tenant_id, plan_id=definition.plan_id)
            require(
                definition.version == len(history) + 1,
                "PLAN_VERSION_SEQUENCE_INVALID",
                "plan versions must be contiguous",
            )
            self._plans[key] = definition
            return definition

    def set_enterprise_override(self, override: EnterprisePlanOverride) -> EnterprisePlanOverride:
        with self._lock:
            key = (override.tenant_id, override.override_id, override.version)
            require(key not in self._overrides, "ENTERPRISE_OVERRIDE_EXISTS", "override version already exists")
            previous = tuple(
                item
                for item_key, item in self._overrides.items()
                if item_key[0] == override.tenant_id and item_key[1] == override.override_id
            )
            require(override.version == len(previous) + 1, "OVERRIDE_VERSION_INVALID", "versions must be contiguous")
            self._overrides[key] = override
            self._audit.append(
                PlanEntitlementAuditEvent(
                    tenant_id=override.tenant_id,
                    aggregate_type="ENTERPRISE_PLAN_OVERRIDE",
                    aggregate_id=override.override_id,
                    action="SET_OVERRIDE",
                    actor=override.created_by,
                    revision=override.version,
                    occurred_at=override.effective_from,
                    state_digest=canonical_digest(
                        {
                            "base_plan_id": override.base_plan_id,
                            "features": override.additional_features,
                            "seats": override.seat_limit,
                            "concurrency": override.concurrent_task_limit,
                            "priority": override.priority,
                        }
                    ),
                )
            )
            return override

    def activate(
        self,
        *,
        tenant_id: str,
        subscription_id: str,
        plan_id: str,
        plan_version: int,
        trial: bool,
        enterprise_override_id: str | None,
        enterprise_override_version: int | None,
        idempotency_key: str,
    ) -> SubscriptionEntitlementSnapshot:
        _required_text(idempotency_key, field="idempotency_key")
        plan = self._required_plan(tenant_id, plan_id, plan_version)
        fingerprint = canonical_digest(
            {
                "subscription_id": subscription_id,
                "plan_id": plan_id,
                "plan_version": plan_version,
                "trial": trial,
                "enterprise_override_id": enterprise_override_id,
                "enterprise_override_version": enterprise_override_version,
            }
        )
        with self._lock:
            replay = self._transitions.get((tenant_id, idempotency_key))
            if replay is not None:
                require(replay[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "activation input changed")
                return replay[1]
            require(subscription_id not in self._subscriptions, "SUBSCRIPTION_EXISTS", "subscription already exists")
            override = self._resolve_override(
                tenant_id=tenant_id,
                plan_id=plan_id,
                override_id=enterprise_override_id,
                override_version=enterprise_override_version,
            )
            snapshot = self._make_snapshot(
                subscription_id=subscription_id,
                plan=plan,
                state=PlanLifecycleState.TRIAL if trial else PlanLifecycleState.ACTIVE,
                override=override,
                paid_credit_minor=plan.paid_credit_minor,
                promotional_credit_minor=plan.promotional_credit_minor,
                sequence=1,
            )
            self._subscriptions[subscription_id] = snapshot
            self._cache[(tenant_id, subscription_id)] = snapshot
            self._transitions[(tenant_id, idempotency_key)] = (fingerprint, snapshot)
            self._snapshot_history.setdefault((tenant_id, subscription_id), []).append(snapshot)
            self._record_plan_audit(snapshot, "ACTIVATE", "entitlement-activation", plan.published_at)
            return snapshot

    def transition(
        self,
        *,
        tenant_id: str,
        subscription_id: str,
        transition: PlanTransition,
        idempotency_key: str,
        target_plan_id: str | None = None,
        target_plan_version: int | None = None,
    ) -> SubscriptionEntitlementSnapshot:
        _required_text(idempotency_key, field="idempotency_key")
        fingerprint = canonical_digest(
            {
                "subscription_id": subscription_id,
                "transition": transition,
                "target_plan_id": target_plan_id,
                "target_plan_version": target_plan_version,
            }
        )
        with self._lock:
            replay = self._transitions.get((tenant_id, idempotency_key))
            if replay is not None:
                require(replay[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "transition input changed")
                return replay[1]
            current = self._required_subscription(tenant_id, subscription_id)
            new_state = self._transition_state(current.lifecycle_state, transition)
            if transition in {PlanTransition.UPGRADE, PlanTransition.DOWNGRADE}:
                if target_plan_id is None or target_plan_version is None:
                    raise DomainError("TARGET_PLAN_REQUIRED", "plan transition requires a target and version")
                plan = self._required_plan(tenant_id, target_plan_id, target_plan_version)
            else:
                require(
                    target_plan_id is None and target_plan_version is None,
                    "UNEXPECTED_TARGET_PLAN",
                    "lifecycle-only transition cannot change plans",
                )
                plan = self._required_plan(tenant_id, current.plan_id, current.plan_version)
            override = self._latest_override(tenant_id=tenant_id, plan_id=plan.plan_id)
            updated = self._make_snapshot(
                subscription_id=subscription_id,
                plan=plan,
                state=new_state,
                override=override,
                paid_credit_minor=current.paid_credit_minor,
                promotional_credit_minor=current.promotional_credit_minor,
                sequence=checked_add(current.sequence, 1, field="snapshot_sequence"),
            )
            self._subscriptions[subscription_id] = updated
            self._cache[(tenant_id, subscription_id)] = updated
            self._transitions[(tenant_id, idempotency_key)] = (fingerprint, updated)
            self._snapshot_history.setdefault((tenant_id, subscription_id), []).append(updated)
            self._record_plan_audit(
                updated,
                f"TRANSITION_{transition.value}",
                "entitlement-transition",
                plan.published_at,
            )
            return updated

    def entitlement(
        self,
        *,
        tenant_id: str,
        subscription_id: str,
        capability: str,
    ) -> EntitlementDecision:
        _required_text(capability, field="capability")
        with self._lock:
            snapshot = self._cache.get((tenant_id, subscription_id))
            if snapshot is None:
                snapshot = self._required_subscription(tenant_id, subscription_id)
                self._cache[(tenant_id, subscription_id)] = snapshot
            active = snapshot.lifecycle_state in {PlanLifecycleState.TRIAL, PlanLifecycleState.ACTIVE}
            allowed = active and capability in snapshot.features
            reason = "ALLOWED" if allowed else ("SUBSCRIPTION_INACTIVE" if not active else "FEATURE_NOT_INCLUDED")
            return EntitlementDecision(tenant_id, subscription_id, capability, allowed, reason, snapshot.sequence)

    def acquire_task_slot(self, *, tenant_id: str, subscription_id: str, lease_id: str) -> int:
        _required_text(lease_id, field="lease_id")
        with self._lock:
            snapshot = self._required_subscription(tenant_id, subscription_id)
            require(
                snapshot.lifecycle_state in {PlanLifecycleState.TRIAL, PlanLifecycleState.ACTIVE},
                "SUBSCRIPTION_INACTIVE",
                "inactive subscription cannot acquire work",
            )
            key = (tenant_id, subscription_id)
            leases = self._active_leases.setdefault(key, set())
            if lease_id in leases:
                return len(leases)
            require(
                len(leases) < snapshot.concurrent_task_limit,
                "CONCURRENCY_LIMIT_EXCEEDED",
                "concurrent task entitlement exhausted",
            )
            leases.add(lease_id)
            return len(leases)

    def release_task_slot(self, *, tenant_id: str, subscription_id: str, lease_id: str) -> int:
        with self._lock:
            self._required_subscription(tenant_id, subscription_id)
            leases = self._active_leases.setdefault((tenant_id, subscription_id), set())
            leases.discard(lease_id)
            return len(leases)

    def version_event(
        self,
        *,
        tenant_id: str,
        plan_id: str,
        from_version: int,
        to_version: int,
    ) -> PlanVersionEvent:
        self._required_plan(tenant_id, plan_id, from_version)
        self._required_plan(tenant_id, plan_id, to_version)
        require(to_version > from_version, "PLAN_EVENT_VERSION_INVALID", "version event must advance")
        return PlanVersionEvent(
            tenant_id=tenant_id,
            plan_id=plan_id,
            from_version=from_version,
            to_version=to_version,
            event_digest=canonical_digest(
                {
                    "tenant_id": tenant_id,
                    "plan_id": plan_id,
                    "from_version": from_version,
                    "to_version": to_version,
                }
            ),
        )

    def invalidate_from_version_event(self, event: PlanVersionEvent) -> tuple[str, ...]:
        with self._lock:
            invalidated = tuple(
                subscription_id
                for (tenant_id, subscription_id), snapshot in tuple(self._cache.items())
                if tenant_id == event.tenant_id
                and snapshot.plan_id == event.plan_id
                and snapshot.plan_version == event.from_version
            )
            for subscription_id in invalidated:
                del self._cache[(event.tenant_id, subscription_id)]
            return invalidated

    def plan_history(self, *, tenant_id: str, plan_id: str) -> tuple[PlanDefinition, ...]:
        _required_tenant(tenant_id)
        return tuple(
            plan
            for key, plan in sorted(self._plans.items(), key=lambda item: item[0][2])
            if key[0] == tenant_id and key[1] == plan_id
        )

    def subscription_history(
        self,
        *,
        tenant_id: str,
        subscription_id: str,
    ) -> tuple[SubscriptionEntitlementSnapshot, ...]:
        self._required_subscription(tenant_id, subscription_id)
        return tuple(self._snapshot_history.get((tenant_id, subscription_id), ()))

    def audit_events(self, *, tenant_id: str) -> tuple[PlanEntitlementAuditEvent, ...]:
        _required_tenant(tenant_id)
        return tuple(event for event in self._audit if event.tenant_id == tenant_id)

    @staticmethod
    def _transition_state(current: PlanLifecycleState, transition: PlanTransition) -> PlanLifecycleState:
        allowed: dict[tuple[PlanLifecycleState, PlanTransition], PlanLifecycleState] = {
            (PlanLifecycleState.TRIAL, PlanTransition.END_TRIAL): PlanLifecycleState.ACTIVE,
            (PlanLifecycleState.TRIAL, PlanTransition.CANCEL): PlanLifecycleState.CANCELLED,
            (PlanLifecycleState.ACTIVE, PlanTransition.UPGRADE): PlanLifecycleState.ACTIVE,
            (PlanLifecycleState.ACTIVE, PlanTransition.DOWNGRADE): PlanLifecycleState.ACTIVE,
            (PlanLifecycleState.ACTIVE, PlanTransition.PAUSE): PlanLifecycleState.PAUSED,
            (PlanLifecycleState.ACTIVE, PlanTransition.CANCEL): PlanLifecycleState.CANCELLED,
            (PlanLifecycleState.PAUSED, PlanTransition.RESTART): PlanLifecycleState.ACTIVE,
            (PlanLifecycleState.PAUSED, PlanTransition.CANCEL): PlanLifecycleState.CANCELLED,
            (PlanLifecycleState.CANCELLED, PlanTransition.RESTART): PlanLifecycleState.ACTIVE,
        }
        try:
            return allowed[(current, transition)]
        except KeyError as exc:
            raise DomainError("PLAN_TRANSITION_FORBIDDEN", "subscription lifecycle transition is forbidden") from exc

    def _resolve_override(
        self,
        *,
        tenant_id: str,
        plan_id: str,
        override_id: str | None,
        override_version: int | None,
    ) -> EnterprisePlanOverride | None:
        require(
            (override_id is None) == (override_version is None),
            "OVERRIDE_BINDING_INCOMPLETE",
            "override id and version must be bound together",
        )
        if override_id is None or override_version is None:
            return None
        try:
            override = self._overrides[(tenant_id, override_id, override_version)]
        except KeyError as exc:
            if any(key[1:] == (override_id, override_version) for key in self._overrides):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "override belongs to another tenant") from exc
            raise DomainError("ENTERPRISE_OVERRIDE_NOT_FOUND", "enterprise override was not found") from exc
        require(override.base_plan_id == plan_id, "OVERRIDE_PLAN_MISMATCH", "override targets another plan")
        return override

    def _latest_override(self, *, tenant_id: str, plan_id: str) -> EnterprisePlanOverride | None:
        matches = tuple(
            item
            for key, item in self._overrides.items()
            if key[0] == tenant_id and item.base_plan_id == plan_id
        )
        return max(matches, key=lambda item: (item.priority, item.version), default=None)

    @staticmethod
    def _make_snapshot(
        *,
        subscription_id: str,
        plan: PlanDefinition,
        state: PlanLifecycleState,
        override: EnterprisePlanOverride | None,
        paid_credit_minor: int,
        promotional_credit_minor: int,
        sequence: int,
    ) -> SubscriptionEntitlementSnapshot:
        if override is None:
            features = plan.features
            seats = plan.seat_limit
            concurrency = plan.concurrent_task_limit
            override_id = None
            override_version = None
        else:
            features = tuple(sorted(set(plan.features) | set(override.additional_features)))
            seats = override.seat_limit
            concurrency = override.concurrent_task_limit
            override_id = override.override_id
            override_version = override.version
        return SubscriptionEntitlementSnapshot(
            tenant_id=plan.tenant_id,
            subscription_id=subscription_id,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            plan_digest=plan.digest,
            lifecycle_state=state,
            features=features,
            seat_limit=seats,
            concurrent_task_limit=concurrency,
            model_tier=plan.model_tier,
            retention_days=plan.retention_days,
            storage_bytes=plan.storage_bytes,
            paid_credit_minor=paid_credit_minor,
            promotional_credit_minor=promotional_credit_minor,
            enterprise_override_id=override_id,
            enterprise_override_version=override_version,
            sequence=sequence,
        )

    def _required_plan(self, tenant_id: str, plan_id: str, version: int) -> PlanDefinition:
        _required_tenant(tenant_id)
        try:
            return self._plans[(tenant_id, plan_id, version)]
        except KeyError as exc:
            if any(key[1:] == (plan_id, version) for key in self._plans):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "plan belongs to another tenant") from exc
            raise DomainError("PLAN_VERSION_NOT_FOUND", "plan version was not found") from exc

    def _required_subscription(self, tenant_id: str, subscription_id: str) -> SubscriptionEntitlementSnapshot:
        _required_tenant(tenant_id)
        try:
            snapshot = self._subscriptions[subscription_id]
        except KeyError as exc:
            raise DomainError("SUBSCRIPTION_NOT_FOUND", "subscription was not found") from exc
        require(snapshot.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "subscription is cross-tenant")
        return snapshot

    def _record_plan_audit(
        self,
        snapshot: SubscriptionEntitlementSnapshot,
        action: str,
        actor: str,
        occurred_at: datetime,
    ) -> None:
        self._audit.append(
            PlanEntitlementAuditEvent(
                tenant_id=snapshot.tenant_id,
                aggregate_type="SUBSCRIPTION_ENTITLEMENT",
                aggregate_id=snapshot.subscription_id,
                action=action,
                actor=_required_text(actor, field="actor"),
                revision=snapshot.sequence,
                occurred_at=occurred_at,
                state_digest=canonical_digest(
                    {
                        "plan_digest": snapshot.plan_digest,
                        "state": snapshot.lifecycle_state,
                        "features": snapshot.features,
                        "paid_credit_minor": snapshot.paid_credit_minor,
                        "promotional_credit_minor": snapshot.promotional_credit_minor,
                    }
                ),
            )
        )


class EstimateResourceKind(StrEnum):
    MODEL = "MODEL"
    CACHE = "CACHE"
    SANDBOX = "SANDBOX"
    TEST = "TEST"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    TOOL = "TOOL"


class ExecutionModelStrategy(StrEnum):
    ECONOMY = "ECONOMY"
    BALANCED = "BALANCED"
    BEST_QUALITY = "BEST_QUALITY"


class EstimationMode(StrEnum):
    CALIBRATED = "CALIBRATED"
    CONSERVATIVE_RULE = "CONSERVATIVE_RULE"


@dataclass(frozen=True, slots=True)
class ResourceForecast:
    kind: EstimateResourceKind
    quantity: Decimal
    unit_rate: ExactAmount
    machine_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _exact_decimal(self.quantity, field="quantity"))
        require_non_negative(self.machine_seconds, field="machine_seconds")

    @property
    def cost(self) -> ExactAmount:
        return self.unit_rate.scale(self.quantity)


@dataclass(frozen=True, slots=True)
class CostPercentiles:
    p50: ExactAmount
    p80: ExactAmount
    p90: ExactAmount

    def __post_init__(self) -> None:
        self.p50._same_currency(self.p80)
        self.p50._same_currency(self.p90)
        require(
            self.p50.value <= self.p80.value <= self.p90.value,
            "ESTIMATE_PERCENTILES_INVALID",
            "cost percentiles must be monotonic",
        )


@dataclass(frozen=True, slots=True)
class TaskEstimateInput:
    tenant_id: str
    task_id: str
    estimate_id: str
    estimator_version: str
    input_snapshot_digest: str
    input_snapshot_version: int
    strategy: ExecutionModelStrategy
    resources: tuple[ResourceForecast, ...]
    historical_sample_count: int
    drift_basis_points: int
    human_developer_seconds: int
    risk_factors: tuple[str, ...]
    uncertainty_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.task_id, field="task_id")
        _required_text(self.estimate_id, field="estimate_id")
        _required_text(self.estimator_version, field="estimator_version")
        _required_text(self.input_snapshot_digest, field="input_snapshot_digest")
        require_positive(self.input_snapshot_version, field="input_snapshot_version")
        require_non_negative(self.historical_sample_count, field="historical_sample_count")
        require(
            0 <= self.drift_basis_points <= 10_000,
            "DRIFT_BASIS_POINTS_INVALID",
            "drift must be in 0..10000 basis points",
        )
        require_non_negative(self.human_developer_seconds, field="human_developer_seconds")
        require(
            {resource.kind for resource in self.resources} == set(EstimateResourceKind),
            "RESOURCE_FORECAST_INCOMPLETE",
            "model, cache, sandbox, test, storage, network, and tool forecasts are required",
        )
        require(
            len({resource.kind for resource in self.resources}) == len(self.resources),
            "RESOURCE_FORECAST_DUPLICATE",
            "resource forecast kinds must be unique",
        )
        currencies = {resource.unit_rate.currency for resource in self.resources}
        require(len(currencies) == 1, "CURRENCY_MISMATCH", "all forecast rates must use one currency")
        require(all(bool(item.strip()) for item in self.risk_factors), "RISK_FACTOR_INVALID", "risk cannot be blank")
        require(
            all(bool(item.strip()) for item in self.uncertainty_sources),
            "UNCERTAINTY_SOURCE_INVALID",
            "uncertainty cannot be blank",
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "task_id": self.task_id,
                "estimate_id": self.estimate_id,
                "estimator_version": self.estimator_version,
                "input_snapshot_digest": self.input_snapshot_digest,
                "input_snapshot_version": self.input_snapshot_version,
                "strategy": self.strategy,
                "resources": [
                    (item.kind, str(item.quantity), item.unit_rate.canonical, item.machine_seconds)
                    for item in self.resources
                ],
                "historical_sample_count": self.historical_sample_count,
                "drift_basis_points": self.drift_basis_points,
                "human_developer_seconds": self.human_developer_seconds,
                "risk_factors": self.risk_factors,
                "uncertainty_sources": self.uncertainty_sources,
            }
        )


@dataclass(frozen=True, slots=True)
class TaskCostEstimate:
    tenant_id: str
    task_id: str
    estimate_id: str
    estimator_version: str
    input_snapshot_digest: str
    input_snapshot_version: int
    strategy: ExecutionModelStrategy
    mode: EstimationMode
    resource_costs: tuple[tuple[EstimateResourceKind, ExactAmount], ...]
    costs: CostPercentiles
    autonomous_machine_eta_seconds: int
    human_developer_seconds_comparison: int
    confidence_basis_points: int
    risk_factors: tuple[str, ...]
    uncertainty_sources: tuple[str, ...]
    created_at: datetime
    input_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_aware(self.created_at, field_name="created_at"))
        require(
            0 <= self.confidence_basis_points <= 10_000,
            "CONFIDENCE_INVALID",
            "confidence must be in 0..10000 basis points",
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "task_id": self.task_id,
                "estimate_id": self.estimate_id,
                "estimator_version": self.estimator_version,
                "input_snapshot_digest": self.input_snapshot_digest,
                "input_snapshot_version": self.input_snapshot_version,
                "strategy": self.strategy,
                "mode": self.mode,
                "resource_costs": [(kind, amount.canonical) for kind, amount in self.resource_costs],
                "costs": (self.costs.p50.canonical, self.costs.p80.canonical, self.costs.p90.canonical),
                "autonomous_machine_eta_seconds": self.autonomous_machine_eta_seconds,
                "human_developer_seconds_comparison": self.human_developer_seconds_comparison,
                "confidence_basis_points": self.confidence_basis_points,
                "risk_factors": self.risk_factors,
                "uncertainty_sources": self.uncertainty_sources,
                "created_at": self.created_at,
                "input_digest": self.input_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    tenant_id: str
    task_id: str
    estimate_digest: str
    anonymized_history_key: str
    predicted_p90: ExactAmount
    actual_cost: ExactAmount
    predicted_eta_seconds: int
    actual_eta_seconds: int
    recorded_at: datetime


class TaskCostEstimationClosureService:
    """Immutable, tenant-bound local estimator; production calibration evidence remains NOT_RUN."""

    authority = "LOCAL_REFERENCE_ONLY"
    external_evidence = "NOT_RUN"
    certification = "NOT_CERTIFIED"
    _strategy_factor = {
        ExecutionModelStrategy.ECONOMY: Decimal("0.800000"),
        ExecutionModelStrategy.BALANCED: Decimal("1.000000"),
        ExecutionModelStrategy.BEST_QUALITY: Decimal("1.350000"),
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._estimates: dict[tuple[str, str], TaskCostEstimate] = {}
        self._calibration: dict[tuple[str, str], CalibrationObservation] = {}

    def estimate(self, request: TaskEstimateInput, *, created_at: datetime) -> TaskCostEstimate:
        normalized_at = require_aware(created_at, field_name="created_at")
        key = (request.tenant_id, request.estimate_id)
        with self._lock:
            prior = self._estimates.get(key)
            if prior is not None:
                require(prior.input_digest == request.digest, "ESTIMATE_IDEMPOTENCY_CONFLICT", "estimate input changed")
                return prior
            mode = (
                EstimationMode.CONSERVATIVE_RULE
                if request.historical_sample_count < 20 or request.drift_basis_points >= 1_500
                else EstimationMode.CALIBRATED
            )
            factor = self._strategy_factor[request.strategy]
            resource_costs = tuple((item.kind, item.cost.scale(factor)) for item in request.resources)
            currency = request.resources[0].unit_rate.currency
            base = ExactAmount.zero(currency)
            for _, amount in resource_costs:
                base = base.add(amount)
            if mode is EstimationMode.CONSERVATIVE_RULE:
                percentiles = (Decimal("1.150000"), Decimal("1.350000"), Decimal("1.600000"))
                eta_factor = Decimal("1.500000")
                confidence = max(2_500, 6_000 - request.drift_basis_points)
                risks = tuple(dict.fromkeys((*request.risk_factors, "LOW_SAMPLE_OR_MODEL_DRIFT")))
                uncertainties = tuple(
                    dict.fromkeys((*request.uncertainty_sources, "CONSERVATIVE_RULE_FALLBACK"))
                )
            else:
                percentiles = (Decimal("1.000000"), Decimal("1.150000"), Decimal("1.280000"))
                eta_factor = Decimal("1.100000")
                confidence = min(9_500, 7_000 + request.historical_sample_count * 20 - request.drift_basis_points)
                risks = request.risk_factors
                uncertainties = request.uncertainty_sources
            raw_eta = sum(item.machine_seconds for item in request.resources)
            machine_eta = int((Decimal(raw_eta) * eta_factor).to_integral_value(rounding=ROUND_HALF_UP))
            p50_factor, p80_factor, p90_factor = percentiles
            result = TaskCostEstimate(
                tenant_id=request.tenant_id,
                task_id=request.task_id,
                estimate_id=request.estimate_id,
                estimator_version=request.estimator_version,
                input_snapshot_digest=request.input_snapshot_digest,
                input_snapshot_version=request.input_snapshot_version,
                strategy=request.strategy,
                mode=mode,
                resource_costs=resource_costs,
                costs=CostPercentiles(
                    p50=base.scale(p50_factor),
                    p80=base.scale(p80_factor),
                    p90=base.scale(p90_factor),
                ),
                autonomous_machine_eta_seconds=machine_eta,
                human_developer_seconds_comparison=request.human_developer_seconds,
                confidence_basis_points=confidence,
                risk_factors=risks,
                uncertainty_sources=uncertainties,
                created_at=normalized_at,
                input_digest=request.digest,
            )
            self._estimates[key] = result
            return result

    def compare_strategies(
        self,
        request: TaskEstimateInput,
        *,
        created_at: datetime,
    ) -> tuple[TaskCostEstimate, TaskCostEstimate, TaskCostEstimate]:
        estimates = tuple(
            self.estimate(
                replace(request, estimate_id=f"{request.estimate_id}:{strategy.value}", strategy=strategy),
                created_at=created_at,
            )
            for strategy in ExecutionModelStrategy
        )
        return estimates[0], estimates[1], estimates[2]

    def record_actual(
        self,
        *,
        tenant_id: str,
        estimate_id: str,
        anonymized_history_key: str,
        actual_cost: ExactAmount,
        actual_eta_seconds: int,
        recorded_at: datetime,
    ) -> CalibrationObservation:
        require(
            len(anonymized_history_key) == 64
            and all(character in "0123456789abcdef" for character in anonymized_history_key),
            "ANONYMIZED_HISTORY_KEY_INVALID",
            "history keys must be lower-case SHA-256 digests",
        )
        require_non_negative(actual_eta_seconds, field="actual_eta_seconds")
        normalized_at = require_aware(recorded_at, field_name="recorded_at")
        estimate = self._required_estimate(tenant_id, estimate_id)
        estimate.costs.p90._same_currency(actual_cost)
        key = (tenant_id, estimate.digest)
        observation = CalibrationObservation(
            tenant_id=tenant_id,
            task_id=estimate.task_id,
            estimate_digest=estimate.digest,
            anonymized_history_key=anonymized_history_key,
            predicted_p90=estimate.costs.p90,
            actual_cost=actual_cost,
            predicted_eta_seconds=estimate.autonomous_machine_eta_seconds,
            actual_eta_seconds=actual_eta_seconds,
            recorded_at=normalized_at,
        )
        with self._lock:
            prior = self._calibration.get(key)
            if prior is not None:
                require(prior == observation, "CALIBRATION_OBSERVATION_CONFLICT", "actual observation changed")
                return prior
            self._calibration[key] = observation
            return observation

    def calibration_history(self, *, tenant_id: str) -> tuple[CalibrationObservation, ...]:
        _required_tenant(tenant_id)
        return tuple(item for (item_tenant, _), item in self._calibration.items() if item_tenant == tenant_id)

    def _required_estimate(self, tenant_id: str, estimate_id: str) -> TaskCostEstimate:
        _required_tenant(tenant_id)
        try:
            return self._estimates[(tenant_id, estimate_id)]
        except KeyError as exc:
            if any(key[1] == estimate_id for key in self._estimates):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "estimate belongs to another tenant") from exc
            raise DomainError("ESTIMATE_NOT_FOUND", "estimate was not found") from exc


class QuoteFundingKind(StrEnum):
    PREPAID = "PREPAID"
    ENTERPRISE_CREDIT = "ENTERPRISE_CREDIT"


class BudgetExecutionState(StrEnum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    SETTLED = "SETTLED"
    FAILED_SETTLED = "FAILED_SETTLED"
    CANCELLED_SETTLED = "CANCELLED_SETTLED"


class BudgetRemediation(StrEnum):
    INCREASE_BUDGET = "INCREASE_BUDGET"
    DOWNGRADE_MODEL = "DOWNGRADE_MODEL"
    REDUCE_SCOPE = "REDUCE_SCOPE"
    BLOCKERS_ONLY = "BLOCKERS_ONLY"
    STOP_AND_EXPORT = "STOP_AND_EXPORT"


@dataclass(frozen=True, slots=True)
class FundingAccountSnapshot:
    tenant_id: str
    kind: QuoteFundingKind
    available_or_limit: ExactAmount
    reserved: ExactAmount
    captured: ExactAmount
    revision: int

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        self.available_or_limit._same_currency(self.reserved)
        self.available_or_limit._same_currency(self.captured)
        require_positive(self.revision, field="revision")


@dataclass(frozen=True, slots=True)
class FrozenCommercialQuote:
    tenant_id: str
    quote_id: str
    currency: str
    p50: ExactAmount
    p80: ExactAmount
    p90: ExactAmount
    maximum_budget: ExactAmount
    autonomous_machine_eta_seconds: int
    human_developer_seconds_comparison: int
    confidence_basis_points: int
    price_book_id: str
    price_book_version: int
    price_book_digest: str
    estimate_id: str
    estimate_digest: str
    estimator_version: str
    model_strategy: ExecutionModelStrategy
    scope_version: int
    scope_digest: str
    alert_basis_points: tuple[int, ...]
    issued_at: datetime
    expires_at: datetime
    frozen_digest: str

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.quote_id, field="quote_id")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        for amount in (self.p50, self.p80, self.p90, self.maximum_budget):
            require(amount.currency == self.currency, "CURRENCY_MISMATCH", "quote amount currency mismatch")
        require(
            self.p50.value <= self.p80.value <= self.p90.value <= self.maximum_budget.value,
            "QUOTE_RANGE_INVALID",
            "quote range must be monotonic and within maximum budget",
        )
        require_non_negative(self.autonomous_machine_eta_seconds, field="autonomous_machine_eta_seconds")
        require_non_negative(self.human_developer_seconds_comparison, field="human_developer_seconds_comparison")
        require(0 <= self.confidence_basis_points <= 10_000, "CONFIDENCE_INVALID", "confidence is invalid")
        _required_text(self.price_book_id, field="price_book_id")
        require_positive(self.price_book_version, field="price_book_version")
        _required_text(self.price_book_digest, field="price_book_digest")
        _required_text(self.estimate_id, field="estimate_id")
        _required_text(self.estimate_digest, field="estimate_digest")
        _required_text(self.estimator_version, field="estimator_version")
        require_positive(self.scope_version, field="scope_version")
        _required_text(self.scope_digest, field="scope_digest")
        require(
            self.alert_basis_points == tuple(sorted(set(self.alert_basis_points))),
            "BUDGET_ALERTS_INVALID",
            "budget alerts must be unique and increasing",
        )
        require(
            all(0 < threshold < 10_000 for threshold in self.alert_basis_points),
            "BUDGET_ALERTS_INVALID",
            "budget alerts must be below the hard cap",
        )
        object.__setattr__(self, "issued_at", require_aware(self.issued_at, field_name="issued_at"))
        object.__setattr__(self, "expires_at", require_aware(self.expires_at, field_name="expires_at"))
        require(self.expires_at > self.issued_at, "QUOTE_EXPIRY_INVALID", "quote expiry must follow issue time")
        _required_text(self.frozen_digest, field="frozen_digest")


@dataclass(frozen=True, slots=True)
class BudgetExecutionSnapshot:
    tenant_id: str
    quote_id: str
    funding_kind: QuoteFundingKind
    reserved_budget: ExactAmount
    active_hard_cap: ExactAmount
    committed_billable: ExactAmount
    emitted_alert_basis_points: tuple[int, ...]
    state: BudgetExecutionState
    remediation_history: tuple[BudgetRemediation, ...]
    revision: int
    accepted_by: str
    accepted_at: datetime
    outcome_evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class BudgetPreflightDecision:
    allowed: bool
    reason: str
    projected_billable: ExactAmount
    newly_crossed_alerts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BudgetSettlement:
    tenant_id: str
    quote_id: str
    captured: ExactAmount
    released: ExactAmount
    state: BudgetExecutionState
    responsibility: str
    outcome_evidence_digest: str
    settled_at: datetime


@dataclass(frozen=True, slots=True)
class BudgetRecoveryRecord:
    quote: FrozenCommercialQuote
    execution: BudgetExecutionSnapshot
    funding: FundingAccountSnapshot
    record_digest: str


@dataclass(frozen=True, slots=True)
class QuoteBudgetAuditEvent:
    tenant_id: str
    quote_id: str
    action: str
    actor: str
    occurred_at: datetime
    state_digest: str


class QuoteBudgetGuardClosureService:
    """Atomic local quote reservation and hard-cap guard with replayable recovery records."""

    authority = "LOCAL_REFERENCE_ONLY"
    external_credit_verification = "NOT_RUN"
    certification = "NOT_CERTIFIED"

    def __init__(self) -> None:
        self._lock = RLock()
        self._funding: dict[tuple[str, str], FundingAccountSnapshot] = {}
        self._quotes: dict[str, FrozenCommercialQuote] = {}
        self._executions: dict[str, BudgetExecutionSnapshot] = {}
        self._invalidated: set[str] = set()
        self._commands: dict[tuple[str, str], tuple[str, object]] = {}
        self._audit: list[QuoteBudgetAuditEvent] = []

    def configure_funding(
        self,
        *,
        tenant_id: str,
        kind: QuoteFundingKind,
        available_or_credit_limit: ExactAmount,
    ) -> FundingAccountSnapshot:
        _required_tenant(tenant_id)
        key = (tenant_id, available_or_credit_limit.currency)
        with self._lock:
            prior = self._funding.get(key)
            require(
                prior is None or prior.reserved.value == 0,
                "FUNDING_HAS_RESERVATIONS",
                "cannot reset active funding",
            )
            snapshot = FundingAccountSnapshot(
                tenant_id=tenant_id,
                kind=kind,
                available_or_limit=available_or_credit_limit,
                reserved=ExactAmount.zero(available_or_credit_limit.currency),
                captured=ExactAmount.zero(available_or_credit_limit.currency),
                revision=1 if prior is None else checked_add(prior.revision, 1, field="funding_revision"),
            )
            self._funding[key] = snapshot
            return snapshot

    def issue_quote(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        estimate: TaskCostEstimate,
        maximum_budget: ExactAmount,
        price_book_id: str,
        price_book_version: int,
        price_book_digest: str,
        scope_version: int,
        scope_digest: str,
        alert_basis_points: tuple[int, ...],
        issued_at: datetime,
        expires_at: datetime,
    ) -> FrozenCommercialQuote:
        require(estimate.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "estimate is cross-tenant")
        estimate.costs.p90._same_currency(maximum_budget)
        payload = {
            "tenant_id": tenant_id,
            "quote_id": quote_id,
            "currency": maximum_budget.currency,
            "costs": (estimate.costs.p50.canonical, estimate.costs.p80.canonical, estimate.costs.p90.canonical),
            "maximum_budget": maximum_budget.canonical,
            "machine_eta": estimate.autonomous_machine_eta_seconds,
            "human_seconds": estimate.human_developer_seconds_comparison,
            "confidence": estimate.confidence_basis_points,
            "price_book": (price_book_id, price_book_version, price_book_digest),
            "estimate": (estimate.estimate_id, estimate.digest, estimate.estimator_version, estimate.strategy),
            "scope": (scope_version, scope_digest),
            "alerts": alert_basis_points,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        quote = FrozenCommercialQuote(
            tenant_id=tenant_id,
            quote_id=quote_id,
            currency=maximum_budget.currency,
            p50=estimate.costs.p50,
            p80=estimate.costs.p80,
            p90=estimate.costs.p90,
            maximum_budget=maximum_budget,
            autonomous_machine_eta_seconds=estimate.autonomous_machine_eta_seconds,
            human_developer_seconds_comparison=estimate.human_developer_seconds_comparison,
            confidence_basis_points=estimate.confidence_basis_points,
            price_book_id=price_book_id,
            price_book_version=price_book_version,
            price_book_digest=price_book_digest,
            estimate_id=estimate.estimate_id,
            estimate_digest=estimate.digest,
            estimator_version=estimate.estimator_version,
            model_strategy=estimate.strategy,
            scope_version=scope_version,
            scope_digest=scope_digest,
            alert_basis_points=alert_basis_points,
            issued_at=issued_at,
            expires_at=expires_at,
            frozen_digest=canonical_digest(payload),
        )
        with self._lock:
            prior = self._quotes.get(quote_id)
            if prior is not None:
                require(prior == quote, "QUOTE_ID_CONFLICT", "quote identity was reused with different terms")
                return prior
            self._quotes[quote_id] = quote
            return quote

    def accept_and_reserve(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        expected_scope_version: int,
        expected_scope_digest: str,
        accepted_by: str,
        accepted_at: datetime,
        idempotency_key: str,
    ) -> BudgetExecutionSnapshot:
        normalized_at = require_aware(accepted_at, field_name="accepted_at")
        _required_text(idempotency_key, field="idempotency_key")
        fingerprint = canonical_digest(
            {
                "quote_id": quote_id,
                "scope_version": expected_scope_version,
                "scope_digest": expected_scope_digest,
                "accepted_by": accepted_by,
                "accepted_at": normalized_at,
            }
        )
        with self._lock:
            replay = self._replay(tenant_id, idempotency_key, fingerprint)
            if replay is not None:
                if not isinstance(replay, BudgetExecutionSnapshot):
                    raise DomainError("COMMAND_REPLAY_TYPE_INVALID", "replay type changed")
                return replay
            quote = self._required_quote(tenant_id, quote_id)
            require(quote_id not in self._invalidated, "QUOTE_REQUOTE_REQUIRED", "quote was invalidated")
            require(normalized_at <= quote.expires_at, "QUOTE_EXPIRED", "quote has expired")
            require(
                (expected_scope_version, expected_scope_digest) == (quote.scope_version, quote.scope_digest),
                "QUOTE_SCOPE_CHANGED",
                "scope changed and requires a new quote",
            )
            require(quote_id not in self._executions, "QUOTE_ALREADY_ACCEPTED", "quote was already accepted")
            account = self._required_funding(tenant_id, quote.currency)
            if account.kind is QuoteFundingKind.PREPAID:
                require(
                    account.available_or_limit.value >= quote.maximum_budget.value,
                    "INSUFFICIENT_PREPAID_BALANCE",
                    "prepaid balance cannot reserve the hard cap",
                )
                available = account.available_or_limit.subtract(quote.maximum_budget)
            else:
                require(
                    account.reserved.value + quote.maximum_budget.value <= account.available_or_limit.value,
                    "ENTERPRISE_CREDIT_LIMIT_EXCEEDED",
                    "enterprise credit cannot reserve the hard cap",
                )
                available = account.available_or_limit
            updated_account = replace(
                account,
                available_or_limit=available,
                reserved=account.reserved.add(quote.maximum_budget),
                revision=checked_add(account.revision, 1, field="funding_revision"),
            )
            execution = BudgetExecutionSnapshot(
                tenant_id=tenant_id,
                quote_id=quote_id,
                funding_kind=account.kind,
                reserved_budget=quote.maximum_budget,
                active_hard_cap=quote.maximum_budget,
                committed_billable=ExactAmount.zero(quote.currency),
                emitted_alert_basis_points=(),
                state=BudgetExecutionState.ACTIVE,
                remediation_history=(),
                revision=1,
                accepted_by=_required_text(accepted_by, field="accepted_by"),
                accepted_at=normalized_at,
                outcome_evidence_digest=None,
            )
            self._funding[(tenant_id, quote.currency)] = updated_account
            self._executions[quote_id] = execution
            self._store_command(tenant_id, idempotency_key, fingerprint, execution)
            self._record_quote_audit(execution, "ACCEPT_AND_RESERVE", accepted_by, normalized_at)
            return execution

    def preflight_billable(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        next_amount: ExactAmount,
    ) -> BudgetPreflightDecision:
        with self._lock:
            quote = self._required_quote(tenant_id, quote_id)
            execution = self._required_execution(tenant_id, quote_id)
            next_amount._same_currency(execution.active_hard_cap)
            projected = execution.committed_billable.add(next_amount)
            if execution.state is not BudgetExecutionState.ACTIVE:
                return BudgetPreflightDecision(False, "EXECUTION_NOT_ACTIVE", projected, ())
            if projected.value > execution.active_hard_cap.value:
                return BudgetPreflightDecision(False, "HARD_CAP_WOULD_BE_EXCEEDED", projected, ())
            crossed = tuple(
                threshold
                for threshold in quote.alert_basis_points
                if threshold not in execution.emitted_alert_basis_points
                and projected.value * Decimal(10_000)
                >= execution.active_hard_cap.value * Decimal(threshold)
            )
            return BudgetPreflightDecision(True, "ALLOWED", projected, crossed)

    def commit_billable(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        amount: ExactAmount,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> BudgetExecutionSnapshot:
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        fingerprint = canonical_digest({"quote_id": quote_id, "amount": amount.canonical})
        with self._lock:
            replay = self._replay(tenant_id, idempotency_key, fingerprint)
            if replay is not None:
                if not isinstance(replay, BudgetExecutionSnapshot):
                    raise DomainError("COMMAND_REPLAY_TYPE_INVALID", "replay type changed")
                return replay
            decision = self.preflight_billable(tenant_id=tenant_id, quote_id=quote_id, next_amount=amount)
            require(decision.allowed, decision.reason, "new billable execution is blocked by budget guard")
            current = self._required_execution(tenant_id, quote_id)
            updated = replace(
                current,
                committed_billable=decision.projected_billable,
                emitted_alert_basis_points=tuple(
                    sorted(set(current.emitted_alert_basis_points) | set(decision.newly_crossed_alerts))
                ),
                revision=checked_add(current.revision, 1, field="budget_revision"),
            )
            self._executions[quote_id] = updated
            self._store_command(tenant_id, idempotency_key, fingerprint, updated)
            self._record_quote_audit(updated, "COMMIT_BILLABLE", "budget-guard", normalized_at)
            return updated

    def apply_remediation(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        action: BudgetRemediation,
        actor: str,
        occurred_at: datetime,
        additional_budget: ExactAmount | None = None,
    ) -> BudgetExecutionSnapshot:
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            current = self._required_execution(tenant_id, quote_id)
            require(current.state is BudgetExecutionState.ACTIVE, "EXECUTION_NOT_ACTIVE", "execution cannot change")
            new_cap = current.active_hard_cap
            new_reserved = current.reserved_budget
            if action is BudgetRemediation.INCREASE_BUDGET:
                if additional_budget is None:
                    raise DomainError("ADDITIONAL_BUDGET_REQUIRED", "increase requires an amount")
                additional_budget._same_currency(new_cap)
                require(additional_budget.value > 0, "ADDITIONAL_BUDGET_REQUIRED", "increase must be positive")
                account = self._required_funding(tenant_id, new_cap.currency)
                if account.kind is QuoteFundingKind.PREPAID:
                    require(
                        account.available_or_limit.value >= additional_budget.value,
                        "INSUFFICIENT_PREPAID_BALANCE",
                        "cannot reserve additional budget",
                    )
                    available = account.available_or_limit.subtract(additional_budget)
                else:
                    require(
                        account.reserved.value + additional_budget.value <= account.available_or_limit.value,
                        "ENTERPRISE_CREDIT_LIMIT_EXCEEDED",
                        "cannot reserve additional enterprise credit",
                    )
                    available = account.available_or_limit
                self._funding[(tenant_id, new_cap.currency)] = replace(
                    account,
                    available_or_limit=available,
                    reserved=account.reserved.add(additional_budget),
                    revision=checked_add(account.revision, 1, field="funding_revision"),
                )
                new_cap = new_cap.add(additional_budget)
                new_reserved = new_reserved.add(additional_budget)
            else:
                require(additional_budget is None, "UNEXPECTED_ADDITIONAL_BUDGET", "action cannot change budget")
            state = BudgetExecutionState.STOPPED if action is BudgetRemediation.STOP_AND_EXPORT else current.state
            updated = replace(
                current,
                active_hard_cap=new_cap,
                reserved_budget=new_reserved,
                state=state,
                remediation_history=(*current.remediation_history, action),
                revision=checked_add(current.revision, 1, field="budget_revision"),
            )
            self._executions[quote_id] = updated
            self._record_quote_audit(updated, f"REMEDIATE_{action.value}", actor, normalized_at)
            return updated

    def require_requote_for_scope_or_expiry(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        observed_scope_version: int,
        observed_scope_digest: str,
        as_of: datetime,
    ) -> bool:
        normalized_at = require_aware(as_of, field_name="as_of")
        with self._lock:
            quote = self._required_quote(tenant_id, quote_id)
            invalid = (
                normalized_at > quote.expires_at
                or observed_scope_version != quote.scope_version
                or observed_scope_digest != quote.scope_digest
            )
            if not invalid:
                return False
            self._invalidated.add(quote_id)
            execution = self._executions.get(quote_id)
            if execution is not None and execution.state is BudgetExecutionState.ACTIVE:
                stopped = replace(
                    execution,
                    state=BudgetExecutionState.STOPPED,
                    revision=checked_add(execution.revision, 1, field="budget_revision"),
                )
                self._executions[quote_id] = stopped
                self._record_quote_audit(stopped, "REQUOTE_REQUIRED", "scope-guard", normalized_at)
            return True

    def settle(
        self,
        *,
        tenant_id: str,
        quote_id: str,
        actual_billable: ExactAmount,
        responsibility: str,
        outcome_evidence_digest: str,
        settled_at: datetime,
        terminal_state: BudgetExecutionState = BudgetExecutionState.SETTLED,
    ) -> BudgetSettlement:
        require(
            terminal_state
            in {
                BudgetExecutionState.SETTLED,
                BudgetExecutionState.FAILED_SETTLED,
                BudgetExecutionState.CANCELLED_SETTLED,
            },
            "SETTLEMENT_STATE_INVALID",
            "settlement requires a terminal state",
        )
        _required_text(responsibility, field="responsibility")
        _required_text(outcome_evidence_digest, field="outcome_evidence_digest")
        normalized_at = require_aware(settled_at, field_name="settled_at")
        with self._lock:
            current = self._required_execution(tenant_id, quote_id)
            require(
                current.state in {BudgetExecutionState.ACTIVE, BudgetExecutionState.STOPPED},
                "EXECUTION_ALREADY_SETTLED",
                "execution is already terminal",
            )
            actual_billable._same_currency(current.committed_billable)
            require(
                actual_billable.value <= current.committed_billable.value,
                "SETTLEMENT_EXCEEDS_COMMITTED_USAGE",
                "captured amount cannot exceed recorded actual usage",
            )
            released = current.reserved_budget.subtract(actual_billable)
            account = self._required_funding(tenant_id, actual_billable.currency)
            require(
                account.reserved.value >= current.reserved_budget.value,
                "FUNDING_RECONCILIATION_MISMATCH",
                "reserved account no longer covers execution",
            )
            available = account.available_or_limit
            if account.kind is QuoteFundingKind.PREPAID:
                available = available.add(released)
            self._funding[(tenant_id, actual_billable.currency)] = replace(
                account,
                available_or_limit=available,
                reserved=account.reserved.subtract(current.reserved_budget),
                captured=account.captured.add(actual_billable),
                revision=checked_add(account.revision, 1, field="funding_revision"),
            )
            terminal = replace(
                current,
                state=terminal_state,
                outcome_evidence_digest=outcome_evidence_digest,
                revision=checked_add(current.revision, 1, field="budget_revision"),
            )
            self._executions[quote_id] = terminal
            self._record_quote_audit(terminal, f"SETTLE_{terminal_state.value}", responsibility, normalized_at)
            return BudgetSettlement(
                tenant_id=tenant_id,
                quote_id=quote_id,
                captured=actual_billable,
                released=released,
                state=terminal_state,
                responsibility=responsibility,
                outcome_evidence_digest=outcome_evidence_digest,
                settled_at=normalized_at,
            )

    def recovery_record(self, *, tenant_id: str, quote_id: str) -> BudgetRecoveryRecord:
        quote = self._required_quote(tenant_id, quote_id)
        execution = self._required_execution(tenant_id, quote_id)
        funding = self._required_funding(tenant_id, quote.currency)
        digest = canonical_digest(
            {
                "quote": quote.frozen_digest,
                "execution": self._execution_digest(execution),
                "funding": self._funding_digest(funding),
            }
        )
        return BudgetRecoveryRecord(quote, execution, funding, digest)

    def restore_recovery_record(self, record: BudgetRecoveryRecord) -> BudgetExecutionSnapshot:
        expected = canonical_digest(
            {
                "quote": record.quote.frozen_digest,
                "execution": self._execution_digest(record.execution),
                "funding": self._funding_digest(record.funding),
            }
        )
        require(record.record_digest == expected, "RECOVERY_RECORD_TAMPERED", "recovery digest is invalid")
        require(
            record.quote.tenant_id == record.execution.tenant_id == record.funding.tenant_id,
            "TENANT_ISOLATION_VIOLATION",
            "recovery record crosses tenants",
        )
        with self._lock:
            require(record.quote.quote_id not in self._quotes, "RECOVERY_TARGET_NOT_EMPTY", "quote already exists")
            key = (record.funding.tenant_id, record.funding.available_or_limit.currency)
            require(key not in self._funding, "RECOVERY_TARGET_NOT_EMPTY", "funding account already exists")
            self._quotes[record.quote.quote_id] = record.quote
            self._executions[record.execution.quote_id] = record.execution
            self._funding[key] = record.funding
            return record.execution

    def audit_events(self, *, tenant_id: str) -> tuple[QuoteBudgetAuditEvent, ...]:
        _required_tenant(tenant_id)
        return tuple(event for event in self._audit if event.tenant_id == tenant_id)

    def _required_quote(self, tenant_id: str, quote_id: str) -> FrozenCommercialQuote:
        _required_tenant(tenant_id)
        try:
            quote = self._quotes[quote_id]
        except KeyError as exc:
            raise DomainError("QUOTE_NOT_FOUND", "quote was not found") from exc
        require(quote.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "quote belongs to another tenant")
        return quote

    def _required_execution(self, tenant_id: str, quote_id: str) -> BudgetExecutionSnapshot:
        self._required_quote(tenant_id, quote_id)
        try:
            return self._executions[quote_id]
        except KeyError as exc:
            raise DomainError("BUDGET_EXECUTION_NOT_FOUND", "quote has not been accepted") from exc

    def _required_funding(self, tenant_id: str, currency: str) -> FundingAccountSnapshot:
        try:
            return self._funding[(tenant_id, normalize_currency(currency))]
        except KeyError as exc:
            raise DomainError("FUNDING_ACCOUNT_NOT_FOUND", "funding account was not configured") from exc

    def _replay(self, tenant_id: str, key: str, fingerprint: str) -> object | None:
        prior = self._commands.get((tenant_id, key))
        if prior is None:
            return None
        require(prior[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "command input changed")
        return prior[1]

    def _store_command(self, tenant_id: str, key: str, fingerprint: str, value: object) -> None:
        self._commands[(tenant_id, key)] = (fingerprint, value)

    @staticmethod
    def _execution_digest(execution: BudgetExecutionSnapshot) -> str:
        return canonical_digest(
            {
                "tenant_id": execution.tenant_id,
                "quote_id": execution.quote_id,
                "funding_kind": execution.funding_kind,
                "reserved": execution.reserved_budget.canonical,
                "hard_cap": execution.active_hard_cap.canonical,
                "committed": execution.committed_billable.canonical,
                "alerts": execution.emitted_alert_basis_points,
                "state": execution.state,
                "remediation": execution.remediation_history,
                "revision": execution.revision,
                "accepted_by": execution.accepted_by,
                "accepted_at": execution.accepted_at,
                "outcome": execution.outcome_evidence_digest,
            }
        )

    @staticmethod
    def _funding_digest(funding: FundingAccountSnapshot) -> str:
        return canonical_digest(
            {
                "tenant_id": funding.tenant_id,
                "kind": funding.kind,
                "available_or_limit": funding.available_or_limit.canonical,
                "reserved": funding.reserved.canonical,
                "captured": funding.captured.canonical,
                "revision": funding.revision,
            }
        )

    def _record_quote_audit(
        self,
        execution: BudgetExecutionSnapshot,
        action: str,
        actor: str,
        occurred_at: datetime,
    ) -> None:
        self._audit.append(
            QuoteBudgetAuditEvent(
                tenant_id=execution.tenant_id,
                quote_id=execution.quote_id,
                action=action,
                actor=_required_text(actor, field="actor"),
                occurred_at=occurred_at,
                state_digest=self._execution_digest(execution),
            )
        )


class ProjectContractKind(StrEnum):
    DISCOVERY = "DISCOVERY"
    CAPPED_PRICE = "CAPPED_PRICE"
    FIXED_PRICE = "FIXED_PRICE"


class ChangeOrderState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FixedPriceFailurePath(StrEnum):
    REPAIR = "REPAIR"
    REFUND = "REFUND"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"
    TERMINATE = "TERMINATE"


@dataclass(frozen=True, slots=True)
class FrozenProjectBaseline:
    repository_commit_digest: str
    requirements_digest: str
    scope_version: int
    scope_digest: str
    environment_digest: str
    acceptance_baseline_digest: str

    def __post_init__(self) -> None:
        _required_text(self.repository_commit_digest, field="repository_commit_digest")
        _required_text(self.requirements_digest, field="requirements_digest")
        require_positive(self.scope_version, field="scope_version")
        _required_text(self.scope_digest, field="scope_digest")
        _required_text(self.environment_digest, field="environment_digest")
        _required_text(self.acceptance_baseline_digest, field="acceptance_baseline_digest")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "repository_commit_digest": self.repository_commit_digest,
                "requirements_digest": self.requirements_digest,
                "scope_version": self.scope_version,
                "scope_digest": self.scope_digest,
                "environment_digest": self.environment_digest,
                "acceptance_baseline_digest": self.acceptance_baseline_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class ProjectCommercialContract:
    tenant_id: str
    contract_id: str
    version: int
    kind: ProjectContractKind
    baseline: FrozenProjectBaseline
    currency: str
    quoted_price: ExactAmount
    contractual_cap: ExactAmount | None
    estimated_p80_cost: ExactAmount
    estimated_p90_cost: ExactAmount
    target_margin_basis_points: int
    support_allowance: ExactAmount
    risk_allowance: ExactAmount
    included_revision_rounds: int
    exclusions: tuple[str, ...]
    third_party_responsibilities: tuple[str, ...]
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.contract_id, field="contract_id")
        require_positive(self.version, field="version")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        for amount in (
            self.quoted_price,
            self.estimated_p80_cost,
            self.estimated_p90_cost,
            self.support_allowance,
            self.risk_allowance,
        ):
            require(amount.currency == self.currency, "CURRENCY_MISMATCH", "contract currency mismatch")
        require(
            self.estimated_p80_cost.value <= self.estimated_p90_cost.value,
            "PROJECT_COST_RANGE_INVALID",
            "P80 cost cannot exceed P90 cost",
        )
        require(
            0 <= self.target_margin_basis_points <= 10_000,
            "TARGET_MARGIN_INVALID",
            "target margin must be in 0..10000 basis points",
        )
        require_non_negative(self.included_revision_rounds, field="included_revision_rounds")
        require(bool(self.exclusions), "PROJECT_EXCLUSIONS_REQUIRED", "contract exclusions must be explicit")
        require(
            bool(self.third_party_responsibilities),
            "THIRD_PARTY_BOUNDARY_REQUIRED",
            "third-party responsibility boundaries must be explicit",
        )
        require(all(bool(item.strip()) for item in self.exclusions), "PROJECT_EXCLUSION_INVALID", "blank exclusion")
        require(
            all(bool(item.strip()) for item in self.third_party_responsibilities),
            "THIRD_PARTY_BOUNDARY_INVALID",
            "blank responsibility boundary",
        )
        _required_text(self.created_by, field="created_by")
        object.__setattr__(self, "created_at", require_aware(self.created_at, field_name="created_at"))
        if self.kind is ProjectContractKind.CAPPED_PRICE:
            require(self.contractual_cap is not None, "PROJECT_CAP_REQUIRED", "capped contract requires a cap")
            if self.contractual_cap is not None:
                require(self.contractual_cap.currency == self.currency, "CURRENCY_MISMATCH", "cap currency mismatch")
                require(
                    self.quoted_price.value <= self.contractual_cap.value,
                    "PROJECT_QUOTE_EXCEEDS_CAP",
                    "quoted amount exceeds cap",
                )
        else:
            require(self.contractual_cap is None, "UNEXPECTED_PROJECT_CAP", "only capped contracts declare a cap")
        if self.kind is ProjectContractKind.FIXED_PRICE:
            margin = self.estimated_p90_cost.scale(Decimal(self.target_margin_basis_points) / Decimal(10_000))
            minimum = self.estimated_p90_cost.add(margin).add(self.support_allowance).add(self.risk_allowance)
            require(
                self.quoted_price.value >= minimum.value,
                "FIXED_PRICE_UNDERPRICED",
                "fixed price must cover P90, margin, support, and risk",
            )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "contract_id": self.contract_id,
                "version": self.version,
                "kind": self.kind,
                "baseline": self.baseline.digest,
                "currency": self.currency,
                "quoted_price": self.quoted_price.canonical,
                "contractual_cap": None if self.contractual_cap is None else self.contractual_cap.canonical,
                "estimated_p80_cost": self.estimated_p80_cost.canonical,
                "estimated_p90_cost": self.estimated_p90_cost.canonical,
                "target_margin_basis_points": self.target_margin_basis_points,
                "support_allowance": self.support_allowance.canonical,
                "risk_allowance": self.risk_allowance.canonical,
                "included_revision_rounds": self.included_revision_rounds,
                "exclusions": self.exclusions,
                "third_party_responsibilities": self.third_party_responsibilities,
                "created_by": self.created_by,
                "created_at": self.created_at,
            }
        )


@dataclass(frozen=True, slots=True)
class ProjectChangeOrder:
    tenant_id: str
    change_order_id: str
    contract_id: str
    from_contract_version: int
    proposed_baseline: FrozenProjectBaseline
    incremental_price: ExactAmount
    requested_by: str
    requested_at: datetime
    state: ChangeOrderState
    approved_by: str | None
    approval_evidence_digest: str | None
    isolated_until_approved: bool


@dataclass(frozen=True, slots=True)
class MilestoneAcceptance:
    tenant_id: str
    contract_id: str
    contract_version: int
    milestone_id: str
    automated_test_evidence_digest: str
    approval_evidence_digest: str
    approved_by: str
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectFinancialReview:
    tenant_id: str
    contract_id: str
    contract_version: int
    actual_cost: ExactAmount
    recognized_revenue: ExactAmount
    realized_margin: ExactAmount
    review_evidence_digest: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class FixedPriceFailureResolution:
    tenant_id: str
    contract_id: str
    contract_version: int
    path: FixedPriceFailurePath
    evidence_digest: str
    decided_by: str
    decided_at: datetime


class ProjectPricingContractClosureService:
    """Versioned discovery/capped/fixed contracts; no external acceptance authority."""

    authority = "LOCAL_REFERENCE_ONLY"
    external_acceptance_evidence = "NOT_RUN"
    certification = "NOT_CERTIFIED"

    def __init__(self) -> None:
        self._lock = RLock()
        self._contracts: dict[tuple[str, str, int], ProjectCommercialContract] = {}
        self._changes: dict[tuple[str, str], ProjectChangeOrder] = {}
        self._milestones: dict[tuple[str, str, int, str], MilestoneAcceptance] = {}
        self._reviews: dict[tuple[str, str, int], ProjectFinancialReview] = {}
        self._failures: dict[tuple[str, str, int], FixedPriceFailureResolution] = {}

    def create_contract(self, contract: ProjectCommercialContract) -> ProjectCommercialContract:
        key = (contract.tenant_id, contract.contract_id, contract.version)
        with self._lock:
            prior = self._contracts.get(key)
            if prior is not None:
                require(prior == contract, "PROJECT_CONTRACT_VERSION_CONFLICT", "contract version changed")
                return prior
            history = self.history(tenant_id=contract.tenant_id, contract_id=contract.contract_id)
            require(
                contract.version == len(history) + 1,
                "PROJECT_CONTRACT_VERSION_INVALID",
                "contract versions must be contiguous",
            )
            if history:
                require(
                    contract.created_at >= history[-1].created_at,
                    "PROJECT_CONTRACT_TIME_INVALID",
                    "new version cannot predate history",
                )
            self._contracts[key] = contract
            return contract

    def request_change_order(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        change_order_id: str,
        proposed_baseline: FrozenProjectBaseline,
        incremental_price: ExactAmount,
        requested_by: str,
        requested_at: datetime,
    ) -> ProjectChangeOrder:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        contract.quoted_price._same_currency(incremental_price)
        require(
            proposed_baseline.digest != contract.baseline.digest,
            "CHANGE_ORDER_SCOPE_UNCHANGED",
            "change order must describe changed scope",
        )
        order = ProjectChangeOrder(
            tenant_id=tenant_id,
            change_order_id=_required_text(change_order_id, field="change_order_id"),
            contract_id=contract_id,
            from_contract_version=contract_version,
            proposed_baseline=proposed_baseline,
            incremental_price=incremental_price,
            requested_by=_required_text(requested_by, field="requested_by"),
            requested_at=require_aware(requested_at, field_name="requested_at"),
            state=ChangeOrderState.PENDING,
            approved_by=None,
            approval_evidence_digest=None,
            isolated_until_approved=True,
        )
        with self._lock:
            key = (tenant_id, change_order_id)
            require(key not in self._changes, "CHANGE_ORDER_EXISTS", "change order already exists")
            self._changes[key] = order
            return order

    def approve_change_order(
        self,
        *,
        tenant_id: str,
        change_order_id: str,
        approved_by: str,
        approval_evidence_digest: str,
        approved_at: datetime,
    ) -> tuple[ProjectChangeOrder, ProjectCommercialContract]:
        with self._lock:
            key = (tenant_id, change_order_id)
            try:
                order = self._changes[key]
            except KeyError as exc:
                raise DomainError("CHANGE_ORDER_NOT_FOUND", "change order was not found") from exc
            require(order.state is ChangeOrderState.PENDING, "CHANGE_ORDER_NOT_PENDING", "change order is terminal")
            require(order.requested_by != approved_by, "MAKER_CHECKER_VIOLATION", "requester cannot approve")
            _required_text(approval_evidence_digest, field="approval_evidence_digest")
            contract = self._required_contract(tenant_id, order.contract_id, order.from_contract_version)
            require(
                len(self.history(tenant_id=tenant_id, contract_id=order.contract_id)) == order.from_contract_version,
                "CHANGE_ORDER_BASE_STALE",
                "contract advanced while change order was pending",
            )
            approved = replace(
                order,
                state=ChangeOrderState.APPROVED,
                approved_by=_required_text(approved_by, field="approved_by"),
                approval_evidence_digest=approval_evidence_digest,
                isolated_until_approved=False,
            )
            next_contract = replace(
                contract,
                version=checked_add(contract.version, 1, field="contract_version"),
                baseline=order.proposed_baseline,
                quoted_price=contract.quoted_price.add(order.incremental_price),
                contractual_cap=(
                    None
                    if contract.contractual_cap is None
                    else contract.contractual_cap.add(order.incremental_price)
                ),
                created_by=approved_by,
                created_at=require_aware(approved_at, field_name="approved_at"),
            )
            self._changes[key] = approved
            self.create_contract(next_contract)
            return approved, next_contract

    def accept_milestone(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        milestone_id: str,
        automated_test_evidence_digest: str,
        approval_evidence_digest: str,
        approved_by: str,
        accepted_at: datetime,
    ) -> MilestoneAcceptance:
        self._required_contract(tenant_id, contract_id, contract_version)
        acceptance = MilestoneAcceptance(
            tenant_id=tenant_id,
            contract_id=contract_id,
            contract_version=contract_version,
            milestone_id=_required_text(milestone_id, field="milestone_id"),
            automated_test_evidence_digest=_required_text(
                automated_test_evidence_digest,
                field="automated_test_evidence_digest",
            ),
            approval_evidence_digest=_required_text(approval_evidence_digest, field="approval_evidence_digest"),
            approved_by=_required_text(approved_by, field="approved_by"),
            accepted_at=require_aware(accepted_at, field_name="accepted_at"),
        )
        with self._lock:
            key = (tenant_id, contract_id, contract_version, milestone_id)
            prior = self._milestones.get(key)
            if prior is not None:
                require(prior == acceptance, "MILESTONE_ACCEPTANCE_CONFLICT", "acceptance evidence changed")
                return prior
            self._milestones[key] = acceptance
            return acceptance

    def settle_capped_project(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        actual_billable: ExactAmount,
    ) -> ExactAmount:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        require(contract.kind is ProjectContractKind.CAPPED_PRICE, "PROJECT_NOT_CAPPED", "contract is not capped")
        if contract.contractual_cap is None:
            raise DomainError("PROJECT_CAP_REQUIRED", "capped contract lost its cap")
        actual_billable._same_currency(contract.contractual_cap)
        return actual_billable.minimum(contract.contractual_cap)

    def resolve_fixed_price_acceptance_failure(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        path: FixedPriceFailurePath,
        evidence_digest: str,
        decided_by: str,
        decided_at: datetime,
    ) -> FixedPriceFailureResolution:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        require(contract.kind is ProjectContractKind.FIXED_PRICE, "PROJECT_NOT_FIXED_PRICE", "contract is not fixed")
        result = FixedPriceFailureResolution(
            tenant_id=tenant_id,
            contract_id=contract_id,
            contract_version=contract_version,
            path=path,
            evidence_digest=_required_text(evidence_digest, field="evidence_digest"),
            decided_by=_required_text(decided_by, field="decided_by"),
            decided_at=require_aware(decided_at, field_name="decided_at"),
        )
        with self._lock:
            key = (tenant_id, contract_id, contract_version)
            require(key not in self._failures, "FAILURE_RESOLUTION_EXISTS", "failure already resolved")
            self._failures[key] = result
            return result

    def record_financial_review(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        actual_cost: ExactAmount,
        recognized_revenue: ExactAmount,
        review_evidence_digest: str,
        recorded_at: datetime,
    ) -> ProjectFinancialReview:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        contract.quoted_price._same_currency(actual_cost)
        actual_cost._same_currency(recognized_revenue)
        require(
            recognized_revenue.value >= actual_cost.value,
            "NEGATIVE_REVIEW_MARGIN",
            "negative margin requires a separate loss workflow",
        )
        review = ProjectFinancialReview(
            tenant_id=tenant_id,
            contract_id=contract_id,
            contract_version=contract_version,
            actual_cost=actual_cost,
            recognized_revenue=recognized_revenue,
            realized_margin=recognized_revenue.subtract(actual_cost),
            review_evidence_digest=_required_text(review_evidence_digest, field="review_evidence_digest"),
            recorded_at=require_aware(recorded_at, field_name="recorded_at"),
        )
        with self._lock:
            key = (tenant_id, contract_id, contract_version)
            prior = self._reviews.get(key)
            if prior is not None:
                require(prior == review, "PROJECT_REVIEW_CONFLICT", "financial review changed")
                return prior
            self._reviews[key] = review
            return review

    def validate_standard_sku(
        self,
        *,
        sku: ProjectSkuContract,
        input_digest: str,
        output_digest: str,
        scope_units: int,
    ) -> None:
        sku.validate_delivery(input_digest=input_digest, output_digest=output_digest, scope_units=scope_units)

    def history(self, *, tenant_id: str, contract_id: str) -> tuple[ProjectCommercialContract, ...]:
        _required_tenant(tenant_id)
        return tuple(
            contract
            for key, contract in sorted(self._contracts.items(), key=lambda item: item[0][2])
            if key[0] == tenant_id and key[1] == contract_id
        )

    def _required_contract(self, tenant_id: str, contract_id: str, version: int) -> ProjectCommercialContract:
        _required_tenant(tenant_id)
        try:
            return self._contracts[(tenant_id, contract_id, version)]
        except KeyError as exc:
            if any(key[1:] == (contract_id, version) for key in self._contracts):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "contract belongs to another tenant") from exc
            raise DomainError("PROJECT_CONTRACT_NOT_FOUND", "contract was not found") from exc


@dataclass(frozen=True, slots=True)
class EnterpriseFeeSchedule:
    currency: str
    annual_platform_fee: ExactAmount
    minimum_commit: ExactAmount
    overage_unit_rate: ExactAmount
    private_deployment_fee: ExactAmount
    support_fee: ExactAmount
    sla_fee: ExactAmount

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        for amount in (
            self.annual_platform_fee,
            self.minimum_commit,
            self.overage_unit_rate,
            self.private_deployment_fee,
            self.support_fee,
            self.sla_fee,
        ):
            require(amount.currency == self.currency, "CURRENCY_MISMATCH", "enterprise fee currency mismatch")


@dataclass(frozen=True, slots=True)
class EnterpriseContractVersion:
    tenant_id: str
    contract_id: str
    version: int
    effective_from: datetime
    effective_to: datetime
    fees: EnterpriseFeeSchedule
    committed_usage_units: Decimal
    postpaid_credit_limit: ExactAmount
    purchase_order_reference: str
    payment_terms_days: int
    override_priority: int
    measurement_trust_boundary_digest: str
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.contract_id, field="contract_id")
        require_positive(self.version, field="version")
        object.__setattr__(self, "effective_from", require_aware(self.effective_from, field_name="effective_from"))
        object.__setattr__(self, "effective_to", require_aware(self.effective_to, field_name="effective_to"))
        require(self.effective_to > self.effective_from, "CONTRACT_WINDOW_INVALID", "contract window is invalid")
        object.__setattr__(
            self,
            "committed_usage_units",
            _exact_decimal(self.committed_usage_units, field="committed_usage_units"),
        )
        require(
            self.postpaid_credit_limit.currency == self.fees.currency,
            "CURRENCY_MISMATCH",
            "credit limit currency mismatch",
        )
        _required_text(self.purchase_order_reference, field="purchase_order_reference")
        require_positive(self.payment_terms_days, field="payment_terms_days")
        require_positive(self.override_priority, field="override_priority")
        _required_text(self.measurement_trust_boundary_digest, field="measurement_trust_boundary_digest")
        _required_text(self.created_by, field="created_by")
        object.__setattr__(self, "created_at", require_aware(self.created_at, field_name="created_at"))

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "contract_id": self.contract_id,
                "version": self.version,
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
                "fees": (
                    self.fees.annual_platform_fee.canonical,
                    self.fees.minimum_commit.canonical,
                    self.fees.overage_unit_rate.canonical,
                    self.fees.private_deployment_fee.canonical,
                    self.fees.support_fee.canonical,
                    self.fees.sla_fee.canonical,
                ),
                "committed_usage_units": str(self.committed_usage_units),
                "postpaid_credit_limit": self.postpaid_credit_limit.canonical,
                "purchase_order_reference": self.purchase_order_reference,
                "payment_terms_days": self.payment_terms_days,
                "override_priority": self.override_priority,
                "measurement_trust_boundary_digest": self.measurement_trust_boundary_digest,
                "created_by": self.created_by,
                "created_at": self.created_at,
            }
        )


@dataclass(frozen=True, slots=True)
class SecretReference:
    provider: str
    uri: str
    version: str

    def __post_init__(self) -> None:
        _required_text(self.provider, field="secret_provider")
        _required_text(self.uri, field="secret_reference_uri")
        _required_text(self.version, field="secret_reference_version")
        require(self.uri.startswith("secret://"), "SECRET_REFERENCE_URI_INVALID", "BYOK must use secret:// reference")
        require("?" not in self.uri and "#" not in self.uri, "SECRET_REFERENCE_URI_INVALID", "secret URI is opaque")
        forbidden = ("BEGIN PRIVATE KEY", "sk-", "api_key=", "token=")
        require(
            not any(marker.lower() in self.uri.lower() for marker in forbidden),
            "PLAINTEXT_SECRET_FORBIDDEN",
            "secret material cannot be embedded in a reference",
        )


@dataclass(frozen=True, slots=True)
class ByokBinding:
    tenant_id: str
    binding_id: str
    contract_id: str
    contract_version: int
    model_provider: str
    secret_reference: SecretReference
    quota_units: Decimal
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.binding_id, field="binding_id")
        _required_text(self.contract_id, field="contract_id")
        require_positive(self.contract_version, field="contract_version")
        _required_text(self.model_provider, field="model_provider")
        object.__setattr__(self, "quota_units", _exact_decimal(self.quota_units, field="quota_units"))
        _required_text(self.created_by, field="created_by")
        object.__setattr__(self, "created_at", require_aware(self.created_at, field_name="created_at"))


@dataclass(frozen=True, slots=True)
class ByokChargeBreakdown:
    excluded_customer_model_cost: ExactAmount
    platform_fee: ExactAmount
    infrastructure_fee: ExactAmount
    billable_total: ExactAmount


@dataclass(frozen=True, slots=True)
class ByokUsageAuthorization:
    tenant_id: str
    binding_id: str
    requested_units: Decimal
    cumulative_units: Decimal
    quota_units: Decimal
    idempotency_key: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class EnterpriseByokAuditEvent:
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    action: str
    actor: str
    occurred_at: datetime
    state_digest: str


@dataclass(frozen=True, slots=True)
class CommitmentSnapshot:
    tenant_id: str
    contract_id: str
    contract_version: int
    committed_value: ExactAmount
    burned_value: ExactAmount
    overage_value: ExactAmount
    revision: int


@dataclass(frozen=True, slots=True)
class CommitmentBurn:
    tenant_id: str
    contract_id: str
    contract_version: int
    charge: ExactAmount
    burned_from_commit: ExactAmount
    overage: ExactAmount
    idempotency_key: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class EnterpriseTrueUp:
    tenant_id: str
    contract_id: str
    contract_version: int
    unused_commit: ExactAmount
    billable_overage: ExactAmount
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class CostCenterBudget:
    tenant_id: str
    cost_center_id: str
    department_id: str
    contract_id: str
    contract_version: int
    budget: ExactAmount
    spent: ExactAmount
    owner: str
    revision: int


@dataclass(frozen=True, slots=True)
class InternalChargeback:
    tenant_id: str
    chargeback_id: str
    cost_center_id: str
    amount: ExactAmount
    requested_by: str
    approved_by: str
    purpose: str
    evidence_digest: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class OfflineMeteringBatch:
    tenant_id: str
    contract_id: str
    contract_version: int
    sequence: int
    previous_batch_digest: str | None
    usage_digest: str
    boundary_attestation_digest: str
    captured_from: datetime
    captured_to: datetime

    def __post_init__(self) -> None:
        _required_tenant(self.tenant_id)
        _required_text(self.contract_id, field="contract_id")
        require_positive(self.contract_version, field="contract_version")
        require_positive(self.sequence, field="sequence")
        _required_text(self.usage_digest, field="usage_digest")
        _required_text(self.boundary_attestation_digest, field="boundary_attestation_digest")
        object.__setattr__(self, "captured_from", require_aware(self.captured_from, field_name="captured_from"))
        object.__setattr__(self, "captured_to", require_aware(self.captured_to, field_name="captured_to"))
        require(self.captured_to > self.captured_from, "OFFLINE_METER_WINDOW_INVALID", "meter window is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "tenant_id": self.tenant_id,
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "sequence": self.sequence,
                "previous_batch_digest": self.previous_batch_digest,
                "usage_digest": self.usage_digest,
                "boundary_attestation_digest": self.boundary_attestation_digest,
                "captured_from": self.captured_from,
                "captured_to": self.captured_to,
            }
        )


@dataclass(frozen=True, slots=True)
class ServiceCreditRule:
    rule_id: str
    metric: str
    breach_threshold_basis_points: int
    credit_basis_points: int
    maximum_credit_basis_points: int

    def __post_init__(self) -> None:
        _required_text(self.rule_id, field="rule_id")
        _required_text(self.metric, field="metric")
        require(
            0 <= self.breach_threshold_basis_points <= 10_000,
            "SLA_THRESHOLD_INVALID",
            "SLA threshold is invalid",
        )
        require(0 <= self.credit_basis_points <= 10_000, "SLA_CREDIT_INVALID", "SLA credit is invalid")
        require(
            self.credit_basis_points <= self.maximum_credit_basis_points <= 10_000,
            "SLA_CREDIT_INVALID",
            "SLA maximum credit is invalid",
        )


@dataclass(frozen=True, slots=True)
class ServiceCreditDecision:
    tenant_id: str
    contract_id: str
    contract_version: int
    rule_id: str
    observed_basis_points: int
    eligible_fee: ExactAmount
    credit: ExactAmount
    evidence_digest: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalSettlement:
    tenant_id: str
    settlement_id: str
    contract_id: str
    contract_version: int
    amount: ExactAmount
    source_digest: str
    recorded_at: datetime


class EnterpriseByokClosureService:
    """Enterprise/BYOK local reference with secret references and immutable version bindings."""

    authority = "LOCAL_REFERENCE_ONLY"
    external_reference_resolution = "NOT_RUN"
    external_meter_verification = "NOT_RUN"
    certification = "NOT_CERTIFIED"

    def __init__(self) -> None:
        self._lock = RLock()
        self._contracts: dict[tuple[str, str, int], EnterpriseContractVersion] = {}
        self._commitments: dict[tuple[str, str, int], CommitmentSnapshot] = {}
        self._burns: dict[tuple[str, str], tuple[str, CommitmentBurn]] = {}
        self._byok: dict[tuple[str, str], ByokBinding] = {}
        self._byok_usage: dict[tuple[str, str], Decimal] = {}
        self._byok_commands: dict[tuple[str, str], tuple[str, ByokUsageAuthorization]] = {}
        self._cost_centers: dict[tuple[str, str], CostCenterBudget] = {}
        self._chargebacks: dict[tuple[str, str], InternalChargeback] = {}
        self._offline_batches: dict[tuple[str, str, int, int], OfflineMeteringBatch] = {}
        self._settlements: dict[tuple[str, str], HistoricalSettlement] = {}
        self._audit: list[EnterpriseByokAuditEvent] = []

    def create_contract(self, contract: EnterpriseContractVersion) -> EnterpriseContractVersion:
        key = (contract.tenant_id, contract.contract_id, contract.version)
        with self._lock:
            prior = self._contracts.get(key)
            if prior is not None:
                require(prior.digest == contract.digest, "ENTERPRISE_CONTRACT_VERSION_CONFLICT", "version changed")
                return prior
            history = self.history(tenant_id=contract.tenant_id, contract_id=contract.contract_id)
            require(
                contract.version == len(history) + 1,
                "ENTERPRISE_CONTRACT_VERSION_INVALID",
                "contract versions must be contiguous",
            )
            if history:
                require(
                    contract.effective_from >= history[-1].effective_to,
                    "ENTERPRISE_CONTRACT_WINDOW_OVERLAP",
                    "contract versions cannot overlap",
                )
            self._contracts[key] = contract
            self._commitments[key] = CommitmentSnapshot(
                tenant_id=contract.tenant_id,
                contract_id=contract.contract_id,
                contract_version=contract.version,
                committed_value=contract.fees.minimum_commit,
                burned_value=ExactAmount.zero(contract.fees.currency),
                overage_value=ExactAmount.zero(contract.fees.currency),
                revision=1,
            )
            return contract

    def resolve_contract_override(
        self,
        *,
        tenant_id: str,
        at: datetime,
    ) -> EnterpriseContractVersion:
        normalized_at = require_aware(at, field_name="at")
        matches = tuple(
            contract
            for (item_tenant, _, _), contract in self._contracts.items()
            if item_tenant == tenant_id and contract.effective_from <= normalized_at < contract.effective_to
        )
        require(bool(matches), "ENTERPRISE_CONTRACT_NOT_FOUND", "no active enterprise contract")
        return max(matches, key=lambda item: (item.override_priority, item.version, item.contract_id))

    def renew_contract(self, renewal: EnterpriseContractVersion) -> EnterpriseContractVersion:
        history = self.history(tenant_id=renewal.tenant_id, contract_id=renewal.contract_id)
        require(bool(history), "ENTERPRISE_CONTRACT_NOT_FOUND", "renewal requires an existing contract")
        require(renewal.version == history[-1].version + 1, "RENEWAL_VERSION_INVALID", "renewal must advance")
        return self.create_contract(renewal)

    def bind_byok(self, binding: ByokBinding) -> ByokBinding:
        self._required_contract(binding.tenant_id, binding.contract_id, binding.contract_version)
        with self._lock:
            key = (binding.tenant_id, binding.binding_id)
            prior = self._byok.get(key)
            if prior is not None:
                require(prior == binding, "BYOK_BINDING_CONFLICT", "BYOK binding changed")
                return prior
            self._byok[key] = binding
            self._byok_usage[key] = Decimal("0.000000")
            self._audit.append(
                EnterpriseByokAuditEvent(
                    tenant_id=binding.tenant_id,
                    aggregate_type="BYOK_BINDING",
                    aggregate_id=binding.binding_id,
                    action="BIND_SECRET_REFERENCE",
                    actor=binding.created_by,
                    occurred_at=binding.created_at,
                    state_digest=canonical_digest(
                        {
                            "contract_id": binding.contract_id,
                            "contract_version": binding.contract_version,
                            "model_provider": binding.model_provider,
                            "secret_provider": binding.secret_reference.provider,
                            "secret_reference_uri": binding.secret_reference.uri,
                            "secret_reference_version": binding.secret_reference.version,
                            "quota_units": str(binding.quota_units),
                        }
                    ),
                )
            )
            return binding

    def authorize_byok_usage(
        self,
        *,
        tenant_id: str,
        binding_id: str,
        requested_units: Decimal,
        idempotency_key: str,
        actor: str,
        occurred_at: datetime,
    ) -> ByokUsageAuthorization:
        normalized_units = _exact_decimal(requested_units, field="requested_units", positive=True)
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        _required_text(idempotency_key, field="idempotency_key")
        fingerprint = canonical_digest(
            {"binding_id": binding_id, "requested_units": str(normalized_units), "actor": actor}
        )
        with self._lock:
            replay = self._byok_commands.get((tenant_id, idempotency_key))
            if replay is not None:
                require(replay[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "BYOK usage input changed")
                return replay[1]
            try:
                binding = self._byok[(tenant_id, binding_id)]
            except KeyError as exc:
                if any(key[1] == binding_id for key in self._byok):
                    raise DomainError("TENANT_ISOLATION_VIOLATION", "BYOK binding belongs to another tenant") from exc
                raise DomainError("BYOK_BINDING_NOT_FOUND", "BYOK binding was not found") from exc
            used = self._byok_usage[(tenant_id, binding_id)]
            cumulative = _exact_decimal(used + normalized_units, field="cumulative_units")
            require(cumulative <= binding.quota_units, "BYOK_QUOTA_EXCEEDED", "BYOK quota is exhausted")
            result = ByokUsageAuthorization(
                tenant_id=tenant_id,
                binding_id=binding_id,
                requested_units=normalized_units,
                cumulative_units=cumulative,
                quota_units=binding.quota_units,
                idempotency_key=idempotency_key,
                occurred_at=normalized_at,
            )
            self._byok_usage[(tenant_id, binding_id)] = cumulative
            self._byok_commands[(tenant_id, idempotency_key)] = (fingerprint, result)
            self._audit.append(
                EnterpriseByokAuditEvent(
                    tenant_id=tenant_id,
                    aggregate_type="BYOK_QUOTA",
                    aggregate_id=binding_id,
                    action="AUTHORIZE_USAGE",
                    actor=_required_text(actor, field="actor"),
                    occurred_at=normalized_at,
                    state_digest=canonical_digest(
                        {
                            "requested_units": str(normalized_units),
                            "cumulative_units": str(cumulative),
                            "quota_units": str(binding.quota_units),
                        }
                    ),
                )
            )
            return result

    def calculate_byok_charge(
        self,
        *,
        tenant_id: str,
        binding_id: str,
        customer_paid_model_cost: ExactAmount,
        platform_fee: ExactAmount,
        infrastructure_fee: ExactAmount,
    ) -> ByokChargeBreakdown:
        try:
            binding = self._byok[(tenant_id, binding_id)]
        except KeyError as exc:
            if any(key[1] == binding_id for key in self._byok):
                raise DomainError("TENANT_ISOLATION_VIOLATION", "BYOK binding belongs to another tenant") from exc
            raise DomainError("BYOK_BINDING_NOT_FOUND", "BYOK binding was not found") from exc
        contract = self._required_contract(tenant_id, binding.contract_id, binding.contract_version)
        for amount in (customer_paid_model_cost, platform_fee, infrastructure_fee):
            require(amount.currency == contract.fees.currency, "CURRENCY_MISMATCH", "BYOK charge currency mismatch")
        return ByokChargeBreakdown(
            excluded_customer_model_cost=customer_paid_model_cost,
            platform_fee=platform_fee,
            infrastructure_fee=infrastructure_fee,
            billable_total=platform_fee.add(infrastructure_fee),
        )

    def burn_commitment(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        charge: ExactAmount,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> CommitmentBurn:
        _required_text(idempotency_key, field="idempotency_key")
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        key = (tenant_id, contract_id, contract_version)
        fingerprint = canonical_digest(
            {"contract_id": contract_id, "contract_version": contract_version, "charge": charge.canonical}
        )
        with self._lock:
            replay = self._burns.get((tenant_id, idempotency_key))
            if replay is not None:
                require(replay[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "commit burn input changed")
                return replay[1]
            contract = self._required_contract(tenant_id, contract_id, contract_version)
            require(charge.currency == contract.fees.currency, "CURRENCY_MISMATCH", "commit currency mismatch")
            snapshot = self._commitments[key]
            remaining = snapshot.committed_value.subtract(snapshot.burned_value)
            burned = charge.minimum(remaining)
            overage = charge.subtract(burned)
            updated = replace(
                snapshot,
                burned_value=snapshot.burned_value.add(burned),
                overage_value=snapshot.overage_value.add(overage),
                revision=checked_add(snapshot.revision, 1, field="commitment_revision"),
            )
            result = CommitmentBurn(
                tenant_id=tenant_id,
                contract_id=contract_id,
                contract_version=contract_version,
                charge=charge,
                burned_from_commit=burned,
                overage=overage,
                idempotency_key=idempotency_key,
                occurred_at=normalized_at,
            )
            self._commitments[key] = updated
            self._burns[(tenant_id, idempotency_key)] = (fingerprint, result)
            return result

    def calculate_true_up(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        calculated_at: datetime,
    ) -> EnterpriseTrueUp:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        snapshot = self._commitments[(tenant_id, contract_id, contract_version)]
        require(
            require_aware(calculated_at, field_name="calculated_at") >= contract.effective_to,
            "TRUE_UP_TOO_EARLY",
            "true-up is available after the contract period",
        )
        return EnterpriseTrueUp(
            tenant_id=tenant_id,
            contract_id=contract_id,
            contract_version=contract_version,
            unused_commit=snapshot.committed_value.subtract(snapshot.burned_value),
            billable_overage=snapshot.overage_value,
            calculated_at=calculated_at,
        )

    def register_cost_center(
        self,
        *,
        tenant_id: str,
        cost_center_id: str,
        department_id: str,
        contract_id: str,
        contract_version: int,
        budget: ExactAmount,
        owner: str,
    ) -> CostCenterBudget:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        require(budget.currency == contract.fees.currency, "CURRENCY_MISMATCH", "cost center currency mismatch")
        result = CostCenterBudget(
            tenant_id=tenant_id,
            cost_center_id=_required_text(cost_center_id, field="cost_center_id"),
            department_id=_required_text(department_id, field="department_id"),
            contract_id=contract_id,
            contract_version=contract_version,
            budget=budget,
            spent=ExactAmount.zero(budget.currency),
            owner=_required_text(owner, field="owner"),
            revision=1,
        )
        with self._lock:
            key = (tenant_id, cost_center_id)
            require(key not in self._cost_centers, "COST_CENTER_EXISTS", "cost center already exists")
            self._cost_centers[key] = result
            return result

    def approve_chargeback(
        self,
        *,
        tenant_id: str,
        chargeback_id: str,
        cost_center_id: str,
        amount: ExactAmount,
        requested_by: str,
        approved_by: str,
        purpose: str,
        evidence_digest: str,
        occurred_at: datetime,
    ) -> InternalChargeback:
        require(requested_by != approved_by, "MAKER_CHECKER_VIOLATION", "requester cannot approve chargeback")
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            key = (tenant_id, chargeback_id)
            prior = self._chargebacks.get(key)
            if prior is not None:
                require(
                    (
                        prior.cost_center_id,
                        prior.amount,
                        prior.requested_by,
                        prior.approved_by,
                        prior.purpose,
                        prior.evidence_digest,
                        prior.occurred_at,
                    )
                    == (
                        cost_center_id,
                        amount,
                        requested_by,
                        approved_by,
                        purpose,
                        evidence_digest,
                        normalized_at,
                    ),
                    "CHARGEBACK_CONFLICT",
                    "chargeback identity changed",
                )
                return prior
            try:
                center = self._cost_centers[(tenant_id, cost_center_id)]
            except KeyError as exc:
                if any(key[1] == cost_center_id for key in self._cost_centers):
                    raise DomainError("TENANT_ISOLATION_VIOLATION", "cost center belongs to another tenant") from exc
                raise DomainError("COST_CENTER_NOT_FOUND", "cost center was not found") from exc
            center.budget._same_currency(amount)
            require(
                center.spent.value + amount.value <= center.budget.value,
                "COST_CENTER_BUDGET_EXCEEDED",
                "chargeback exceeds department budget",
            )
            result = InternalChargeback(
                tenant_id=tenant_id,
                chargeback_id=_required_text(chargeback_id, field="chargeback_id"),
                cost_center_id=cost_center_id,
                amount=amount,
                requested_by=_required_text(requested_by, field="requested_by"),
                approved_by=_required_text(approved_by, field="approved_by"),
                purpose=_required_text(purpose, field="purpose"),
                evidence_digest=_required_text(evidence_digest, field="evidence_digest"),
                occurred_at=normalized_at,
            )
            self._cost_centers[(tenant_id, cost_center_id)] = replace(
                center,
                spent=center.spent.add(amount),
                revision=checked_add(center.revision, 1, field="cost_center_revision"),
            )
            self._chargebacks[key] = result
            return result

    def accept_offline_metering_batch(self, batch: OfflineMeteringBatch) -> OfflineMeteringBatch:
        contract = self._required_contract(batch.tenant_id, batch.contract_id, batch.contract_version)
        require(
            batch.boundary_attestation_digest == contract.measurement_trust_boundary_digest,
            "METER_TRUST_BOUNDARY_MISMATCH",
            "offline meter batch is outside the contracted trust boundary",
        )
        with self._lock:
            key = (batch.tenant_id, batch.contract_id, batch.contract_version, batch.sequence)
            prior = self._offline_batches.get(key)
            if prior is not None:
                require(prior.digest == batch.digest, "OFFLINE_BATCH_CONFLICT", "offline batch changed")
                return prior
            previous = self._offline_batches.get(
                (batch.tenant_id, batch.contract_id, batch.contract_version, batch.sequence - 1)
            )
            if batch.sequence == 1:
                require(batch.previous_batch_digest is None, "OFFLINE_BATCH_CHAIN_INVALID", "first batch has no parent")
            else:
                require(previous is not None, "OFFLINE_BATCH_SEQUENCE_GAP", "offline batch sequence has a gap")
                if previous is not None:
                    require(
                        batch.previous_batch_digest == previous.digest,
                        "OFFLINE_BATCH_CHAIN_INVALID",
                        "offline batch chain digest is invalid",
                    )
            self._offline_batches[key] = batch
            return batch

    def calculate_service_credit(
        self,
        *,
        tenant_id: str,
        contract_id: str,
        contract_version: int,
        rule: ServiceCreditRule,
        observed_basis_points: int,
        eligible_fee: ExactAmount,
        evidence_digest: str,
        decided_at: datetime,
    ) -> ServiceCreditDecision:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        require(eligible_fee.currency == contract.fees.currency, "CURRENCY_MISMATCH", "SLA fee currency mismatch")
        require(0 <= observed_basis_points <= 10_000, "SLA_OBSERVATION_INVALID", "SLA observation is invalid")
        breached = observed_basis_points < rule.breach_threshold_basis_points
        applied_basis_points = min(rule.credit_basis_points, rule.maximum_credit_basis_points) if breached else 0
        credit = eligible_fee.scale(Decimal(applied_basis_points) / Decimal(10_000))
        return ServiceCreditDecision(
            tenant_id=tenant_id,
            contract_id=contract_id,
            contract_version=contract_version,
            rule_id=rule.rule_id,
            observed_basis_points=observed_basis_points,
            eligible_fee=eligible_fee,
            credit=credit,
            evidence_digest=_required_text(evidence_digest, field="evidence_digest"),
            decided_at=require_aware(decided_at, field_name="decided_at"),
        )

    def record_historical_settlement(
        self,
        *,
        tenant_id: str,
        settlement_id: str,
        contract_id: str,
        contract_version: int,
        amount: ExactAmount,
        source_digest: str,
        recorded_at: datetime,
    ) -> HistoricalSettlement:
        contract = self._required_contract(tenant_id, contract_id, contract_version)
        require(amount.currency == contract.fees.currency, "CURRENCY_MISMATCH", "settlement currency mismatch")
        result = HistoricalSettlement(
            tenant_id=tenant_id,
            settlement_id=_required_text(settlement_id, field="settlement_id"),
            contract_id=contract_id,
            contract_version=contract_version,
            amount=amount,
            source_digest=_required_text(source_digest, field="source_digest"),
            recorded_at=require_aware(recorded_at, field_name="recorded_at"),
        )
        with self._lock:
            key = (tenant_id, settlement_id)
            prior = self._settlements.get(key)
            if prior is not None:
                require(prior == result, "HISTORICAL_SETTLEMENT_IMMUTABLE", "settlement cannot be rewritten")
                return prior
            self._settlements[key] = result
            return result

    def history(self, *, tenant_id: str, contract_id: str) -> tuple[EnterpriseContractVersion, ...]:
        _required_tenant(tenant_id)
        return tuple(
            contract
            for key, contract in sorted(self._contracts.items(), key=lambda item: item[0][2])
            if key[0] == tenant_id and key[1] == contract_id
        )

    def audit_events(self, *, tenant_id: str) -> tuple[EnterpriseByokAuditEvent, ...]:
        _required_tenant(tenant_id)
        return tuple(event for event in self._audit if event.tenant_id == tenant_id)

    def _required_contract(self, tenant_id: str, contract_id: str, version: int) -> EnterpriseContractVersion:
        _required_tenant(tenant_id)
        try:
            return self._contracts[(tenant_id, contract_id, version)]
        except KeyError as exc:
            if any(key[1:] == (contract_id, version) for key in self._contracts):
                raise DomainError(
                    "TENANT_ISOLATION_VIOLATION",
                    "enterprise contract belongs to another tenant",
                ) from exc
            raise DomainError("ENTERPRISE_CONTRACT_NOT_FOUND", "enterprise contract was not found") from exc
