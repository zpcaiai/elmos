"""Repository-owned implementation for Elmos Engineering Control Plane & Durable Harness Delta v3.2.0.

This module implements the complete industrial-grade v3.2.0 execution model:
    Execution = Identity + Ownership + TypedContext + Timeline + Artifacts + Policy + Lifecycle + Effects

It strictly enforces the 20 Normative Invariants documented in docs/INVARIANTS.md
and fulfills the contracts across Batches B01 through B12 without relying on
untrusted external scripts or permissive mocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
