"""``RefactorPlan`` — the frozen DAG a run executes, and the maths over it.

A plan is more than a list of steps.  The orchestrator relies on this module
for four things that decide whether a long refactor is safe:

* **Acyclic dependency order**, with cycles reported as the actual cycle rather
  than "something went wrong".
* **Read/write set conflict analysis**, which is what makes parallel shard
  execution deterministic: two steps may only run concurrently when their write
  sets are disjoint and neither reads what the other writes.
* **Critical path and percentile ETA**, so a caller is told p50/p80/p95 rather
  than a single number that will be wrong.
* **Approval gate placement**, derived from step risk and policy rather than
  hand-written, so a high-risk step cannot exist without a gate in front of it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .catalog import SKILL_NAMES, spec_for
from .contracts import (
    AdapterLevel,
    ContractError,
    RiskClass,
    RollbackStrategy,
    decimal_value,
    integer_value,
    optional_string,
    reject_unknown_fields,
    require_bool,
    require_digest,
    require_enum,
    require_identifier,
    require_mapping,
    require_mapping_sequence,
    require_string,
    require_string_sequence,
    sha256_payload,
)

PLAN_KIND = "RefactorPlan"
API_VERSION = "elmos.dev/v1"

ASSUMPTION_STATES = ("accepted", "rejected", "requires-approval", "unverified")


@dataclass(frozen=True, slots=True)
class StepScope:
    repositories: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    build_targets: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.repositories:
            payload["repositories"] = list(self.repositories)
        if self.paths:
            payload["paths"] = list(self.paths)
        if self.symbols:
            payload["symbols"] = list(self.symbols)
        if self.build_targets:
            payload["buildTargets"] = list(self.build_targets)
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> StepScope:
        if value is None:
            return cls()
        mapping = require_mapping(value, "step.scope")
        reject_unknown_fields(mapping, {"repositories", "paths", "symbols", "buildTargets"}, "step.scope")
        return cls(
            repositories=require_string_sequence(mapping.get("repositories", ()), "step.scope.repositories"),
            paths=require_string_sequence(mapping.get("paths", ()), "step.scope.paths"),
            symbols=require_string_sequence(mapping.get("symbols", ()), "step.scope.symbols"),
            build_targets=require_string_sequence(mapping.get("buildTargets", ()), "step.scope.buildTargets"),
        )


@dataclass(frozen=True, slots=True)
class StepValidation:
    gate: str
    blocking: bool
    profile: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"gate": self.gate, "blocking": self.blocking}
        if self.profile:
            payload["profile"] = self.profile
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> StepValidation:
        reject_unknown_fields(value, {"gate", "blocking", "profile"}, "step.validation[]")
        return cls(
            gate=require_string(value.get("gate"), "step.validation[].gate", max_length=128),
            blocking=require_bool(value.get("blocking"), "step.validation[].blocking"),
            profile=optional_string(value.get("profile"), "step.validation[].profile"),
        )


@dataclass(frozen=True, slots=True)
class StepRollback:
    strategy: RollbackStrategy = RollbackStrategy.REVERSE_PATCH
    handler: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"strategy": self.strategy.value}
        if self.handler:
            payload["handler"] = self.handler
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> StepRollback:
        if value is None:
            return cls()
        mapping = require_mapping(value, "step.rollback")
        reject_unknown_fields(mapping, {"strategy", "handler"}, "step.rollback")
        return cls(
            strategy=require_enum(
                mapping.get("strategy", "reverse-patch"), RollbackStrategy, "step.rollback.strategy"
            ),
            handler=optional_string(mapping.get("handler"), "step.rollback.handler"),
        )


@dataclass(frozen=True, slots=True)
class StepBudget:
    max_attempts: int = 3
    max_cost_usd: Decimal = Decimal("0")
    timeout_seconds: int = 3600

    def to_payload(self) -> dict[str, Any]:
        return {
            "maxAttempts": self.max_attempts,
            "maxCostUsd": str(self.max_cost_usd),
            "timeoutSeconds": self.timeout_seconds,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> StepBudget:
        if value is None:
            return cls()
        mapping = require_mapping(value, "step.budgets")
        reject_unknown_fields(mapping, {"maxAttempts", "maxCostUsd", "timeoutSeconds"}, "step.budgets")
        return cls(
            max_attempts=integer_value(
                mapping.get("maxAttempts", 3), "step.budgets.maxAttempts", minimum=1, maximum=50
            ),
            max_cost_usd=decimal_value(mapping.get("maxCostUsd", 0), "step.budgets.maxCostUsd", minimum=Decimal("0")),
            timeout_seconds=integer_value(
                mapping.get("timeoutSeconds", 3600), "step.budgets.timeoutSeconds", minimum=1, maximum=86400
            ),
        )


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    name: str
    skill: str
    depends_on: tuple[str, ...]
    risk_class: RiskClass
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    validation: tuple[StepValidation, ...]
    recipe_refs: tuple[str, ...] = ()
    adapter_requirements: Mapping[str, AdapterLevel] = field(default_factory=dict)
    scope: StepScope = field(default_factory=StepScope)
    read_set: tuple[str, ...] = ()
    write_set: tuple[str, ...] = ()
    rollback: StepRollback = field(default_factory=StepRollback)
    budgets: StepBudget = field(default_factory=StepBudget)
    estimated_seconds: int = 60

    @property
    def mutating(self) -> bool:
        return bool(self.write_set) or spec_for(self.skill).mutating

    @property
    def blocking_gates(self) -> tuple[str, ...]:
        return tuple(item.gate for item in self.validation if item.blocking)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stepId": self.step_id,
            "name": self.name,
            "skill": self.skill,
            "dependsOn": list(self.depends_on),
            "riskClass": self.risk_class.value,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "validation": [item.to_payload() for item in self.validation],
            "rollback": self.rollback.to_payload(),
            "budgets": self.budgets.to_payload(),
        }
        if self.recipe_refs:
            payload["recipeRefs"] = list(self.recipe_refs)
        if self.adapter_requirements:
            payload["adapterRequirements"] = {
                key: level.value for key, level in sorted(self.adapter_requirements.items())
            }
        scope = self.scope.to_payload()
        if scope:
            payload["scope"] = scope
        if self.read_set:
            payload["readSet"] = list(self.read_set)
        if self.write_set:
            payload["writeSet"] = list(self.write_set)
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> PlanStep:
        reject_unknown_fields(
            value,
            {
                "stepId",
                "name",
                "skill",
                "dependsOn",
                "riskClass",
                "recipeRefs",
                "adapterRequirements",
                "scope",
                "inputs",
                "outputs",
                "readSet",
                "writeSet",
                "validation",
                "rollback",
                "budgets",
                "estimatedSeconds",
            },
            "plan.steps[]",
        )
        skill = require_string(value.get("skill"), "plan.steps[].skill", max_length=128)
        if skill not in SKILL_NAMES:
            raise ContractError("unknown_skill", f"plan step references unknown skill '{skill}'")
        requirements_raw = require_mapping(
            value.get("adapterRequirements", {}), "plan.steps[].adapterRequirements"
        )
        return cls(
            step_id=require_identifier(value.get("stepId"), "plan.steps[].stepId"),
            name=require_string(value.get("name"), "plan.steps[].name", max_length=256),
            skill=skill,
            depends_on=require_string_sequence(
                value.get("dependsOn", ()), "plan.steps[].dependsOn", unique=True
            ),
            risk_class=require_enum(value.get("riskClass"), RiskClass, "plan.steps[].riskClass"),
            inputs=require_string_sequence(value.get("inputs", ()), "plan.steps[].inputs"),
            outputs=require_string_sequence(value.get("outputs", ()), "plan.steps[].outputs"),
            validation=tuple(
                StepValidation.from_payload(item)
                for item in require_mapping_sequence(value.get("validation", ()), "plan.steps[].validation")
            ),
            recipe_refs=require_string_sequence(value.get("recipeRefs", ()), "plan.steps[].recipeRefs"),
            adapter_requirements={
                require_string(key, "plan.steps[].adapterRequirements key"): require_enum(
                    item, AdapterLevel, "plan.steps[].adapterRequirements value"
                )
                for key, item in requirements_raw.items()
            },
            scope=StepScope.from_payload(value.get("scope")),
            read_set=require_string_sequence(value.get("readSet", ()), "plan.steps[].readSet"),
            write_set=require_string_sequence(value.get("writeSet", ()), "plan.steps[].writeSet"),
            rollback=StepRollback.from_payload(value.get("rollback")),
            budgets=StepBudget.from_payload(value.get("budgets")),
            estimated_seconds=integer_value(
                value.get("estimatedSeconds", 60), "plan.steps[].estimatedSeconds", minimum=1, maximum=86400
            ),
        )


@dataclass(frozen=True, slots=True)
class Assumption:
    id: str
    statement: str
    status: str
    evidence_refs: tuple[str, ...] = ()
    confidence: Decimal = Decimal("0")
    source: str = "inferred"

    @property
    def blocks_execution(self) -> bool:
        return self.status in {"requires-approval", "rejected"}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "statement": self.statement, "status": self.status}
        if self.evidence_refs:
            payload["evidenceRefs"] = list(self.evidence_refs)
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> Assumption:
        reject_unknown_fields(value, {"id", "statement", "status", "evidenceRefs"}, "plan.assumptions[]")
        status = require_string(value.get("status"), "plan.assumptions[].status", max_length=32)
        if status not in ASSUMPTION_STATES:
            raise ContractError("invalid_enum", f"assumption status must be one of: {', '.join(ASSUMPTION_STATES)}")
        return cls(
            id=require_identifier(value.get("id"), "plan.assumptions[].id"),
            statement=require_string(value.get("statement"), "plan.assumptions[].statement", max_length=2048),
            status=status,
            evidence_refs=require_string_sequence(value.get("evidenceRefs", ()), "plan.assumptions[].evidenceRefs"),
        )


@dataclass(frozen=True, slots=True)
class ApprovalGate:
    gate_id: str
    before_step_id: str
    roles: tuple[str, ...]
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "gateId": self.gate_id,
            "beforeStepId": self.before_step_id,
            "roles": list(self.roles),
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> ApprovalGate:
        reject_unknown_fields(value, {"gateId", "beforeStepId", "roles", "reason"}, "plan.approvalGates[]")
        return cls(
            gate_id=require_identifier(value.get("gateId"), "plan.approvalGates[].gateId"),
            before_step_id=require_identifier(value.get("beforeStepId"), "plan.approvalGates[].beforeStepId"),
            roles=require_string_sequence(
                value.get("roles"), "plan.approvalGates[].roles", allow_empty=False, unique=True
            ),
            reason=optional_string(value.get("reason"), "plan.approvalGates[].reason", max_length=2048) or "",
        )


@dataclass(frozen=True, slots=True)
class RiskSummary:
    overall_class: RiskClass
    reasons: tuple[str, ...]
    unknown_risk_weight: Decimal = Decimal("0")

    def to_payload(self) -> dict[str, Any]:
        return {
            "overallClass": self.overall_class.value,
            "reasons": list(self.reasons),
            "unknownRiskWeight": str(self.unknown_risk_weight),
        }


@dataclass(frozen=True, slots=True)
class Estimate:
    wall_clock_p50: int
    wall_clock_p80: int
    wall_clock_p95: int
    cost_p50: Decimal = Decimal("0")
    cost_p95: Decimal = Decimal("0")
    changed_files: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "wallClockSeconds": {"p50": self.wall_clock_p50, "p80": self.wall_clock_p80, "p95": self.wall_clock_p95},
            "costUsd": {"p50": str(self.cost_p50), "p95": str(self.cost_p95)},
            "changedFiles": self.changed_files,
        }


@dataclass(frozen=True, slots=True)
class RefactorPlan:
    plan_id: str
    run_id: str
    version: int
    snapshot_digests: Mapping[str, str]
    steps: tuple[PlanStep, ...]
    risk_summary: RiskSummary
    assumptions: tuple[Assumption, ...] = ()
    estimated: Estimate | None = None
    approval_gates: tuple[ApprovalGate, ...] = ()

    def __post_init__(self) -> None:
        validate_dag(self.steps)

    # -- lookups ---------------------------------------------------------

    @property
    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.steps)

    def step(self, step_id: str) -> PlanStep:
        for item in self.steps:
            if item.step_id == step_id:
                return item
        raise ContractError("unknown_step", f"plan has no step '{step_id}'")

    def gates_before(self, step_id: str) -> tuple[ApprovalGate, ...]:
        return tuple(gate for gate in self.approval_gates if gate.before_step_id == step_id)

    @property
    def mutating_steps(self) -> tuple[PlanStep, ...]:
        return tuple(step for step in self.steps if step.mutating)

    # -- graph -----------------------------------------------------------

    def topological_order(self) -> tuple[str, ...]:
        return topological_order(self.steps)

    def waves(self) -> tuple[tuple[str, ...], ...]:
        return execution_waves(self.steps)

    def critical_path(self) -> tuple[tuple[str, ...], int]:
        return critical_path(self.steps)

    def conflicts(self) -> tuple[tuple[str, str, str], ...]:
        return read_write_conflicts(self.steps)

    def parallel_groups(self) -> tuple[tuple[str, ...], ...]:
        """Waves narrowed so that no group contains a read/write conflict."""

        conflicting: dict[str, set[str]] = defaultdict(set)
        for left, right, _ in self.conflicts():
            conflicting[left].add(right)
            conflicting[right].add(left)
        groups: list[tuple[str, ...]] = []
        for wave in self.waves():
            current: list[str] = []
            for step_id in wave:
                if any(step_id in conflicting[member] for member in current):
                    groups.append(tuple(current))
                    current = [step_id]
                else:
                    current.append(step_id)
            if current:
                groups.append(tuple(current))
        return tuple(groups)

    # -- serialisation ---------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "apiVersion": API_VERSION,
            "kind": PLAN_KIND,
            "planId": self.plan_id,
            "runId": self.run_id,
            "version": self.version,
            "snapshotDigests": dict(sorted(self.snapshot_digests.items())),
            "steps": [step.to_payload() for step in self.steps],
            "riskSummary": self.risk_summary.to_payload(),
        }
        if self.assumptions:
            payload["assumptions"] = [item.to_payload() for item in self.assumptions]
        if self.estimated is not None:
            payload["estimated"] = self.estimated.to_payload()
        if self.approval_gates:
            payload["approvalGates"] = [gate.to_payload() for gate in self.approval_gates]
        return payload

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RefactorPlan:
        value = require_mapping(payload, "plan")
        reject_unknown_fields(
            value,
            {
                "apiVersion",
                "kind",
                "planId",
                "runId",
                "version",
                "snapshotDigests",
                "assumptions",
                "steps",
                "riskSummary",
                "estimated",
                "approvalGates",
            },
            "plan",
        )
        if value.get("apiVersion") != API_VERSION:
            raise ContractError("invalid_api_version", f"plan.apiVersion must be {API_VERSION}")
        if value.get("kind") != PLAN_KIND:
            raise ContractError("invalid_kind", f"plan.kind must be {PLAN_KIND}")
        digests_raw = require_mapping(value.get("snapshotDigests"), "plan.snapshotDigests")
        risk_raw = require_mapping(value.get("riskSummary"), "plan.riskSummary")
        return cls(
            plan_id=require_identifier(value.get("planId"), "plan.planId"),
            run_id=require_identifier(value.get("runId"), "plan.runId"),
            version=integer_value(value.get("version"), "plan.version", minimum=1),
            snapshot_digests={
                require_string(key, "plan.snapshotDigests key"): require_digest(
                    item, "plan.snapshotDigests value"
                )
                for key, item in digests_raw.items()
            },
            steps=tuple(
                PlanStep.from_payload(item)
                for item in require_mapping_sequence(value.get("steps"), "plan.steps", allow_empty=False)
            ),
            risk_summary=RiskSummary(
                overall_class=require_enum(risk_raw.get("overallClass"), RiskClass, "plan.riskSummary.overallClass"),
                reasons=require_string_sequence(risk_raw.get("reasons", ()), "plan.riskSummary.reasons"),
                unknown_risk_weight=decimal_value(
                    risk_raw.get("unknownRiskWeight", 0),
                    "plan.riskSummary.unknownRiskWeight",
                    minimum=Decimal("0"),
                    maximum=Decimal("1"),
                ),
            ),
            assumptions=tuple(
                Assumption.from_payload(item)
                for item in require_mapping_sequence(value.get("assumptions", ()), "plan.assumptions")
            ),
            approval_gates=tuple(
                ApprovalGate.from_payload(item)
                for item in require_mapping_sequence(value.get("approvalGates", ()), "plan.approvalGates")
            ),
        )


# ---------------------------------------------------------------------------
# Graph algorithms
# ---------------------------------------------------------------------------


def validate_dag(steps: Sequence[PlanStep]) -> None:
    if not steps:
        raise ContractError("empty_plan", "a plan must contain at least one step")
    ids = [step.step_id for step in steps]
    if len(set(ids)) != len(ids):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        raise ContractError("duplicate_step", "duplicate step id(s): " + ", ".join(duplicates))
    known = set(ids)
    for step in steps:
        unknown = sorted(set(step.depends_on) - known)
        if unknown:
            raise ContractError(
                "unknown_dependency",
                f"step '{step.step_id}' depends on unknown step(s): " + ", ".join(unknown),
            )
        if step.step_id in step.depends_on:
            raise ContractError("self_dependency", f"step '{step.step_id}' depends on itself")
    cycle = find_cycle(steps)
    if cycle:
        raise ContractError(
            "plan_cycle",
            "plan dependency graph contains a cycle: " + " -> ".join(cycle),
            {"cycle": list(cycle)},
        )


def find_cycle(steps: Sequence[PlanStep]) -> tuple[str, ...]:
    """Return one concrete cycle, or ``()``.

    Reporting the actual cycle matters: the operator has to break it, and
    "there is a cycle somewhere" is not actionable in a 400-step plan.
    """

    return find_cycle_in_graph({step.step_id: tuple(step.depends_on) for step in steps})


def find_cycle_in_graph(dependencies: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """The same cycle search over a bare dependency mapping.

    Programs, portfolios and plans all need this and none of them should have
    to fabricate :class:`PlanStep` objects to get at it.
    """

    state: dict[str, int] = dict.fromkeys(dependencies, 0)
    stack: list[str] = []

    def visit(node: str) -> tuple[str, ...]:
        state[node] = 1
        stack.append(node)
        for dependency in dependencies.get(node, ()):
            if state.get(dependency, 0) == 1:
                index = stack.index(dependency)
                return (*stack[index:], dependency)
            if state.get(dependency, 0) == 0:
                found = visit(dependency)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return ()

    for node in sorted(dependencies):
        if state[node] == 0:
            found = visit(node)
            if found:
                return found
    return ()


def topological_order(steps: Sequence[PlanStep]) -> tuple[str, ...]:
    remaining = {step.step_id: set(step.depends_on) for step in steps}
    ordered: list[str] = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps - set(ordered))
        if not ready:
            raise ContractError("plan_cycle", "plan dependency graph contains a cycle")
        for name in ready:
            ordered.append(name)
            del remaining[name]
    return tuple(ordered)


def execution_waves(steps: Sequence[PlanStep]) -> tuple[tuple[str, ...], ...]:
    """Group steps into dependency levels; every level may run concurrently."""

    depths: dict[str, int] = {}
    by_id = {step.step_id: step for step in steps}
    for step_id in topological_order(steps):
        step = by_id[step_id]
        depths[step_id] = 0 if not step.depends_on else 1 + max(depths[item] for item in step.depends_on)
    waves: dict[int, list[str]] = defaultdict(list)
    for step_id, depth in depths.items():
        waves[depth].append(step_id)
    return tuple(tuple(sorted(waves[depth])) for depth in sorted(waves))


def critical_path(steps: Sequence[PlanStep]) -> tuple[tuple[str, ...], int]:
    """Longest-duration dependency chain and its total estimated seconds."""

    by_id = {step.step_id: step for step in steps}
    best: dict[str, tuple[int, tuple[str, ...]]] = {}
    for step_id in topological_order(steps):
        step = by_id[step_id]
        if not step.depends_on:
            best[step_id] = (step.estimated_seconds, (step_id,))
            continue
        parent = max((best[item] for item in step.depends_on), key=lambda entry: entry[0])
        best[step_id] = (parent[0] + step.estimated_seconds, (*parent[1], step_id))
    if not best:
        return (), 0
    total, path = max(best.values(), key=lambda entry: entry[0])
    return path, total


def _sets_overlap(left: Iterable[str], right: Iterable[str]) -> str | None:
    """Overlap between two path/glob sets, prefix-aware."""

    from .contracts import match_path_glob, path_within

    for a in left:
        for b in right:
            if a == b:
                return a
            if "*" in a and match_path_glob(b.replace("*", "x"), a):
                return f"{a}~{b}"
            if "*" in b and match_path_glob(a.replace("*", "x"), b):
                return f"{a}~{b}"
            if "*" not in a and "*" not in b and (path_within(a, b) or path_within(b, a)):
                return f"{a}~{b}"
    return None


def read_write_conflicts(steps: Sequence[PlanStep]) -> tuple[tuple[str, str, str], ...]:
    """Pairs of independent steps that may not run concurrently.

    Two steps conflict when their write sets intersect, or when one writes what
    the other reads, *unless* one already depends on the other (in which case
    the ordering is already forced and there is nothing to detect).
    """

    order = topological_order(steps)
    position = {step_id: index for index, step_id in enumerate(order)}
    by_id = {step.step_id: step for step in steps}
    ancestors: dict[str, set[str]] = {}
    for step_id in order:
        step = by_id[step_id]
        collected: set[str] = set()
        for dependency in step.depends_on:
            collected.add(dependency)
            collected |= ancestors[dependency]
        ancestors[step_id] = collected

    conflicts: list[tuple[str, str, str]] = []
    ids = sorted(by_id, key=lambda item: position[item])
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1 :]:
            if left_id in ancestors[right_id] or right_id in ancestors[left_id]:
                continue
            left, right = by_id[left_id], by_id[right_id]
            overlap = _sets_overlap(left.write_set, right.write_set)
            if overlap is not None:
                conflicts.append((left_id, right_id, f"write-write:{overlap}"))
                continue
            overlap = _sets_overlap(left.write_set, right.read_set)
            if overlap is not None:
                conflicts.append((left_id, right_id, f"write-read:{overlap}"))
                continue
            overlap = _sets_overlap(left.read_set, right.write_set)
            if overlap is not None:
                conflicts.append((left_id, right_id, f"read-write:{overlap}"))
    return tuple(conflicts)


def estimate_plan(
    steps: Sequence[PlanStep],
    *,
    max_parallel_shards: int,
    changed_files: int = 0,
    cost_per_step_usd: Decimal = Decimal("0"),
) -> Estimate:
    """Percentile wall-clock estimate.

    The p50 is the critical path when parallelism is unconstrained, floored by
    total work divided by the shard limit — a plan cannot finish faster than
    its own throughput ceiling.  p80/p95 apply variance multipliers that grow
    with plan size, because long plans are where retries actually accumulate.
    """

    path, path_seconds = critical_path(steps)
    total_seconds = sum(step.estimated_seconds for step in steps)
    shards = max(1, max_parallel_shards)
    throughput_floor = -(-total_seconds // shards)  # ceiling division
    p50 = max(path_seconds, throughput_floor)
    size_factor = min(Decimal("0.6"), Decimal(len(steps)) / Decimal(100))
    p80 = int(p50 * (Decimal("1.25") + size_factor))
    p95 = int(p50 * (Decimal("1.7") + size_factor * 2))
    retry_allowance = sum(step.budgets.max_attempts - 1 for step in steps if step.mutating)
    p95 += retry_allowance * 30
    return Estimate(
        wall_clock_p50=int(p50),
        wall_clock_p80=p80,
        wall_clock_p95=p95,
        cost_p50=cost_per_step_usd * len(steps),
        cost_p95=cost_per_step_usd * len(steps) * Decimal("2"),
        changed_files=changed_files,
    )


__all__ = [
    "ASSUMPTION_STATES",
    "ApprovalGate",
    "Assumption",
    "Estimate",
    "PlanStep",
    "RefactorPlan",
    "RiskSummary",
    "StepBudget",
    "StepRollback",
    "StepScope",
    "StepValidation",
    "critical_path",
    "estimate_plan",
    "execution_waves",
    "find_cycle",
    "find_cycle_in_graph",
    "read_write_conflicts",
    "topological_order",
    "validate_dag",
]
