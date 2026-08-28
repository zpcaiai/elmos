from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from threading import RLock
from typing import Any

from .errors import DomainError, require
from .models import canonical_digest as _base_digest
from .models import require_aware
from .operations_closure import CertificationState, ExternalExecutionState


class ImplementationState(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    STUB = "STUB"
    MISSING = "MISSING"
    NOT_VERIFIED = "NOT_VERIFIED"


class MigrationAuthority(StrEnum):
    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
    NEW = "NEW"
    READ_ONLY_LEGACY = "READ_ONLY_LEGACY"


@dataclass(frozen=True, slots=True)
class RequirementTrace:
    requirement_id: str
    source_file: str | None
    symbol: str | None
    test_node_id: str | None
    test_state: ExternalExecutionState
    runtime_evidence_digest: str | None
    commit: str | None
    behavior_implemented: bool
    acceptance_complete: bool
    stub_only: bool = False

    @property
    def state(self) -> ImplementationState:
        if self.source_file is None or self.symbol is None:
            return ImplementationState.MISSING
        if self.stub_only:
            return ImplementationState.STUB
        if not self.behavior_implemented or not self.acceptance_complete:
            return ImplementationState.PARTIAL
        if (
            self.test_node_id is None
            or self.test_state is ExternalExecutionState.NOT_RUN
            or self.runtime_evidence_digest is None
            or self.commit is None
        ):
            return ImplementationState.NOT_VERIFIED
        return ImplementationState.IMPLEMENTED


@dataclass(frozen=True, slots=True)
class RepositoryBaseline:
    baseline_id: str
    repository_commit: str
    capabilities: tuple[str, ...]
    captured_at: datetime
    digest: str


@dataclass(frozen=True, slots=True)
class BatchNode:
    batch_id: str
    dependencies: tuple[str, ...]
    resumable: bool
    parallel_group: str


@dataclass(frozen=True, slots=True)
class WorkCheckpoint:
    checkpoint_id: str
    tenant_id: str
    batch_id: str
    input_digest: str
    code_baseline: str
    completed_nodes: tuple[str, ...]
    output_digest: str
    cost_snapshot: Decimal
    billing_receipt_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HandoffReceipt:
    handoff_id: str
    checkpoint_id: str
    from_agent: str
    to_agent: str
    evidence_digest: str
    billing_receipt_id: str


@dataclass(frozen=True, slots=True)
class ContractChangeCandidate:
    candidate_id: str
    contract_id: str
    old_scope_digest: str
    new_scope_digest: str
    adr_id: str
    impact_digest: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReleaseGateDecision:
    allowed: bool
    failed_domains: tuple[str, ...]
    evaluated_digest: str
    maximum_decision: CertificationState


class RequirementTraceabilityService:
    """Machine-derived five-state traceability without status inflation."""

    def __init__(self, requirement_ids: tuple[str, ...]) -> None:
        require(
            len(requirement_ids) == len(set(requirement_ids)), "REQUIREMENT_DUPLICATE", "requirement ids must be unique"
        )
        self._required = frozenset(requirement_ids)
        self._traces: dict[str, RequirementTrace] = {}

    def record(self, trace: RequirementTrace) -> RequirementTrace:
        require(trace.requirement_id in self._required, "REQUIREMENT_UNKNOWN", "requirement is not in the catalog")
        previous = self._traces.get(trace.requirement_id)
        if previous is not None:
            require(previous == trace, "TRACE_IMMUTABLE", "requirement trace is immutable")
        self._traces[trace.requirement_id] = trace
        return trace

    def status(self, requirement_id: str) -> ImplementationState:
        require(requirement_id in self._required, "REQUIREMENT_UNKNOWN", "requirement is not in the catalog")
        trace = self._traces.get(requirement_id)
        return ImplementationState.MISSING if trace is None else trace.state

    def machine_report(self) -> dict[str, object]:
        rows = [
            {
                "requirement_id": requirement_id,
                "state": self.status(requirement_id),
                "trace": self._traces.get(requirement_id),
            }
            for requirement_id in sorted(self._required)
        ]
        return {
            "requirement_count": len(rows),
            "rows": rows,
            "digest": canonical_digest(rows),
        }


class BillingOrchestrationService:
    """Exact orchestration contracts for EB-01."""

    RELEASE_DOMAINS = (
        "security",
        "ledger-balance",
        "reconciliation",
        "performance",
        "recovery",
        "rollback",
    )

    def __init__(self) -> None:
        self._lock = RLock()
        self._baselines: dict[str, RepositoryBaseline] = {}
        self._checkpoints: dict[str, WorkCheckpoint] = {}
        self._handoffs: dict[str, HandoffReceipt] = {}
        self._changes: dict[str, ContractChangeCandidate] = {}

    def capture_baseline(
        self,
        *,
        baseline_id: str,
        repository_commit: str,
        capabilities: tuple[str, ...],
        captured_at: datetime,
    ) -> RepositoryBaseline:
        required = {"billing", "task", "payment", "model", "tenant"}
        require(required <= set(capabilities), "BASELINE_INCOMPLETE", "billing baseline is incomplete")
        require(bool(repository_commit.strip()), "COMMIT_REQUIRED", "repository commit is required")
        timestamp = require_aware(captured_at, field_name="captured_at")
        facts = {
            "baseline_id": baseline_id,
            "repository_commit": repository_commit,
            "capabilities": tuple(sorted(capabilities)),
            "captured_at": timestamp,
        }
        baseline = RepositoryBaseline(
            baseline_id, repository_commit, tuple(sorted(capabilities)), timestamp, canonical_digest(facts)
        )
        with self._lock:
            previous = self._baselines.get(baseline_id)
            if previous is not None:
                require(previous == baseline, "IDEMPOTENCY_CONFLICT", "baseline id was reused")
                return previous
            self._baselines[baseline_id] = baseline
            return baseline

    @staticmethod
    def dependency_order(nodes: tuple[BatchNode, ...]) -> tuple[str, ...]:
        by_id = {node.batch_id: node for node in nodes}
        require(len(by_id) == len(nodes), "BATCH_DUPLICATE", "batch ids must be unique")
        for node in nodes:
            require(node.resumable, "BATCH_NOT_RESUMABLE", "every batch must be resumable")
            require(bool(node.parallel_group.strip()), "PARALLEL_GROUP_REQUIRED", "parallel group is required")
            require(set(node.dependencies) <= set(by_id), "DEPENDENCY_UNKNOWN", "batch dependency is unknown")
            require(node.batch_id not in node.dependencies, "DEPENDENCY_SELF_CYCLE", "batch cannot depend on itself")
        remaining = {key: set(value.dependencies) for key, value in by_id.items()}
        ordered: list[str] = []
        while remaining:
            ready = sorted(key for key, dependencies in remaining.items() if not dependencies)
            require(bool(ready), "DEPENDENCY_CYCLE", "batch dependency graph contains a cycle")
            ordered.extend(ready)
            for key in ready:
                remaining.pop(key)
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
        return tuple(ordered)

    def save_checkpoint(
        self,
        *,
        checkpoint_id: str,
        tenant_id: str,
        batch_id: str,
        inputs: object,
        code_baseline: str,
        completed_nodes: tuple[str, ...],
        output: object,
        cost_snapshot: Decimal,
        billing_receipt_id: str,
        created_at: datetime,
    ) -> WorkCheckpoint:
        _tenant(tenant_id)
        require(
            bool(checkpoint_id.strip()) and bool(batch_id.strip()),
            "CHECKPOINT_IDENTITY_REQUIRED",
            "checkpoint identities are required",
        )
        require(
            bool(code_baseline.strip()) and bool(billing_receipt_id.strip()),
            "CHECKPOINT_BINDING_REQUIRED",
            "code and billing bindings are required",
        )
        require(
            cost_snapshot.is_finite() and cost_snapshot >= Decimal("0"),
            "COST_SNAPSHOT_INVALID",
            "cost snapshot is invalid",
        )
        checkpoint = WorkCheckpoint(
            checkpoint_id,
            tenant_id,
            batch_id,
            canonical_digest(inputs),
            code_baseline,
            completed_nodes,
            canonical_digest(output),
            cost_snapshot,
            billing_receipt_id,
            require_aware(created_at, field_name="created_at"),
        )
        with self._lock:
            previous = self._checkpoints.get(checkpoint_id)
            if previous is not None:
                require(previous == checkpoint, "IDEMPOTENCY_CONFLICT", "checkpoint id was reused")
                return previous
            self._checkpoints[checkpoint_id] = checkpoint
            return checkpoint

    def handoff(
        self,
        *,
        handoff_id: str,
        checkpoint_id: str,
        from_agent: str,
        to_agent: str,
        tenant_id: str,
    ) -> HandoffReceipt:
        with self._lock:
            checkpoint = self._required_checkpoint(checkpoint_id, tenant_id)
            require(from_agent != to_agent, "HANDOFF_AGENT_CONFLICT", "handoff agents must differ")
            require(
                bool(from_agent.strip()) and bool(to_agent.strip()),
                "HANDOFF_AGENT_REQUIRED",
                "handoff agents are required",
            )
            receipt = HandoffReceipt(
                handoff_id,
                checkpoint_id,
                from_agent,
                to_agent,
                canonical_digest(checkpoint),
                checkpoint.billing_receipt_id,
            )
            previous = self._handoffs.get(handoff_id)
            if previous is not None:
                require(previous == receipt, "IDEMPOTENCY_CONFLICT", "handoff id was reused")
                return previous
            self._handoffs[handoff_id] = receipt
            return receipt

    @staticmethod
    def authorize_contract_change(
        *,
        contract_id: str,
        fixed_price: bool,
        old_scope: object,
        new_scope: object,
        adr_id: str,
        impact_analysis: object,
        reason: str,
    ) -> ContractChangeCandidate | None:
        old_digest = canonical_digest(old_scope)
        new_digest = canonical_digest(new_scope)
        if old_digest == new_digest:
            return None
        require(bool(adr_id.strip()), "ADR_REQUIRED", "contract change requires an ADR")
        require(bool(reason.strip()), "CHANGE_REASON_REQUIRED", "contract change reason is required")
        require(
            fixed_price, "IMPLICIT_CONTRACT_CHANGE_FORBIDDEN", "non-fixed contract changes require their own workflow"
        )
        return ContractChangeCandidate(
            canonical_digest({"contract_id": contract_id, "old": old_digest, "new": new_digest, "adr_id": adr_id})[:24],
            contract_id,
            old_digest,
            new_digest,
            adr_id,
            canonical_digest(impact_analysis),
            reason,
        )

    @classmethod
    def release_gate(cls, results: dict[str, bool]) -> ReleaseGateDecision:
        require(
            set(results) == set(cls.RELEASE_DOMAINS), "RELEASE_GATE_INCOMPLETE", "release gate domains are incomplete"
        )
        failed = tuple(domain for domain in cls.RELEASE_DOMAINS if not results[domain])
        return ReleaseGateDecision(
            allowed=not failed,
            failed_domains=failed,
            evaluated_digest=canonical_digest(results),
            maximum_decision=CertificationState.READY_FOR_EXTERNAL_GATE
            if not failed
            else CertificationState.NOT_CERTIFIED,
        )

    @staticmethod
    def completion_trace(
        *,
        requirement_id: str,
        files: tuple[str, ...],
        symbols: tuple[str, ...],
        tests: tuple[str, ...],
        runtime_evidence: tuple[str, ...],
        commit: str | None,
    ) -> dict[str, object]:
        require(
            bool(files) and bool(symbols) and bool(tests), "TRACE_INCOMPLETE", "source, symbols and tests are required"
        )
        report = {
            "requirement_id": requirement_id,
            "files": files,
            "symbols": symbols,
            "tests": tests,
            "runtime_evidence": runtime_evidence,
            "commit": commit,
        }
        return {**report, "digest": canonical_digest(report)}

    def _required_checkpoint(self, checkpoint_id: str, tenant_id: str) -> WorkCheckpoint:
        try:
            checkpoint = self._checkpoints[checkpoint_id]
        except KeyError as exc:
            raise DomainError("CHECKPOINT_NOT_FOUND", "checkpoint was not found") from exc
        require(checkpoint.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "checkpoint belongs to another tenant")
        return checkpoint


@dataclass(frozen=True, slots=True)
class VerificationBinding:
    requirement_id: str
    test_node_ids: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    executor: str | None
    verifier: str | None
    authorization_id: str | None


@dataclass(frozen=True, slots=True)
class CertificationReport:
    environment_id: str
    commit: str
    requirement_count: int
    eligible: bool
    decision: CertificationState
    external_execution: ExternalExecutionState
    failed_requirements: tuple[str, ...]
    digest: str


class BillingQualificationService:
    """Conservative EB-17 test/evidence composition and certification ceiling."""

    PROPERTY_INVARIANTS = frozenset(
        {"ledger-balance", "non-negative-balance", "idempotency", "hard-cap", "refund-limit"}
    )
    CONTRACT_SURFACES = frozenset({"api", "event", "migration"})
    CONCURRENCY_CASES = frozenset({"reservation", "duplicate-event", "late-usage", "crash-recovery"})
    SECURITY_CASES = frozenset({"cross-tenant", "authorization", "secret", "replay", "injection", "fraud"})

    @staticmethod
    def require_complete_binding(binding: VerificationBinding) -> None:
        require(bool(binding.test_node_ids), "TEST_BINDING_REQUIRED", "requirement must bind tests")
        require(bool(binding.evidence_digests), "EVIDENCE_BINDING_REQUIRED", "requirement must bind evidence")
        require(
            bool(binding.executor) and bool(binding.verifier),
            "EVIDENCE_ROLES_REQUIRED",
            "executor and verifier are required",
        )
        require(
            binding.executor != binding.verifier, "SELF_VERIFICATION_FORBIDDEN", "executor and verifier must differ"
        )
        require(bool(binding.authorization_id), "AUTHORIZATION_REQUIRED", "authorization is required")

    @classmethod
    def property_suite(cls, results: dict[str, bool]) -> bool:
        return set(results) == cls.PROPERTY_INVARIANTS and all(results.values())

    @classmethod
    def contract_suite(cls, results: dict[str, bool]) -> bool:
        return set(results) == cls.CONTRACT_SURFACES and all(results.values())

    @classmethod
    def concurrency_suite(cls, results: dict[str, bool]) -> bool:
        return set(results) == cls.CONCURRENCY_CASES and all(results.values())

    @classmethod
    def security_suite(cls, results: dict[str, bool]) -> bool:
        return set(results) == cls.SECURITY_CASES and all(results.values())

    @staticmethod
    def payment_sandbox_evidence(
        *, sandbox_receipt: str | None, settlement_sample_digest: str | None
    ) -> ExternalExecutionState:
        if sandbox_receipt and settlement_sample_digest:
            return ExternalExecutionState.EXTERNALLY_VERIFIED
        return ExternalExecutionState.NOT_RUN

    @staticmethod
    def shadow_billing(*, old_total: Decimal, new_total: Decimal, tolerance: Decimal, explanation: str) -> bool:
        require(
            all(value.is_finite() for value in (old_total, new_total, tolerance)),
            "SHADOW_DECIMAL_INVALID",
            "shadow values must be finite",
        )
        require(tolerance >= Decimal("0"), "TOLERANCE_INVALID", "tolerance must be non-negative")
        require(bool(explanation.strip()), "SHADOW_EXPLANATION_REQUIRED", "shadow difference explanation is required")
        return abs(old_total - new_total) <= tolerance

    @staticmethod
    def certify(
        *,
        environment_id: str,
        commit: str,
        bindings: tuple[VerificationBinding, ...],
        p0_failures: tuple[str, ...],
        critical_invariant_failures: tuple[str, ...],
        external_levels: dict[str, ExternalExecutionState],
    ) -> CertificationReport:
        require(
            bool(environment_id.strip()) and bool(commit.strip()),
            "REPORT_BINDING_REQUIRED",
            "environment and commit are required",
        )
        failed = tuple(sorted(set(p0_failures + critical_invariant_failures)))
        unique_requirements = {binding.requirement_id for binding in bindings}
        all_external = bool(external_levels) and all(
            state is ExternalExecutionState.EXTERNALLY_VERIFIED for state in external_levels.values()
        )
        eligible = not failed and len(unique_requirements) == 180 and all_external
        decision = CertificationState.READY_FOR_EXTERNAL_GATE if eligible else CertificationState.NOT_CERTIFIED
        facts = {
            "environment_id": environment_id,
            "commit": commit,
            "requirements": tuple(sorted(unique_requirements)),
            "failed": failed,
            "external_levels": external_levels,
            "decision": decision,
        }
        return CertificationReport(
            environment_id,
            commit,
            len(unique_requirements),
            eligible,
            decision,
            ExternalExecutionState.EXTERNALLY_VERIFIED if all_external else ExternalExecutionState.NOT_RUN,
            failed,
            canonical_digest(facts),
        )


@dataclass(frozen=True, slots=True)
class MigrationAnomaly:
    anomaly_id: str
    tenant_id: str
    source_id: str
    kind: str
    facts_digest: str
    state: str


@dataclass(frozen=True, slots=True)
class MigratedRecord:
    migration_id: str
    tenant_id: str
    source_id: str
    source_hash: str
    source_version: str
    approved_by: str
    target_digest: str


@dataclass(frozen=True, slots=True)
class ShadowRating:
    tenant_id: str
    source_id: str
    legacy_amount: Decimal
    new_amount: Decimal
    difference: Decimal
    explanation: str
    within_tolerance: bool


@dataclass(frozen=True, slots=True)
class MigrationWave:
    wave_id: str
    tenant_ids: tuple[str, ...]
    risk_tier: str
    state: str
    rollback_reasons: tuple[str, ...]


class BillingMigrationService:
    """Idempotent, single-authority local migration contracts for EB-18."""

    ROLLBACK_SIGNALS = frozenset(
        {"DUPLICATE_CHARGE", "NEGATIVE_BALANCE", "BUDGET_BREACH", "SHADOW_DRIFT", "SLO_FAILURE"}
    )

    def __init__(self) -> None:
        self._lock = RLock()
        self._anomalies: dict[str, MigrationAnomaly] = {}
        self._records: dict[str, MigratedRecord] = {}
        self._authority: dict[str, MigrationAuthority] = {}
        self._waves: dict[str, MigrationWave] = {}
        self._legacy_retention: dict[str, dict[str, object]] = {}

    def assess_data_quality(
        self,
        *,
        tenant_id: str,
        source_id: str,
        facts: object,
        anomaly_kinds: tuple[str, ...],
    ) -> tuple[MigrationAnomaly, ...]:
        _tenant(tenant_id)
        items: list[MigrationAnomaly] = []
        for index, kind in enumerate(anomaly_kinds, start=1):
            require(bool(kind.strip()), "ANOMALY_KIND_REQUIRED", "anomaly kind is required")
            anomaly_id = canonical_digest({"tenant": tenant_id, "source": source_id, "kind": kind, "index": index})[:24]
            anomaly = MigrationAnomaly(anomaly_id, tenant_id, source_id, kind, canonical_digest(facts), "OPEN")
            with self._lock:
                self._anomalies[anomaly_id] = anomaly
            items.append(anomaly)
        return tuple(items)

    @staticmethod
    def opening_balance_entries(
        *, tenant_id: str, currency: str, amount: Decimal, reference: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        _tenant(tenant_id)
        require(amount.is_finite(), "OPENING_BALANCE_INVALID", "opening balance must be finite")
        require(
            bool(currency.strip()) and bool(reference.strip()),
            "OPENING_BALANCE_BINDING_REQUIRED",
            "currency and reference are required",
        )
        debit_amount = -amount
        credit_amount = amount
        debit: dict[str, object] = {
            "tenant_id": tenant_id,
            "account": "migration-clearing",
            "currency": currency,
            "amount": debit_amount,
            "reference": reference,
        }
        credit: dict[str, object] = {
            "tenant_id": tenant_id,
            "account": "customer-wallet",
            "currency": currency,
            "amount": credit_amount,
            "reference": reference,
        }
        require(
            debit_amount + credit_amount == Decimal("0"),
            "OPENING_BALANCE_UNBALANCED",
            "opening entries must balance",
        )
        return debit, credit

    def register_record(
        self,
        *,
        migration_id: str,
        tenant_id: str,
        source_id: str,
        source_payload: object,
        source_version: str,
        approved_by: str,
        target: object,
    ) -> MigratedRecord:
        _tenant(tenant_id)
        for value in (migration_id, source_id, source_version, approved_by):
            require(
                bool(value.strip()),
                "MIGRATION_BINDING_REQUIRED",
                "migration identity, version and approval are required",
            )
        record = MigratedRecord(
            migration_id,
            tenant_id,
            source_id,
            canonical_digest(source_payload),
            source_version,
            approved_by,
            canonical_digest(target),
        )
        with self._lock:
            previous = self._records.get(migration_id)
            if previous is not None:
                require(previous == record, "IDEMPOTENCY_CONFLICT", "migration id was reused")
                return previous
            self._records[migration_id] = record
            return record

    @staticmethod
    def shadow_rate(
        *,
        tenant_id: str,
        source_id: str,
        legacy_amount: Decimal,
        new_amount: Decimal,
        tolerance: Decimal,
        explanation: str,
    ) -> ShadowRating:
        _tenant(tenant_id)
        require(
            all(value.is_finite() for value in (legacy_amount, new_amount, tolerance)),
            "SHADOW_DECIMAL_INVALID",
            "shadow values must be finite",
        )
        require(tolerance >= Decimal("0"), "TOLERANCE_INVALID", "tolerance must be non-negative")
        difference = new_amount - legacy_amount
        require(bool(explanation.strip()), "SHADOW_EXPLANATION_REQUIRED", "shadow difference requires explanation")
        return ShadowRating(
            tenant_id, source_id, legacy_amount, new_amount, difference, explanation, abs(difference) <= tolerance
        )

    def set_authority(self, *, tenant_id: str, authority: MigrationAuthority) -> MigrationAuthority:
        _tenant(tenant_id)
        with self._lock:
            current = self._authority.get(tenant_id)
            allowed = {
                None: {MigrationAuthority.LEGACY},
                MigrationAuthority.LEGACY: {MigrationAuthority.LEGACY, MigrationAuthority.SHADOW},
                MigrationAuthority.SHADOW: {MigrationAuthority.SHADOW, MigrationAuthority.NEW},
                MigrationAuthority.NEW: {MigrationAuthority.NEW, MigrationAuthority.READ_ONLY_LEGACY},
                MigrationAuthority.READ_ONLY_LEGACY: {MigrationAuthority.READ_ONLY_LEGACY},
            }
            require(
                authority in allowed[current],
                "AUTHORITY_TRANSITION_INVALID",
                "migration authority transition is invalid",
            )
            self._authority[tenant_id] = authority
            return authority

    def create_wave(self, *, wave_id: str, tenant_ids: tuple[str, ...], risk_tier: str) -> MigrationWave:
        require(risk_tier in {"LOW", "MEDIUM", "HIGH"}, "RISK_TIER_INVALID", "unsupported risk tier")
        require(
            bool(tenant_ids) and len(tenant_ids) == len(set(tenant_ids)),
            "WAVE_TENANTS_INVALID",
            "wave tenants must be unique",
        )
        for tenant_id in tenant_ids:
            _tenant(tenant_id)
        wave = MigrationWave(wave_id, tenant_ids, risk_tier, "PLANNED", ())
        with self._lock:
            previous = self._waves.get(wave_id)
            if previous is not None:
                require(previous == wave, "IDEMPOTENCY_CONFLICT", "wave id was reused")
                return previous
            self._waves[wave_id] = wave
            return wave

    def apply_rollback_signals(self, *, wave_id: str, signals: tuple[str, ...]) -> MigrationWave:
        require(set(signals) <= self.ROLLBACK_SIGNALS, "ROLLBACK_SIGNAL_INVALID", "unsupported rollback signal")
        with self._lock:
            try:
                wave = self._waves[wave_id]
            except KeyError as exc:
                raise DomainError("WAVE_NOT_FOUND", "migration wave was not found") from exc
            updated = replace(
                wave, state="ROLLED_BACK" if signals else wave.state, rollback_reasons=tuple(sorted(set(signals)))
            )
            self._waves[wave_id] = updated
            return updated

    @staticmethod
    def cutover_reconciliation(
        *,
        ledger_digest: str | None,
        invoice_digest: str | None,
        payment_digest: str | None,
        final_incremental_digest: str | None,
    ) -> dict[str, object]:
        values = (ledger_digest, invoice_digest, payment_digest, final_incremental_digest)
        complete = all(bool(value) for value in values)
        return {
            "complete": complete,
            "decision": "READY_FOR_HUMAN_DECISION" if complete else "BLOCKED",
            "external_execution": ExternalExecutionState.NOT_RUN,
            "certification": CertificationState.NOT_CERTIFIED,
            "digest": canonical_digest(values) if complete else None,
        }

    @staticmethod
    def customer_support_plan(
        *,
        notification_template: str,
        support_runbook: str,
        dispute_fast_track: str,
    ) -> dict[str, object]:
        require(
            all(value.strip() for value in (notification_template, support_runbook, dispute_fast_track)),
            "CUSTOMER_PLAN_INCOMPLETE",
            "customer migration plan is incomplete",
        )
        plan = {
            "notification_template": notification_template,
            "support_runbook": support_runbook,
            "dispute_fast_track": dispute_fast_track,
        }
        return {**plan, "digest": canonical_digest(plan)}

    def retain_legacy(
        self,
        *,
        tenant_id: str,
        read_only: bool,
        audit_available: bool,
        rollback_available: bool,
    ) -> dict[str, object]:
        _tenant(tenant_id)
        require(
            read_only and audit_available and rollback_available,
            "LEGACY_RETENTION_INCOMPLETE",
            "legacy system must remain read-only, auditable and rollback-capable",
        )
        record = {
            "tenant_id": tenant_id,
            "read_only": read_only,
            "audit_available": audit_available,
            "rollback_available": rollback_available,
            "decommission_allowed": False,
        }
        with self._lock:
            self._legacy_retention[tenant_id] = record
        return record


def _tenant(tenant_id: str) -> None:
    require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant id is required")
    require(tenant_id != "*", "WILDCARD_TENANT_FORBIDDEN", "wildcard tenant is forbidden")


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
