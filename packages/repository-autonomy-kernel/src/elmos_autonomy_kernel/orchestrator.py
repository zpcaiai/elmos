"""Durable run orchestration: state machine, event log, DAG, side effects, rollback.

This module owns *execution truth*.  Everything else in the kernel may hold an
opinion about what a run has done; only the hash-chained event log knows.  Three
choices here are load-bearing and easy to get wrong, so they are stated up front:

* **The event is appended before the materialised view moves.**  A crash between
  the two must leave a log that is ahead of the view, never a view that is ahead
  of the log — the first is recoverable by replay, the second is a fabricated
  history.  :meth:`DurableRun.rehydrate` is the recovery path and it trusts the
  log, not the cache.
* **A side effect is announced before it is attempted.**  A
  ``SIDE_EFFECT_INTENDED`` without a matching ``SIDE_EFFECT_OBSERVED`` is an
  *unresolved* effect: after a crash we do not know whether the world changed.
  Such a run may not be retried and may not be declared done; it goes to
  :func:`reconciliation_plan` and a human or a probe supplies the verdict.  This
  is the entire reason the module exists.
* **PARTIAL, INTERRUPTED and SUCCEEDED are different states with no edge between
  them.**  Neither the run table nor the step table contains a transition that
  widens partial work into success, and a step whose dependency ended PARTIAL is
  not ready to run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from .adapters.memory import (
    FixedClock,
    InMemoryArtifactStore,
    InMemoryEventStore,
    InMemoryKeyValueStore,
)
from .contracts import (
    canonical_json,
    digest,
    format_timestamp,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, not_applicable, register_codes
from .registry import DESCRIPTORS, register

register_codes(
    Category.ORCHESTRATION,
    "DAG_CYCLE",
    "DUPLICATE_STEP",
    "UNKNOWN_STEP",
    "STEP_NOT_READY",
    "PAUSE_ORIGIN_MISSING",
    "UNSAFE_CANCEL_POINT",
    "ATTEMPTS_EXHAUSTED",
    "ROLLBACK_INCOMPLETE",
    "TASK_SPEC_VERSION_NOT_BUMPED",
)
register_codes(
    Category.INTEGRITY,
    "UNRESOLVED_SIDE_EFFECT",
    "EVENT_CHAIN_BROKEN",
    "HISTORY_GAP",
)
register_codes(Category.RESOURCE, "RESOURCE_EXHAUSTED")

__all__ = [
    "SKILL_ID",
    "GENESIS_CHAIN",
    "RunState",
    "StepState",
    "EventType",
    "RetryClass",
    "TERMINAL_RUN_STATES",
    "PAUSABLE_RUN_STATES",
    "RUN_TRANSITIONS",
    "STEP_TRANSITIONS",
    "allowed_targets",
    "is_terminal",
    "transition",
    "step_transition",
    "RunEvent",
    "chain_for",
    "verify_chain",
    "StepDefinition",
    "WorkflowDefinition",
    "Dag",
    "build_dag",
    "Budget",
    "budget_report",
    "SideEffectIntent",
    "StepView",
    "RunView",
    "replay",
    "view_digest",
    "next_ready_steps",
    "idempotency_key",
    "ReconciliationTask",
    "reconciliation_plan",
    "unresolved_intents",
    "Checkpoint",
    "checkpoint",
    "CompensationEntry",
    "RollbackPlan",
    "rollback_plan",
    "SafePoint",
    "is_safe_point",
    "steps_to_rerun",
    "RetryPolicy",
    "RetryDecision",
    "classify_failure",
    "backoff_ms",
    "decide_retry",
    "DurableRun",
    "handle",
]

SKILL_ID = "durable-run-orchestrator"

#: Anchor of the per-run hash chain.  A stream whose first event does not chain
#: from this cannot be a complete history.
GENESIS_CHAIN = "sha256:" + "0" * 64

_EPOCH = datetime.fromisoformat("2026-01-01T00:00:00+00:00")


# --- state machines ----------------------------------------------------------


class RunState(StrEnum):
    """The nineteen run states of the autonomy contract.

    The set is closed: a run state that is not here cannot be persisted, which
    is what keeps a workflow author from inventing ``ALMOST_DONE``.
    """

    CREATED = "CREATED"
    DISCOVERING = "DISCOVERING"
    SPECIFYING = "SPECIFYING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    RELEASING = "RELEASING"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    SUCCEEDED = "SUCCEEDED"


class StepState(StrEnum):
    """Per-step lifecycle.

    ``PARTIAL`` and ``INTERRUPTED`` are first-class outcomes with no edge to
    ``SUCCEEDED``: partial work stays partial until a repair produces a fresh
    success, and interrupted work stays interrupted until it is reconciled.
    """

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    INTERRUPTED = "INTERRUPTED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    SKIPPED = "SKIPPED"


class EventType(StrEnum):
    """Every kind of fact the log can hold.

    The list is deliberately small.  An orchestrator that needs a new fact adds
    an event type here and a clause to :func:`_apply`; it never smuggles state
    into an existing payload, because replay would then depend on the writer's
    conventions rather than on the schema.
    """

    RUN_CREATED = "RUN_CREATED"
    RUN_STATE_CHANGED = "RUN_STATE_CHANGED"
    STEP_STATE_CHANGED = "STEP_STATE_CHANGED"
    SIDE_EFFECT_INTENDED = "SIDE_EFFECT_INTENDED"
    SIDE_EFFECT_OBSERVED = "SIDE_EFFECT_OBSERVED"
    SIDE_EFFECT_RECONCILED = "SIDE_EFFECT_RECONCILED"
    CHECKPOINT_WRITTEN = "CHECKPOINT_WRITTEN"
    BUDGET_CONSUMED = "BUDGET_CONSUMED"
    SAFE_POINT_REACHED = "SAFE_POINT_REACHED"
    REQUIREMENT_UPDATED = "REQUIREMENT_UPDATED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    COMPENSATION_APPLIED = "COMPENSATION_APPLIED"
    FORK = "FORK"


class RetryClass(StrEnum):
    """How a failure should be treated by the retry controller."""

    RETRYABLE = "RETRYABLE"
    TERMINAL = "TERMINAL"
    INTERRUPTED = "INTERRUPTED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


#: Absorbing states.  A run that has succeeded, been cancelled, been rolled back
#: or failed terminally is finished; re-opening it would make "how did this run
#: end?" unanswerable.  These therefore have *no* outgoing edges at all.
TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {
        RunState.SUCCEEDED,
        RunState.CANCELLED,
        RunState.ROLLED_BACK,
        RunState.FAILED_TERMINAL,
    }
)

#: States a run may be paused from, and therefore exactly the states it may be
#: resumed into.  ``RELEASING`` is deliberately absent: a release is a critical
#: section and pausing inside it would strand a half-published artefact.
PAUSABLE_RUN_STATES: tuple[RunState, ...] = (
    RunState.DISCOVERING,
    RunState.SPECIFYING,
    RunState.PLANNING,
    RunState.EXECUTING,
    RunState.VERIFYING,
    RunState.REPAIRING,
    RunState.BLOCKED,
)

_R = RunState

_BASE_TRANSITIONS: dict[RunState, set[RunState]] = {
    _R.CREATED: {_R.DISCOVERING, _R.SPECIFYING, _R.CANCEL_REQUESTED},
    _R.DISCOVERING: {_R.SPECIFYING, _R.PLANNING, _R.FAILED_RETRYABLE,
                     _R.FAILED_TERMINAL, _R.CANCEL_REQUESTED},
    _R.SPECIFYING: {_R.PLANNING, _R.BLOCKED, _R.FAILED_TERMINAL, _R.CANCEL_REQUESTED},
    _R.PLANNING: {_R.AWAITING_APPROVAL, _R.EXECUTING, _R.BLOCKED, _R.FAILED_RETRYABLE,
                  _R.FAILED_TERMINAL, _R.CANCEL_REQUESTED},
    _R.AWAITING_APPROVAL: {_R.EXECUTING, _R.BLOCKED, _R.CANCEL_REQUESTED, _R.FAILED_TERMINAL},
    _R.EXECUTING: {_R.VERIFYING, _R.BLOCKED, _R.FAILED_RETRYABLE, _R.FAILED_TERMINAL,
                   _R.CANCEL_REQUESTED},
    _R.VERIFYING: {_R.REPAIRING, _R.RELEASING, _R.PARTIALLY_COMPLETED, _R.FAILED_TERMINAL,
                   _R.CANCEL_REQUESTED},
    _R.REPAIRING: {_R.EXECUTING, _R.VERIFYING, _R.PARTIALLY_COMPLETED, _R.FAILED_TERMINAL,
                   _R.CANCEL_REQUESTED},
    _R.RELEASING: {_R.SUCCEEDED, _R.ROLLING_BACK, _R.FAILED_TERMINAL},
    # A blocked run is waiting on a human answer, not dead.  The reference
    # sketch gave BLOCKED no outgoing edges, which made every blocked run
    # unrecoverable.
    _R.BLOCKED: {_R.SPECIFYING, _R.PLANNING, _R.EXECUTING, _R.CANCEL_REQUESTED,
                 _R.FAILED_TERMINAL},
    # PARTIALLY_COMPLETED may be repaired or rolled back.  It may NOT reach
    # RELEASING, because RELEASING is the only door to SUCCEEDED and partial
    # work must never walk through it without a repair producing real success.
    _R.PARTIALLY_COMPLETED: {_R.REPAIRING, _R.ROLLING_BACK, _R.CANCEL_REQUESTED,
                             _R.FAILED_TERMINAL},
    _R.CANCEL_REQUESTED: {_R.CANCELLED, _R.ROLLING_BACK},
    _R.ROLLING_BACK: {_R.ROLLED_BACK, _R.FAILED_TERMINAL},
    _R.FAILED_RETRYABLE: {_R.DISCOVERING, _R.SPECIFYING, _R.PLANNING, _R.EXECUTING,
                          _R.VERIFYING, _R.REPAIRING, _R.FAILED_TERMINAL,
                          _R.CANCEL_REQUESTED},
}


def _build_run_transitions() -> dict[RunState, frozenset[RunState]]:
    """Derive the run transition table, pausing included, terminals closed.

    Pause edges are generated from :data:`PAUSABLE_RUN_STATES` in both
    directions so the table cannot drift into a state that can be paused but
    not resumed.
    """

    table: dict[RunState, set[RunState]] = {
        state: set(targets) for state, targets in _BASE_TRANSITIONS.items()
    }
    for state in PAUSABLE_RUN_STATES:
        table.setdefault(state, set()).add(RunState.PAUSED)
    table[RunState.PAUSED] = set(PAUSABLE_RUN_STATES) | {RunState.CANCEL_REQUESTED}
    for state in TERMINAL_RUN_STATES:
        table[state] = set()
    for state in RunState:
        table.setdefault(state, set())
    return {state: frozenset(targets) for state, targets in table.items()}


RUN_TRANSITIONS: Mapping[RunState, frozenset[RunState]] = _build_run_transitions()

_S = StepState

STEP_TRANSITIONS: Mapping[StepState, frozenset[StepState]] = {
    _S.PENDING: frozenset({_S.READY, _S.SKIPPED, _S.CANCELLED, _S.PAUSED}),
    _S.READY: frozenset({_S.RUNNING, _S.PENDING, _S.SKIPPED, _S.CANCELLED, _S.PAUSED}),
    _S.RUNNING: frozenset({_S.SUCCEEDED, _S.PARTIAL, _S.FAILED_RETRYABLE, _S.FAILED_TERMINAL,
                           _S.INTERRUPTED, _S.WAITING_APPROVAL, _S.PAUSED, _S.CANCELLED}),
    _S.WAITING_APPROVAL: frozenset({_S.RUNNING, _S.CANCELLED, _S.FAILED_TERMINAL, _S.PAUSED}),
    _S.PAUSED: frozenset({_S.PENDING, _S.READY, _S.RUNNING, _S.CANCELLED}),
    _S.SUCCEEDED: frozenset({_S.COMPENSATING, _S.PENDING}),
    # No edge to SUCCEEDED: a partial step is re-run from PENDING and earns a
    # new success, or it is compensated.  It is never relabelled.
    _S.PARTIAL: frozenset({_S.PENDING, _S.READY, _S.COMPENSATING, _S.FAILED_TERMINAL}),
    _S.FAILED_RETRYABLE: frozenset({_S.PENDING, _S.READY, _S.FAILED_TERMINAL, _S.CANCELLED}),
    _S.FAILED_TERMINAL: frozenset({_S.PENDING, _S.COMPENSATING}),
    # An interrupted step must be reconciled first; reconciliation moves it to
    # PENDING (effect did not land) or COMPENSATING/PARTIAL (it did).
    _S.INTERRUPTED: frozenset({_S.PENDING, _S.READY, _S.PARTIAL, _S.FAILED_TERMINAL,
                               _S.COMPENSATING}),
    _S.CANCELLED: frozenset({_S.COMPENSATING}),
    _S.COMPENSATING: frozenset({_S.COMPENSATED, _S.FAILED_TERMINAL}),
    _S.COMPENSATED: frozenset({_S.PENDING}),
    _S.SKIPPED: frozenset({_S.PENDING, _S.READY}),
}


def allowed_targets(state: RunState) -> frozenset[RunState]:
    """Return the legal successors of ``state`` (empty for terminal states)."""

    return RUN_TRANSITIONS[state]


def is_terminal(state: RunState) -> bool:
    """True when the run has an answer and must never move again."""

    return state in TERMINAL_RUN_STATES


def transition(current: RunState, target: RunState) -> RunState:
    """Validate a run-level transition and return ``target``.

    Raises ``ILLEGAL_TRANSITION`` rather than returning a boolean so that a
    caller cannot forget to check.  A terminal source is reported as such in
    the error details: "you tried to move a finished run" is a different bug
    from "you took a wrong turn".
    """

    if target not in RUN_TRANSITIONS[current]:
        raise KernelError(
            code="ILLEGAL_TRANSITION",
            message=f"illegal run transition {current} -> {target}",
            retryable=False,
            recommended_action=(
                "the run has already ended; open a new run"
                if is_terminal(current)
                else "route through a legal intermediate state"
            ),
            details={
                "current": str(current),
                "target": str(target),
                "terminal": is_terminal(current),
                "allowed": sorted(str(item) for item in RUN_TRANSITIONS[current]),
            },
        )
    return target


def step_transition(current: StepState, target: StepState) -> StepState:
    """Validate a step-level transition and return ``target``."""

    if target not in STEP_TRANSITIONS[current]:
        raise KernelError(
            code="ILLEGAL_TRANSITION",
            message=f"illegal step transition {current} -> {target}",
            retryable=False,
            recommended_action="route through a legal intermediate step state",
            details={
                "current": str(current),
                "target": str(target),
                "allowed": sorted(str(item) for item in STEP_TRANSITIONS[current]),
            },
        )
    return target


# --- events ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One immutable fact, self-describing and self-chaining.

    ``chain`` is computed over the *previous* chain value and this event's whole
    content, so editing any field of any event invalidates every chain value
    after it.  The event carries its own ``run_id`` rather than inheriting the
    stream's, which is what lets a forked stream hold its parent's events
    verbatim without breaking the audit chain.
    """

    sequence: int
    event_type: EventType
    run_id: str
    step_id: str | None
    occurred_at: str
    body: Mapping[str, Any]
    chain: str

    def content(self) -> dict[str, Any]:
        """The chained content of the event, excluding the chain value itself."""

        return {
            "sequence": self.sequence,
            "eventType": str(self.event_type),
            "runId": self.run_id,
            "stepId": self.step_id,
            "occurredAt": self.occurred_at,
            "body": dict(self.body),
        }

    def to_payload(self) -> dict[str, Any]:
        """The mapping written to the :class:`~.ports.EventStore`."""

        payload = self.content()
        payload["chain"] = self.chain
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RunEvent:
        """Decode a stored payload strictly; an unknown field is a hard error."""

        body = require_mapping(payload, "event")
        reject_unknown_fields(
            body,
            ("sequence", "eventType", "runId", "stepId", "occurredAt", "body", "chain"),
            field_name="event",
        )
        step_id = body.get("stepId")
        return cls(
            sequence=require_int(body.get("sequence"), "event.sequence", minimum=1),
            event_type=_require_event_type(body.get("eventType")),
            run_id=require_identifier(body.get("runId"), "event.runId"),
            step_id=None if step_id is None else require_identifier(step_id, "event.stepId"),
            occurred_at=require_str(body.get("occurredAt"), "event.occurredAt"),
            body=dict(require_mapping(body.get("body") or {}, "event.body")),
            chain=require_str(body.get("chain"), "event.chain"),
        )

    @classmethod
    def from_stored(cls, stored: Any) -> RunEvent:
        """Decode an event as returned by an :class:`~.ports.EventStore`."""

        return cls.from_payload(stored.payload)


def _require_event_type(value: Any) -> EventType:
    text = require_str(value, "event.eventType")
    try:
        return EventType(text)
    except ValueError as exc:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown event type {text!r}",
            recommended_action="upgrade the kernel or drop the foreign event",
        ) from exc


def chain_for(previous_chain: str, event_content: Mapping[str, Any]) -> str:
    """Chain value for an event whose content is ``event_content``."""

    return digest({"previous": previous_chain, "event": dict(event_content)})


def verify_chain(events: Sequence[RunEvent]) -> bool:
    """Recompute the hash chain and compare it to what each event recorded.

    Returns ``False`` for any tampering — an edited payload, a reordered event,
    a deleted event, or a spliced-in one.  It returns a bool rather than raising
    because callers routinely need to *report* corruption, and the raise happens
    one layer up where the failure code carries the evidence ids.
    """

    previous = GENESIS_CHAIN
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence:
            return False
        if chain_for(previous, event.content()) != event.chain:
            return False
        previous = event.chain
        expected_sequence += 1
    return True


# --- workflow definition and DAG --------------------------------------------


@dataclass(frozen=True, slots=True)
class StepDefinition:
    """One node of the workflow DAG.

    ``compensation`` doubles as the reversibility marker: a side-effecting step
    with ``compensation=None`` cannot be undone, and :func:`rollback_plan` must
    say so out loud instead of quietly producing a plan that only looks whole.
    """

    step_id: str
    requires: tuple[str, ...] = ()
    required_capability: str = ""
    inputs_digest: str = ""
    side_effecting: bool = False
    compensation: str | None = None
    max_attempts: int = 1

    def __post_init__(self) -> None:
        require_identifier(self.step_id, "step_id")
        require_int(self.max_attempts, "max_attempts", minimum=1, maximum=1000)
        if self.required_capability:
            require_identifier(self.required_capability, "required_capability")
        if self.compensation is not None:
            require_identifier(self.compensation, "compensation")
        if self.step_id in self.requires:
            raise KernelError(
                code="DAG_CYCLE",
                message=f"step {self.step_id!r} depends on itself",
                recommended_action="remove the self-dependency",
                details={"cycle": [self.step_id, self.step_id]},
            )

    @property
    def reversible(self) -> bool:
        """A step is reversible exactly when it declares a compensation."""

        return self.compensation is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "requires": list(self.requires),
            "requiredCapability": self.required_capability,
            "inputsDigest": self.inputs_digest,
            "sideEffecting": self.side_effecting,
            "compensation": self.compensation,
            "maxAttempts": self.max_attempts,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> StepDefinition:
        body = require_mapping(payload, "step")
        reject_unknown_fields(
            body,
            ("stepId", "requires", "requiredCapability", "inputsDigest", "sideEffecting",
             "compensation", "maxAttempts"),
            field_name="step",
        )
        compensation = body.get("compensation")
        return cls(
            step_id=require_identifier(body.get("stepId"), "step.stepId"),
            requires=require_str_seq(body.get("requires", ()), "step.requires"),
            required_capability=(
                require_identifier(body["requiredCapability"], "step.requiredCapability")
                if body.get("requiredCapability") else ""
            ),
            inputs_digest=require_str(body.get("inputsDigest", "unset"), "step.inputsDigest"),
            side_effecting=require_bool(body.get("sideEffecting", False), "step.sideEffecting"),
            compensation=(
                None if compensation is None
                else require_identifier(compensation, "step.compensation")
            ),
            max_attempts=require_int(body.get("maxAttempts", 1), "step.maxAttempts", minimum=1),
        )


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """A versioned, content-addressed workflow."""

    workflow_id: str
    workflow_version: str
    task_spec_version: str
    steps: tuple[StepDefinition, ...]

    def __post_init__(self) -> None:
        require_identifier(self.workflow_id, "workflow_id")
        require_str(self.workflow_version, "workflow_version")
        require_str(self.task_spec_version, "task_spec_version")
        if not self.steps:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="a workflow definition needs at least one step",
                recommended_action="declare the steps of the workflow",
            )

    def step(self, step_id: str) -> StepDefinition:
        for item in self.steps:
            if item.step_id == step_id:
                return item
        raise KernelError(
            code="UNKNOWN_STEP",
            message=f"step {step_id!r} is not part of workflow {self.workflow_id!r}",
            recommended_action="check the step id against the workflow definition",
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "workflowId": self.workflow_id,
            "workflowVersion": self.workflow_version,
            "taskSpecVersion": self.task_spec_version,
            "steps": [item.to_payload() for item in self.steps],
        }

    @property
    def definition_digest(self) -> str:
        return digest(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, task_spec_version: str
                     ) -> WorkflowDefinition:
        body = require_mapping(payload, "workflow_definition")
        reject_unknown_fields(
            body, ("workflowId", "workflowVersion", "steps"),
            field_name="workflow_definition",
        )
        raw_steps = body.get("steps")
        if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="workflow_definition.steps must be an array",
                recommended_action="supply steps as a JSON array",
            )
        return cls(
            workflow_id=require_identifier(body.get("workflowId"), "workflow.workflowId"),
            workflow_version=require_str(body.get("workflowVersion"), "workflow.workflowVersion"),
            task_spec_version=task_spec_version,
            steps=tuple(StepDefinition.from_payload(item) for item in raw_steps),
        )


@dataclass(frozen=True, slots=True)
class Dag:
    """The validated dependency graph of a workflow."""

    order: tuple[str, ...]
    requires: Mapping[str, tuple[str, ...]]
    dependents: Mapping[str, tuple[str, ...]]
    waves: tuple[tuple[str, ...], ...]
    topological: tuple[str, ...]
    critical_path: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "waves": [list(wave) for wave in self.waves],
            "topological": list(self.topological),
            "criticalPath": list(self.critical_path),
            "criticalPathLength": len(self.critical_path),
        }


def _find_cycle(order: Sequence[str], requires: Mapping[str, tuple[str, ...]]
                ) -> tuple[str, ...] | None:
    """Iterative DFS returning the actual cycle, e.g. ``('a', 'b', 'c', 'a')``.

    Reporting the path rather than the word "cycle" is the difference between a
    two-minute fix and an afternoon in a fifty-node workflow.
    """

    white, grey, black = 0, 1, 2
    colour: dict[str, int] = dict.fromkeys(order, white)
    for root in order:
        if colour[root] != white:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        path: list[str] = []
        while stack:
            node, index = stack.pop()
            if index == 0:
                if colour[node] == black:
                    continue
                colour[node] = grey
                path.append(node)
            deps = requires[node]
            if index < len(deps):
                stack.append((node, index + 1))
                dependency = deps[index]
                if colour[dependency] == grey:
                    start = path.index(dependency)
                    return tuple(path[start:]) + (dependency,)
                if colour[dependency] == white:
                    stack.append((dependency, 0))
            else:
                colour[node] = black
                path.pop()
    return None


def build_dag(steps: Sequence[StepDefinition]) -> Dag:
    """Validate the graph and precompute waves, topological order, critical path.

    Rejects duplicate ids, dangling dependencies and cycles.  Every derived
    ordering is deterministic (definition order for waves' membership, sorted
    within a wave) so that two planners agree byte for byte.
    """

    order: list[str] = []
    requires: dict[str, tuple[str, ...]] = {}
    for definition in steps:
        if definition.step_id in requires:
            raise KernelError(
                code="DUPLICATE_STEP",
                message=f"step {definition.step_id!r} is declared twice",
                recommended_action="give every step a unique id",
                details={"stepId": definition.step_id},
            )
        order.append(definition.step_id)
        requires[definition.step_id] = tuple(definition.requires)

    known = set(order)
    for step_id, deps in requires.items():
        unknown = sorted(set(deps) - known)
        if unknown:
            raise KernelError(
                code="UNKNOWN_STEP",
                message=f"step {step_id!r} depends on undeclared steps {unknown}",
                recommended_action="declare the dependency or remove the edge",
                details={"stepId": step_id, "unknown": unknown},
            )

    cycle = _find_cycle(order, requires)
    if cycle is not None:
        raise KernelError(
            code="DAG_CYCLE",
            message="workflow graph contains a cycle: " + " -> ".join(cycle),
            recommended_action="break the cycle by removing one dependency edge",
            details={"cycle": list(cycle)},
        )

    dependents: dict[str, list[str]] = {step_id: [] for step_id in order}
    for step_id, deps in requires.items():
        for dependency in deps:
            dependents[dependency].append(step_id)

    remaining = dict(requires)
    done: set[str] = set()
    waves: list[tuple[str, ...]] = []
    while remaining:
        wave = tuple(sorted(
            step_id for step_id, deps in remaining.items() if set(deps) <= done
        ))
        if not wave:  # pragma: no cover - cycle detection already ran
            raise KernelError(
                code="DAG_CYCLE",
                message="workflow graph cannot be layered",
                recommended_action="break the cycle",
                details={"remaining": sorted(remaining)},
            )
        waves.append(wave)
        done.update(wave)
        for step_id in wave:
            del remaining[step_id]

    topological = tuple(step_id for wave in waves for step_id in wave)

    length: dict[str, int] = {}
    chain: dict[str, tuple[str, ...]] = {}
    for step_id in topological:
        best_length = 0
        best_chain: tuple[str, ...] = ()
        for dependency in sorted(requires[step_id]):
            candidate = (length[dependency], chain[dependency])
            if candidate[0] > best_length or (
                candidate[0] == best_length and best_length > 0 and candidate[1] < best_chain
            ):
                best_length, best_chain = candidate
        length[step_id] = best_length + 1
        chain[step_id] = best_chain + (step_id,)
    critical = max(topological, key=lambda item: (length[item], tuple(-ord(c) for c in item)))
    best_len = max(length.values())
    critical_candidates = sorted(chain[item] for item in topological if length[item] == best_len)
    critical_path = critical_candidates[0] if critical_candidates else chain[critical]

    return Dag(
        order=tuple(order),
        requires={key: tuple(value) for key, value in sorted(requires.items())},
        dependents={key: tuple(sorted(value)) for key, value in sorted(dependents.items())},
        waves=tuple(waves),
        topological=topological,
        critical_path=critical_path,
    )


# --- budget ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Budget:
    """Integer-only spend limits plus the mandatory turn ceiling.

    Every quantity is an integer of the smallest unit (micro-dollars, tokens,
    milliseconds).  There are no floats anywhere near a budget: two workers must
    reach the same verdict about "is this run over budget?".
    """

    limits: Mapping[str, int] = field(default_factory=dict)
    max_turns: int = 1

    def __post_init__(self) -> None:
        require_int(self.max_turns, "budget.maxTurns", minimum=1)
        for meter, limit in self.limits.items():
            require_identifier(meter, "budget.limits key")
            require_int(limit, f"budget.limits.{meter}", minimum=0)

    def to_payload(self) -> dict[str, Any]:
        return {"limits": dict(sorted(self.limits.items())), "maxTurns": self.max_turns}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Budget:
        body = require_mapping(payload, "budget")
        reject_unknown_fields(body, ("limits", "maxTurns"), field_name="budget")
        if "maxTurns" not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="budget.maxTurns is required; an unbounded run is not durable",
                recommended_action="declare budget.maxTurns",
            )
        raw_limits = require_mapping(body.get("limits", {}), "budget.limits")
        return cls(
            limits={
                require_identifier(meter, "budget.limits key"):
                    require_int(limit, f"budget.limits.{meter}", minimum=0)
                for meter, limit in raw_limits.items()
            },
            max_turns=require_int(body.get("maxTurns"), "budget.maxTurns", minimum=1),
        )


def budget_report(budget: Budget, spent: Mapping[str, int]) -> dict[str, Any]:
    """Report each meter with an explicit ``measured`` flag.

    A meter with a limit but no recorded consumption is reported as *unmeasured*
    with ``spent: null``, never as ``spent: 0``.  "Nobody has told us" and "it
    cost nothing" are different facts, and conflating them is how a run silently
    burns a budget nobody was watching.  To record a true zero, emit a
    ``BUDGET_CONSUMED`` event with amount 0.
    """

    meters: dict[str, Any] = {}
    for meter in sorted(set(budget.limits) | set(spent)):
        limit = budget.limits.get(meter)
        measured = meter in spent
        used = spent.get(meter)
        remaining = None if (limit is None or not measured) else limit - used
        meters[meter] = {
            "limit": limit,
            "spent": used,
            "measured": measured,
            "remaining": remaining,
            "exhausted": bool(limit is not None and measured and used >= limit),
        }
    return {"maxTurns": budget.max_turns, "meters": meters}


# --- materialised view -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SideEffectIntent:
    """A declared intent to change the outside world.

    ``observed`` is only ever set by a ``SIDE_EFFECT_OBSERVED`` event written by
    the executor that saw the effect land, or by an explicit
    ``SIDE_EFFECT_RECONCILED`` verdict.  Nothing infers it.
    """

    key: str
    step_id: str
    attempt: int
    intent_sequence: int
    observed: bool = False
    observation_digest: str | None = None
    reconciled: bool = False
    reconciliation_verdict: str | None = None

    @property
    def unresolved(self) -> bool:
        return not self.observed and not self.reconciled

    def to_payload(self) -> dict[str, Any]:
        return {
            "idempotencyKey": self.key,
            "stepId": self.step_id,
            "attempt": self.attempt,
            "intentSequence": self.intent_sequence,
            "observed": self.observed,
            "observationDigest": self.observation_digest,
            "reconciled": self.reconciled,
            "reconciliationVerdict": self.reconciliation_verdict,
            "unresolved": self.unresolved,
        }


@dataclass(frozen=True, slots=True)
class StepView:
    """Materialised step: its definition plus its runtime state."""

    step_id: str
    requires: tuple[str, ...]
    required_capability: str
    inputs_digest: str
    side_effecting: bool
    compensation: str | None
    max_attempts: int
    state: StepState = StepState.PENDING
    attempts: int = 0
    completed_sequence: int | None = None
    last_error_code: str | None = None
    outputs_digest: str | None = None

    @property
    def reversible(self) -> bool:
        return self.compensation is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "requires": list(self.requires),
            "requiredCapability": self.required_capability,
            "inputsDigest": self.inputs_digest,
            "sideEffecting": self.side_effecting,
            "compensation": self.compensation,
            "maxAttempts": self.max_attempts,
            "state": str(self.state),
            "attemptNo": self.attempts,
            "completedSequence": self.completed_sequence,
            "lastErrorCode": self.last_error_code,
            "outputsDigest": self.outputs_digest,
        }


_COUNTER_KEYS = (
    "budgetEvents",
    "checkpoints",
    "compensationsApplied",
    "forks",
    "reconciliations",
    "requirementUpdates",
    "retriesScheduled",
    "runTransitions",
    "safePoints",
    "sideEffectIntents",
    "sideEffectObservations",
    "stepTransitions",
)


@dataclass(frozen=True, slots=True)
class RunView:
    """The materialised state of a run — a *cache* of the log, never the truth.

    Every field here is derivable from the event stream by :func:`replay`; if it
    is not, it does not belong in this class.  That rule is what makes crash
    recovery a replay rather than a reconciliation of two half-written stores.
    """

    run_id: str
    state: RunState
    workflow_id: str
    workflow_version: str
    task_spec_version: str
    definition_digest: str
    steps: Mapping[str, StepView] = field(default_factory=dict)
    counters: Mapping[str, int] = field(default_factory=dict)
    budget_spent: Mapping[str, int] = field(default_factory=dict)
    max_turns: int = 1
    turns_used: int = 0
    checkpoint_id: str | None = None
    sequence: int = 0
    intents: Mapping[str, SideEffectIntent] = field(default_factory=dict)
    paused_from: RunState | None = None
    cancel_requested: bool = False
    parent_run_id: str | None = None
    parent_sequence: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "state": str(self.state),
            "workflowId": self.workflow_id,
            "workflowVersion": self.workflow_version,
            "taskSpecVersion": self.task_spec_version,
            "definitionDigest": self.definition_digest,
            "steps": {key: value.to_payload() for key, value in sorted(self.steps.items())},
            "counters": dict(sorted(self.counters.items())),
            "budgetSpent": dict(sorted(self.budget_spent.items())),
            "maxTurns": self.max_turns,
            "turnsUsed": self.turns_used,
            "checkpointId": self.checkpoint_id,
            "sequence": self.sequence,
            "intents": {
                key: value.to_payload() for key, value in sorted(self.intents.items())
            },
            "pausedFrom": None if self.paused_from is None else str(self.paused_from),
            "cancelRequested": self.cancel_requested,
            "parentRunId": self.parent_run_id,
            "parentSequence": self.parent_sequence,
        }


def view_digest(view: RunView) -> str:
    """Content address of a materialised view."""

    return digest(view.to_payload())


def _bump(counters: Mapping[str, int], key: str, amount: int = 1) -> dict[str, int]:
    updated = dict(counters)
    updated[key] = updated.get(key, 0) + amount
    return updated


def _create_view(event: RunEvent) -> RunView:
    body = event.body
    steps: dict[str, StepView] = {}
    for raw in body.get("steps", ()):
        definition = StepDefinition.from_payload(raw)
        steps[definition.step_id] = StepView(
            step_id=definition.step_id,
            requires=definition.requires,
            required_capability=definition.required_capability,
            inputs_digest=definition.inputs_digest,
            side_effecting=definition.side_effecting,
            compensation=definition.compensation,
            max_attempts=definition.max_attempts,
        )
    return RunView(
        run_id=event.run_id,
        state=RunState.CREATED,
        workflow_id=require_str(body.get("workflowId"), "RUN_CREATED.workflowId"),
        workflow_version=require_str(body.get("workflowVersion"), "RUN_CREATED.workflowVersion"),
        task_spec_version=require_str(body.get("taskSpecVersion"), "RUN_CREATED.taskSpecVersion"),
        definition_digest=require_str(body.get("definitionDigest"),
                                      "RUN_CREATED.definitionDigest"),
        steps=steps,
        counters=dict.fromkeys(_COUNTER_KEYS, 0),
        budget_spent={},
        max_turns=require_int(body.get("maxTurns", 1), "RUN_CREATED.maxTurns", minimum=1),
        sequence=event.sequence,
    )


def _inconsistent(message: str, **details: Any) -> KernelError:
    return KernelError(
        code="ORCHESTRATOR_INCONSISTENT",
        message=message,
        retryable=False,
        recommended_action="treat the stream as corrupt; do not materialise it",
        details=details,
    )


def _apply_run_state(view: RunView, event: RunEvent) -> RunView:
    target = RunState(require_str(event.body.get("to"), "RUN_STATE_CHANGED.to"))
    if view.state is RunState.PAUSED and target is not RunState.CANCEL_REQUESTED:
        if view.paused_from is None:
            raise KernelError(
                code="PAUSE_ORIGIN_MISSING",
                message=f"run {view.run_id!r} is PAUSED without a recorded origin",
                recommended_action="never infer the pre-pause state; repair the log",
            )
        if target is not view.paused_from:
            raise _inconsistent(
                f"resume must restore {view.paused_from}, not {target}",
                pausedFrom=str(view.paused_from), attempted=str(target),
            )
    transition(view.state, target)
    paused_from = view.paused_from
    if target is RunState.PAUSED:
        raw_origin = event.body.get("pausedFrom")
        if raw_origin is None:
            raise KernelError(
                code="PAUSE_ORIGIN_MISSING",
                message="a PAUSED transition must record the state it paused from",
                recommended_action="write pausedFrom into the event; do not guess on resume",
            )
        origin = RunState(require_str(raw_origin, "RUN_STATE_CHANGED.pausedFrom"))
        if origin is not view.state:
            raise _inconsistent(
                "pausedFrom does not match the state actually being left",
                recorded=str(origin), actual=str(view.state),
            )
        paused_from = origin
    elif view.state is RunState.PAUSED:
        paused_from = None
    return replace(
        view,
        state=target,
        paused_from=paused_from,
        cancel_requested=view.cancel_requested or target is RunState.CANCEL_REQUESTED,
        counters=_bump(view.counters, "runTransitions"),
    )


def _apply_step_state(view: RunView, event: RunEvent) -> RunView:
    step_id = event.step_id
    if step_id is None or step_id not in view.steps:
        raise KernelError(
            code="UNKNOWN_STEP",
            message=f"STEP_STATE_CHANGED names unknown step {step_id!r}",
            recommended_action="check the workflow definition in RUN_CREATED",
        )
    current = view.steps[step_id]
    target = StepState(require_str(event.body.get("to"), "STEP_STATE_CHANGED.to"))
    step_transition(current.state, target)
    attempts = current.attempts
    if target is StepState.RUNNING:
        attempts += 1
        if attempts > current.max_attempts:
            raise KernelError(
                code="ATTEMPTS_EXHAUSTED",
                message=(
                    f"step {step_id!r} started attempt {attempts} of at most "
                    f"{current.max_attempts}"
                ),
                retryable=False,
                recommended_action="fail the step terminally instead of retrying again",
                details={"stepId": step_id, "maxAttempts": current.max_attempts},
            )
    completed = current.completed_sequence
    if target in _COMPLETED_STEP_STATES:
        completed = event.sequence
    error_code = event.body.get("errorCode")
    steps = dict(view.steps)
    steps[step_id] = replace(
        current,
        state=target,
        attempts=attempts,
        completed_sequence=completed,
        last_error_code=None if error_code is None else require_str(error_code, "errorCode"),
        outputs_digest=event.body.get("outputsDigest", current.outputs_digest),
    )
    turns = view.turns_used + (1 if target is StepState.RUNNING else 0)
    return replace(
        view, steps=steps, turns_used=turns,
        counters=_bump(view.counters, "stepTransitions"),
    )


_COMPLETED_STEP_STATES = frozenset(
    {StepState.SUCCEEDED, StepState.PARTIAL, StepState.FAILED_TERMINAL,
     StepState.FAILED_RETRYABLE, StepState.INTERRUPTED, StepState.CANCELLED}
)


def _apply_intent(view: RunView, event: RunEvent) -> RunView:
    key = require_str(event.body.get("idempotencyKey"), "SIDE_EFFECT_INTENDED.idempotencyKey")
    step_id = event.step_id or ""
    if key in view.intents and view.intents[key].unresolved:
        # Re-announcing an unresolved intent is legal (the executor restarted);
        # creating a *second* intent for the same key is not.
        return replace(view, counters=_bump(view.counters, "sideEffectIntents"))
    intents = dict(view.intents)
    intents[key] = SideEffectIntent(
        key=key,
        step_id=step_id,
        attempt=require_int(event.body.get("attempt", 1), "attempt", minimum=1),
        intent_sequence=event.sequence,
    )
    return replace(view, intents=intents,
                   counters=_bump(view.counters, "sideEffectIntents"))


def _apply_observation(view: RunView, event: RunEvent) -> RunView:
    key = require_str(event.body.get("idempotencyKey"), "SIDE_EFFECT_OBSERVED.idempotencyKey")
    intent = view.intents.get(key)
    if intent is None:
        raise _inconsistent(
            "a side effect was observed that was never intended", idempotencyKey=key,
        )
    intents = dict(view.intents)
    intents[key] = replace(
        intent, observed=True,
        observation_digest=event.body.get("observationDigest"),
    )
    return replace(view, intents=intents,
                   counters=_bump(view.counters, "sideEffectObservations"))


def _apply_reconciliation(view: RunView, event: RunEvent) -> RunView:
    key = require_str(event.body.get("idempotencyKey"), "SIDE_EFFECT_RECONCILED.idempotencyKey")
    intent = view.intents.get(key)
    if intent is None:
        raise _inconsistent(
            "a side effect was reconciled that was never intended", idempotencyKey=key,
        )
    verdict = require_str(event.body.get("verdict"), "SIDE_EFFECT_RECONCILED.verdict")
    if verdict not in {"LANDED", "DID_NOT_LAND"}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"reconciliation verdict must be LANDED or DID_NOT_LAND, got {verdict!r}",
            recommended_action="probe the external system and record what it says",
        )
    intents = dict(view.intents)
    intents[key] = replace(
        intent,
        observed=verdict == "LANDED",
        reconciled=True,
        reconciliation_verdict=verdict,
        observation_digest=event.body.get("evidenceDigest", intent.observation_digest),
    )
    return replace(view, intents=intents,
                   counters=_bump(view.counters, "reconciliations"))


def _apply_budget(view: RunView, event: RunEvent) -> RunView:
    meter = require_identifier(event.body.get("meter"), "BUDGET_CONSUMED.meter")
    amount = require_int(event.body.get("amount"), "BUDGET_CONSUMED.amount", minimum=0)
    spent = dict(view.budget_spent)
    spent[meter] = spent.get(meter, 0) + amount
    return replace(view, budget_spent=spent, counters=_bump(view.counters, "budgetEvents"))


def _apply_requirement_update(view: RunView, event: RunEvent) -> RunView:
    steps: dict[str, StepView] = {}
    invalidated = set(require_str_seq(event.body.get("invalidated", ()), "invalidated"))
    for raw in event.body.get("steps", ()):
        definition = StepDefinition.from_payload(raw)
        previous = view.steps.get(definition.step_id)
        state = StepState.PENDING
        attempts = 0
        completed = None
        outputs = None
        if previous is not None and definition.step_id not in invalidated:
            state, attempts = previous.state, previous.attempts
            completed, outputs = previous.completed_sequence, previous.outputs_digest
        steps[definition.step_id] = StepView(
            step_id=definition.step_id,
            requires=definition.requires,
            required_capability=definition.required_capability,
            inputs_digest=definition.inputs_digest,
            side_effecting=definition.side_effecting,
            compensation=definition.compensation,
            max_attempts=definition.max_attempts,
            state=state,
            attempts=attempts,
            completed_sequence=completed,
            outputs_digest=outputs,
        )
    return replace(
        view,
        steps=steps,
        task_spec_version=require_str(event.body.get("taskSpecVersion"), "taskSpecVersion"),
        definition_digest=require_str(event.body.get("definitionDigest"), "definitionDigest"),
        counters=_bump(view.counters, "requirementUpdates"),
    )


def _apply_fork(view: RunView, event: RunEvent) -> RunView:
    """Rebind the stream to a new run identity with its own budget.

    The fork inherits state and step outcomes but not spend: invariant I3 of the
    time-travel contract requires an independent budget and lease, so the
    fork's meters start at a *measured* zero for exactly the meters the parent
    was tracking, and the parent's totals are preserved in the event body for
    audit rather than carried forward as debt.
    """

    new_run_id = require_identifier(event.body.get("newRunId"), "FORK.newRunId")
    parent_run_id = require_identifier(event.body.get("parentRunId"), "FORK.parentRunId")
    parent_sequence = require_int(event.body.get("parentSequence"), "FORK.parentSequence",
                                  minimum=1)
    return replace(
        view,
        run_id=new_run_id,
        parent_run_id=parent_run_id,
        parent_sequence=parent_sequence,
        budget_spent=dict.fromkeys(sorted(view.budget_spent), 0),
        checkpoint_id=None,
        counters=_bump(view.counters, "forks"),
    )


def _apply(view: RunView, event: RunEvent) -> RunView:
    """Fold one event into the materialised view.

    Every legality rule lives here rather than in the writer, so a hand-edited
    or replayed log is held to the same standard as a live run.
    """

    if event.sequence != view.sequence + 1:
        raise KernelError(
            code="HISTORY_GAP",
            message=(
                f"event sequence {event.sequence} does not follow {view.sequence} "
                f"on run {view.run_id!r}"
            ),
            recommended_action="fetch the missing events before materialising",
            details={"expected": view.sequence + 1, "found": event.sequence},
        )
    kind = event.event_type
    if kind is EventType.RUN_CREATED:
        raise _inconsistent("RUN_CREATED may only be the first event of a stream")
    if kind is EventType.RUN_STATE_CHANGED:
        updated = _apply_run_state(view, event)
    elif kind is EventType.STEP_STATE_CHANGED:
        updated = _apply_step_state(view, event)
    elif kind is EventType.SIDE_EFFECT_INTENDED:
        updated = _apply_intent(view, event)
    elif kind is EventType.SIDE_EFFECT_OBSERVED:
        updated = _apply_observation(view, event)
    elif kind is EventType.SIDE_EFFECT_RECONCILED:
        updated = _apply_reconciliation(view, event)
    elif kind is EventType.CHECKPOINT_WRITTEN:
        updated = replace(
            view,
            checkpoint_id=require_str(event.body.get("checkpointId"), "checkpointId"),
            counters=_bump(view.counters, "checkpoints"),
        )
    elif kind is EventType.BUDGET_CONSUMED:
        updated = _apply_budget(view, event)
    elif kind is EventType.SAFE_POINT_REACHED:
        updated = replace(view, counters=_bump(view.counters, "safePoints"))
    elif kind is EventType.REQUIREMENT_UPDATED:
        updated = _apply_requirement_update(view, event)
    elif kind is EventType.RETRY_SCHEDULED:
        updated = replace(view, counters=_bump(view.counters, "retriesScheduled"))
    elif kind is EventType.COMPENSATION_APPLIED:
        updated = replace(view, counters=_bump(view.counters, "compensationsApplied"))
    elif kind is EventType.FORK:
        updated = _apply_fork(view, event)
    else:  # pragma: no cover - EventType is closed
        raise _inconsistent(f"unhandled event type {kind}")
    return replace(updated, sequence=event.sequence)


def replay(events: Sequence[RunEvent]) -> RunView:
    """Rebuild the materialised view from the log alone.

    This is the only supported recovery path.  It verifies the hash chain first:
    materialising a tampered log would produce a state that looks authoritative
    and is not.
    """

    if not events:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="cannot replay an empty event stream",
            recommended_action="supply the run's events",
        )
    if not verify_chain(events):
        raise KernelError(
            code="EVENT_CHAIN_BROKEN",
            message="event hash chain does not verify; the stream has been altered",
            retryable=False,
            recommended_action="restore the stream from backup; do not materialise it",
        )
    first = events[0]
    if first.event_type is not EventType.RUN_CREATED:
        raise _inconsistent(
            f"a run stream must open with RUN_CREATED, found {first.event_type}",
        )
    view = _create_view(first)
    for event in events[1:]:
        view = _apply(view, event)
    return view


# --- readiness, idempotency, reconciliation ----------------------------------


def next_ready_steps(view: RunView) -> tuple[str, ...]:
    """Steps whose dependencies have all genuinely SUCCEEDED.

    ``PARTIAL`` does not satisfy a dependency, and neither does ``INTERRUPTED``
    or ``SKIPPED``.  A downstream step that consumes the output of a half-done
    step would be building on sand, and the resulting run would look successful.
    A run that is paused, cancelling or terminal has no ready steps at all.
    """

    if view.state is RunState.PAUSED or view.cancel_requested or is_terminal(view.state):
        return ()
    ready: list[str] = []
    for step_id, step in sorted(view.steps.items()):
        if step.state not in {StepState.PENDING, StepState.READY}:
            continue
        if all(
            view.steps[dependency].state is StepState.SUCCEEDED
            for dependency in step.requires
        ):
            ready.append(step_id)
    return tuple(ready)


def idempotency_key(run_id: str, step_id: str, inputs_digest: str) -> str:
    """Deterministic key identifying one side effect, invariant across attempts.

    The attempt number is deliberately *excluded*: attempt 2 of a step must
    present the same key as attempt 1 so the downstream system recognises the
    retry as a duplicate rather than performing the effect twice.
    """

    return digest({
        "kind": "side-effect",
        "runId": require_identifier(run_id, "run_id"),
        "stepId": require_identifier(step_id, "step_id"),
        "inputsDigest": require_str(inputs_digest, "inputs_digest"),
    })


@dataclass(frozen=True, slots=True)
class ReconciliationTask:
    """One outside-world question the run cannot answer by itself."""

    idempotency_key: str
    step_id: str
    intent_sequence: int
    attempt: int
    probe: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "idempotencyKey": self.idempotency_key,
            "stepId": self.step_id,
            "intentSequence": self.intent_sequence,
            "attempt": self.attempt,
            "probe": self.probe,
            "resolutionRequired": True,
        }


def unresolved_intents(view: RunView) -> tuple[SideEffectIntent, ...]:
    """Intents with no observation and no reconciliation verdict."""

    return tuple(
        intent for _, intent in sorted(view.intents.items()) if intent.unresolved
    )


def reconciliation_plan(view: RunView) -> tuple[ReconciliationTask, ...]:
    """Turn every unresolved side effect into an explicit question.

    A run that crashed after announcing an effect is in exactly one of two
    worlds and cannot tell which from the inside.  Retrying would risk doing the
    work twice; assuming success would risk claiming work that never happened.
    The only correct move is to ask, keyed by the idempotency key so the answer
    is checkable.
    """

    return tuple(
        ReconciliationTask(
            idempotency_key=intent.key,
            step_id=intent.step_id,
            intent_sequence=intent.intent_sequence,
            attempt=intent.attempt,
            probe=(
                f"query the target system for idempotency key {intent.key} produced by step "
                f"{intent.step_id!r}; record LANDED or DID_NOT_LAND"
            ),
        )
        for intent in unresolved_intents(view)
    )


# --- checkpoints and rollback ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A content-addressed snapshot of the materialised state."""

    checkpoint_id: str
    run_id: str
    sequence: int
    side_effect_cursor: int
    state_snapshot: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "checkpointId": self.checkpoint_id,
            "runId": self.run_id,
            "sequenceNo": self.sequence,
            "sideEffectCursor": self.side_effect_cursor,
            "stateSnapshot": dict(self.state_snapshot),
        }


def checkpoint(view: RunView) -> Checkpoint:
    """Snapshot ``view``; the id *is* the digest of the snapshot.

    Content addressing means two checkpoints of identical state collapse to one
    id, and a checkpoint that has been edited no longer matches its own id.
    """

    snapshot = view.to_payload()
    cursor = max(
        (intent.intent_sequence for intent in view.intents.values()), default=0
    )
    return Checkpoint(
        checkpoint_id=digest(snapshot),
        run_id=view.run_id,
        sequence=view.sequence,
        side_effect_cursor=cursor,
        state_snapshot=snapshot,
    )


@dataclass(frozen=True, slots=True)
class CompensationEntry:
    """One undo action, ordered."""

    order: int
    step_id: str
    compensation: str
    certainty: str
    idempotency_keys: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "stepId": self.step_id,
            "compensation": self.compensation,
            "certainty": self.certainty,
            "idempotencyKeys": list(self.idempotency_keys),
        }


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """A compensation plan and an honest statement of what it cannot undo."""

    run_id: str
    entries: tuple[CompensationEntry, ...]
    irreversible: tuple[str, ...]
    unresolved: tuple[str, ...]
    complete: bool
    plan_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "entries": [entry.to_payload() for entry in self.entries],
            "irreversible": list(self.irreversible),
            "unresolved": list(self.unresolved),
            "complete": self.complete,
            "planDigest": self.plan_digest,
        }

    def require_complete(self) -> None:
        """Raise unless the plan can actually restore the world.

        Called by the release gate.  A plan that silently omits an irreversible
        effect is worse than no plan: it buys confidence that is not there.
        """

        if not self.complete:
            raise KernelError(
                code="ROLLBACK_INCOMPLETE",
                message=(
                    f"rollback for run {self.run_id!r} cannot be completed: "
                    f"irreversible={list(self.irreversible)} "
                    f"unresolved={list(self.unresolved)}"
                ),
                retryable=False,
                recommended_action="escalate to a human; do not present this as a rollback",
                details={
                    "irreversible": list(self.irreversible),
                    "unresolved": list(self.unresolved),
                },
            )


def rollback_plan(view: RunView) -> RollbackPlan:
    """Walk completed side-effecting steps in reverse and emit compensations.

    Reverse *completion* order, not definition order: undoing must unwind the
    world in the order it was wound.  A completed side-effecting step without a
    compensation is irreversible; it is listed by name and the plan is marked
    incomplete.  A step with an unresolved intent also blocks completeness — you
    cannot compensate an effect whose existence is unknown.
    """

    completed = [
        step for step in view.steps.values()
        if step.side_effecting and step.completed_sequence is not None
        and step.state in {StepState.SUCCEEDED, StepState.PARTIAL, StepState.INTERRUPTED,
                           StepState.FAILED_TERMINAL, StepState.FAILED_RETRYABLE,
                           StepState.CANCELLED}
    ]
    touched = {
        intent.step_id for intent in view.intents.values()
        if intent.observed or intent.unresolved
    }
    completed = [step for step in completed if step.step_id in touched or step.state in {
        StepState.SUCCEEDED, StepState.PARTIAL}]

    # The crash this whole module exists for: the process died between announcing
    # an effect and observing it, so the step has an unresolved intent and NO
    # completion record.  Requiring completed_sequence dropped exactly that step
    # from the plan, and the plan then reported complete=True — telling a release
    # gate it was safe to proceed over an effect that may well have landed in the
    # outside world.  An unresolved intent puts its step in the plan regardless of
    # whether the step ever finished.
    unresolved_step_ids = {
        intent.step_id for intent in view.intents.values() if intent.unresolved
    }
    known = {step.step_id for step in completed}
    for step_id in sorted(unresolved_step_ids - known):
        step = view.steps.get(step_id)
        if step is not None and step.side_effecting:
            completed.append(step)

    def _unwind_key(step: StepView) -> tuple[int, str]:
        # Unwind in reverse completion order; a step that never completed is
        # ordered by the sequence at which it announced its effect, which is the
        # only position in the timeline it can honestly claim.
        if step.completed_sequence is not None:
            return (-step.completed_sequence, step.step_id)
        announced = [
            intent.intent_sequence for intent in view.intents.values()
            if intent.step_id == step.step_id
        ]
        return (-max(announced) if announced else 0, step.step_id)

    completed.sort(key=_unwind_key)

    entries: list[CompensationEntry] = []
    irreversible: list[str] = []
    unresolved: list[str] = []
    order = 0
    for step in completed:
        keys = tuple(sorted(
            intent.key for intent in view.intents.values() if intent.step_id == step.step_id
        ))
        step_unresolved = any(
            intent.unresolved for intent in view.intents.values()
            if intent.step_id == step.step_id
        )
        if step_unresolved:
            unresolved.append(step.step_id)
        if step.compensation is None:
            irreversible.append(step.step_id)
            continue
        order += 1
        entries.append(CompensationEntry(
            order=order,
            step_id=step.step_id,
            compensation=step.compensation,
            certainty="unresolved" if step_unresolved else "observed",
            idempotency_keys=keys,
        ))

    payload = {
        "runId": view.run_id,
        "entries": [entry.to_payload() for entry in entries],
        "irreversible": sorted(irreversible),
        "unresolved": sorted(unresolved),
    }
    return RollbackPlan(
        run_id=view.run_id,
        entries=tuple(entries),
        irreversible=tuple(sorted(irreversible)),
        unresolved=tuple(sorted(unresolved)),
        complete=not irreversible and not unresolved,
        plan_digest=digest(payload),
    )


# --- safe points and requirement updates ------------------------------------


@dataclass(frozen=True, slots=True)
class SafePoint:
    """The declared boundary at which a cancellation may take effect."""

    sequence: int
    safe: bool
    reasons: tuple[str, ...]
    cancel_effective: bool
    resulting_state: RunState

    def to_payload(self) -> dict[str, Any]:
        return {
            "sequenceNo": self.sequence,
            "safe": self.safe,
            "reasons": list(self.reasons),
            "cancelEffective": self.cancel_effective,
            "state": str(self.resulting_state),
        }


def is_safe_point(view: RunView) -> tuple[bool, tuple[str, ...]]:
    """Is the run at a boundary where stopping abandons nothing?

    Unsafe while any step is RUNNING or COMPENSATING, or while any side effect
    is unresolved.  Cancelling mid-step is precisely how a half-applied side
    effect is orphaned with nobody left to compensate it.
    """

    reasons: list[str] = []
    running = sorted(
        step.step_id for step in view.steps.values()
        if step.state in {StepState.RUNNING, StepState.COMPENSATING}
    )
    if running:
        reasons.append("steps in flight: " + ",".join(running))
    pending = unresolved_intents(view)
    if pending:
        reasons.append(
            "unresolved side effects: " + ",".join(intent.key for intent in pending)
        )
    return (not reasons), tuple(reasons)


def steps_to_rerun(old_view: RunView, new_definition: WorkflowDefinition) -> tuple[str, ...]:
    """Which steps a requirement update invalidates.

    A step is rerun when its own contract changed (inputs digest, dependencies,
    required capability) or when something it depends on is being rerun.  A step
    whose inputs are byte-identical and whose ancestors are untouched keeps its
    result: re-running it would burn budget to reproduce a value we already hold
    and can prove is the same.  Steps that only *disappeared* are not rerun.
    """

    new_steps = {item.step_id: item for item in new_definition.steps}
    changed: set[str] = set()
    for step_id, definition in new_steps.items():
        previous = old_view.steps.get(step_id)
        if previous is None:
            changed.add(step_id)
            continue
        if (
            previous.inputs_digest != definition.inputs_digest
            or previous.requires != definition.requires
            or previous.required_capability != definition.required_capability
            or previous.side_effecting != definition.side_effecting
        ):
            changed.add(step_id)

    dependents: dict[str, list[str]] = {step_id: [] for step_id in new_steps}
    for step_id, definition in new_steps.items():
        for dependency in definition.requires:
            if dependency in dependents:
                dependents[dependency].append(step_id)

    frontier = sorted(changed)
    while frontier:
        current = frontier.pop()
        for dependent in dependents.get(current, ()):
            if dependent not in changed:
                changed.add(dependent)
                frontier.append(dependent)
    return tuple(sorted(changed))


# --- retry classification ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Integer-only backoff parameters.

    Milliseconds, not seconds-as-float: a backoff that differs by a rounding
    step between two workers turns a thundering herd into a reproducibility bug
    nobody can bisect.
    """

    base_ms: int = 200
    multiplier: int = 2
    max_ms: int = 60_000
    jitter_pct: int = 20
    resource_floor_ms: int = 5_000
    max_exponent: int = 16

    def __post_init__(self) -> None:
        require_int(self.base_ms, "base_ms", minimum=1)
        require_int(self.multiplier, "multiplier", minimum=1, maximum=16)
        require_int(self.max_ms, "max_ms", minimum=1)
        require_int(self.jitter_pct, "jitter_pct", minimum=0, maximum=100)
        require_int(self.resource_floor_ms, "resource_floor_ms", minimum=0)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """The verdict of the retry controller.

    ``backoff_ms`` is ``None`` when there is no retry.  It is *not* 0: zero is a
    legal backoff ("retry immediately") and must not be how "never" is spelled.
    """

    step_id: str
    attempt: int
    retry_class: RetryClass
    should_retry: bool
    backoff_ms: int | None
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "attemptNo": self.attempt,
            "retryClass": str(self.retry_class),
            "shouldRetry": self.should_retry,
            "backoffMs": self.backoff_ms,
            "reason": self.reason,
        }


_RESOURCE_CODES = frozenset({"BUDGET_EXHAUSTED", "RESOURCE_EXHAUSTED", "MAX_TURNS_EXCEEDED",
                             "INPUT_TOO_LARGE"})
_RETRYABLE_CATEGORIES = frozenset({Category.CONCURRENCY, Category.PROVIDER})


def classify_failure(error: KernelError) -> RetryClass:
    """Sort a failure into the four classes the controller understands.

    ``INTERRUPTED`` outranks everything, including ``retryable``: an interrupted
    attempt has an unknown outcome, and retrying an unknown outcome is exactly
    the duplicate-side-effect bug this module exists to prevent.
    """

    if error.interrupted:
        return RetryClass.INTERRUPTED
    if error.code in _RESOURCE_CODES or error.category is Category.RESOURCE:
        return RetryClass.RESOURCE_EXHAUSTED
    if error.retryable or error.code == "FAILED_RETRYABLE":
        return RetryClass.RETRYABLE
    if error.category in _RETRYABLE_CATEGORIES:
        return RetryClass.RETRYABLE
    return RetryClass.TERMINAL


def _deterministic_unit(run_id: str, step_id: str, attempt: int, modulus: int) -> int:
    """Reproducible pseudo-random integer in ``[0, modulus)``.

    Derived from a digest of the run/step/attempt triple rather than ``random``:
    a replayed run must schedule the same retry at the same offset, or the
    replay is not a replay.
    """

    if modulus <= 1:
        return 0
    material = canonical_json({"runId": run_id, "stepId": step_id, "attempt": attempt})
    raw = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(raw[:8], "big") % modulus


def backoff_ms(run_id: str, step_id: str, attempt: int, *,
               policy: RetryPolicy | None = None,
               retry_class: RetryClass = RetryClass.RETRYABLE) -> int:
    """Exponential backoff in whole milliseconds with deterministic jitter."""

    policy = policy or RetryPolicy()
    require_int(attempt, "attempt", minimum=1)
    exponent = min(attempt - 1, policy.max_exponent)
    base = policy.base_ms * (policy.multiplier ** exponent)
    capped = min(base, policy.max_ms)
    if retry_class is RetryClass.RESOURCE_EXHAUSTED:
        capped = max(capped, policy.resource_floor_ms)
        capped = min(capped, policy.max_ms) if policy.max_ms >= policy.resource_floor_ms else capped
    spread = (capped * policy.jitter_pct) // 100
    offset = _deterministic_unit(run_id, step_id, attempt, spread + 1)
    return capped - offset


def decide_retry(view: RunView, step_id: str, error: KernelError, *,
                 policy: RetryPolicy | None = None) -> RetryDecision:
    """Classify a step failure and schedule (or refuse) the next attempt."""

    if step_id not in view.steps:
        raise KernelError(
            code="UNKNOWN_STEP",
            message=f"step {step_id!r} is not part of run {view.run_id!r}",
            recommended_action="check the step id against the workflow definition",
        )
    step = view.steps[step_id]
    retry_class = classify_failure(error)
    attempt = step.attempts
    if retry_class is RetryClass.INTERRUPTED:
        return RetryDecision(
            step_id=step_id, attempt=attempt, retry_class=retry_class, should_retry=False,
            backoff_ms=None,
            reason="interrupted attempts have an unknown outcome; reconcile before retrying",
        )
    if retry_class is RetryClass.TERMINAL:
        return RetryDecision(
            step_id=step_id, attempt=attempt, retry_class=retry_class, should_retry=False,
            backoff_ms=None, reason=f"{error.code} is terminal for this step",
        )
    if any(
        intent.unresolved for intent in view.intents.values() if intent.step_id == step_id
    ):
        return RetryDecision(
            step_id=step_id, attempt=attempt, retry_class=retry_class, should_retry=False,
            backoff_ms=None,
            reason="an unresolved side effect blocks retry; reconcile first",
        )
    if attempt >= step.max_attempts:
        return RetryDecision(
            step_id=step_id, attempt=attempt, retry_class=retry_class, should_retry=False,
            backoff_ms=None,
            reason=f"attempt {attempt} reached maxAttempts {step.max_attempts}",
        )
    return RetryDecision(
        step_id=step_id,
        attempt=attempt,
        retry_class=retry_class,
        should_retry=True,
        backoff_ms=backoff_ms(view.run_id, step_id, attempt + 1, policy=policy,
                              retry_class=retry_class),
        reason=f"{error.code} classified {retry_class}",
    )


# --- the durable engine ------------------------------------------------------


class DurableRun:
    """A run driven through its state machine, with the log as the only truth.

    The single most important line in this class is the ordering inside
    :meth:`_emit`: append, then materialise.  If the process dies between the
    two, the log holds a fact the cache has not seen, and :meth:`rehydrate`
    recovers it.  Reverse the order and a crash invents a state transition that
    never happened — the cache would claim work the log cannot corroborate.

    Every append carries the caller's fencing token, so a worker whose lease was
    taken over cannot write to the stream even if it never noticed.
    """

    __slots__ = ("_events", "_kv", "_clock", "_artifacts", "_budget", "_definition",
                 "_fencing_token", "_retry_policy", "_view")

    def __init__(self, *, view: RunView, definition: WorkflowDefinition, events: Any,
                 kv: Any, clock: Any, artifacts: Any = None, budget: Budget | None = None,
                 fencing_token: int = 1,
                 retry_policy: RetryPolicy | None = None) -> None:
        self._view = view
        self._definition = definition
        self._events = events
        self._kv = kv
        self._clock = clock
        self._artifacts = artifacts
        self._budget = budget or Budget(max_turns=view.max_turns)
        self._fencing_token = require_int(fencing_token, "fencing_token", minimum=1)
        self._retry_policy = retry_policy or RetryPolicy()

    # -- construction ---------------------------------------------------------

    @classmethod
    def create(cls, *, run_id: str, definition: WorkflowDefinition, budget: Budget,
               events: Any, kv: Any, clock: Any, artifacts: Any = None,
               fencing_token: int = 1,
               retry_policy: RetryPolicy | None = None) -> DurableRun:
        """Open a new run by writing its ``RUN_CREATED`` event."""

        require_identifier(run_id, "run_id")
        build_dag(definition.steps)
        if events.head(run_id) is not None:
            raise KernelError(
                code="WRITE_CONFLICT",
                message=f"stream {run_id!r} already exists; use rehydrate()",
                retryable=False,
                recommended_action="rehydrate the existing run instead of recreating it",
            )
        occurred_at = format_timestamp(clock.now())
        body = {
            "workflowId": definition.workflow_id,
            "workflowVersion": definition.workflow_version,
            "taskSpecVersion": definition.task_spec_version,
            "definitionDigest": definition.definition_digest,
            "maxTurns": budget.max_turns,
            "budget": budget.to_payload(),
            "steps": [item.to_payload() for item in definition.steps],
        }
        content = {
            "sequence": 1,
            "eventType": str(EventType.RUN_CREATED),
            "runId": run_id,
            "stepId": None,
            "occurredAt": occurred_at,
            "body": body,
        }
        event = RunEvent(
            sequence=1, event_type=EventType.RUN_CREATED, run_id=run_id, step_id=None,
            occurred_at=occurred_at, body=body,
            chain=chain_for(GENESIS_CHAIN, content),
        )
        events.append(run_id, event.to_payload(), expected_sequence=0,
                      fencing_token=fencing_token)
        view = _create_view(event)
        run = cls(view=view, definition=definition, events=events, kv=kv, clock=clock,
                  artifacts=artifacts, budget=budget, fencing_token=fencing_token,
                  retry_policy=retry_policy)
        run._materialise()
        return run

    @classmethod
    def rehydrate(cls, *, run_id: str, definition: WorkflowDefinition, events: Any,
                  kv: Any, clock: Any, artifacts: Any = None, budget: Budget | None = None,
                  fencing_token: int = 1,
                  retry_policy: RetryPolicy | None = None) -> DurableRun:
        """Rebuild a run from its log and repair the materialised view.

        The cached view is never read back: it is a derived artefact and a crash
        may have left it stale or half-written.  Replaying costs microseconds
        and is the only answer that cannot be wrong.
        """

        stored = events.read(run_id)
        if not stored:
            raise KernelError(
                code="HISTORY_GAP",
                message=f"no events exist for run {run_id!r}",
                recommended_action="the run was never created; create it",
            )
        stream = tuple(RunEvent.from_stored(item) for item in stored)
        view = replay(stream)
        run = cls(view=view, definition=definition, events=events, kv=kv, clock=clock,
                  artifacts=artifacts, budget=budget, fencing_token=fencing_token,
                  retry_policy=retry_policy)
        run._materialise()
        return run

    # -- accessors ------------------------------------------------------------

    @property
    def view(self) -> RunView:
        """The materialised view as of the last applied event."""

        return self._view

    @property
    def definition(self) -> WorkflowDefinition:
        return self._definition

    @property
    def stream_id(self) -> str:
        return self._view.run_id

    def stream(self) -> tuple[RunEvent, ...]:
        """The full event log of this run, decoded."""

        return tuple(RunEvent.from_stored(item) for item in self._events.read(self.stream_id))

    def view_key(self) -> str:
        return f"run:{self.stream_id}:view"

    # -- the write path -------------------------------------------------------

    def _materialise(self) -> None:
        self._kv.put(self.view_key(), self._view.to_payload())

    def _emit(self, event_type: EventType, body: Mapping[str, Any], *,
              step_id: str | None = None) -> RunEvent:
        """Append the event, then move the materialised view.  Never the reverse."""

        head = self._events.head(self.stream_id)
        current_sequence = head.sequence if head is not None else 0
        previous_chain = (
            RunEvent.from_stored(head).chain if head is not None else GENESIS_CHAIN
        )
        content = {
            "sequence": current_sequence + 1,
            "eventType": str(event_type),
            "runId": self._view.run_id,
            "stepId": step_id,
            "occurredAt": format_timestamp(self._clock.now()),
            "body": dict(body),
        }
        event = RunEvent(
            sequence=content["sequence"],
            event_type=event_type,
            run_id=content["runId"],
            step_id=step_id,
            occurred_at=content["occurredAt"],
            body=content["body"],
            chain=chain_for(previous_chain, content),
        )
        # 1. durable truth
        self._events.append(self.stream_id, event.to_payload(),
                            expected_sequence=current_sequence,
                            fencing_token=self._fencing_token)
        # 2. derived cache (a failure here is recoverable; a failure above is not)
        self._view = _apply(self._view, event)
        self._materialise()
        return event

    # -- run-level control ----------------------------------------------------

    def advance(self, target: RunState) -> RunView:
        """Move the run to ``target``, validating the transition first."""

        body: dict[str, Any] = {"from": str(self._view.state), "to": str(target)}
        if target is RunState.PAUSED:
            body["pausedFrom"] = str(self._view.state)
        transition(self._view.state, target)
        self._emit(EventType.RUN_STATE_CHANGED, body)
        return self._view

    def pause(self) -> RunView:
        """Pause, recording the exact state being left.

        The origin is written into the event because resume must *restore* it.
        Guessing "probably EXECUTING" is how a run that paused during VERIFYING
        silently re-executes its side effects.
        """

        return self.advance(RunState.PAUSED)

    def resume(self) -> RunView:
        """Resume into the recorded pre-pause state."""

        if self._view.state is not RunState.PAUSED:
            raise KernelError(
                code="ILLEGAL_TRANSITION",
                message=f"run {self.stream_id!r} is {self._view.state}, not PAUSED",
                recommended_action="pause the run before resuming it",
                details={"current": str(self._view.state)},
            )
        origin = self._view.paused_from
        if origin is None:
            raise KernelError(
                code="PAUSE_ORIGIN_MISSING",
                message=f"run {self.stream_id!r} has no recorded pre-pause state",
                recommended_action="repair the log; never infer the pre-pause state",
            )
        self.require_resolved_side_effects()
        return self.advance(origin)

    def request_cancel(self, reason: str = "operator request") -> RunView:
        """Ask for cancellation.

        This only moves the run to ``CANCEL_REQUESTED``.  The cancellation takes
        effect at the next :meth:`safe_point`, so an in-flight side effect is
        allowed to finish and be recorded rather than being orphaned.
        """

        transition(self._view.state, RunState.CANCEL_REQUESTED)
        self._emit(EventType.RUN_STATE_CHANGED, {
            "from": str(self._view.state),
            "to": str(RunState.CANCEL_REQUESTED),
            "reason": require_str(reason, "reason"),
        })
        return self._view

    def safe_point(self) -> SafePoint:
        """Declare a cancellation boundary and apply any pending cancel.

        Safety is computed, not asserted: a step still RUNNING or a side effect
        still unresolved makes this point unsafe, and a pending cancel simply
        does not fire.  The run stays in ``CANCEL_REQUESTED`` until a genuinely
        safe boundary arrives.
        """

        safe, reasons = is_safe_point(self._view)
        cancel_pending = self._view.state is RunState.CANCEL_REQUESTED
        event = self._emit(EventType.SAFE_POINT_REACHED, {
            "safe": safe,
            "reasons": list(reasons),
            "cancelPending": cancel_pending,
        })
        cancel_effective = False
        if safe and cancel_pending:
            plan = rollback_plan(self._view)
            target = RunState.ROLLING_BACK if plan.entries else RunState.CANCELLED
            self.advance(target)
            cancel_effective = True
        return SafePoint(
            sequence=event.sequence,
            safe=safe,
            reasons=reasons,
            cancel_effective=cancel_effective,
            resulting_state=self._view.state,
        )

    # -- step-level control ---------------------------------------------------

    def mark_step(self, step_id: str, target: StepState, *,
                  outputs_digest: str | None = None,
                  error_code: str | None = None) -> RunView:
        """Move one step, validating the step transition."""

        body: dict[str, Any] = {"to": str(target)}
        if outputs_digest is not None:
            body["outputsDigest"] = require_str(outputs_digest, "outputs_digest")
        if error_code is not None:
            body["errorCode"] = require_str(error_code, "error_code")
        self._emit(EventType.STEP_STATE_CHANGED, body, step_id=step_id)
        return self._view

    def start_step(self, step_id: str) -> RunView:
        """Take a ready step to ``RUNNING``, enforcing readiness and the turn cap."""

        if step_id not in self._view.steps:
            raise KernelError(
                code="UNKNOWN_STEP",
                message=f"step {step_id!r} is not part of run {self.stream_id!r}",
                recommended_action="check the step id against the workflow definition",
            )
        if step_id not in next_ready_steps(self._view):
            step = self._view.steps[step_id]
            blocking = sorted(
                dependency for dependency in step.requires
                if self._view.steps[dependency].state is not StepState.SUCCEEDED
            )
            raise KernelError(
                code="STEP_NOT_READY",
                message=(
                    f"step {step_id!r} is {step.state} and its dependencies are not all "
                    f"SUCCEEDED: {blocking}"
                ),
                retryable=False,
                recommended_action="wait for the dependencies; PARTIAL does not satisfy one",
                details={
                    "stepId": step_id,
                    "blockedBy": blocking,
                    "dependencyStates": {
                        dependency: str(self._view.steps[dependency].state)
                        for dependency in sorted(step.requires)
                    },
                },
            )
        if self._view.turns_used >= self._view.max_turns:
            raise KernelError(
                code="MAX_TURNS_EXCEEDED",
                message=(
                    f"run {self.stream_id!r} has used all {self._view.max_turns} declared turns"
                ),
                retryable=False,
                recommended_action="raise budget.maxTurns explicitly or end the run",
                details={"maxTurns": self._view.max_turns, "turnsUsed": self._view.turns_used},
            )
        if self._view.steps[step_id].state is StepState.PENDING:
            self.mark_step(step_id, StepState.READY)
        return self.mark_step(step_id, StepState.RUNNING)

    # -- side effects ---------------------------------------------------------

    def begin_side_effect(self, step_id: str) -> str:
        """Announce a side effect *before* performing it and return its key.

        The announcement is what makes a crash survivable.  Without it, a run
        that dies mid-effect looks identical to one that died before starting,
        and the only options left are to duplicate the effect or to lose it.
        """

        step = self._view.steps.get(step_id)
        if step is None:
            raise KernelError(
                code="UNKNOWN_STEP",
                message=f"step {step_id!r} is not part of run {self.stream_id!r}",
                recommended_action="check the step id against the workflow definition",
            )
        if not step.side_effecting:
            raise KernelError(
                code="ORCHESTRATOR_INCONSISTENT",
                message=f"step {step_id!r} did not declare sideEffecting",
                recommended_action="declare the side effect in the workflow definition",
                details={"stepId": step_id},
            )
        key = idempotency_key(self._view.run_id, step_id, step.inputs_digest)
        existing = self._view.intents.get(key)
        if existing is not None and existing.observed:
            raise KernelError(
                code="IDEMPOTENCY_CONFLICT",
                message=(
                    f"side effect {key} for step {step_id!r} already landed; "
                    "performing it again would duplicate it"
                ),
                retryable=False,
                recommended_action="skip the effect and mark the step SUCCEEDED",
                details={"stepId": step_id, "idempotencyKey": key},
            )
        if existing is not None and existing.unresolved:
            raise KernelError(
                code="UNRESOLVED_SIDE_EFFECT",
                message=(
                    f"side effect {key} for step {step_id!r} was announced and never resolved"
                ),
                retryable=False,
                recommended_action="reconcile the intent before attempting it again",
                details={"stepId": step_id, "idempotencyKey": key},
            )
        self._emit(EventType.SIDE_EFFECT_INTENDED, {
            "idempotencyKey": key,
            "attempt": max(self._view.steps[step_id].attempts, 1),
            "inputsDigest": step.inputs_digest,
        }, step_id=step_id)
        return key

    def observe_side_effect(self, step_id: str, observation_digest: str) -> str:
        """Record that the announced effect has been seen to land."""

        step = self._view.steps.get(step_id)
        if step is None:
            raise KernelError(
                code="UNKNOWN_STEP",
                message=f"step {step_id!r} is not part of run {self.stream_id!r}",
                recommended_action="check the step id",
            )
        key = idempotency_key(self._view.run_id, step_id, step.inputs_digest)
        self._emit(EventType.SIDE_EFFECT_OBSERVED, {
            "idempotencyKey": key,
            "observationDigest": require_str(observation_digest, "observation_digest"),
        }, step_id=step_id)
        return key

    def reconcile(self, key: str, verdict: str, *, evidence_digest: str | None = None) -> RunView:
        """Record an external verdict about an unresolved side effect.

        ``verdict`` is ``LANDED`` or ``DID_NOT_LAND`` and must come from probing
        the target system.  There is deliberately no ``PROBABLY`` — the whole
        point of the reconciliation path is to replace a guess with a fact.
        """

        intent = self._view.intents.get(key)
        if intent is None:
            raise KernelError(
                code="UNKNOWN_STEP",
                message=f"no side-effect intent {key!r} exists on run {self.stream_id!r}",
                recommended_action="list reconciliation_plan(view) for the real keys",
            )
        body: dict[str, Any] = {"idempotencyKey": key, "verdict": verdict}
        if evidence_digest is not None:
            body["evidenceDigest"] = require_str(evidence_digest, "evidence_digest")
        self._emit(EventType.SIDE_EFFECT_RECONCILED, body, step_id=intent.step_id)
        return self._view

    def require_resolved_side_effects(self) -> None:
        """Refuse to continue while any announced effect is unaccounted for."""

        pending = unresolved_intents(self._view)
        if pending:
            plan = reconciliation_plan(self._view)
            raise KernelError(
                code="UNRESOLVED_SIDE_EFFECT",
                message=(
                    f"run {self.stream_id!r} has {len(pending)} announced side effect(s) with "
                    "no observation; the outside world may or may not have changed"
                ),
                retryable=False,
                interrupted=True,
                recommended_action="probe each idempotency key and record LANDED/DID_NOT_LAND",
                details={"reconciliation": [task.to_payload() for task in plan]},
            )

    # -- budget ---------------------------------------------------------------

    def consume_budget(self, meter: str, amount: int) -> dict[str, Any]:
        """Record measured consumption, then enforce the limit.

        The event is written *before* the limit check on purpose: the spend has
        already happened, and a log that hides it to make the error tidier is a
        log that lies.  Recording ``amount=0`` is how a genuine zero is stated;
        never recording anything leaves the meter *unmeasured*.
        """

        self._emit(EventType.BUDGET_CONSUMED, {
            "meter": require_identifier(meter, "meter"),
            "amount": require_int(amount, "amount", minimum=0),
        })
        report = budget_report(self._budget, self._view.budget_spent)
        entry = report["meters"].get(meter, {})
        if entry.get("limit") is not None and entry["spent"] > entry["limit"]:
            raise KernelError(
                code="BUDGET_EXHAUSTED",
                message=(
                    f"meter {meter!r} spent {entry['spent']} of a {entry['limit']} limit"
                ),
                retryable=False,
                recommended_action="raise the limit explicitly or end the run",
                details={"meter": meter, "report": entry},
            )
        return report

    def budget_report(self) -> dict[str, Any]:
        """Current budget position with explicit measured flags."""

        return budget_report(self._budget, self._view.budget_spent)

    # -- checkpoints, rollback, requirements ---------------------------------

    def write_checkpoint(self) -> Checkpoint:
        """Snapshot the state, store it content-addressed, and record the id."""

        snapshot = checkpoint(self._view)
        if self._artifacts is not None:
            self._artifacts.put(
                canonical_json(snapshot.state_snapshot).encode("utf-8"),
                media_type="application/json",
            )
        self._emit(EventType.CHECKPOINT_WRITTEN, {
            "checkpointId": snapshot.checkpoint_id,
            "sideEffectCursor": snapshot.side_effect_cursor,
        })
        return snapshot

    def rollback_plan(self) -> RollbackPlan:
        """Compensation plan for everything this run has already done."""

        return rollback_plan(self._view)

    def apply_compensation(self, step_id: str) -> RunView:
        """Run one compensation, moving the step through COMPENSATING."""

        step = self._view.steps.get(step_id)
        if step is None or step.compensation is None:
            raise KernelError(
                code="ROLLBACK_INCOMPLETE",
                message=f"step {step_id!r} declares no compensation and cannot be undone",
                retryable=False,
                recommended_action="escalate; do not report this step as rolled back",
                details={"stepId": step_id},
            )
        self.mark_step(step_id, StepState.COMPENSATING)
        self._emit(EventType.COMPENSATION_APPLIED, {
            "compensation": step.compensation,
        }, step_id=step_id)
        return self.mark_step(step_id, StepState.COMPENSATED)

    def update_requirements(self, new_definition: WorkflowDefinition) -> tuple[str, ...]:
        """Apply a requirement change, invalidating only what actually changed.

        A new task spec version is mandatory when the content changes: a silent
        redefinition under the same version makes every cached result and every
        evidence binding unfalsifiable.
        """

        if (
            new_definition.task_spec_version == self._view.task_spec_version
            and new_definition.definition_digest != self._view.definition_digest
        ):
            raise KernelError(
                code="TASK_SPEC_VERSION_NOT_BUMPED",
                message=(
                    f"workflow content changed but taskSpecVersion is still "
                    f"{self._view.task_spec_version!r}"
                ),
                retryable=False,
                recommended_action="bump taskSpecVersion so caches and evidence can be invalidated",
            )
        build_dag(new_definition.steps)
        invalidated = steps_to_rerun(self._view, new_definition)
        needs_compensation = sorted(
            step_id for step_id in invalidated
            if step_id in self._view.steps
            and self._view.steps[step_id].side_effecting
            and any(
                intent.step_id == step_id and (intent.observed or intent.unresolved)
                for intent in self._view.intents.values()
            )
        )
        self._emit(EventType.REQUIREMENT_UPDATED, {
            "taskSpecVersion": new_definition.task_spec_version,
            "definitionDigest": new_definition.definition_digest,
            "steps": [item.to_payload() for item in new_definition.steps],
            "invalidated": list(invalidated),
            "requiresCompensation": needs_compensation,
        })
        self._definition = new_definition
        return invalidated

    # -- retries --------------------------------------------------------------

    def schedule_retry(self, step_id: str, error: KernelError) -> RetryDecision:
        """Classify a step failure and, when retryable, record the next attempt."""

        decision = decide_retry(self._view, step_id, error, policy=self._retry_policy)
        self._emit(EventType.RETRY_SCHEDULED, decision.to_payload(), step_id=step_id)
        if decision.should_retry:
            self.mark_step(step_id, StepState.PENDING)
        return decision

    def progress_snapshot(self) -> dict[str, Any]:
        """Everything a progress UI needs, with no derived number left implicit."""

        dag = build_dag(self._definition.steps)
        counts: dict[str, int] = {}
        for step in self._view.steps.values():
            counts[str(step.state)] = counts.get(str(step.state), 0) + 1
        safe, reasons = is_safe_point(self._view)
        return {
            "runId": self.stream_id,
            "state": str(self._view.state),
            "sequenceNo": self._view.sequence,
            "stepStateCounts": dict(sorted(counts.items())),
            "readySteps": list(next_ready_steps(self._view)),
            "waves": [list(wave) for wave in dag.waves],
            "criticalPath": list(dag.critical_path),
            "safePoint": {"safe": safe, "reasons": list(reasons)},
            "budget": self.budget_report(),
            "turnsUsed": self._view.turns_used,
            "maxTurns": self._view.max_turns,
            "unresolvedSideEffects": [
                intent.to_payload() for intent in unresolved_intents(self._view)
            ],
            "viewDigest": view_digest(self._view),
        }


# --- registry entry point ----------------------------------------------------


def _require_snapshot(body: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    snapshot = require_mapping(body.get("repository_snapshot"), "repository_snapshot")
    return snapshot, require_str(snapshot.get("snapshotSha"), "repository_snapshot.snapshotSha")


def _check_capabilities(definition: WorkflowDefinition) -> None:
    """Deny any step naming a capability the kernel does not declare.

    Step definitions may be assembled from untrusted material (an issue body, a
    README, a model's suggestion).  Matching against the declared capability set
    is what stops "run-anything-as-root" from becoming a workflow step just
    because a document asked for it.
    """

    for step in definition.steps:
        if not step.required_capability:
            continue
        if step.required_capability not in DESCRIPTORS:
            raise KernelError(
                code="TOOL_DENIED",
                message=(
                    f"step {step.step_id!r} requires unknown capability "
                    f"{step.required_capability!r}"
                ),
                retryable=False,
                recommended_action="use a declared capability id; unknown capabilities are denied",
                details={"stepId": step.step_id, "requiredCapability": step.required_capability},
            )


@register(SKILL_ID)
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point: validate, instantiate and checkpoint a durable run.

    This facade is deterministic on purpose — it drives an in-memory event store
    and a clock fixed at the kernel epoch, so identical inputs produce identical
    digests and the result can be cached and compared.  Production drives
    :class:`DurableRun` directly with the real ports; this entry point exists to
    make the plan, its DAG and its rollback posture inspectable before anything
    executes.
    """

    body = require_mapping(request, "request")
    reject_unknown_fields(
        body,
        ("task_spec", "workflow_definition", "repository_snapshot", "budget",
         "policy_snapshot"),
        field_name="request",
    )
    if "workflow_definition" not in body:
        raise not_applicable("workflow_definition is required", skill=SKILL_ID)

    task_spec = require_mapping(body.get("task_spec"), "task_spec")
    task_spec_version = require_str(task_spec.get("taskSpecVersion"), "task_spec.taskSpecVersion")
    tenant_id = require_identifier(task_spec.get("tenantId"), "task_spec.tenantId")
    account_id = require_identifier(task_spec.get("accountId"), "task_spec.accountId")
    run_id = require_identifier(task_spec.get("runId", "run-1"), "task_spec.runId")

    snapshot, snapshot_sha = _require_snapshot(body)
    declared_sha = task_spec.get("repoSnapshotSha")
    if declared_sha is not None and declared_sha != snapshot_sha:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"task spec was written against {declared_sha!r} but the supplied snapshot is "
                f"{snapshot_sha!r}"
            ),
            retryable=False,
            recommended_action="recompile the task spec against the current snapshot",
            details={"taskSpecSnapshot": declared_sha, "suppliedSnapshot": snapshot_sha},
        )

    policy_snapshot = require_mapping(body.get("policy_snapshot"), "policy_snapshot")
    policy_hash = policy_snapshot.get("snapshotHash")
    if not policy_hash:
        raise KernelError(
            code="POLICY_SNAPSHOT_MISSING",
            message="policy_snapshot.snapshotHash is required; an unpolicied run is denied",
            retryable=False,
            recommended_action="bind the run to a policy snapshot",
        )

    budget = Budget.from_payload(require_mapping(body.get("budget"), "budget"))
    definition = WorkflowDefinition.from_payload(
        body.get("workflow_definition"), task_spec_version=task_spec_version
    )
    _check_capabilities(definition)
    dag = build_dag(definition.steps)

    clock = FixedClock(_EPOCH)
    run = DurableRun.create(
        run_id=run_id, definition=definition, budget=budget,
        events=InMemoryEventStore(clock), kv=InMemoryKeyValueStore(), clock=clock,
        artifacts=InMemoryArtifactStore(), fencing_token=1,
    )
    run.advance(RunState.SPECIFYING)
    run.advance(RunState.PLANNING)
    snapshot_point = run.write_checkpoint()
    plan = run.rollback_plan()

    view = run.view
    return {
        "run": {
            **view.to_payload(),
            "tenantId": tenant_id,
            "accountId": account_id,
            "repoSnapshotSha": snapshot_sha,
            "policySnapshotHash": policy_hash,
            "snapshotPaths": len(snapshot.get("paths", ()) or ()),
            "dag": dag.to_payload(),
            "viewDigest": view_digest(view),
        },
        "step_runs": [step.to_payload() for _, step in sorted(view.steps.items())],
        "run_events": [event.to_payload() for event in run.stream()],
        "checkpoints": [snapshot_point.to_payload()],
        "rollback_plan": plan.to_payload(),
        "progress_snapshot": run.progress_snapshot(),
        "evidenceIds": [
            definition.definition_digest,
            view_digest(view),
            snapshot_point.checkpoint_id,
            plan.plan_digest,
        ],
    }
