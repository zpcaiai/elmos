"""Domain models and value objects shared across all 296 skill handlers.

Provides the typed entities, events, commands and state machines that each
skill handler module imports.  Every skill follows the same lifecycle
(REQUESTED → PROFILED → PLANNED → RUNNING → VERIFYING → EVIDENCE_SEALED →
COMPLETED | BLOCKED | FAILED | CANCELLED) with tenant isolation, append-only
event journal, content-addressed artifacts, and fail-closed defaults.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Execution lifecycle state machine
# ---------------------------------------------------------------------------

class RunState(str, enum.Enum):
    REQUESTED = "REQUESTED"
    PROFILED = "PROFILED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    EVIDENCE_SEALED = "EVIDENCE_SEALED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({
    RunState.COMPLETED, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED,
})

ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.REQUESTED: frozenset({RunState.PROFILED, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED}),
    RunState.PROFILED: frozenset({RunState.PLANNED, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED}),
    RunState.PLANNED: frozenset({RunState.RUNNING, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED}),
    RunState.RUNNING: frozenset({RunState.PAUSED, RunState.VERIFYING, RunState.REPAIRING, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED}),
    RunState.PAUSED: frozenset({RunState.RUNNING, RunState.CANCELLED}),
    RunState.VERIFYING: frozenset({RunState.EVIDENCE_SEALED, RunState.REPAIRING, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED}),
    RunState.REPAIRING: frozenset({RunState.RUNNING, RunState.VERIFYING, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED}),
    RunState.EVIDENCE_SEALED: frozenset({RunState.COMPLETED, RunState.BLOCKED, RunState.FAILED}),
}


# ---------------------------------------------------------------------------
# Core value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TenantScope:
    tenant_id: str
    project_id: str
    actor_id: str = "system"
    revision_set_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.project_id:
            raise ValueError("tenant_id and project_id are required")


@dataclass(frozen=True)
class ExecutionEpoch:
    epoch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    authority_digest: str = ""


@dataclass(frozen=True)
class ContentDigest:
    algorithm: str = "sha256"
    value: str = ""

    @staticmethod
    def of(data: bytes) -> "ContentDigest":
        return ContentDigest("sha256", hashlib.sha256(data).hexdigest())

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.value}"


@dataclass(frozen=True)
class Artifact:
    path: str
    content_type: str
    digest: ContentDigest
    immutable: bool = True
    evidence_bound: bool = True


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    tenant_id: str
    goal_id: str
    revision_set_id: str
    run_id: str
    sequence: int
    occurred_at: str
    producer: str
    payload_hash: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProofObligation:
    obligation_id: str
    claim: str
    status: str  # PENDING, SATISFIED, VIOLATED, UNKNOWN
    evidence_digest: str = ""
    verifier: str = ""


@dataclass(frozen=True)
class SideEffect:
    effect_id: str
    effect_type: str  # FILE_WRITE, API_CALL, DB_MUTATION, EVENT_EMIT
    idempotency_key: str
    status: str  # PENDING, COMMITTED, COMPENSATED, UNKNOWN
    reconciled: bool = False


@dataclass
class UsageLedger:
    tokens_in: int = 0
    tokens_out: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    wall_clock_ms: float = 0.0
    estimated_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Skill run aggregate
# ---------------------------------------------------------------------------

@dataclass
class SkillRun:
    run_id: str
    skill_name: str
    scope: TenantScope
    epoch: ExecutionEpoch
    state: RunState = RunState.REQUESTED
    events: list[Event] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    obligations: list[ProofObligation] = field(default_factory=list)
    side_effects: list[SideEffect] = field(default_factory=list)
    usage: UsageLedger = field(default_factory=UsageLedger)
    checkpoints: list[str] = field(default_factory=list)
    error: str | None = None
    _sequence: int = 0

    def transition(self, target: RunState) -> None:
        if target not in ALLOWED_TRANSITIONS.get(self.state, frozenset()):
            raise ValueError(f"invalid transition {self.state} -> {target}")
        self.state = target

    def emit_event(self, event_type: str, payload: Mapping[str, Any] | None = None) -> Event:
        self._sequence += 1
        payload = payload or {}
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        evt = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            tenant_id=self.scope.tenant_id,
            goal_id=f"goal-{self.skill_name}",
            revision_set_id=self.scope.revision_set_id,
            run_id=self.run_id,
            sequence=self._sequence,
            occurred_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            producer=self.skill_name,
            payload_hash=hashlib.sha256(payload_bytes).hexdigest(),
            payload=payload,
        )
        self.events.append(evt)
        return evt

    def add_artifact(self, path: str, content: bytes, content_type: str = "application/json") -> Artifact:
        artifact = Artifact(path, content_type, ContentDigest.of(content))
        self.artifacts.append(artifact)
        return artifact

    def add_obligation(self, claim: str, status: str = "PENDING") -> ProofObligation:
        obl = ProofObligation(str(uuid.uuid4()), claim, status)
        self.obligations.append(obl)
        return obl

    def checkpoint(self) -> str:
        cp_id = f"cp-{self._sequence}"
        self.checkpoints.append(cp_id)
        self.emit_event("Checkpointed", {"checkpoint_id": cp_id})
        return cp_id

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def all_obligations_satisfied(self) -> bool:
        return all(o.status == "SATISFIED" for o in self.obligations)

    @property
    def all_side_effects_settled(self) -> bool:
        return all(se.status in ("COMMITTED", "COMPENSATED") and se.reconciled for se in self.side_effects)

    @property
    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "skill": self.skill_name,
            "tenant_id": self.scope.tenant_id,
            "project_id": self.scope.project_id,
            "state": self.state.value,
            "event_count": len(self.events),
            "artifact_count": len(self.artifacts),
            "artifact_digests": [str(a.digest) for a in self.artifacts],
            "obligations": [{"claim": o.claim, "status": o.status} for o in self.obligations],
            "side_effects_settled": self.all_side_effects_settled,
            "usage": {
                "tokens_in": self.usage.tokens_in,
                "tokens_out": self.usage.tokens_out,
                "model_calls": self.usage.model_calls,
                "tool_calls": self.usage.tool_calls,
                "wall_clock_ms": self.usage.wall_clock_ms,
                "estimated_cost_usd": self.usage.estimated_cost_usd,
            },
            "epoch_id": self.epoch.epoch_id,
        }


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def new_run(skill_name: str, inputs: Mapping[str, Any]) -> SkillRun:
    tenant_id = inputs.get("tenant_id") or "default-tenant"
    project_id = inputs.get("project_id") or "default-project"
    scope = TenantScope(
        tenant_id=tenant_id,
        project_id=project_id,
        actor_id=inputs.get("actor_id", "system"),
        revision_set_id=inputs.get("revision_set_id", ""),
    )
    return SkillRun(
        run_id=str(uuid.uuid4()),
        skill_name=skill_name,
        scope=scope,
        epoch=ExecutionEpoch(),
    )
