from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable
import json


class ContractError(RuntimeError):
    pass


class MappingResult(str, Enum):
    EXACT = "EXACT"
    LOSSY = "LOSSY"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class CallIdentity:
    invocation_id: str
    call_id: str
    execution_plan_hash: str
    environment_id: str
    authority_snapshot_id: str


@dataclass(frozen=True)
class ToolResult:
    identity: CallIdentity
    ok: bool
    content: Any


@dataclass(frozen=True)
class InterceptorDecision:
    interceptor_id: str
    version: str
    before_hash: str
    after_hash: str


@dataclass(frozen=True)
class CommittedToolResult:
    raw: ToolResult
    effective: ToolResult
    decisions: tuple[InterceptorDecision, ...]
    commit_key: str


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


class ResultCommitter:
    def __init__(self) -> None:
        self._committed: dict[str, CommittedToolResult] = {}

    def commit(self, raw: ToolResult, interceptors: Iterable[tuple[str, str, Callable[[ToolResult], ToolResult]]], *, attempt: int, epoch: int) -> CommittedToolResult:
        effective = raw
        decisions: list[InterceptorDecision] = []
        for interceptor_id, version, fn in interceptors:
            before = digest(effective)
            candidate = fn(effective)
            if candidate.identity != raw.identity:
                raise ContractError("interceptor changed immutable call identity")
            decisions.append(InterceptorDecision(interceptor_id, version, before, digest(candidate)))
            effective = candidate
        key = f"{raw.identity.invocation_id}:{attempt}:{epoch}"
        result = CommittedToolResult(raw, effective, tuple(decisions), key)
        existing = self._committed.get(key)
        if existing is not None and existing != result:
            raise ContractError("conflicting RESULT_COMMIT")
        self._committed[key] = result
        return result


@dataclass(frozen=True)
class ModelSnapshot:
    provider: str
    model: str
    revision: str
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    model: ModelSnapshot
    tools: tuple[str, ...]
    environment_snapshot_id: str
    authority_snapshot_id: str
    mode: str
    state: str = "CANDIDATE"

    @property
    def plan_hash(self) -> str:
        return digest(self)


class PlanStore:
    def __init__(self) -> None:
        self.active: ExecutionPlan | None = None

    def build_candidate(self, model: ModelSnapshot, tools: Iterable[str], env: str, auth: str, mode: str) -> ExecutionPlan:
        return ExecutionPlan(model, tuple(tools), env, auth, mode)

    def finalize(self, candidate: ExecutionPlan) -> ExecutionPlan:
        finalized = replace(candidate, state="FINALIZED")
        self.active = finalized
        return finalized


@dataclass(frozen=True)
class PermissionProfile:
    filesystem_roots: tuple[str, ...]
    network: str
    mutable: bool
    extra: tuple[tuple[str, str], ...] = ()


class PermissionAdapter:
    @staticmethod
    def project(profile: PermissionProfile, representable: dict[str, PermissionProfile]) -> tuple[MappingResult, str | None]:
        for value, exact in representable.items():
            if exact == profile:
                return MappingResult.EXACT, value
        if not representable:
            return MappingResult.UNSUPPORTED, None
        return MappingResult.LOSSY, None

    @staticmethod
    def require_exact(result: MappingResult) -> None:
        if result is not MappingResult.EXACT:
            raise ContractError(f"permission mapping is {result.value}")


@dataclass
class CapabilityLease:
    lease_id: str
    invocation_id: str
    environment_id: str
    authority_snapshot_id: str
    execution_epoch: int
    capabilities: frozenset[str]
    active: bool = True

    def use(self, invocation_id: str, epoch: int, capability: str) -> None:
        if not self.active:
            raise ContractError("capability lease revoked")
        if invocation_id != self.invocation_id or epoch != self.execution_epoch:
            raise ContractError("capability lease scope mismatch")
        if capability not in self.capabilities:
            raise ContractError("capability not leased")

    def revoke(self) -> None:
        self.active = False


class SecurityContextBroker:
    RESERVED = {"verifiedSecurityContext", "entitlementContext", "executionAuthority"}

    @classmethod
    def sanitize_caller_metadata(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in metadata.items() if k not in cls.RESERVED}

    @classmethod
    def mint(cls, *, eligible: bool, account_stable: bool, bindings: dict[str, str], entitlements: dict[str, Any]) -> dict[str, Any]:
        required = {"pluginId", "toolId", "accountId", "tenantId", "environmentId", "invocationId", "policyVersion"}
        if not eligible or not account_stable or set(bindings) != required:
            return {"status": "UNKNOWN", "bindings": bindings, "entitlements": {}}
        return {"status": "VERIFIED", "bindings": bindings, "entitlements": entitlements, "signature": digest([bindings, entitlements])}


@dataclass(frozen=True)
class AuthoritySnapshot:
    snapshot_id: str
    permissions: frozenset[str]

    @staticmethod
    def intersect(owner: "AuthoritySnapshot", parent: "AuthoritySnapshot", policy: frozenset[str], snapshot_id: str) -> "AuthoritySnapshot":
        return AuthoritySnapshot(snapshot_id, owner.permissions & parent.permissions & policy)


class GenerationFence:
    def __init__(self, generation: int = 0, connection_epoch: int = 0) -> None:
        self.generation = generation
        self.connection_epoch = connection_epoch

    def reconnect_same(self) -> tuple[int, int]:
        self.connection_epoch += 1
        return self.generation, self.connection_epoch

    def replace_executor(self) -> tuple[int, int]:
        self.generation += 1
        self.connection_epoch += 1
        return self.generation, self.connection_epoch

    def accept(self, generation: int, connection_epoch: int) -> None:
        if (generation, connection_epoch) != (self.generation, self.connection_epoch):
            raise ContractError("stale executor result")


@dataclass(frozen=True)
class WorkspaceLease:
    workspace_id: str
    owner_execution_id: str
    generation: int
    repository_id: str
    base_revision: str


class WorkspaceLeaseManager:
    def __init__(self) -> None:
        self._active: dict[str, WorkspaceLease] = {}

    def bind(self, lease: WorkspaceLease) -> WorkspaceLease:
        current = self._active.get(lease.workspace_id)
        if current is None:
            self._active[lease.workspace_id] = lease
            return lease
        if current == lease:
            return current
        raise ContractError("workspace owner conflict")

    def takeover(self, workspace_id: str, new_owner: str) -> WorkspaceLease:
        current = self._active[workspace_id]
        replacement = replace(current, owner_execution_id=new_owner, generation=current.generation + 1)
        self._active[workspace_id] = replacement
        return replacement


@dataclass(frozen=True)
class ProtocolCapabilities:
    provider: str
    version: str
    features: frozenset[str]

    def require(self, required: Iterable[str]) -> None:
        missing = set(required) - self.features
        if missing:
            raise ContractError(f"unsupported protocol capabilities: {sorted(missing)}")


class SkillTrustVerifier:
    @staticmethod
    def verify(skill_path: Path, trusted_root: Path) -> Path:
        root = trusted_root.resolve(strict=True)
        actual = skill_path.resolve(strict=True)
        try:
            actual.relative_to(root)
        except ValueError as exc:
            raise ContractError("skill path escapes trust root") from exc
        return actual


@dataclass(frozen=True)
class EventRegistration:
    event_type: str
    owner: str
    schema_version: int
    semantics: str
    validator: Callable[[dict[str, Any]], bool] = field(compare=False, repr=False)
    upgrader: Callable[[dict[str, Any]], dict[str, Any]] = field(compare=False, repr=False)


class DurableEventRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], EventRegistration] = {}

    def register(self, item: EventRegistration) -> None:
        key = (item.event_type, item.schema_version)
        current = self._items.get(key)
        if current is not None and (current.owner, current.semantics) != (item.owner, item.semantics):
            raise ContractError("conflicting event registration")
        self._items[key] = item

    def replay(self, event_type: str, version: int, payload: dict[str, Any], *, unknown_optional: bool = False) -> dict[str, Any] | None:
        item = self._items.get((event_type, version))
        if item is None:
            if unknown_optional:
                return None
            raise ContractError("unknown required durable event")
        if not item.validator(payload):
            raise ContractError("event schema validation failed")
        return payload


class IngressLedger:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def accept(self, key: str, kind: str) -> bool:
        if kind not in {"USER_INPUT", "TOOL_RESULT", "EXTERNAL_EVENT", "APPROVAL_INPUT", "CONTROL_INPUT"}:
            raise ContractError("unknown ingress kind")
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


@dataclass(frozen=True)
class SubagentSpec:
    provider: str
    model: str
    reasoning_effort: str
    max_output_tokens: int
    authority: frozenset[str]
    tools: frozenset[str]

    def validate_under(self, parent_authority: frozenset[str], parent_tools: frozenset[str], max_tokens: int) -> None:
        if not self.authority <= parent_authority:
            raise ContractError("subagent authority widening")
        if not self.tools <= parent_tools:
            raise ContractError("subagent tool widening")
        if self.max_output_tokens > max_tokens:
            raise ContractError("subagent output budget exceeded")
