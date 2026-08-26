from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from threading import RLock
from typing import Any

from .errors import DomainError, require
from .models import canonical_digest as _base_digest
from .models import require_aware
from .money import normalize_currency


class ExternalExecutionState(StrEnum):
    NOT_RUN = "NOT_RUN"
    LOCAL_EXECUTED = "LOCAL_EXECUTED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"


class CertificationState(StrEnum):
    NOT_CERTIFIED = "NOT_CERTIFIED"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"


class BudgetAction(StrEnum):
    ADD_BUDGET = "ADD_BUDGET"
    DOWNGRADE_MODE = "DOWNGRADE_MODE"
    SHRINK_SCOPE = "SHRINK_SCOPE"
    BLOCKERS_ONLY = "BLOCKERS_ONLY"
    STOP_AND_EXPORT = "STOP_AND_EXPORT"


class HighRiskActionState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class OperationsMode(StrEnum):
    ACTIVE = "ACTIVE"
    READ_ONLY = "READ_ONLY"
    KILLED = "KILLED"


@dataclass(frozen=True, slots=True)
class QuoteCard:
    tenant_id: str
    quote_id: str
    currency: str
    low: Decimal
    expected: Decimal
    high: Decimal
    hard_cap: Decimal
    machine_eta_seconds: int
    human_reference_seconds: int
    mode: str
    test_plan: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    pricing_version: str


@dataclass(frozen=True, slots=True)
class RunBudgetView:
    tenant_id: str
    run_id: str
    currency: str
    used: Decimal
    reserved: Decimal
    projected_remaining: Decimal
    hard_cap: Decimal
    threshold_percents: tuple[int, ...]
    allowed_actions: tuple[BudgetAction, ...]


@dataclass(frozen=True, slots=True)
class WalletView:
    tenant_id: str
    currency: str
    paid: Decimal
    promotional: Decimal
    reserved: Decimal
    consumed: Decimal
    refunded: Decimal
    expired: Decimal


@dataclass(frozen=True, slots=True)
class BillingDrilldown:
    tenant_id: str
    invoice_id: str
    task_id: str
    run_id: str
    node_id: str
    resource_id: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class ProjectCommercialView:
    tenant_id: str
    project_id: str
    scope_baseline_digest: str
    milestones: tuple[str, ...]
    accepted_milestones: tuple[str, ...]
    change_order_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HighRiskAction:
    action_id: str
    tenant_id: str
    action: str
    preview_digest: str
    requested_by: str
    approved_by: str | None
    state: HighRiskActionState
    audit_digest: str | None


@dataclass(frozen=True, slots=True)
class BackendRuleDecision:
    tenant_id: str
    rule_id: str
    rule_version: str
    input_digest: str
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CostCenterBudget:
    tenant_id: str
    cost_center: str
    department: str
    currency: str
    limit: Decimal
    approvers: tuple[str, ...]


class BillingAdminExperienceService:
    """Backend-owned projections and commands for EB-14.

    This service intentionally returns typed view models. It never lets a client
    calculate a financial rule or convert a preview into its own authority.
    """

    _ACTIONS = tuple(BudgetAction)

    def __init__(self) -> None:
        self._lock = RLock()
        self._high_risk: dict[str, HighRiskAction] = {}
        self._cost_centers: dict[tuple[str, str], CostCenterBudget] = {}
        self._resume_tokens: dict[tuple[str, str], str] = {}

    @staticmethod
    def quote_card(
        *,
        tenant_id: str,
        quote_id: str,
        currency: str,
        low: Decimal,
        expected: Decimal,
        high: Decimal,
        hard_cap: Decimal,
        machine_eta_seconds: int,
        human_reference_seconds: int,
        mode: str,
        test_plan: tuple[str, ...],
        acceptance_criteria: tuple[str, ...],
        pricing_version: str,
    ) -> QuoteCard:
        _tenant(tenant_id)
        require(bool(quote_id.strip()), "QUOTE_ID_REQUIRED", "quote id is required")
        for label, value in (
            ("low", low),
            ("expected", expected),
            ("high", high),
            ("hard_cap", hard_cap),
        ):
            _non_negative(value, label)
        require(low <= expected <= high <= hard_cap, "QUOTE_RANGE_INVALID", "quote range must fit the hard cap")
        require(machine_eta_seconds >= 0, "ETA_INVALID", "machine ETA must be non-negative")
        require(human_reference_seconds >= 0, "HUMAN_REFERENCE_INVALID", "human reference must be non-negative")
        require(bool(mode.strip()), "MODE_REQUIRED", "execution mode is required")
        require(bool(test_plan), "TEST_PLAN_REQUIRED", "quote card requires a test plan")
        require(bool(acceptance_criteria), "ACCEPTANCE_REQUIRED", "quote card requires acceptance criteria")
        require(bool(pricing_version.strip()), "PRICING_VERSION_REQUIRED", "pricing version is required")
        return QuoteCard(
            tenant_id=tenant_id,
            quote_id=quote_id,
            currency=normalize_currency(currency),
            low=low,
            expected=expected,
            high=high,
            hard_cap=hard_cap,
            machine_eta_seconds=machine_eta_seconds,
            human_reference_seconds=human_reference_seconds,
            mode=mode,
            test_plan=test_plan,
            acceptance_criteria=acceptance_criteria,
            pricing_version=pricing_version,
        )

    @classmethod
    def run_budget(
        cls,
        *,
        tenant_id: str,
        run_id: str,
        currency: str,
        used: Decimal,
        reserved: Decimal,
        projected_remaining: Decimal,
        hard_cap: Decimal,
        threshold_percents: tuple[int, ...],
    ) -> RunBudgetView:
        _tenant(tenant_id)
        require(bool(run_id.strip()), "RUN_ID_REQUIRED", "run id is required")
        for label, value in (
            ("used", used),
            ("reserved", reserved),
            ("projected_remaining", projected_remaining),
            ("hard_cap", hard_cap),
        ):
            _non_negative(value, label)
        require(used + reserved <= hard_cap, "BUDGET_CAP_EXCEEDED", "used and reserved exceed the cap")
        require(
            threshold_percents == tuple(sorted(set(threshold_percents)))
            and all(0 < value <= 100 for value in threshold_percents),
            "THRESHOLDS_INVALID",
            "budget thresholds must be unique, sorted percentages",
        )
        return RunBudgetView(
            tenant_id=tenant_id,
            run_id=run_id,
            currency=normalize_currency(currency),
            used=used,
            reserved=reserved,
            projected_remaining=projected_remaining,
            hard_cap=hard_cap,
            threshold_percents=threshold_percents,
            allowed_actions=cls._ACTIONS,
        )

    @staticmethod
    def wallet(
        *,
        tenant_id: str,
        currency: str,
        paid: Decimal,
        promotional: Decimal,
        reserved: Decimal,
        consumed: Decimal,
        refunded: Decimal,
        expired: Decimal,
    ) -> WalletView:
        _tenant(tenant_id)
        values = (paid, promotional, reserved, consumed, refunded, expired)
        for label, value in zip(
            ("paid", "promotional", "reserved", "consumed", "refunded", "expired"),
            values,
            strict=True,
        ):
            _non_negative(value, label)
        require(
            reserved + consumed + expired <= paid + promotional + refunded,
            "WALLET_IMBALANCE",
            "wallet buckets do not reconcile",
        )
        return WalletView(tenant_id, normalize_currency(currency), *values)

    @staticmethod
    def drilldown(rows: tuple[BillingDrilldown, ...], *, tenant_id: str) -> tuple[BillingDrilldown, ...]:
        _tenant(tenant_id)
        require(bool(rows), "DRILLDOWN_REQUIRED", "at least one drilldown row is required")
        for row in rows:
            require(row.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "drilldown row belongs to another tenant")
            for value in (row.invoice_id, row.task_id, row.run_id, row.node_id, row.resource_id):
                require(bool(value.strip()), "DRILLDOWN_KEY_REQUIRED", "all drilldown identities are required")
            _non_negative(row.amount, "drilldown.amount")
            normalize_currency(row.currency)
        return rows

    @staticmethod
    def project_view(view: ProjectCommercialView, *, tenant_id: str) -> ProjectCommercialView:
        _tenant(tenant_id)
        require(view.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "project belongs to another tenant")
        require(bool(view.scope_baseline_digest.strip()), "SCOPE_BASELINE_REQUIRED", "scope baseline is required")
        require(
            set(view.accepted_milestones) <= set(view.milestones), "MILESTONE_INVALID", "accepted milestones must exist"
        )
        return view

    def define_cost_center(self, budget: CostCenterBudget) -> CostCenterBudget:
        _tenant(budget.tenant_id)
        require(bool(budget.cost_center.strip()), "COST_CENTER_REQUIRED", "cost center is required")
        require(bool(budget.department.strip()), "DEPARTMENT_REQUIRED", "department is required")
        _non_negative(budget.limit, "cost_center.limit")
        require(bool(budget.approvers), "APPROVER_REQUIRED", "at least one approver is required")
        normalized = replace(budget, currency=normalize_currency(budget.currency))
        with self._lock:
            self._cost_centers[(budget.tenant_id, budget.cost_center)] = normalized
        return normalized

    def request_high_risk(
        self,
        *,
        action_id: str,
        tenant_id: str,
        action: str,
        preview: object,
        requested_by: str,
    ) -> HighRiskAction:
        _tenant(tenant_id)
        for label, value in (("action_id", action_id), ("action", action), ("requested_by", requested_by)):
            require(bool(value.strip()), f"{label.upper()}_REQUIRED", f"{label} is required")
        candidate = HighRiskAction(
            action_id=action_id,
            tenant_id=tenant_id,
            action=action,
            preview_digest=canonical_digest(preview),
            requested_by=requested_by,
            approved_by=None,
            state=HighRiskActionState.PENDING,
            audit_digest=None,
        )
        with self._lock:
            previous = self._high_risk.get(action_id)
            if previous is not None:
                require(previous == candidate, "IDEMPOTENCY_CONFLICT", "action id was reused with different input")
                return previous
            self._high_risk[action_id] = candidate
            return candidate

    def approve_high_risk(self, *, action_id: str, tenant_id: str, approved_by: str) -> HighRiskAction:
        with self._lock:
            action = self._required_action(action_id, tenant_id)
            require(action.state is HighRiskActionState.PENDING, "ACTION_NOT_PENDING", "action is not pending")
            require(bool(approved_by.strip()), "APPROVER_REQUIRED", "approver is required")
            require(approved_by != action.requested_by, "SEGREGATION_OF_DUTIES", "requester cannot approve")
            approved = replace(action, approved_by=approved_by, state=HighRiskActionState.APPROVED)
            self._high_risk[action_id] = approved
            return approved

    def execute_high_risk(
        self,
        *,
        action_id: str,
        tenant_id: str,
        preview: object,
        backend_decision: BackendRuleDecision,
    ) -> HighRiskAction:
        with self._lock:
            action = self._required_action(action_id, tenant_id)
            require(action.state is HighRiskActionState.APPROVED, "ACTION_NOT_APPROVED", "action is not approved")
            require(
                action.preview_digest == canonical_digest(preview), "PREVIEW_DRIFT", "preview changed after approval"
            )
            require(backend_decision.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "decision tenant mismatch")
            require(backend_decision.allowed, "BACKEND_RULE_DENIED", backend_decision.reason)
            executed = replace(
                action,
                state=HighRiskActionState.EXECUTED,
                audit_digest=canonical_digest({"action": action, "decision": backend_decision}),
            )
            self._high_risk[action_id] = executed
            return executed

    @staticmethod
    def backend_rule(
        *,
        tenant_id: str,
        rule_id: str,
        rule_version: str,
        facts: object,
        allowed: bool,
        reason: str,
    ) -> BackendRuleDecision:
        _tenant(tenant_id)
        require(
            bool(rule_id.strip()) and bool(rule_version.strip()), "RULE_IDENTITY_REQUIRED", "rule identity is required"
        )
        require(bool(reason.strip()), "RULE_REASON_REQUIRED", "rule reason is required")
        return BackendRuleDecision(tenant_id, rule_id, rule_version, canonical_digest(facts), allowed, reason)

    def save_resume_token(self, *, tenant_id: str, journey_id: str, state: object) -> str:
        _tenant(tenant_id)
        require(bool(journey_id.strip()), "JOURNEY_ID_REQUIRED", "journey id is required")
        token = canonical_digest({"tenant_id": tenant_id, "journey_id": journey_id, "state": state})
        with self._lock:
            self._resume_tokens[(tenant_id, journey_id)] = token
        return token

    def resume(self, *, tenant_id: str, journey_id: str, token: str) -> bool:
        with self._lock:
            return self._resume_tokens.get((tenant_id, journey_id)) == token

    @staticmethod
    def accessible_money(*, amount: Decimal, currency: str, locale: str) -> dict[str, str]:
        _non_negative(amount, "amount")
        normalized_currency = normalize_currency(currency)
        require(bool(locale.strip()), "LOCALE_REQUIRED", "locale is required")
        text = f"{normalized_currency} {amount:.2f}"
        return {"text": text, "aria_label": f"{amount:.2f} {normalized_currency}", "locale": locale}

    def _required_action(self, action_id: str, tenant_id: str) -> HighRiskAction:
        try:
            action = self._high_risk[action_id]
        except KeyError as exc:
            raise DomainError("ACTION_NOT_FOUND", "high-risk action was not found") from exc
        require(action.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "action belongs to another tenant")
        return action


@dataclass(frozen=True, slots=True)
class SecretReference:
    value: str

    def __post_init__(self) -> None:
        require(self.value.startswith("secret://"), "SECRET_REFERENCE_REQUIRED", "raw secrets are forbidden")
        require(len(self.value) <= 512, "SECRET_REFERENCE_TOO_LONG", "secret reference is too long")
        require(
            "\n" not in self.value and "\r" not in self.value, "SECRET_REFERENCE_INVALID", "secret reference is invalid"
        )


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    allowed: bool
    tenant_id: str
    principal_id: str
    action: str
    reason: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class AuditChainEntry:
    sequence: int
    tenant_id: str
    actor: str
    action: str
    occurred_at: datetime
    previous_digest: str
    payload_digest: str
    digest: str


@dataclass(frozen=True, slots=True)
class FraudAssessment:
    tenant_id: str
    assessment_id: str
    signals: tuple[str, ...]
    blocked: bool
    rules_version: str
    facts_digest: str


@dataclass(frozen=True, slots=True)
class PrivacyRequest:
    request_id: str
    tenant_id: str
    subject_id: str
    kind: str
    state: str
    legal_hold_reason: str | None


class BillingSecurityComplianceService:
    """Fail-closed local security controls for EB-15.

    Encryption, external secret managers and red-team execution remain evidence
    boundaries. This module validates references and decisions; it never claims
    that an external provider operation occurred.
    """

    REQUIRED_SURFACES = frozenset({"api", "queue", "database", "cache", "object-storage", "analytics"})
    _ROLE_ACTIONS = {
        "VIEWER": frozenset({"billing:read"}),
        "OPERATOR": frozenset({"billing:read", "quote:create", "work:execute"}),
        "APPROVER": frozenset({"billing:read", "quote:approve", "refund:approve", "change:approve"}),
    }
    _SENSITIVE_KEY = re.compile(r"(?i)(secret|token|password|prompt|authorization|card|bank)")

    def __init__(self) -> None:
        self._lock = RLock()
        self._audit: dict[str, list[AuditChainEntry]] = {}
        self._privacy: dict[str, PrivacyRequest] = {}

    @classmethod
    def authorize(
        cls,
        *,
        principal_id: str,
        principal_tenant_id: str,
        resource_tenant_id: str,
        role: str,
        action: str,
        policy_version: str,
    ) -> AuthorizationResult:
        _tenant(principal_tenant_id)
        _tenant(resource_tenant_id)
        require(bool(principal_id.strip()), "PRINCIPAL_REQUIRED", "principal is required")
        require(bool(action.strip()), "ACTION_REQUIRED", "action is required")
        require(bool(policy_version.strip()), "POLICY_VERSION_REQUIRED", "policy version is required")
        same_tenant = principal_tenant_id == resource_tenant_id
        allowed = same_tenant and action in cls._ROLE_ACTIONS.get(role, frozenset())
        reason = "ALLOWED" if allowed else ("TENANT_MISMATCH" if not same_tenant else "ACTION_NOT_GRANTED")
        return AuthorizationResult(allowed, resource_tenant_id, principal_id, action, reason, policy_version)

    @staticmethod
    def require_dual_approval(*, requested_by: str, approved_by: str, action: str) -> None:
        require(
            bool(requested_by.strip()) and bool(approved_by.strip()),
            "DUAL_APPROVAL_REQUIRED",
            "two actors are required",
        )
        require(requested_by != approved_by, "SEGREGATION_OF_DUTIES", "requester and approver must differ")
        require(bool(action.strip()), "ACTION_REQUIRED", "high-risk action is required")

    @staticmethod
    def secret_reference(value: str) -> SecretReference:
        return SecretReference(value)

    @staticmethod
    def encryption_binding(
        *,
        in_transit_policy: str,
        at_rest_key: SecretReference,
        backup_key: SecretReference,
    ) -> dict[str, object]:
        require(
            in_transit_policy in {"TLS1.3", "mTLS1.3"}, "TRANSPORT_ENCRYPTION_REQUIRED", "TLS 1.3 policy is required"
        )
        return {
            "in_transit_policy": in_transit_policy,
            "at_rest_key_reference": at_rest_key.value,
            "backup_key_reference": backup_key.value,
            "external_execution": ExternalExecutionState.NOT_RUN,
        }

    def append_audit(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        occurred_at: datetime,
        payload: object,
    ) -> AuditChainEntry:
        _tenant(tenant_id)
        require(
            bool(actor.strip()) and bool(action.strip()),
            "AUDIT_IDENTITY_REQUIRED",
            "audit actor and action are required",
        )
        timestamp = require_aware(occurred_at, field_name="occurred_at")
        payload_digest = canonical_digest(payload)
        with self._lock:
            chain = self._audit.setdefault(tenant_id, [])
            previous = chain[-1].digest if chain else "0" * 64
            sequence = len(chain) + 1
            digest = canonical_digest(
                {
                    "sequence": sequence,
                    "tenant_id": tenant_id,
                    "actor": actor,
                    "action": action,
                    "occurred_at": timestamp,
                    "previous_digest": previous,
                    "payload_digest": payload_digest,
                }
            )
            entry = AuditChainEntry(sequence, tenant_id, actor, action, timestamp, previous, payload_digest, digest)
            chain.append(entry)
            return entry

    def verify_audit(self, *, tenant_id: str) -> bool:
        _tenant(tenant_id)
        with self._lock:
            previous = "0" * 64
            for sequence, entry in enumerate(self._audit.get(tenant_id, []), start=1):
                expected = canonical_digest(
                    {
                        "sequence": sequence,
                        "tenant_id": tenant_id,
                        "actor": entry.actor,
                        "action": entry.action,
                        "occurred_at": entry.occurred_at,
                        "previous_digest": previous,
                        "payload_digest": entry.payload_digest,
                    }
                )
                if entry.sequence != sequence or entry.previous_digest != previous or entry.digest != expected:
                    return False
                previous = entry.digest
            return True

    @staticmethod
    def assess_fraud(
        *,
        tenant_id: str,
        assessment_id: str,
        topup_count: int,
        refund_ratio: Decimal,
        concurrent_sessions: int,
        account_takeover_signal: bool,
        bot_score: Decimal,
        rules_version: str,
    ) -> FraudAssessment:
        _tenant(tenant_id)
        require(
            bool(assessment_id.strip()) and bool(rules_version.strip()),
            "FRAUD_IDENTITY_REQUIRED",
            "fraud identities are required",
        )
        require(
            topup_count >= 0 and concurrent_sessions >= 0, "FRAUD_COUNT_INVALID", "fraud counters must be non-negative"
        )
        for label, value in (("refund_ratio", refund_ratio), ("bot_score", bot_score)):
            require(
                Decimal("0") <= value <= Decimal("1"), "FRAUD_RATIO_INVALID", f"{label} must be between zero and one"
            )
        signals: list[str] = []
        if topup_count >= 5:
            signals.append("TOPUP_VELOCITY")
        if refund_ratio >= Decimal("0.5"):
            signals.append("REFUND_ABUSE")
        if concurrent_sessions >= 10:
            signals.append("CONCURRENCY_ABUSE")
        if account_takeover_signal:
            signals.append("ACCOUNT_TAKEOVER")
        if bot_score >= Decimal("0.8"):
            signals.append("BOT_AUTOMATION")
        facts = {
            "topup_count": topup_count,
            "refund_ratio": str(refund_ratio),
            "concurrent_sessions": concurrent_sessions,
            "account_takeover_signal": account_takeover_signal,
            "bot_score": str(bot_score),
        }
        return FraudAssessment(
            tenant_id, assessment_id, tuple(signals), bool(signals), rules_version, canonical_digest(facts)
        )

    @classmethod
    def redact(cls, fields: dict[str, object]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in fields.items():
            result[key] = "[REDACTED]" if cls._SENSITIVE_KEY.search(key) else value
        return result

    def request_privacy_action(
        self,
        *,
        request_id: str,
        tenant_id: str,
        subject_id: str,
        kind: str,
        legal_hold_reason: str | None = None,
    ) -> PrivacyRequest:
        _tenant(tenant_id)
        require(kind in {"ACCESS", "EXPORT", "DELETE"}, "PRIVACY_KIND_INVALID", "unsupported privacy request")
        require(
            bool(request_id.strip()) and bool(subject_id.strip()),
            "PRIVACY_IDENTITY_REQUIRED",
            "privacy identities are required",
        )
        state = "BLOCKED_LEGAL_HOLD" if kind == "DELETE" and legal_hold_reason else "PENDING"
        request = PrivacyRequest(request_id, tenant_id, subject_id, kind, state, legal_hold_reason)
        with self._lock:
            previous = self._privacy.get(request_id)
            if previous is not None:
                require(previous == request, "IDEMPOTENCY_CONFLICT", "privacy request id was reused")
                return previous
            self._privacy[request_id] = request
            return request

    @classmethod
    def validate_surface_policy(cls, surfaces: dict[str, str]) -> str:
        require(
            set(surfaces) == cls.REQUIRED_SURFACES,
            "POLICY_SURFACE_INCOMPLETE",
            "security policy must cover every required surface",
        )
        for surface, version in surfaces.items():
            require(bool(version.strip()), "POLICY_VERSION_REQUIRED", f"{surface} policy version is required")
        return canonical_digest(surfaces)

    @staticmethod
    def red_team_release_gate(results: dict[str, ExternalExecutionState]) -> dict[str, object]:
        required = {"authorization", "replay", "race", "injection", "secret-leak"}
        complete = set(results) == required and all(
            value is ExternalExecutionState.EXTERNALLY_VERIFIED for value in results.values()
        )
        return {
            "ready": complete,
            "certification": CertificationState.NOT_CERTIFIED,
            "external_execution": ExternalExecutionState.EXTERNALLY_VERIFIED
            if complete
            else ExternalExecutionState.NOT_RUN,
        }


@dataclass(frozen=True, slots=True)
class TraceSpan:
    tenant_id: str
    correlation_id: str
    stage: str
    subject_id: str
    occurred_at: datetime
    facts_digest: str


@dataclass(frozen=True, slots=True)
class SloDefinition:
    operation: str
    objective_basis_points: int
    window_seconds: int
    definition_version: str


@dataclass(frozen=True, slots=True)
class FinancialSignal:
    tenant_id: str
    kind: str
    subject_id: str
    severity: str
    facts_digest: str


@dataclass(frozen=True, slots=True)
class OperationsWorkItem:
    work_id: str
    tenant_id: str
    kind: str
    subject_id: str
    correlation_id: str
    state: str
    assigned_to: str | None
    replay_of: str | None


@dataclass(frozen=True, slots=True)
class RecoveryVerification:
    tenant_id: str
    before_digest: str
    after_digest: str
    ledger_balanced: bool
    idempotency_preserved: bool
    reconciliation_matched: bool


class BillingObservabilityOperationsService:
    """Local trace, alert, queue and replay controls for EB-16."""

    SIGNALS = frozenset(
        {"DUPLICATE", "LATE", "BUDGET_DRIFT", "NEGATIVE_BALANCE", "LEDGER_IMBALANCE", "RECONCILIATION_DIFFERENCE"}
    )
    SLO_OPERATIONS = frozenset({"quote", "authorization", "metering", "payment", "refund", "reconciliation"})

    def __init__(self) -> None:
        self._lock = RLock()
        self._traces: list[TraceSpan] = []
        self._signals: list[FinancialSignal] = []
        self._slo: dict[str, SloDefinition] = {}
        self._modes: dict[str, OperationsMode] = {}
        self._work: dict[str, OperationsWorkItem] = {}

    def record_trace(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        stage: str,
        subject_id: str,
        occurred_at: datetime,
        facts: object,
    ) -> TraceSpan:
        _tenant(tenant_id)
        require(
            stage in {"quote", "authorization", "usage", "invoice", "payment", "refund", "reconciliation"},
            "TRACE_STAGE_INVALID",
            "unsupported trace stage",
        )
        require(
            bool(correlation_id.strip()) and bool(subject_id.strip()),
            "TRACE_IDENTITY_REQUIRED",
            "trace identities are required",
        )
        span = TraceSpan(
            tenant_id,
            correlation_id,
            stage,
            subject_id,
            require_aware(occurred_at, field_name="occurred_at"),
            canonical_digest(facts),
        )
        with self._lock:
            self._traces.append(span)
        return span

    def trace(self, *, tenant_id: str, correlation_id: str) -> tuple[TraceSpan, ...]:
        _tenant(tenant_id)
        with self._lock:
            return tuple(
                span for span in self._traces if span.tenant_id == tenant_id and span.correlation_id == correlation_id
            )

    def observe_signal(
        self, *, tenant_id: str, kind: str, subject_id: str, severity: str, facts: object
    ) -> FinancialSignal:
        _tenant(tenant_id)
        require(kind in self.SIGNALS, "SIGNAL_KIND_INVALID", "unsupported financial signal")
        require(severity in {"INFO", "WARNING", "CRITICAL"}, "SEVERITY_INVALID", "unsupported severity")
        signal = FinancialSignal(tenant_id, kind, subject_id, severity, canonical_digest(facts))
        with self._lock:
            self._signals.append(signal)
            if kind in {"NEGATIVE_BALANCE", "LEDGER_IMBALANCE"} and severity == "CRITICAL":
                self._modes[tenant_id] = OperationsMode.KILLED
            elif kind == "RECONCILIATION_DIFFERENCE" and severity == "CRITICAL":
                self._modes[tenant_id] = OperationsMode.READ_ONLY
        return signal

    def configure_slo(self, definition: SloDefinition) -> SloDefinition:
        require(definition.operation in self.SLO_OPERATIONS, "SLO_OPERATION_INVALID", "unsupported SLO operation")
        require(0 < definition.objective_basis_points <= 10_000, "SLO_OBJECTIVE_INVALID", "SLO objective is invalid")
        require(definition.window_seconds > 0, "SLO_WINDOW_INVALID", "SLO window must be positive")
        require(bool(definition.definition_version.strip()), "SLO_VERSION_REQUIRED", "SLO version is required")
        with self._lock:
            self._slo[definition.operation] = definition
        return definition

    def slo_complete(self) -> bool:
        with self._lock:
            return set(self._slo) == self.SLO_OPERATIONS

    def mode(self, *, tenant_id: str) -> OperationsMode:
        _tenant(tenant_id)
        with self._lock:
            return self._modes.get(tenant_id, OperationsMode.ACTIVE)

    def assert_mutable(self, *, tenant_id: str) -> None:
        require(
            self.mode(tenant_id=tenant_id) is OperationsMode.ACTIVE,
            "FINANCIAL_WRITES_DISABLED",
            "tenant financial writes are disabled",
        )

    def enqueue(
        self,
        *,
        work_id: str,
        tenant_id: str,
        kind: str,
        subject_id: str,
        correlation_id: str,
        replay_of: str | None = None,
    ) -> OperationsWorkItem:
        _tenant(tenant_id)
        require(
            kind in {"STUCK_SAGA", "DEAD_LETTER", "INCONSISTENCY", "REPLAY", "REBUILD", "RECONCILE"},
            "WORK_KIND_INVALID",
            "unsupported work kind",
        )
        item = OperationsWorkItem(work_id, tenant_id, kind, subject_id, correlation_id, "PENDING", None, replay_of)
        with self._lock:
            previous = self._work.get(work_id)
            if previous is not None:
                require(previous == item, "IDEMPOTENCY_CONFLICT", "work id was reused")
                return previous
            self._work[work_id] = item
            return item

    def assign(self, *, work_id: str, tenant_id: str, assigned_to: str) -> OperationsWorkItem:
        with self._lock:
            item = self._required_work(work_id, tenant_id)
            require(item.state == "PENDING", "WORK_NOT_PENDING", "only pending work may be assigned")
            require(bool(assigned_to.strip()), "ASSIGNEE_REQUIRED", "assignee is required")
            assigned = replace(item, state="ASSIGNED", assigned_to=assigned_to)
            self._work[work_id] = assigned
            return assigned

    def replay(self, *, work_id: str, tenant_id: str, new_work_id: str) -> OperationsWorkItem:
        with self._lock:
            original = self._required_work(work_id, tenant_id)
            require(original.state in {"FAILED", "ASSIGNED"}, "WORK_NOT_REPLAYABLE", "work is not replayable")
        return self.enqueue(
            work_id=new_work_id,
            tenant_id=tenant_id,
            kind="REPLAY",
            subject_id=original.subject_id,
            correlation_id=original.correlation_id,
            replay_of=work_id,
        )

    @staticmethod
    def verify_recovery(
        *,
        tenant_id: str,
        before: object,
        after: object,
        ledger_balanced: bool,
        idempotency_preserved: bool,
        reconciliation_matched: bool,
    ) -> RecoveryVerification:
        _tenant(tenant_id)
        return RecoveryVerification(
            tenant_id,
            canonical_digest(before),
            canonical_digest(after),
            ledger_balanced,
            idempotency_preserved,
            reconciliation_matched,
        )

    @staticmethod
    def recovery_ready(verification: RecoveryVerification) -> bool:
        return (
            verification.ledger_balanced and verification.idempotency_preserved and verification.reconciliation_matched
        )

    @staticmethod
    def backup_dr_contract(*, asset_kinds: tuple[str, ...], rpo_seconds: int, rto_seconds: int) -> dict[str, object]:
        require(
            set(asset_kinds) == {"ledger", "contract", "invoice", "audit"},
            "BACKUP_SCOPE_INCOMPLETE",
            "backup scope is incomplete",
        )
        require(rpo_seconds >= 0 and rto_seconds > 0, "RECOVERY_OBJECTIVE_INVALID", "RPO/RTO is invalid")
        return {
            "asset_kinds": tuple(sorted(asset_kinds)),
            "rpo_seconds": rpo_seconds,
            "rto_seconds": rto_seconds,
            "backup_execution": ExternalExecutionState.NOT_RUN,
            "restore_drill": ExternalExecutionState.NOT_RUN,
            "certification": CertificationState.NOT_CERTIFIED,
        }

    @staticmethod
    def incident_report(
        *,
        incident_id: str,
        timeline: tuple[str, ...],
        financial_impact: dict[str, str],
        root_cause: str,
        prevention_actions: tuple[str, ...],
    ) -> dict[str, object]:
        require(bool(incident_id.strip()), "INCIDENT_ID_REQUIRED", "incident id is required")
        require(
            bool(timeline) and bool(financial_impact), "INCIDENT_EVIDENCE_REQUIRED", "timeline and impact are required"
        )
        require(
            bool(root_cause.strip()) and bool(prevention_actions),
            "INCIDENT_CLOSURE_REQUIRED",
            "root cause and prevention are required",
        )
        report = {
            "incident_id": incident_id,
            "timeline": timeline,
            "financial_impact": financial_impact,
            "root_cause": root_cause,
            "prevention_actions": prevention_actions,
        }
        return {**report, "digest": canonical_digest(report)}

    def _required_work(self, work_id: str, tenant_id: str) -> OperationsWorkItem:
        try:
            item = self._work[work_id]
        except KeyError as exc:
            raise DomainError("WORK_NOT_FOUND", "operations work item was not found") from exc
        require(item.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "work belongs to another tenant")
        return item


def _tenant(tenant_id: str) -> None:
    require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant id is required")
    require(tenant_id != "*", "WILDCARD_TENANT_FORBIDDEN", "wildcard tenant is forbidden")


def _non_negative(value: Decimal, field: str) -> None:
    require(value.is_finite(), "DECIMAL_NOT_FINITE", f"{field} must be finite")
    require(value >= Decimal("0"), "NEGATIVE_VALUE", f"{field} must be non-negative")


def canonical_digest(value: object) -> str:
    return _base_digest(_canonical_local(value))


def _canonical_local(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_local(asdict(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical_local(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical_local(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_canonical_local(item) for item in value)
    return value
