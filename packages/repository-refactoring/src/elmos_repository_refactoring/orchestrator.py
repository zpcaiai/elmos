"""Skill 00 — the resumable run state machine.

The orchestrator owns three things and delegates everything else:

1. **Plan synthesis** — turning a request plus a policy into a concrete step
   DAG, with approval gates placed by rule rather than by hand.
2. **Scheduling** — deciding which steps may start now, honouring dependencies,
   read/write conflicts, the shard limit, budgets and open approval gates.
3. **State** — an event-sourced run whose replay is deterministic, whose
   failures are classified into an action (retry / repair / approve / roll back
   / stop), and whose progress and ETA are reported as distributions.

Every transition is an event in :class:`~.journal.RunJournal`.  Reconstructing
a run from its events must produce byte-identical state; that property is what
makes "resume after a worker died" a supported operation rather than a hope.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .contracts import (
    AdapterLevel,
    ContractError,
    ExecutionMode,
    FailureClass,
    RiskClass,
    RollbackStrategy,
    isoformat_utc,
    sha256_payload,
    utc_now,
)
from .journal import Checkpoint, JournalEvent, Lease, RunJournal, idempotency_key
from .plan import (
    ApprovalGate,
    Assumption,
    Estimate,
    PlanStep,
    RefactorPlan,
    RiskSummary,
    StepBudget,
    StepRollback,
    StepScope,
    StepValidation,
    estimate_plan,
)
from .policy import RefactorPolicy
from .request import RefactorRequest


class RunState(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    ROLLING_BACK = "rolling-back"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}

    @property
    def accepts_scheduling(self) -> bool:
        return self in {RunState.PLANNED, RunState.RUNNING}


class StepState(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled-back"


#: Legal state transitions.  Anything not listed is a bug in a caller, and the
#: run refuses it rather than silently accepting an impossible history.
_RUN_TRANSITIONS: Mapping[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.PLANNED, RunState.CANCELLED, RunState.FAILED}),
    RunState.PLANNED: frozenset({RunState.RUNNING, RunState.PAUSED, RunState.CANCELLED, RunState.BLOCKED}),
    RunState.RUNNING: frozenset(
        {
            RunState.PAUSED,
            RunState.BLOCKED,
            RunState.ROLLING_BACK,
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.PAUSED: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.ROLLING_BACK}),
    RunState.BLOCKED: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.ROLLING_BACK, RunState.FAILED}),
    RunState.ROLLING_BACK: frozenset({RunState.FAILED, RunState.CANCELLED, RunState.PLANNED}),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

#: Signature fragments mapped to the action the orchestrator must take.  Order
#: matters: the first match wins, and the list is ordered most-specific first
#: so that "approval" never loses to a generic "retryable".
_FAILURE_RULES: tuple[tuple[str, FailureClass], ...] = (
    ("approval_required", FailureClass.APPROVAL_REQUIRED),
    ("policy_violation", FailureClass.APPROVAL_REQUIRED),
    ("scope_expansion", FailureClass.APPROVAL_REQUIRED),
    ("risk_escalation", FailureClass.APPROVAL_REQUIRED),
    ("unknown_semantics", FailureClass.APPROVAL_REQUIRED),
    ("side_effect_inconsistent", FailureClass.ROLLBACK_REQUIRED),
    ("workspace_diverged", FailureClass.ROLLBACK_REQUIRED),
    ("partial_external_write", FailureClass.ROLLBACK_REQUIRED),
    ("migration_partially_applied", FailureClass.ROLLBACK_REQUIRED),
    ("compile_error", FailureClass.REPAIRABLE),
    ("type_error", FailureClass.REPAIRABLE),
    ("test_failure", FailureClass.REPAIRABLE),
    ("import_error", FailureClass.REPAIRABLE),
    ("lint_error", FailureClass.REPAIRABLE),
    ("timeout", FailureClass.RETRYABLE),
    ("lease_expired", FailureClass.RETRYABLE),
    ("stale_fencing_token", FailureClass.RETRYABLE),
    ("resource_exhausted", FailureClass.RETRYABLE),
    ("transient", FailureClass.RETRYABLE),
    ("budget_exhausted", FailureClass.TERMINAL),
    ("adapter_capability_insufficient", FailureClass.TERMINAL),
    ("snapshot_changed", FailureClass.TERMINAL),
    ("contract_error", FailureClass.TERMINAL),
)


def classify_failure(signature: str) -> FailureClass:
    """Map a failure signature onto the orchestrator's response.

    Unknown signatures are ``TERMINAL``, not ``RETRYABLE``: retrying something
    nobody has characterised is how a partial side effect becomes three partial
    side effects.
    """

    lowered = signature.lower()
    for fragment, classification in _FAILURE_RULES:
        if fragment in lowered:
            return classification
    return FailureClass.TERMINAL


def should_retry(attempt: int, budget: StepBudget, classification: FailureClass) -> bool:
    if classification is not FailureClass.RETRYABLE:
        return False
    return attempt < budget.max_attempts


def backoff_seconds(attempt: int, *, base: int = 5, ceiling: int = 300) -> int:
    """Deterministic exponential backoff — no jitter, so replay is exact."""

    if attempt <= 0:
        return 0
    return int(min(ceiling, base * (2 ** (attempt - 1))))


# ---------------------------------------------------------------------------
# Plan synthesis
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _PhaseSpec:
    step_id: str
    name: str
    skill: str
    depends_on: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    gates: tuple[tuple[str, bool], ...]
    seconds: int
    mutating: bool = False
    required_level: AdapterLevel = AdapterLevel.L0
    when: str = ""


#: The canonical phase DAG.  ``when`` is an intent/constraint predicate applied
#: at synthesis time; a phase that does not apply is simply absent from the
#: plan rather than present-and-skipped, so the DAG stays honest.
_PHASES: tuple[_PhaseSpec, ...] = (
    _PhaseSpec(
        "discover", "Repository discovery", "repository-discovery", (),
        ("repository_snapshot",), ("repository_inventory", "sensitive_area_map"),
        (("scope-containment", True),), 120,
    ),
    _PhaseSpec(
        "buildgraph", "Build graph and environment", "build-graph-and-environment", ("discover",),
        ("repository_inventory",), ("build_graph", "toolchain_lock", "baseline_report"),
        (("build", True),), 600, required_level=AdapterLevel.L1,
    ),
    _PhaseSpec(
        "index", "Semantic index", "semantic-index", ("discover", "buildgraph"),
        ("repository_inventory", "build_graph"), ("semantic_index_snapshot", "coverage_metrics"),
        (("parse", True),), 900, required_level=AdapterLevel.L1,
    ),
    _PhaseSpec(
        "intent", "Compile refactor intent", "refactor-intent-compiler", ("index",),
        ("refactor_request", "semantic_index_snapshot"), ("compiled_intent", "acceptance_predicates"),
        (), 60,
    ),
    _PhaseSpec(
        "impact", "Change impact analysis", "change-impact-analysis", ("intent",),
        ("compiled_intent", "semantic_index_snapshot"), ("impact_report", "change_closure", "wave_plan"),
        (), 300, required_level=AdapterLevel.L2,
    ),
    _PhaseSpec(
        "api-baseline", "API compatibility baseline", "api-compatibility", ("index",),
        ("semantic_index_snapshot",), ("api_diff",),
        (("api-compatibility", True),), 180, required_level=AdapterLevel.L2,
        when="public-api",
    ),
    _PhaseSpec(
        "recipes", "Recipe synthesis and lock", "recipe-synthesis", ("impact",),
        ("compiled_intent", "change_closure"), ("recipe_set", "recipe_lock", "dry_run_patch"),
        (("idempotence", True),), 300, required_level=AdapterLevel.L2,
    ),
    _PhaseSpec(
        "transform", "Deterministic transform", "deterministic-transform-executor", ("recipes",),
        ("recipe_lock", "repository_snapshot"), ("patch_set", "source_map"),
        (("scope-containment", True), ("round-trip", True)), 900,
        mutating=True, required_level=AdapterLevel.L2,
    ),
    _PhaseSpec(
        "contracts", "Cross-language contract migration", "cross-language-contract-refactor", ("transform",),
        ("patch_set", "api_diff"), ("contract_migration_plan", "contract_diff"),
        (("api-compatibility", True),), 600,
        mutating=True, required_level=AdapterLevel.L3, when="contract",
    ),
    _PhaseSpec(
        "schema", "Data schema expand-contract", "data-schema-refactor", ("transform",),
        ("impact_report",), ("schema_migration_plan", "migration_files", "rollback_plan"),
        (("schema-compatibility", True), ("rollback-proof", True)), 900,
        mutating=True, required_level=AdapterLevel.L3, when="database",
    ),
    _PhaseSpec(
        "distributed", "Distributed system refactor", "distributed-system-refactor", ("contracts", "schema"),
        ("contract_migration_plan", "schema_migration_plan"), ("service_boundary_plan", "resilience_tests"),
        (("full-tests", True),), 900,
        mutating=True, required_level=AdapterLevel.L3, when="distributed",
    ),
    _PhaseSpec(
        "ui", "UI and client refactor", "ui-and-client-refactor", ("transform",),
        ("patch_set",), ("client_patch_set", "platform_compatibility_matrix"),
        (("changed-target-tests", True),), 600,
        mutating=True, required_level=AdapterLevel.L2, when="ui",
    ),
    _PhaseSpec(
        "verify", "Layered verification", "test-and-verification", ("transform",),
        ("patch_set", "baseline_report"), ("validation_report", "gate_decisions", "sarif"),
        (("typecheck", True), ("build", True), ("changed-target-tests", True), ("anti-cheat", True)), 1800,
        required_level=AdapterLevel.L2,
    ),
    _PhaseSpec(
        "repair", "Bounded auto-repair", "bounded-auto-repair", ("verify",),
        ("validation_report", "patch_set"), ("updated_patch_set", "repair_attempt_records"),
        (("anti-cheat", True),), 600,
        mutating=True, required_level=AdapterLevel.L2,
    ),
    _PhaseSpec(
        "performance", "Performance preservation", "performance-preservation", ("verify",),
        ("baseline_report", "patch_set"), ("performance_diff", "guardrail_decision"),
        (("performance", True),), 1200, required_level=AdapterLevel.L2, when="performance",
    ),
    _PhaseSpec(
        "security", "Security preservation", "security-preservation", ("verify",),
        ("patch_set",), ("security_diff", "sarif", "sbom_delta"),
        (("security-scan", True),), 600, required_level=AdapterLevel.L2, when="security",
    ),
    _PhaseSpec(
        "approval", "Human approval gate", "human-approval-gate", ("verify",),
        ("validation_report", "patch_set"), ("approval_decision",),
        (), 0, when="approval",
    ),
    _PhaseSpec(
        "rollout", "Canary rollout / changeset", "canary-rollout", ("verify",),
        ("patch_set", "validation_report"), ("changesets", "rollout_plan", "canary_report"),
        (("rollback-proof", True),), 900,
        mutating=True, required_level=AdapterLevel.L3, when="rollout",
    ),
    _PhaseSpec(
        "evidence", "Evidence and audit", "evidence-and-audit", ("verify",),
        ("validation_report",), ("evidence_bundle", "signed_manifest", "billing_breakdown"),
        (("evidence-completeness", True),), 120,
    ),
)


def _phase_applies(spec: _PhaseSpec, request: RefactorRequest, policy: RefactorPolicy) -> bool:
    condition = spec.when
    if not condition:
        return True
    intent = request.intent.type
    constraints = request.constraints
    if condition == "public-api":
        return constraints.public_api_compatibility != "strict" or intent in {"api-migration", "framework-upgrade"}
    if condition == "contract":
        return intent in {"api-migration", "distributed-system-refactor", "architecture-refactor"} or bool(
            request.repositories[1:]
        )
    if condition == "database":
        return constraints.database_strategy != "none" or intent == "data-schema-refactor"
    if condition == "distributed":
        return intent == "distributed-system-refactor"
    if condition == "ui":
        return intent == "ui-client-refactor"
    if condition == "performance":
        return intent == "performance-refactor" or bool(constraints.performance_guardrails)
    if condition == "security":
        return intent == "security-refactor" or constraints.security_policy_ref is not None
    if condition == "approval":
        return request.execution.mode in {
            ExecutionMode.SUPERVISED,
            ExecutionMode.FLEET_WAVE,
        } or request.risk_floor.rank >= RiskClass.R3.rank
    if condition == "rollout":
        return request.execution.mode is not ExecutionMode.ANALYZE_ONLY and request.execution.create_pull_request
    raise ContractError("unknown_phase_condition", f"unknown phase condition '{condition}'")


def _step_risk(spec: _PhaseSpec, request: RefactorRequest) -> RiskClass:
    if not spec.mutating:
        return RiskClass.R0 if spec.step_id in {"discover", "index", "intent", "impact"} else RiskClass.R1
    floor = request.risk_floor
    if spec.step_id in {"schema", "distributed", "rollout"}:
        return RiskClass.max_of([floor, RiskClass.R4])
    if spec.step_id in {"contracts"}:
        return RiskClass.max_of([floor, RiskClass.R3])
    return floor


def synthesize_plan(
    request: RefactorRequest,
    policy: RefactorPolicy,
    *,
    run_id: str,
    snapshot_digests: Mapping[str, str],
    plan_version: int = 1,
    assumptions: Sequence[Assumption] = (),
    unknown_risk_weight: Decimal = Decimal("0"),
    changed_files_estimate: int = 0,
) -> RefactorPlan:
    """Turn a request plus a policy into an executable step DAG."""

    analyze_only = request.execution.mode is ExecutionMode.ANALYZE_ONLY
    selected = [spec for spec in _PHASES if _phase_applies(spec, request, policy)]
    if analyze_only:
        selected = [spec for spec in selected if not spec.mutating and spec.step_id != "approval"]
    chosen = {spec.step_id for spec in selected}

    steps: list[PlanStep] = []
    for spec in selected:
        dependencies = tuple(item for item in spec.depends_on if item in chosen)
        risk = _step_risk(spec, request)
        write_set: tuple[str, ...] = ()
        read_set: tuple[str, ...] = tuple(
            sorted({*request.constraints.allowed_paths} or {"**"})
        )
        if spec.mutating:
            write_set = read_set
        steps.append(
            PlanStep(
                step_id=spec.step_id,
                name=spec.name,
                skill=spec.skill,
                depends_on=dependencies,
                risk_class=risk,
                inputs=spec.inputs,
                outputs=spec.outputs,
                validation=tuple(
                    StepValidation(gate=gate, blocking=_gate_blocking(policy, gate, blocking))
                    for gate, blocking in spec.gates
                ),
                adapter_requirements=(
                    {"*": spec.required_level} if spec.required_level is not AdapterLevel.L0 else {}
                ),
                scope=StepScope(
                    repositories=tuple(item.repository_id for item in request.repositories),
                    paths=read_set,
                ),
                read_set=read_set,
                write_set=write_set,
                rollback=StepRollback(
                    strategy=RollbackStrategy.COMPENSATION
                    if spec.step_id in {"schema", "rollout", "distributed"}
                    else (RollbackStrategy.REVERSE_PATCH if spec.mutating else RollbackStrategy.FORWARD_ONLY)
                ),
                budgets=StepBudget(
                    max_attempts=request.execution.repair_budget.max_attempts if spec.step_id == "repair" else 3,
                    timeout_seconds=max(spec.seconds * 2, 60),
                ),
                estimated_seconds=max(spec.seconds, 1),
            )
        )

    gates = _derive_approval_gates(steps, request, policy)
    reasons = _risk_reasons(request, steps, unknown_risk_weight)
    overall = RiskClass.max_of([step.risk_class for step in steps] or [RiskClass.R0])
    estimate = estimate_plan(
        steps,
        max_parallel_shards=request.execution.max_parallel_shards,
        changed_files=changed_files_estimate,
    )
    return RefactorPlan(
        plan_id=sha256_payload({"run": run_id, "request": request.digest, "version": plan_version})[:24],
        run_id=run_id,
        version=plan_version,
        snapshot_digests=dict(snapshot_digests),
        steps=tuple(steps),
        risk_summary=RiskSummary(
            overall_class=overall,
            reasons=reasons,
            unknown_risk_weight=unknown_risk_weight,
        ),
        assumptions=tuple(assumptions),
        estimated=estimate,
        approval_gates=gates,
    )


def _gate_blocking(policy: RefactorPolicy, gate: str, default: bool) -> bool:
    rule = policy.gate_rule(gate)
    return default if rule is None else rule.blocking


def _derive_approval_gates(
    steps: Sequence[PlanStep],
    request: RefactorRequest,
    policy: RefactorPolicy,
) -> tuple[ApprovalGate, ...]:
    """Place an approval gate before every step the policy requires one for.

    A high-risk step with no gate is not a possible output of this function;
    that is the point of deriving gates instead of trusting a caller to add
    them.
    """

    gates: list[ApprovalGate] = []
    for step in steps:
        context = {
            "risk": {"class": step.risk_class.value},
            "step": {"id": step.step_id, "skill": step.skill, "mutating": step.mutating},
            "impact": {
                "database_touched": step.step_id == "schema",
                "security_touched": step.step_id == "security" or request.intent.type == "security-refactor",
                "public_api_touched": step.step_id in {"contracts", "api-baseline"},
                "public_api_breaking": request.constraints.public_api_compatibility
                in {"versioned-break", "approved-break"},
            },
            "scope": {"expanded": False},
            "execution": {"mode": request.execution.mode.value, "mutates": step.mutating},
        }
        required = policy.required_approval_roles(context)
        if not required:
            continue
        roles = tuple(sorted({role for group in required for role in group}))
        gates.append(
            ApprovalGate(
                gate_id=f"gate-{step.step_id}",
                before_step_id=step.step_id,
                roles=roles,
                reason=f"policy '{policy.name}' requires approval for a {step.risk_class.value} step",
            )
        )
    return tuple(gates)


def _risk_reasons(
    request: RefactorRequest,
    steps: Sequence[PlanStep],
    unknown_risk_weight: Decimal,
) -> tuple[str, ...]:
    reasons: list[str] = [f"intent '{request.intent.type}' has risk floor {request.intent.risk_floor.value}"]
    if len(request.repositories) > 1:
        reasons.append(f"{len(request.repositories)} repositories are in scope")
    if request.constraints.database_strategy != "none":
        reasons.append(f"database strategy is '{request.constraints.database_strategy}'")
    if request.constraints.public_api_compatibility != "strict":
        reasons.append(f"public API compatibility is '{request.constraints.public_api_compatibility}'")
    mutating = [step.step_id for step in steps if step.mutating]
    if mutating:
        reasons.append("mutating steps: " + ", ".join(mutating))
    if unknown_risk_weight > Decimal("0.05"):
        reasons.append(f"index unknown-risk weight is {unknown_risk_weight}")
    return tuple(reasons)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StepStatus:
    step_id: str
    state: StepState = StepState.PENDING
    attempts: int = 0
    failure_signature: str = ""
    failure_class: FailureClass | None = None
    output_digest: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stepId": self.step_id,
            "state": self.state.value,
            "attempts": self.attempts,
        }
        if self.failure_signature:
            payload["failureSignature"] = self.failure_signature
        if self.failure_class is not None:
            payload["failureClass"] = self.failure_class.value
        if self.output_digest:
            payload["outputDigest"] = self.output_digest
        if self.started_at is not None:
            payload["startedAt"] = isoformat_utc(self.started_at)
        if self.finished_at is not None:
            payload["finishedAt"] = isoformat_utc(self.finished_at)
        return payload


@dataclass(frozen=True, slots=True)
class ScheduleDecision:
    runnable: tuple[str, ...]
    waiting_on_dependencies: tuple[str, ...]
    waiting_on_approval: tuple[str, ...]
    blocked_by_conflict: tuple[str, ...]
    shard_limit: int
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "runnable": list(self.runnable),
            "waitingOnDependencies": list(self.waiting_on_dependencies),
            "waitingOnApproval": list(self.waiting_on_approval),
            "blockedByConflict": list(self.blocked_by_conflict),
            "shardLimit": self.shard_limit,
            "reason": self.reason,
        }


class RefactorRun:
    """One resumable refactor run.

    The instance is a projection of its journal.  Every mutating method appends
    an event first and updates the projection second, so a crash between the
    two loses nothing: the next replay derives the same state from the event.
    """

    __slots__ = ("_request", "_policy", "_journal", "_plan", "_state", "_steps", "_approvals", "_spent")

    def __init__(
        self,
        request: RefactorRequest,
        policy: RefactorPolicy,
        *,
        run_id: str,
        journal: RunJournal | None = None,
        now: datetime | None = None,
    ) -> None:
        self._request = request
        self._policy = policy
        self._journal = journal or RunJournal(run_id)
        self._plan: RefactorPlan | None = None
        self._state = RunState.CREATED
        self._steps: dict[str, StepStatus] = {}
        self._approvals: dict[str, str] = {}
        self._spent = Decimal("0")
        if not self._journal.events:
            self._journal.append(
                "run.created",
                {
                    "requestDigest": request.digest,
                    "policyDigest": policy.digest,
                    "mode": request.execution.mode.value,
                    "riskFloor": request.risk_floor.value,
                },
                now=now,
            )

    # -- accessors -------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._journal.run_id

    @property
    def state(self) -> RunState:
        return self._state

    @property
    def journal(self) -> RunJournal:
        return self._journal

    @property
    def plan(self) -> RefactorPlan:
        if self._plan is None:
            raise ContractError("plan_not_frozen", "the run has no frozen plan yet")
        return self._plan

    @property
    def request(self) -> RefactorRequest:
        return self._request

    @property
    def policy(self) -> RefactorPolicy:
        return self._policy

    def status_of(self, step_id: str) -> StepStatus:
        return self._steps.get(step_id, StepStatus(step_id=step_id))

    @property
    def completed_steps(self) -> tuple[str, ...]:
        return tuple(
            sorted(step_id for step_id, status in self._steps.items() if status.state is StepState.SUCCEEDED)
        )

    # -- state machine ---------------------------------------------------

    def _transition(self, target: RunState, *, lease: Lease | None = None, now: datetime | None = None) -> None:
        allowed = _RUN_TRANSITIONS[self._state]
        if target not in allowed:
            raise ContractError(
                "illegal_transition",
                f"run cannot move from {self._state.value} to {target.value}",
                {"from": self._state.value, "to": target.value, "allowed": sorted(item.value for item in allowed)},
            )
        self._state = target
        event_map = {
            RunState.PAUSED: "run.paused",
            RunState.RUNNING: "run.resumed",
            RunState.CANCELLED: "run.cancelled",
            RunState.SUCCEEDED: "run.completed",
            RunState.FAILED: "run.failed",
            RunState.ROLLING_BACK: "rollback.started",
        }
        event = event_map.get(target)
        if event:
            self._journal.append(event, {"state": target.value}, lease=lease, now=now)

    def freeze_plan(self, plan: RefactorPlan, *, lease: Lease | None = None, now: datetime | None = None) -> None:
        if plan.run_id != self.run_id:
            raise ContractError("plan_run_mismatch", "plan.runId does not match this run")
        if self._plan is not None and plan.digest != self._plan.digest:
            raise ContractError("plan_already_frozen", "a different plan is already frozen for this run")
        self._plan = plan
        self._steps = {step.step_id: StepStatus(step_id=step.step_id) for step in plan.steps}
        self._journal.append(
            "run.plan.frozen",
            {"planId": plan.plan_id, "planDigest": plan.digest},
            lease=lease,
            now=now,
        )
        self._transition(RunState.PLANNED, lease=lease, now=now)

    def pause(self, *, lease: Lease | None = None, now: datetime | None = None) -> None:
        self._transition(RunState.PAUSED, lease=lease, now=now)

    def resume(self, *, lease: Lease | None = None, now: datetime | None = None) -> None:
        self._transition(RunState.RUNNING, lease=lease, now=now)

    def cancel(self, reason: str = "", *, lease: Lease | None = None, now: datetime | None = None) -> None:
        self._journal.append("run.cancelled", {"reason": reason}, lease=lease, now=now)
        self._state = RunState.CANCELLED

    # -- approvals -------------------------------------------------------

    def record_approval(
        self,
        gate_id: str,
        approval_digest: str,
        *,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> None:
        gate = next((item for item in self.plan.approval_gates if item.gate_id == gate_id), None)
        if gate is None:
            raise ContractError("unknown_gate", f"plan has no approval gate '{gate_id}'")
        self._approvals[gate_id] = approval_digest
        self._journal.append(
            "approval.recorded",
            {"gateId": gate_id, "approvalDigest": approval_digest},
            step_id=gate.before_step_id,
            lease=lease,
            now=now,
        )

    def gate_satisfied(self, gate: ApprovalGate) -> bool:
        return gate.gate_id in self._approvals

    # -- scheduling ------------------------------------------------------

    def schedule(self, *, running: Sequence[str] = ()) -> ScheduleDecision:
        """Which steps may start right now."""

        if not self._state.accepts_scheduling:
            return ScheduleDecision((), (), (), (), 0, reason=f"run state '{self._state.value}' does not schedule")
        plan = self.plan
        completed = set(self.completed_steps)
        active = set(running)
        conflict_map: dict[str, set[str]] = {step.step_id: set() for step in plan.steps}
        for left, right, _ in plan.conflicts():
            conflict_map[left].add(right)
            conflict_map[right].add(left)

        runnable: list[str] = []
        waiting_dependencies: list[str] = []
        waiting_approval: list[str] = []
        blocked_conflict: list[str] = []
        limit = self._request.execution.max_parallel_shards

        for step in plan.steps:
            status = self.status_of(step.step_id)
            if status.state in {StepState.SUCCEEDED, StepState.SKIPPED} or step.step_id in active:
                continue
            if status.state is StepState.BLOCKED:
                waiting_approval.append(step.step_id)
                continue
            if not set(step.depends_on) <= completed:
                waiting_dependencies.append(step.step_id)
                continue
            gates = plan.gates_before(step.step_id)
            if gates and not all(self.gate_satisfied(gate) for gate in gates):
                waiting_approval.append(step.step_id)
                continue
            if conflict_map[step.step_id] & (active | set(runnable)):
                blocked_conflict.append(step.step_id)
                continue
            if len(runnable) + len(active) >= limit:
                blocked_conflict.append(step.step_id)
                continue
            runnable.append(step.step_id)

        return ScheduleDecision(
            runnable=tuple(runnable),
            waiting_on_dependencies=tuple(waiting_dependencies),
            waiting_on_approval=tuple(waiting_approval),
            blocked_by_conflict=tuple(blocked_conflict),
            shard_limit=limit,
        )

    # -- step lifecycle --------------------------------------------------

    def start_step(self, step_id: str, *, lease: Lease | None = None, now: datetime | None = None) -> StepStatus:
        step = self.plan.step(step_id)
        status = self.status_of(step_id)
        if status.state is StepState.SUCCEEDED:
            return status
        if self._state is RunState.PLANNED:
            self._transition(RunState.RUNNING, lease=lease, now=now)
        moment = now or utc_now()
        updated = replace(
            status,
            state=StepState.RUNNING,
            attempts=status.attempts + 1,
            started_at=status.started_at or moment,
        )
        self._steps[step_id] = updated
        self._journal.append(
            "step.started",
            {"attempt": updated.attempts, "skill": step.skill, "riskClass": step.risk_class.value},
            step_id=step_id,
            idempotency_key=idempotency_key(self.run_id, step_id, updated.attempts),
            lease=lease,
            now=moment,
        )
        return updated

    def complete_step(
        self,
        step_id: str,
        output: Mapping[str, Any],
        *,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> StepStatus:
        status = self.status_of(step_id)
        moment = now or utc_now()
        digest = sha256_payload(dict(output))
        updated = replace(status, state=StepState.SUCCEEDED, output_digest=digest, finished_at=moment)
        self._steps[step_id] = updated
        self._journal.append(
            "step.succeeded",
            {"outputDigest": digest},
            step_id=step_id,
            lease=lease,
            now=moment,
        )
        if set(self.completed_steps) == set(self.plan.step_ids):
            self._transition(RunState.SUCCEEDED, lease=lease, now=moment)
        return updated

    def fail_step(
        self,
        step_id: str,
        signature: str,
        *,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> tuple[StepStatus, FailureClass]:
        step = self.plan.step(step_id)
        status = self.status_of(step_id)
        classification = classify_failure(signature)
        moment = now or utc_now()
        retryable = should_retry(status.attempts, step.budgets, classification)
        state = StepState.FAILED
        if classification is FailureClass.APPROVAL_REQUIRED:
            state = StepState.BLOCKED
        updated = replace(
            status,
            state=state,
            failure_signature=signature,
            failure_class=classification,
            finished_at=moment,
        )
        self._steps[step_id] = updated
        self._journal.append(
            "step.blocked" if state is StepState.BLOCKED else "step.failed",
            {
                "signature": signature,
                "failureClass": classification.value,
                "attempt": status.attempts,
                "retryScheduled": retryable,
                "backoffSeconds": backoff_seconds(status.attempts) if retryable else 0,
            },
            step_id=step_id,
            lease=lease,
            now=moment,
        )
        if classification is FailureClass.ROLLBACK_REQUIRED and self._state is RunState.RUNNING:
            self._transition(RunState.ROLLING_BACK, lease=lease, now=moment)
        elif classification is FailureClass.TERMINAL and not retryable and self._state is RunState.RUNNING:
            self._transition(RunState.FAILED, lease=lease, now=moment)
        elif state is StepState.BLOCKED and self._state is RunState.RUNNING:
            self._transition(RunState.BLOCKED, lease=lease, now=moment)
        return updated, classification

    def checkpoint(
        self,
        step_id: str,
        *,
        workspace_tree_digest: str,
        artifact_manifest_digest: str,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> Checkpoint:
        return self._journal.write_checkpoint(
            step_id=step_id,
            workspace_tree_digest=workspace_tree_digest,
            artifact_manifest_digest=artifact_manifest_digest,
            state_version=len(self._steps) + self._journal.sequence,
            lease=lease,
            now=now,
        )

    # -- reporting -------------------------------------------------------

    def progress(self) -> dict[str, Any]:
        plan = self.plan
        done = len(self.completed_steps)
        total = len(plan.steps)
        remaining_seconds = sum(
            step.estimated_seconds
            for step in plan.steps
            if self.status_of(step.step_id).state
            not in {StepState.SUCCEEDED, StepState.SKIPPED}
        )
        estimate = plan.estimated or Estimate(0, 0, 0)
        return {
            "runId": self.run_id,
            "state": self._state.value,
            "planDigest": plan.digest,
            "stepsCompleted": done,
            "stepsTotal": total,
            "completionRatio": str(
                (Decimal(done) / Decimal(total)).quantize(Decimal("0.0001")) if total else Decimal("0")
            ),
            "remainingSecondsEstimate": remaining_seconds,
            "etaSeconds": {
                "p50": estimate.wall_clock_p50,
                "p80": estimate.wall_clock_p80,
                "p95": estimate.wall_clock_p95,
            },
            "steps": [self.status_of(step.step_id).to_payload() for step in plan.steps],
            "openApprovalGates": [
                gate.to_payload() for gate in plan.approval_gates if not self.gate_satisfied(gate)
            ],
            "journalHead": self._journal.head_digest,
            "sideEffectCursor": self._journal.side_effect_cursor,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "state": self._state.value,
            "requestDigest": self._request.digest,
            "policyDigest": self._policy.digest,
            "planDigest": self._plan.digest if self._plan is not None else None,
            "steps": {step_id: status.to_payload() for step_id, status in sorted(self._steps.items())},
            "approvals": dict(sorted(self._approvals.items())),
            "journalHead": self._journal.head_digest,
        }

    # -- replay ----------------------------------------------------------

    @classmethod
    def replay(
        cls,
        request: RefactorRequest,
        policy: RefactorPolicy,
        plan: RefactorPlan,
        events: Sequence[Mapping[str, Any]],
    ) -> RefactorRun:
        """Rebuild a run from its event log.

        The projection below must stay exhaustive: an event type that reaches
        it without a handler raises, because silently ignoring history is how a
        resumed run diverges from the run it claims to continue.
        """

        journal = RunJournal(plan.run_id)
        journal.replay(events)
        run = cls.__new__(cls)
        run._request = request
        run._policy = policy
        run._journal = journal
        run._plan = plan
        run._state = RunState.CREATED
        run._steps = {step.step_id: StepStatus(step_id=step.step_id) for step in plan.steps}
        run._approvals = {}
        run._spent = Decimal("0")
        for event in journal.events:
            run._apply(event)
        return run

    def _apply(self, event: JournalEvent) -> None:
        kind = event.event_type
        step_id = event.step_id
        if kind == "run.created":
            self._state = RunState.CREATED
        elif kind == "run.plan.frozen":
            self._state = RunState.PLANNED
        elif kind == "run.paused":
            self._state = RunState.PAUSED
        elif kind == "run.resumed":
            self._state = RunState.RUNNING
        elif kind == "run.cancelled":
            self._state = RunState.CANCELLED
        elif kind == "run.completed":
            self._state = RunState.SUCCEEDED
        elif kind == "run.failed":
            self._state = RunState.FAILED
        elif kind == "rollback.started":
            self._state = RunState.ROLLING_BACK
        elif kind == "rollback.completed":
            self._state = RunState.PLANNED
        elif kind in {"step.scheduled", "step.started"} and step_id:
            status = self.status_of(step_id)
            self._steps[step_id] = replace(
                status,
                state=StepState.RUNNING,
                attempts=int(event.payload.get("attempt", status.attempts + 1)),
                started_at=status.started_at or event.occurred_at,
            )
            if self._state is RunState.PLANNED:
                self._state = RunState.RUNNING
        elif kind == "step.succeeded" and step_id:
            self._steps[step_id] = replace(
                self.status_of(step_id),
                state=StepState.SUCCEEDED,
                output_digest=str(event.payload.get("outputDigest", "")),
                finished_at=event.occurred_at,
            )
            if self._plan is not None and set(self.completed_steps) == set(self._plan.step_ids):
                self._state = RunState.SUCCEEDED
        elif kind in {"step.failed", "step.blocked"} and step_id:
            signature = str(event.payload.get("signature", ""))
            self._steps[step_id] = replace(
                self.status_of(step_id),
                state=StepState.BLOCKED if kind == "step.blocked" else StepState.FAILED,
                failure_signature=signature,
                failure_class=classify_failure(signature) if signature else None,
                finished_at=event.occurred_at,
            )
        elif kind == "step.skipped" and step_id:
            self._steps[step_id] = replace(self.status_of(step_id), state=StepState.SKIPPED)
        elif kind == "approval.recorded":
            gate_id = str(event.payload.get("gateId", ""))
            if gate_id:
                self._approvals[gate_id] = str(event.payload.get("approvalDigest", ""))
        elif kind in {
            "checkpoint.written",
            "approval.requested",
            "sideeffect.recorded",
            "sideeffect.compensated",
            "shard.started",
            "shard.succeeded",
            "shard.failed",
            "budget.exhausted",
            "scope.expanded",
        }:
            return
        else:  # pragma: no cover - guarded by EVENT_TYPES at append time
            raise ContractError("unhandled_event", f"replay has no handler for event '{kind}'")


__all__ = [
    "RefactorRun",
    "RunState",
    "ScheduleDecision",
    "StepState",
    "StepStatus",
    "backoff_seconds",
    "classify_failure",
    "should_retry",
    "synthesize_plan",
]
