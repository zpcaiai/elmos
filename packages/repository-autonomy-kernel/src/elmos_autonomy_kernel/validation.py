"""Validation DAG: build, plan under a budget, execute, aggregate, compare to a baseline.

Three separations carry the whole module.

``SKIPPED`` is a status, not an absence.  A check that the budget did not reach is not
``PASSED`` and it is not simply missing from the report; it is present with a reason.  The
moment "skipped" and "passed" are allowed to look alike in an aggregate, a budget squeeze
turns silently into a green build.

``INCOMPLETE`` is a verdict, not a shade of ``PASSED``.  The overall status can only be
``PASSED`` when every *required* check actually ran and passed.  Any required check left
``SKIPPED`` or ``NOT_RUN`` means the run has no verdict on that requirement, and saying
otherwise is the single most expensive lie a gate can tell.

``INFRA_FAILURE`` is not ``FAILED``.  A runner that could not produce the evidence it
declared has told us nothing about the product; reporting it as a product defect sends
engineers to debug code that is fine, and — worse — a later "flaky, ignore it" policy then
covers real failures too.

Differential mode adds the fourth: a check present in the baseline and absent from the
current run is a *regression risk*, never an improvement.  A disappearing test is how
coverage silently drops, and it is invisible to any comparison that only walks the checks
the current run happens to contain.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .contracts import (
    Status,
    digest,
    format_timestamp,
    reject_unknown_fields,
    require_bool,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import Clock
from .registry import register

__all__ = [
    "CheckStatus",
    "OverallStatus",
    "SkipReason",
    "Check",
    "ValidationDag",
    "Budget",
    "Skip",
    "ExecutionPlan",
    "CheckOutcome",
    "ValidationResult",
    "Differential",
    "plan",
    "execute",
    "compare_to_baseline",
    "coverage_map",
    "handle",
]

register_codes(
    Category.VERIFICATION,
    "VALIDATION_CYCLE",
    "VALIDATION_UNKNOWN_DEPENDENCY",
    "VALIDATION_DUPLICATE_CHECK",
    "VALIDATION_EVIDENCE_MISSING",
    "VALIDATION_RUNNER_CONTRACT_VIOLATION",
    "VALIDATION_BUDGET_INVALID",
    "VALIDATION_BASELINE_MISMATCH",
    # Codes named by skills/validation-dag/SKILL.md.
    "VALIDATION_PLAN_INCOMPLETE",
    "TEST_INFRA_FAILURE",
    "GATE_UNMAPPED",
    "NONDETERMINISTIC_VALIDATION",
)


class CheckStatus(StrEnum):
    """Per-check outcome.

    ``SKIPPED`` (the plan chose not to run it) and ``NOT_RUN`` (the plan intended to run it
    and execution never reached it) are distinct because the remedies differ: raise the
    budget versus investigate why the run stopped.  Collapsing them hides which one
    happened.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"
    INFRA_FAILURE = "INFRA_FAILURE"


#: Projection onto ``contracts/schemas/validation-result.schema.json``, whose enum has no
#: NOT_RUN.  The projection is lossy, so the kernel-native status is always emitted beside
#: it as ``kernelStatus`` rather than being thrown away at the boundary.
_SCHEMA_STATUS: Mapping[CheckStatus, str] = {
    CheckStatus.PASSED: "PASS",
    CheckStatus.FAILED: "FAIL",
    CheckStatus.SKIPPED: "SKIPPED",
    CheckStatus.NOT_RUN: "BLOCKED",
    CheckStatus.BLOCKED: "BLOCKED",
    CheckStatus.INFRA_FAILURE: "INFRA_FAILURE",
}

_RAN = frozenset({CheckStatus.PASSED, CheckStatus.FAILED})
_UNKNOWN = frozenset({CheckStatus.SKIPPED, CheckStatus.NOT_RUN, CheckStatus.BLOCKED,
                      CheckStatus.INFRA_FAILURE})


class OverallStatus(StrEnum):
    """Aggregate verdict.

    ``INCOMPLETE`` means "no verdict": at least one required check produced no result.  It
    is never a synonym for ``PASSED`` and never a synonym for ``FAILED``.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


class SkipReason(StrEnum):
    """Why a check was not selected or not executed."""

    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CHECK_LIMIT_REACHED = "CHECK_LIMIT_REACHED"
    DEPENDENCY_SKIPPED = "DEPENDENCY_SKIPPED"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    PLAN_TRUNCATED = "PLAN_TRUNCATED"


#: Check kinds that count as adversarial coverage.  ``negative-tests-included`` is a gate,
#: so the set it is measured against has to be data, not a reviewer's memory.
NEGATIVE_KINDS: frozenset[str] = frozenset({
    "negative", "fault-injection", "security", "recovery", "chaos", "property",
})


@dataclass(frozen=True, slots=True)
class Check:
    """One validator node.

    ``required`` defaults to ``True``: a check whose necessity was never stated is treated
    as necessary, so a missing flag cannot quietly downgrade a gate into an optional
    nicety.  ``cost_weight`` and ``timeout_ms`` are integers — budgets are compared and
    hashed, and a float budget is not reproducible across machines.
    """

    check_id: str
    requires: tuple[str, ...] = ()
    kind: str = "unit"
    command_ref: str = ""
    timeout_ms: int = 60_000
    cost_weight: int = 1
    required_evidence_kinds: tuple[str, ...] = ()
    required: bool = True

    def __post_init__(self) -> None:
        require_str(self.check_id, "check_id", max_length=128)
        require_int(self.timeout_ms, "timeout_ms", minimum=1)
        require_int(self.cost_weight, "cost_weight", minimum=0)

    def to_payload(self) -> dict[str, Any]:
        return {"checkId": self.check_id, "requires": list(self.requires), "kind": self.kind,
                "commandRef": self.command_ref, "timeoutMs": self.timeout_ms,
                "costWeight": self.cost_weight,
                "requiredEvidenceKinds": list(self.required_evidence_kinds),
                "required": self.required}


@dataclass(frozen=True, slots=True)
class ValidationDag:
    """A validated dependency graph of checks."""

    checks: tuple[Check, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for check in self.checks:
            if check.check_id in seen:
                raise KernelError(
                    code="VALIDATION_DUPLICATE_CHECK",
                    message=f"check {check.check_id!r} is declared twice",
                    recommended_action="give every check a unique id",
                )
            seen.add(check.check_id)
        for check in self.checks:
            for dependency in check.requires:
                if dependency not in seen:
                    raise KernelError(
                        code="VALIDATION_UNKNOWN_DEPENDENCY",
                        message=f"check {check.check_id!r} requires unknown {dependency!r}",
                        recommended_action="declare the dependency or remove the edge",
                        details={"checkId": check.check_id, "missing": dependency},
                    )
        self._detect_cycle()

    def by_id(self) -> dict[str, Check]:
        return {check.check_id: check for check in self.checks}

    def _detect_cycle(self) -> None:
        graph = {check.check_id: tuple(sorted(check.requires)) for check in self.checks}
        state: dict[str, int] = {}
        path: list[str] = []

        def visit(node: str) -> None:
            state[node] = 1
            path.append(node)
            for dependency in graph[node]:
                mark = state.get(dependency, 0)
                if mark == 1:
                    cycle = path[path.index(dependency):] + [dependency]
                    raise KernelError(
                        code="VALIDATION_CYCLE",
                        message="validation graph is not a DAG: " + " -> ".join(cycle),
                        recommended_action="break the dependency cycle",
                        details={"cycle": cycle},
                    )
                if mark == 0:
                    visit(dependency)
            path.pop()
            state[node] = 2

        for node in sorted(graph):
            if state.get(node, 0) == 0:
                visit(node)

    def waves(self) -> tuple[tuple[str, ...], ...]:
        """Layer the DAG: every check in a wave depends only on earlier waves."""

        graph = self.by_id()
        depth: dict[str, int] = {}
        remaining = set(graph)
        layers: list[tuple[str, ...]] = []
        while remaining:
            ready = tuple(sorted(
                node for node in remaining
                if all(dependency in depth for dependency in graph[node].requires)
            ))
            if not ready:  # pragma: no cover - guarded by _detect_cycle
                raise KernelError(
                    code="VALIDATION_CYCLE",
                    message="validation graph cannot be layered",
                    recommended_action="break the dependency cycle",
                )
            level = len(layers)
            for node in ready:
                depth[node] = level
            remaining -= set(ready)
            layers.append(ready)
        return tuple(layers)

    def critical_path(self) -> tuple[tuple[str, ...], int]:
        """Longest dependency chain by declared timeout, and its total in ms."""

        graph = self.by_id()
        best: dict[str, tuple[int, tuple[str, ...]]] = {}

        def cost(node: str) -> tuple[int, tuple[str, ...]]:
            if node in best:
                return best[node]
            check = graph[node]
            longest_ms = 0
            longest_path: tuple[str, ...] = ()
            for dependency in sorted(check.requires):
                dependency_ms, dependency_path = cost(dependency)
                if (dependency_ms, dependency_path) > (longest_ms, longest_path):
                    longest_ms, longest_path = dependency_ms, dependency_path
            best[node] = (longest_ms + check.timeout_ms, (*longest_path, node))
            return best[node]

        total = 0
        path: tuple[str, ...] = ()
        for node in sorted(graph):
            node_total, node_path = cost(node)
            if (node_total, node_path) > (total, path):
                total, path = node_total, node_path
        return path, total

    def to_payload(self) -> dict[str, Any]:
        path, total_ms = self.critical_path()
        return {
            "checks": [check.to_payload() for check in
                       sorted(self.checks, key=lambda c: c.check_id)],
            "waves": [list(wave) for wave in self.waves()],
            "criticalPath": list(path),
            "criticalPathMs": total_ms,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class Budget:
    """An integer cost budget, optionally also a check-count cap."""

    max_cost: int
    max_checks: int | None = None

    def __post_init__(self) -> None:
        require_int(self.max_cost, "max_cost", minimum=0)
        if self.max_checks is not None:
            require_int(self.max_checks, "max_checks", minimum=0)

    def to_payload(self) -> dict[str, Any]:
        return {"maxCost": self.max_cost, "maxChecks": self.max_checks}


@dataclass(frozen=True, slots=True)
class Skip:
    """A check that was deliberately not selected or not executed, with its reason."""

    check_id: str
    reason: SkipReason
    message: str
    required: bool

    def to_payload(self) -> dict[str, Any]:
        return {"checkId": self.check_id, "reason": str(self.reason),
                "message": self.message, "required": self.required}


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """A selected order plus everything that fell outside the budget."""

    order: tuple[str, ...]
    skipped: tuple[Skip, ...]
    budget: Budget
    planned_cost: int

    def to_payload(self) -> dict[str, Any]:
        return {"order": list(self.order),
                "skipped": [skip.to_payload() for skip in self.skipped],
                "budget": self.budget.to_payload(),
                "plannedCost": self.planned_cost,
                "selectedCount": len(self.order),
                "skippedCount": len(self.skipped)}

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def plan(dag: ValidationDag, budget: Budget) -> ExecutionPlan:
    """Select an execution order under ``budget``.

    Within a wave, required checks are considered before optional ones and cheaper checks
    before expensive ones, so a tight budget spends itself on the checks that can actually
    produce a verdict.  Every check not selected appears in ``skipped`` with a reason —
    the plan never simply omits work.
    """

    graph = dag.by_id()
    selected: list[str] = []
    skipped: list[Skip] = []
    dropped: set[str] = set()
    spent = 0

    for wave in dag.waves():
        ordered = sorted(wave, key=lambda node: (not graph[node].required,
                                                 graph[node].cost_weight, node))
        for node in ordered:
            check = graph[node]
            blocked_by = sorted(d for d in check.requires if d in dropped)
            if blocked_by:
                dropped.add(node)
                skipped.append(Skip(check_id=node, reason=SkipReason.DEPENDENCY_SKIPPED,
                                    message=f"depends on skipped {', '.join(blocked_by)}",
                                    required=check.required))
                continue
            if budget.max_checks is not None and len(selected) >= budget.max_checks:
                dropped.add(node)
                skipped.append(Skip(check_id=node, reason=SkipReason.CHECK_LIMIT_REACHED,
                                    message=f"plan already holds {budget.max_checks} checks",
                                    required=check.required))
                continue
            if spent + check.cost_weight > budget.max_cost:
                dropped.add(node)
                skipped.append(Skip(
                    check_id=node, reason=SkipReason.BUDGET_EXHAUSTED,
                    message=(f"cost {check.cost_weight} exceeds the remaining "
                             f"{budget.max_cost - spent} of {budget.max_cost}"),
                    required=check.required))
                continue
            selected.append(node)
            spent += check.cost_weight

    return ExecutionPlan(order=tuple(selected),
                         skipped=tuple(sorted(skipped, key=lambda s: s.check_id)),
                         budget=budget, planned_cost=spent)


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """What one check actually did.

    ``duration_ms`` is ``None`` with ``duration_measured=False`` when nothing measured it.
    A duration of ``0`` means "measured, and it was that fast"; the two must not render
    identically, because a monitoring rule that treats 0 ms as "instant" will happily hide
    a whole subsystem that never reported.
    """

    check_id: str
    status: CheckStatus
    required: bool
    duration_ms: int | None = None
    duration_measured: bool = False
    evidence_ids: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    reason: str = ""

    def to_payload(self, *, validation_id: str, started_at: str,
                   finished_at: str) -> dict[str, Any]:
        return {
            "validationId": f"{validation_id}:{self.check_id}",
            "validatorId": self.check_id,
            "status": _SCHEMA_STATUS[self.status],
            "kernelStatus": str(self.status),
            "required": self.required,
            "findingIds": list(self.finding_ids),
            "evidenceIds": list(self.evidence_ids),
            "startedAt": started_at,
            "finishedAt": finished_at,
            "reason": self.reason,
            "metrics": {"durationMs": self.duration_ms,
                        "durationMeasured": self.duration_measured},
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The aggregate of one validation run."""

    result_id: str
    outcomes: tuple[CheckOutcome, ...]
    started_at: str
    finished_at: str
    plan_digest: str = ""

    def by_id(self) -> dict[str, CheckOutcome]:
        return {outcome.check_id: outcome for outcome in self.outcomes}

    @property
    def required_outcomes(self) -> tuple[CheckOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.required)

    @property
    def unknown_required(self) -> tuple[str, ...]:
        """Required checks that produced no verdict — the incompleteness, itemised."""

        return tuple(sorted(outcome.check_id for outcome in self.required_outcomes
                            if outcome.status in _UNKNOWN))

    @property
    def failed_required(self) -> tuple[str, ...]:
        return tuple(sorted(outcome.check_id for outcome in self.required_outcomes
                            if outcome.status is CheckStatus.FAILED))

    @property
    def overall(self) -> OverallStatus:
        """``PASSED`` only when every required check ran and passed.

        Precedence when a run has both a failure and an unknown: ``FAILED`` wins, because
        a definite negative verdict is the more actionable one and both block release.
        The incompleteness is not lost — :attr:`unknown_required` still itemises it and
        :attr:`is_complete` is still ``False``.
        """

        if self.failed_required:
            return OverallStatus.FAILED
        if self.unknown_required:
            return OverallStatus.INCOMPLETE
        return OverallStatus.PASSED

    @property
    def is_complete(self) -> bool:
        return not self.unknown_required

    def to_payload(self) -> dict[str, Any]:
        return {
            "resultId": self.result_id,
            "overall": str(self.overall),
            "complete": self.is_complete,
            "unknownRequired": list(self.unknown_required),
            "failedRequired": list(self.failed_required),
            "planDigest": self.plan_digest,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "results": [outcome.to_payload(validation_id=self.result_id,
                                           started_at=self.started_at,
                                           finished_at=self.finished_at)
                        for outcome in sorted(self.outcomes, key=lambda o: o.check_id)],
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


Runner = Callable[[Check], Mapping[str, Any]]

_RUNNER_FIELDS = ("status", "evidenceIds", "findingIds", "durationMs")
_RUNNER_STATUSES = {"PASSED", "FAILED", "INFRA_FAILURE"}


def _decode_runner_result(check: Check, raw: Any) -> CheckOutcome:
    if not isinstance(raw, Mapping):
        raise KernelError(
            code="VALIDATION_RUNNER_CONTRACT_VIOLATION",
            message=f"runner for {check.check_id!r} returned {type(raw).__name__}",
            recommended_action="return a mapping with at least a status",
        )
    reject_unknown_fields(raw, _RUNNER_FIELDS, field_name=f"runner[{check.check_id}]")
    status_text = require_str(raw.get("status"), f"runner[{check.check_id}].status",
                              max_length=32)
    if status_text not in _RUNNER_STATUSES:
        raise KernelError(
            code="VALIDATION_RUNNER_CONTRACT_VIOLATION",
            message=(f"runner for {check.check_id!r} reported {status_text!r}; a runner may "
                     "only report PASSED, FAILED or INFRA_FAILURE"),
            recommended_action="SKIPPED and NOT_RUN are decided by the plan, not the runner",
            details={"supported": sorted(_RUNNER_STATUSES)},
        )
    duration = raw.get("durationMs")
    if duration is not None:
        require_int(duration, f"runner[{check.check_id}].durationMs", minimum=0)
    evidence = require_str_seq(raw.get("evidenceIds", ()), f"runner[{check.check_id}].evidenceIds")
    findings = require_str_seq(raw.get("findingIds", ()), f"runner[{check.check_id}].findingIds")
    return CheckOutcome(
        check_id=check.check_id,
        status=CheckStatus(status_text),
        required=check.required,
        duration_ms=duration,
        duration_measured=duration is not None,
        evidence_ids=evidence,
        finding_ids=findings,
    )


def execute(execution_plan: ExecutionPlan, dag: ValidationDag, runner: Runner, *,
            clock: Clock | None = None, result_id: str = "validation-run",
            started_at: str = "1970-01-01T00:00:00.000000Z") -> ValidationResult:
    """Run the plan through ``runner`` and aggregate.

    A check whose runner reported success but produced none of the evidence it declared is
    recorded as ``INFRA_FAILURE``, not ``PASSED`` and not ``FAILED``: an unevidenced pass
    is not a pass, and it is not a product defect either.
    """

    graph = dag.by_id()
    outcomes: list[CheckOutcome] = []
    finished: dict[str, CheckStatus] = {}
    start_wall = clock.now() if clock is not None else None

    for check_id in execution_plan.order:
        check = graph[check_id]
        blocked = sorted(d for d in check.requires
                         if finished.get(d) not in (CheckStatus.PASSED,))
        if blocked:
            outcome = CheckOutcome(
                check_id=check_id, status=CheckStatus.BLOCKED, required=check.required,
                reason=f"dependency not passed: {', '.join(blocked)}")
            outcomes.append(outcome)
            finished[check_id] = outcome.status
            continue
        before = clock.monotonic_ns() if clock is not None else None
        raw = runner(check)
        outcome = _decode_runner_result(check, raw)
        if before is not None and clock is not None:
            measured = (clock.monotonic_ns() - before) // 1_000_000
            outcome = CheckOutcome(
                check_id=outcome.check_id, status=outcome.status, required=outcome.required,
                duration_ms=measured, duration_measured=True,
                evidence_ids=outcome.evidence_ids, finding_ids=outcome.finding_ids,
                reason=outcome.reason)
        if outcome.status is CheckStatus.PASSED and check.required_evidence_kinds \
                and not outcome.evidence_ids:
            outcome = CheckOutcome(
                check_id=outcome.check_id, status=CheckStatus.INFRA_FAILURE,
                required=outcome.required, duration_ms=outcome.duration_ms,
                duration_measured=outcome.duration_measured, evidence_ids=(),
                finding_ids=outcome.finding_ids,
                reason=("declared evidence kinds "
                        f"{list(check.required_evidence_kinds)} but produced none; "
                        "an unevidenced pass is not a pass"))
        outcomes.append(outcome)
        finished[check_id] = outcome.status

    for skip in execution_plan.skipped:
        check = graph[skip.check_id]
        outcomes.append(CheckOutcome(check_id=skip.check_id, status=CheckStatus.SKIPPED,
                                     required=check.required,
                                     reason=f"{skip.reason}: {skip.message}"))

    ran = {outcome.check_id for outcome in outcomes}
    for check_id in sorted(set(graph) - ran):
        outcomes.append(CheckOutcome(check_id=check_id, status=CheckStatus.NOT_RUN,
                                     required=graph[check_id].required,
                                     reason="in the DAG but neither selected nor skipped"))

    finished_at = format_timestamp(clock.now()) if clock is not None else started_at
    if start_wall is not None:
        started_at = format_timestamp(start_wall)
    return ValidationResult(result_id=result_id, outcomes=tuple(outcomes),
                            started_at=started_at, finished_at=finished_at,
                            plan_digest=execution_plan.digest)


# --- differential mode -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Differential:
    """Current run against a baseline run.

    ``missing_from_current`` is the field that exists because of a specific production
    failure mode: a test that stops being emitted looks, to any naive comparison, exactly
    like a test that has no news.  It is reported as a regression risk.
    """

    newly_failing: tuple[str, ...] = ()
    newly_passing: tuple[str, ...] = ()
    still_failing: tuple[str, ...] = ()
    missing_from_current: tuple[str, ...] = ()
    new_in_current: tuple[str, ...] = ()
    regression_risks: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def has_regression_risk(self) -> bool:
        return bool(self.regression_risks) or bool(self.newly_failing)

    def to_payload(self) -> dict[str, Any]:
        return {
            "newlyFailing": list(self.newly_failing),
            "newlyPassing": list(self.newly_passing),
            "stillFailing": list(self.still_failing),
            "missingFromCurrent": list(self.missing_from_current),
            "newInCurrent": list(self.new_in_current),
            "regressionRisks": [dict(risk) for risk in self.regression_risks],
            "hasRegressionRisk": self.has_regression_risk,
        }


def compare_to_baseline(current: ValidationResult, baseline: ValidationResult) -> Differential:
    """Classify the current run against a baseline.

    A check the baseline covered and the current run does not cover — because it vanished
    from the DAG, or because it was skipped — is a regression risk.  It is never treated as
    "no change": lost coverage is a change, and the whole point of a differential gate is
    that it cannot be defeated by deleting the test.
    """

    current_map = current.by_id()
    baseline_map = baseline.by_id()
    newly_failing: list[str] = []
    newly_passing: list[str] = []
    still_failing: list[str] = []
    risks: list[Mapping[str, Any]] = []

    for check_id in sorted(set(baseline_map) & set(current_map)):
        was = baseline_map[check_id].status
        now = current_map[check_id].status
        if was is CheckStatus.PASSED and now is CheckStatus.FAILED:
            newly_failing.append(check_id)
        elif was is CheckStatus.FAILED and now is CheckStatus.PASSED:
            newly_passing.append(check_id)
        elif was is CheckStatus.FAILED and now is CheckStatus.FAILED:
            still_failing.append(check_id)
        if was in _RAN and now in _UNKNOWN:
            risks.append({
                "checkId": check_id,
                "reason": "COVERAGE_LOST",
                "detail": f"produced {was} in the baseline and {now} now",
                "required": current_map[check_id].required,
            })

    missing = tuple(sorted(set(baseline_map) - set(current_map)))
    for check_id in missing:
        risks.append({
            "checkId": check_id,
            "reason": "CHECK_DISAPPEARED",
            "detail": (f"present in the baseline with status {baseline_map[check_id].status} "
                       "and absent from the current run"),
            "required": baseline_map[check_id].required,
        })

    return Differential(
        newly_failing=tuple(newly_failing),
        newly_passing=tuple(newly_passing),
        still_failing=tuple(still_failing),
        missing_from_current=missing,
        new_in_current=tuple(sorted(set(current_map) - set(baseline_map))),
        regression_risks=tuple(sorted(risks, key=lambda risk: (risk["reason"],
                                                              risk["checkId"]))),
    )


# --- coverage ----------------------------------------------------------------


def coverage_map(dag: ValidationDag, criteria: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Map every acceptance criterion to the checks that gate it.

    A criterion with no check raises ``GATE_UNMAPPED``.  Invariant I1 of the SKILL says
    every MUST has at least one gate; an unmapped criterion that merely warns is a
    criterion that will ship ungated.
    """

    graph = dag.by_id()
    mapped: dict[str, list[str]] = {}
    unmapped: list[str] = []
    unknown: list[str] = []
    for criterion in sorted(criteria):
        check_ids = sorted(criteria[criterion])
        for check_id in check_ids:
            if check_id not in graph:
                unknown.append(f"{criterion}->{check_id}")
        if not check_ids:
            unmapped.append(criterion)
        mapped[criterion] = check_ids
    if unmapped or unknown:
        raise KernelError(
            code="GATE_UNMAPPED",
            message=(f"{len(unmapped)} criteria have no gate; "
                     f"{len(unknown)} reference an unknown check"),
            recommended_action="map every acceptance criterion to at least one real check",
            details={"unmapped": unmapped, "unknown": unknown},
        )
    covered = sorted({check_id for ids in mapped.values() for check_id in ids})
    return {
        "criteria": mapped,
        "criterionCount": len(mapped),
        "coveredChecks": covered,
        "uncoveredChecks": sorted(set(graph) - set(covered)),
        "criterionCoveragePerMille": 1000 if mapped else None,
        "measured": bool(mapped),
    }


def require_negative_coverage(dag: ValidationDag) -> tuple[str, ...]:
    """Return the adversarial checks, refusing a plan that has none."""

    negative = tuple(sorted(check.check_id for check in dag.checks
                            if check.kind in NEGATIVE_KINDS))
    if not negative:
        raise KernelError(
            code="VALIDATION_PLAN_INCOMPLETE",
            message="the validation DAG contains no negative, security or recovery check",
            recommended_action=("add at least one check whose kind is one of: "
                                + ", ".join(sorted(NEGATIVE_KINDS))),
            details={"acceptedKinds": sorted(NEGATIVE_KINDS)},
        )
    return negative


# --- decoding & registry entry point -----------------------------------------

_KNOWN_FIELDS = ("checks", "budget", "criteria", "recordedOutcomes", "requireNegativeCoverage")
_KNOWN_CHECK_FIELDS = ("checkId", "requires", "kind", "commandRef", "timeoutMs", "costWeight",
                       "requiredEvidenceKinds", "required")
_KNOWN_BUDGET_FIELDS = ("maxCost", "maxChecks")


def _decode_check(payload: Any, where: str) -> Check:
    mapping = require_mapping(payload, where)
    reject_unknown_fields(mapping, _KNOWN_CHECK_FIELDS, field_name=where)
    return Check(
        check_id=require_str(mapping.get("checkId"), f"{where}.checkId", max_length=128),
        requires=require_str_seq(mapping.get("requires", ()), f"{where}.requires"),
        kind=require_str(mapping.get("kind", "unit"), f"{where}.kind", max_length=64),
        command_ref=str(mapping.get("commandRef", "")),
        timeout_ms=require_int(mapping.get("timeoutMs", 60_000), f"{where}.timeoutMs",
                               minimum=1),
        cost_weight=require_int(mapping.get("costWeight", 1), f"{where}.costWeight", minimum=0),
        required_evidence_kinds=require_str_seq(mapping.get("requiredEvidenceKinds", ()),
                                                f"{where}.requiredEvidenceKinds"),
        required=require_bool(mapping.get("required", True), f"{where}.required"),
    )


@register("validation-dag")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point: build the DAG, plan under budget, optionally replay outcomes.

    Execution needs a runner, which cannot arrive over a JSON boundary.  Rather than
    pretending the plan ran, ``executed`` is an explicit flag and ``validationResult`` is
    ``None`` unless ``recordedOutcomes`` were supplied for a deterministic replay.
    """

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _KNOWN_FIELDS, field_name="validation-dag request")

    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, Sequence) or isinstance(raw_checks, (str, bytes)):
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="checks must be an array of check declarations",
            recommended_action="supply at least one check",
        )
    dag = ValidationDag(checks=tuple(_decode_check(item, f"checks[{index}]")
                                     for index, item in enumerate(raw_checks)))

    raw_budget = require_mapping(payload.get("budget", {}), "budget")
    reject_unknown_fields(raw_budget, _KNOWN_BUDGET_FIELDS, field_name="budget")
    if "maxCost" not in raw_budget:
        raise KernelError(
            code="VALIDATION_BUDGET_INVALID",
            message="budget.maxCost is required; an absent budget is not an unlimited budget",
            recommended_action="state the budget explicitly",
        )
    max_checks = raw_budget.get("maxChecks")
    budget = Budget(
        max_cost=require_int(raw_budget.get("maxCost"), "budget.maxCost", minimum=0),
        max_checks=None if max_checks is None else require_int(max_checks, "budget.maxChecks",
                                                               minimum=0),
    )
    execution_plan = plan(dag, budget)

    negative: tuple[str, ...] | None = None
    if require_bool(payload.get("requireNegativeCoverage", False), "requireNegativeCoverage"):
        negative = require_negative_coverage(dag)

    coverage: dict[str, Any] | None = None
    raw_criteria = payload.get("criteria")
    if raw_criteria is not None:
        criteria = require_mapping(raw_criteria, "criteria")
        coverage = coverage_map(dag, {
            name: require_str_seq(value, f"criteria[{name}]")
            for name, value in criteria.items()
        })

    result_payload: dict[str, Any] | None = None
    recorded = payload.get("recordedOutcomes")
    if recorded is not None:
        outcomes = require_mapping(recorded, "recordedOutcomes")

        def replay(check: Check) -> Mapping[str, Any]:
            entry = outcomes.get(check.check_id)
            if entry is None:
                raise KernelError(
                    code="VALIDATION_RUNNER_CONTRACT_VIOLATION",
                    message=f"recordedOutcomes has no entry for {check.check_id!r}",
                    recommended_action="record every selected check or shrink the plan",
                )
            return require_mapping(entry, f"recordedOutcomes[{check.check_id}]")

        result_payload = execute(execution_plan, dag, replay).to_payload()

    return {
        "status": Status.SUCCEEDED,
        "validationPlan": execution_plan.to_payload(),
        "validationDag": dag.to_payload(),
        "criticalPath": {"path": list(dag.critical_path()[0]), "totalMs": dag.critical_path()[1]},
        "coverageMap": coverage,
        "negativeChecks": None if negative is None else list(negative),
        "validationBudget": {**budget.to_payload(), "plannedCost": execution_plan.planned_cost,
                             "remaining": budget.max_cost - execution_plan.planned_cost,
                             "measured": True},
        "validationResult": result_payload,
        "executed": result_payload is not None,
        "digest": digest({"dag": dag.to_payload(), "plan": execution_plan.to_payload()}),
    }
