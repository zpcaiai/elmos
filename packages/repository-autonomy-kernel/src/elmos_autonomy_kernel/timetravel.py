"""Session time travel: restore, fork and compare runs from the event log.

Time travel is a read operation that people mistake for a write one.  Every
function here derives a *new* value — a view, a new stream, a report — and none
of them touches the timeline it was given.  The original stream is the audit
record; if a fork could rewrite it, the audit record would only ever describe
the last person to look at it.

The dangerous case is forking from a point where a side effect had been
announced but never observed.  Replaying forward from there re-executes the
attempt, and the outside world may already carry the first one.  The kernel
refuses that fork unless the caller explicitly acknowledges the duplication
risk, and the acknowledgement — with the exact idempotency keys it covers — is
written into the ``FORK`` event, so the person who accepted the risk is on the
record rather than in somebody's memory.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    digest,
    format_timestamp,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
)
from .errors import Category, KernelError, not_applicable, register_codes
from .orchestrator import (
    EventType,
    RunEvent,
    RunView,
    chain_for,
    replay,
    rollback_plan,
    unresolved_intents,
    verify_chain,
    view_digest,
)
from .registry import register

register_codes(Category.INTEGRITY, "TIME_TRAVEL_SNAPSHOT_INVALID", "HISTORY_GAP")
register_codes(Category.ORCHESTRATION, "UNSAFE_REPLAY")
register_codes(Category.CONCURRENCY, "FORK_CONFLICT")

__all__ = [
    "SKILL_ID",
    "SAFE_REPLAY_EVENTS",
    "UNSAFE_REPLAY_EVENTS",
    "decode_events",
    "restore",
    "ForkResult",
    "fork",
    "fork_into",
    "ReplayPlan",
    "replay_plan",
    "FieldDivergence",
    "DivergenceReport",
    "diff",
    "handle",
]

SKILL_ID = "session-time-travel"

#: Events whose replay changes nothing outside the kernel.
SAFE_REPLAY_EVENTS: frozenset[EventType] = frozenset({
    EventType.RUN_CREATED,
    EventType.RUN_STATE_CHANGED,
    EventType.STEP_STATE_CHANGED,
    EventType.CHECKPOINT_WRITTEN,
    EventType.BUDGET_CONSUMED,
    EventType.SAFE_POINT_REACHED,
    EventType.REQUIREMENT_UPDATED,
    EventType.RETRY_SCHEDULED,
    EventType.FORK,
})

#: Events that describe something that happened *outside* the kernel.  Replaying
#: one of these does not re-do the effect, it merely re-asserts it — which is
#: worse, because the assertion would then be unbacked.  They are always
#: reported for operator review instead of being executed automatically.
UNSAFE_REPLAY_EVENTS: frozenset[EventType] = frozenset({
    EventType.SIDE_EFFECT_INTENDED,
    EventType.SIDE_EFFECT_OBSERVED,
    EventType.SIDE_EFFECT_RECONCILED,
    EventType.COMPENSATION_APPLIED,
})


def decode_events(raw: Any, field_name: str = "run_event_stream") -> tuple[RunEvent, ...]:
    """Decode a wire event array strictly."""

    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be an array of run events",
            recommended_action=f"supply {field_name} as a JSON array",
        )
    return tuple(RunEvent.from_payload(item) for item in raw)


def _validate_stream(events: Sequence[RunEvent]) -> None:
    """Reject a stream that is not a complete, untampered history."""

    if not events:
        raise KernelError(
            code="HISTORY_GAP",
            message="the event stream is empty; there is no history to travel",
            recommended_action="supply the run's events",
        )
    expected = 1
    for event in events:
        if event.sequence != expected:
            raise KernelError(
                code="HISTORY_GAP",
                message=(
                    f"event stream jumps from sequence {expected - 1} to {event.sequence}"
                ),
                retryable=False,
                recommended_action="fetch the missing events before restoring",
                details={"expected": expected, "found": event.sequence},
            )
        expected += 1
    if not verify_chain(events):
        raise KernelError(
            code="TIME_TRAVEL_SNAPSHOT_INVALID",
            message="event hash chain does not verify; the stream has been altered",
            retryable=False,
            recommended_action="restore the stream from backup; do not travel through it",
        )


def _prefix(events: Sequence[RunEvent], at_sequence: int) -> tuple[RunEvent, ...]:
    _validate_stream(events)
    head = events[-1].sequence
    require_int(at_sequence, "at_sequence", minimum=1)
    if at_sequence > head:
        raise KernelError(
            code="TIME_TRAVEL_SNAPSHOT_INVALID",
            message=(
                f"target sequence {at_sequence} is beyond the stream head {head}; "
                "there is no such point in this history"
            ),
            retryable=False,
            recommended_action=f"choose a sequence in 1..{head}",
            details={"requested": at_sequence, "head": head},
        )
    return tuple(events[:at_sequence])


def restore(events: Sequence[RunEvent], at_sequence: int) -> RunView:
    """Return the materialised view exactly as it was after ``at_sequence``.

    This is a pure fold over a prefix of the log; it neither reads nor writes
    the materialised store, so a corrupted cache cannot influence the answer.
    """

    return replay(_prefix(events, at_sequence))


# --- forking -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForkResult:
    """A new timeline that shares the parent's past and none of its future."""

    new_run_id: str
    parent_run_id: str
    parent_sequence: int
    events: tuple[RunEvent, ...]
    view: RunView
    acknowledged_keys: tuple[str, ...]
    fork_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "newRunId": self.new_run_id,
            "parentRunId": self.parent_run_id,
            "parentSequence": self.parent_sequence,
            "eventCount": len(self.events),
            "events": [event.to_payload() for event in self.events],
            "view": self.view.to_payload(),
            "viewDigest": view_digest(self.view),
            "acknowledgedUnresolvedSideEffects": list(self.acknowledged_keys),
            "forkDigest": self.fork_digest,
        }


def fork(events: Sequence[RunEvent], at_sequence: int, new_run_id: str, *,
         acknowledge_unresolved_side_effects: bool = False,
         clock: Any = None) -> ForkResult:
    """Branch a new run from ``at_sequence`` without touching the original.

    The prefix is copied *verbatim* — each copied event keeps its own run id and
    its own chain value — so the fork's audit chain verifies end to end and the
    ``FORK`` event is the visible seam rather than a rewrite.  From that event
    on, the stream belongs to ``new_run_id`` and carries its own budget.

    Forking from a point with an unresolved side-effect intent means the branch
    will re-attempt an effect that may already have happened.  That is refused
    unless the caller acknowledges it, and the acknowledgement is recorded with
    the keys it covers.
    """

    require_identifier(new_run_id, "new_run_id")
    prefix = _prefix(events, at_sequence)
    view = replay(prefix)
    if new_run_id == view.run_id:
        raise KernelError(
            code="FORK_CONFLICT",
            message=f"fork target {new_run_id!r} is the parent run itself",
            retryable=False,
            recommended_action="choose a distinct run id for the fork",
        )
    pending = unresolved_intents(view)
    keys = tuple(intent.key for intent in pending)
    if pending and not acknowledge_unresolved_side_effects:
        raise KernelError(
            code="UNSAFE_REPLAY",
            message=(
                f"sequence {at_sequence} sits inside {len(pending)} unresolved side-effect "
                "intent(s); forking here would re-attempt an effect that may already have "
                "landed"
            ),
            retryable=False,
            recommended_action=(
                "reconcile the intents first, or pass acknowledge_unresolved_side_effects=True "
                "to accept the duplication risk on the record"
            ),
            details={
                "idempotencyKeys": list(keys),
                "atSequence": at_sequence,
            },
        )

    # With no clock the fork is stamped at the parent event's time: a fork is a
    # statement about a moment in the parent's history, and inventing a fresh
    # timestamp would make two forks of the same point look different.
    occurred_at = (
        prefix[-1].occurred_at if clock is None else format_timestamp(clock.now())
    )
    body: dict[str, Any] = {
        "newRunId": new_run_id,
        "parentRunId": view.run_id,
        "parentSequence": at_sequence,
        "parentChain": prefix[-1].chain,
        "acknowledgedUnresolvedSideEffects": list(keys) if pending else [],
        "acknowledgementGranted": bool(pending and acknowledge_unresolved_side_effects),
        "inheritedBudgetSpent": dict(sorted(view.budget_spent.items())),
    }
    content = {
        "sequence": at_sequence + 1,
        "eventType": str(EventType.FORK),
        "runId": new_run_id,
        "stepId": None,
        "occurredAt": occurred_at,
        "body": body,
    }
    fork_event = RunEvent(
        sequence=at_sequence + 1,
        event_type=EventType.FORK,
        run_id=new_run_id,
        step_id=None,
        occurred_at=occurred_at,
        body=body,
        chain=chain_for(prefix[-1].chain, content),
    )
    forked = prefix + (fork_event,)
    forked_view = replay(forked)
    return ForkResult(
        new_run_id=new_run_id,
        parent_run_id=view.run_id,
        parent_sequence=at_sequence,
        events=forked,
        view=forked_view,
        acknowledged_keys=keys if pending else (),
        fork_digest=digest({
            "parentRunId": view.run_id,
            "parentSequence": at_sequence,
            "newRunId": new_run_id,
            "chain": fork_event.chain,
        }),
    )


def fork_into(store: Any, result: ForkResult) -> tuple[RunEvent, ...]:
    """Persist a fork as a new stream, refusing to overwrite an existing one.

    Writing to a stream that already has events would splice two histories
    together, which is the one way a fork *can* corrupt an audit record.
    """

    if store.head(result.new_run_id) is not None:
        raise KernelError(
            code="FORK_CONFLICT",
            message=f"stream {result.new_run_id!r} already exists",
            retryable=False,
            recommended_action="choose an unused run id for the fork",
        )
    for index, event in enumerate(result.events):
        store.append(result.new_run_id, event.to_payload(), expected_sequence=index)
    return result.events


# --- replay safety -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    """What may be replayed automatically and what a human must decide."""

    from_sequence: int
    safe: tuple[int, ...]
    unsafe: tuple[Mapping[str, Any], ...]
    requires_operator: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "fromSequence": self.from_sequence,
            "safeSequences": list(self.safe),
            "unsafe": [dict(item) for item in self.unsafe],
            "requiresOperator": self.requires_operator,
            "autoReplayable": not self.requires_operator,
        }


def replay_plan(events: Sequence[RunEvent], from_sequence: int = 0) -> ReplayPlan:
    """Split the tail of a stream into auto-replayable and operator-gated events.

    Nothing that describes an external effect is ever put in the safe bucket.
    The kernel can rebuild its own beliefs; it cannot rebuild the world.
    """

    _validate_stream(events)
    require_int(from_sequence, "from_sequence", minimum=0)
    safe: list[int] = []
    unsafe: list[Mapping[str, Any]] = []
    for event in events:
        if event.sequence <= from_sequence:
            continue
        if event.event_type in UNSAFE_REPLAY_EVENTS:
            unsafe.append({
                "sequenceNo": event.sequence,
                "eventType": str(event.event_type),
                "stepId": event.step_id,
                "idempotencyKey": event.body.get("idempotencyKey"),
                "reason": "describes an external effect; replay cannot re-establish it",
            })
        else:
            safe.append(event.sequence)
    return ReplayPlan(
        from_sequence=from_sequence,
        safe=tuple(safe),
        unsafe=tuple(unsafe),
        requires_operator=bool(unsafe),
    )


# --- divergence --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldDivergence:
    """One materialised field on which two runs disagree."""

    path: str
    left: Any
    right: Any

    def to_payload(self) -> dict[str, Any]:
        return {"path": self.path, "left": self.left, "right": self.right}


@dataclass(frozen=True, slots=True)
class DivergenceReport:
    """Where two timelines parted and what the difference amounts to."""

    left_run_id: str
    right_run_id: str
    left_length: int
    right_length: int
    common_prefix_length: int
    first_divergent_sequence: int | None
    divergence_kind: str
    field_divergences: tuple[FieldDivergence, ...] = ()
    report_digest: str = ""

    @property
    def identical(self) -> bool:
        return self.first_divergent_sequence is None and not self.field_divergences

    def to_payload(self) -> dict[str, Any]:
        return {
            "leftRunId": self.left_run_id,
            "rightRunId": self.right_run_id,
            "leftLength": self.left_length,
            "rightLength": self.right_length,
            "commonPrefixLength": self.common_prefix_length,
            "firstDivergentSequence": self.first_divergent_sequence,
            "divergenceKind": self.divergence_kind,
            "identical": self.identical,
            "fieldDivergences": [item.to_payload() for item in self.field_divergences],
            "reportDigest": self.report_digest,
        }


_MISSING = object()


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key in sorted(value):
            flat.update(_flatten(value[key], f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, (list, tuple)):
        flat[prefix or "$"] = list(value)
    else:
        flat[prefix or "$"] = value
    return flat


def diff(run_a: Sequence[RunEvent], run_b: Sequence[RunEvent]) -> DivergenceReport:
    """Compare two timelines: where they split, and how their state differs.

    The event comparison ignores each event's chain value and compares content,
    so a stream copied into a fork is recognised as the same history rather than
    as an immediate divergence.
    """

    _validate_stream(run_a)
    _validate_stream(run_b)
    view_a = replay(run_a)
    view_b = replay(run_b)

    common = 0
    first_divergent: int | None = None
    kind = "identical"
    # strict=False is deliberate: comparing a run against its own fork means the
    # two streams have different lengths by construction.  The shorter-run case
    # is handled below as kind="length" rather than by raising here.
    for left, right in zip(run_a, run_b, strict=False):
        if left.content() == right.content():
            common += 1
            continue
        first_divergent = left.sequence
        kind = "event-content"
        break
    if first_divergent is None and len(run_a) != len(run_b):
        first_divergent = min(len(run_a), len(run_b)) + 1
        kind = "length"

    flat_a = _flatten(view_a.to_payload())
    flat_b = _flatten(view_b.to_payload())
    divergences: list[FieldDivergence] = []
    for path in sorted(set(flat_a) | set(flat_b)):
        left_value = flat_a.get(path, _MISSING)
        right_value = flat_b.get(path, _MISSING)
        if left_value is _MISSING or right_value is _MISSING or left_value != right_value:
            divergences.append(FieldDivergence(
                path=path,
                left=None if left_value is _MISSING else left_value,
                right=None if right_value is _MISSING else right_value,
            ))
    if divergences and kind == "identical":
        kind = "state-only"

    payload = {
        "leftRunId": view_a.run_id,
        "rightRunId": view_b.run_id,
        "firstDivergentSequence": first_divergent,
        "fieldDivergences": [item.to_payload() for item in divergences],
    }
    return DivergenceReport(
        left_run_id=view_a.run_id,
        right_run_id=view_b.run_id,
        left_length=len(run_a),
        right_length=len(run_b),
        common_prefix_length=common,
        first_divergent_sequence=first_divergent,
        divergence_kind=kind,
        field_divergences=tuple(divergences),
        report_digest=digest(payload),
    )


# --- registry entry point ----------------------------------------------------

_KNOWN_FIELDS = (
    "run_event_stream", "run_events", "target_point", "checkpoints",
    "context_ledgers", "change_graph", "artifacts",
)
_TARGET_FIELDS = (
    "operation", "atSequence", "newRunId", "acknowledgeUnresolvedSideEffects", "compareTo",
)


def _session_snapshot(view: RunView, at_sequence: int) -> dict[str, Any]:
    return {
        "atSequence": at_sequence,
        "view": view.to_payload(),
        "viewDigest": view_digest(view),
        "unresolvedSideEffects": [
            intent.to_payload() for intent in unresolved_intents(view)
        ],
    }


@register(SKILL_ID)
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for restore / fork / diff.

    The operation lives inside ``target_point`` because the declared input
    surface of this capability is a fixed set of documents; smuggling a verb in
    as a sixth top-level field would make the schema a lie.  Every one of the
    five declared outputs is always present, ``null`` where the operation does
    not produce it — an absent key and a null key must not be the same signal.
    """

    body = require_mapping(request, "request")
    reject_unknown_fields(body, _KNOWN_FIELDS, field_name="request")
    raw_events = body.get("run_event_stream", body.get("run_events"))
    if raw_events is None:
        raise not_applicable("run_event_stream is required", skill=SKILL_ID)
    events = decode_events(raw_events)
    _validate_stream(events)

    target = require_mapping(body.get("target_point", {}), "target_point")
    reject_unknown_fields(target, _TARGET_FIELDS, field_name="target_point")
    operation = require_str(target.get("operation", "restore"), "target_point.operation")
    if operation not in {"restore", "fork", "diff"}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown time-travel operation {operation!r}",
            recommended_action="use restore, fork or diff",
        )
    at_sequence = require_int(
        target.get("atSequence", events[-1].sequence), "target_point.atSequence", minimum=1
    )

    outputs: dict[str, Any] = {
        "session_snapshot": None,
        "forked_run": None,
        "replay_report": None,
        "state_comparison": None,
        "rollback_plan": None,
    }
    evidence: list[str] = []

    if operation == "diff":
        other = decode_events(target.get("compareTo"), "target_point.compareTo")
        report = diff(events, other)
        outputs["state_comparison"] = report.to_payload()
        outputs["session_snapshot"] = _session_snapshot(replay(events), events[-1].sequence)
        outputs["replay_report"] = replay_plan(events, report.common_prefix_length).to_payload()
        outputs["rollback_plan"] = rollback_plan(replay(events)).to_payload()
        evidence.append(report.report_digest)
    elif operation == "fork":
        result = fork(
            events, at_sequence,
            require_identifier(target.get("newRunId"), "target_point.newRunId"),
            acknowledge_unresolved_side_effects=require_bool(
                target.get("acknowledgeUnresolvedSideEffects", False),
                "target_point.acknowledgeUnresolvedSideEffects",
            ),
        )
        outputs["forked_run"] = result.to_payload()
        outputs["session_snapshot"] = _session_snapshot(result.view, at_sequence)
        outputs["replay_report"] = replay_plan(events, at_sequence).to_payload()
        outputs["state_comparison"] = diff(events, result.events).to_payload()
        outputs["rollback_plan"] = rollback_plan(result.view).to_payload()
        evidence.extend([result.fork_digest, view_digest(result.view)])
    else:
        view = restore(events, at_sequence)
        outputs["session_snapshot"] = _session_snapshot(view, at_sequence)
        outputs["replay_report"] = replay_plan(events, at_sequence).to_payload()
        outputs["rollback_plan"] = rollback_plan(view).to_payload()
        evidence.append(view_digest(view))

    outputs["evidenceIds"] = evidence
    return outputs
