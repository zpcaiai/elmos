"""K4 agent execution domain model.

This module deliberately stops at the domain/effect boundary.  It can validate
and persist task/workspace state, but requests to an external agent host are
represented as :class:`AgentEffectRequest` objects whose status is ``NOT_RUN``.
Repository or model output never receives authority merely by being parsed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from .contracts import (
    AgentTask,
    EvidenceRecord,
    ExecutionContext,
    ProofCarryingAgentResult,
    ResourceScope,
)
from .assurance import ReleaseReviewDecision
from .canonical import digest_object, require_sha256_digest
from .errors import (
    AuthorizationError,
    ConflictError,
    UnknownCapabilityError as FoundationUnknownCapabilityError,
    ValidationError,
)
from .registry import CAPABILITY_REGISTRY, OperationSpec


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentValidationError(f"{name} is required", code="INVALID_INPUT")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AgentValidationError(f"{name} must be timezone-aware", code="INVALID_TIME")
    return value


def _scope_key(scope: ResourceScope) -> tuple[str, str, str]:
    return (scope.tenant_id, scope.project_id, scope.repository_id)


def _same_scope(left: ResourceScope, right: ResourceScope) -> bool:
    return _scope_key(left) == _scope_key(right) and left.input_revision == right.input_revision


def _stable_digest(domain: str, value: Mapping[str, Any]) -> str:
    return digest_object(value, domain=domain)


class AgentRuntimeError(RuntimeError):
    """Base fail-closed K4 error with a stable machine code."""

    def __init__(self, message: str, *, code: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class AgentValidationError(ValidationError):
    pass


class AgentAuthorizationError(AuthorizationError):
    pass


class StaleFenceError(ConflictError):
    pass


class AgentConflictError(ConflictError):
    pass


class UnknownCapabilityError(FoundationUnknownCapabilityError):
    pass


class AgentState(StrEnum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PARKED = "PARKED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    QUARANTINED = "QUARANTINED"


TERMINAL_AGENT_STATES = frozenset(
    {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.ABORTED, AgentState.QUARANTINED}
)

_STATE_TRANSITIONS: Mapping[AgentState, frozenset[AgentState]] = MappingProxyType(
    {
        AgentState.CREATED: frozenset({AgentState.READY, AgentState.ABORTED, AgentState.QUARANTINED}),
        AgentState.READY: frozenset({AgentState.RUNNING, AgentState.ABORTED, AgentState.QUARANTINED}),
        AgentState.RUNNING: frozenset(
            {
                AgentState.WAITING,
                AgentState.SUCCEEDED,
                AgentState.FAILED,
                AgentState.ABORTED,
                AgentState.QUARANTINED,
            }
        ),
        AgentState.WAITING: frozenset(
            {
                AgentState.RUNNING,
                AgentState.PARKED,
                AgentState.FAILED,
                AgentState.ABORTED,
                AgentState.QUARANTINED,
            }
        ),
        AgentState.PARKED: frozenset(
            {AgentState.READY, AgentState.ABORTED, AgentState.QUARANTINED}
        ),
        AgentState.SUCCEEDED: frozenset(),
        AgentState.FAILED: frozenset(),
        AgentState.ABORTED: frozenset(),
        AgentState.QUARANTINED: frozenset(),
    }
)


class EffortLevel(IntEnum):
    LOW = 10
    MEDIUM = 20
    HIGH = 30
    XHIGH = 40


class SecurityCeiling(IntEnum):
    REPOSITORY_READ = 10
    REPOSITORY_WRITE = 20
    AGENT_CONTROL = 30
    EXTERNAL_SIDE_EFFECT = 40


class SchedulingMode(StrEnum):
    BLOCKING = "BLOCKING"
    ASYNC = "ASYNC"


class EffectStatus(StrEnum):
    NOT_RUN = "NOT_RUN"


class AgentEffectKind(StrEnum):
    SPAWN = "SPAWN"
    STEER = "STEER"
    PARK = "PARK"
    REVIVE = "REVIVE"
    KILL = "KILL"
    RELEASE = "RELEASE"
    MERGE = "MERGE"
    ORPHAN_REAP = "ORPHAN_REAP"


@dataclass(frozen=True, slots=True)
class AgentCapability:
    capability_id: str
    operation_names: tuple[str, ...]
    tools: tuple[str, ...] = ()
    write_capable: bool = False
    security_ceiling: SecurityCeiling = SecurityCeiling.REPOSITORY_READ

    def __post_init__(self) -> None:
        _required(self.capability_id, "capability_id")
        if not self.operation_names or len(set(self.operation_names)) != len(self.operation_names):
            raise AgentValidationError(
                "capability operations must be non-empty and unique", code="INVALID_CAPABILITY"
            )
        if self.write_capable and self.security_ceiling < SecurityCeiling.REPOSITORY_WRITE:
            raise AgentValidationError(
                "write capability requires repository-write security", code="INVALID_CAPABILITY"
            )


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    allowed_models: tuple[str, ...]
    effort_ceiling: EffortLevel
    security_ceiling: SecurityCeiling
    fallback_chain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.allowed_models or len(set(self.allowed_models)) != len(self.allowed_models):
            raise AgentValidationError("allowed_models must be non-empty and unique", code="INVALID_MODEL_POLICY")
        unknown = set(self.fallback_chain).difference(self.allowed_models)
        if unknown:
            raise AgentValidationError(
                "fallback model is outside the allowlist",
                code="MODEL_FALLBACK_ESCALATION",
                details={"models": sorted(unknown)},
            )

    def select(
        self,
        candidates: Sequence[str],
        *,
        effort: EffortLevel,
        security: SecurityCeiling,
    ) -> str:
        if effort > self.effort_ceiling:
            raise AgentAuthorizationError("effort ceiling exceeded", code="EFFORT_CEILING_EXCEEDED")
        if security > self.security_ceiling:
            raise AgentAuthorizationError("security ceiling exceeded", code="SECURITY_CEILING_EXCEEDED")
        available = tuple(candidates) + self.fallback_chain
        for candidate in available:
            if candidate in self.allowed_models:
                return candidate
        raise AgentAuthorizationError("no authorized model candidate", code="MODEL_NOT_AUTHORIZED")


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    agent_id: str
    namespace: str
    name: str
    version: str
    capability_ids: tuple[str, ...]
    authority_profile: str
    model_policy: ModelPolicy
    max_depth: int = 1
    allow_self_recursion: bool = False
    autoload_skills: tuple[str, ...] = ()
    read_summary_required: bool = True

    def __post_init__(self) -> None:
        for value, name in (
            (self.agent_id, "agent_id"),
            (self.namespace, "namespace"),
            (self.name, "name"),
            (self.version, "version"),
            (self.authority_profile, "authority_profile"),
        ):
            _required(value, name)
        if not self.capability_ids or len(set(self.capability_ids)) != len(self.capability_ids):
            raise AgentValidationError("capability_ids must be non-empty and unique", code="INVALID_AGENT")
        if self.max_depth < 0:
            raise AgentValidationError("max_depth cannot be negative", code="INVALID_AGENT")

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.namespace, self.name, self.version)


class AgentDefinitionRegistry:
    """Exact namespace/version registry; no silent name-only first-wins lookup."""

    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str, str], AgentDefinition] = {}
        self._capabilities: dict[str, AgentCapability] = {}

    def register_capability(self, capability: AgentCapability) -> None:
        if capability.capability_id in self._capabilities:
            raise AgentConflictError("duplicate capability", code="CAPABILITY_COLLISION")
        self._capabilities[capability.capability_id] = capability

    def register_definition(self, definition: AgentDefinition) -> None:
        if definition.identity in self._definitions:
            raise AgentConflictError("duplicate agent definition", code="AGENT_DEFINITION_COLLISION")
        missing = set(definition.capability_ids).difference(self._capabilities)
        if missing:
            raise AgentValidationError(
                "agent references unknown capabilities",
                code="UNKNOWN_AGENT_CAPABILITY",
                details={"capabilities": sorted(missing)},
            )
        self._definitions[definition.identity] = definition

    def resolve(self, namespace: str, name: str, version: str) -> AgentDefinition:
        try:
            return self._definitions[(namespace, name, version)]
        except KeyError as exc:
            raise AgentValidationError("agent definition not found", code="AGENT_NOT_FOUND") from exc

    def discover(self, name: str) -> tuple[AgentDefinition, ...]:
        return tuple(sorted((item for item in self._definitions.values() if item.name == name), key=lambda x: x.identity))

    def capability(self, capability_id: str) -> AgentCapability:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise AgentValidationError("capability not found", code="CAPABILITY_NOT_FOUND") from exc


@dataclass(frozen=True, slots=True)
class WorkspaceOwner:
    scope: ResourceScope
    workspace_id: str
    agent_id: str
    authority_profile: str
    generation: int
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceLease:
    scope: ResourceScope
    workspace_id: str
    lease_id: str
    agent_id: str
    fence_token: int
    generation: int
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    scope: ResourceScope
    workspace_id: str
    snapshot_id: str
    revision_digest: str
    owner_agent_id: str
    lease_id: str
    fence_token: int
    created_at: datetime


class WorkspaceAuthorityPort(Protocol):
    """Durable adapter boundary.  Implementations must preserve CAS semantics."""

    durable: bool

    def claim_owner(self, context: ExecutionContext, *, agent_id: str, now: datetime) -> WorkspaceOwner: ...

    def issue_lease(
        self, context: ExecutionContext, *, agent_id: str, ttl: timedelta, now: datetime
    ) -> WorkspaceLease: ...

    def validate(self, context: ExecutionContext, *, agent_id: str, now: datetime) -> WorkspaceLease: ...

    def create_snapshot(
        self, context: ExecutionContext, *, agent_id: str, revision_digest: str, now: datetime
    ) -> WorkspaceSnapshot: ...

    def validate_snapshot(
        self,
        context: ExecutionContext,
        *,
        agent_id: str,
        snapshot: WorkspaceSnapshot,
        now: datetime,
    ) -> WorkspaceSnapshot: ...

    def release(self, context: ExecutionContext, *, agent_id: str, now: datetime) -> None: ...


class InMemoryWorkspaceAuthority:
    """Deterministic test/domain adapter; never external or production evidence."""

    durable = False

    def __init__(self) -> None:
        self._owners: dict[tuple[str, str, str, str], WorkspaceOwner] = {}
        self._leases: dict[tuple[str, str, str, str], WorkspaceLease] = {}
        self._snapshots: dict[tuple[str, str, str, str, str], WorkspaceSnapshot] = {}

    @staticmethod
    def _key(context: ExecutionContext) -> tuple[str, str, str, str]:
        if context.workspace_id is None:
            raise AgentValidationError("workspace_id is required", code="WORKSPACE_REQUIRED")
        return (*_scope_key(context.scope), context.workspace_id)

    def claim_owner(self, context: ExecutionContext, *, agent_id: str, now: datetime) -> WorkspaceOwner:
        _aware(now, "now")
        key = self._key(context)
        current = self._owners.get(key)
        if current is not None and current.agent_id != agent_id:
            raise AgentConflictError("workspace already has another owner", code="WORKSPACE_OWNED")
        if current is not None and (
            not _same_scope(current.scope, context.scope)
            or current.generation != context.fence_token
            or current.authority_profile != context.authority_profile
        ):
            raise StaleFenceError(
                "workspace owner binding is stale or changed", code="STALE_WORKSPACE_OWNER"
            )
        generation = context.fence_token or (1 if current is None else current.generation)
        owner = WorkspaceOwner(
            scope=context.scope,
            workspace_id=context.workspace_id or "",
            agent_id=_required(agent_id, "agent_id"),
            authority_profile=context.authority_profile,
            generation=generation,
            acquired_at=now,
        )
        self._owners[key] = owner
        return owner

    def issue_lease(
        self, context: ExecutionContext, *, agent_id: str, ttl: timedelta, now: datetime
    ) -> WorkspaceLease:
        _aware(now, "now")
        if ttl <= timedelta(0):
            raise AgentValidationError("lease ttl must be positive", code="INVALID_LEASE")
        key = self._key(context)
        owner = self._owners.get(key)
        if owner is None or owner.agent_id != agent_id or owner.authority_profile != context.authority_profile:
            raise AgentAuthorizationError("workspace ownership is not bound", code="OWNER_MISMATCH")
        if not _same_scope(owner.scope, context.scope):
            raise StaleFenceError("workspace revision is stale", code="STALE_WORKSPACE_REVISION")
        previous = self._leases.get(key)
        generation = owner.generation if previous is None else previous.generation + 1
        token = generation
        if context.fence_token != token:
            raise StaleFenceError(
                "lease request does not carry the next fence generation", code="STALE_FENCE"
            )
        if context.lease_id is None:
            raise AgentValidationError("lease_id is required", code="INVALID_LEASE")
        lease_id = context.lease_id
        lease = WorkspaceLease(
            scope=context.scope,
            workspace_id=context.workspace_id or "",
            lease_id=lease_id,
            agent_id=agent_id,
            fence_token=token,
            generation=generation,
            issued_at=now,
            expires_at=now + ttl,
        )
        self._leases[key] = lease
        self._owners[key] = WorkspaceOwner(
            scope=owner.scope,
            workspace_id=owner.workspace_id,
            agent_id=owner.agent_id,
            authority_profile=owner.authority_profile,
            generation=generation,
            acquired_at=owner.acquired_at,
        )
        return lease

    def validate(self, context: ExecutionContext, *, agent_id: str, now: datetime) -> WorkspaceLease:
        _aware(now, "now")
        key = self._key(context)
        owner = self._owners.get(key)
        lease = self._leases.get(key)
        if owner is None or lease is None:
            raise AgentAuthorizationError("workspace authority is missing", code="WORKSPACE_AUTHORITY_MISSING")
        if not _same_scope(owner.scope, context.scope) or not _same_scope(lease.scope, context.scope):
            raise AgentAuthorizationError("workspace scope mismatch", code="WORKSPACE_SCOPE_MISMATCH")
        if owner.agent_id != agent_id or lease.agent_id != agent_id:
            raise AgentAuthorizationError("workspace owner mismatch", code="OWNER_MISMATCH")
        if owner.authority_profile != context.authority_profile:
            raise AgentAuthorizationError("authority profile changed", code="AUTHORITY_PROFILE_MISMATCH")
        if now >= lease.expires_at:
            raise StaleFenceError("workspace lease expired", code="LEASE_EXPIRED")
        if context.lease_id != lease.lease_id:
            raise StaleFenceError("workspace lease is stale", code="STALE_LEASE")
        if context.fence_token != lease.fence_token:
            raise StaleFenceError("workspace fence is stale", code="STALE_FENCE")
        return lease

    def create_snapshot(
        self, context: ExecutionContext, *, agent_id: str, revision_digest: str, now: datetime
    ) -> WorkspaceSnapshot:
        lease = self.validate(context, agent_id=agent_id, now=now)
        require_sha256_digest(revision_digest, field="revision_digest")
        snapshot_id = _stable_digest(
            "workspace-snapshot",
            {
                "scope": _scope_key(context.scope),
                "workspace": lease.workspace_id,
                "revision": revision_digest,
                "fence": lease.fence_token,
            },
        )
        snapshot = WorkspaceSnapshot(
            scope=context.scope,
            workspace_id=lease.workspace_id,
            snapshot_id=snapshot_id,
            revision_digest=revision_digest,
            owner_agent_id=agent_id,
            lease_id=lease.lease_id,
            fence_token=lease.fence_token,
            created_at=now,
        )
        self._snapshots[(*self._key(context), snapshot_id)] = snapshot
        return snapshot

    def validate_snapshot(
        self,
        context: ExecutionContext,
        *,
        agent_id: str,
        snapshot: WorkspaceSnapshot,
        now: datetime,
    ) -> WorkspaceSnapshot:
        lease = self.validate(context, agent_id=agent_id, now=now)
        persisted = self._snapshots.get((*self._key(context), snapshot.snapshot_id))
        if persisted is None or persisted != snapshot:
            raise AgentValidationError("snapshot is not persisted", code="SNAPSHOT_NOT_FOUND")
        if (
            not _same_scope(snapshot.scope, context.scope)
            or snapshot.owner_agent_id != agent_id
            or snapshot.lease_id != lease.lease_id
            or snapshot.fence_token != lease.fence_token
        ):
            raise StaleFenceError("snapshot authority is stale", code="STALE_SNAPSHOT_FENCE")
        return persisted

    def release(self, context: ExecutionContext, *, agent_id: str, now: datetime) -> None:
        self.validate(context, agent_id=agent_id, now=now)
        key = self._key(context)
        del self._leases[key]
        del self._owners[key]


@dataclass(frozen=True, slots=True)
class AgentTaskNode:
    scope: ResourceScope
    task: AgentTask
    state: AgentState = AgentState.CREATED
    version: int = 1
    last_checkpoint: str | None = None
    completed_effect_ids: tuple[str, ...] = ()
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AgentTaskStateStore(Protocol):
    durable: bool

    def load(self, scope: ResourceScope, job_id: str) -> "AgentTaskGraphSnapshot": ...

    def save(
        self,
        scope: ResourceScope,
        job_id: str,
        nodes: Mapping[str, AgentTaskNode],
        *,
        expected_revision: int,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class AgentTaskGraphSnapshot:
    revision: int
    nodes: Mapping[str, AgentTaskNode]


class InMemoryAgentTaskStateStore:
    durable = False

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str, str, str], AgentTaskGraphSnapshot] = {}

    def load(self, scope: ResourceScope, job_id: str) -> AgentTaskGraphSnapshot:
        current = self._jobs.get((*_scope_key(scope), job_id))
        if current is None:
            return AgentTaskGraphSnapshot(0, MappingProxyType({}))
        return AgentTaskGraphSnapshot(current.revision, MappingProxyType(dict(current.nodes)))

    def save(
        self,
        scope: ResourceScope,
        job_id: str,
        nodes: Mapping[str, AgentTaskNode],
        *,
        expected_revision: int,
    ) -> int:
        for node in nodes.values():
            if not _same_scope(scope, node.scope):
                raise AgentAuthorizationError("task store scope mismatch", code="TASK_SCOPE_MISMATCH")
        key = (*_scope_key(scope), job_id)
        current = self._jobs.get(key)
        current_revision = 0 if current is None else current.revision
        if current_revision != expected_revision:
            raise AgentConflictError("task graph revision is stale", code="STALE_TASK_GRAPH")
        next_revision = current_revision + 1
        self._jobs[key] = AgentTaskGraphSnapshot(
            next_revision, MappingProxyType(dict(nodes))
        )
        return next_revision


class AgentTaskDAG:
    """Versioned task DAG persisted independently of model/provider sessions."""

    def __init__(self, scope: ResourceScope, job_id: str, store: AgentTaskStateStore) -> None:
        self.scope = scope
        self.job_id = _required(job_id, "job_id")
        self.store = store
        loaded = store.load(scope, job_id)
        self._store_revision = loaded.revision
        self._nodes = dict(loaded.nodes)

    @property
    def nodes(self) -> Mapping[str, AgentTaskNode]:
        return MappingProxyType(self._nodes)

    def add(self, task: AgentTask, *, now: datetime) -> AgentTaskNode:
        _aware(now, "now")
        if task.job_id != self.job_id or task.project_id != self.scope.project_id:
            raise AgentAuthorizationError("task scope/job mismatch", code="TASK_SCOPE_MISMATCH")
        if task.input_revision != self.scope.input_revision:
            raise AgentConflictError("task input revision is stale", code="STALE_TASK_REVISION")
        if task.task_id in self._nodes:
            raise AgentConflictError("task already exists", code="TASK_EXISTS")
        dependencies = tuple(task.dependencies or ())
        missing = set(dependencies).difference(self._nodes)
        if missing:
            raise AgentValidationError(
                "task dependency is missing", code="MISSING_TASK_DEPENDENCY", details={"tasks": sorted(missing)}
            )
        node = AgentTaskNode(scope=self.scope, task=task, updated_at=now)
        self._nodes[task.task_id] = node
        if self._has_cycle():
            del self._nodes[task.task_id]
            raise AgentValidationError("task graph contains a cycle", code="TASK_DAG_CYCLE")
        try:
            self._persist()
        except Exception:
            del self._nodes[task.task_id]
            raise
        return node

    def transition(
        self,
        task_id: str,
        target: AgentState,
        *,
        expected_version: int,
        now: datetime,
        checkpoint: str | None = None,
        completed_effect_id: str | None = None,
    ) -> AgentTaskNode:
        _aware(now, "now")
        try:
            current = self._nodes[task_id]
        except KeyError as exc:
            raise AgentValidationError("task not found", code="TASK_NOT_FOUND") from exc
        if current.version != expected_version:
            raise AgentConflictError("task version is stale", code="STALE_TASK_VERSION")
        if target not in _STATE_TRANSITIONS[current.state]:
            raise AgentConflictError(
                "invalid agent state transition",
                code="INVALID_AGENT_TRANSITION",
                details={"from": current.state.value, "to": target.value},
            )
        effects = current.completed_effect_ids
        if completed_effect_id is not None:
            if completed_effect_id in effects:
                return current
            effects = (*effects, completed_effect_id)
        updated = AgentTaskNode(
            scope=current.scope,
            task=current.task,
            state=target,
            version=current.version + 1,
            last_checkpoint=checkpoint if checkpoint is not None else current.last_checkpoint,
            completed_effect_ids=effects,
            updated_at=now,
        )
        self._nodes[task_id] = updated
        try:
            self._persist()
        except Exception:
            self._nodes[task_id] = current
            raise
        return updated

    def ready(self) -> tuple[AgentTaskNode, ...]:
        terminal_success = {
            node.task.task_id for node in self._nodes.values() if node.state is AgentState.SUCCEEDED
        }
        return tuple(
            node
            for node in self._nodes.values()
            if node.state is AgentState.READY
            and set(node.task.dependencies or ()).issubset(terminal_success)
        )

    def _persist(self) -> None:
        self._store_revision = self.store.save(
            self.scope,
            self.job_id,
            self._nodes,
            expected_revision=self._store_revision,
        )

    def _has_cycle(self) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> bool:
            if task_id in visiting:
                return True
            if task_id in visited:
                return False
            visiting.add(task_id)
            for dependency in self._nodes[task_id].task.dependencies or ():
                if visit(dependency):
                    return True
            visiting.remove(task_id)
            visited.add(task_id)
            return False

        return any(visit(task_id) for task_id in self._nodes)


@dataclass(frozen=True, slots=True)
class SpawnPolicy:
    allowed_parent_agent_ids: frozenset[str]
    allowed_agent_ids: frozenset[str]
    allowed_capability_ids: frozenset[str]
    maximum_depth: int
    effort_ceiling: EffortLevel
    security_ceiling: SecurityCeiling
    allow_async: bool = True

    def __post_init__(self) -> None:
        if self.maximum_depth < 0:
            raise AgentValidationError("maximum_depth cannot be negative", code="INVALID_SPAWN_POLICY")


@dataclass(frozen=True, slots=True)
class SpawnRequest:
    context: ExecutionContext
    parent_agent_id: str
    namespace: str
    name: str
    version: str
    capability_id: str
    model_candidates: tuple[str, ...]
    effort: EffortLevel
    security: SecurityCeiling
    depth: int
    lineage: tuple[str, ...]
    scheduling: SchedulingMode = SchedulingMode.BLOCKING
    workspace_owner_agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentEffectRequest:
    request_id: str
    context: ExecutionContext
    kind: AgentEffectKind
    target_agent_id: str
    payload: tuple[tuple[str, str], ...]
    status: EffectStatus = EffectStatus.NOT_RUN
    external_evidence_status: EffectStatus = EffectStatus.NOT_RUN

    def __post_init__(self) -> None:
        _required(self.request_id, "request_id")
        _required(self.target_agent_id, "target_agent_id")
        if self.status is not EffectStatus.NOT_RUN or self.external_evidence_status is not EffectStatus.NOT_RUN:
            raise AgentValidationError(
                "external agent effects must originate as NOT_RUN", code="FABRICATED_EXTERNAL_EFFECT"
            )


class SpawnGuard:
    def __init__(
        self,
        definitions: AgentDefinitionRegistry,
        workspace_authority: WorkspaceAuthorityPort,
    ) -> None:
        self._definitions = definitions
        self._workspace_authority = workspace_authority

    def authorize(
        self, request: SpawnRequest, policy: SpawnPolicy, *, now: datetime
    ) -> AgentEffectRequest:
        _aware(now, "now")
        definition = self._definitions.resolve(request.namespace, request.name, request.version)
        if request.parent_agent_id not in policy.allowed_parent_agent_ids:
            raise AgentAuthorizationError("spawn caller is not authorized", code="UNAUTHORIZED_SPAWN")
        if definition.agent_id not in policy.allowed_agent_ids:
            raise AgentAuthorizationError("spawn target is not authorized", code="UNAUTHORIZED_SPAWN")
        if request.capability_id not in policy.allowed_capability_ids or request.capability_id not in definition.capability_ids:
            raise AgentAuthorizationError("spawn capability is not authorized", code="UNAUTHORIZED_SPAWN")
        if request.context.authority_profile != definition.authority_profile:
            raise AgentAuthorizationError("authority profile mismatch", code="AUTHORITY_PROFILE_MISMATCH")
        ceiling = min(policy.maximum_depth, definition.max_depth)
        if request.depth < 1 or request.depth > ceiling:
            raise AgentAuthorizationError("recursion depth exceeded", code="RECURSION_DEPTH_EXCEEDED")
        if (
            len(request.lineage) != request.depth
            or not request.lineage
            or request.lineage[-1] != request.parent_agent_id
            or len(set(request.lineage)) != len(request.lineage)
        ):
            raise AgentAuthorizationError("agent lineage is malformed", code="INVALID_AGENT_LINEAGE")
        if definition.agent_id in request.lineage and not definition.allow_self_recursion:
            raise AgentAuthorizationError("self recursion is forbidden", code="SELF_RECURSION_FORBIDDEN")
        if request.scheduling is SchedulingMode.ASYNC and not policy.allow_async:
            raise AgentAuthorizationError("async spawn is forbidden", code="ASYNC_SPAWN_FORBIDDEN")
        if request.effort > policy.effort_ceiling or request.security > policy.security_ceiling:
            raise AgentAuthorizationError("spawn ceiling exceeded", code="SPAWN_CEILING_EXCEEDED")
        model = definition.model_policy.select(
            request.model_candidates, effort=request.effort, security=request.security
        )
        capability = self._definitions.capability(request.capability_id)
        if capability.security_ceiling < request.security:
            raise AgentAuthorizationError("capability security ceiling exceeded", code="SECURITY_CEILING_EXCEEDED")
        if capability.write_capable:
            if request.workspace_owner_agent_id != definition.agent_id:
                raise AgentAuthorizationError(
                    "write-capable child requires its own owned workspace",
                    code="CHILD_WORKSPACE_NOT_ISOLATED",
                )
            self._workspace_authority.validate(
                request.context, agent_id=request.workspace_owner_agent_id, now=now
            )
        payload = (
            ("agent_definition", "/".join(definition.identity)),
            ("capability_id", request.capability_id),
            ("model", model),
            ("effort", request.effort.name),
            ("security", request.security.name),
            ("scheduling", request.scheduling.value),
            ("depth", str(request.depth)),
        )
        request_id = _stable_digest(
            "agent-effect",
            {
                "idempotency_key": request.context.idempotency_key,
                "context": request.context,
                "kind": AgentEffectKind.SPAWN.value,
                "target": definition.agent_id,
                "payload": payload,
            },
        )
        return AgentEffectRequest(
            request_id=request_id,
            context=request.context,
            kind=AgentEffectKind.SPAWN,
            target_agent_id=definition.agent_id,
            payload=payload,
        )


@dataclass(frozen=True, slots=True)
class TypedAgentYield:
    context: ExecutionContext
    agent_id: str
    parent_task_id: str
    result: ProofCarryingAgentResult
    evidence_records: tuple[EvidenceRecord, ...]
    workspace_snapshot_id: str | None = None
    schema_version: str = "1.0.0"


class YieldValidator:
    NON_SUCCESS_EVIDENCE = frozenset(
        {"NOT_RUN", "UNKNOWN", "INCONCLUSIVE", "MISSING", "STALE", "UNAUTHORIZED"}
    )

    @staticmethod
    def _status_text(value: object) -> str:
        raw = getattr(value, "value", value)
        return str(raw).upper()

    def validate(self, yielded: TypedAgentYield, *, expected_context: ExecutionContext) -> TypedAgentYield:
        if not isinstance(yielded, TypedAgentYield) or not isinstance(
            yielded.result, ProofCarryingAgentResult
        ):
            raise AgentValidationError("agent yield is not typed", code="MALFORMED_AGENT_YIELD")
        if yielded.schema_version != "1.0.0":
            raise AgentValidationError("unsupported yield schema", code="UNSUPPORTED_YIELD_SCHEMA")
        if not _same_scope(yielded.context.scope, expected_context.scope):
            raise AgentAuthorizationError("yield resource scope mismatch", code="YIELD_SCOPE_MISMATCH")
        if yielded.context.task_id != expected_context.task_id or yielded.result.task_id != expected_context.task_id:
            raise AgentAuthorizationError("yield task binding mismatch", code="YIELD_TASK_MISMATCH")
        if (
            yielded.context.actor_id != expected_context.actor_id
            or yielded.context.job_id != expected_context.job_id
            or yielded.context.authority_profile != expected_context.authority_profile
            or yielded.context.workspace_id != expected_context.workspace_id
            or yielded.context.lease_id != expected_context.lease_id
            or yielded.context.fence_token != expected_context.fence_token
            or yielded.agent_id != yielded.context.actor_id
        ):
            raise AgentAuthorizationError("yield execution binding mismatch", code="YIELD_CONTEXT_MISMATCH")
        _required(yielded.parent_task_id, "parent_task_id")
        if yielded.result.changed_artifacts:
            if yielded.workspace_snapshot_id is None:
                raise AgentValidationError(
                    "changed yield requires workspace snapshot", code="YIELD_SNAPSHOT_REQUIRED"
                )
            for artifact in yielded.result.changed_artifacts:
                expected_context.require_write(artifact)
        records = yielded.evidence_records
        if yielded.result.changed_artifacts and not records:
            raise AgentValidationError("changed artifacts require evidence", code="MISSING_YIELD_EVIDENCE")
        if set(yielded.result.evidence) != {record.evidence_id for record in records}:
            raise AgentValidationError(
                "yield evidence ids do not match typed records", code="YIELD_EVIDENCE_MISMATCH"
            )
        for record in records:
            if not isinstance(record, EvidenceRecord):
                raise AgentValidationError("yield evidence is not typed", code="MALFORMED_AGENT_YIELD")
            if record.scope is None or not _same_scope(record.scope, expected_context.scope):
                raise AgentAuthorizationError("evidence resource binding missing", code="EVIDENCE_SCOPE_MISMATCH")
            if self._status_text(record.status) in self.NON_SUCCESS_EVIDENCE:
                raise AgentValidationError("yield contains non-closing evidence", code="UNKNOWN_YIELD_EVIDENCE")
        if self._status_text(yielded.result.verification_status) in self.NON_SUCCESS_EVIDENCE:
            raise AgentValidationError("yield verification is non-closing", code="UNKNOWN_YIELD_VERIFICATION")
        return yielded


@dataclass(frozen=True, slots=True)
class ParkReceipt:
    context: ExecutionContext
    agent_id: str
    authority_profile: str
    workspace_snapshot_id: str
    lease_id: str
    fence_token: int
    checkpoint_id: str


class AgentSupervisor:
    def __init__(self, workspace: WorkspaceAuthorityPort, yield_validator: YieldValidator) -> None:
        self._workspace = workspace
        self._yield_validator = yield_validator

    @staticmethod
    def _effect(
        context: ExecutionContext,
        kind: AgentEffectKind,
        agent_id: str,
        payload: Mapping[str, str],
    ) -> AgentEffectRequest:
        frozen = tuple(sorted(payload.items()))
        request_id = _stable_digest(
            "agent-effect",
            {
                "idempotency_key": context.idempotency_key,
                "context": context,
                "kind": kind.value,
                "target": agent_id,
                "payload": frozen,
            },
        )
        return AgentEffectRequest(request_id, context, kind, agent_id, frozen)

    def request_steer(self, context: ExecutionContext, *, agent_id: str, instruction_digest: str) -> AgentEffectRequest:
        return self._effect(context, AgentEffectKind.STEER, agent_id, {"instruction_digest": instruction_digest})

    def request_park(
        self, context: ExecutionContext, *, agent_id: str, checkpoint_id: str, now: datetime
    ) -> AgentEffectRequest:
        self._workspace.validate(context, agent_id=agent_id, now=now)
        return self._effect(context, AgentEffectKind.PARK, agent_id, {"checkpoint_id": checkpoint_id})

    def request_revive(
        self, context: ExecutionContext, *, receipt: ParkReceipt, now: datetime
    ) -> AgentEffectRequest:
        if not _same_scope(context.scope, receipt.context.scope):
            raise AgentAuthorizationError("park receipt scope mismatch", code="REVIVE_SCOPE_MISMATCH")
        if context.authority_profile != receipt.authority_profile:
            raise AgentAuthorizationError("revive cannot change authority", code="REVIVE_AUTHORITY_MISMATCH")
        if context.lease_id != receipt.lease_id or context.fence_token != receipt.fence_token:
            raise StaleFenceError("revive workspace authority is stale", code="STALE_FENCE")
        self._workspace.validate(context, agent_id=receipt.agent_id, now=now)
        return self._effect(
            context,
            AgentEffectKind.REVIVE,
            receipt.agent_id,
            {"checkpoint_id": receipt.checkpoint_id, "snapshot_id": receipt.workspace_snapshot_id},
        )

    def request_kill(self, context: ExecutionContext, *, agent_id: str, reason: str) -> AgentEffectRequest:
        return self._effect(context, AgentEffectKind.KILL, agent_id, {"reason": _required(reason, "reason")})

    def request_orphan_reap(
        self,
        context: ExecutionContext,
        *,
        agent_id: str,
        last_heartbeat: datetime,
        orphan_after: timedelta,
        now: datetime,
    ) -> AgentEffectRequest:
        _aware(last_heartbeat, "last_heartbeat")
        _aware(now, "now")
        if orphan_after <= timedelta(0) or now - last_heartbeat < orphan_after:
            raise AgentValidationError("agent is not an orphan", code="AGENT_NOT_ORPHANED")
        return self._effect(
            context,
            AgentEffectKind.ORPHAN_REAP,
            agent_id,
            {"last_heartbeat": last_heartbeat.isoformat()},
        )

    def request_merge(
        self,
        context: ExecutionContext,
        *,
        agent_id: str,
        yielded: TypedAgentYield,
        snapshot: WorkspaceSnapshot,
        independent_review_status: object,
        now: datetime,
    ) -> AgentEffectRequest:
        self._workspace.validate(context, agent_id=agent_id, now=now)
        self._yield_validator.validate(yielded, expected_context=context)
        self._workspace.validate_snapshot(
            context, agent_id=agent_id, snapshot=snapshot, now=now
        )
        if not isinstance(independent_review_status, ReleaseReviewDecision):
            raise AgentAuthorizationError(
                "independent review must be a typed release decision",
                code="MERGE_REVIEW_UNTYPED",
            )
        review = YieldValidator._status_text(independent_review_status.verdict)
        if (
            review != "PASS"
            or getattr(independent_review_status, "certification_allowed", False) is not True
        ):
            raise AgentAuthorizationError("independent review did not pass", code="MERGE_REVIEW_BLOCKED")
        return self._effect(
            context,
            AgentEffectKind.MERGE,
            agent_id,
            {"snapshot_id": snapshot.snapshot_id, "yield_schema": yielded.schema_version},
        )


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    capability: str
    source_owner: str
    canonical_owner: str
    handler: str
    input_contract: str
    output_contract: str
    external_effect: bool = False


_K4_BINDING_ROWS = (
    ("agent-definition-ir", "K4", "K4", "AgentDefinition", "mapping", "AgentDefinition", False),
    ("agent-capability-registry", "K4", "K4", "AgentDefinitionRegistry.register_capability", "AgentCapability", "None", False),
    ("agent-discovery", "K4", "K4", "AgentDefinitionRegistry.discover", "name", "AgentDefinition[]", False),
    ("agent-policy-resolution", "K4", "K4", "SpawnGuard.authorize", "SpawnRequest+SpawnPolicy", "AgentEffectRequest", True),
    ("spawn-policy", "K4", "K4", "SpawnGuard.authorize", "SpawnRequest+SpawnPolicy", "AgentEffectRequest", True),
    ("recursion-depth-governor", "K4", "K4", "SpawnGuard.authorize", "SpawnRequest.depth", "AgentEffectRequest", True),
    ("self-recursion-guard", "K4", "K4", "SpawnGuard.authorize", "SpawnRequest.lineage", "AgentEffectRequest", True),
    ("tool-authority-profile", "K4", "K4", "AgentDefinition.authority_profile", "ExecutionContext", "authorization", False),
    ("agent-model-policy", "K4", "K4", "ModelPolicy.select", "model candidates", "model id", False),
    ("effort-ceiling", "K4", "K4", "ModelPolicy.select", "effort", "model id", False),
    ("autoload-skill-policy", "K4", "K4", "AgentDefinition.autoload_skills", "skill ids", "authorized skill ids", False),
    ("read-summary-policy", "K4", "K4", "AgentDefinition.read_summary_required", "summary receipt", "authorization", False),
    ("prewalk-agent", "K4", "K4", "SpawnGuard.authorize", "prewalk SpawnRequest", "AgentEffectRequest", True),
    # The source lists this in K4 and K8; K8 is the sole runtime owner.
    ("phase-model-handoff", "K4", "K8", "K8.phase_model_handoff", "handoff request", "handoff plan", False),
    ("isolated-workspace", "K4", "K4", "WorkspaceAuthorityPort", "ExecutionContext", "WorkspaceLease", False),
    ("workspace-owner", "K4", "K4", "WorkspaceAuthorityPort.claim_owner", "ExecutionContext", "WorkspaceOwner", False),
    ("workspace-lease", "K4", "K4", "WorkspaceAuthorityPort.issue_lease", "ExecutionContext", "WorkspaceLease", False),
    ("workspace-fence", "K4", "K4", "WorkspaceAuthorityPort.validate", "ExecutionContext", "WorkspaceLease", False),
    ("workspace-snapshot", "K4", "K4", "WorkspaceAuthorityPort.create_snapshot", "ExecutionContext", "WorkspaceSnapshot", False),
    ("typed-agent-yield", "K4", "K4", "YieldValidator.validate", "TypedAgentYield", "TypedAgentYield", False),
    ("proof-carrying-result", "K4", "K4", "YieldValidator.validate", "ProofCarryingAgentResult", "TypedAgentYield", False),
    ("agent-task-dag", "K4", "K4", "AgentTaskDAG", "AgentTask", "AgentTaskNode", False),
    ("blocking-vs-async-policy", "K4", "K4", "SpawnGuard.authorize", "SchedulingMode", "AgentEffectRequest", True),
    ("agent-supervisor", "K4", "K4", "AgentSupervisor", "control request", "AgentEffectRequest", True),
    ("steer-agent", "K4", "K9", "AgentSupervisor.request_steer", "instruction digest", "AgentEffectRequest", True),
    ("park-revive-agent", "K4", "K4", "AgentSupervisor.request_park/request_revive", "ParkReceipt", "AgentEffectRequest", True),
    ("kill-release-agent", "K4", "K4", "AgentSupervisor.request_kill", "reason", "AgentEffectRequest", True),
    ("child-lineage", "K4", "K4", "SpawnRequest.lineage", "agent lineage", "authorization", False),
    ("merge-coordinator", "K4", "K4", "AgentSupervisor.request_merge", "yield+snapshot+review", "AgentEffectRequest", True),
    ("orphan-agent-reaper", "K4", "K4", "AgentSupervisor.request_orphan_reap", "heartbeat", "AgentEffectRequest", True),
)

K4_CAPABILITIES = tuple(row[0] for row in _K4_BINDING_ROWS)
K4_OPERATION_BINDINGS: Mapping[str, CapabilityBinding] = MappingProxyType(
    {name: CapabilityBinding(*row) for row in _K4_BINDING_ROWS for name in (row[0],)}
)
K4_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {name: CAPABILITY_REGISTRY[name] for name in K4_CAPABILITIES}
)


def resolve_k4_binding(capability: str) -> CapabilityBinding:
    try:
        return K4_OPERATION_BINDINGS[capability]
    except KeyError as exc:
        raise UnknownCapabilityError(
            "unknown K4 capability; generic fallback is forbidden",
            code="UNKNOWN_K4_CAPABILITY",
            details={"capability": capability},
        ) from exc


if len(K4_CAPABILITIES) != 30 or len(set(K4_CAPABILITIES)) != len(K4_CAPABILITIES):
    raise RuntimeError("K4 capability bindings must contain exactly 30 unique source occurrences")
