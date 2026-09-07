"""Bind the five-layer cache-parity composition to concrete engine services.

``parity_composition`` is a pure seam: it owns the correctness argument and
knows nothing about SQLite, HTTP or any cache subsystem.  This module is the
other half — the trusted, server-owned adapters that let a real control plane
drive that seam.  It lives beside the seam rather than inside ``api.py`` so the
HTTP layer keeps depending only on routing, idempotency and error mapping, and
so a non-HTTP driver (CLI, coordinator) can reuse the same adapters.

Two invariants are enforced here rather than left to callers:

* every ``LayerLookup`` / ``LayerRestore`` / ``LayerPopulation`` this module
  produces is stamped with ``request.binding_digest``, so a port that drifts out
  of the request scope is refused by the composition instead of served;
* a layer with no probe wired for the current request is *out of scope* and
  answers ``BYPASS``.  A bypassing layer can never be restored, and only a
  restored exact Action result may skip execution, so an unwired layer can never
  widen what the API is allowed to skip;
* the Action layer's port is always built here from the request's own probe.
  ``ServingCompositionWiring`` refuses a ``layer_ports`` override for it, so the
  one lookup that may skip execution can never be unbound from the real Action
  Cache by deployment configuration.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .action_cache import ActionCache, LookupRequest, LookupResult
from .canonical import digest_of, require_digest
from .enums import CacheMode, TrustNamespace, ValidationLevel
from .errors import ContractViolation
from .miss_diagnostics import CacheOutcome, CacheOutcomeReason
from .parity_composition import (
    CacheLayerPort,
    CompositionLayer,
    CompositionOutcomeEvent,
    CompositionOutcomeSink,
    CompositionPhase,
    CompositionRequest,
    CompositionResult,
    CompositionRuntimeBinding,
    CompositionStatus,
    FallbackExecutionResult,
    FallbackExecutor,
    FiveLayerCacheComposition,
    LayerLookup,
    LayerPopulation,
    LayerRestore,
    LayerWork,
    LookupDisposition,
    MissCausalEdge,
    SignedServingBoundary,
    SloRollbackLatch,
)

OUTCOME_EVENT_SCHEMA_VERSION = "1.2.0"

# Layer values accepted by ``cache-outcome-event.schema.json``.  The composition
# also has an AFFINITY layer, which the external outcome vocabulary models as a
# coordinator-level placement decision.
_EXTERNAL_OUTCOME_LAYER: Mapping[CompositionLayer, str] = {
    CompositionLayer.PROMPT: "PROMPT",
    CompositionLayer.CONTEXT: "CONTEXT",
    CompositionLayer.ACTION: "ACTION",
    CompositionLayer.ENVIRONMENT: "ENVIRONMENT",
    CompositionLayer.AFFINITY: "COORDINATOR",
}

_HIT_REASON: Mapping[CompositionLayer, CacheOutcomeReason] = {
    CompositionLayer.PROMPT: CacheOutcomeReason.PROMPT_PREFIX_REUSED,
    CompositionLayer.CONTEXT: CacheOutcomeReason.ARTIFACT_RESTORED,
    CompositionLayer.ACTION: CacheOutcomeReason.EXACT_RESULT_REUSED,
    CompositionLayer.ENVIRONMENT: CacheOutcomeReason.ARTIFACT_RESTORED,
    CompositionLayer.AFFINITY: CacheOutcomeReason.ARTIFACT_RESTORED,
}


class CompositionOutcomeWriter(Protocol):
    """The persistent writer behind ``GET /cache/explain/{requestId}``."""

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def put_cache_causal_graph(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        events: tuple[Mapping[str, Any], ...],
        edges: tuple[Mapping[str, Any], ...],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class LayerProbe:
    """What a layer knows about the current request, before any restore."""

    disposition: LookupDisposition
    reason_code: str
    material_digest: str | None = None
    verified: bool = False
    compatible: bool = False

    @classmethod
    def hit(cls, material_digest: str, *, reason_code: str) -> LayerProbe:
        return cls(
            LookupDisposition.HIT,
            reason_code,
            require_digest(material_digest),
            verified=True,
            compatible=True,
        )

    @classmethod
    def miss(cls, reason_code: str) -> LayerProbe:
        return cls(LookupDisposition.MISS, reason_code)

    @classmethod
    def bypass(cls, reason_code: str) -> LayerProbe:
        return cls(LookupDisposition.BYPASS, reason_code)

    @classmethod
    def error(cls, reason_code: str) -> LayerProbe:
        return cls(LookupDisposition.ERROR, reason_code)


LayerProbeFn = Callable[[CompositionRequest], LayerProbe]
LayerWriterFn = Callable[[CompositionRequest, FallbackExecutionResult], str | None]

_WORK_FOR: Mapping[CompositionLayer, LayerWork] = {
    CompositionLayer.PROMPT: LayerWork.PROMPT_PREFIX,
    CompositionLayer.CONTEXT: LayerWork.CONTEXT_REHYDRATION,
    CompositionLayer.ACTION: LayerWork.ACTION_EXECUTION,
    CompositionLayer.ENVIRONMENT: LayerWork.ENVIRONMENT_PREPARATION,
    CompositionLayer.AFFINITY: LayerWork.AFFINITY_PLACEMENT,
}


class ScopedCacheLayerPort:
    """A ``CacheLayerPort`` over one read-only probe and one optional writer.

    The control plane confirms availability of immutable material; it never
    materialises it into a workspace.  ``restore`` therefore has no side effect:
    it hands back the verified material digest plus a receipt that binds the
    request scope, which is exactly the "this layer supplied its piece of work"
    claim the composition needs.
    """

    def __init__(
        self,
        layer: CompositionLayer,
        *,
        probe: LayerProbeFn | None = None,
        writer: LayerWriterFn | None = None,
    ) -> None:
        if not isinstance(layer, CompositionLayer):
            raise ContractViolation("cache layer port requires a closed layer")
        self._layer = layer
        self._probe = probe
        self._writer = writer

    @property
    def layer(self) -> CompositionLayer:
        return self._layer

    def lookup(
        self,
        request: CompositionRequest,
        deadline_monotonic: float,
    ) -> LayerLookup:
        del deadline_monotonic
        if self._probe is None:
            return self._bypass(request, "LAYER_OUT_OF_REQUEST_SCOPE")
        probe = self._probe(request)
        if not isinstance(probe, LayerProbe):
            return self._bypass(request, "LAYER_PROBE_CONTRACT_INVALID")
        if probe.disposition is not LookupDisposition.HIT:
            return LayerLookup(
                layer=self._layer,
                binding_digest=request.binding_digest,
                disposition=probe.disposition,
                reason_code=probe.reason_code,
            )
        if probe.material_digest is None:
            return self._bypass(request, "LAYER_PROBE_CONTRACT_INVALID")
        return LayerLookup(
            layer=self._layer,
            binding_digest=request.binding_digest,
            disposition=LookupDisposition.HIT,
            reason_code=probe.reason_code,
            material_digest=probe.material_digest,
            verified=probe.verified,
            compatible=probe.compatible,
            exact_action_result=self._layer is CompositionLayer.ACTION,
        )

    def restore(
        self,
        request: CompositionRequest,
        lookup: LayerLookup,
        deadline_monotonic: float,
    ) -> LayerRestore:
        del deadline_monotonic
        material = require_digest(str(lookup.material_digest))
        receipt = digest_of(
            {
                "layer": self._layer.value,
                "binding_digest": request.binding_digest,
                "material_digest": material,
                "request_id": request.request_id,
            }
        )
        return LayerRestore(
            layer=self._layer,
            binding_digest=request.binding_digest,
            material_digest=material,
            work=_WORK_FOR[self._layer],
            success=True,
            reason_code="LAYER_MATERIAL_CONFIRMED",
            receipt_digest=receipt,
        )

    def populate(
        self,
        request: CompositionRequest,
        execution: FallbackExecutionResult,
        deadline_monotonic: float,
    ) -> LayerPopulation:
        del deadline_monotonic
        if self._writer is None:
            # A boundary that grants POPULATE for a layer with no writer is a
            # deployment claiming write authority the runtime cannot honour;
            # report failure so the composition latches instead of pretending.
            return LayerPopulation(
                layer=self._layer,
                binding_digest=request.binding_digest,
                work=_WORK_FOR[self._layer],
                success=False,
                reason_code="LAYER_POPULATION_NOT_WIRED",
            )
        artifact = self._writer(request, execution)
        if artifact is None:
            return LayerPopulation(
                layer=self._layer,
                binding_digest=request.binding_digest,
                work=_WORK_FOR[self._layer],
                success=False,
                reason_code="LAYER_POPULATION_DECLINED",
            )
        return LayerPopulation(
            layer=self._layer,
            binding_digest=request.binding_digest,
            work=_WORK_FOR[self._layer],
            success=True,
            reason_code="LAYER_POPULATED",
            artifact_digest=require_digest(artifact),
        )

    def _bypass(self, request: CompositionRequest, reason_code: str) -> LayerLookup:
        return LayerLookup(
            layer=self._layer,
            binding_digest=request.binding_digest,
            disposition=LookupDisposition.BYPASS,
            reason_code=reason_code,
        )


class ActionCacheLayerProbe:
    """The real Action Cache lookup, exposed as a composition layer probe.

    The lookup runs at most once per request; the call site reads
    :attr:`result` afterwards so the HTTP response body is built from the same
    lookup the composition judged, never a second one.
    """

    def __init__(
        self,
        action_cache: ActionCache,
        *,
        tenant_id: str,
        action_key: str,
        trust_namespace: TrustNamespace,
        minimum_validation: ValidationLevel,
        mode: CacheMode,
    ) -> None:
        self._action_cache = action_cache
        self._request = LookupRequest(
            tenant_id=tenant_id,
            action_key=action_key,
            trust_namespace=trust_namespace,
            minimum_validation=minimum_validation,
            mode=mode,
        )
        self.result: LookupResult | None = None

    def lookup(self) -> LookupResult:
        """The single Action Cache lookup for this request, memoised."""

        if self.result is None:
            self.result = self._action_cache.lookup(self._request)
        return self.result

    def __call__(self, request: CompositionRequest) -> LayerProbe:
        del request
        result = self.lookup()
        if not result.hit or result.result_digest is None:
            reasons = [str(reason) for reason in result.reasons]
            return LayerProbe.miss(reasons[0] if reasons else "NO_ENTRY")
        return LayerProbe.hit(result.result_digest, reason_code="EXACT_RESULT_AVAILABLE")


class ControlPlaneFallbackExecutor:
    """Run the real serving/execution path and declare the work it covered.

    The control plane does not itself compile, prompt or link: it either serves
    a verified cached result or hands the request to the execution path.  The
    partition this reports — everything the layers did *not* restore — is the
    statement the composition checks, and it is computed from the restores the
    composition actually accepted, never from anything a caller supplies.
    """

    def __init__(
        self,
        operation: Callable[[], Any],
        *,
        reason_code: str = "CONTROL_PLANE_EXECUTION_PERFORMED",
    ) -> None:
        self._operation = operation
        self.reason_code = reason_code
        self.calls = 0
        self.value: Any = None

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult:
        del cache_deadline_monotonic
        self.calls += 1
        self.value = self._operation()
        performed = tuple(
            work for work in LayerWork if work not in {item.work for item in restored}
        )
        return FallbackExecutionResult(
            success=True,
            reason_code=self.reason_code,
            performed_work=performed,
            execution_digest=digest_of(
                {
                    "request_id": request.request_id,
                    "binding_digest": request.binding_digest,
                    "performed_work": [item.value for item in performed],
                }
            ),
        )


def _external_outcome(
    event: CompositionOutcomeEvent,
) -> tuple[CacheOutcome, CacheOutcomeReason]:
    """Map one composition event onto the closed diagnostic vocabulary."""

    if event.status is CompositionStatus.SKIPPED:
        return CacheOutcome.HIT, CacheOutcomeReason.EXACT_RESULT_REUSED
    if event.status is CompositionStatus.BYPASS:
        return CacheOutcome.BYPASS, CacheOutcomeReason.POLICY_BYPASS
    if event.status is CompositionStatus.MISS:
        return CacheOutcome.NECESSARY_MISS, CacheOutcomeReason.COLD_NO_ENTRY
    if event.status is CompositionStatus.ERROR:
        if event.phase is CompositionPhase.RESTORE:
            return CacheOutcome.RESTORE_FAILURE, CacheOutcomeReason.RESTORE_FAILED
        return CacheOutcome.LOOKUP_ERROR, CacheOutcomeReason.UNKNOWN_LOOKUP_ERROR
    # SUCCESS.  A successful lookup or restore is a genuine layer hit; every
    # other successful phase is bookkeeping around work that still had to run.
    if event.phase in (CompositionPhase.LOOKUP, CompositionPhase.RESTORE):
        layer = event.layer if event.layer is not None else CompositionLayer.ACTION
        return CacheOutcome.HIT, _HIT_REASON[layer]
    return CacheOutcome.NECESSARY_MISS, CacheOutcomeReason.COLD_NO_ENTRY


class ParityCompositionOutcomeSink:
    """Persist the composition's event graph where the explain endpoint reads.

    ``cache-outcome-event`` is a closed external vocabulary and the composition
    has its own; :func:`_external_outcome` is the total translation between
    them.  Every event is written — a refusal is never dropped merely because
    its composition reason has no exact external name.
    """

    def __init__(
        self,
        writer: CompositionOutcomeWriter,
        *,
        tenant_id: str,
        project_id: str,
        now: Callable[[], float],
    ) -> None:
        self._writer = writer
        self._tenant_id = tenant_id
        self._project_id = project_id
        self._now = now

    def persist(
        self,
        request: CompositionRequest,
        events: tuple[CompositionOutcomeEvent, ...],
        edges: tuple[MissCausalEdge, ...],
    ) -> None:
        # The packaged cache-outcome schema is intentionally closed and has no
        # causal-edge field.  Write the canonical external outcome rows first;
        # the graph is a derived claim.  If graph persistence fails after the
        # outcome rows commit, explain remains safely OBSERVED_ONLY instead of
        # exposing an orphan causal graph.  A writer without graph capability
        # is rejected rather than silently dropping the diagnostic lineage.
        persist_graph = getattr(self._writer, "put_cache_causal_graph", None)
        if not callable(persist_graph):
            raise ContractViolation("causal graph persistence is not wired")
        occurred_at = datetime.fromtimestamp(self._now(), tz=UTC).isoformat()
        for event in events:
            outcome, reason = _external_outcome(event)
            layer = (
                "COORDINATOR"
                if event.layer is None
                else _EXTERNAL_OUTCOME_LAYER[event.layer]
            )
            document: dict[str, Any] = {
                "schema_version": OUTCOME_EVENT_SCHEMA_VERSION,
                "event_id": event.event_id,
                "request_id": request.request_id,
                "layer": layer,
                "outcome": outcome.value,
                "reason_code": reason.value,
                "eligible": outcome is not CacheOutcome.BYPASS,
                "identity_digest": event.material_digest,
                "occurred_at": occurred_at,
            }
            self._writer.put_cache_outcome(
                self._tenant_id,
                self._project_id,
                request.request_id,
                event.event_id,
                document,
            )
        persist_graph(
            self._tenant_id,
            self._project_id,
            request.request_id,
            tuple(event.to_dict() for event in events),
            tuple(edge.to_dict() for edge in edges),
        )


@dataclass(frozen=True)
class ServingCompositionWiring:
    """Trusted collaborators that make the composition reachable.

    Every field is server-owned runtime composition.  Nothing here may be
    derived from a request body, and there is no default for the signed
    boundary: absence of this whole object is the deny-all state, exactly like
    ``serving_authorizer`` and ``prompt_cache_controller``.

    ``layer_ports`` deliberately excludes the Action layer.  Action is the only
    layer whose lookup may answer "you do not have to execute this"
    (:class:`LayerLookup` refuses ``exact_action_result`` from any other layer),
    and the only thing binding that answer to the real Action Cache is the
    per-request :class:`ActionCacheLayerProbe` the route supplies.  A port
    override replaces the whole port and so discards that probe silently, which
    is a deployment claiming an authority the runtime cannot honour — the same
    condition ``LAYER_POPULATION_NOT_WIRED`` refuses rather than pretends.
    Influence the Action layer through ``layer_probes`` instead; a per-request
    probe still wins, which is the precedence this seam requires.
    """

    serving_boundary: SignedServingBoundary
    layer_probes: Mapping[CompositionLayer, LayerProbeFn] = field(default_factory=dict)
    layer_writers: Mapping[CompositionLayer, LayerWriterFn] = field(default_factory=dict)
    layer_ports: Mapping[CompositionLayer, CacheLayerPort] = field(default_factory=dict)
    fallback_executor_factory: Callable[[Callable[[], Any]], FallbackExecutor] = (
        ControlPlaneFallbackExecutor
    )
    cache_deadline_seconds: float = 5.0
    monotonic: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if not isinstance(self.serving_boundary, SignedServingBoundary):
            raise ContractViolation(
                "cache composition wiring requires a signed serving boundary"
            )
        if self.cache_deadline_seconds <= 0:
            raise ContractViolation("cache composition deadline must be positive")
        if CompositionLayer.ACTION in self.layer_ports:
            raise ContractViolation(
                "cache composition wiring may not replace the Action layer port",
                layer=CompositionLayer.ACTION.value,
            )


@dataclass(frozen=True)
class CompositionRunOutcome:
    """What one composed request scope produced."""

    result: CompositionResult
    fallback_value: Any


class CompositionRunner:
    """One composed request scope: build the ports, run the composition once."""

    def __init__(
        self,
        wiring: ServingCompositionWiring,
        *,
        tenant_id: str,
        project_id: str,
        principal_digest: str,
        request_id: str,
        work_digest: str,
        outcome_sink: CompositionOutcomeSink,
        rollback_latch: SloRollbackLatch,
        probes: Mapping[CompositionLayer, LayerProbeFn] | None = None,
    ) -> None:
        self._wiring = wiring
        self._outcome_sink = outcome_sink
        self._rollback_latch = rollback_latch
        boundary = wiring.serving_boundary
        merged: dict[CompositionLayer, LayerProbeFn] = dict(wiring.layer_probes)
        merged.update(probes or {})
        self._ports: dict[CompositionLayer, CacheLayerPort] = {}
        for layer in CompositionLayer:
            # A port override replaces the whole port, discarding ``merged`` for
            # that layer. ``ServingCompositionWiring`` refuses that for ACTION,
            # so the layer that may skip execution always keeps its probe.
            override = wiring.layer_ports.get(layer)
            self._ports[layer] = (
                override
                if override is not None
                else ScopedCacheLayerPort(
                    layer,
                    probe=merged.get(layer),
                    writer=wiring.layer_writers.get(layer),
                )
            )
        self._binding = CompositionRuntimeBinding(
            tenant_id,
            project_id,
            principal_digest,
        )
        self.request = CompositionRequest(
            request_id=request_id,
            tenant_id=tenant_id,
            project_id=project_id,
            principal_digest=principal_digest,
            authorization_digest=boundary.authorization_digest,
            compatibility_digest=boundary.compatibility_digest,
            work_digest=work_digest,
            cache_deadline_monotonic=wiring.monotonic() + wiring.cache_deadline_seconds,
        )

    def run(self, operation: Callable[[], Any]) -> CompositionRunOutcome:
        executor = self._wiring.fallback_executor_factory(operation)
        composition = FiveLayerCacheComposition(
            binding=self._binding,
            serving_boundary=self._wiring.serving_boundary,
            prompt_port=self._ports[CompositionLayer.PROMPT],
            context_port=self._ports[CompositionLayer.CONTEXT],
            action_port=self._ports[CompositionLayer.ACTION],
            environment_port=self._ports[CompositionLayer.ENVIRONMENT],
            affinity_port=self._ports[CompositionLayer.AFFINITY],
            fallback_executor=executor,
            outcome_sink=self._outcome_sink,
            rollback_latch=self._rollback_latch,
            monotonic=self._wiring.monotonic,
        )
        result = composition.execute(self.request)
        return CompositionRunOutcome(result, getattr(executor, "value", None))


__all__ = [
    "ActionCacheLayerProbe",
    "CompositionOutcomeWriter",
    "CompositionRunOutcome",
    "CompositionRunner",
    "ControlPlaneFallbackExecutor",
    "LayerProbe",
    "LayerProbeFn",
    "LayerWriterFn",
    "ParityCompositionOutcomeSink",
    "ScopedCacheLayerPort",
    "ServingCompositionWiring",
]
