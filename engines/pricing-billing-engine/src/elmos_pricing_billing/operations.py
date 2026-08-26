from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Protocol

from .errors import DomainError, require
from .ledger import LedgerService
from .models import (
    AdminSnapshot,
    AuditEvent,
    AuthorizationDecision,
    ChargeAuthority,
    ChargeDecision,
    ExternalEvidenceState,
    MarginView,
    MigrationMode,
    QualificationReport,
    ReadinessState,
    ShadowComparison,
    WorkItem,
    WorkState,
    canonical_digest,
    require_aware,
)
from .money import Money, checked_add, checked_mul, normalize_currency, require_non_negative, round_half_up_div
from .registry import EXTERNAL_BOUNDARIES as REGISTRY_EXTERNAL_BOUNDARIES
from .registry import LocalImplementationState
from .usage import UsageMeteringService


class SuspenseCaseReader(Protocol):
    def suspense_cases(self, *, tenant_id: str) -> tuple[object, ...]: ...


class MarginAnalyticsService:
    """Pure read model; it has no path to mutate prices, invoices, or ledger state."""

    @staticmethod
    def calculate(
        *,
        currency: str,
        revenue_minor: int,
        provider_cost_minor: int,
        runner_cost_minor: int,
        support_cost_minor: int,
    ) -> MarginView:
        for value in (revenue_minor, provider_cost_minor, runner_cost_minor, support_cost_minor):
            require_non_negative(value, field="margin_input_minor")
        costs = checked_add(
            provider_cost_minor,
            runner_cost_minor,
            support_cost_minor,
            field="total_cost_minor",
        )
        margin = checked_add(revenue_minor, -costs, field="margin_minor")
        basis_points = (
            None
            if revenue_minor == 0
            else round_half_up_div(checked_mul(margin, 10_000, field="margin_basis_points_numerator"), revenue_minor)
        )
        return MarginView(
            currency=normalize_currency(currency),
            revenue_minor=revenue_minor,
            provider_cost_minor=provider_cost_minor,
            runner_cost_minor=runner_cost_minor,
            support_cost_minor=support_cost_minor,
            margin_minor=margin,
            margin_basis_points=basis_points,
        )


class AuditOperationsService:
    """Correlation, immutable audit, kill switches, local work queues, replay, and recovery."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._audit: list[AuditEvent] = []
        self._audit_sequences: dict[str, int] = {}
        self._kill_switches: set[str] = set()
        self._work: dict[str, WorkItem] = {}

    def record_audit(
        self,
        *,
        tenant_id: str,
        correlation_id: str,
        actor: str,
        action: str,
        outcome: str,
        occurred_at: datetime,
        details: object,
    ) -> AuditEvent:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(tenant_id != "*", "WILDCARD_TENANT_FORBIDDEN", "wildcard tenant mutation is forbidden")
        require(bool(correlation_id.strip()), "CORRELATION_ID_REQUIRED", "correlation id is required")
        require(bool(actor.strip()), "ACTOR_REQUIRED", "actor is required")
        require(bool(action.strip()), "ACTION_REQUIRED", "action is required")
        require(bool(outcome.strip()), "OUTCOME_REQUIRED", "outcome is required")
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            sequence = checked_add(self._audit_sequences.get(tenant_id, 0), 1, field="audit_sequence")
            event = AuditEvent(
                sequence=sequence,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                actor=actor,
                action=action,
                outcome=outcome,
                occurred_at=normalized_at,
                details_digest=canonical_digest(details),
            )
            self._audit.append(event)
            self._audit_sequences[tenant_id] = sequence
            return event

    def set_kill_switch(
        self,
        *,
        tenant_id: str,
        enabled: bool,
        actor: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> AuditEvent:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(tenant_id != "*", "WILDCARD_TENANT_FORBIDDEN", "wildcard tenant mutation is forbidden")
        require(bool(correlation_id.strip()), "CORRELATION_ID_REQUIRED", "correlation id is required")
        require(bool(actor.strip()), "ACTOR_REQUIRED", "actor is required")
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            if enabled:
                self._kill_switches.add(tenant_id)
            else:
                self._kill_switches.discard(tenant_id)
            return self.record_audit(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                actor=actor,
                action="kill-switch:set",
                outcome="ENABLED" if enabled else "DISABLED",
                occurred_at=normalized_at,
                details={"enabled": enabled},
            )

    def is_killed(self, *, tenant_id: str) -> bool:
        with self._lock:
            return tenant_id in self._kill_switches

    def assert_enabled(self, *, tenant_id: str, operation: str) -> None:
        require(not self.is_killed(tenant_id=tenant_id), "KILL_SWITCH_ACTIVE", f"operation {operation} is disabled")

    def enqueue(
        self,
        *,
        work_id: str,
        tenant_id: str,
        correlation_id: str,
        operation: str,
    ) -> WorkItem:
        require(bool(work_id.strip()), "WORK_ID_REQUIRED", "work_id is required")
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(correlation_id.strip()), "CORRELATION_ID_REQUIRED", "correlation id is required")
        require(bool(operation.strip()), "OPERATION_REQUIRED", "operation is required")
        with self._lock:
            self.assert_enabled(tenant_id=tenant_id, operation=operation)
            require(work_id not in self._work, "WORK_ITEM_EXISTS", "work item already exists")
            item = WorkItem(
                work_id=work_id,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                operation=operation,
                state=WorkState.PENDING,
                attempt=1,
            )
            self._work[work_id] = item
            return item

    def claim(self, *, work_id: str, tenant_id: str) -> WorkItem:
        with self._lock:
            self.assert_enabled(tenant_id=tenant_id, operation="work:claim")
            item = self._required_work(work_id, tenant_id)
            require(item.state is WorkState.PENDING, "WORK_NOT_PENDING", "only pending work may be claimed")
            claimed = replace(item, state=WorkState.RUNNING)
            self._work[work_id] = claimed
            return claimed

    def complete(self, *, work_id: str, tenant_id: str) -> WorkItem:
        with self._lock:
            item = self._required_work(work_id, tenant_id)
            require(item.state is WorkState.RUNNING, "WORK_NOT_RUNNING", "only running work may complete")
            completed = replace(item, state=WorkState.SUCCEEDED)
            self._work[work_id] = completed
            return completed

    def fail(self, *, work_id: str, tenant_id: str, error_code: str) -> WorkItem:
        with self._lock:
            item = self._required_work(work_id, tenant_id)
            require(item.state is WorkState.RUNNING, "WORK_NOT_RUNNING", "only running work may fail")
            failed = replace(item, state=WorkState.FAILED, error_code=error_code)
            self._work[work_id] = failed
            return failed

    def replay(self, *, failed_work_id: str, new_work_id: str, tenant_id: str) -> WorkItem:
        with self._lock:
            self.assert_enabled(tenant_id=tenant_id, operation="work:replay")
            failed = self._required_work(failed_work_id, tenant_id)
            require(failed.state is WorkState.FAILED, "WORK_NOT_FAILED", "only failed work may be replayed")
            require(new_work_id not in self._work, "WORK_ITEM_EXISTS", "replay id already exists")
            replay = WorkItem(
                work_id=new_work_id,
                tenant_id=tenant_id,
                correlation_id=failed.correlation_id,
                operation=failed.operation,
                state=WorkState.PENDING,
                attempt=failed.attempt + 1,
                replay_of=failed.work_id,
            )
            self._work[new_work_id] = replay
            return replay

    def recoverable(self, *, tenant_id: str) -> tuple[WorkItem, ...]:
        with self._lock:
            return tuple(
                item
                for item in self._work.values()
                if item.tenant_id == tenant_id and item.state in {WorkState.PENDING, WorkState.FAILED}
            )

    def work_items(self, *, tenant_id: str) -> tuple[WorkItem, ...]:
        with self._lock:
            return tuple(item for item in self._work.values() if item.tenant_id == tenant_id)

    def audit_events(self, *, tenant_id: str) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(event for event in self._audit if event.tenant_id == tenant_id)

    def _required_work(self, work_id: str, tenant_id: str) -> WorkItem:
        try:
            item = self._work[work_id]
        except KeyError as exc:
            raise DomainError("WORK_ITEM_NOT_FOUND", "work item was not found") from exc
        require(item.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "work item belongs to another tenant")
        return item


class SecurityComplianceService:
    """Small deny-by-default local authorization reference with audit binding."""

    _ROLE_ACTIONS: dict[str, frozenset[str]] = {
        "VIEWER": frozenset({"billing:read", "margin:read"}),
        "OPERATOR": frozenset({"billing:read", "margin:read", "work:execute", "quote:create"}),
        "APPROVER": frozenset({"billing:read", "margin:read", "quote:accept", "refund:approve", "change:approve"}),
    }

    def __init__(self, operations: AuditOperationsService) -> None:
        self._operations = operations

    def authorize(
        self,
        *,
        principal_id: str,
        principal_tenant_id: str,
        resource_tenant_id: str,
        role: str,
        action: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> AuthorizationDecision:
        require(bool(principal_id.strip()), "PRINCIPAL_REQUIRED", "principal_id is required")
        require(bool(principal_tenant_id.strip()), "TENANT_REQUIRED", "principal tenant is required")
        require(bool(resource_tenant_id.strip()), "TENANT_REQUIRED", "resource tenant is required")
        require(bool(role.strip()), "ROLE_REQUIRED", "role is required")
        require(bool(action.strip()), "ACTION_REQUIRED", "action is required")
        role_actions = self._ROLE_ACTIONS.get(role, frozenset())
        same_tenant = principal_tenant_id == resource_tenant_id
        allowed = same_tenant and action in role_actions
        reason = "ALLOWED" if allowed else ("TENANT_MISMATCH" if not same_tenant else "ACTION_NOT_GRANTED")
        decision = AuthorizationDecision(
            allowed=allowed,
            tenant_id=resource_tenant_id,
            principal_id=principal_id,
            role=role,
            action=action,
            reason=reason,
        )
        self._operations.record_audit(
            tenant_id=resource_tenant_id,
            correlation_id=correlation_id,
            actor=principal_id,
            action=f"authorize:{action}",
            outcome=reason,
            occurred_at=occurred_at,
            details={"role": role, "principal_tenant": principal_tenant_id},
        )
        return decision

    @staticmethod
    def validate_secret_reference(value: str) -> str:
        require(
            value.startswith("secret://") and len(value) > len("secret://"),
            "SECRET_REFERENCE_REQUIRED",
            "secret reference is invalid",
        )
        require("=" not in value and " " not in value, "INLINE_SECRET_FORBIDDEN", "secret values must not be embedded")
        return value


class MigrationService:
    """Opening balances, shadow/canary decisions, and one local simulation authority."""

    def __init__(self, ledger: LedgerService, *, environment: str = "local") -> None:
        require(
            environment in {"local", "test"}, "PRODUCTION_AUTHORITY_FORBIDDEN", "reference migration is local/test only"
        )
        self._ledger = ledger
        self._environment = environment
        self._lock = RLock()
        self._mode = MigrationMode.SHADOW
        self._canary_tenants: set[str] = set()
        self._opening_keys: dict[tuple[str, str], tuple[int, str, str]] = {}
        self._comparisons: dict[str, ShadowComparison] = {}

    def import_opening_balance(
        self,
        *,
        tenant_id: str,
        money: Money,
        source_snapshot_digest: str,
        occurred_at: datetime,
    ) -> str:
        require(bool(source_snapshot_digest.strip()), "SOURCE_SNAPSHOT_DIGEST_REQUIRED", "snapshot digest is required")
        key = (tenant_id, money.currency)
        with self._lock:
            existing = self._opening_keys.get(key)
            if existing is not None:
                require(
                    existing[:2] == (money.minor, source_snapshot_digest),
                    "OPENING_BALANCE_CONFLICT",
                    "opening balance or source snapshot differs from prior import",
                )
                return existing[2]
            transaction = self._ledger.opening_balance(
                tenant_id=tenant_id,
                money=money,
                idempotency_key=f"opening:{source_snapshot_digest}",
                reference=source_snapshot_digest,
                occurred_at=occurred_at,
            )
            self._opening_keys[key] = (money.minor, source_snapshot_digest, transaction.transaction_id)
            return transaction.transaction_id

    def compare_shadow(
        self,
        *,
        comparison_id: str,
        tenant_id: str,
        reference: str,
        external_minor: int,
        simulated_minor: int,
    ) -> ShadowComparison:
        require(bool(comparison_id.strip()), "COMPARISON_ID_REQUIRED", "comparison_id is required")
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(reference.strip()), "REFERENCE_REQUIRED", "reference is required")
        require_non_negative(external_minor, field="external_minor")
        require_non_negative(simulated_minor, field="simulated_minor")
        with self._lock:
            require(comparison_id not in self._comparisons, "SHADOW_COMPARISON_EXISTS", "comparison id exists")
            comparison = ShadowComparison(
                comparison_id=comparison_id,
                tenant_id=tenant_id,
                reference=reference,
                external_minor=external_minor,
                simulated_minor=simulated_minor,
                matched=external_minor == simulated_minor,
            )
            self._comparisons[comparison_id] = comparison
            return comparison

    def set_mode(self, *, mode: MigrationMode) -> None:
        with self._lock:
            self._mode = mode

    def set_canary(self, *, tenant_id: str, enabled: bool) -> None:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        with self._lock:
            if enabled:
                self._canary_tenants.add(tenant_id)
            else:
                self._canary_tenants.discard(tenant_id)

    def charge_decision(self, *, tenant_id: str) -> ChargeDecision:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        with self._lock:
            local = self._mode is MigrationMode.LOCAL_ONLY or (
                self._mode is MigrationMode.CANARY and tenant_id in self._canary_tenants
            )
            authority = ChargeAuthority.LOCAL_SIMULATION if local else ChargeAuthority.EXTERNAL_SYSTEM_NOT_INVOKED
            return ChargeDecision(
                tenant_id=tenant_id,
                mode=self._mode,
                authority=authority,
                simulation_only=True,
            )


class AdminProjectionService:
    """Read-only admin projection over already-authoritative local facts."""

    def __init__(
        self,
        *,
        ledger: LedgerService,
        usage: UsageMeteringService,
        payments: SuspenseCaseReader,
        operations: AuditOperationsService,
    ) -> None:
        self._ledger = ledger
        self._usage = usage
        self._payments = payments
        self._operations = operations

    def snapshot(self, *, tenant_id: str, currency: str) -> AdminSnapshot:
        balance = self._ledger.balance(tenant_id=tenant_id, currency=currency)
        suspense = self._payments.suspense_cases(tenant_id=tenant_id)
        return AdminSnapshot(
            tenant_id=tenant_id,
            currency=balance.currency,
            available_minor=balance.available_minor,
            reserved_minor=balance.reserved_minor,
            captured_minor=balance.captured_minor,
            rated_usage_count=len(self._usage.events(tenant_id=tenant_id)),
            suspense_count=len(suspense),
            work_item_count=len(self._operations.work_items(tenant_id=tenant_id)),
            kill_switch_enabled=self._operations.is_killed(tenant_id=tenant_id),
        )


class QualificationService:
    """Local evidence gate whose state ceiling excludes external or production claims."""

    EXTERNAL_BOUNDARIES: tuple[tuple[str, ExternalEvidenceState], ...] = tuple(
        (name, ExternalEvidenceState(state)) for name, state in REGISTRY_EXTERNAL_BOUNDARIES
    )

    @classmethod
    def build_report(
        cls,
        *,
        expected_handlers: tuple[str, ...],
        handler_results: dict[str, bool],
    ) -> QualificationReport:
        require(
            set(handler_results) == set(expected_handlers),
            "HANDLER_COVERAGE_INCOMPLETE",
            "qualification must cover every exact handler",
        )
        require(
            len(expected_handlers) == len(set(expected_handlers)),
            "HANDLER_COVERAGE_INVALID",
            "expected handler names must be unique",
        )
        ordered = tuple(
            (
                name,
                LocalImplementationState.LOCAL_EXECUTED if handler_results[name] else LocalImplementationState.PARTIAL,
            )
            for name in expected_handlers
        )
        if all(state is LocalImplementationState.LOCAL_EXECUTED for _, state in ordered):
            readiness = ReadinessState.LOCAL_EXECUTED
        else:
            readiness = ReadinessState.DECLARED
        return QualificationReport(
            readiness=readiness,
            handler_results=ordered,
            external_evidence=cls.EXTERNAL_BOUNDARIES,
            limitations=(
                "No payment provider or bank operation was executed.",
                "No production charging authority is implemented.",
                "No DR, independent holdout, customer, tax, accounting, or external certification evidence exists.",
                "State is in-memory and same-process only; restart durability and crash recovery were not executed.",
            ),
        )
