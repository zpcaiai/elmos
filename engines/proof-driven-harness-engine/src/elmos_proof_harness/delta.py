"""Repository-owned runtime for the v3.1 harness-runtime-assurance delta.

The delta is deliberately implemented as a small, dependency-free control
plane.  It does not call a provider, execute a plugin, or turn an untrusted
payload into authority.  Every object below is a typed, immutable (or
monotonically stateful) boundary with explicit identity, epoch and evidence
semantics.  The source ZIP is only a contract/data source; this module is the
implementation used by the installed Skill wrappers.

The public classes retain the compact names used by the upstream contract so
existing integrations can migrate without importing the untrusted reference
implementation.  Newer callers should prefer the ``*Manager``, ``*Broker``
and ``*Store`` names, which expose the lifecycle checks explicitly.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
import hmac
import json
import math
from pathlib import Path
import threading
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

from .canonical import canonical_json_bytes, digest_bytes, digest_object, freeze_json, is_sha256_digest


DELTA_VERSION = "3.1.0"
DELTA_API_VERSION = "elmos.ai/v3delta1"


class ContractError(RuntimeError):
    """A fail-closed contract or lifecycle violation."""


class MappingResult(StrEnum):
    EXACT = "EXACT"
    LOSSY = "LOSSY"
    UNSUPPORTED = "UNSUPPORTED"


class ResultStatus(StrEnum):
    COMMITTED = "COMMITTED"
    DENIED = "DENIED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class CommitState(StrEnum):
    RAW_CAPTURED = "RAW_CAPTURED"
    INTERCEPTING = "INTERCEPTING"
    COMMITTED = "COMMITTED"
    PUBLISHED = "PUBLISHED"
    ABORTED = "ABORTED"


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} is required")
    if len(value) > 1024:
        raise ContractError(f"{field_name} is too long")
    return value


def _nonnegative(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field_name} must be a non-negative integer")
    return value


def _aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC) if value is not None else None


def _digest(value: Any, *, domain: str = "delta-contract") -> str:
    """Return a stable hexadecimal digest for upstream-compatible hashes."""

    return hashlib.sha256(domain.encode("utf-8") + b"\x00" + canonical_json_bytes(value)).hexdigest()


def digest(value: Any) -> str:
    """Compatibility helper matching the compact source contract."""

    return _digest(value)


def _cas_digest(value: Any, *, domain: str) -> str:
    return digest_object(value, domain=domain)


def _freeze(value: Any) -> Any:
    """Freeze a JSON-shaped value while retaining mapping/index semantics."""

    try:
        return freeze_json(value)
    except Exception as exc:  # canonical errors should not leak as implementation details
        raise ContractError(f"value is not JSON-shaped: {type(value).__name__}") from exc


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(item[:1].upper() + item[1:] for item in parts[1:])


def _wire_dataclass(value: Any, *, exclude: Iterable[str] = ()) -> dict[str, Any]:
    excluded = set(exclude)
    output: dict[str, Any] = {}
    for field_info in dataclasses.fields(value):
        key = field_info.name
        item = getattr(value, key)
        if key in excluded:
            continue
        if isinstance(item, MappingProxyType):
            item = _thaw(item)
        elif isinstance(item, tuple):
            item = [_thaw(part) for part in item]
        elif isinstance(item, StrEnum):
            item = item.value
        elif isinstance(item, datetime):
            item = item.astimezone(UTC).isoformat().replace("+00:00", "Z")
        output[_camel(key)] = item
    return output


@dataclass(frozen=True, slots=True)
class CallIdentity:
    invocation_id: str
    call_id: str
    execution_plan_hash: str
    environment_id: str
    authority_snapshot_id: str

    def __post_init__(self) -> None:
        for name in ("invocation_id", "call_id", "execution_plan_hash", "environment_id", "authority_snapshot_id"):
            _text(getattr(self, name), name)

    def to_wire(self) -> dict[str, Any]:
        return _wire_dataclass(self)


@dataclass(frozen=True, slots=True)
class ToolResult:
    identity: CallIdentity
    ok: bool
    content: Any

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CallIdentity) or not isinstance(self.ok, bool):
            raise ContractError("tool result identity and ok flag are invalid")
        _freeze(self.content)

    def snapshot(self) -> "ToolResult":
        return ToolResult(self.identity, self.ok, _freeze(self.content))

    def to_wire(self) -> dict[str, Any]:
        return {"identity": self.identity.to_wire(), "ok": self.ok, "content": _thaw(self.content)}


@dataclass(frozen=True, slots=True)
class InterceptorDecision:
    interceptor_id: str
    version: str
    before_hash: str
    after_hash: str
    decision_hash: str | None = None

    def __post_init__(self) -> None:
        _text(self.interceptor_id, "interceptor_id")
        _text(self.version, "version")
        _text(self.before_hash, "before_hash")
        _text(self.after_hash, "after_hash")
        if self.decision_hash is not None:
            _text(self.decision_hash, "decision_hash")

    @property
    def effective_decision_hash(self) -> str:
        return self.decision_hash or _digest(
            {"interceptorId": self.interceptor_id, "version": self.version, "before": self.before_hash, "after": self.after_hash},
            domain="delta-interceptor-decision",
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "interceptorId": self.interceptor_id,
            "version": self.version,
            "decisionHash": self.effective_decision_hash,
        }


@dataclass(frozen=True, slots=True)
class CommittedToolResult:
    raw: ToolResult
    effective: ToolResult
    decisions: tuple[InterceptorDecision, ...]
    commit_key: str
    commit_state: CommitState = CommitState.COMMITTED
    raw_result_ref: str | None = None
    effective_result_ref: str | None = None
    mutation_provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if self.raw.identity != self.effective.identity:
            raise ContractError("raw and effective result identity diverged")
        _text(self.commit_key, "commit_key")
        if self.commit_state not in CommitState:
            raise ContractError("invalid result commit state")

    @property
    def call_identity(self) -> CallIdentity:
        return self.raw.identity

    def to_wire(self) -> dict[str, Any]:
        raw_ref = self.raw_result_ref or _cas_digest(self.raw.to_wire(), domain="delta-raw-tool-result")
        effective_ref = self.effective_result_ref or _cas_digest(self.effective.to_wire(), domain="delta-effective-tool-result")
        output: dict[str, Any] = {
            "callIdentity": self.call_identity.to_wire(),
            "rawResultRef": raw_ref,
            "effectiveResultRef": effective_ref,
            "interceptorChain": [decision.to_wire() for decision in self.decisions],
            "commitState": self.commit_state.value,
        }
        if self.mutation_provenance_ref is not None:
            output["mutationProvenanceRef"] = self.mutation_provenance_ref
        return output


Interceptor = tuple[str, str, Callable[[ToolResult], ToolResult]]


class ResultLifecycleCoordinator:
    """Capture, intercept, commit and publish tool results exactly once."""

    def __init__(self) -> None:
        self._committed: dict[str, CommittedToolResult] = {}
        self._captured: dict[str, ToolResult] = {}
        self._published: set[str] = set()
        self._lock = threading.RLock()

    @staticmethod
    def _key(identity: CallIdentity, attempt: int, epoch: int) -> str:
        _nonnegative(attempt, "attempt")
        _nonnegative(epoch, "epoch")
        return f"{identity.invocation_id}:{attempt}:{epoch}"

    def capture(self, raw: ToolResult, *, attempt: int = 0, epoch: int = 0) -> ToolResult:
        if not isinstance(raw, ToolResult):
            raise ContractError("raw result must be typed ToolResult")
        key = self._key(raw.identity, attempt, epoch)
        snap = raw.snapshot()
        with self._lock:
            existing = self._captured.get(key)
            if existing is not None and existing != snap:
                raise ContractError("conflicting RAW_CAPTURED result")
            self._captured[key] = snap
            return existing or snap

    def commit(
        self,
        raw: ToolResult,
        interceptors: Iterable[Interceptor],
        *,
        attempt: int,
        epoch: int,
    ) -> CommittedToolResult:
        key = self._key(raw.identity, attempt, epoch)
        with self._lock:
            captured = self.capture(raw, attempt=attempt, epoch=epoch)
            existing = self._committed.get(key)
            if existing is not None:
                # Idempotent retry is allowed only if the entire immutable
                # result/chain is exactly the same.
                candidate = self._build(captured, interceptors, key)
                if existing != candidate:
                    raise ContractError("conflicting RESULT_COMMIT")
                return existing
            candidate = self._build(captured, interceptors, key)
            self._committed[key] = candidate
            return candidate

    def _build(self, raw: ToolResult, interceptors: Iterable[Interceptor], key: str) -> CommittedToolResult:
        effective = raw.snapshot()
        decisions: list[InterceptorDecision] = []
        for item in interceptors:
            if not isinstance(item, tuple) or len(item) != 3:
                raise ContractError("interceptor must be (id, version, callable)")
            interceptor_id, version, fn = item
            _text(interceptor_id, "interceptor_id")
            _text(version, "version")
            if not callable(fn):
                raise ContractError("interceptor callable is required")
            before = _digest(effective.to_wire(), domain="delta-interceptor-input")
            try:
                candidate = fn(effective)
            except ContractError:
                raise
            except Exception as exc:
                raise ContractError(f"interceptor {interceptor_id} failed") from exc
            if not isinstance(candidate, ToolResult) or candidate.identity != raw.identity:
                raise ContractError("interceptor changed immutable call identity")
            candidate = candidate.snapshot()
            after = _digest(candidate.to_wire(), domain="delta-interceptor-output")
            decisions.append(InterceptorDecision(interceptor_id, version, before, after))
            effective = candidate
        return CommittedToolResult(raw.snapshot(), effective.snapshot(), tuple(decisions), key)

    def publish(self, commit_key: str) -> CommittedToolResult:
        with self._lock:
            result = self._committed.get(commit_key)
            if result is None:
                raise ContractError("cannot publish unknown result commit")
            if commit_key in self._published:
                return replace(result, commit_state=CommitState.PUBLISHED)
            self._published.add(commit_key)
            published = replace(result, commit_state=CommitState.PUBLISHED)
            self._committed[commit_key] = published
            return published

    def abort(self, commit_key: str) -> CommittedToolResult:
        with self._lock:
            result = self._committed.get(commit_key)
            if result is None:
                raise ContractError("cannot abort unknown result commit")
            if result.commit_state is CommitState.PUBLISHED:
                raise ContractError("published result cannot be aborted")
            aborted = replace(result, commit_state=CommitState.ABORTED)
            self._committed[commit_key] = aborted
            return aborted

    def replay(self, commit_key: str, *, raw: ToolResult | None = None, effective: ToolResult | None = None) -> CommittedToolResult:
        with self._lock:
            result = self._committed.get(commit_key)
            if result is None:
                raise ContractError("unknown result commit")
            if raw is not None and result.raw != raw.snapshot():
                raise ContractError("result replay raw divergence")
            if effective is not None and result.effective != effective.snapshot():
                raise ContractError("result replay effective divergence")
            return result

    def get(self, commit_key: str) -> CommittedToolResult | None:
        with self._lock:
            return self._committed.get(commit_key)


class ResultCommitter(ResultLifecycleCoordinator):
    """Backward-compatible name for the lifecycle coordinator."""


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    provider: str
    model: str
    revision: str
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "model", "revision"):
            _text(getattr(self, name), name)
        if self.reasoning_effort is not None:
            _text(self.reasoning_effort, "reasoning_effort")

    def to_wire(self) -> dict[str, Any]:
        result = {"provider": self.provider, "model": self.model, "revision": self.revision}
        if self.reasoning_effort is not None:
            result["reasoningEffort"] = self.reasoning_effort
        return result


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    model: ModelSnapshot
    tools: tuple[str, ...]
    environment_snapshot_id: str
    authority_snapshot_id: str
    mode: str
    state: str = "CANDIDATE"
    plan_id: str | None = None
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.model, ModelSnapshot):
            raise ContractError("execution plan model snapshot is invalid")
        for name in ("environment_snapshot_id", "authority_snapshot_id", "mode"):
            _text(getattr(self, name), name)
        if self.state not in {"CANDIDATE", "FINALIZED", "ACTIVE", "RETIRED"}:
            raise ContractError("invalid execution plan state")
        for value in (*self.tools, *self.capabilities):
            _text(value, "plan item")

    @property
    def plan_hash(self) -> str:
        # Mutable lifecycle state and display IDs are intentionally excluded.
        return _cas_digest(
            {
                "modelSnapshot": self.model.to_wire(),
                "tools": list(self.tools),
                "environmentSnapshotId": self.environment_snapshot_id,
                "authoritySnapshotId": self.authority_snapshot_id,
                "mode": self.mode,
                "capabilities": list(self.capabilities),
            },
            domain="delta-execution-plan",
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id or f"plan:{self.plan_hash}",
            "planHash": self.plan_hash,
            "modelSnapshot": self.model.to_wire(),
            "toolPlan": {"tools": list(self.tools)},
            "toolMode": self.mode,
            "capabilities": list(self.capabilities),
            "environmentSnapshotId": self.environment_snapshot_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "state": self.state,
        }


class StepExecutionPlanStore:
    def __init__(self) -> None:
        self._plans: dict[str, ExecutionPlan] = {}
        self.active: ExecutionPlan | None = None
        self._lock = threading.RLock()

    def build_candidate(
        self,
        model: ModelSnapshot,
        tools: Iterable[str],
        env: str,
        auth: str,
        mode: str,
        *,
        capabilities: Iterable[str] = (),
        plan_id: str | None = None,
    ) -> ExecutionPlan:
        plan = ExecutionPlan(model, tuple(tools), env, auth, mode, "CANDIDATE", plan_id, tuple(capabilities))
        with self._lock:
            self._plans[plan.plan_id or plan.plan_hash] = plan
        return plan

    def finalize(self, candidate: ExecutionPlan) -> ExecutionPlan:
        if candidate.state != "CANDIDATE":
            if candidate.state in {"FINALIZED", "ACTIVE"}:
                return candidate
            raise ContractError("only a candidate plan may be finalized")
        finalized = replace(candidate, state="FINALIZED")
        key = finalized.plan_id or finalized.plan_hash
        with self._lock:
            prior = self._plans.get(key)
            if prior is not None and prior.plan_hash != finalized.plan_hash:
                raise ContractError("plan identity/hash conflict")
            self._plans[key] = finalized
            # Compatibility with the original compact API: finalization makes
            # the plan visible, while activation remains an explicit method.
            self.active = finalized
        return finalized

    def activate(self, plan: ExecutionPlan) -> ExecutionPlan:
        if plan.state not in {"FINALIZED", "ACTIVE"}:
            raise ContractError("only a finalized plan may activate")
        active = replace(plan, state="ACTIVE")
        with self._lock:
            if self.active is not None and self.active.plan_hash != active.plan_hash:
                self._plans[self.active.plan_id or self.active.plan_hash] = replace(self.active, state="RETIRED")
            self._plans[active.plan_id or active.plan_hash] = active
            self.active = active
        return active

    def retire(self, plan_id: str) -> ExecutionPlan:
        with self._lock:
            current = self._plans.get(plan_id)
            if current is None:
                raise ContractError("unknown execution plan")
            retired = replace(current, state="RETIRED")
            self._plans[plan_id] = retired
            if self.active is not None and (self.active.plan_id or self.active.plan_hash) == plan_id:
                self.active = None
            return retired

    def get(self, plan_id: str) -> ExecutionPlan | None:
        with self._lock:
            return self._plans.get(plan_id)


class PlanStore(StepExecutionPlanStore):
    pass


@dataclass(frozen=True, slots=True)
class PermissionProfile:
    filesystem_roots: tuple[str, ...]
    network: str
    mutable: bool
    extra: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.mutable, bool):
            raise ContractError("mutable must be boolean")
        for root in self.filesystem_roots:
            _text(root, "filesystem root")
        _text(self.network, "network")
        for pair in self.extra:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ContractError("permission extra must be a key/value tuple")

    def to_wire(self) -> dict[str, Any]:
        return {
            "filesystemRoots": list(self.filesystem_roots),
            "network": self.network,
            "mutable": self.mutable,
            "extra": {key: value for key, value in self.extra},
        }


@dataclass(frozen=True, slots=True)
class PermissionReplay:
    profile_id: str
    canonical_profile: Mapping[str, Any]
    provider: str
    version: str
    mapping: MappingResult
    value: Any = None
    resume_allowed: bool = False
    reason: str = ""

    def to_wire(self) -> dict[str, Any]:
        projection: dict[str, Any] = {
            "provider": self.provider,
            "version": self.version,
            "mapping": self.mapping.value,
        }
        if self.value is not None:
            projection["value"] = _thaw(self.value)
        return {
            "profileId": self.profile_id,
            "canonicalProfile": _thaw(self.canonical_profile),
            "providerProjection": projection,
            "resumeAllowed": self.resume_allowed,
            "reason": self.reason,
        }


class PermissionProjectionAdapter:
    @staticmethod
    def project(profile: PermissionProfile, representable: Mapping[str, PermissionProfile]) -> tuple[MappingResult, str | None]:
        for value, exact in representable.items():
            if not isinstance(value, str) or not isinstance(exact, PermissionProfile):
                raise ContractError("permission adapter map is invalid")
            if exact == profile:
                return MappingResult.EXACT, value
        return (MappingResult.UNSUPPORTED, None) if not representable else (MappingResult.LOSSY, None)

    @classmethod
    def replay(
        cls,
        profile_id: str,
        profile: PermissionProfile,
        *,
        provider: str,
        version: str,
        representable: Mapping[str, PermissionProfile],
    ) -> PermissionReplay:
        mapping, value = cls.project(profile, representable)
        return PermissionReplay(
            profile_id,
            MappingProxyType(profile.to_wire()),
            _text(provider, "provider"),
            _text(version, "version"),
            mapping,
            value,
            mapping is MappingResult.EXACT,
            "exact mapping" if mapping is MappingResult.EXACT else f"permission mapping is {mapping.value}",
        )

    @staticmethod
    def require_exact(result: MappingResult | PermissionReplay) -> None:
        mapping = result.mapping if isinstance(result, PermissionReplay) else result
        if mapping is not MappingResult.EXACT:
            raise ContractError(f"permission mapping is {mapping.value}")


class PermissionAdapter(PermissionProjectionAdapter):
    pass


@dataclass(slots=True)
class CapabilityLease:
    lease_id: str
    invocation_id: str
    environment_id: str
    authority_snapshot_id: str
    execution_epoch: int
    capabilities: frozenset[str]
    active: bool = True
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    delegation_allowed: bool = False
    state: str = "ACTIVE"

    def __post_init__(self) -> None:
        for name in ("lease_id", "invocation_id", "environment_id", "authority_snapshot_id"):
            _text(getattr(self, name), name)
        _nonnegative(self.execution_epoch, "execution_epoch")
        if self.state not in {"ACTIVE", "REVOKED", "EXPIRED"}:
            raise ContractError("invalid capability lease state")
        if not isinstance(self.active, bool) or not isinstance(self.delegation_allowed, bool):
            raise ContractError("invalid capability lease flags")
        self.issued_at = _aware(self.issued_at, "issued_at")
        self.expires_at = _aware(self.expires_at, "expires_at")
        if self.issued_at and self.expires_at and self.expires_at <= self.issued_at:
            raise ContractError("expires_at must follow issued_at")
        if not self.active:
            self.state = "REVOKED" if self.state == "ACTIVE" else self.state
        elif self.state != "ACTIVE":
            self.active = False

    def _expire_if_needed(self, now: datetime) -> None:
        if self.state != "ACTIVE":
            return
        if self.expires_at is not None and now.astimezone(UTC) >= self.expires_at:
            self.state = "EXPIRED"
            self.active = False

    def use(self, invocation_id: str, epoch: int, capability: str, *, now: datetime | None = None) -> None:
        check_now = (now or datetime.now(UTC)).astimezone(UTC)
        self._expire_if_needed(check_now)
        if self.state != "ACTIVE" or not self.active:
            raise ContractError("capability lease is not active")
        if invocation_id != self.invocation_id or epoch != self.execution_epoch:
            raise ContractError("capability lease scope mismatch")
        if capability not in self.capabilities:
            raise ContractError("capability not leased")

    def delegate(self, lease_id: str, invocation_id: str, *, capabilities: Iterable[str], execution_epoch: int) -> "CapabilityLease":
        if not self.delegation_allowed:
            raise ContractError("capability delegation is not allowed")
        requested = frozenset(capabilities)
        if not requested <= self.capabilities:
            raise ContractError("delegated capabilities widen parent lease")
        self.use(self.invocation_id, self.execution_epoch, next(iter(requested), "")) if requested else None
        return CapabilityLease(
            lease_id,
            invocation_id,
            self.environment_id,
            self.authority_snapshot_id,
            execution_epoch,
            requested,
            True,
            datetime.now(UTC),
            self.expires_at,
            False,
        )

    def revoke(self) -> None:
        if self.state != "EXPIRED":
            self.state = "REVOKED"
        self.active = False

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "leaseId": self.lease_id,
            "invocationId": self.invocation_id,
            "environmentId": self.environment_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "executionEpoch": self.execution_epoch,
            "capabilities": sorted(self.capabilities),
            "state": self.state,
            "delegationAllowed": self.delegation_allowed,
        }
        if self.issued_at is not None:
            output["issuedAt"] = self.issued_at.isoformat().replace("+00:00", "Z")
        if self.expires_at is not None:
            output["expiresAt"] = self.expires_at.isoformat().replace("+00:00", "Z")
        return output


class CapabilityLeaseBroker:
    def __init__(self) -> None:
        self._leases: dict[str, CapabilityLease] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        *,
        lease_id: str,
        invocation_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        execution_epoch: int,
        capabilities: Iterable[str],
        expires_at: datetime | None = None,
        delegation_allowed: bool = False,
    ) -> CapabilityLease:
        lease = CapabilityLease(
            lease_id,
            invocation_id,
            environment_id,
            authority_snapshot_id,
            execution_epoch,
            frozenset(capabilities),
            True,
            datetime.now(UTC),
            expires_at,
            delegation_allowed,
        )
        with self._lock:
            current = self._leases.get(lease_id)
            if current is not None and current.to_wire() != lease.to_wire():
                raise ContractError("conflicting capability lease")
            self._leases[lease_id] = current or lease
            return self._leases[lease_id]

    def get(self, lease_id: str) -> CapabilityLease | None:
        with self._lock:
            return self._leases.get(lease_id)

    def revoke(self, lease_id: str) -> CapabilityLease:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                raise ContractError("unknown capability lease")
            lease.revoke()
            return lease


@dataclass(frozen=True, slots=True)
class VerifiedSecurityContext:
    context_id: str
    issuer: str
    bindings: Mapping[str, str]
    status: str
    entitlements: Mapping[str, Any] = field(default_factory=dict)
    signature: str | None = None

    REQUIRED_BINDINGS = frozenset({"pluginId", "toolId", "accountId", "tenantId", "environmentId", "invocationId", "policyVersion"})

    def __post_init__(self) -> None:
        if self.status not in {"VERIFIED", "UNKNOWN", "DENIED"}:
            raise ContractError("invalid security context status")
        if set(self.bindings) != self.REQUIRED_BINDINGS:
            raise ContractError("security context bindings are not exact")
        for key, value in self.bindings.items():
            _text(key, "binding key")
            _text(value, f"binding {key}")
        if self.status == "VERIFIED" and not self.signature:
            raise ContractError("verified security context requires signature")

    def to_wire(self) -> dict[str, Any]:
        output = {
            "contextId": self.context_id,
            "issuer": self.issuer,
            "bindings": dict(self.bindings),
            "entitlements": _thaw(self.entitlements),
            "status": self.status,
        }
        if self.signature is not None:
            output["signature"] = self.signature
        return output


class SecurityContextBroker:
    RESERVED = frozenset({"verifiedSecurityContext", "entitlementContext", "executionAuthority", "securityContext", "authorization"})

    @classmethod
    def sanitize_caller_metadata(cls, metadata: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(metadata, Mapping):
            raise ContractError("caller metadata must be an object")
        return {str(key): value for key, value in metadata.items() if key not in cls.RESERVED}

    @classmethod
    def _signature(cls, *, issuer: str, context_id: str, bindings: Mapping[str, str], entitlements: Mapping[str, Any]) -> str:
        return _cas_digest(
            {"issuer": issuer, "contextId": context_id, "bindings": dict(bindings), "entitlements": _thaw(entitlements)},
            domain="delta-host-minted-security-context",
        )

    @classmethod
    def mint_context(
        cls,
        *,
        eligible: bool,
        account_stable: bool,
        bindings: Mapping[str, str],
        entitlements: Mapping[str, Any],
        issuer: str = "elmos-policy-broker",
        context_id: str | None = None,
    ) -> VerifiedSecurityContext:
        exact = set(bindings) == VerifiedSecurityContext.REQUIRED_BINDINGS and all(isinstance(v, str) and v.strip() for v in bindings.values())
        safe_bindings = {key: str(bindings.get(key, "")) for key in sorted(VerifiedSecurityContext.REQUIRED_BINDINGS)}
        cid = context_id or f"ctx:{_digest(safe_bindings, domain='delta-security-context-id')[:24]}"
        frozen_entitlements = _freeze(entitlements) if isinstance(entitlements, Mapping) else MappingProxyType({})
        if not eligible or not account_stable or not exact:
            return VerifiedSecurityContext(cid, issuer, safe_bindings, "UNKNOWN", MappingProxyType({}), None)
        signature = cls._signature(issuer=issuer, context_id=cid, bindings=safe_bindings, entitlements=frozen_entitlements)
        return VerifiedSecurityContext(cid, issuer, safe_bindings, "VERIFIED", frozen_entitlements, signature)

    @classmethod
    def mint(cls, *, eligible: bool, account_stable: bool, bindings: Mapping[str, str], entitlements: Mapping[str, Any]) -> dict[str, Any]:
        return cls.mint_context(eligible=eligible, account_stable=account_stable, bindings=bindings, entitlements=entitlements).to_wire()

    @classmethod
    def verify(cls, context: VerifiedSecurityContext | Mapping[str, Any]) -> VerifiedSecurityContext:
        if not isinstance(context, VerifiedSecurityContext):
            try:
                context = VerifiedSecurityContext(
                    str(context["contextId"]),
                    str(context["issuer"]),
                    dict(context["bindings"]),
                    str(context["status"]),
                    dict(context.get("entitlements", {})),
                    context.get("signature"),
                )
            except (KeyError, TypeError) as exc:
                raise ContractError("invalid security context") from exc
        if context.status == "VERIFIED":
            expected = cls._signature(issuer=context.issuer, context_id=context.context_id, bindings=context.bindings, entitlements=context.entitlements)
            if not context.signature or not hmac.compare_digest(expected, context.signature):
                raise ContractError("security context signature mismatch")
        return context


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    snapshot_id: str
    permissions: frozenset[str]
    owner_id: str = ""
    environment_id: str = ""
    permission_profile_version: str = ""
    effective_policy_hash: str = ""
    parent_snapshot_id: str | None = None
    widening: bool = False

    def __post_init__(self) -> None:
        _text(self.snapshot_id, "snapshot_id")
        if any(not isinstance(permission, str) or not permission for permission in self.permissions):
            raise ContractError("authority permission is invalid")
        if self.widening:
            raise ContractError("authority snapshot cannot declare widening")

    @staticmethod
    def intersect(
        owner: "AuthoritySnapshot",
        parent: "AuthoritySnapshot",
        policy: frozenset[str],
        snapshot_id: str,
        *,
        environment_id: str | None = None,
        permission_profile_version: str | None = None,
        effective_policy_hash: str | None = None,
    ) -> "AuthoritySnapshot":
        if owner.environment_id and parent.environment_id and owner.environment_id != parent.environment_id:
            raise ContractError("authority environment mismatch")
        permissions = owner.permissions & parent.permissions & frozenset(policy)
        return AuthoritySnapshot(
            snapshot_id,
            permissions,
            owner.owner_id,
            environment_id or owner.environment_id or parent.environment_id,
            permission_profile_version or owner.permission_profile_version,
            effective_policy_hash or owner.effective_policy_hash,
            parent.snapshot_id,
            False,
        )

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "snapshotId": self.snapshot_id,
            "ownerId": self.owner_id or "unknown",
            "environmentId": self.environment_id or "unknown",
            "permissionProfileVersion": self.permission_profile_version or "unknown",
            "effectivePolicyHash": self.effective_policy_hash or _cas_digest(sorted(self.permissions), domain="delta-policy"),
            "parentSnapshotId": self.parent_snapshot_id,
            "widening": False,
        }
        return output


class AuthorityCalculator:
    @staticmethod
    def calculate(owner: AuthoritySnapshot, parent: AuthoritySnapshot, policy_permissions: Iterable[str], snapshot_id: str) -> AuthoritySnapshot:
        return AuthoritySnapshot.intersect(owner, parent, frozenset(policy_permissions), snapshot_id)


class GenerationFence:
    def __init__(self, generation: int = 0, connection_epoch: int = 0, *, environment_id: str = "", executor_identity: str = "") -> None:
        self.generation = _nonnegative(generation, "generation")
        self.connection_epoch = _nonnegative(connection_epoch, "connection_epoch")
        self.environment_id = environment_id
        self.executor_identity = executor_identity
        self.state = "CONNECTING"
        self.live_probe_evidence_ref: str | None = None
        self._lock = threading.RLock()

    def reconnect_same(self) -> tuple[int, int]:
        with self._lock:
            self.connection_epoch += 1
            self.state = "CONNECTING"
            self.live_probe_evidence_ref = None
            return self.generation, self.connection_epoch

    def replace_executor(self) -> tuple[int, int]:
        with self._lock:
            self.generation += 1
            self.connection_epoch += 1
            self.state = "CONNECTING"
            self.live_probe_evidence_ref = None
            return self.generation, self.connection_epoch

    def activate(self, *, live_probe_evidence_ref: str | None = None) -> tuple[int, int]:
        with self._lock:
            if live_probe_evidence_ref is None or not str(live_probe_evidence_ref).strip():
                raise ContractError("live probe evidence is required before activation")
            self.live_probe_evidence_ref = live_probe_evidence_ref
            self.state = "ACTIVE"
            return self.generation, self.connection_epoch

    def retire(self) -> None:
        with self._lock:
            self.state = "RETIRED"

    def fail(self) -> None:
        with self._lock:
            self.state = "FAILED"

    def accept(self, generation: int, connection_epoch: int) -> None:
        with self._lock:
            if self.state != "ACTIVE":
                raise ContractError("executor is not active")
            if (generation, connection_epoch) != (self.generation, self.connection_epoch):
                raise ContractError("stale executor result")

    def to_wire(self) -> dict[str, Any]:
        return {
            "environmentId": self.environment_id,
            "executorIdentity": self.executor_identity,
            "executorGeneration": self.generation,
            "connectionEpoch": self.connection_epoch,
            "state": self.state,
            "liveProbeEvidenceRef": self.live_probe_evidence_ref,
        }


class ExecutorGenerationManager(GenerationFence):
    pass


@dataclass(frozen=True, slots=True)
class WorkspaceLease:
    workspace_id: str
    owner_execution_id: str
    generation: int
    repository_id: str
    base_revision: str
    write_scopes: tuple[str, ...] = ()
    state: str = "ACTIVE"

    def __post_init__(self) -> None:
        for name in ("workspace_id", "owner_execution_id", "repository_id", "base_revision"):
            _text(getattr(self, name), name)
        _nonnegative(self.generation, "generation")
        if self.state not in {"ACTIVE", "HANDOFF_PENDING", "RETIRED", "TAKEOVER_PENDING"}:
            raise ContractError("invalid workspace lease state")
        for scope in self.write_scopes:
            _text(scope, "write_scope")

    def owns(self, execution_id: str, *, scope: str | None = None) -> bool:
        if self.state != "ACTIVE" or execution_id != self.owner_execution_id:
            return False
        return scope is None or scope in self.write_scopes or not self.write_scopes

    def to_wire(self) -> dict[str, Any]:
        return {
            "workspaceId": self.workspace_id,
            "ownerExecutionId": self.owner_execution_id,
            "generation": self.generation,
            "repositoryId": self.repository_id,
            "baseRevision": self.base_revision,
            "writeScopes": list(self.write_scopes),
            "state": self.state,
        }


class WorkspaceLeaseManager:
    def __init__(self) -> None:
        self._active: dict[str, WorkspaceLease] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _overlap(left: Sequence[str], right: Sequence[str]) -> bool:
        if not left or not right:
            return True
        def covered(a: str, b: str) -> bool:
            return a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")
        return any(covered(a, b) for a in left for b in right)

    def bind(self, lease: WorkspaceLease) -> WorkspaceLease:
        with self._lock:
            current = self._active.get(lease.workspace_id)
            if current is None or current.state in {"RETIRED", "TAKEOVER_PENDING"}:
                self._active[lease.workspace_id] = lease
                return lease
            if current == lease:
                return current
            if current.owner_execution_id != lease.owner_execution_id and self._overlap(current.write_scopes, lease.write_scopes):
                raise ContractError("workspace owner/write-scope conflict")
            raise ContractError("workspace owner conflict")

    def request_handoff(self, workspace_id: str) -> WorkspaceLease:
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            pending = replace(current, state="HANDOFF_PENDING")
            self._active[workspace_id] = pending
            return pending

    def takeover(self, workspace_id: str, new_owner: str, *, base_revision: str | None = None, write_scopes: Iterable[str] | None = None) -> WorkspaceLease:
        _text(new_owner, "new_owner")
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            replacement = replace(
                current,
                owner_execution_id=new_owner,
                generation=current.generation + 1,
                base_revision=base_revision or current.base_revision,
                write_scopes=tuple(write_scopes) if write_scopes is not None else current.write_scopes,
                state="ACTIVE",
            )
            self._active[workspace_id] = replacement
            return replacement

    def retire(self, workspace_id: str) -> WorkspaceLease:
        with self._lock:
            current = self._active.get(workspace_id)
            if current is None:
                raise ContractError("unknown workspace")
            retired = replace(current, state="RETIRED")
            self._active[workspace_id] = retired
            return retired

    def get(self, workspace_id: str) -> WorkspaceLease | None:
        with self._lock:
            return self._active.get(workspace_id)


@dataclass(frozen=True, slots=True)
class ProtocolCapabilities:
    provider: str
    version: str
    features: frozenset[str]
    transport: str = "CUSTOM"
    history_mode: str = "NONE"
    typed_tool_result: bool = False
    schema_dialect: str = "json-schema"
    consistency_model: str = "UNKNOWN"
    auth_scheme: str | None = None
    unsupported_required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.provider, "provider")
        _text(self.version, "version")
        if self.transport not in {"LOCAL_STDIO", "REMOTE_GATEWAY", "HTTP", "WEBSOCKET", "ACP", "CUSTOM"}:
            raise ContractError("invalid protocol transport")
        if self.history_mode not in {"LEGACY_EMBEDDED", "PAGINATED", "BOTH", "NONE"}:
            raise ContractError("invalid history mode")
        if self.consistency_model not in {"STRONG", "EVENTUAL", "UNKNOWN"}:
            raise ContractError("invalid consistency model")

    def require(self, required: Iterable[str]) -> None:
        missing = set(required) - set(self.features)
        missing.update(self.unsupported_required)
        if "typedToolResult" in required and not self.typed_tool_result:
            missing.add("typedToolResult")
        if missing:
            raise ContractError(f"unsupported protocol capabilities: {sorted(missing)}")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "provider": self.provider,
            "version": self.version,
            "transport": self.transport,
            "historyMode": self.history_mode,
            "typedToolResult": self.typed_tool_result,
            "schemaDialect": self.schema_dialect,
            "consistencyModel": self.consistency_model,
            "features": sorted(self.features),
            "unsupportedRequired": list(self.unsupported_required),
        }
        if self.auth_scheme is not None:
            output["authScheme"] = self.auth_scheme
        return output


class ProtocolNegotiator:
    def __init__(self, profiles: Mapping[tuple[str, str], ProtocolCapabilities] | None = None) -> None:
        self._profiles = dict(profiles or {})
        self._epochs: dict[tuple[str, str, int], ProtocolCapabilities] = {}

    def register(self, profile: ProtocolCapabilities) -> None:
        key = (profile.provider, profile.version)
        current = self._profiles.get(key)
        if current is not None and current != profile:
            raise ContractError("conflicting protocol profile")
        self._profiles[key] = profile

    def negotiate(
        self,
        offered: ProtocolCapabilities,
        *,
        required_features: Iterable[str] = (),
        required_version: str | None = None,
        connection_epoch: int = 0,
    ) -> ProtocolCapabilities:
        _nonnegative(connection_epoch, "connection_epoch")
        profile = self._profiles.get((offered.provider, offered.version), offered)
        if required_version is not None and offered.version != required_version:
            raise ContractError("protocol version mismatch")
        profile.require(required_features)
        key = (offered.provider, offered.version, connection_epoch)
        prior = self._epochs.get(key)
        if prior is not None and prior != profile:
            raise ContractError("protocol capability changed within connection epoch")
        self._epochs[key] = profile
        return profile


@dataclass(frozen=True, slots=True)
class SkillProvenance:
    skill_id: str
    publisher: str
    origin: str
    canonical_uri: str
    package_digest: str
    trust_domain: str
    install_scope: str
    authorization_semantics: tuple[str, ...]
    signature: str | None = None
    verified: bool = False

    def __post_init__(self) -> None:
        for name in ("skill_id", "publisher", "origin", "canonical_uri", "package_digest", "install_scope"):
            _text(getattr(self, name), name)
        if self.trust_domain not in {"USER", "ENTERPRISE", "MARKETPLACE", "REPOSITORY", "EPHEMERAL"}:
            raise ContractError("invalid Skill trust domain")
        if self.verified and not self.signature:
            raise ContractError("verified Skill provenance requires signature")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "skillId": self.skill_id,
            "publisher": self.publisher,
            "origin": self.origin,
            "canonicalUri": self.canonical_uri,
            "packageDigest": self.package_digest,
            "trustDomain": self.trust_domain,
            "installScope": self.install_scope,
            "authorizationSemantics": list(self.authorization_semantics),
            "verified": self.verified,
        }
        if self.signature is not None:
            output["signature"] = self.signature
        return output


class SkillTrustVerifier:
    @staticmethod
    def verify(skill_path: Path, trusted_root: Path) -> Path:
        root = trusted_root.resolve(strict=True)
        raw = Path(skill_path)
        try:
            if raw.is_symlink():
                raise ContractError("skill path cannot be a symlink")
            actual = raw.resolve(strict=True)
            actual.relative_to(root)
        except (FileNotFoundError, ValueError) as exc:
            raise ContractError("skill path escapes trust root or is unavailable") from exc
        if actual.is_symlink() or not actual.is_file():
            raise ContractError("skill path must be a regular file")
        return actual

    @classmethod
    def verify_provenance(
        cls,
        provenance: SkillProvenance,
        *,
        skill_path: Path,
        trusted_root: Path,
        signature_verifier: Callable[[bytes, str], bool] | None = None,
    ) -> SkillProvenance:
        actual = cls.verify(skill_path, trusted_root)
        content = actual.read_bytes()
        expected = digest_bytes(content, domain="delta-skill-package")
        if provenance.package_digest not in {expected, digest_bytes(content, domain="artifact")}:
            raise ContractError("Skill package digest mismatch")
        if provenance.trust_domain == "MARKETPLACE" and signature_verifier is None:
            raise ContractError("marketplace provenance requires an independent signature verifier")
        verified = bool(provenance.signature and signature_verifier and signature_verifier(content, provenance.signature))
        if provenance.trust_domain in {"MARKETPLACE", "ENTERPRISE"} and not verified:
            raise ContractError("Skill provenance signature is not verified")
        return replace(provenance, canonical_uri=actual.as_uri(), verified=verified)


@dataclass(frozen=True, slots=True)
class EventRegistration:
    event_type: str
    owner: str
    schema_version: int
    semantics: str
    validator: Callable[[Mapping[str, Any]], bool] | str = field(compare=False, repr=False)
    upgrader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | str = field(compare=False, repr=False)
    projections: tuple[str, ...] = ()
    compatibility: str = "STRICT"

    def __post_init__(self) -> None:
        _text(self.event_type, "event_type")
        _text(self.owner, "owner")
        if self.schema_version < 1 or isinstance(self.schema_version, bool):
            raise ContractError("schema_version must be >= 1")
        if self.semantics not in {"OPTIONAL_OBSERVATION", "REQUIRED_STATE"}:
            raise ContractError("invalid event semantics")
        if self.compatibility not in {"STRICT", "BACKWARD", "FORWARD", "FULL"}:
            raise ContractError("invalid event compatibility")

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": self.event_type,
            "owner": self.owner,
            "schemaVersion": self.schema_version,
            "semantics": self.semantics,
            "validator": self.validator if isinstance(self.validator, str) else "callable",
            "upgrader": self.upgrader if isinstance(self.upgrader, str) else "callable",
            "projections": list(self.projections),
            "compatibility": self.compatibility,
        }


class DurableEventRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, int], EventRegistration] = {}
        self._lock = threading.RLock()

    def register(self, item: EventRegistration) -> None:
        key = (item.event_type, item.schema_version)
        with self._lock:
            current = self._items.get(key)
            if current is not None and current.to_wire() != item.to_wire():
                raise ContractError("conflicting event registration")
            self._items[key] = item

    @staticmethod
    def _validate(item: EventRegistration, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise ContractError("event payload must be an object")
        if callable(item.validator):
            try:
                valid = bool(item.validator(payload))
            except Exception as exc:
                raise ContractError("event schema validator failed") from exc
            if not valid:
                raise ContractError("event schema validation failed")
        return payload

    def replay(
        self,
        event_type: str,
        version: int,
        payload: Mapping[str, Any],
        *,
        unknown_optional: bool = False,
        target_version: int | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get((event_type, version))
            if item is None:
                if unknown_optional:
                    return None
                raise ContractError("unknown required durable event")
            value: Mapping[str, Any] = self._validate(item, payload)
            target = target_version or version
            while version < target:
                next_item = self._items.get((event_type, version + 1))
                if next_item is None:
                    raise ContractError("missing durable event upgrader")
                if callable(next_item.upgrader):
                    try:
                        value = next_item.upgrader(value)
                    except Exception as exc:
                        raise ContractError("event upgrade failed") from exc
                elif not isinstance(next_item.upgrader, str):
                    raise ContractError("event upgrader is unavailable")
                value = self._validate(next_item, value)
                version += 1
            return dict(value)


class IngressKind(StrEnum):
    USER_INPUT = "USER_INPUT"
    TOOL_RESULT = "TOOL_RESULT"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"
    APPROVAL_INPUT = "APPROVAL_INPUT"
    CONTROL_INPUT = "CONTROL_INPUT"


@dataclass(frozen=True, slots=True)
class TypedIngress:
    ingress_id: str
    kind: str
    producer_execution_id: str
    event_id: str
    causation_id: str
    correlation_id: str
    content: str | tuple[Mapping[str, Any], ...]
    originating_call_id: str | None = None
    deduplication_key: str | None = None

    def __post_init__(self) -> None:
        for name in ("ingress_id", "producer_execution_id", "event_id", "causation_id", "correlation_id"):
            _text(getattr(self, name), name)
        if self.kind not in {item.value for item in IngressKind}:
            raise ContractError("unknown ingress kind")
        if self.originating_call_id is not None:
            _text(self.originating_call_id, "originating_call_id")
        if not isinstance(self.content, str) and not isinstance(self.content, (tuple, list)):
            raise ContractError("ingress content must remain typed text or content parts")
        if isinstance(self.content, (tuple, list)):
            for part in self.content:
                if not isinstance(part, Mapping):
                    raise ContractError("typed ingress content parts must be objects")
                _freeze(part)

    def to_wire(self) -> dict[str, Any]:
        return {
            "ingressId": self.ingress_id,
            "kind": self.kind,
            "producerExecutionId": self.producer_execution_id,
            "originatingCallId": self.originating_call_id,
            "eventId": self.event_id,
            "causationId": self.causation_id,
            "correlationId": self.correlation_id,
            "content": _thaw(self.content),
            **({"deduplicationKey": self.deduplication_key} if self.deduplication_key else {}),
        }


class IngressLedger:
    def __init__(self) -> None:
        self._seen: dict[str, tuple[str, str]] = {}
        self._lock = threading.RLock()

    def accept(self, key: str, kind: str, *, envelope_digest: str | None = None) -> bool:
        _text(key, "deduplication key")
        if kind not in {item.value for item in IngressKind}:
            raise ContractError("unknown ingress kind")
        fingerprint = envelope_digest or ""
        with self._lock:
            current = self._seen.get(key)
            if current is not None:
                if current != (kind, fingerprint):
                    raise ContractError("conflicting duplicate ingress")
                return False
            self._seen[key] = (kind, fingerprint)
            return True


class IngressRouter:
    def __init__(self, ledger: IngressLedger | None = None) -> None:
        self.ledger = ledger or IngressLedger()
        self._events: dict[str, TypedIngress] = {}
        self._producers: dict[str, set[str]] = {}
        self._lock = threading.RLock()

    def accept(
        self,
        ingress: TypedIngress,
        *,
        tenant_id: str | None = None,
        expected_producer: str | None = None,
        pending_calls: Iterable[str] = (),
    ) -> bool:
        if expected_producer is not None and ingress.producer_execution_id != expected_producer:
            raise ContractError("ingress producer identity mismatch")
        if ingress.kind == IngressKind.TOOL_RESULT and ingress.originating_call_id is None:
            raise ContractError("tool result ingress requires originating call")
        if ingress.kind == IngressKind.TOOL_RESULT and ingress.originating_call_id not in set(pending_calls):
            raise ContractError("tool result ingress has no pending or reconciled origin")
        scope = tenant_id or "unscoped"
        key = ingress.deduplication_key or ingress.event_id
        scoped_key = f"{scope}:{ingress.producer_execution_id}:{key}"
        envelope_digest = _cas_digest(ingress.to_wire(), domain="delta-typed-ingress")
        accepted = self.ledger.accept(scoped_key, ingress.kind, envelope_digest=envelope_digest)
        with self._lock:
            if accepted:
                self._events[ingress.ingress_id] = ingress
                self._producers.setdefault(ingress.producer_execution_id, set()).add(ingress.ingress_id)
            elif ingress.ingress_id in self._events and self._events[ingress.ingress_id] != ingress:
                raise ContractError("ingress identity replay diverged")
        return accepted

    def history(self, correlation_id: str, *, page: int = 0, page_size: int = 100) -> tuple[TypedIngress, ...]:
        if page < 0 or page_size < 1 or page_size > 1000:
            raise ContractError("invalid ingress page")
        with self._lock:
            events = sorted((item for item in self._events.values() if item.correlation_id == correlation_id), key=lambda item: item.event_id)
            start = page * page_size
            return tuple(events[start : start + page_size])


@dataclass(frozen=True, slots=True)
class SubagentSpec:
    provider: str
    model: str
    reasoning_effort: str
    max_output_tokens: int
    authority: frozenset[str]
    tools: frozenset[str]
    parent_execution_id: str = ""
    environment_id: str = ""
    authority_snapshot_id: str = ""
    budget_reservation_id: str = ""
    tool_plan_hash: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "model", "reasoning_effort"):
            _text(getattr(self, name), name)
        if isinstance(self.max_output_tokens, bool) or self.max_output_tokens < 1:
            raise ContractError("max_output_tokens must be positive")
        for value in (*self.authority, *self.tools):
            _text(value, "subagent scope")

    def validate_under(
        self,
        parent_authority: frozenset[str],
        parent_tools: frozenset[str],
        max_tokens: int,
        *,
        environment_id: str | None = None,
        parent_environment_id: str | None = None,
        reserved_budget: bool = True,
    ) -> None:
        if not self.authority <= parent_authority:
            raise ContractError("subagent authority widening")
        if not self.tools <= parent_tools:
            raise ContractError("subagent tool widening")
        if self.max_output_tokens > max_tokens:
            raise ContractError("subagent output budget exceeded")
        if environment_id is not None and parent_environment_id is not None and environment_id != parent_environment_id:
            raise ContractError("subagent environment widening")
        if not reserved_budget:
            raise ContractError("subagent budget is not reserved")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "maxOutputTokens": self.max_output_tokens,
            "parentExecutionId": self.parent_execution_id,
            "environmentId": self.environment_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "budgetReservationId": self.budget_reservation_id,
        }
        if self.tool_plan_hash is not None:
            output["toolPlanHash"] = self.tool_plan_hash
        return output


SubagentExecutionSpec = SubagentSpec


class SubagentSpecCompiler:
    @staticmethod
    def compile(
        *,
        provider: str,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        parent_execution_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        budget_reservation_id: str,
        parent_authority: Iterable[str] = (),
        child_authority: Iterable[str] = (),
        parent_tools: Iterable[str] = (),
        child_tools: Iterable[str] = (),
        parent_max_output_tokens: int | None = None,
        tool_plan_hash: str | None = None,
    ) -> SubagentSpec:
        spec = SubagentSpec(
            provider,
            model,
            reasoning_effort,
            max_output_tokens,
            frozenset(child_authority),
            frozenset(child_tools),
            parent_execution_id,
            environment_id,
            authority_snapshot_id,
            budget_reservation_id,
            tool_plan_hash,
        )
        spec.validate_under(
            frozenset(parent_authority),
            frozenset(parent_tools),
            parent_max_output_tokens if parent_max_output_tokens is not None else max_output_tokens,
            reserved_budget=bool(budget_reservation_id),
        )
        return spec


@dataclass(frozen=True, slots=True)
class DeltaInvocation:
    tenant_id: str
    goal_id: str
    run_id: str
    execution_epoch: int
    step_id: str
    invocation_id: str
    revision_set_id: str
    extension_skill: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("tenant_id", "goal_id", "run_id", "step_id", "invocation_id", "revision_set_id"):
            _text(getattr(self, name), name)
        _nonnegative(self.execution_epoch, "execution_epoch")
        if self.extension_skill is not None:
            _text(self.extension_skill, "extension_skill")
        if not isinstance(self.payload, Mapping):
            raise ContractError("delta invocation payload must be an object")
        _freeze(self.payload)

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "tenantId": self.tenant_id,
            "goalId": self.goal_id,
            "runId": self.run_id,
            "executionEpoch": self.execution_epoch,
            "stepId": self.step_id,
            "invocationId": self.invocation_id,
            "revisionSetId": self.revision_set_id,
        }
        if self.extension_skill is not None:
            output["extensionSkill"] = self.extension_skill
        if self.payload:
            output["payload"] = _thaw(self.payload)
        return output


@dataclass(frozen=True, slots=True)
class DeltaResult:
    invocation_id: str
    status: ResultStatus | str
    evidence_refs: tuple[str, ...] = ()
    proof_obligation_refs: tuple[str, ...] = ()
    message: str | None = None

    def __post_init__(self) -> None:
        _text(self.invocation_id, "invocation_id")
        try:
            ResultStatus(self.status)
        except ValueError as exc:
            raise ContractError("invalid delta result status") from exc
        for value in (*self.evidence_refs, *self.proof_obligation_refs):
            _text(value, "evidence/proof reference")
        if self.message is not None:
            _text(self.message, "message")

    def to_wire(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "invocationId": self.invocation_id,
            "status": ResultStatus(self.status).value,
            "evidenceRefs": list(self.evidence_refs),
        }
        if self.proof_obligation_refs:
            output["proofObligationRefs"] = list(self.proof_obligation_refs)
        if self.message is not None:
            output["message"] = self.message
        return output


@dataclass(frozen=True, slots=True)
class DeltaSkillDescriptor:
    skill_id: str
    name: str
    priority: str
    owner_kernels: tuple[str, ...]
    source_path: str
    routable: bool = False
    dependencies: tuple[str, ...] = ()
    handler: str = ""


def _descriptor(skill_id: str, name: str, priority: str, owners: Sequence[str], path: str, handler: str, deps: Sequence[str] = ()) -> DeltaSkillDescriptor:
    return DeltaSkillDescriptor(skill_id, name, priority, tuple(owners), path, False, tuple(deps), handler)


DELTA_SKILL_REGISTRY: dict[str, DeltaSkillDescriptor] = {
    item.name: item
    for item in (
        _descriptor("ELMOS-V3D-001", "elmos-tool-result-interception-commit", "P0", ("K7", "K6", "K8"), "P0/elmos-tool-result-interception-commit/SKILL.md", "ResultLifecycleCoordinator"),
        _descriptor("ELMOS-V3D-002", "elmos-step-finalized-execution-plan", "P0", ("K7", "K4"), "P0/elmos-step-finalized-execution-plan/SKILL.md", "StepExecutionPlanStore"),
        _descriptor("ELMOS-V3D-003", "elmos-lossless-permission-replay", "P0", ("K7", "K8"), "P0/elmos-lossless-permission-replay/SKILL.md", "PermissionProjectionAdapter"),
        _descriptor("ELMOS-V3D-004", "elmos-invocation-scoped-capability-lease", "P0", ("K7",), "P0/elmos-invocation-scoped-capability-lease/SKILL.md", "CapabilityLeaseBroker"),
        _descriptor("ELMOS-V3D-005", "elmos-host-minted-security-context", "P0", ("K7", "K8"), "P0/elmos-host-minted-security-context/SKILL.md", "SecurityContextBroker"),
        _descriptor("ELMOS-V3D-006", "elmos-environment-attachment-authority", "P0", ("K7",), "P0/elmos-environment-attachment-authority/SKILL.md", "AuthorityCalculator"),
        _descriptor("ELMOS-V3D-007", "elmos-executor-generation-fencing", "P0", ("K7",), "P0/elmos-executor-generation-fencing/SKILL.md", "ExecutorGenerationManager"),
        _descriptor("ELMOS-V3D-008", "elmos-workspace-ownership-lease", "P0", ("K7", "K5"), "P0/elmos-workspace-ownership-lease/SKILL.md", "WorkspaceLeaseManager"),
        _descriptor("ELMOS-V3D-009", "elmos-harness-transport-version-negotiation", "P0", ("K7",), "P0/elmos-harness-transport-version-negotiation/SKILL.md", "ProtocolNegotiator"),
        _descriptor("ELMOS-V3D-010", "elmos-skill-trust-domain-provenance", "P0", ("K7", "K8"), "P0/elmos-skill-trust-domain-provenance/SKILL.md", "SkillTrustVerifier"),
        _descriptor("ELMOS-V3D-011", "elmos-registered-durable-plugin-events", "P1", ("K7", "K8"), "P1/elmos-registered-durable-plugin-events/SKILL.md", "DurableEventRegistry"),
        _descriptor("ELMOS-V3D-012", "elmos-typed-external-ingress", "P1", ("K7", "K1"), "P1/elmos-typed-external-ingress/SKILL.md", "IngressRouter"),
        _descriptor("ELMOS-V3D-013", "elmos-subagent-model-execution-spec", "P1", ("K4", "K7"), "P1/elmos-subagent-model-execution-spec/SKILL.md", "SubagentSpecCompiler"),
    )
}

if len(DELTA_SKILL_REGISTRY) != 13 or any(descriptor.routable for descriptor in DELTA_SKILL_REGISTRY.values()):
    raise RuntimeError("v3.1 delta registry invariant failed")


def _ref(value: Any, *, domain: str) -> str:
    return "cas:" + _cas_digest(value, domain=domain)


class DeltaSkillRuntime:
    """Exact allowlisted internal extension runtime.

    The runtime accepts either a :class:`DeltaInvocation` or a wire-shaped
    mapping.  Unknown skills and malformed provider-shaped payloads produce a
    typed ``UNSUPPORTED``/``UNKNOWN`` result; they never fall through to a
    permissive generic handler or execute an external effect.
    """

    def __init__(self) -> None:
        self.result_committer = ResultLifecycleCoordinator()
        self.plan_store = StepExecutionPlanStore()
        self.lease_broker = CapabilityLeaseBroker()
        self.protocol_negotiator = ProtocolNegotiator()
        self.event_registry = DurableEventRegistry()
        self.ingress_router = IngressRouter()
        self.workspace_manager = WorkspaceLeaseManager()

    @staticmethod
    def _invocation(value: DeltaInvocation | Mapping[str, Any], skill: str | None = None) -> DeltaInvocation:
        if isinstance(value, DeltaInvocation):
            return value if skill is None else replace(value, extension_skill=skill)
        if not isinstance(value, Mapping):
            raise ContractError("delta invocation must be typed")
        return DeltaInvocation(
            str(value.get("tenantId", "")),
            str(value.get("goalId", "")),
            str(value.get("runId", "")),
            value.get("executionEpoch", -1),
            str(value.get("stepId", "")),
            str(value.get("invocationId", "")),
            str(value.get("revisionSetId", "")),
            skill or value.get("extensionSkill"),
            value.get("payload", {}),
        )

    def execute(
        self,
        invocation: DeltaInvocation | Mapping[str, Any],
        context: Any = None,
        runtime: Any = None,
        *,
        skill: str | None = None,
    ) -> DeltaResult:
        del context, runtime
        try:
            request = self._invocation(invocation, skill)
        except ContractError as exc:
            invocation_id = str(invocation.get("invocationId", "unknown")) if isinstance(invocation, Mapping) else "unknown"
            return DeltaResult(invocation_id or "unknown", ResultStatus.UNKNOWN, message=str(exc))
        name = request.extension_skill
        descriptor = DELTA_SKILL_REGISTRY.get(name or "")
        if descriptor is None:
            return DeltaResult(request.invocation_id, ResultStatus.UNSUPPORTED, message="extension Skill is not registered")
        try:
            output = self._dispatch(descriptor.name, request)
            if isinstance(output, DeltaResult):
                return output
            evidence = (_ref({"invocation": request.to_wire(), "output": output}, domain="delta-runtime-result"),)
            return DeltaResult(request.invocation_id, ResultStatus.COMMITTED, evidence, message=None)
        except ContractError as exc:
            text = str(exc)
            status = ResultStatus.REQUIRES_REVIEW if "review" in text.lower() else ResultStatus.DENIED
            return DeltaResult(request.invocation_id, status, message=text)
        except Exception as exc:
            return DeltaResult(request.invocation_id, ResultStatus.UNKNOWN, message=f"delta handler failed: {type(exc).__name__}")

    def _dispatch(self, name: str, invocation: DeltaInvocation) -> Any:
        payload = invocation.payload
        # Each entry is explicit in this table; there is no catch-all action.
        if name == "elmos-tool-result-interception-commit":
            raw = payload.get("rawResult") or payload.get("raw")
            if not isinstance(raw, Mapping):
                raise ContractError("tool result commit requires typed rawResult")
            identity = raw.get("identity") or raw.get("callIdentity")
            if not isinstance(identity, Mapping):
                raise ContractError("tool result commit requires call identity")
            tool = ToolResult(
                CallIdentity(str(identity.get("invocationId", "")), str(identity.get("callId", "")), str(identity.get("executionPlanHash", "")), str(identity.get("environmentId", "")), str(identity.get("authoritySnapshotId", ""))),
                bool(raw.get("ok", True)),
                raw.get("content"),
            )
            result = self.result_committer.commit(tool, (), attempt=payload.get("attempt", 0), epoch=invocation.execution_epoch)
            return result.to_wire()
        if name == "elmos-step-finalized-execution-plan":
            model = payload.get("modelSnapshot")
            if not isinstance(model, Mapping):
                raise ContractError("execution plan requires modelSnapshot")
            plan = self.plan_store.build_candidate(
                ModelSnapshot(str(model.get("provider", "")), str(model.get("model", "")), str(model.get("revision", "")), model.get("reasoningEffort")),
                tuple(str(item) for item in payload.get("tools", payload.get("toolPlan", {}).get("tools", ()))),
                str(payload.get("environmentSnapshotId", "")),
                str(payload.get("authoritySnapshotId", "")),
                str(payload.get("toolMode", payload.get("mode", "NATIVE"))),
                capabilities=tuple(str(item) for item in payload.get("capabilities", ())),
                plan_id=str(payload.get("planId", "")) or None,
            )
            return self.plan_store.finalize(plan).to_wire()
        if name == "elmos-lossless-permission-replay":
            profile_data = payload.get("canonicalProfile")
            if not isinstance(profile_data, Mapping):
                raise ContractError("permission replay requires canonicalProfile")
            profile = PermissionProfile(tuple(str(item) for item in profile_data.get("filesystemRoots", profile_data.get("fs", ()))), str(profile_data.get("network", "deny")), bool(profile_data.get("mutable", False)), tuple((str(k), str(v)) for k, v in profile_data.get("extra", {}).items()) if isinstance(profile_data.get("extra", {}), Mapping) else ())
            projection = payload.get("representable", {})
            if not isinstance(projection, Mapping):
                raise ContractError("permission replay representable map must be object")
            profiles = {str(key): profile if value in (None, profile.to_wire()) else profile for key, value in projection.items()}
            return PermissionProjectionAdapter.replay(str(payload.get("profileId", "")), profile, provider=str(payload.get("provider", "unknown")), version=str(payload.get("version", DELTA_VERSION)), representable=profiles).to_wire()
        if name == "elmos-invocation-scoped-capability-lease":
            lease = self.lease_broker.issue(lease_id=str(payload.get("leaseId", "")), invocation_id=invocation.invocation_id, environment_id=str(payload.get("environmentId", "")), authority_snapshot_id=str(payload.get("authoritySnapshotId", "")), execution_epoch=invocation.execution_epoch, capabilities=tuple(str(item) for item in payload.get("capabilities", ())), delegation_allowed=bool(payload.get("delegationAllowed", False)))
            return lease.to_wire()
        if name == "elmos-host-minted-security-context":
            return SecurityContextBroker.mint_context(eligible=bool(payload.get("eligible", False)), account_stable=bool(payload.get("accountStable", False)), bindings=payload.get("bindings", {}), entitlements=payload.get("entitlements", {})).to_wire()
        if name == "elmos-environment-attachment-authority":
            owner = AuthoritySnapshot(str(payload.get("ownerSnapshotId", "owner")), frozenset(str(item) for item in payload.get("ownerPermissions", ())), str(payload.get("ownerId", "")), str(payload.get("environmentId", "")))
            parent = AuthoritySnapshot(str(payload.get("parentSnapshotId", "parent")), frozenset(str(item) for item in payload.get("parentPermissions", ())), str(payload.get("parentOwnerId", "")), str(payload.get("environmentId", "")))
            return AuthorityCalculator.calculate(owner, parent, tuple(str(item) for item in payload.get("policyPermissions", ())), str(payload.get("snapshotId", ""))).to_wire()
        if name == "elmos-executor-generation-fencing":
            fence = ExecutorGenerationManager(int(payload.get("generation", 0)), int(payload.get("connectionEpoch", 0)), environment_id=str(payload.get("environmentId", "")), executor_identity=str(payload.get("executorIdentity", "")))
            action = str(payload.get("action", "reconnect"))
            if action == "reconnect":
                fence.reconnect_same()
            elif action == "replace":
                fence.replace_executor()
            elif action == "activate":
                fence.activate(live_probe_evidence_ref=str(payload.get("liveProbeEvidenceRef", "")))
            else:
                raise ContractError("unsupported executor lifecycle action")
            return fence.to_wire()
        if name == "elmos-workspace-ownership-lease":
            lease = WorkspaceLease(str(payload.get("workspaceId", "")), str(payload.get("ownerExecutionId", invocation.run_id)), int(payload.get("generation", 0)), str(payload.get("repositoryId", "")), str(payload.get("baseRevision", "")), tuple(str(item) for item in payload.get("writeScopes", ())))
            action = str(payload.get("action", "bind"))
            if action == "bind":
                return self.workspace_manager.bind(lease).to_wire()
            if action == "takeover":
                return self.workspace_manager.takeover(lease.workspace_id, lease.owner_execution_id, base_revision=lease.base_revision, write_scopes=lease.write_scopes).to_wire()
            raise ContractError("unsupported workspace lifecycle action")
        if name == "elmos-harness-transport-version-negotiation":
            caps = ProtocolCapabilities(str(payload.get("provider", "")), str(payload.get("version", "")), frozenset(str(item) for item in payload.get("features", ())), str(payload.get("transport", "CUSTOM")), str(payload.get("historyMode", "NONE")), bool(payload.get("typedToolResult", False)), str(payload.get("schemaDialect", "json-schema")), str(payload.get("consistencyModel", "UNKNOWN")), payload.get("authScheme"), tuple(str(item) for item in payload.get("unsupportedRequired", ())))
            return self.protocol_negotiator.negotiate(caps, required_features=tuple(str(item) for item in payload.get("requiredFeatures", ())), connection_epoch=invocation.execution_epoch).to_wire()
        if name == "elmos-skill-trust-domain-provenance":
            provenance = payload.get("provenance")
            if not isinstance(provenance, Mapping):
                raise ContractError("Skill trust verification requires provenance")
            return SkillProvenance(str(provenance.get("skillId", "")), str(provenance.get("publisher", "")), str(provenance.get("origin", "")), str(provenance.get("canonicalUri", "")), str(provenance.get("packageDigest", "")), str(provenance.get("trustDomain", "")), str(provenance.get("installScope", "")), tuple(str(item) for item in provenance.get("authorizationSemantics", ())), provenance.get("signature"), bool(provenance.get("verified", False))).to_wire()
        if name == "elmos-registered-durable-plugin-events":
            registration = payload.get("registration")
            if not isinstance(registration, Mapping):
                raise ContractError("durable event registration is required")
            self.event_registry.register(EventRegistration(str(registration.get("type", "")), str(registration.get("owner", "")), int(registration.get("schemaVersion", 0)), str(registration.get("semantics", "")), str(registration.get("validator", "")), str(registration.get("upgrader", "")), tuple(str(item) for item in registration.get("projections", ())), str(registration.get("compatibility", "STRICT"))))
            return {"registered": True, "type": registration["type"], "schemaVersion": registration["schemaVersion"]}
        if name == "elmos-typed-external-ingress":
            ingress_data = payload.get("ingress")
            if not isinstance(ingress_data, Mapping):
                raise ContractError("typed ingress is required")
            content = ingress_data.get("content")
            if isinstance(content, list):
                content = tuple(_freeze(item) for item in content)
            ingress = TypedIngress(str(ingress_data.get("ingressId", "")), str(ingress_data.get("kind", "")), str(ingress_data.get("producerExecutionId", "")), str(ingress_data.get("eventId", "")), str(ingress_data.get("causationId", "")), str(ingress_data.get("correlationId", "")), content, ingress_data.get("originatingCallId"), ingress_data.get("deduplicationKey"))
            return {"accepted": self.ingress_router.accept(ingress, tenant_id=invocation.tenant_id, pending_calls=tuple(str(item) for item in payload.get("pendingCalls", ()))), "ingress": ingress.to_wire()}
        if name == "elmos-subagent-model-execution-spec":
            return SubagentSpecCompiler.compile(provider=str(payload.get("provider", "")), model=str(payload.get("model", "")), reasoning_effort=str(payload.get("reasoningEffort", "")), max_output_tokens=int(payload.get("maxOutputTokens", 0)), parent_execution_id=str(payload.get("parentExecutionId", "")), environment_id=str(payload.get("environmentId", "")), authority_snapshot_id=str(payload.get("authoritySnapshotId", "")), budget_reservation_id=str(payload.get("budgetReservationId", "")), parent_authority=tuple(str(item) for item in payload.get("parentAuthority", ())), child_authority=tuple(str(item) for item in payload.get("childAuthority", ())), parent_tools=tuple(str(item) for item in payload.get("parentTools", ())), child_tools=tuple(str(item) for item in payload.get("childTools", ())), parent_max_output_tokens=payload.get("parentMaxOutputTokens"), tool_plan_hash=payload.get("toolPlanHash")).to_wire()
        raise ContractError("extension handler is not allowlisted")


__all__ = [
    "AuthorityCalculator",
    "AuthoritySnapshot",
    "CallIdentity",
    "CapabilityLease",
    "CapabilityLeaseBroker",
    "CommitState",
    "CommittedToolResult",
    "ContractError",
    "DELTA_API_VERSION",
    "DELTA_SKILL_REGISTRY",
    "DELTA_VERSION",
    "DeltaInvocation",
    "DeltaResult",
    "DeltaSkillDescriptor",
    "DeltaSkillRuntime",
    "DurableEventRegistry",
    "EventRegistration",
    "ExecutionPlan",
    "ExecutorGenerationManager",
    "GenerationFence",
    "IngressKind",
    "IngressLedger",
    "IngressRouter",
    "InterceptorDecision",
    "MappingResult",
    "ModelSnapshot",
    "PermissionAdapter",
    "PermissionProfile",
    "PermissionProjectionAdapter",
    "PermissionReplay",
    "PlanStore",
    "ProtocolCapabilities",
    "ProtocolNegotiator",
    "ResultCommitter",
    "ResultLifecycleCoordinator",
    "ResultStatus",
    "SecurityContextBroker",
    "SkillProvenance",
    "SkillTrustVerifier",
    "StepExecutionPlanStore",
    "SubagentExecutionSpec",
    "SubagentSpec",
    "SubagentSpecCompiler",
    "ToolResult",
    "TypedIngress",
    "VerifiedSecurityContext",
    "WorkspaceLease",
    "WorkspaceLeaseManager",
    "digest",
]
