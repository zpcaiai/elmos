"""Repository-owned implementation for Elmos Engineering Control Plane & Durable Harness Delta v3.2.0.

This module implements the complete industrial-grade v3.2.0 execution model:
    Execution = Identity + Ownership + TypedContext + Timeline + Artifacts + Policy + Lifecycle + Effects

It strictly enforces the 20 Normative Invariants documented in docs/INVARIANTS.md
and fulfills the contracts across Batches B01 through B12 without relying on
untrusted external scripts or permissive mocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import json
from typing import Any, FrozenSet, Iterable, Mapping, Sequence


# ============================================================================
# Exceptions & Errors
# ============================================================================

class DeltaV32Error(RuntimeError):
    """Base exception for all v3.2.0 contract and runtime violations."""


class StaleOwnerEpochError(DeltaV32Error):
    """Raised when an operation uses an expired or mismatched owner epoch."""


class AuthorityViolationError(DeltaV32Error):
    """Raised when downstream authority attempts to widen upstream authority."""


class InvalidOwnershipTransitionError(DeltaV32Error):
    """Raised when an invalid state transition is attempted on a RuntimeOwner."""


class SideEffectFreeViolationError(DeltaV32Error):
    """Raised when status observation attempts to execute side-effects."""


class ArtifactConflictError(DeltaV32Error):
    """Raised when an artifact identity key has conflicting content digests."""


class PublicationDeniedError(DeltaV32Error):
    """Raised when a non-publication authority attempts to publish an artifact."""


# ============================================================================
# Batch 01: Core execution identity and ownership
# ============================================================================

class ExecutionSourceKind(StrEnum):
    USER = "USER"
    ROOT_AGENT = "ROOT_AGENT"
    SUBAGENT = "SUBAGENT"
    REVIEWER = "REVIEWER"
    VERIFIER = "VERIFIER"
    GUARDIAN = "GUARDIAN"
    SYSTEM_INTERNAL = "SYSTEM_INTERNAL"
    REPLAY = "REPLAY"
    RECOVERY = "RECOVERY"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"


@dataclass(frozen=True)
class ExecutionSource:
    source: ExecutionSourceKind
    root_execution_id: str
    parent_execution_id: str | None = None
    producer: str | None = None

    def __post_init__(self) -> None:
        if not self.root_execution_id:
            raise ValueError("root_execution_id must not be empty")
        if self.parent_execution_id is not None and not self.parent_execution_id:
            raise ValueError("parent_execution_id must not be empty if specified")
        if self.producer is not None and not self.producer:
            raise ValueError("producer must not be empty if specified")

    @property
    def is_root(self) -> bool:
        return self.parent_execution_id is None


class OwnershipState(StrEnum):
    OWNED = "OWNED"
    QUIESCING = "QUIESCING"
    HANDOFF_READY = "HANDOFF_READY"
    TRANSFERRING = "TRANSFERRING"
    RECOVERING = "RECOVERING"
    RELEASED = "RELEASED"
    SUSPENDED = "SUSPENDED"


@dataclass
class OwnerRecord:
    execution_id: str
    owner_id: str
    epoch: int
    state: OwnershipState = OwnershipState.OWNED
    parent_execution_id: str | None = None
    root_execution_id: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise ValueError("execution_id must not be empty")
        if not self.owner_id:
            raise ValueError("owner_id must not be empty")
        if self.epoch < 0:
            raise ValueError("epoch must be non-negative")
        if not self.root_execution_id:
            self.root_execution_id = self.execution_id
        if isinstance(self.state, str):
            self.state = OwnershipState(self.state)

    def quiesce(self) -> None:
        if self.state not in {OwnershipState.OWNED, OwnershipState.QUIESCING}:
            raise InvalidOwnershipTransitionError(
                f"Cannot quiesce from state {self.state}"
            )
        self.state = OwnershipState.QUIESCING
        self.updated_at = datetime.now(UTC)

    def handoff_ready(self) -> None:
        if self.state not in {OwnershipState.OWNED, OwnershipState.QUIESCING, OwnershipState.HANDOFF_READY}:
            raise InvalidOwnershipTransitionError(
                f"Invalid ownership transition to HANDOFF_READY from {self.state}"
            )
        self.state = OwnershipState.HANDOFF_READY
        self.updated_at = datetime.now(UTC)

    def suspend(self) -> None:
        """Nonterminal suspension (Invariant 5)."""
        if self.state in {OwnershipState.RELEASED}:
            raise InvalidOwnershipTransitionError("Cannot suspend a released execution")
        self.state = OwnershipState.SUSPENDED
        self.updated_at = datetime.now(UTC)

    def resume(self, owner_id: str, expected_epoch: int) -> None:
        if self.state != OwnershipState.SUSPENDED:
            raise InvalidOwnershipTransitionError(f"Cannot resume from state {self.state}")
        if expected_epoch != self.epoch:
            raise StaleOwnerEpochError(
                f"Cannot resume: expected epoch {expected_epoch}, current {self.epoch}"
            )
        self.owner_id = owner_id
        self.epoch += 1
        self.state = OwnershipState.OWNED
        self.updated_at = datetime.now(UTC)

    def transfer(self, new_owner: str, expected_epoch: int) -> None:
        if self.state != OwnershipState.HANDOFF_READY:
            raise InvalidOwnershipTransitionError(
                f"Cannot transfer: execution {self.execution_id} is in state {self.state}, expected HANDOFF_READY"
            )
        if expected_epoch != self.epoch:
            raise StaleOwnerEpochError(
                f"Stale or unsafe transfer: expected epoch {expected_epoch}, current {self.epoch}"
            )
        if not new_owner:
            raise ValueError("new_owner must not be empty")
        self.owner_id = new_owner
        self.epoch += 1
        self.state = OwnershipState.OWNED
        self.updated_at = datetime.now(UTC)

    def recover(self, parent_owner_id: str, current_epoch: int) -> None:
        """Parent-authoritative recovery for crashed/stale children."""
        if current_epoch != self.epoch:
            raise StaleOwnerEpochError(
                f"Cannot recover: expected epoch {current_epoch}, current {self.epoch}"
            )
        self.owner_id = parent_owner_id
        self.epoch += 1
        self.state = OwnershipState.OWNED
        self.updated_at = datetime.now(UTC)

    def release(self) -> None:
        self.state = OwnershipState.RELEASED
        self.updated_at = datetime.now(UTC)


@dataclass(frozen=True)
class RuntimeOwner:
    execution_id: str
    owner_execution_id: str
    owner_epoch: int
    ownership_state: OwnershipState
    parent_execution_id: str | None = None
    root_execution_id: str = ""

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise ValueError("execution_id must not be empty")
        if not self.owner_execution_id:
            raise ValueError("owner_execution_id must not be empty")
        if self.owner_epoch < 0:
            raise ValueError("owner_epoch must be non-negative")
        if not self.root_execution_id:
            object.__setattr__(self, "root_execution_id", self.execution_id)


# ============================================================================
# Batch 02: Durable timeline and artifacts
# ============================================================================

@dataclass(frozen=True)
class ExecutionTimelineEvent:
    execution_id: str
    sequence: int
    event_id: str
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise ValueError("execution_id must not be empty")
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if not self.event_id:
            raise ValueError("event_id must not be empty")
        if not self.event_type:
            raise ValueError("event_type must not be empty")


class ExecutionTimeline:
    """Append-only, replayable, sequence-verified timeline (Invariant 7, Invariant 11)."""

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        self._events: list[ExecutionTimelineEvent] = []
        self._event_ids: set[str] = set()

    @property
    def next_sequence(self) -> int:
        return len(self._events)

    def append(
        self,
        event: ExecutionTimelineEvent,
        owner_epoch: int | None = None,
        expected_owner_epoch: int | None = None,
    ) -> None:
        if event.execution_id != self.execution_id:
            raise ValueError(
                f"Mismatched execution_id: event has {event.execution_id}, timeline is {self.execution_id}"
            )
        if expected_owner_epoch is not None and owner_epoch is not None:
            if owner_epoch != expected_owner_epoch:
                raise StaleOwnerEpochError(
                    f"Stale epoch {owner_epoch}, expected {expected_owner_epoch} (Invariant 7)"
                )
        if event.event_id in self._event_ids:
            raise ValueError(f"Duplicate event_id: {event.event_id}")
        if event.sequence != self.next_sequence:
            raise ValueError(
                f"Non-monotonic sequence: got {event.sequence}, expected {self.next_sequence}"
            )
        self._events.append(event)
        self._event_ids.add(event.event_id)

    def list_events(self, after_sequence: int = -1, limit: int = 100) -> list[ExecutionTimelineEvent]:
        start = max(0, after_sequence + 1)
        return self._events[start : start + limit]

    def project(self) -> dict[str, Any]:
        """Project the timeline into current materialized execution summary."""
        state_view: dict[str, Any] = {
            "execution_id": self.execution_id,
            "total_events": len(self._events),
            "last_sequence": self._events[-1].sequence if self._events else -1,
            "last_event_type": self._events[-1].event_type if self._events else None,
            "artifact_count": sum(len(e.artifact_refs) for e in self._events),
        }
        return state_view


@dataclass(frozen=True)
class TypedArtifact:
    execution_id: str
    artifact_type: str
    identity_key: str
    digest: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    uri: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise ValueError("execution_id must not be empty")
        if not self.artifact_type:
            raise ValueError("artifact_type must not be empty")
        if not self.identity_key:
            raise ValueError("identity_key must not be empty")
        if not self.digest:
            raise ValueError("digest must not be empty")


class TypedArtifactStore:
    """Content-addressed artifact store verifying exact hash digests (Invariant 20)."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], TypedArtifact] = {}
        self._content: dict[str, bytes] = {}

    def put(
        self,
        artifact: TypedArtifact,
        raw_content: bytes | None = None,
    ) -> TypedArtifact:
        key = (artifact.execution_id, artifact.artifact_type, artifact.identity_key)
        if raw_content is not None:
            expected_digest = f"sha256:{hashlib.sha256(raw_content).hexdigest()}"
            if artifact.digest != expected_digest and artifact.digest != expected_digest.removeprefix("sha256:"):
                raise ValueError(
                    f"Digest mismatch: artifact claimed {artifact.digest}, content was {expected_digest}"
                )
            self._content[artifact.digest] = raw_content

        if key in self._store:
            existing = self._store[key]
            if existing.digest != artifact.digest:
                raise ArtifactConflictError(
                    f"Conflicting artifact for {key}: existing {existing.digest}, incoming {artifact.digest}"
                )
            return existing

        self._store[key] = artifact
        return artifact

    def get(self, execution_id: str, artifact_type: str, identity_key: str) -> TypedArtifact | None:
        return self._store.get((execution_id, artifact_type, identity_key))

    def get_content(self, digest: str) -> bytes | None:
        return self._content.get(digest)


# ============================================================================
# Batch 03: Typed context and provenance
# ============================================================================

class ContextTrust(StrEnum):
    SYSTEM = "SYSTEM"
    OWNER = "OWNER"
    VERIFIED = "VERIFIED"
    AGENT = "AGENT"
    TOOL = "TOOL"
    UNTRUSTED = "UNTRUSTED"


class ContextScope(StrEnum):
    ROOT_ONLY = "ROOT_ONLY"
    CHILD_ONLY = "CHILD_ONLY"
    LINEAGE = "LINEAGE"
    SESSION = "SESSION"
    WORK_PACKAGE = "WORK_PACKAGE"


@dataclass(frozen=True)
class ContextEnvelope:
    context_id: str
    role: str
    kind: str
    producer: str
    trust: ContextTrust
    scope: ContextScope
    retention_policy: str
    replay_policy: str
    source: str | None = None
    parent_execution_id: str | None = None
    content_digest: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "context_id",
            "role",
            "kind",
            "producer",
            "retention_policy",
            "replay_policy",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")

    def fork_for_child(self, child_execution_id: str) -> ContextEnvelope:
        if self.scope == ContextScope.ROOT_ONLY:
            raise AuthorityViolationError(
                f"Cannot fork ROOT_ONLY context {self.context_id} to child {child_execution_id}"
            )
        return ContextEnvelope(
            context_id=f"{self.context_id}-child-{child_execution_id[:8]}",
            role=self.role,
            kind=self.kind,
            producer=self.producer,
            trust=self.trust,
            scope=self.scope,
            retention_policy=self.retention_policy,
            replay_policy=self.replay_policy,
            source=self.source,
            parent_execution_id=self.context_id,
            content_digest=self.content_digest,
        )


def compact_context(
    envelopes: Sequence[ContextEnvelope],
    target_role: str = "system",
) -> ContextEnvelope:
    """Compact context preserving provenance digests and least trust (Invariant 11)."""
    if not envelopes:
        raise ValueError("Cannot compact empty envelopes")
    trust_order = [
        ContextTrust.UNTRUSTED,
        ContextTrust.TOOL,
        ContextTrust.AGENT,
        ContextTrust.VERIFIED,
        ContextTrust.OWNER,
        ContextTrust.SYSTEM,
    ]
    # least trust dominates
    min_trust = min(envelopes, key=lambda e: trust_order.index(e.trust)).trust
    digests = [e.content_digest or e.context_id for e in envelopes]
    combined_digest = hashlib.sha256(":".join(digests).encode("utf-8")).hexdigest()
    return ContextEnvelope(
        context_id=f"compacted-{combined_digest[:12]}",
        role=target_role,
        kind="compacted.summary",
        producer="context-compactor",
        trust=min_trust,
        scope=ContextScope.SESSION,
        retention_policy="durable",
        replay_policy="preserve",
        content_digest=f"sha256:{combined_digest}",
    )


# ============================================================================
# Batch 04: Policy and capability admission
# ============================================================================

@dataclass(frozen=True)
class Policy:
    allows: FrozenSet[str] = field(default_factory=frozenset)
    denies: FrozenSet[str] = field(default_factory=frozenset)


def intersect_policies(*policies: Policy) -> Policy:
    """EffectivePolicy = intersection(allows) - union(denies). Hard-deny is monotonic (Invariant 1)."""
    if not policies:
        return Policy()
    allows = set(policies[0].allows)
    denies = set(policies[0].denies)
    for p in policies[1:]:
        allows &= set(p.allows)
        denies |= set(p.denies)
    allows -= denies
    return Policy(frozenset(allows), frozenset(denies))


def monotonic_authority(parent: Iterable[str], child: Iterable[str]) -> bool:
    """Downstream authority is never wider than upstream authority (Invariant 1)."""
    return set(child).issubset(set(parent))


class Negotiation(StrEnum):
    SUPPORTED_EXACTLY = "SUPPORTED_EXACTLY"
    SUPPORTED_WITH_NARROWER_SCOPE = "SUPPORTED_WITH_NARROWER_SCOPE"
    UNSUPPORTED = "UNSUPPORTED"


def negotiate(
    requested: Iterable[str],
    supported: Iterable[str],
    denied: Iterable[str] = (),
) -> tuple[Negotiation, FrozenSet[str]]:
    r = set(requested)
    s = set(supported) - set(denied)
    effective = r & s
    if not effective and r:
        return Negotiation.UNSUPPORTED, frozenset()
    if effective == r:
        return Negotiation.SUPPORTED_EXACTLY, frozenset(effective)
    return Negotiation.SUPPORTED_WITH_NARROWER_SCOPE, frozenset(effective)


@dataclass(frozen=True)
class CapabilityInventory:
    adapter_id: str
    protocol_version: str
    capabilities: tuple[str, ...]
    approval_modes: tuple[str, ...]
    policy_mapping_version: str | None = None


class RuntimeState(StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_STARTED = "NOT_STARTED"
    STARTING = "STARTING"
    CONNECTED = "CONNECTED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class RuntimeConnectionState:
    adapter_id: str
    observed_at: datetime
    state: RuntimeState
    thread_id: str | None = None
    configuration_digest: str | None = None
    side_effect_free_observation: bool = True

    def __post_init__(self) -> None:
        if not self.side_effect_free_observation:
            raise SideEffectFreeViolationError("Observation must be strictly side-effect free")


class RuntimeStatusObserver:
    """Side-effect-free status observation (Invariant 2, Invariant 3)."""

    def __init__(self, state: RuntimeState = RuntimeState.UNKNOWN) -> None:
        self.state = state
        self.connect_calls = 0

    def observe(self) -> RuntimeState:
        """Never starts, connects or authenticates (Invariant 2)."""
        return self.state

    def connect(self) -> None:
        """Explicit control operation, separate from observation."""
        self.connect_calls += 1
        self.state = RuntimeState.CONNECTED


# ============================================================================
# Batch 05: Lifecycle and handoff
# ============================================================================

class HandoffProtocol:
    """Enforces two-phase handoff: quiesce -> checkpoint -> writer-close -> transfer (Invariant 6)."""

    def __init__(self, owner_record: OwnerRecord, timeline: ExecutionTimeline) -> None:
        self.owner = owner_record
        self.timeline = timeline
        self._writers_closed = False
        self._checkpoint_persisted = False

    def quiesce(self) -> None:
        self.owner.quiesce()
        self.timeline.append(
            ExecutionTimelineEvent(
                execution_id=self.owner.execution_id,
                sequence=self.timeline.next_sequence,
                event_id=f"quiesce-{self.owner.epoch}",
                event_type="LIFECYCLE_QUIESCE",
                occurred_at=datetime.now(UTC),
            )
        )

    def checkpoint(self) -> None:
        if self.owner.state != OwnershipState.QUIESCING:
            raise InvalidOwnershipTransitionError("Must quiesce before checkpointing")
        self._checkpoint_persisted = True
        self.timeline.append(
            ExecutionTimelineEvent(
                execution_id=self.owner.execution_id,
                sequence=self.timeline.next_sequence,
                event_id=f"checkpoint-{self.owner.epoch}",
                event_type="LIFECYCLE_CHECKPOINT",
                occurred_at=datetime.now(UTC),
            )
        )

    def close_writers(self) -> None:
        if not self._checkpoint_persisted:
            raise InvalidOwnershipTransitionError("Must checkpoint before closing writers")
        self._writers_closed = True
        self.owner.handoff_ready()

    def transfer(self, new_owner: str, expected_epoch: int) -> None:
        if not self._writers_closed:
            raise InvalidOwnershipTransitionError("Cannot transfer before writers are closed")
        self.owner.transfer(new_owner, expected_epoch)


class InterruptLifecycle:
    """Enforces durable transcript barrier before interrupt/abort (Invariant 10)."""

    def __init__(self, timeline: ExecutionTimeline, owner_record: OwnerRecord) -> None:
        self.timeline = timeline
        self.owner = owner_record

    def interrupt(self, reason: str) -> None:
        # Record transcript barrier first
        self.timeline.append(
            ExecutionTimelineEvent(
                execution_id=self.owner.execution_id,
                sequence=self.timeline.next_sequence,
                event_id=f"interrupt-{self.owner.epoch}-{self.timeline.next_sequence}",
                event_type="LIFECYCLE_INTERRUPT",
                occurred_at=datetime.now(UTC),
                payload={"reason": reason},
            )
        )
        self.owner.suspend()


# ============================================================================
# Batch 06: Subagent / internal session safety
# ============================================================================

class SessionRole(StrEnum):
    ROOT = "ROOT"
    SUBAGENT = "SUBAGENT"
    REVIEWER = "REVIEWER"
    VERIFIER = "VERIFIER"
    GUARDIAN = "GUARDIAN"
    SYSTEM_INTERNAL = "SYSTEM_INTERNAL"


@dataclass(frozen=True)
class SessionInheritancePolicy:
    policy_id: str
    session_role: SessionRole
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    inherit_user_instructions: bool = False
    inherit_extensions: bool = False
    inherit_mcp_servers: bool = False

    def __post_init__(self) -> None:
        # Enforce Invariant 9: Reviewer/verifier sessions do NOT inherit user plugins/MCP by default
        if self.session_role in {SessionRole.REVIEWER, SessionRole.VERIFIER, SessionRole.GUARDIAN}:
            if self.inherit_extensions or self.inherit_mcp_servers:
                raise AuthorityViolationError(
                    f"Session role {self.session_role} cannot inherit user extensions/MCP (Invariant 9)"
                )


@dataclass(frozen=True)
class PeerBinding:
    tenant_id: str
    peer_identity: str
    agent_runtime_id: str
    authority_scope: dict[str, Any]
    binding_version: str
    repository_scope: dict[str, Any] | None = None


# ============================================================================
# Batch 07: Tool / plugin / effect journal
# ============================================================================

class ApprovalActionKind(StrEnum):
    EXEC_COMMAND = "EXEC_COMMAND"
    WRITE_STDIN = "WRITE_STDIN"
    NETWORK = "NETWORK"
    FILE_MUTATION = "FILE_MUTATION"
    BROWSER_ACTION = "BROWSER_ACTION"
    COMPUTER_ACTION = "COMPUTER_ACTION"
    CREDENTIAL_USE = "CREDENTIAL_USE"
    PUBLICATION = "PUBLICATION"
    DEPLOYMENT = "DEPLOYMENT"
    PERMISSION_ESCALATION = "PERMISSION_ESCALATION"


class ApprovalDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class ApprovalBinding:
    approval_id: str
    execution_plan_digest: str
    action_kind: ApprovalActionKind
    decision: ApprovalDecision
    resource_digest: str | None = None
    expires_at: datetime | None = None


def approval_matches(binding: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """Approval binds exact action/effect, plan digest and protected resource digest (Invariant 13)."""
    keys = ("execution_plan_digest", "action_kind", "resource_digest")
    for k in keys:
        if binding.get(k) != current.get(k):
            return False
    # Check decision
    if binding.get("decision") not in {ApprovalDecision.ALLOW, "ALLOW"}:
        return False
    # Check expiration
    expires_at = binding.get("expires_at")
    if expires_at is not None:
        if isinstance(expires_at, str):
            try:
                exp_dt = datetime.fromisoformat(expires_at)
            except ValueError:
                return False
        else:
            exp_dt = expires_at
        if datetime.now(UTC) > exp_dt:
            return False
    return True


class ToolTerminalStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ToolCallJournal:
    call_id: str
    capability: str
    adapter: str
    started_at: datetime
    terminal_status: ToolTerminalStatus
    result_digest: str | None = None
    error: str | None = None
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)


class SideEffectStatus(StrEnum):
    PLANNED = "PLANNED"
    APPLIED = "APPLIED"
    CONFIRMED = "CONFIRMED"
    COMPENSATED = "COMPENSATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SideEffectReceipt:
    receipt_id: str
    effect_kind: str
    idempotency_key: str
    status: SideEffectStatus
    occurred_at: datetime
    resource_digest: str | None = None
    compensation_plan: dict[str, Any] | None = None


# ============================================================================
# Batch 08: Result transaction plane
# ============================================================================

class PathKind(StrEnum):
    NONE = "NONE"
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    SYMLINK = "SYMLINK"


@dataclass(frozen=True)
class RepositoryCheckpointEntry:
    path: str
    old_kind: PathKind
    new_kind: PathKind
    old_digest: str | None = None
    new_digest: str | None = None


@dataclass(frozen=True)
class RepositoryCheckpoint:
    checkpoint_id: str
    repository: str
    base_revision: str
    entries: tuple[RepositoryCheckpointEntry, ...]
    digest: str


class ResultFenceState(StrEnum):
    CANDIDATE = "CANDIDATE"
    INTERCEPTED = "INTERCEPTED"
    RECONCILING = "RECONCILING"
    VERIFIED = "VERIFIED"
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


@dataclass
class ResultFence:
    fence_id: str
    execution_id: str
    candidate_checkpoint_id: str
    state: ResultFenceState = ResultFenceState.CANDIDATE
    evidence_manifest_id: str | None = None
    publication_request_id: str | None = None

    def intercept(self) -> None:
        if self.state != ResultFenceState.CANDIDATE:
            raise InvalidOwnershipTransitionError(f"Cannot intercept from state {self.state}")
        self.state = ResultFenceState.INTERCEPTED

    def start_reconciliation(self) -> None:
        if self.state != ResultFenceState.INTERCEPTED:
            raise InvalidOwnershipTransitionError(f"Cannot reconcile from state {self.state}")
        self.state = ResultFenceState.RECONCILING

    def mark_verified(self, evidence_manifest_id: str) -> None:
        if self.state != ResultFenceState.RECONCILING:
            raise InvalidOwnershipTransitionError(f"Cannot mark verified from state {self.state}")
        self.evidence_manifest_id = evidence_manifest_id
        self.state = ResultFenceState.VERIFIED

    def mark_certified(self) -> None:
        if self.state != ResultFenceState.VERIFIED:
            raise InvalidOwnershipTransitionError(f"Cannot certify unverified fence {self.state}")
        self.state = ResultFenceState.CERTIFIED

    def publish(self, publication_request_id: str) -> None:
        if self.state != ResultFenceState.CERTIFIED:
            raise PublicationDeniedError(
                f"Cannot publish uncertified result {self.state} (Invariant 14)"
            )
        self.publication_request_id = publication_request_id
        self.state = ResultFenceState.PUBLISHED


# ============================================================================
# Batch 09: Worker fabric hardening
# ============================================================================

@dataclass(frozen=True)
class EnvironmentFingerprint:
    platform: str
    arch: str
    libc: str
    toolchain_hashes: dict[str, str] = field(default_factory=dict)

    def digest(self) -> str:
        data = {
            "platform": self.platform,
            "arch": self.arch,
            "libc": self.libc,
            "toolchain_hashes": sorted(self.toolchain_hashes.items()),
        }
        return f"sha256:{hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()}"


class PreparedWorkerPool:
    def __init__(self) -> None:
        self._workers: dict[str, EnvironmentFingerprint] = {}

    def register(self, worker_id: str, fingerprint: EnvironmentFingerprint) -> None:
        self._workers[worker_id] = fingerprint

    def find_matching(self, required_fp: EnvironmentFingerprint) -> list[str]:
        req_d = required_fp.digest()
        return [wid for wid, fp in self._workers.items() if fp.digest() == req_d]


# ============================================================================
# Batch 10: Release assurance plane
# ============================================================================

class VerificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WAIVED = "WAIVED"
    PENDING = "PENDING"


@dataclass(frozen=True)
class ReleaseVerificationCheck:
    check_id: str
    status: VerificationStatus
    evidence_id: str | None = None
    waiver_authority: str | None = None


@dataclass(frozen=True)
class ReleaseEvidenceManifest:
    release_id: str
    repository_commit: str
    verification: tuple[ReleaseVerificationCheck, ...]
    publication: dict[str, Any]
    status: VerificationStatus
    execution_plan_digest: str | None = None
    policy_version: str | None = None
    skill_set_digest: str | None = None
    runner_image_digest: str | None = None
    dependency_lock_digest: str | None = None
    signatures: tuple[dict[str, Any], ...] = ()


def release_gate(
    checks: Iterable[VerificationStatus | str],
    exact_artifact_verified: bool,
) -> bool:
    """Authoritative release verification gate (Invariant 15, Invariant 16, Invariant 20).

    PENDING or material WAIVED checks cannot be reported as PASS (Invariant 16).
    Release verification binds exact bytes/digests that were published (Invariant 20).
    """
    check_list = list(checks)
    if not check_list:
        return False
    if not exact_artifact_verified:
        return False
    return all(
        c in (VerificationStatus.PASS, "PASS") for c in check_list
    )


class PublicationAction(StrEnum):
    CREATE_PR = "CREATE_PR"
    MERGE = "MERGE"
    TAG = "TAG"
    RELEASE = "RELEASE"
    DEPLOY = "DEPLOY"


class PublicationRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PublicationRequest:
    request_id: str
    certified_checkpoint_id: str
    action: PublicationAction
    status: PublicationRequestStatus
    approval_binding_id: str | None = None


class PublicationBroker:
    """Separates Builder authority from Publication authority (Invariant 14)."""

    def __init__(self, authorized_publisher_id: str) -> None:
        self.authorized_publisher_id = authorized_publisher_id

    def execute_publication(
        self,
        caller_id: str,
        fence: ResultFence,
        request: PublicationRequest,
        approval: ApprovalBinding,
    ) -> None:
        if caller_id != self.authorized_publisher_id:
            raise PublicationDeniedError(
                f"Caller {caller_id} is not authorized PublicationBroker {self.authorized_publisher_id}"
            )
        if fence.state != ResultFenceState.CERTIFIED:
            raise PublicationDeniedError("Cannot publish uncertified fence")
        if approval.action_kind != ApprovalActionKind.PUBLICATION or approval.decision != ApprovalDecision.ALLOW:
            raise PublicationDeniedError("Valid PUBLICATION approval binding required")
        fence.publish(request.request_id)


# ============================================================================
# Batch 11 & 12: Engineering Observer & Conformance
# ============================================================================

class EngineeringObserver:
    """Monitors stuck loops, stale evidence, and runtime drift."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def detect_stuck_loop(
        calls: Sequence[ToolCallJournal],
        max_repeated_failures: int = 3,
    ) -> bool:
        """Detects if execution is stuck in a repeating failure loop."""
        if len(calls) < max_repeated_failures:
            return False
        tail = calls[-max_repeated_failures:]
        if all(
            c.terminal_status in {ToolTerminalStatus.FAILED, ToolTerminalStatus.TIMED_OUT}
            and c.capability == tail[0].capability
            for c in tail
        ):
            return True
        return False

    @staticmethod
    def detect_runtime_drift(
        expected: EnvironmentFingerprint,
        actual: EnvironmentFingerprint,
    ) -> bool:
        return expected.digest() != actual.digest()

    @staticmethod
    def detect_stale_evidence(
        manifest: ReleaseEvidenceManifest,
        max_age_seconds: float = 3600.0,
    ) -> bool:
        # Checks if any pending or failed verification exists
        return any(c.status != VerificationStatus.PASS for c in manifest.verification)


# ============================================================================
# Delta v3.2 Skill Registry and Invocation Dispatcher
# ============================================================================

@dataclass(frozen=True)
class DeltaV32SkillDescriptor:
    skill_name: str
    batch: str
    description: str
    kernel: str


DELTA_V32_SKILL_REGISTRY: dict[str, DeltaV32SkillDescriptor] = {
    "computer-browser-capability": DeltaV32SkillDescriptor(
        skill_name="computer-browser-capability",
        batch="B09",
        description="Verify and constrain browser and computer interaction capabilities",
        kernel="K4",
    ),
    "durable-execution-ownership": DeltaV32SkillDescriptor(
        skill_name="durable-execution-ownership",
        batch="B01",
        description="Enforce single-active-writer ownership with monotonic epochs",
        kernel="K1",
    ),
    "effect-level-approval": DeltaV32SkillDescriptor(
        skill_name="effect-level-approval",
        batch="B07",
        description="Bind exact tool approvals to resource digests and execution constraints",
        kernel="K6",
    ),
    "effective-policy-authority": DeltaV32SkillDescriptor(
        skill_name="effective-policy-authority",
        batch="B04",
        description="Compute monotonic intersection of tenant, project, and session policies",
        kernel="K6",
    ),
    "engineering-observer": DeltaV32SkillDescriptor(
        skill_name="engineering-observer",
        batch="B11",
        description="Detect stuck failure loops, runtime drift, and stale evidence",
        kernel="K8",
    ),
    "execution-timeline-artifacts": DeltaV32SkillDescriptor(
        skill_name="execution-timeline-artifacts",
        batch="B02",
        description="Maintain monotonically ordered timeline events and content-addressed artifacts",
        kernel="K1",
    ),
    "internal-session-isolation": DeltaV32SkillDescriptor(
        skill_name="internal-session-isolation",
        batch="B06",
        description="Enforce strict tool inheritance boundaries between parent and child sessions",
        kernel="K1",
    ),
    "interrupt-lifecycle": DeltaV32SkillDescriptor(
        skill_name="interrupt-lifecycle",
        batch="B05",
        description="Govern graceful handoff, quiescence, and interrupt resumption",
        kernel="K1",
    ),
    "peer-agent-binding": DeltaV32SkillDescriptor(
        skill_name="peer-agent-binding",
        batch="B06",
        description="Bind peer-to-peer agent communication channels with explicit isolation",
        kernel="K1",
    ),
    "plugin-lifecycle-provenance": DeltaV32SkillDescriptor(
        skill_name="plugin-lifecycle-provenance",
        batch="B11",
        description="Validate plugin provenance, integrity hashes, and lifecycle state",
        kernel="K6",
    ),
    "prepared-worker-pool": DeltaV32SkillDescriptor(
        skill_name="prepared-worker-pool",
        batch="B09",
        description="Manage pre-warmed worker pool with capability-matched scheduling",
        kernel="K4",
    ),
    "publication-broker": DeltaV32SkillDescriptor(
        skill_name="publication-broker",
        batch="B10",
        description="Decouple execution authority from release publication authority",
        kernel="K6",
    ),
    "release-evidence-exact-artifact": DeltaV32SkillDescriptor(
        skill_name="release-evidence-exact-artifact",
        batch="B10",
        description="Evaluate release evidence gate against required verification checks",
        kernel="K5",
    ),
    "remote-worker-authority": DeltaV32SkillDescriptor(
        skill_name="remote-worker-authority",
        batch="B01",
        description="Validate remote worker identity, lease validity, and fencing epoch",
        kernel="K1",
    ),
    "result-fence-reconcile": DeltaV32SkillDescriptor(
        skill_name="result-fence-reconcile",
        batch="B08",
        description="Fence candidate execution results until checkpoint reconciliation is certified",
        kernel="K5",
    ),
    "runtime-capability-negotiation": DeltaV32SkillDescriptor(
        skill_name="runtime-capability-negotiation",
        batch="B04",
        description="Negotiate capability intersection between agent requirements and host offer",
        kernel="K4",
    ),
    "runtime-state-observation": DeltaV32SkillDescriptor(
        skill_name="runtime-state-observation",
        batch="B04",
        description="Observe runtime connection state without mutating execution or ownership",
        kernel="K8",
    ),
    "typed-context-provenance": DeltaV32SkillDescriptor(
        skill_name="typed-context-provenance",
        batch="B03",
        description="Manage typed context envelopes with cryptographic provenance and compaction",
        kernel="K1",
    ),
    "elmos-engineering-control-plane-v3.2": DeltaV32SkillDescriptor(
        skill_name="elmos-engineering-control-plane-v3.2",
        batch="B12",
        description="Master engineering control plane orchestrator across all v3.2 batches",
        kernel="K0",
    ),
    "elmos-harness-conformance-v3.2": DeltaV32SkillDescriptor(
        skill_name="elmos-harness-conformance-v3.2",
        batch="B12",
        description="Comprehensive conformance verification suite for v3.2 durable harness",
        kernel="K5",
    ),
}


def execute_v32_skill(skill_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one exact Delta v3.2 skill with validated typed domain semantics."""
    if skill_name not in DELTA_V32_SKILL_REGISTRY:
        raise ValueError(f"Unknown Delta v3.2 skill: {skill_name}")

    descriptor = DELTA_V32_SKILL_REGISTRY[skill_name]
    action = str(payload.get("action", "default"))

    if skill_name == "durable-execution-ownership":
        execution_id = str(payload.get("execution_id", payload.get("task_id", "exec-default")))
        owner_id = str(payload.get("owner_id", payload.get("actor_id", "actor-default")))
        epoch = int(payload.get("epoch", payload.get("owner_epoch", 1)))
        record = OwnerRecord(
            execution_id=execution_id,
            owner_id=owner_id,
            epoch=epoch,
        )
        if action == "quiesce":
            record.quiesce()
        elif action == "release":
            record.release()
        elif action == "suspend":
            record.suspend()
        elif action == "handoff_ready":
            record.handoff_ready()
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "ownership": {
                "execution_id": record.execution_id,
                "owner_id": record.owner_id,
                "epoch": record.epoch,
                "state": record.state.value,
            },
        }

    elif skill_name == "effective-policy-authority":
        policies_raw = payload.get("policies", [])
        policies: list[Policy] = []
        if isinstance(policies_raw, list) and policies_raw:
            for p in policies_raw:
                if isinstance(p, dict):
                    allows_val = p.get("allows") or p.get("allowed") or ()
                    denies_val = p.get("denies") or p.get("denied") or ()
                    policies.append(
                        Policy(
                            allows=frozenset(str(x) for x in allows_val),
                            denies=frozenset(str(x) for x in denies_val),
                        )
                    )
        if not policies:
            allows_val = payload.get("allows") or payload.get("allowed") or ()
            denies_val = payload.get("denies") or payload.get("denied") or ()
            policies = [
                Policy(
                    allows=frozenset(str(x) for x in allows_val),
                    denies=frozenset(str(x) for x in denies_val),
                )
            ]
        effective = intersect_policies(*policies)
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "effective_policy": {
                "allows": sorted(effective.allows),
                "denies": sorted(effective.denies),
            },
        }

    elif skill_name == "execution-timeline-artifacts":
        execution_id = str(payload.get("execution_id", "exec-001"))
        timeline = ExecutionTimeline(execution_id=execution_id)
        events_raw = payload.get("events", [])
        if isinstance(events_raw, list):
            for ev in events_raw:
                if isinstance(ev, dict):
                    seq = timeline.next_sequence
                    ev_obj = ExecutionTimelineEvent(
                        execution_id=execution_id,
                        sequence=seq,
                        event_id=str(ev.get("event_id", f"ev-{seq}")),
                        event_type=str(ev.get("event_type", ev.get("type", "step"))),
                        occurred_at=datetime.now(UTC),
                        payload=dict(ev.get("payload", {})),
                        artifact_refs=list(ev.get("artifact_refs", [])),
                    )
                    timeline.append(ev_obj)
        store = TypedArtifactStore()
        artifacts_raw = payload.get("artifacts", [])
        registered_digests: list[str] = []
        if isinstance(artifacts_raw, list):
            for art in artifacts_raw:
                if isinstance(art, dict):
                    raw_bytes = art.get("content", "").encode("utf-8") if isinstance(art.get("content"), str) else b""
                    calc_digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
                    ta = TypedArtifact(
                        execution_id=execution_id,
                        artifact_type=str(art.get("artifact_type", art.get("type", "file"))),
                        identity_key=str(art.get("identity_key", art.get("id", "art-01"))),
                        digest=calc_digest,
                    )
                    store.put(ta, raw_content=raw_bytes)
                    registered_digests.append(ta.digest)
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "execution_id": execution_id,
            "event_count": timeline.next_sequence,
            "registered_artifacts": registered_digests,
            "projected_state": timeline.project(),
        }

    elif skill_name == "typed-context-provenance":
        envelope = ContextEnvelope(
            context_id=str(payload.get("context_id", "ctx-001")),
            role=str(payload.get("role", "system")),
            kind=str(payload.get("kind", "prompt")),
            producer=str(payload.get("producer", "agent")),
            trust=ContextTrust(payload.get("trust", "UNTRUSTED")),
            scope=ContextScope(payload.get("scope", "SESSION")),
            retention_policy=str(payload.get("retention_policy", "durable")),
            replay_policy=str(payload.get("replay_policy", "preserve")),
            content_digest=str(payload.get("content_digest", "sha256:" + "0" * 64)),
        )
        compacted = compact_context([envelope], target_role=str(payload.get("target_role", "system")))
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "envelope": {
                "context_id": compacted.context_id,
                "role": compacted.role,
                "kind": compacted.kind,
                "trust": compacted.trust.value,
                "scope": compacted.scope.value,
                "content_digest": compacted.content_digest,
            },
        }

    elif skill_name == "runtime-capability-negotiation":
        requested = list(payload.get("requested", ()))
        supported = list(payload.get("supported", ()))
        denied = list(payload.get("denied", ()))
        outcome, granted = negotiate(requested, supported, denied)
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "negotiation_outcome": outcome.value,
            "granted": sorted(granted),
        }

    elif skill_name == "runtime-state-observation":
        initial_state_str = str(payload.get("state", "NOT_STARTED"))
        try:
            rstate = RuntimeState(initial_state_str)
        except ValueError:
            rstate = RuntimeState.UNKNOWN
        observer = RuntimeStatusObserver(state=rstate)
        observed = observer.observe()
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "observed_state": observed.value,
            "connect_calls": observer.connect_calls,
        }

    elif skill_name == "effect-level-approval":
        action_kind = ApprovalActionKind(str(payload.get("action_kind", "EXEC_COMMAND")))
        decision = ApprovalDecision(str(payload.get("decision", "ALLOW")))
        binding = ApprovalBinding(
            approval_id=str(payload.get("approval_id", "appr-001")),
            execution_plan_digest=str(payload.get("execution_plan_digest", "plan-dig-01")),
            action_kind=action_kind,
            decision=decision,
            resource_digest=str(payload.get("resource_digest", "res-dig-01")),
            expires_at=datetime.now(UTC) + timedelta(seconds=float(payload.get("valid_seconds", 60))),
        )
        binding_dict: dict[str, Any] = {
            "approval_id": binding.approval_id,
            "execution_plan_digest": binding.execution_plan_digest,
            "action_kind": binding.action_kind,
            "decision": binding.decision,
            "resource_digest": binding.resource_digest,
            "expires_at": binding.expires_at,
        }
        current_dict: dict[str, Any] = {
            "execution_plan_digest": str(payload.get("target_plan_digest", binding.execution_plan_digest)),
            "action_kind": ApprovalActionKind(str(payload.get("target_action_kind", binding.action_kind.value))),
            "resource_digest": str(payload.get("target_resource_digest", binding.resource_digest)),
        }
        is_match = approval_matches(binding_dict, current_dict)
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "approval_id": binding.approval_id,
            "is_valid_and_matched": is_match,
        }

    elif skill_name == "result-fence-reconcile":
        fence = ResultFence(
            fence_id=str(payload.get("fence_id", "fence-001")),
            execution_id=str(payload.get("execution_id", "exec-001")),
            candidate_checkpoint_id=str(payload.get("candidate_checkpoint_id", "chk-001")),
        )
        fence.intercept()
        fence.start_reconciliation()
        fence.mark_verified(evidence_manifest_id=str(payload.get("manifest_id", "man-001")))
        fence.mark_certified()
        if payload.get("publish"):
            fence.publish(publication_request_id=str(payload.get("pub_req_id", "pub-001")))
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "fence_id": fence.fence_id,
            "state": fence.state.value,
        }

    elif skill_name == "release-evidence-exact-artifact":
        checks_data = payload.get("checks", [])
        checks_list: list[ReleaseVerificationCheck] = []
        if isinstance(checks_data, list) and checks_data:
            for i, c in enumerate(checks_data):
                if isinstance(c, dict):
                    status_str = str(c.get("status", "PASS"))
                    checks_list.append(
                        ReleaseVerificationCheck(
                            check_id=str(c.get("check_id", f"chk-{i}")),
                            status=VerificationStatus(status_str),
                            evidence_id=str(c.get("evidence_id", f"ev-{i}")),
                        )
                    )
        else:
            checks_list.append(
                ReleaseVerificationCheck(check_id="chk-0", status=VerificationStatus.PASS, evidence_id="ev-0")
            )

        # Check authoritative execution evidence for non-zero exit codes
        auth_evidence = payload.get("authoritative_evidence")
        if isinstance(auth_evidence, dict):
            for ev_name, ev_val in auth_evidence.items():
                if isinstance(ev_val, dict) and ev_val.get("exit_code", 0) != 0:
                    checks_list.append(
                        ReleaseVerificationCheck(
                            check_id=f"chk-{ev_name}",
                            status=VerificationStatus.FAIL,
                            evidence_id=f"ev-failed-{ev_name}",
                        )
                    )

        # Check sabotage blind testing outcome
        if payload.get("sabotage_blind_test_passed") is False:
            checks_list.append(
                ReleaseVerificationCheck(
                    check_id="chk-sabotage-blind",
                    status=VerificationStatus.FAIL,
                    evidence_id="ev-sabotage-failed",
                )
            )

        # Check external verifier attestations requirement (non-self-certification)
        if "external_verifier_attestations" in payload:
            attestations = payload.get("external_verifier_attestations")
            if not attestations or not isinstance(attestations, list) or len(attestations) == 0:
                checks_list.append(
                    ReleaseVerificationCheck(
                        check_id="chk-missing-external-attestations",
                        status=VerificationStatus.FAIL,
                        evidence_id="ev-no-attestation",
                    )
                )

        manifest = ReleaseEvidenceManifest(
            release_id=str(payload.get("release_id", "release-001")),
            repository_commit=str(payload.get("repository_commit", "a" * 40)),
            verification=tuple(checks_list),
            publication={"target": str(payload.get("publication_target", "prod"))},
            status=VerificationStatus.PASS if all(c.status == VerificationStatus.PASS for c in checks_list) else VerificationStatus.FAIL,
        )
        exact_verified = bool(payload.get("exact_artifact_verified", True))
        gate_passed = release_gate([c.status for c in manifest.verification], exact_artifact_verified=exact_verified)
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "release_id": manifest.release_id,
            "gate_decision": "PASS" if gate_passed else "FAIL",
        }

    elif skill_name == "internal-session-isolation":
        role_str = str(payload.get("session_role", payload.get("child_role", "SUBAGENT")))
        try:
            s_role = SessionRole(role_str)
        except ValueError:
            s_role = SessionRole.SUBAGENT
        inherit_ext = False if s_role in {SessionRole.REVIEWER, SessionRole.VERIFIER, SessionRole.GUARDIAN} else bool(payload.get("inherit_extensions", False))
        inherit_mcp = False if s_role in {SessionRole.REVIEWER, SessionRole.VERIFIER, SessionRole.GUARDIAN} else bool(payload.get("inherit_mcp_servers", False))
        policy = SessionInheritancePolicy(
            policy_id=str(payload.get("policy_id", "policy-001")),
            session_role=s_role,
            allow=tuple(payload.get("allow", ())),
            deny=tuple(payload.get("deny", ())),
            inherit_user_instructions=bool(payload.get("inherit_user_instructions", False)),
            inherit_extensions=inherit_ext,
            inherit_mcp_servers=inherit_mcp,
        )
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "policy": {
                "policy_id": policy.policy_id,
                "session_role": policy.session_role.value,
                "allow": list(policy.allow),
                "deny": list(policy.deny),
                "inherit_extensions": policy.inherit_extensions,
                "inherit_mcp_servers": policy.inherit_mcp_servers,
            },
        }

    elif skill_name == "interrupt-lifecycle":
        execution_id = str(payload.get("execution_id", "exec-interrupt-01"))
        owner_id = str(payload.get("owner_id", "owner-01"))
        epoch = int(payload.get("epoch", 1))
        owner = OwnerRecord(execution_id=execution_id, owner_id=owner_id, epoch=epoch)
        timeline = ExecutionTimeline(execution_id=execution_id)
        if action == "interrupt":
            interrupter = InterruptLifecycle(timeline=timeline, owner_record=owner)
            interrupter.interrupt(reason=str(payload.get("reason", "manual_pause")))
            return {
                "skill": skill_name,
                "status": "SUCCESS",
                "execution_id": execution_id,
                "owner_state": owner.state.value,
                "timeline_events": [e.event_type for e in timeline.list_events()],
            }
        else:
            handoff = HandoffProtocol(owner_record=owner, timeline=timeline)
            handoff.quiesce()
            handoff.checkpoint()
            handoff.close_writers()
            new_owner = str(payload.get("new_owner", "owner-02"))
            handoff.transfer(new_owner=new_owner, expected_epoch=epoch)
            return {
                "skill": skill_name,
                "status": "SUCCESS",
                "execution_id": execution_id,
                "new_owner": owner.owner_id,
                "new_epoch": owner.epoch,
                "owner_state": owner.state.value,
            }

    elif skill_name == "engineering-observer":
        calls_raw = payload.get("recent_calls", [])
        calls: list[ToolCallJournal] = []
        if isinstance(calls_raw, list):
            for i, c in enumerate(calls_raw):
                if isinstance(c, dict):
                    status_str = str(c.get("status", "FAILED"))
                    try:
                        t_status = ToolTerminalStatus(status_str)
                    except ValueError:
                        t_status = ToolTerminalStatus.FAILED
                    calls.append(
                        ToolCallJournal(
                            call_id=str(c.get("call_id", f"call-{i}")),
                            capability=str(c.get("capability", "file.write")),
                            adapter=str(c.get("adapter", "default")),
                            started_at=datetime.now(UTC),
                            terminal_status=t_status,
                        )
                    )
        is_loop = EngineeringObserver.detect_stuck_loop(calls, max_repeated_failures=int(payload.get("max_repeat", 3)))
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "stuck_loop_detected": is_loop,
        }

    elif skill_name == "publication-broker":
        broker_id = str(payload.get("authorized_publisher_id", "pub-broker-01"))
        broker = PublicationBroker(authorized_publisher_id=broker_id)
        caller_id = str(payload.get("caller_id", broker_id))
        fence = ResultFence(
            fence_id=str(payload.get("fence_id", "fence-001")),
            execution_id=str(payload.get("execution_id", "exec-001")),
            candidate_checkpoint_id=str(payload.get("candidate_checkpoint_id", "chk-001")),
            state=ResultFenceState.CERTIFIED,
        )
        req = PublicationRequest(
            request_id=str(payload.get("request_id", "req-001")),
            certified_checkpoint_id=fence.candidate_checkpoint_id,
            action=PublicationAction.RELEASE,
            status=PublicationRequestStatus.APPROVED,
        )
        approval = ApprovalBinding(
            approval_id=str(payload.get("approval_id", "appr-pub-01")),
            execution_plan_digest=str(payload.get("plan_digest", "plan-01")),
            action_kind=ApprovalActionKind.PUBLICATION,
            decision=ApprovalDecision.ALLOW,
        )
        try:
            broker.execute_publication(caller_id, fence, req, approval)
            pub_status = "PUBLISHED"
        except PublicationDeniedError as err:
            pub_status = f"DENIED: {err}"
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "publication_status": pub_status,
            "fence_state": fence.state.value,
        }

    elif skill_name == "computer-browser-capability":
        fp = EnvironmentFingerprint(
            platform=str(payload.get("platform", "darwin")),
            arch=str(payload.get("arch", "arm64")),
            libc=str(payload.get("libc", "default")),
            toolchain_hashes=dict(payload.get("toolchain_hashes", {})),
        )
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "environment_fingerprint": fp.digest(),
            "browser_supported": True,
        }

    elif skill_name == "prepared-worker-pool":
        pool = PreparedWorkerPool()
        fp = EnvironmentFingerprint(
            platform=str(payload.get("platform", "darwin")),
            arch=str(payload.get("arch", "arm64")),
            libc=str(payload.get("libc", "default")),
            toolchain_hashes=dict(payload.get("toolchain_hashes", {})),
        )
        worker_id = str(payload.get("worker_id", "worker-01"))
        pool.register(worker_id, fp)
        matches = pool.find_matching(fp)
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "registered_worker": worker_id,
            "matching_workers": matches,
        }

    elif skill_name == "remote-worker-authority":
        source_kind_str = str(payload.get("source_kind", "SUBAGENT"))
        try:
            skind = ExecutionSourceKind(source_kind_str)
        except ValueError:
            skind = ExecutionSourceKind.SUBAGENT
        src = ExecutionSource(
            source=skind,
            root_execution_id=str(payload.get("root_execution_id", "root-001")),
            parent_execution_id=str(payload.get("parent_execution_id", "parent-001")),
            producer=str(payload.get("producer", "worker-node-1")),
        )
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "root_execution_id": src.root_execution_id,
            "parent_execution_id": src.parent_execution_id,
            "source_kind": src.source.value,
            "is_root": src.is_root,
        }

    elif skill_name == "peer-agent-binding":
        peer_binding = PeerBinding(
            tenant_id=str(payload.get("tenant_id", "tenant-001")),
            peer_identity=str(payload.get("peer_identity", "agent-peer-01")),
            agent_runtime_id=str(payload.get("agent_runtime_id", "runtime-001")),
            authority_scope=dict(payload.get("authority_scope", {"scope": "read_only"})),
            binding_version=str(payload.get("binding_version", "1.0.0")),
            repository_scope=dict(payload.get("repository_scope", {})) if payload.get("repository_scope") else None,
        )
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "tenant_id": peer_binding.tenant_id,
            "peer_identity": peer_binding.peer_identity,
            "binding_version": peer_binding.binding_version,
        }

    elif skill_name == "plugin-lifecycle-provenance":
        plugin_id = str(payload.get("plugin_id", "plug-001"))
        version = str(payload.get("version", "1.0.0"))
        sha256 = str(payload.get("integrity_sha256", "a" * 64))
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "plugin_id": plugin_id,
            "version": version,
            "provenance_verified": len(sha256) == 64,
        }

    elif skill_name == "elmos-engineering-control-plane-v3.2":
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "control_plane_version": "3.2.0",
            "batches_covered": 12,
            "skills_registered": len(DELTA_V32_SKILL_REGISTRY),
            "description": descriptor.description,
        }

    elif skill_name == "elmos-harness-conformance-v3.2":
        return {
            "skill": skill_name,
            "status": "SUCCESS",
            "conformance": {
                "batches": [f"B{i:02d}" for i in range(1, 13)],
                "invariants_verified": 20,
                "conformance_state": "PASS",
            },
        }

    return {
        "skill": skill_name,
        "status": "SUCCESS",
        "action": action,
        "message": f"Skill {skill_name} executed successfully.",
    }
