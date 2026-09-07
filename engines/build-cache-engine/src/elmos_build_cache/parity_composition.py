"""Server-owned composition for the five cache-parity serving layers.

The module is deliberately a composition seam, not another cache engine.  A
request cannot register a port, provider adapter, executor, verifier, receipt,
or evidence source.  Those dependencies are supplied once by trusted runtime
composition and every cache effect is re-authorized against an asymmetric,
signed boundary.

Only a verified exact Action Cache result may replace correct execution.  A
prompt, context, environment, or affinity hit restores only its corresponding
piece of work and the fallback executor still runs the remaining partition.
Cache deadline exhaustion, port failure, scope drift, or an invalid grant is a
typed slow-path outcome and never permission to skip fallback execution.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from .canonical import digest_of, require_digest
from .errors import ContractViolation, PermissionDenied, ProvenanceInvalid
from .security import ProvenanceSigner, SignedStatement, require_asymmetric

SERVING_BOUNDARY_KIND = "elmos.cache-parity-composition-serving/v1.2"
SERVING_BOUNDARY_DECISION = "AUTHORIZE_CACHE_PARITY_COMPOSITION"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")


class _ValueEnum(StrEnum):
    pass


class CompositionLayer(_ValueEnum):
    PROMPT = "PROMPT"
    CONTEXT = "CONTEXT"
    ACTION = "ACTION"
    ENVIRONMENT = "ENVIRONMENT"
    AFFINITY = "AFFINITY"


class LayerWork(_ValueEnum):
    PROMPT_PREFIX = "PROMPT_PREFIX"
    CONTEXT_REHYDRATION = "CONTEXT_REHYDRATION"
    ACTION_EXECUTION = "ACTION_EXECUTION"
    ENVIRONMENT_PREPARATION = "ENVIRONMENT_PREPARATION"
    AFFINITY_PLACEMENT = "AFFINITY_PLACEMENT"


class ServingAction(_ValueEnum):
    LOOKUP = "LOOKUP"
    RESTORE = "RESTORE"
    POPULATE = "POPULATE"


class LookupDisposition(_ValueEnum):
    HIT = "HIT"
    MISS = "MISS"
    BYPASS = "BYPASS"
    ERROR = "ERROR"


class CompositionPhase(_ValueEnum):
    REQUEST = "REQUEST"
    LOOKUP = "LOOKUP"
    RESTORE = "RESTORE"
    FALLBACK = "FALLBACK"
    POPULATE = "POPULATE"
    COMPLETE = "COMPLETE"


class CompositionStatus(_ValueEnum):
    SUCCESS = "SUCCESS"
    MISS = "MISS"
    BYPASS = "BYPASS"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class CausalRelation(_ValueEnum):
    REQUESTED = "REQUESTED"
    RESTORED_FROM = "RESTORED_FROM"
    CAUSED_FALLBACK = "CAUSED_FALLBACK"
    SUPPLIED_LAYER_WORK = "SUPPLIED_LAYER_WORK"
    POPULATED_AFTER = "POPULATED_AFTER"
    COMPLETED_BY = "COMPLETED_BY"


_WORK_BY_LAYER: Mapping[CompositionLayer, LayerWork] = MappingProxyType(
    {
        CompositionLayer.PROMPT: LayerWork.PROMPT_PREFIX,
        CompositionLayer.CONTEXT: LayerWork.CONTEXT_REHYDRATION,
        CompositionLayer.ACTION: LayerWork.ACTION_EXECUTION,
        CompositionLayer.ENVIRONMENT: LayerWork.ENVIRONMENT_PREPARATION,
        CompositionLayer.AFFINITY: LayerWork.AFFINITY_PLACEMENT,
    }
)

# Exact Action Cache is first so no lower-layer work occurs before a result that
# can legally replace execution.  The remaining order is deterministic only;
# none of those layers can short-circuit fallback.
_LAYER_ORDER: tuple[CompositionLayer, ...] = (
    CompositionLayer.ACTION,
    CompositionLayer.CONTEXT,
    CompositionLayer.ENVIRONMENT,
    CompositionLayer.AFFINITY,
    CompositionLayer.PROMPT,
)


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(
            f"{field_name} must be a bounded identifier",
            field=field_name,
        )
    return value


def _finite_non_negative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field_name} must be numeric", field=field_name)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContractViolation(
            f"{field_name} must be finite and non-negative",
            field=field_name,
        )
    return number


@dataclass(frozen=True)
class CompositionRuntimeBinding:
    """Principal and resource scope fixed by trusted server composition."""

    tenant_id: str
    project_id: str
    principal_digest: str

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.principal_digest)


@dataclass(frozen=True)
class CompositionRequest:
    """Content-free request contract; it contains no runtime registration."""

    request_id: str
    tenant_id: str
    project_id: str
    principal_digest: str
    authorization_digest: str
    compatibility_digest: str
    work_digest: str
    cache_deadline_monotonic: float

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request_id")
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.principal_digest)
        require_digest(self.authorization_digest)
        require_digest(self.compatibility_digest)
        require_digest(self.work_digest)
        object.__setattr__(
            self,
            "cache_deadline_monotonic",
            _finite_non_negative(
                self.cache_deadline_monotonic,
                "cache_deadline_monotonic",
            ),
        )

    @property
    def runtime_binding(self) -> CompositionRuntimeBinding:
        return CompositionRuntimeBinding(
            self.tenant_id,
            self.project_id,
            self.principal_digest,
        )

    @property
    def binding_digest(self) -> str:
        return digest_of(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "principal_digest": self.principal_digest,
                "authorization_digest": self.authorization_digest,
                "compatibility_digest": self.compatibility_digest,
                "work_digest": self.work_digest,
            }
        )


@dataclass(frozen=True)
class VerifiedServingGrant:
    """One exact action grant returned by a server-owned authorization boundary."""

    request_id: str
    tenant_id: str
    project_id: str
    principal_digest: str
    authorization_digest: str
    compatibility_digest: str
    layer: CompositionLayer
    action: ServingAction
    receipt_digest: str
    allowed: bool

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request_id")
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.principal_digest)
        require_digest(self.authorization_digest)
        require_digest(self.compatibility_digest)
        require_digest(self.receipt_digest)
        if not isinstance(self.layer, CompositionLayer):
            raise ContractViolation("serving grant uses an unknown layer")
        if not isinstance(self.action, ServingAction):
            raise ContractViolation("serving grant uses an unknown action")
        if not isinstance(self.allowed, bool):
            raise ContractViolation("serving grant allowed must be boolean")


class ServingAuthorizationBoundary(Protocol):
    """Trusted PAP/PDP boundary; request material never implements this protocol."""

    def authorize(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        action: ServingAction,
    ) -> VerifiedServingGrant: ...


def serving_boundary_statement(
    *,
    tenant_id: str,
    project_id: str,
    principal_digest: str,
    authorization_digest: str,
    compatibility_digest: str,
    actions: Mapping[CompositionLayer, Sequence[ServingAction]],
    issued_at: float,
    expires_at: float,
) -> dict[str, object]:
    """Build the canonical statement an independent serving authority signs."""

    tenant = _identifier(tenant_id, "tenant_id")
    project = _identifier(project_id, "project_id")
    require_digest(principal_digest)
    require_digest(authorization_digest)
    require_digest(compatibility_digest)
    issued = _finite_non_negative(issued_at, "issued_at")
    expires = _finite_non_negative(expires_at, "expires_at")
    if expires <= issued:
        raise ContractViolation("serving boundary expiry must follow issuance")
    normalized: dict[str, list[str]] = {}
    for layer, layer_actions in actions.items():
        if not isinstance(layer, CompositionLayer):
            raise ContractViolation("serving boundary contains an unknown layer")
        values = tuple(layer_actions)
        if not values or any(not isinstance(item, ServingAction) for item in values):
            raise ContractViolation("serving boundary actions must use the closed vocabulary")
        if len(values) != len(set(values)):
            raise ContractViolation("serving boundary contains duplicate actions")
        normalized[layer.value] = sorted(item.value for item in values)
    if not normalized:
        raise ContractViolation("serving boundary must authorize at least one action")
    return {
        "schema_version": "1.2.0",
        "decision": SERVING_BOUNDARY_DECISION,
        "tenant_id": tenant,
        "project_id": project,
        "principal_digest": principal_digest,
        "authorization_digest": authorization_digest,
        "compatibility_digest": compatibility_digest,
        "actions": dict(sorted(normalized.items())),
        "issued_at": issued,
        "expires_at": expires,
    }


class SignedServingBoundary:
    """Verify one immutable asymmetric receipt, then issue exact per-call grants."""

    def __init__(
        self,
        receipt: SignedStatement,
        verifier: ProvenanceSigner,
        *,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if receipt.kind != SERVING_BOUNDARY_KIND:
            raise ProvenanceInvalid("cache composition serving receipt has the wrong kind")
        self.verifier = require_asymmetric(verifier)
        self.verifier.verify_statement(receipt)
        self.receipt = receipt
        self.receipt_digest = digest_of(receipt.to_dict())
        self.wall_clock = wall_clock
        statement = dict(receipt.statement)
        expected = {
            "schema_version",
            "decision",
            "tenant_id",
            "project_id",
            "principal_digest",
            "authorization_digest",
            "compatibility_digest",
            "actions",
            "issued_at",
            "expires_at",
        }
        if set(statement) != expected:
            raise ProvenanceInvalid("cache composition serving receipt has an invalid shape")
        if statement.get("schema_version") != "1.2.0":
            raise ProvenanceInvalid("cache composition serving receipt schema is unsupported")
        if statement.get("decision") != SERVING_BOUNDARY_DECISION:
            raise ProvenanceInvalid("cache composition serving receipt decision is denied")
        self.tenant_id = _identifier(statement["tenant_id"], "tenant_id")
        self.project_id = _identifier(statement["project_id"], "project_id")
        self.principal_digest = require_digest(str(statement["principal_digest"]))
        self.authorization_digest = require_digest(str(statement["authorization_digest"]))
        self.compatibility_digest = require_digest(str(statement["compatibility_digest"]))
        self.issued_at = _finite_non_negative(statement["issued_at"], "issued_at")
        self.expires_at = _finite_non_negative(statement["expires_at"], "expires_at")
        if self.expires_at <= self.issued_at:
            raise ProvenanceInvalid("cache composition serving receipt has invalid time bounds")
        raw_actions = statement["actions"]
        if not isinstance(raw_actions, Mapping) or not raw_actions:
            raise ProvenanceInvalid("cache composition serving receipt has no actions")
        parsed: dict[CompositionLayer, frozenset[ServingAction]] = {}
        try:
            for raw_layer, raw_values in raw_actions.items():
                layer = CompositionLayer(str(raw_layer))
                if (
                    not isinstance(raw_values, list)
                    or not raw_values
                    or any(not isinstance(item, str) for item in raw_values)
                ):
                    raise ValueError("invalid action list")
                values = tuple(ServingAction(item) for item in raw_values)
                if len(values) != len(set(values)):
                    raise ValueError("duplicate action")
                parsed[layer] = frozenset(values)
        except (TypeError, ValueError) as exc:
            raise ProvenanceInvalid(
                "cache composition serving receipt contains unknown actions"
            ) from exc
        if len(parsed) != len(raw_actions):
            raise ProvenanceInvalid("cache composition serving receipt duplicates a layer")
        self.actions: Mapping[CompositionLayer, frozenset[ServingAction]] = MappingProxyType(
            parsed
        )

    def authorize(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        action: ServingAction,
    ) -> VerifiedServingGrant:
        now = _finite_non_negative(self.wall_clock(), "authorization_time")
        if now < self.issued_at or now >= self.expires_at:
            raise PermissionDenied("cache composition serving receipt is not currently valid")
        if (
            request.tenant_id != self.tenant_id
            or request.project_id != self.project_id
            or request.principal_digest != self.principal_digest
            or request.authorization_digest != self.authorization_digest
            or request.compatibility_digest != self.compatibility_digest
        ):
            raise PermissionDenied("cache composition serving scope is not authorized")
        return VerifiedServingGrant(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            principal_digest=request.principal_digest,
            authorization_digest=request.authorization_digest,
            compatibility_digest=request.compatibility_digest,
            layer=layer,
            action=action,
            receipt_digest=self.receipt_digest,
            allowed=action in self.actions.get(layer, frozenset()),
        )


@dataclass(frozen=True)
class LayerLookup:
    layer: CompositionLayer
    binding_digest: str
    disposition: LookupDisposition
    reason_code: str
    material_digest: str | None = None
    verified: bool = False
    compatible: bool = False
    exact_action_result: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.layer, CompositionLayer):
            raise ContractViolation("lookup uses an unknown layer")
        require_digest(self.binding_digest)
        if not isinstance(self.disposition, LookupDisposition):
            raise ContractViolation("lookup uses an unknown disposition")
        _identifier(self.reason_code, "reason_code")
        for name in ("verified", "compatible", "exact_action_result"):
            if not isinstance(getattr(self, name), bool):
                raise ContractViolation(f"{name} must be boolean", field=name)
        if self.disposition is LookupDisposition.HIT:
            if self.material_digest is None:
                raise ContractViolation("cache hit must identify immutable material")
            require_digest(self.material_digest)
            if self.layer is CompositionLayer.ACTION and not self.exact_action_result:
                raise ContractViolation("Action Cache hits must be exact results")
            if self.layer is not CompositionLayer.ACTION and self.exact_action_result:
                raise ContractViolation("only Action Cache may return an exact result")
        elif self.material_digest is not None or self.exact_action_result:
            raise ContractViolation("non-hit lookup cannot return reusable material")


@dataclass(frozen=True)
class LayerRestore:
    layer: CompositionLayer
    binding_digest: str
    material_digest: str
    work: LayerWork
    success: bool
    reason_code: str
    receipt_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.layer, CompositionLayer):
            raise ContractViolation("restore uses an unknown layer")
        require_digest(self.binding_digest)
        require_digest(self.material_digest)
        if not isinstance(self.work, LayerWork) or self.work is not _WORK_BY_LAYER[self.layer]:
            raise ContractViolation("restore may save only its corresponding layer work")
        if not isinstance(self.success, bool):
            raise ContractViolation("restore success must be boolean")
        _identifier(self.reason_code, "reason_code")
        if self.success:
            if self.receipt_digest is None:
                raise ContractViolation("successful restore requires an immutable receipt")
            require_digest(self.receipt_digest)
        elif self.receipt_digest is not None:
            raise ContractViolation("failed restore cannot return a success receipt")


@dataclass(frozen=True)
class FallbackExecutionResult:
    success: bool
    reason_code: str
    performed_work: tuple[LayerWork, ...]
    execution_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise ContractViolation("fallback success must be boolean")
        _identifier(self.reason_code, "reason_code")
        work = tuple(self.performed_work)
        if any(not isinstance(item, LayerWork) for item in work):
            raise ContractViolation("fallback performed_work uses an unknown value")
        if len(work) != len(set(work)):
            raise ContractViolation("fallback performed_work contains duplicates")
        object.__setattr__(self, "performed_work", work)
        if self.success:
            if self.execution_digest is None:
                raise ContractViolation("successful fallback requires an execution digest")
            require_digest(self.execution_digest)
        elif self.execution_digest is not None:
            require_digest(self.execution_digest)


@dataclass(frozen=True)
class LayerPopulation:
    layer: CompositionLayer
    binding_digest: str
    work: LayerWork
    success: bool
    reason_code: str
    artifact_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.layer, CompositionLayer):
            raise ContractViolation("population uses an unknown layer")
        require_digest(self.binding_digest)
        if not isinstance(self.work, LayerWork) or self.work is not _WORK_BY_LAYER[self.layer]:
            raise ContractViolation("population may write only its corresponding layer work")
        if not isinstance(self.success, bool):
            raise ContractViolation("population success must be boolean")
        _identifier(self.reason_code, "reason_code")
        if self.success:
            if self.artifact_digest is None:
                raise ContractViolation("successful population requires an artifact digest")
            require_digest(self.artifact_digest)
        elif self.artifact_digest is not None:
            raise ContractViolation("failed population cannot return an artifact digest")


class CacheLayerPort(Protocol):
    """Server-owned typed port.  Implementations retain all raw cache payloads."""

    @property
    def layer(self) -> CompositionLayer: ...

    def lookup(
        self,
        request: CompositionRequest,
        deadline_monotonic: float,
    ) -> LayerLookup: ...

    def restore(
        self,
        request: CompositionRequest,
        lookup: LayerLookup,
        deadline_monotonic: float,
    ) -> LayerRestore: ...

    def populate(
        self,
        request: CompositionRequest,
        execution: FallbackExecutionResult,
        deadline_monotonic: float,
    ) -> LayerPopulation: ...


class FallbackExecutor(Protocol):
    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult: ...


@dataclass(frozen=True)
class CompositionOutcomeEvent:
    event_id: str
    request_id: str
    binding_digest: str
    phase: CompositionPhase
    status: CompositionStatus
    reason_code: str
    layer: CompositionLayer | None = None
    material_digest: str | None = None
    receipt_digest: str | None = None

    def __post_init__(self) -> None:
        require_digest(self.event_id)
        _identifier(self.request_id, "request_id")
        require_digest(self.binding_digest)
        if not isinstance(self.phase, CompositionPhase):
            raise ContractViolation("outcome event uses an unknown phase")
        if not isinstance(self.status, CompositionStatus):
            raise ContractViolation("outcome event uses an unknown status")
        _identifier(self.reason_code, "reason_code")
        if self.layer is not None and not isinstance(self.layer, CompositionLayer):
            raise ContractViolation("outcome event uses an unknown layer")
        if self.material_digest is not None:
            require_digest(self.material_digest)
        if self.receipt_digest is not None:
            require_digest(self.receipt_digest)

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "binding_digest": self.binding_digest,
            "phase": self.phase.value,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "layer": None if self.layer is None else self.layer.value,
            "material_digest": self.material_digest,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True)
class MissCausalEdge:
    source_event_id: str
    target_event_id: str
    relation: CausalRelation

    def __post_init__(self) -> None:
        require_digest(self.source_event_id)
        require_digest(self.target_event_id)
        if not isinstance(self.relation, CausalRelation):
            raise ContractViolation("causal edge uses an unknown relation")

    def to_dict(self) -> dict[str, str]:
        return {
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "relation": self.relation.value,
        }


class CompositionOutcomeSink(Protocol):
    def persist(
        self,
        request: CompositionRequest,
        events: tuple[CompositionOutcomeEvent, ...],
        edges: tuple[MissCausalEdge, ...],
    ) -> None: ...


class SloRollbackLatch(Protocol):
    def latch_rollback(self, reason_code: str) -> None: ...


@dataclass(frozen=True)
class CompositionResult:
    request_id: str
    binding_digest: str
    exact_action_reused: bool
    fallback_executed: bool
    fallback_result: FallbackExecutionResult | None
    restored: tuple[LayerRestore, ...]
    populations: tuple[LayerPopulation, ...]
    events: tuple[CompositionOutcomeEvent, ...]
    causal_edges: tuple[MissCausalEdge, ...]
    outcome_persisted: bool

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request_id")
        require_digest(self.binding_digest)
        if self.exact_action_reused == self.fallback_executed:
            raise ContractViolation(
                "exact Action reuse and fallback execution must be mutually exclusive"
            )
        if self.fallback_executed != (self.fallback_result is not None):
            raise ContractViolation("fallback result does not match execution state")
        if not isinstance(self.outcome_persisted, bool):
            raise ContractViolation("outcome_persisted must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.2.0",
            "request_id": self.request_id,
            "binding_digest": self.binding_digest,
            "exact_action_reused": self.exact_action_reused,
            "fallback_executed": self.fallback_executed,
            "fallback_success": (
                None if self.fallback_result is None else self.fallback_result.success
            ),
            "restored_layers": [item.layer.value for item in self.restored],
            "populated_layers": [item.layer.value for item in self.populations],
            "events": [item.to_dict() for item in self.events],
            "causal_edges": [item.to_dict() for item in self.causal_edges],
            "outcome_persisted": self.outcome_persisted,
            "certification": "NOT_CERTIFIED",
        }


class _Recorder:
    def __init__(self, request: CompositionRequest) -> None:
        self.request = request
        self.events: list[CompositionOutcomeEvent] = []
        self.edges: list[MissCausalEdge] = []

    def add(
        self,
        *,
        phase: CompositionPhase,
        status: CompositionStatus,
        reason_code: str,
        layer: CompositionLayer | None = None,
        material_digest: str | None = None,
        receipt_digest: str | None = None,
        parents: Sequence[tuple[str, CausalRelation]] = (),
    ) -> CompositionOutcomeEvent:
        ordinal = len(self.events)
        event_id = digest_of(
            {
                "request_id": self.request.request_id,
                "binding_digest": self.request.binding_digest,
                "ordinal": ordinal,
                "phase": phase.value,
                "status": status.value,
                "reason_code": reason_code,
                "layer": None if layer is None else layer.value,
                "material_digest": material_digest,
                "receipt_digest": receipt_digest,
            }
        )
        event = CompositionOutcomeEvent(
            event_id=event_id,
            request_id=self.request.request_id,
            binding_digest=self.request.binding_digest,
            phase=phase,
            status=status,
            reason_code=reason_code,
            layer=layer,
            material_digest=material_digest,
            receipt_digest=receipt_digest,
        )
        self.events.append(event)
        self.edges.extend(
            MissCausalEdge(parent, event.event_id, relation)
            for parent, relation in parents
        )
        return event


class FiveLayerCacheComposition:
    """Fail-closed five-layer orchestration with one correctness slow path."""

    def __init__(
        self,
        *,
        binding: CompositionRuntimeBinding,
        serving_boundary: ServingAuthorizationBoundary,
        prompt_port: CacheLayerPort,
        context_port: CacheLayerPort,
        action_port: CacheLayerPort,
        environment_port: CacheLayerPort,
        affinity_port: CacheLayerPort,
        fallback_executor: FallbackExecutor,
        outcome_sink: CompositionOutcomeSink,
        rollback_latch: SloRollbackLatch,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(binding, CompositionRuntimeBinding):
            raise ContractViolation("composition binding has an invalid type")
        self.binding = binding
        self.serving_boundary = serving_boundary
        self.fallback_executor = fallback_executor
        self.outcome_sink = outcome_sink
        self.rollback_latch = rollback_latch
        self.monotonic = monotonic
        ports = {
            CompositionLayer.PROMPT: prompt_port,
            CompositionLayer.CONTEXT: context_port,
            CompositionLayer.ACTION: action_port,
            CompositionLayer.ENVIRONMENT: environment_port,
            CompositionLayer.AFFINITY: affinity_port,
        }
        for expected, port in ports.items():
            try:
                actual = port.layer
            except Exception as exc:
                raise ContractViolation(
                    "cache composition port does not expose a closed layer",
                    layer=expected.value,
                ) from exc
            if actual is not expected:
                raise ContractViolation(
                    "cache composition port is wired to the wrong layer",
                    expected=expected.value,
                    actual=str(actual),
                )
        self.ports: Mapping[CompositionLayer, CacheLayerPort] = MappingProxyType(ports)

    def execute(self, request: CompositionRequest) -> CompositionResult:
        if not isinstance(request, CompositionRequest):
            raise ContractViolation("composition requires the closed request type")
        if request.runtime_binding != self.binding:
            raise PermissionDenied("cache composition scope is not accessible")

        recorder = _Recorder(request)
        root = recorder.add(
            phase=CompositionPhase.REQUEST,
            status=CompositionStatus.SUCCESS,
            reason_code="BOUND_SCOPE_ACCEPTED",
        )
        restored: list[LayerRestore] = []
        restored_events: list[str] = []
        fallback_causes: list[str] = []
        exact_action = False

        for layer in _LAYER_ORDER:
            lookup_event, lookup = self._lookup(
                request,
                layer,
                recorder,
                root.event_id,
            )
            if lookup is None:
                fallback_causes.append(lookup_event.event_id)
                continue
            restore_event, restore = self._restore(
                request,
                lookup,
                recorder,
                lookup_event.event_id,
            )
            if restore is None:
                fallback_causes.append(restore_event.event_id)
                continue
            restored.append(restore)
            restored_events.append(restore_event.event_id)
            if layer is CompositionLayer.ACTION:
                exact_action = True
                break

        if exact_action:
            completion = recorder.add(
                phase=CompositionPhase.COMPLETE,
                status=CompositionStatus.SKIPPED,
                reason_code="EXACT_ACTION_REUSED",
                layer=CompositionLayer.ACTION,
                material_digest=restored[-1].material_digest,
                receipt_digest=restored[-1].receipt_digest,
                parents=((restored_events[-1], CausalRelation.COMPLETED_BY),),
            )
            del completion
            persisted = self._persist(request, recorder)
            return CompositionResult(
                request_id=request.request_id,
                binding_digest=request.binding_digest,
                exact_action_reused=True,
                fallback_executed=False,
                fallback_result=None,
                restored=tuple(restored),
                populations=(),
                events=tuple(recorder.events),
                causal_edges=tuple(recorder.edges),
                outcome_persisted=persisted,
            )

        fallback = self._execute_fallback(
            request,
            tuple(restored),
            recorder,
            root.event_id,
            tuple(fallback_causes),
            tuple(restored_events),
        )
        fallback_event = recorder.events[-1]
        populations: list[LayerPopulation] = []
        if fallback.success:
            for layer in _LAYER_ORDER:
                if _WORK_BY_LAYER[layer] not in fallback.performed_work:
                    continue
                population = self._populate(
                    request,
                    layer,
                    fallback,
                    recorder,
                    fallback_event.event_id,
                )
                if population is not None:
                    populations.append(population)
        persisted = self._persist(request, recorder)
        return CompositionResult(
            request_id=request.request_id,
            binding_digest=request.binding_digest,
            exact_action_reused=False,
            fallback_executed=True,
            fallback_result=fallback,
            restored=tuple(restored),
            populations=tuple(populations),
            events=tuple(recorder.events),
            causal_edges=tuple(recorder.edges),
            outcome_persisted=persisted,
        )

    def _lookup(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        recorder: _Recorder,
        root_event_id: str,
    ) -> tuple[CompositionOutcomeEvent, LayerLookup | None]:
        authorized, authorization_reason = self._authorized(
            request,
            layer,
            ServingAction.LOOKUP,
        )
        if not authorized:
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.BYPASS,
                    reason_code=authorization_reason,
                    layer=layer,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        if self._deadline_exceeded(request):
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.BYPASS,
                    reason_code="CACHE_DEADLINE_EXCEEDED",
                    layer=layer,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        try:
            candidate = self.ports[layer].lookup(
                request,
                request.cache_deadline_monotonic,
            )
        except Exception:
            self._latch("CACHE_LOOKUP_RUNTIME_FAILED")
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.ERROR,
                    reason_code="LOOKUP_RUNTIME_FAILED",
                    layer=layer,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        if self._deadline_exceeded(request):
            self._latch("CACHE_LOOKUP_DEADLINE_EXCEEDED")
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.BYPASS,
                    reason_code="LOOKUP_DEADLINE_EXCEEDED",
                    layer=layer,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        if (
            not isinstance(candidate, LayerLookup)
            or candidate.layer is not layer
            or candidate.binding_digest != request.binding_digest
        ):
            self._latch("CACHE_LOOKUP_SCOPE_DRIFT")
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.ERROR,
                    reason_code="LOOKUP_SCOPE_DRIFT",
                    layer=layer,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        if candidate.disposition is not LookupDisposition.HIT:
            status = {
                LookupDisposition.MISS: CompositionStatus.MISS,
                LookupDisposition.BYPASS: CompositionStatus.BYPASS,
                LookupDisposition.ERROR: CompositionStatus.ERROR,
            }[candidate.disposition]
            if status is CompositionStatus.ERROR:
                self._latch("CACHE_LOOKUP_REPORTED_ERROR")
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=status,
                    reason_code=candidate.reason_code,
                    layer=layer,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        if not candidate.verified:
            self._latch("CACHE_LOOKUP_UNVERIFIED_MATERIAL")
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.ERROR,
                    reason_code="UNVERIFIED_MATERIAL",
                    layer=layer,
                    material_digest=candidate.material_digest,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        if not candidate.compatible:
            return (
                recorder.add(
                    phase=CompositionPhase.LOOKUP,
                    status=CompositionStatus.MISS,
                    reason_code="COMPATIBILITY_MISMATCH",
                    layer=layer,
                    material_digest=candidate.material_digest,
                    parents=((root_event_id, CausalRelation.REQUESTED),),
                ),
                None,
            )
        return (
            recorder.add(
                phase=CompositionPhase.LOOKUP,
                status=CompositionStatus.SUCCESS,
                reason_code=candidate.reason_code,
                layer=layer,
                material_digest=candidate.material_digest,
                parents=((root_event_id, CausalRelation.REQUESTED),),
            ),
            candidate,
        )

    def _restore(
        self,
        request: CompositionRequest,
        lookup: LayerLookup,
        recorder: _Recorder,
        lookup_event_id: str,
    ) -> tuple[CompositionOutcomeEvent, LayerRestore | None]:
        layer = lookup.layer
        authorized, authorization_reason = self._authorized(
            request,
            layer,
            ServingAction.RESTORE,
        )
        if not authorized:
            return (
                recorder.add(
                    phase=CompositionPhase.RESTORE,
                    status=CompositionStatus.BYPASS,
                    reason_code=authorization_reason,
                    layer=layer,
                    material_digest=lookup.material_digest,
                    parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
                ),
                None,
            )
        if self._deadline_exceeded(request):
            return (
                recorder.add(
                    phase=CompositionPhase.RESTORE,
                    status=CompositionStatus.BYPASS,
                    reason_code="CACHE_DEADLINE_EXCEEDED",
                    layer=layer,
                    material_digest=lookup.material_digest,
                    parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
                ),
                None,
            )
        try:
            restored = self.ports[layer].restore(
                request,
                lookup,
                request.cache_deadline_monotonic,
            )
        except Exception:
            self._latch("CACHE_RESTORE_RUNTIME_FAILED")
            return (
                recorder.add(
                    phase=CompositionPhase.RESTORE,
                    status=CompositionStatus.ERROR,
                    reason_code="RESTORE_RUNTIME_FAILED",
                    layer=layer,
                    material_digest=lookup.material_digest,
                    parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
                ),
                None,
            )
        if self._deadline_exceeded(request):
            self._latch("CACHE_RESTORE_DEADLINE_EXCEEDED")
            return (
                recorder.add(
                    phase=CompositionPhase.RESTORE,
                    status=CompositionStatus.ERROR,
                    reason_code="RESTORE_DEADLINE_EXCEEDED",
                    layer=layer,
                    material_digest=lookup.material_digest,
                    parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
                ),
                None,
            )
        if (
            not isinstance(restored, LayerRestore)
            or restored.layer is not layer
            or restored.binding_digest != request.binding_digest
            or restored.material_digest != lookup.material_digest
            or restored.work is not _WORK_BY_LAYER[layer]
        ):
            self._latch("CACHE_RESTORE_SCOPE_DRIFT")
            return (
                recorder.add(
                    phase=CompositionPhase.RESTORE,
                    status=CompositionStatus.ERROR,
                    reason_code="RESTORE_SCOPE_DRIFT",
                    layer=layer,
                    material_digest=lookup.material_digest,
                    parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
                ),
                None,
            )
        if not restored.success:
            self._latch("CACHE_RESTORE_FAILED")
            return (
                recorder.add(
                    phase=CompositionPhase.RESTORE,
                    status=CompositionStatus.ERROR,
                    reason_code=restored.reason_code,
                    layer=layer,
                    material_digest=lookup.material_digest,
                    parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
                ),
                None,
            )
        return (
            recorder.add(
                phase=CompositionPhase.RESTORE,
                status=CompositionStatus.SUCCESS,
                reason_code=restored.reason_code,
                layer=layer,
                material_digest=lookup.material_digest,
                receipt_digest=restored.receipt_digest,
                parents=((lookup_event_id, CausalRelation.RESTORED_FROM),),
            ),
            restored,
        )

    def _execute_fallback(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        recorder: _Recorder,
        root_event_id: str,
        fallback_causes: tuple[str, ...],
        restored_events: tuple[str, ...],
    ) -> FallbackExecutionResult:
        parents: list[tuple[str, CausalRelation]] = [
            (root_event_id, CausalRelation.REQUESTED)
        ]
        parents.extend(
            (event_id, CausalRelation.CAUSED_FALLBACK)
            for event_id in fallback_causes
        )
        parents.extend(
            (event_id, CausalRelation.SUPPLIED_LAYER_WORK)
            for event_id in restored_events
        )
        try:
            result = self.fallback_executor.execute(
                request,
                restored,
                request.cache_deadline_monotonic,
            )
        except Exception:
            self._latch("FALLBACK_EXECUTION_RUNTIME_FAILED")
            recorder.add(
                phase=CompositionPhase.FALLBACK,
                status=CompositionStatus.ERROR,
                reason_code="FALLBACK_EXECUTION_RUNTIME_FAILED",
                parents=parents,
            )
            self._persist(request, recorder)
            raise
        if not isinstance(result, FallbackExecutionResult):
            self._latch("FALLBACK_EXECUTION_CONTRACT_INVALID")
            recorder.add(
                phase=CompositionPhase.FALLBACK,
                status=CompositionStatus.ERROR,
                reason_code="FALLBACK_EXECUTION_CONTRACT_INVALID",
                parents=parents,
            )
            self._persist(request, recorder)
            raise ContractViolation("fallback executor returned an unknown result type")
        restored_work = {item.work for item in restored}
        if len(restored_work) != len(restored):
            self._latch("RESTORED_WORK_PARTITION_INVALID")
            raise ContractViolation("restored layer work overlaps")
        if result.success:
            expected = set(LayerWork) - restored_work
            if set(result.performed_work) != expected:
                self._latch("FALLBACK_WORK_PARTITION_INVALID")
                recorder.add(
                    phase=CompositionPhase.FALLBACK,
                    status=CompositionStatus.ERROR,
                    reason_code="FALLBACK_WORK_PARTITION_INVALID",
                    parents=parents,
                )
                self._persist(request, recorder)
                raise ContractViolation(
                    "fallback must execute every layer work item not restored",
                    expected=sorted(item.value for item in expected),
                    found=sorted(item.value for item in result.performed_work),
                )
        recorder.add(
            phase=CompositionPhase.FALLBACK,
            status=(
                CompositionStatus.SUCCESS if result.success else CompositionStatus.ERROR
            ),
            reason_code=result.reason_code,
            receipt_digest=result.execution_digest,
            parents=parents,
        )
        if not result.success:
            self._latch("FALLBACK_EXECUTION_FAILED")
        return result

    def _populate(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        execution: FallbackExecutionResult,
        recorder: _Recorder,
        fallback_event_id: str,
    ) -> LayerPopulation | None:
        authorized, authorization_reason = self._authorized(
            request,
            layer,
            ServingAction.POPULATE,
        )
        if not authorized:
            recorder.add(
                phase=CompositionPhase.POPULATE,
                status=CompositionStatus.BYPASS,
                reason_code=authorization_reason,
                layer=layer,
                parents=((fallback_event_id, CausalRelation.POPULATED_AFTER),),
            )
            return None
        if self._deadline_exceeded(request):
            recorder.add(
                phase=CompositionPhase.POPULATE,
                status=CompositionStatus.BYPASS,
                reason_code="CACHE_DEADLINE_EXCEEDED",
                layer=layer,
                parents=((fallback_event_id, CausalRelation.POPULATED_AFTER),),
            )
            return None
        try:
            population = self.ports[layer].populate(
                request,
                execution,
                request.cache_deadline_monotonic,
            )
        except Exception:
            self._latch("CACHE_POPULATE_RUNTIME_FAILED")
            recorder.add(
                phase=CompositionPhase.POPULATE,
                status=CompositionStatus.ERROR,
                reason_code="POPULATE_RUNTIME_FAILED",
                layer=layer,
                parents=((fallback_event_id, CausalRelation.POPULATED_AFTER),),
            )
            return None
        if self._deadline_exceeded(request):
            self._latch("CACHE_POPULATE_DEADLINE_EXCEEDED")
            recorder.add(
                phase=CompositionPhase.POPULATE,
                status=CompositionStatus.ERROR,
                reason_code="POPULATE_DEADLINE_EXCEEDED",
                layer=layer,
                parents=((fallback_event_id, CausalRelation.POPULATED_AFTER),),
            )
            return None
        if (
            not isinstance(population, LayerPopulation)
            or population.layer is not layer
            or population.binding_digest != request.binding_digest
            or population.work is not _WORK_BY_LAYER[layer]
        ):
            self._latch("CACHE_POPULATE_SCOPE_DRIFT")
            recorder.add(
                phase=CompositionPhase.POPULATE,
                status=CompositionStatus.ERROR,
                reason_code="POPULATE_SCOPE_DRIFT",
                layer=layer,
                parents=((fallback_event_id, CausalRelation.POPULATED_AFTER),),
            )
            return None
        recorder.add(
            phase=CompositionPhase.POPULATE,
            status=(
                CompositionStatus.SUCCESS
                if population.success
                else CompositionStatus.ERROR
            ),
            reason_code=population.reason_code,
            layer=layer,
            material_digest=population.artifact_digest,
            parents=((fallback_event_id, CausalRelation.POPULATED_AFTER),),
        )
        if not population.success:
            self._latch("CACHE_POPULATE_FAILED")
            return None
        return population

    def _authorized(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        action: ServingAction,
    ) -> tuple[bool, str]:
        try:
            grant = self.serving_boundary.authorize(request, layer, action)
        except Exception:
            self._latch("SERVING_AUTHORIZATION_FAILED")
            return False, "SERVING_AUTHORIZATION_FAILED"
        if not isinstance(grant, VerifiedServingGrant):
            self._latch("SERVING_AUTHORIZATION_INVALID")
            return False, "SERVING_AUTHORIZATION_INVALID"
        if (
            grant.request_id != request.request_id
            or grant.tenant_id != request.tenant_id
            or grant.project_id != request.project_id
            or grant.principal_digest != request.principal_digest
            or grant.authorization_digest != request.authorization_digest
            or grant.compatibility_digest != request.compatibility_digest
            or grant.layer is not layer
            or grant.action is not action
        ):
            self._latch("SERVING_AUTHORIZATION_SCOPE_DRIFT")
            return False, "SERVING_AUTHORIZATION_SCOPE_DRIFT"
        if not grant.allowed:
            return False, "SERVING_ACTION_DENIED"
        return True, "SERVING_ACTION_AUTHORIZED"

    def _deadline_exceeded(self, request: CompositionRequest) -> bool:
        try:
            now = _finite_non_negative(self.monotonic(), "monotonic_time")
        except ContractViolation:
            self._latch("MONOTONIC_CLOCK_INVALID")
            return True
        return now >= request.cache_deadline_monotonic

    def _persist(self, request: CompositionRequest, recorder: _Recorder) -> bool:
        try:
            self.outcome_sink.persist(
                request,
                tuple(recorder.events),
                tuple(recorder.edges),
            )
        except Exception:
            self._latch("CACHE_OUTCOME_PERSISTENCE_FAILED")
            return False
        return True

    def _latch(self, reason_code: str) -> None:
        self.rollback_latch.latch_rollback(_identifier(reason_code, "rollback_reason"))


__all__ = [
    "CacheLayerPort",
    "CausalRelation",
    "CompositionLayer",
    "CompositionOutcomeEvent",
    "CompositionOutcomeSink",
    "CompositionPhase",
    "CompositionRequest",
    "CompositionResult",
    "CompositionRuntimeBinding",
    "CompositionStatus",
    "FallbackExecutionResult",
    "FallbackExecutor",
    "FiveLayerCacheComposition",
    "LayerLookup",
    "LayerPopulation",
    "LayerRestore",
    "LayerWork",
    "LookupDisposition",
    "MissCausalEdge",
    "SERVING_BOUNDARY_DECISION",
    "SERVING_BOUNDARY_KIND",
    "ServingAction",
    "ServingAuthorizationBoundary",
    "SignedServingBoundary",
    "SloRollbackLatch",
    "VerifiedServingGrant",
    "serving_boundary_statement",
]
