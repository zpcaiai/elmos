"""Model-state continuity: state that survives compaction, restart and failover.

A model's implicit memory is not state.  It cannot be inspected, it cannot be
handed to a different provider, and it disappears the moment a context window is
compacted or a process is restarted.  Everything this module keeps is explicit,
structured and content-free: identifiers, digests, enums and counts, and nothing
that reads like prose or file content.  The restriction is not tidiness — a
ledger that is allowed to hold free text becomes a second, unverified transcript,
and the first thing anyone does with a transcript is trust it.

The claim this module makes is deliberately narrow.  Compaction is **lossless for
decisions**, not lossless in general.  The checkpoint retains exactly the state
that :func:`decide` reads — decisions already taken, obligations still open, the
entity ids in play, the evidence digests relied upon, and the side effects whose
outcome is unresolved — and drops everything else.  A summary, an intermediate
observation or a discharged obligation's history is gone, and
:func:`continuity_report` says so by name.  Claiming more than that would be
claiming that a lossy transform is lossless, which is how a resumed run quietly
makes a different decision than the one it was going to make.

Restore never widens authority.  A checkpoint carries the binding it was taken
under, and restoring under a different permission profile, workspace or policy
snapshot is a refusal rather than an adjustment: a provider failover is a change
of model, never a change of what the run is allowed to do.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
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
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import Clock, EventStore
from .registry import register

__all__ = [
    "Binding",
    "Checkpoint",
    "CompactionPolicy",
    "ContextLedger",
    "ContinuityReport",
    "Decision",
    "DecisionReason",
    "DecisionRequest",
    "Observation",
    "ObservationKind",
    "RestoredState",
    "StateDiff",
    "Verdict",
    "WorkingState",
    "assert_replay_safe",
    "bind_clock",
    "bound_clock",
    "compact",
    "continuation_prompt",
    "continuity_report",
    "decide",
    "handle",
    "materialise",
    "record_checkpoint",
    "restore",
    "run_decisions",
    "state_diff",
    "verify_resume_equivalence",
]

register_codes(
    Category.SEMANTIC,
    "CONTINUITY_UNCONFIGURED",
    "STATE_CONTINUITY_LOST",
    "LEDGER_CONTENT_FORBIDDEN",
    "LEDGER_SEQUENCE_GAP",
    "COMPACTION_LOSSY",
)
register_codes(
    Category.VERIFICATION,
    "RESUME_DIVERGED",
)
register_codes(
    Category.PROVIDER,
    "PROVIDER_FAILOVER_FAILED",
)
register_codes(
    Category.INPUT,
    "STALE_STATE",
)
register_codes(
    Category.INTEGRITY,
    "UNRESOLVED_SIDE_EFFECT",
)

#: A ledger token: an identifier, a path, or a digest.  No whitespace, no
#: newlines, bounded length.  Anything that fails this is prose, a file body or
#: a tool transcript, and none of those belong in durable state.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/#+-]{0,199}$")

_LEDGER_SCHEMA = "elmos.continuity.ledger/1"
_CHECKPOINT_SCHEMA = "elmos.continuity.checkpoint/1"


def _require_token(value: Any, path: str) -> str:
    """Accept an identifier-shaped token; refuse anything that carries content."""

    if not isinstance(value, str) or not value:
        raise KernelError(
            code="LEDGER_CONTENT_FORBIDDEN",
            message=f"{path} must be a non-empty identifier token",
            recommended_action="record an id, a path or a digest — never free text",
            details={"field": path},
        )
    if not _TOKEN_RE.match(value):
        raise KernelError(
            code="LEDGER_CONTENT_FORBIDDEN",
            message=(
                f"{path} is not a content-free token; the context ledger holds "
                "identifiers, digests, enums and counts only"
            ),
            recommended_action="store the content as an artifact and record its digest",
            details={"field": path, "length": len(value)},
        )
    return value


class ObservationKind(StrEnum):
    """The closed vocabulary of things a run may record about itself.

    It is closed on purpose.  An open vocabulary is an invitation to record
    "note" or "summary", and a ledger with a note field is a transcript.
    """

    DECISION_TAKEN = "DECISION_TAKEN"
    OBLIGATION_OPENED = "OBLIGATION_OPENED"
    OBLIGATION_DISCHARGED = "OBLIGATION_DISCHARGED"
    ENTITY_OBSERVED = "ENTITY_OBSERVED"
    ENTITY_RETIRED = "ENTITY_RETIRED"
    EVIDENCE_RELIED_UPON = "EVIDENCE_RELIED_UPON"
    SIDE_EFFECT_APPLIED = "SIDE_EFFECT_APPLIED"
    SIDE_EFFECT_UNRESOLVED = "SIDE_EFFECT_UNRESOLVED"
    SIDE_EFFECT_RESOLVED = "SIDE_EFFECT_RESOLVED"
    TOOL_INVOKED = "TOOL_INVOKED"
    STEP_COMPLETED = "STEP_COMPLETED"
    PROVIDER_SWITCHED = "PROVIDER_SWITCHED"


#: Kinds the decision procedure reads.  Dropping one of these in compaction is
#: what turns "lossless for decisions" into a lie, so it is checked rather than
#: documented.
DECISION_BEARING_KINDS: frozenset[ObservationKind] = frozenset({
    ObservationKind.DECISION_TAKEN,
    ObservationKind.OBLIGATION_OPENED,
    ObservationKind.OBLIGATION_DISCHARGED,
    ObservationKind.ENTITY_OBSERVED,
    ObservationKind.ENTITY_RETIRED,
    ObservationKind.EVIDENCE_RELIED_UPON,
    ObservationKind.SIDE_EFFECT_UNRESOLVED,
    ObservationKind.SIDE_EFFECT_RESOLVED,
})


@dataclass(frozen=True, slots=True)
class Observation:
    """One content-free fact, at one point in a run.

    ``refs``, ``counts`` and ``enums`` are the only payload.  There is no free
    string field anywhere in this dataclass, and the validators enforce that a
    caller cannot smuggle one in through a ref.
    """

    sequence: int
    kind: ObservationKind
    subject_id: str
    refs: tuple[str, ...] = ()
    counts: tuple[tuple[str, int], ...] = ()
    enums: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        require_int(self.sequence, "observation.sequence", minimum=1)
        if not isinstance(self.kind, ObservationKind):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown observation kind {self.kind!r}",
                recommended_action=f"use one of {sorted(k.value for k in ObservationKind)}",
            )
        _require_token(self.subject_id, "observation.subject_id")
        for index, ref in enumerate(self.refs):
            _require_token(ref, f"observation.refs[{index}]")
        for name, value in self.counts:
            _require_token(name, "observation.counts.name")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise KernelError(
                    code="LEDGER_CONTENT_FORBIDDEN",
                    message=f"observation.counts[{name!r}] must be a non-negative integer",
                    recommended_action="counts are integers; never floats and never text",
                )
        for name, value in self.enums:
            _require_token(name, "observation.enums.name")
            _require_token(value, f"observation.enums[{name}]")

    def count(self, name: str) -> int | None:
        """Return a count or ``None`` when it was never recorded."""

        for key, value in self.counts:
            if key == name:
                return value
        return None

    def enum(self, name: str) -> str | None:
        for key, value in self.enums:
            if key == name:
                return value
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": str(self.kind),
            "subjectId": self.subject_id,
            "refs": list(self.refs),
            "counts": {name: value for name, value in self.counts},
            "enums": {name: value for name, value in self.enums},
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def _decode_observation(payload: Mapping[str, Any], sequence: int) -> Observation:
    reject_unknown_fields(payload, {"sequence", "kind", "subjectId", "refs", "counts", "enums"},
                          field_name="observation")
    kind = require_str(payload.get("kind"), "observation.kind", max_length=64)
    if kind not in {item.value for item in ObservationKind}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown observation kind {kind!r}",
            recommended_action=f"use one of {sorted(k.value for k in ObservationKind)}",
        )
    counts = require_mapping(payload.get("counts", {}), "observation.counts")
    enums = require_mapping(payload.get("enums", {}), "observation.enums")
    refs_raw = payload.get("refs", ())
    if isinstance(refs_raw, (str, bytes)) or not isinstance(refs_raw, Sequence):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="observation.refs must be an array",
            recommended_action="supply refs as a JSON array of tokens",
        )
    return Observation(
        sequence=sequence,
        kind=ObservationKind(kind),
        subject_id=payload.get("subjectId"),
        refs=tuple(refs_raw),
        counts=tuple((name, counts[name]) for name in sorted(counts)),
        enums=tuple((name, enums[name]) for name in sorted(enums)),
    )


class ContextLedger:
    """Append-only, hash-chained sequence of content-free observations.

    There is no update and no delete.  The chain exists so that a ledger that
    has been edited between a checkpoint and a restore is detectable: without
    it, "the state we resumed from" and "the state we recorded" are two claims
    with nothing connecting them.
    """

    __slots__ = ("_ledger_id", "_observations", "_chain")

    def __init__(self, ledger_id: str) -> None:
        require_identifier(ledger_id, "ledger_id")
        self._ledger_id = ledger_id
        self._observations: list[Observation] = []
        self._chain: list[str] = []

    @property
    def ledger_id(self) -> str:
        return self._ledger_id

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._observations)

    @property
    def head_sequence(self) -> int:
        return len(self._observations)

    @property
    def head_digest(self) -> str:
        """The chain head.  An empty ledger has a defined, non-zero head."""

        return self._chain[-1] if self._chain else digest({"ledgerId": self._ledger_id})

    def append(self, kind: ObservationKind, subject_id: str, *,
               refs: Sequence[str] = (), counts: Mapping[str, int] | None = None,
               enums: Mapping[str, str] | None = None) -> Observation:
        """Append one observation and return it with its assigned sequence."""

        counts = counts or {}
        enums = enums or {}
        observation = Observation(
            sequence=len(self._observations) + 1,
            kind=kind,
            subject_id=subject_id,
            refs=tuple(refs),
            counts=tuple((name, counts[name]) for name in sorted(counts)),
            enums=tuple((name, enums[name]) for name in sorted(enums)),
        )
        previous = self.head_digest
        self._observations.append(observation)
        self._chain.append(digest({"previous": previous, "observation": observation.to_payload()}))
        return observation

    def digest_at(self, sequence: int) -> str:
        """Chain digest after ``sequence`` observations."""

        if sequence == 0:
            return digest({"ledgerId": self._ledger_id})
        if sequence < 0 or sequence > len(self._chain):
            raise KernelError(
                code="LEDGER_SEQUENCE_GAP",
                message=f"ledger {self._ledger_id!r} has no sequence {sequence}",
                recommended_action="checkpoint against a sequence the ledger reached",
            )
        return self._chain[sequence - 1]

    def verify(self) -> bool:
        """Recompute the chain; any edit to a recorded observation breaks it."""

        previous = digest({"ledgerId": self._ledger_id})
        for index, observation in enumerate(self._observations):
            expected = digest({"previous": previous, "observation": observation.to_payload()})
            if expected != self._chain[index]:
                return False
            previous = expected
        return True

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": _LEDGER_SCHEMA,
            "ledgerId": self._ledger_id,
            "observations": [item.to_payload() for item in self._observations],
            "headDigest": self.head_digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ContextLedger:
        """Rebuild a ledger, re-deriving the chain and refusing a gap."""

        reject_unknown_fields(payload, {"schema", "ledgerId", "observations", "headDigest"},
                              field_name="context_ledger")
        if payload.get("schema") not in (None, _LEDGER_SCHEMA):
            raise KernelError(
                code="STATE_CONTINUITY_LOST",
                message=f"context ledger has schema {payload.get('schema')!r}",
                recommended_action=f"this build reads {_LEDGER_SCHEMA}",
            )
        ledger = cls(require_identifier(payload.get("ledgerId"), "context_ledger.ledgerId"))
        raw = payload.get("observations", ())
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="context_ledger.observations must be an array",
                recommended_action="supply observations as a JSON array",
            )
        for index, item in enumerate(raw):
            entry = require_mapping(item, f"observations[{index}]")
            observed = _decode_observation(entry, index + 1)
            declared = entry.get("sequence")
            if declared is not None and declared != observed.sequence:
                raise KernelError(
                    code="LEDGER_SEQUENCE_GAP",
                    message=(
                        f"observation {index} declares sequence {declared}, "
                        f"the ledger is at {observed.sequence}"
                    ),
                    recommended_action="a ledger is append-only; do not renumber it",
                )
            ledger.append(observed.kind, observed.subject_id, refs=observed.refs,
                          counts=dict(observed.counts), enums=dict(observed.enums))
        expected_head = payload.get("headDigest")
        if expected_head is not None and expected_head != ledger.head_digest:
            raise KernelError(
                code="STATE_CONTINUITY_LOST",
                message="context ledger head digest does not match its observations",
                recommended_action="the ledger was edited; do not resume from it",
            )
        return ledger


# --- materialised state ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WorkingState:
    """Everything the decision procedure reads, and nothing else.

    This is the definition that makes "lossless for decisions" a checkable
    claim rather than a slogan: if two states have the same digest, every
    decision taken from them is identical, because :func:`decide` has no other
    input.
    """

    decisions: tuple[tuple[str, str], ...] = ()
    open_obligations: tuple[tuple[str, tuple[str, ...]], ...] = ()
    entities: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    applied_side_effects: tuple[str, ...] = ()
    unresolved_side_effects: tuple[str, ...] = ()
    step_count: int = 0
    tool_invocations: int = 0
    provider_id: str | None = None

    def verdict_for(self, decision_id: str) -> str | None:
        for recorded, verdict in self.decisions:
            if recorded == decision_id:
                return verdict
        return None

    def blocking_obligations(self, subject_id: str) -> tuple[str, ...]:
        return tuple(sorted(
            obligation for obligation, scope in self.open_obligations if subject_id in scope
        ))

    def with_decision(self, decision_id: str, verdict: str) -> WorkingState:
        """Record a decision, keeping the decision list sorted and unique."""

        kept = {name: value for name, value in self.decisions}
        kept[decision_id] = verdict
        return replace(self, decisions=tuple(sorted(kept.items())))

    def to_payload(self) -> dict[str, Any]:
        return {
            "decisions": [[name, verdict] for name, verdict in self.decisions],
            "openObligations": [[name, list(scope)] for name, scope in self.open_obligations],
            "entities": list(self.entities),
            "evidence": list(self.evidence),
            "appliedSideEffects": list(self.applied_side_effects),
            "unresolvedSideEffects": list(self.unresolved_side_effects),
            "stepCount": self.step_count,
            "toolInvocations": self.tool_invocations,
            "providerId": self.provider_id,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def materialise(observations: Sequence[Observation]) -> WorkingState:
    """Fold observations into the state the decision procedure reads.

    The fold is total and order-dependent, which is why the ledger is
    sequenced: replaying the same observations in a different order is a
    different state, and pretending otherwise is how a resumed run "discharges"
    an obligation that was reopened later.
    """

    decisions: dict[str, str] = {}
    obligations: dict[str, tuple[str, ...]] = {}
    entities: set[str] = set()
    evidence: set[str] = set()
    applied: set[str] = set()
    unresolved: set[str] = set()
    steps = 0
    tools = 0
    provider: str | None = None

    for item in observations:
        if item.kind is ObservationKind.DECISION_TAKEN:
            decisions[item.subject_id] = item.enum("verdict") or str(Verdict.PROCEED)
        elif item.kind is ObservationKind.OBLIGATION_OPENED:
            obligations[item.subject_id] = tuple(sorted(set(item.refs)))
        elif item.kind is ObservationKind.OBLIGATION_DISCHARGED:
            obligations.pop(item.subject_id, None)
        elif item.kind is ObservationKind.ENTITY_OBSERVED:
            entities.add(item.subject_id)
        elif item.kind is ObservationKind.ENTITY_RETIRED:
            entities.discard(item.subject_id)
        elif item.kind is ObservationKind.EVIDENCE_RELIED_UPON:
            evidence.add(item.subject_id)
        elif item.kind is ObservationKind.SIDE_EFFECT_APPLIED:
            applied.add(item.subject_id)
        elif item.kind is ObservationKind.SIDE_EFFECT_UNRESOLVED:
            unresolved.add(item.subject_id)
        elif item.kind is ObservationKind.SIDE_EFFECT_RESOLVED:
            unresolved.discard(item.subject_id)
            applied.add(item.subject_id)
        elif item.kind is ObservationKind.TOOL_INVOKED:
            tools += 1
        elif item.kind is ObservationKind.STEP_COMPLETED:
            steps += 1
        elif item.kind is ObservationKind.PROVIDER_SWITCHED:
            provider = item.subject_id

    return WorkingState(
        decisions=tuple(sorted(decisions.items())),
        open_obligations=tuple(sorted(obligations.items())),
        entities=tuple(sorted(entities)),
        evidence=tuple(sorted(evidence)),
        applied_side_effects=tuple(sorted(applied)),
        unresolved_side_effects=tuple(sorted(unresolved)),
        step_count=steps,
        tool_invocations=tools,
        provider_id=provider,
    )


# --- decisions ---------------------------------------------------------------


class Verdict(StrEnum):
    """What the run decided to do about one subject."""

    PROCEED = "PROCEED"
    BLOCK = "BLOCK"
    DEFER = "DEFER"


class DecisionReason(StrEnum):
    """Why a verdict came out the way it did."""

    ALREADY_DECIDED = "ALREADY_DECIDED"
    NO_OBSTACLE = "NO_OBSTACLE"
    OBLIGATION_OPEN = "OBLIGATION_OPEN"
    ENTITY_UNKNOWN = "ENTITY_UNKNOWN"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    SIDE_EFFECT_UNRESOLVED = "SIDE_EFFECT_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """A decision the run is about to take, stated in terms of ids only."""

    decision_id: str
    subject_id: str
    required_entities: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_token(self.decision_id, "decision.decision_id")
        _require_token(self.subject_id, "decision.subject_id")
        for index, item in enumerate(self.required_entities):
            _require_token(item, f"decision.required_entities[{index}]")
        for index, item in enumerate(self.required_evidence):
            _require_token(item, f"decision.required_evidence[{index}]")

    def to_payload(self) -> dict[str, Any]:
        return {
            "decisionId": self.decision_id,
            "subjectId": self.subject_id,
            "requiredEntities": list(self.required_entities),
            "requiredEvidence": list(self.required_evidence),
        }


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of one decision, content-addressed so it can be compared."""

    decision_id: str
    subject_id: str
    verdict: Verdict
    reason: DecisionReason
    missing: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "decisionId": self.decision_id,
            "subjectId": self.subject_id,
            "verdict": str(self.verdict),
            "reason": str(self.reason),
            "missing": list(self.missing),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def decide(state: WorkingState, request: DecisionRequest) -> Decision:
    """Take one decision from ``state`` alone.

    The function is pure and reads nothing but :class:`WorkingState`.  That is
    the whole reason the checkpoint can be small: state that no decision reads
    does not need to survive, and state that a decision reads must.
    """

    recorded = state.verdict_for(request.decision_id)
    if recorded is not None:
        return Decision(request.decision_id, request.subject_id, Verdict(recorded),
                        DecisionReason.ALREADY_DECIDED)
    missing_entities = tuple(sorted(
        item for item in request.required_entities if item not in state.entities
    ))
    if missing_entities:
        return Decision(request.decision_id, request.subject_id, Verdict.DEFER,
                        DecisionReason.ENTITY_UNKNOWN, missing_entities)
    missing_evidence = tuple(sorted(
        item for item in request.required_evidence if item not in state.evidence
    ))
    if missing_evidence:
        return Decision(request.decision_id, request.subject_id, Verdict.DEFER,
                        DecisionReason.EVIDENCE_MISSING, missing_evidence)
    if request.subject_id in state.unresolved_side_effects:
        return Decision(request.decision_id, request.subject_id, Verdict.BLOCK,
                        DecisionReason.SIDE_EFFECT_UNRESOLVED, (request.subject_id,))
    blocking = state.blocking_obligations(request.subject_id)
    if blocking:
        return Decision(request.decision_id, request.subject_id, Verdict.BLOCK,
                        DecisionReason.OBLIGATION_OPEN, blocking)
    return Decision(request.decision_id, request.subject_id, Verdict.PROCEED,
                    DecisionReason.NO_OBSTACLE)


def run_decisions(state: WorkingState,
                  requests: Sequence[DecisionRequest]) -> tuple[tuple[Decision, ...],
                                                                WorkingState]:
    """Take a sequence of decisions, folding each one back into the state."""

    outcomes: list[Decision] = []
    current = state
    for request in requests:
        outcome = decide(current, request)
        outcomes.append(outcome)
        if outcome.reason is not DecisionReason.ALREADY_DECIDED:
            current = current.with_decision(outcome.decision_id, str(outcome.verdict))
    return tuple(outcomes), current


def verify_resume_equivalence(live: Sequence[Decision], restored: Sequence[Decision]) -> None:
    """Raise ``RESUME_DIVERGED`` at the first decision that differs.

    Reporting the first divergence rather than a count matters during an
    incident: the interesting question is always "which decision changed", and
    a boolean cannot answer it.
    """

    if len(live) != len(restored):
        raise KernelError(
            code="RESUME_DIVERGED",
            message=(
                f"resumed run took {len(restored)} decisions, the live run took {len(live)}"
            ),
            recommended_action="do not resume; reconcile the ledger first",
        )
    for index, (before, after) in enumerate(zip(live, restored, strict=True)):
        if before.digest != after.digest:
            raise KernelError(
                code="RESUME_DIVERGED",
                message=(
                    f"decision {index} diverged: live {before.verdict}/{before.reason} "
                    f"vs restored {after.verdict}/{after.reason}"
                ),
                recommended_action="treat the checkpoint as lossy for decisions",
                details={"index": index, "live": before.to_payload(),
                         "restored": after.to_payload()},
            )


# --- binding -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Binding:
    """What the state was produced under, and must be restored under.

    Authority is in here so that a provider failover cannot become a privilege
    escalation.  Swapping the model is allowed; swapping the permission profile
    while claiming to be the same run is not.
    """

    task_spec_version: str
    repo_snapshot_sha: str
    workflow_version: str
    policy_snapshot_hash: str
    workspace_id: str
    environment_id: str
    permission_profile_id: str

    def __post_init__(self) -> None:
        for name in ("task_spec_version", "repo_snapshot_sha", "workflow_version",
                     "policy_snapshot_hash", "workspace_id", "environment_id",
                     "permission_profile_id"):
            require_str(getattr(self, name), f"binding.{name}", max_length=256)

    def to_payload(self) -> dict[str, Any]:
        return {
            "taskSpecVersion": self.task_spec_version,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "workflowVersion": self.workflow_version,
            "policySnapshotHash": self.policy_snapshot_hash,
            "workspaceId": self.workspace_id,
            "environmentId": self.environment_id,
            "permissionProfileId": self.permission_profile_id,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Binding:
        reject_unknown_fields(
            payload,
            {"taskSpecVersion", "repoSnapshotSha", "workflowVersion", "policySnapshotHash",
             "workspaceId", "environmentId", "permissionProfileId"},
            field_name="binding",
        )
        return cls(
            task_spec_version=require_str(payload.get("taskSpecVersion"), "taskSpecVersion"),
            repo_snapshot_sha=require_str(payload.get("repoSnapshotSha"), "repoSnapshotSha"),
            workflow_version=require_str(payload.get("workflowVersion"), "workflowVersion"),
            policy_snapshot_hash=require_str(payload.get("policySnapshotHash"),
                                             "policySnapshotHash"),
            workspace_id=require_str(payload.get("workspaceId"), "workspaceId"),
            environment_id=require_str(payload.get("environmentId"), "environmentId"),
            permission_profile_id=require_str(payload.get("permissionProfileId"),
                                              "permissionProfileId"),
        )


# --- compaction --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompactionPolicy:
    """What compaction is permitted to throw away.

    ``allow_decision_loss`` defaults to ``False`` and must be set explicitly.
    Dropping a decision-bearing kind is a real operation with a real cost, and
    a caller who wants it should have to say so in the request rather than
    discover it in a divergence three hours later.
    """

    keep_last_observations: int = 0
    drop_kinds: frozenset[ObservationKind] = frozenset()
    allow_decision_loss: bool = False

    def __post_init__(self) -> None:
        require_int(self.keep_last_observations, "policy.keep_last_observations", minimum=0)
        require_bool(self.allow_decision_loss, "policy.allow_decision_loss")
        for item in self.drop_kinds:
            if not isinstance(item, ObservationKind):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"unknown observation kind in drop_kinds: {item!r}",
                    recommended_action="use ObservationKind members",
                )

    @property
    def drops_decision_bearing(self) -> tuple[ObservationKind, ...]:
        return tuple(sorted(str(item) for item in self.drop_kinds & DECISION_BEARING_KINDS))

    def to_payload(self) -> dict[str, Any]:
        return {
            "keepLastObservations": self.keep_last_observations,
            "dropKinds": sorted(str(item) for item in self.drop_kinds),
            "allowDecisionLoss": self.allow_decision_loss,
        }


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A restorable, auditable, content-free snapshot of a run's state."""

    checkpoint_id: str
    ledger_id: str
    ledger_head_digest: str
    up_to_sequence: int
    created_at: datetime
    binding: Binding
    state: WorkingState
    retained_tail: tuple[Observation, ...]
    lossy_for_decisions: bool
    policy: CompactionPolicy

    def __post_init__(self) -> None:
        require_identifier(self.checkpoint_id, "checkpoint.checkpoint_id")
        require_int(self.up_to_sequence, "checkpoint.up_to_sequence", minimum=0)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": _CHECKPOINT_SCHEMA,
            "checkpointId": self.checkpoint_id,
            "ledgerId": self.ledger_id,
            "ledgerHeadDigest": self.ledger_head_digest,
            "upToSequence": self.up_to_sequence,
            "createdAt": format_timestamp(self.created_at),
            "binding": self.binding.to_payload(),
            "state": self.state.to_payload(),
            "retainedTail": [item.to_payload() for item in self.retained_tail],
            "lossyForDecisions": self.lossy_for_decisions,
            "policy": self.policy.to_payload(),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def compact(ledger: ContextLedger, policy: CompactionPolicy, *, binding: Binding,
            clock: Clock, checkpoint_id: str = "checkpoint-1") -> Checkpoint:
    """Fold a ledger into a checkpoint, refusing a silently lossy fold.

    A policy that drops a decision-bearing kind without
    ``allow_decision_loss`` raises ``COMPACTION_LOSSY``.  The alternative — do
    it and hope — produces a checkpoint that restores cleanly, verifies
    cleanly, and decides differently.
    """

    if not ledger.verify():
        raise KernelError(
            code="STATE_CONTINUITY_LOST",
            message=f"ledger {ledger.ledger_id!r} fails its own hash chain",
            recommended_action="do not checkpoint an edited ledger",
        )
    dropping = policy.drops_decision_bearing
    if dropping and not policy.allow_decision_loss:
        raise KernelError(
            code="COMPACTION_LOSSY",
            message=(
                f"compaction would drop decision-bearing observations {list(dropping)}; "
                "the checkpoint would not reproduce the run's decisions"
            ),
            retryable=False,
            recommended_action="narrow drop_kinds, or set allow_decision_loss explicitly",
            details={"droppedKinds": list(dropping)},
        )

    kept = tuple(item for item in ledger.observations if item.kind not in policy.drop_kinds)
    state = materialise(kept)
    tail = kept[-policy.keep_last_observations:] if policy.keep_last_observations else ()
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        ledger_id=ledger.ledger_id,
        ledger_head_digest=ledger.head_digest,
        up_to_sequence=ledger.head_sequence,
        created_at=clock.now(),
        binding=binding,
        state=state,
        retained_tail=tuple(tail),
        lossy_for_decisions=bool(dropping),
        policy=policy,
    )


@dataclass(frozen=True, slots=True)
class ContinuityReport:
    """What compaction dropped, named so that the loss is visible.

    A compaction report that only says how much was saved is marketing.  This
    one lists the sequences and kinds that are gone, and states plainly whether
    the remaining state still reproduces the run's decisions.
    """

    ledger_id: str
    checkpoint_id: str
    observations_before: int
    observations_retained: int
    dropped_sequences: tuple[int, ...]
    dropped_by_kind: tuple[tuple[str, int], ...]
    dropped_decision_bearing: tuple[str, ...]
    lossless_for_decisions: bool

    @property
    def observations_dropped(self) -> int:
        return len(self.dropped_sequences)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ledgerId": self.ledger_id,
            "checkpointId": self.checkpoint_id,
            "observationsBefore": self.observations_before,
            "observationsRetained": self.observations_retained,
            "observationsDropped": self.observations_dropped,
            "droppedSequences": list(self.dropped_sequences),
            "droppedByKind": [[kind, count] for kind, count in self.dropped_by_kind],
            "droppedDecisionBearing": list(self.dropped_decision_bearing),
            "losslessForDecisions": self.lossless_for_decisions,
            "claim": (
                "compaction is lossless for decisions only: the checkpoint reproduces "
                "every decision decide() would take, and nothing else"
            ),
        }


def continuity_report(ledger: ContextLedger, checkpoint: Checkpoint) -> ContinuityReport:
    """Describe exactly what ``checkpoint`` no longer holds from ``ledger``."""

    retained_sequences = {item.sequence for item in checkpoint.retained_tail}
    dropped: list[Observation] = [
        item for item in ledger.observations if item.sequence not in retained_sequences
    ]
    by_kind: dict[str, int] = {}
    for item in dropped:
        by_kind[str(item.kind)] = by_kind.get(str(item.kind), 0) + 1
    return ContinuityReport(
        ledger_id=ledger.ledger_id,
        checkpoint_id=checkpoint.checkpoint_id,
        observations_before=len(ledger.observations),
        observations_retained=len(checkpoint.retained_tail),
        dropped_sequences=tuple(item.sequence for item in dropped),
        dropped_by_kind=tuple(sorted(by_kind.items())),
        dropped_decision_bearing=checkpoint.policy.drops_decision_bearing,
        lossless_for_decisions=not checkpoint.lossy_for_decisions,
    )


# --- restore -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RestoredState:
    """A rebuilt run state plus everything the caller must reconcile by hand."""

    checkpoint_id: str
    checkpoint_digest: str
    state: WorkingState
    resume_cursor: int
    binding: Binding
    unresolved_side_effects: tuple[str, ...]
    provider_id: str | None

    @property
    def replay_safe(self) -> bool:
        """False whenever a side effect's outcome is unknown.

        ``restore`` deliberately does not decide this for the caller: replaying
        an effect whose outcome is unknown is how a payment is taken twice.
        """

        return not self.unresolved_side_effects

    def to_payload(self) -> dict[str, Any]:
        return {
            "checkpointId": self.checkpoint_id,
            "checkpointDigest": self.checkpoint_digest,
            "state": self.state.to_payload(),
            "resumeCursor": self.resume_cursor,
            "binding": self.binding.to_payload(),
            "unresolvedSideEffects": list(self.unresolved_side_effects),
            "replaySafe": self.replay_safe,
            "providerId": self.provider_id,
        }


def restore(checkpoint: Checkpoint, *, binding: Binding,
            expected_digest: str | None = None) -> RestoredState:
    """Rebuild state from a checkpoint under a verified binding.

    Every mismatch is a distinct code because they need distinct handling: a
    tampered checkpoint is an integrity incident, a moved snapshot is a
    staleness bug, and a changed permission profile is an authority violation
    that must never be resolved by adopting the new profile.
    """

    if expected_digest is not None and expected_digest != checkpoint.digest:
        raise KernelError(
            code="STATE_CONTINUITY_LOST",
            message="checkpoint digest does not match the expected value",
            recommended_action="do not resume from a checkpoint that has been edited",
        )
    stored = checkpoint.binding
    if (stored.repo_snapshot_sha != binding.repo_snapshot_sha
            or stored.policy_snapshot_hash != binding.policy_snapshot_hash
            or stored.task_spec_version != binding.task_spec_version
            or stored.workflow_version != binding.workflow_version):
        raise KernelError(
            code="STALE_STATE",
            message=(
                "checkpoint was taken under a different snapshot, policy, spec or workflow "
                "version than the one being restored into"
            ),
            retryable=False,
            recommended_action="re-plan against the live snapshot instead of resuming",
            details={"checkpointBinding": stored.to_payload(),
                     "liveBinding": binding.to_payload()},
        )
    if (stored.permission_profile_id != binding.permission_profile_id
            or stored.workspace_id != binding.workspace_id
            or stored.environment_id != binding.environment_id):
        raise KernelError(
            code="AUTHORITY_SCOPE_MISMATCH",
            message=(
                "checkpoint authority does not match the restore target; a resume never "
                "adopts a new permission profile, workspace or environment"
            ),
            retryable=False,
            recommended_action="restore into the same authority, or start a new run",
        )
    return RestoredState(
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_digest=checkpoint.digest,
        state=checkpoint.state,
        resume_cursor=checkpoint.up_to_sequence,
        binding=binding,
        unresolved_side_effects=checkpoint.state.unresolved_side_effects,
        provider_id=checkpoint.state.provider_id,
    )


def assert_replay_safe(restored: RestoredState) -> None:
    """Refuse to resume automatically while a side effect's outcome is unknown."""

    if not restored.replay_safe:
        raise KernelError(
            code="UNRESOLVED_SIDE_EFFECT",
            message=(
                "cannot resume: side effects "
                f"{list(restored.unresolved_side_effects)} have unknown outcomes"
            ),
            retryable=False,
            partial=False,
            recommended_action="reconcile each effect against its target before resuming",
            details={"unresolved": list(restored.unresolved_side_effects)},
        )


def continuation_prompt(restored: RestoredState) -> dict[str, Any]:
    """Provider-neutral continuation.

    It is structured data, not prose, for two reasons: a different provider
    must be able to consume it, and a prompt built from free text would smuggle
    the very content the ledger refuses to hold.
    """

    return {
        "kind": "elmos.continuity.continuation/1",
        "checkpointId": restored.checkpoint_id,
        "resumeCursor": restored.resume_cursor,
        "decisionsTaken": [[name, verdict] for name, verdict in restored.state.decisions],
        "openObligations": [name for name, _ in restored.state.open_obligations],
        "entitiesInPlay": list(restored.state.entities),
        "evidenceRelied": list(restored.state.evidence),
        "unresolvedSideEffects": list(restored.unresolved_side_effects),
        "replaySafe": restored.replay_safe,
        "binding": restored.binding.to_payload(),
    }


# --- diffing -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StateDiff:
    """What changed between two working states."""

    decisions_added: tuple[str, ...]
    decisions_removed: tuple[str, ...]
    decisions_changed: tuple[str, ...]
    obligations_opened: tuple[str, ...]
    obligations_closed: tuple[str, ...]
    entities_added: tuple[str, ...]
    entities_removed: tuple[str, ...]
    evidence_added: tuple[str, ...]
    evidence_removed: tuple[str, ...]

    @property
    def acceptable(self) -> bool:
        """Acceptable means nothing a decision reads disappeared.

        Additions are fine — the run made progress.  Removals are not, because
        no legitimate compaction un-decides a decision or un-observes an
        entity that a later decision depends on.
        """

        return not (self.decisions_removed or self.decisions_changed
                    or self.entities_removed or self.evidence_removed)

    def to_payload(self) -> dict[str, Any]:
        return {
            "decisionsAdded": list(self.decisions_added),
            "decisionsRemoved": list(self.decisions_removed),
            "decisionsChanged": list(self.decisions_changed),
            "obligationsOpened": list(self.obligations_opened),
            "obligationsClosed": list(self.obligations_closed),
            "entitiesAdded": list(self.entities_added),
            "entitiesRemoved": list(self.entities_removed),
            "evidenceAdded": list(self.evidence_added),
            "evidenceRemoved": list(self.evidence_removed),
            "acceptable": self.acceptable,
        }


def state_diff(before: WorkingState, after: WorkingState) -> StateDiff:
    """Compare two states field by field, in a stable order."""

    before_decisions = dict(before.decisions)
    after_decisions = dict(after.decisions)
    before_obligations = {name for name, _ in before.open_obligations}
    after_obligations = {name for name, _ in after.open_obligations}
    return StateDiff(
        decisions_added=tuple(sorted(set(after_decisions) - set(before_decisions))),
        decisions_removed=tuple(sorted(set(before_decisions) - set(after_decisions))),
        decisions_changed=tuple(sorted(
            name for name in set(before_decisions) & set(after_decisions)
            if before_decisions[name] != after_decisions[name]
        )),
        obligations_opened=tuple(sorted(after_obligations - before_obligations)),
        obligations_closed=tuple(sorted(before_obligations - after_obligations)),
        entities_added=tuple(sorted(set(after.entities) - set(before.entities))),
        entities_removed=tuple(sorted(set(before.entities) - set(after.entities))),
        evidence_added=tuple(sorted(set(after.evidence) - set(before.evidence))),
        evidence_removed=tuple(sorted(set(before.evidence) - set(after.evidence))),
    )


# --- durable record ----------------------------------------------------------


def record_checkpoint(checkpoint: Checkpoint, events: EventStore, *, stream_id: str,
                      fencing_token: int) -> Mapping[str, Any]:
    """Append a checkpoint to the run log, idempotently and behind a fence."""

    event = events.append(
        stream_id,
        {"kind": "continuity.checkpoint", "checkpoint": checkpoint.to_payload(),
         "checkpointDigest": checkpoint.digest},
        idempotency_key=checkpoint.digest,
        fencing_token=fencing_token,
    )
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "checkpointDigest": checkpoint.digest,
    }


# --- registry entry point ----------------------------------------------------

_CLOCK: Clock | None = None


def bind_clock(clock: Clock | None) -> None:
    """Bind the clock :func:`handle` stamps checkpoints with."""

    global _CLOCK
    _CLOCK = clock


def bound_clock() -> Clock:
    """Return the bound clock or fail closed.

    Falling back to ``datetime.now`` here would make every checkpoint digest
    depend on when it was taken, which would make a replay unreproducible — the
    exact property this module exists to provide.
    """

    if _CLOCK is None:
        raise KernelError(
            code="CONTINUITY_UNCONFIGURED",
            message="no clock is bound; a checkpoint cannot be stamped deterministically",
            recommended_action="call continuity.bind_clock at startup",
        )
    return _CLOCK


def _decode_policy(payload: Mapping[str, Any]) -> CompactionPolicy:
    reject_unknown_fields(payload, {"keepLastObservations", "dropKinds", "allowDecisionLoss"},
                          field_name="compaction_policy")
    kinds: set[ObservationKind] = set()
    for item in require_str_seq(payload.get("dropKinds", ()), "compaction_policy.dropKinds"):
        if item not in {kind.value for kind in ObservationKind}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown observation kind {item!r} in dropKinds",
                recommended_action=f"use one of {sorted(k.value for k in ObservationKind)}",
            )
        kinds.add(ObservationKind(item))
    return CompactionPolicy(
        keep_last_observations=require_int(payload.get("keepLastObservations", 0),
                                           "compaction_policy.keepLastObservations", minimum=0),
        drop_kinds=frozenset(kinds),
        allow_decision_loss=require_bool(payload.get("allowDecisionLoss", False),
                                         "compaction_policy.allowDecisionLoss"),
    )


def _decode_decision_request(payload: Mapping[str, Any]) -> DecisionRequest:
    reject_unknown_fields(payload,
                          {"decisionId", "subjectId", "requiredEntities", "requiredEvidence"},
                          field_name="decision")
    return DecisionRequest(
        decision_id=payload.get("decisionId"),
        subject_id=payload.get("subjectId"),
        required_entities=require_str_seq(payload.get("requiredEntities", ()),
                                          "decision.requiredEntities"),
        required_evidence=require_str_seq(payload.get("requiredEvidence", ()),
                                          "decision.requiredEvidence"),
    )


@register("model-state-continuity")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Compacts the supplied ledger, restores from the resulting checkpoint, and —
    when decisions are supplied — proves the restored state takes exactly the
    same decisions the live state would have.  A divergence raises rather than
    being reported in an output field, because a caller reading outputs would
    otherwise resume on a state that has already been shown to be different.
    """

    reject_unknown_fields(
        request,
        {"context_ledger", "compaction_policy", "binding", "decisions", "provider_event",
         "checkpoint_id"},
        field_name="model-state-continuity request",
    )
    ledger = ContextLedger.from_payload(
        require_mapping(request.get("context_ledger"), "context_ledger")
    )
    policy = _decode_policy(require_mapping(request.get("compaction_policy", {}),
                                            "compaction_policy"))
    binding = Binding.from_payload(require_mapping(request.get("binding"), "binding"))
    checkpoint_id = require_identifier(request.get("checkpoint_id", "checkpoint-1"),
                                       "checkpoint_id")

    live_state = materialise(ledger.observations)
    requests = tuple(
        _decode_decision_request(require_mapping(item, "decisions[]"))
        for item in request.get("decisions", ())
    )

    provider_event = request.get("provider_event")
    if provider_event is not None:
        mapping = require_mapping(provider_event, "provider_event")
        reject_unknown_fields(mapping, {"fromProvider", "toProvider", "permissionProfileId"},
                              field_name="provider_event")
        target_profile = mapping.get("permissionProfileId")
        if target_profile is not None and target_profile != binding.permission_profile_id:
            raise KernelError(
                code="PROVIDER_FAILOVER_FAILED",
                message=(
                    "provider failover would change the permission profile from "
                    f"{binding.permission_profile_id!r} to {target_profile!r}"
                ),
                retryable=False,
                recommended_action="fail over the model, never the authority",
            )

    checkpoint = compact(ledger, policy, binding=binding, clock=bound_clock(),
                         checkpoint_id=checkpoint_id)
    restored = restore(checkpoint, binding=binding, expected_digest=checkpoint.digest)

    live_decisions, live_after = run_decisions(live_state, requests)
    restored_decisions, restored_after = run_decisions(restored.state, requests)
    verify_resume_equivalence(live_decisions, restored_decisions)

    report = continuity_report(ledger, checkpoint)
    diff = state_diff(live_after, restored_after)
    return {
        "checkpoint": checkpoint.to_payload(),
        "model_state_snapshot": checkpoint.to_payload(),
        "restored_state": restored.to_payload(),
        "continuation_prompt": continuation_prompt(restored),
        "resume_cursor": restored.resume_cursor,
        "state_diff": diff.to_payload(),
        "continuity_report": report.to_payload(),
        "decisions": [item.to_payload() for item in restored_decisions],
        "checkpointDigest": checkpoint.digest,
    }
