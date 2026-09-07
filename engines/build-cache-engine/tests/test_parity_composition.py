"""Behavioural tests for the signed five-layer cache-parity composition.

The module under test is a correctness seam, not a cache.  The single rule it
exists to protect is that **only a verified exact Action-layer result may
replace execution**; a prompt, context, environment or affinity hit restores a
slice of work and the fallback executor still runs everything else.  Every test
here drives the real public entry points (:class:`FiveLayerCacheComposition`,
:class:`SignedServingBoundary`, :func:`serving_boundary_statement`) with real
signing material.  Nothing in the module under test is mocked; only the ports,
executor, sink and latch it composes -- which are, by design, supplied by
trusted runtime composition -- are stubbed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any, cast

import pytest

from elmos_build_cache.errors import (
    ContractViolation,
    DigestMismatch,
    ElmosCacheError,
    PermissionDenied,
    ProvenanceInvalid,
)
from elmos_build_cache.parity_composition import (
    SERVING_BOUNDARY_DECISION,
    SERVING_BOUNDARY_KIND,
    CacheLayerPort,
    CausalRelation,
    CompositionLayer,
    CompositionOutcomeEvent,
    CompositionPhase,
    CompositionRequest,
    CompositionResult,
    CompositionRuntimeBinding,
    CompositionStatus,
    FallbackExecutionResult,
    FiveLayerCacheComposition,
    LayerLookup,
    LayerPopulation,
    LayerRestore,
    LayerWork,
    LookupDisposition,
    MissCausalEdge,
    ServingAction,
    ServingAuthorizationBoundary,
    SignedServingBoundary,
    VerifiedServingGrant,
    serving_boundary_statement,
)
from elmos_build_cache.security import (
    Ed25519ProvenanceSigner,
    HmacProvenanceSigner,
    SignedStatement,
)

TENANT = "tenant-composition"
PROJECT = "project-composition"
PRINCIPAL = "sha256:" + "a1" * 32
AUTHORIZATION = "sha256:" + "b2" * 32
COMPATIBILITY = "sha256:" + "c3" * 32
WORK = "sha256:" + "d4" * 32
MATERIAL = "sha256:" + "e5" * 32
RECEIPT = "sha256:" + "f6" * 32
ARTIFACT = "sha256:" + "07" * 32
EXECUTION = "sha256:" + "18" * 32

ISSUED_AT = 1_000.0
EXPIRES_AT = 2_000.0
NOW = 1_500.0
DEADLINE = 100.0
EARLY = 10.0
LATE = 999.0

NON_ACTION_LAYERS: tuple[CompositionLayer, ...] = (
    CompositionLayer.PROMPT,
    CompositionLayer.CONTEXT,
    CompositionLayer.ENVIRONMENT,
    CompositionLayer.AFFINITY,
)

WORK_BY_LAYER: Mapping[CompositionLayer, LayerWork] = {
    CompositionLayer.PROMPT: LayerWork.PROMPT_PREFIX,
    CompositionLayer.CONTEXT: LayerWork.CONTEXT_REHYDRATION,
    CompositionLayer.ACTION: LayerWork.ACTION_EXECUTION,
    CompositionLayer.ENVIRONMENT: LayerWork.ENVIRONMENT_PREPARATION,
    CompositionLayer.AFFINITY: LayerWork.AFFINITY_PLACEMENT,
}

EVERY_ACTION: tuple[ServingAction, ...] = (
    ServingAction.LOOKUP,
    ServingAction.RESTORE,
    ServingAction.POPULATE,
)


# ---------------------------------------------------------------------------
# stubs for the trusted collaborators the composition is handed
# ---------------------------------------------------------------------------


@dataclass
class LayerScript:
    """What one stubbed cache port should do for a single composition."""

    hit: bool = False
    disposition: LookupDisposition = LookupDisposition.MISS
    verified: bool = True
    compatible: bool = True
    foreign_namespace: bool = False
    claims_exact: bool | None = None
    lookup_raises: bool = False
    lookup_returns_none: bool = False
    lookup_wrong_layer: bool = False
    restore_raises: bool = False
    restore_succeeds: bool = True
    restore_drifts: bool = False
    restore_returns_none: bool = False
    populate_raises: bool = False
    populate_succeeds: bool = True
    populate_returns_none: bool = False


class StubPort:
    """A server-owned typed port.  It never sees or returns raw payloads."""

    def __init__(self, layer: CompositionLayer, script: LayerScript) -> None:
        self._layer = layer
        self.script = script
        self.calls: list[str] = []

    @property
    def layer(self) -> CompositionLayer:
        return self._layer

    def lookup(self, request: CompositionRequest, deadline_monotonic: float) -> LayerLookup:
        self.calls.append("lookup")
        script = self.script
        if script.lookup_raises:
            raise RuntimeError("postgres://cache:hunter2@db/parity is unreachable")
        if script.lookup_returns_none:
            return cast(LayerLookup, None)
        binding = "sha256:" + "99" * 32 if script.foreign_namespace else request.binding_digest
        layer = self._layer
        if script.lookup_wrong_layer:
            layer = (
                CompositionLayer.CONTEXT if layer is not CompositionLayer.CONTEXT else CompositionLayer.PROMPT
            )
        if not script.hit:
            return LayerLookup(layer, binding, script.disposition, "COLD_MISS")
        exact = script.claims_exact
        if exact is None:
            exact = layer is CompositionLayer.ACTION
        return LayerLookup(
            layer,
            binding,
            LookupDisposition.HIT,
            "WARM_MATERIAL",
            material_digest=MATERIAL,
            verified=script.verified,
            compatible=script.compatible,
            exact_action_result=exact,
        )

    def restore(
        self,
        request: CompositionRequest,
        lookup: LayerLookup,
        deadline_monotonic: float,
    ) -> LayerRestore:
        self.calls.append("restore")
        script = self.script
        if script.restore_raises:
            raise RuntimeError("/var/lib/elmos/secret-material is missing")
        if script.restore_returns_none:
            return cast(LayerRestore, None)
        material = "sha256:" + "22" * 32 if script.restore_drifts else MATERIAL
        if not script.restore_succeeds:
            return LayerRestore(
                self._layer,
                request.binding_digest,
                material,
                WORK_BY_LAYER[self._layer],
                False,
                "MATERIAL_UNAVAILABLE",
            )
        return LayerRestore(
            self._layer,
            request.binding_digest,
            material,
            WORK_BY_LAYER[self._layer],
            True,
            "RESTORED",
            receipt_digest=RECEIPT,
        )

    def populate(
        self,
        request: CompositionRequest,
        execution: FallbackExecutionResult,
        deadline_monotonic: float,
    ) -> LayerPopulation:
        self.calls.append("populate")
        script = self.script
        if script.populate_raises:
            raise RuntimeError("s3://elmos-cache credentials rejected")
        if script.populate_returns_none:
            return cast(LayerPopulation, None)
        if not script.populate_succeeds:
            return LayerPopulation(
                self._layer,
                request.binding_digest,
                WORK_BY_LAYER[self._layer],
                False,
                "QUOTA_EXCEEDED",
            )
        return LayerPopulation(
            self._layer,
            request.binding_digest,
            WORK_BY_LAYER[self._layer],
            True,
            "POPULATED",
            artifact_digest=ARTIFACT,
        )


class StubExecutor:
    """The correctness path: it performs every layer work item not restored."""

    def __init__(self, *, raises: bool = False, wrong_type: bool = False, succeeds: bool = True) -> None:
        self.calls = 0
        self.restored_seen: tuple[LayerRestore, ...] = ()
        self.raises = raises
        self.wrong_type = wrong_type
        self.succeeds = succeeds

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult:
        self.calls += 1
        self.restored_seen = restored
        if self.raises:
            raise RuntimeError("the compiler crashed")
        if self.wrong_type:
            return cast(FallbackExecutionResult, object())
        if not self.succeeds:
            return FallbackExecutionResult(False, "COMPILATION_FAILED", ())
        outstanding = tuple(set(LayerWork) - {item.work for item in restored})
        return FallbackExecutionResult(True, "EXECUTED", outstanding, execution_digest=EXECUTION)


class UnderPerformingExecutor:
    """Claims success while skipping work no layer restored."""

    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult:
        self.calls += 1
        return FallbackExecutionResult(
            True,
            "PARTIAL",
            (LayerWork.PROMPT_PREFIX,),
            execution_digest=EXECUTION,
        )


class StubSink:
    def __init__(self, *, raises: bool = False) -> None:
        self.calls = 0
        self.events: tuple[CompositionOutcomeEvent, ...] = ()
        self.edges: tuple[MissCausalEdge, ...] = ()
        self.raises = raises

    def persist(
        self,
        request: CompositionRequest,
        events: tuple[CompositionOutcomeEvent, ...],
        edges: tuple[MissCausalEdge, ...],
    ) -> None:
        self.calls += 1
        if self.raises:
            raise RuntimeError("cassandra://outcomes is down")
        self.events = events
        self.edges = edges


class StubLatch:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    def latch_rollback(self, reason_code: str) -> None:
        self.reasons.append(reason_code)


class ThresholdClock:
    """Returns ``early`` for the first ``trips_after`` reads, then ``late``."""

    def __init__(self, trips_after: int, *, early: float = EARLY, late: float = LATE) -> None:
        self.trips_after = trips_after
        self.early = early
        self.late = late
        self.reads = 0

    def __call__(self) -> float:
        value = self.early if self.reads < self.trips_after else self.late
        self.reads += 1
        return value


class ForgedGrantBoundary:
    """A boundary that mints grants which do not match the request it was asked about."""

    def __init__(self, delegate: SignedServingBoundary, mutation: Mapping[str, Any]) -> None:
        self.delegate = delegate
        self.mutation: dict[str, Any] = dict(mutation)

    def authorize(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        action: ServingAction,
    ) -> VerifiedServingGrant:
        return replace(self.delegate.authorize(request, layer, action), **self.mutation)


class UntypedGrantBoundary:
    def authorize(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        action: ServingAction,
    ) -> VerifiedServingGrant:
        return cast(VerifiedServingGrant, {"allowed": True})


class BrokenBoundary:
    def authorize(
        self,
        request: CompositionRequest,
        layer: CompositionLayer,
        action: ServingAction,
    ) -> VerifiedServingGrant:
        raise RuntimeError("the policy decision point is unreachable")


# ---------------------------------------------------------------------------
# construction helpers
# ---------------------------------------------------------------------------


def make_request(
    *,
    request_id: str = "request-0001",
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    principal_digest: str = PRINCIPAL,
    authorization_digest: str = AUTHORIZATION,
    compatibility_digest: str = COMPATIBILITY,
    work_digest: str = WORK,
    cache_deadline_monotonic: float = DEADLINE,
) -> CompositionRequest:
    return CompositionRequest(
        request_id=request_id,
        tenant_id=tenant_id,
        project_id=project_id,
        principal_digest=principal_digest,
        authorization_digest=authorization_digest,
        compatibility_digest=compatibility_digest,
        work_digest=work_digest,
        cache_deadline_monotonic=cache_deadline_monotonic,
    )


def make_statement(
    *,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    principal_digest: str = PRINCIPAL,
    authorization_digest: str = AUTHORIZATION,
    compatibility_digest: str = COMPATIBILITY,
    actions: Mapping[CompositionLayer, Sequence[ServingAction]] | None = None,
    issued_at: float = ISSUED_AT,
    expires_at: float = EXPIRES_AT,
) -> dict[str, Any]:
    if actions is None:
        actions = {layer: EVERY_ACTION for layer in CompositionLayer}
    return serving_boundary_statement(
        tenant_id=tenant_id,
        project_id=project_id,
        principal_digest=principal_digest,
        authorization_digest=authorization_digest,
        compatibility_digest=compatibility_digest,
        actions=actions,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def make_signer() -> Ed25519ProvenanceSigner:
    return Ed25519ProvenanceSigner.generate("cache-parity-serving")


def make_boundary(
    signer: Ed25519ProvenanceSigner,
    *,
    now: float = NOW,
    **statement_kwargs: Any,
) -> SignedServingBoundary:
    statement = make_statement(**statement_kwargs)
    receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, statement)
    return SignedServingBoundary(receipt, signer, wall_clock=lambda: now)


@dataclass
class Harness:
    composition: FiveLayerCacheComposition
    ports: dict[CompositionLayer, StubPort]
    executor: StubExecutor
    sink: StubSink
    latch: StubLatch
    signer: Ed25519ProvenanceSigner
    request: CompositionRequest = field(default_factory=make_request)

    def run(self) -> CompositionResult:
        return self.composition.execute(self.request)

    def port_calls(self) -> dict[CompositionLayer, list[str]]:
        return {layer: list(port.calls) for layer, port in self.ports.items()}

    def reasons(self, phase: CompositionPhase) -> list[str]:
        return [event.reason_code for event in self.sink.events if event.phase is phase]


def build_harness(
    *,
    scripts: Mapping[CompositionLayer, LayerScript] | None = None,
    executor: StubExecutor | None = None,
    sink: StubSink | None = None,
    boundary: ServingAuthorizationBoundary | None = None,
    binding: CompositionRuntimeBinding | None = None,
    monotonic: ThresholdClock | None = None,
    signer: Ed25519ProvenanceSigner | None = None,
) -> Harness:
    scripts = scripts or {}
    signer = signer or make_signer()
    ports = {layer: StubPort(layer, scripts.get(layer, LayerScript())) for layer in CompositionLayer}
    executor = executor if executor is not None else StubExecutor()
    sink = sink if sink is not None else StubSink()
    latch = StubLatch()
    clock = monotonic or ThresholdClock(trips_after=10_000)
    composition = FiveLayerCacheComposition(
        binding=binding or CompositionRuntimeBinding(TENANT, PROJECT, PRINCIPAL),
        serving_boundary=boundary or make_boundary(signer),
        prompt_port=ports[CompositionLayer.PROMPT],
        context_port=ports[CompositionLayer.CONTEXT],
        action_port=ports[CompositionLayer.ACTION],
        environment_port=ports[CompositionLayer.ENVIRONMENT],
        affinity_port=ports[CompositionLayer.AFFINITY],
        fallback_executor=executor,
        outcome_sink=sink,
        rollback_latch=latch,
        monotonic=clock,
    )
    return Harness(composition, ports, executor, sink, latch, signer)


def hit_scripts(layers: Iterable[CompositionLayer], **overrides: Any) -> dict[CompositionLayer, LayerScript]:
    return {layer: replace(LayerScript(hit=True), **overrides) for layer in layers}


def assert_execution_happened(result: CompositionResult, harness: Harness) -> None:
    """The composition did not skip the model/compiler/test work."""

    assert result.exact_action_reused is False
    assert result.fallback_executed is True
    assert harness.executor.calls == 1
    assert result.fallback_result is not None
    assert LayerWork.ACTION_EXECUTION in result.fallback_result.performed_work


# ---------------------------------------------------------------------------
# 1. authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("tenant_id", "tenant-intruder"),
        ("principal_digest", "sha256:" + "31" * 32),
        ("project_id", "project-intruder"),
    ],
)
def test_out_of_scope_caller_cannot_compose(field_name: str, value: str) -> None:
    harness = build_harness(scripts=hit_scripts(CompositionLayer))
    override: dict[str, Any] = {field_name: value}
    foreign = replace(harness.request, **override)

    with pytest.raises(PermissionDenied) as excinfo:
        harness.composition.execute(foreign)

    assert "cache composition scope is not accessible" in str(excinfo.value)
    assert harness.port_calls() == {layer: [] for layer in CompositionLayer}
    assert harness.executor.calls == 0
    assert harness.sink.calls == 0


def test_refusal_of_a_foreign_caller_is_not_an_existence_oracle() -> None:
    """The refusal is identical whether or not an exact Action entry exists."""

    populated = build_harness(scripts=hit_scripts(CompositionLayer))
    empty = build_harness()
    foreign_populated = replace(populated.request, tenant_id="tenant-intruder")
    foreign_empty = replace(empty.request, tenant_id="tenant-intruder")

    with pytest.raises(PermissionDenied) as hot:
        populated.composition.execute(foreign_populated)
    with pytest.raises(PermissionDenied) as cold:
        empty.composition.execute(foreign_empty)

    assert str(hot.value) == str(cold.value)
    assert hot.value.to_dict() == cold.value.to_dict()
    assert populated.port_calls() == empty.port_calls()
    assert populated.sink.calls == empty.sink.calls == 0


@pytest.mark.parametrize(
    "receipt_override",
    [
        {"tenant_id": "tenant-other"},
        {"project_id": "project-other"},
        {"principal_digest": "sha256:" + "42" * 32},
        {"authorization_digest": "sha256:" + "43" * 32},
        {"compatibility_digest": "sha256:" + "44" * 32},
    ],
)
def test_receipt_for_another_scope_authorizes_nothing(receipt_override: dict[str, Any]) -> None:
    signer = make_signer()
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        boundary=make_boundary(signer, **receipt_override),
        signer=signer,
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.reasons(CompositionPhase.LOOKUP) == ["SERVING_AUTHORIZATION_FAILED"] * 5
    assert harness.port_calls() == {layer: [] for layer in CompositionLayer}
    assert set(harness.latch.reasons) == {"SERVING_AUTHORIZATION_FAILED"}


def test_cross_tenant_grant_request_is_refused_at_the_boundary() -> None:
    signer = make_signer()
    boundary = make_boundary(signer)

    with pytest.raises(PermissionDenied) as excinfo:
        boundary.authorize(
            make_request(tenant_id="tenant-other"),
            CompositionLayer.ACTION,
            ServingAction.LOOKUP,
        )

    assert "serving scope is not authorized" in str(excinfo.value)


def test_cross_principal_grant_request_is_refused_at_the_boundary() -> None:
    signer = make_signer()
    boundary = make_boundary(signer)

    with pytest.raises(PermissionDenied) as excinfo:
        boundary.authorize(
            make_request(principal_digest="sha256:" + "52" * 32),
            CompositionLayer.ACTION,
            ServingAction.LOOKUP,
        )

    assert "serving scope is not authorized" in str(excinfo.value)


@pytest.mark.parametrize("now", [ISSUED_AT - 1.0, EXPIRES_AT, EXPIRES_AT + 1.0])
def test_receipt_outside_its_validity_window_authorizes_nothing(now: float) -> None:
    signer = make_signer()
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        boundary=make_boundary(signer, now=now),
        signer=signer,
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.reasons(CompositionPhase.LOOKUP) == ["SERVING_AUTHORIZATION_FAILED"] * 5


def test_action_lookup_denied_by_the_grant_still_runs_execution() -> None:
    signer = make_signer()
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        boundary=make_boundary(
            signer,
            actions={layer: (ServingAction.POPULATE,) for layer in CompositionLayer},
        ),
        signer=signer,
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.reasons(CompositionPhase.LOOKUP) == ["SERVING_ACTION_DENIED"] * 5
    # The grant still permits POPULATE, so the port is written to but never read from.
    assert harness.port_calls()[CompositionLayer.ACTION] == ["populate"]
    assert all("lookup" not in calls for calls in harness.port_calls().values())


def test_restore_denied_by_the_grant_still_runs_execution() -> None:
    signer = make_signer()
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        boundary=make_boundary(
            signer,
            actions={layer: (ServingAction.LOOKUP, ServingAction.POPULATE) for layer in CompositionLayer},
        ),
        signer=signer,
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert result.restored == ()
    assert harness.reasons(CompositionPhase.RESTORE) == ["SERVING_ACTION_DENIED"] * 5
    assert harness.executor.restored_seen == ()


@pytest.mark.parametrize(
    "mutation",
    [
        {"request_id": "request-9999"},
        {"tenant_id": "tenant-other"},
        {"project_id": "project-other"},
        {"principal_digest": "sha256:" + "62" * 32},
        {"authorization_digest": "sha256:" + "63" * 32},
        {"compatibility_digest": "sha256:" + "64" * 32},
        {"layer": CompositionLayer.PROMPT},
        {"action": ServingAction.POPULATE},
    ],
)
def test_a_grant_that_does_not_match_the_call_is_refused(mutation: dict[str, Any]) -> None:
    signer = make_signer()
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        boundary=ForgedGrantBoundary(make_boundary(signer), mutation),
        signer=signer,
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert set(harness.latch.reasons) == {"SERVING_AUTHORIZATION_SCOPE_DRIFT"}
    # A grant is only usable for the exact (request, layer, action) triple it names, so the
    # Action layer -- the only one that could skip execution -- is always refused here.
    action_lookup = next(
        event
        for event in harness.sink.events
        if event.phase is CompositionPhase.LOOKUP and event.layer is CompositionLayer.ACTION
    )
    assert action_lookup.status is CompositionStatus.BYPASS
    assert action_lookup.reason_code == "SERVING_AUTHORIZATION_SCOPE_DRIFT"
    assert harness.port_calls()[CompositionLayer.ACTION][:1] != ["lookup"]


def test_a_boundary_returning_an_unknown_grant_type_is_refused() -> None:
    harness = build_harness(scripts=hit_scripts(CompositionLayer), boundary=UntypedGrantBoundary())

    result = harness.run()

    assert_execution_happened(result, harness)
    assert set(harness.latch.reasons) == {"SERVING_AUTHORIZATION_INVALID"}


def test_a_boundary_that_fails_open_is_refused() -> None:
    harness = build_harness(scripts=hit_scripts(CompositionLayer), boundary=BrokenBoundary())

    result = harness.run()

    assert_execution_happened(result, harness)
    assert set(harness.latch.reasons) == {"SERVING_AUTHORIZATION_FAILED"}


def test_execute_refuses_a_request_that_is_not_the_closed_type() -> None:
    harness = build_harness()

    with pytest.raises(ContractViolation) as excinfo:
        harness.composition.execute(cast(CompositionRequest, {"tenant_id": TENANT}))

    assert "closed request type" in str(excinfo.value)
    assert harness.executor.calls == 0


# ---------------------------------------------------------------------------
# 2. deadline
# ---------------------------------------------------------------------------


def test_a_deadline_already_in_the_past_consults_no_layer() -> None:
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        monotonic=ThresholdClock(trips_after=0),
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.port_calls() == {layer: [] for layer in CompositionLayer}
    assert harness.reasons(CompositionPhase.LOOKUP) == ["CACHE_DEADLINE_EXCEEDED"] * 5
    assert result.restored == ()
    assert result.populations == ()
    assert result.fallback_result is not None
    assert set(result.fallback_result.performed_work) == set(LayerWork)


def test_a_deadline_that_expires_during_lookup_discards_the_lookup() -> None:
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        monotonic=ThresholdClock(trips_after=1),
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.port_calls()[CompositionLayer.ACTION] == ["lookup"]
    assert harness.reasons(CompositionPhase.LOOKUP)[0] == "LOOKUP_DEADLINE_EXCEEDED"
    assert "CACHE_LOOKUP_DEADLINE_EXCEEDED" in harness.latch.reasons


def test_a_deadline_that_expires_during_restore_discards_the_restore() -> None:
    """A restore that finished after the deadline is never allowed to skip execution."""

    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        monotonic=ThresholdClock(trips_after=3),
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.port_calls()[CompositionLayer.ACTION] == ["lookup", "restore"]
    assert harness.reasons(CompositionPhase.RESTORE) == ["RESTORE_DEADLINE_EXCEEDED"]
    assert "CACHE_RESTORE_DEADLINE_EXCEEDED" in harness.latch.reasons
    assert result.restored == ()


def test_a_deadline_that_expires_before_population_bypasses_population() -> None:
    harness = build_harness(monotonic=ThresholdClock(trips_after=10))

    result = harness.run()

    assert_execution_happened(result, harness)
    assert result.populations == ()
    assert harness.reasons(CompositionPhase.POPULATE) == ["CACHE_DEADLINE_EXCEEDED"] * 5
    assert harness.port_calls()[CompositionLayer.ACTION] == ["lookup"]


def test_an_unusable_monotonic_clock_is_treated_as_an_expired_deadline() -> None:
    class NanClock(ThresholdClock):
        def __call__(self) -> float:
            self.reads += 1
            return float("nan")

    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        monotonic=NanClock(trips_after=0),
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "MONOTONIC_CLOCK_INVALID" in harness.latch.reasons
    assert harness.port_calls() == {layer: [] for layer in CompositionLayer}


@pytest.mark.parametrize("deadline", [-1.0, float("nan"), float("inf")])
def test_a_request_refuses_an_unusable_deadline(deadline: float) -> None:
    with pytest.raises(ContractViolation) as excinfo:
        make_request(cache_deadline_monotonic=deadline)

    assert "cache_deadline_monotonic" in str(excinfo.value)


@pytest.mark.parametrize("deadline", [True, "100", None])
def test_a_request_refuses_a_non_numeric_deadline(deadline: object) -> None:
    with pytest.raises(ContractViolation) as excinfo:
        make_request(cache_deadline_monotonic=cast(float, deadline))

    assert "must be numeric" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 3. the five hooks: lookup / restore / populate / outcome / miss
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_lookup_hook_success_path(layer: CompositionLayer) -> None:
    harness = build_harness(scripts=hit_scripts([layer]))

    result = harness.run()

    assert harness.port_calls()[layer][0] == "lookup"
    lookup_events = [event for event in harness.sink.events if event.phase is CompositionPhase.LOOKUP]
    hit = next(event for event in lookup_events if event.layer is layer)
    assert hit.status is CompositionStatus.SUCCESS
    assert hit.reason_code == "WARM_MATERIAL"
    assert hit.material_digest == MATERIAL
    assert result.outcome_persisted is True


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_lookup_hook_fails_closed_when_the_port_raises(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(hit=True, lookup_raises=True)})

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_LOOKUP_RUNTIME_FAILED" in harness.latch.reasons
    failure = next(
        event
        for event in harness.sink.events
        if event.phase is CompositionPhase.LOOKUP and event.layer is layer
    )
    assert failure.status is CompositionStatus.ERROR
    assert failure.reason_code == "LOOKUP_RUNTIME_FAILED"
    assert failure.material_digest is None
    assert "hunter2" not in failure.reason_code


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_lookup_hook_fails_closed_on_scope_drift(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(hit=True, lookup_wrong_layer=True)})

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_LOOKUP_SCOPE_DRIFT" in harness.latch.reasons


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_restore_hook_success_path(layer: CompositionLayer) -> None:
    harness = build_harness(scripts=hit_scripts([layer]))

    result = harness.run()

    assert harness.port_calls()[layer] == ["lookup", "restore"]
    assert [item.layer for item in result.restored] == [layer]
    assert result.restored[0].work is WORK_BY_LAYER[layer]
    assert result.restored[0].receipt_digest == RECEIPT


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_restore_hook_fails_closed_when_the_port_raises(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(hit=True, restore_raises=True)})

    result = harness.run()

    assert_execution_happened(result, harness)
    assert result.restored == ()
    assert "CACHE_RESTORE_RUNTIME_FAILED" in harness.latch.reasons
    failure = next(
        event
        for event in harness.sink.events
        if event.phase is CompositionPhase.RESTORE and event.layer is layer
    )
    assert failure.status is CompositionStatus.ERROR
    assert failure.reason_code == "RESTORE_RUNTIME_FAILED"


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_restore_hook_fails_closed_when_material_drifts(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(hit=True, restore_drifts=True)})

    result = harness.run()

    assert_execution_happened(result, harness)
    assert result.restored == ()
    assert "CACHE_RESTORE_SCOPE_DRIFT" in harness.latch.reasons


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_populate_hook_success_path(layer: CompositionLayer) -> None:
    harness = build_harness()

    result = harness.run()

    assert harness.port_calls()[layer] == ["lookup", "populate"]
    populated = {item.layer for item in result.populations}
    assert populated == set(CompositionLayer)
    entry = next(item for item in result.populations if item.layer is layer)
    assert entry.work is WORK_BY_LAYER[layer]
    assert entry.artifact_digest == ARTIFACT


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_populate_hook_fails_closed_when_the_port_raises(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(populate_raises=True)})

    result = harness.run()

    assert {item.layer for item in result.populations} == set(CompositionLayer) - {layer}
    assert "CACHE_POPULATE_RUNTIME_FAILED" in harness.latch.reasons
    failure = next(
        event
        for event in harness.sink.events
        if event.phase is CompositionPhase.POPULATE and event.layer is layer
    )
    assert failure.status is CompositionStatus.ERROR
    assert failure.reason_code == "POPULATE_RUNTIME_FAILED"


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_populate_hook_fails_closed_when_the_port_reports_failure(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(populate_succeeds=False)})

    result = harness.run()

    assert {item.layer for item in result.populations} == set(CompositionLayer) - {layer}
    assert "CACHE_POPULATE_FAILED" in harness.latch.reasons


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_populate_hook_fails_closed_on_scope_drift(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(populate_returns_none=True)})

    result = harness.run()

    assert {item.layer for item in result.populations} == set(CompositionLayer) - {layer}
    assert "CACHE_POPULATE_SCOPE_DRIFT" in harness.latch.reasons


def test_populate_only_writes_the_layers_the_fallback_actually_recomputed() -> None:
    harness = build_harness(scripts=hit_scripts([CompositionLayer.CONTEXT]))

    result = harness.run()

    assert_execution_happened(result, harness)
    assert {item.layer for item in result.populations} == set(CompositionLayer) - {CompositionLayer.CONTEXT}
    assert harness.port_calls()[CompositionLayer.CONTEXT] == ["lookup", "restore"]


def test_outcome_hook_receives_the_full_event_and_edge_graph() -> None:
    harness = build_harness()

    result = harness.run()

    assert harness.sink.calls == 1
    assert result.outcome_persisted is True
    assert harness.sink.events == result.events
    assert harness.sink.edges == result.causal_edges
    event_ids = {event.event_id for event in result.events}
    assert len(event_ids) == len(result.events)
    for edge in result.causal_edges:
        assert edge.source_event_id in event_ids
        assert edge.target_event_id in event_ids
    assert result.events[0].phase is CompositionPhase.REQUEST
    assert result.events[0].reason_code == "BOUND_SCOPE_ACCEPTED"


def test_outcome_hook_failure_is_reported_and_never_silently_swallowed() -> None:
    harness = build_harness(sink=StubSink(raises=True))

    result = harness.run()

    assert result.outcome_persisted is False
    assert "CACHE_OUTCOME_PERSISTENCE_FAILED" in harness.latch.reasons


def test_miss_hook_records_a_causal_edge_from_every_miss_to_the_fallback() -> None:
    harness = build_harness()

    result = harness.run()

    fallback = next(event for event in result.events if event.phase is CompositionPhase.FALLBACK)
    causes = {
        edge.source_event_id
        for edge in result.causal_edges
        if edge.target_event_id == fallback.event_id and edge.relation is CausalRelation.CAUSED_FALLBACK
    }
    misses = {
        event.event_id
        for event in result.events
        if event.phase is CompositionPhase.LOOKUP and event.status is CompositionStatus.MISS
    }
    assert misses
    assert causes == misses
    assert any(
        edge.relation is CausalRelation.REQUESTED and edge.target_event_id == fallback.event_id
        for edge in result.causal_edges
    )


def test_miss_hook_records_restored_layers_as_supplying_layer_work() -> None:
    harness = build_harness(scripts=hit_scripts([CompositionLayer.PROMPT, CompositionLayer.AFFINITY]))

    result = harness.run()

    fallback = next(event for event in result.events if event.phase is CompositionPhase.FALLBACK)
    suppliers = {
        edge.source_event_id
        for edge in result.causal_edges
        if edge.target_event_id == fallback.event_id
        and edge.relation is CausalRelation.SUPPLIED_LAYER_WORK
    }
    restores = {
        event.event_id
        for event in result.events
        if event.phase is CompositionPhase.RESTORE and event.status is CompositionStatus.SUCCESS
    }
    assert len(restores) == 2
    assert suppliers == restores


def test_miss_hook_marks_an_exact_action_reuse_as_completed_by_its_restore() -> None:
    harness = build_harness(scripts=hit_scripts([CompositionLayer.ACTION]))

    result = harness.run()

    completion = next(event for event in result.events if event.phase is CompositionPhase.COMPLETE)
    assert completion.status is CompositionStatus.SKIPPED
    assert completion.reason_code == "EXACT_ACTION_REUSED"
    restore = next(event for event in result.events if event.phase is CompositionPhase.RESTORE)
    assert MissCausalEdge(restore.event_id, completion.event_id, CausalRelation.COMPLETED_BY) in (
        result.causal_edges
    )


# ---------------------------------------------------------------------------
# 4. THE CENTRAL INVARIANT: only an exact Action-layer hit may skip execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layer", list(NON_ACTION_LAYERS))
def test_a_single_non_action_hit_still_requires_execution(layer: CompositionLayer) -> None:
    """A prompt / context / environment / affinity hit restores work; it never skips it."""

    harness = build_harness(scripts=hit_scripts([layer]))

    result = harness.run()

    assert_execution_happened(result, harness)
    assert [item.layer for item in result.restored] == [layer]
    assert result.fallback_result is not None
    assert set(result.fallback_result.performed_work) == set(LayerWork) - {WORK_BY_LAYER[layer]}
    assert harness.executor.restored_seen == result.restored


def test_all_four_non_action_hits_together_still_require_execution() -> None:
    harness = build_harness(scripts=hit_scripts(NON_ACTION_LAYERS))

    result = harness.run()

    assert_execution_happened(result, harness)
    assert {item.layer for item in result.restored} == set(NON_ACTION_LAYERS)
    assert result.fallback_result is not None
    assert set(result.fallback_result.performed_work) == {LayerWork.ACTION_EXECUTION}


@pytest.mark.parametrize(
    "combo",
    [
        combo
        for size in range(1, len(NON_ACTION_LAYERS) + 1)
        for combo in combinations(NON_ACTION_LAYERS, size)
    ],
)
def test_no_combination_of_non_action_hits_can_skip_execution(
    combo: tuple[CompositionLayer, ...],
) -> None:
    harness = build_harness(scripts=hit_scripts(combo))

    result = harness.run()

    assert_execution_happened(result, harness)
    assert {item.layer for item in result.restored} == set(combo)


def test_only_a_validated_exact_action_result_short_circuits_execution() -> None:
    harness = build_harness(scripts=hit_scripts(CompositionLayer))

    result = harness.run()

    assert result.exact_action_reused is True
    assert result.fallback_executed is False
    assert result.fallback_result is None
    assert harness.executor.calls == 0
    assert [item.layer for item in result.restored] == [CompositionLayer.ACTION]
    assert result.populations == ()
    # No other layer is even consulted: the Action Cache is probed first.
    for layer in NON_ACTION_LAYERS:
        assert harness.port_calls()[layer] == []


def test_an_action_entry_that_fails_validation_does_not_skip_execution() -> None:
    harness = build_harness(scripts={CompositionLayer.ACTION: LayerScript(hit=True, verified=False)})

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_LOOKUP_UNVERIFIED_MATERIAL" in harness.latch.reasons
    failure = next(
        event
        for event in harness.sink.events
        if event.phase is CompositionPhase.LOOKUP and event.layer is CompositionLayer.ACTION
    )
    assert failure.reason_code == "UNVERIFIED_MATERIAL"


def test_an_action_entry_below_the_required_validation_level_does_not_skip_execution() -> None:
    harness = build_harness(scripts={CompositionLayer.ACTION: LayerScript(hit=True, compatible=False)})

    result = harness.run()

    assert_execution_happened(result, harness)
    failure = next(
        event
        for event in harness.sink.events
        if event.phase is CompositionPhase.LOOKUP and event.layer is CompositionLayer.ACTION
    )
    assert failure.status is CompositionStatus.MISS
    assert failure.reason_code == "COMPATIBILITY_MISMATCH"
    assert harness.port_calls()[CompositionLayer.ACTION] == ["lookup", "populate"]


def test_an_action_entry_from_another_trust_namespace_does_not_skip_execution() -> None:
    harness = build_harness(
        scripts={CompositionLayer.ACTION: LayerScript(hit=True, foreign_namespace=True)}
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_LOOKUP_SCOPE_DRIFT" in harness.latch.reasons


def test_an_action_entry_not_marked_exact_cannot_be_offered_at_all() -> None:
    with pytest.raises(ContractViolation) as excinfo:
        LayerLookup(
            CompositionLayer.ACTION,
            make_request().binding_digest,
            LookupDisposition.HIT,
            "WARM_MATERIAL",
            material_digest=MATERIAL,
            verified=True,
            compatible=True,
            exact_action_result=False,
        )

    assert "Action Cache hits must be exact results" in str(excinfo.value)


def test_a_port_offering_a_non_exact_action_hit_fails_closed_end_to_end() -> None:
    harness = build_harness(
        scripts={CompositionLayer.ACTION: LayerScript(hit=True, claims_exact=False)}
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_LOOKUP_RUNTIME_FAILED" in harness.latch.reasons


@pytest.mark.parametrize("layer", list(NON_ACTION_LAYERS))
def test_a_non_action_layer_may_never_claim_an_exact_result(layer: CompositionLayer) -> None:
    with pytest.raises(ContractViolation) as excinfo:
        LayerLookup(
            layer,
            make_request().binding_digest,
            LookupDisposition.HIT,
            "WARM_MATERIAL",
            material_digest=MATERIAL,
            verified=True,
            compatible=True,
            exact_action_result=True,
        )

    assert "only Action Cache may return an exact result" in str(excinfo.value)


def test_a_failing_action_restore_does_not_skip_execution() -> None:
    harness = build_harness(
        scripts={CompositionLayer.ACTION: LayerScript(hit=True, restore_succeeds=False)}
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_RESTORE_FAILED" in harness.latch.reasons
    assert result.restored == ()


def test_an_action_hit_whose_restore_returns_other_material_does_not_skip_execution() -> None:
    harness = build_harness(
        scripts={CompositionLayer.ACTION: LayerScript(hit=True, restore_drifts=True)}
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_RESTORE_SCOPE_DRIFT" in harness.latch.reasons


@pytest.mark.parametrize(
    "disposition",
    [LookupDisposition.MISS, LookupDisposition.BYPASS, LookupDisposition.ERROR],
)
def test_a_non_hit_action_disposition_never_skips_execution(disposition: LookupDisposition) -> None:
    harness = build_harness(scripts={CompositionLayer.ACTION: LayerScript(disposition=disposition)})

    result = harness.run()

    assert_execution_happened(result, harness)


def test_the_result_type_forbids_claiming_both_reuse_and_execution() -> None:
    binding = make_request().binding_digest
    with pytest.raises(ContractViolation) as excinfo:
        CompositionResult("request-0001", binding, True, True, None, (), (), (), (), True)
    assert "mutually exclusive" in str(excinfo.value)

    with pytest.raises(ContractViolation):
        CompositionResult("request-0001", binding, False, False, None, (), (), (), (), True)


def test_the_result_type_forbids_execution_without_an_execution_result() -> None:
    binding = make_request().binding_digest
    with pytest.raises(ContractViolation) as excinfo:
        CompositionResult("request-0001", binding, False, True, None, (), (), (), (), True)

    assert "fallback result does not match execution state" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 5. signature binding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tamper",
    [
        {"tenant_id": "tenant-other"},
        {"project_id": "project-other"},
        {"principal_digest": "sha256:" + "72" * 32},
        {"authorization_digest": "sha256:" + "73" * 32},
        {"compatibility_digest": "sha256:" + "74" * 32},
        {"issued_at": 0.0},
        {"expires_at": 9_999.0},
        {"decision": "DENY_CACHE_PARITY_COMPOSITION"},
        {"actions": {"ACTION": ["LOOKUP", "RESTORE", "POPULATE"], "PROMPT": ["POPULATE"]}},
    ],
)
def test_the_receipt_signature_binds_every_claim_it_makes(tamper: dict[str, Any]) -> None:
    signer = make_signer()
    statement = make_statement(actions={CompositionLayer.ACTION: EVERY_ACTION})
    receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, statement)
    forged = replace(receipt, statement={**statement, **tamper})

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(forged, signer, wall_clock=lambda: NOW)

    assert "signature does not verify" in str(excinfo.value)


def test_a_signature_from_one_composition_does_not_verify_another() -> None:
    signer = make_signer()
    wide = make_statement()
    narrow = make_statement(actions={CompositionLayer.ACTION: (ServingAction.LOOKUP,)})
    wide_receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, wide)
    narrow_receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, narrow)
    assert wide_receipt.signature != narrow_receipt.signature

    replayed = SignedStatement(
        SERVING_BOUNDARY_KIND,
        dict(narrow),
        wide_receipt.signature,
        wide_receipt.key_id,
        wide_receipt.algorithm,
    )

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(replayed, signer, wall_clock=lambda: NOW)

    assert "signature does not verify" in str(excinfo.value)


def test_a_receipt_signed_for_another_purpose_is_refused() -> None:
    signer = make_signer()
    receipt = signer.sign_statement("elmos.some-other-decision/v1", make_statement())

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(receipt, signer, wall_clock=lambda: NOW)

    assert "wrong kind" in str(excinfo.value)


def test_a_receipt_from_an_unknown_key_is_refused() -> None:
    ours = make_signer()
    theirs = Ed25519ProvenanceSigner.generate("attacker-key")
    receipt = theirs.sign_statement(SERVING_BOUNDARY_KIND, make_statement())

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(receipt, ours, wall_clock=lambda: NOW)

    assert "unknown signing key" in str(excinfo.value)


def test_a_symmetric_signer_may_not_verify_the_serving_boundary() -> None:
    shared = HmacProvenanceSigner({"shared": b"0" * 32}, "shared")
    receipt = shared.sign_statement(SERVING_BOUNDARY_KIND, make_statement())

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(receipt, shared, wall_clock=lambda: NOW)

    assert "asymmetric" in str(excinfo.value)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": "9.9.9"}, "schema is unsupported"),
        ({"decision": "DENY"}, "decision is denied"),
        ({"expires_at": ISSUED_AT - 1.0}, "invalid time bounds"),
        ({"actions": {}}, "has no actions"),
        ({"actions": ["ACTION"]}, "has no actions"),
        ({"actions": {"NOT_A_LAYER": ["LOOKUP"]}}, "unknown actions"),
        ({"actions": {"ACTION": ["EVICT"]}}, "unknown actions"),
        ({"actions": {"ACTION": "LOOKUP"}}, "unknown actions"),
        ({"actions": {"ACTION": []}}, "unknown actions"),
        ({"actions": {"ACTION": ["LOOKUP", "LOOKUP"]}}, "unknown actions"),
        ({"extra_claim": True}, "invalid shape"),
    ],
)
def test_a_structurally_invalid_receipt_is_refused(mutation: dict[str, Any], message: str) -> None:
    signer = make_signer()
    statement = {**make_statement(), **mutation}
    receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, statement)

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(receipt, signer, wall_clock=lambda: NOW)

    assert message in str(excinfo.value)


def test_a_receipt_missing_a_claim_is_refused() -> None:
    signer = make_signer()
    statement = {key: value for key, value in make_statement().items() if key != "principal_digest"}
    receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, statement)

    with pytest.raises(ProvenanceInvalid) as excinfo:
        SignedServingBoundary(receipt, signer, wall_clock=lambda: NOW)

    assert "invalid shape" in str(excinfo.value)


def test_the_receipt_survives_a_json_round_trip_and_still_binds_its_layer_set() -> None:
    signer = make_signer()
    statement = make_statement(
        actions={
            CompositionLayer.ACTION: (ServingAction.RESTORE, ServingAction.LOOKUP),
            CompositionLayer.PROMPT: (ServingAction.LOOKUP,),
        }
    )
    assert statement["decision"] == SERVING_BOUNDARY_DECISION
    receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, statement)
    stored = SignedStatement.from_dict(json.loads(json.dumps(receipt.to_dict())))

    boundary = SignedServingBoundary(stored, signer, wall_clock=lambda: NOW)
    request = make_request()

    assert boundary.authorize(request, CompositionLayer.ACTION, ServingAction.LOOKUP).allowed is True
    assert boundary.authorize(request, CompositionLayer.ACTION, ServingAction.POPULATE).allowed is False
    assert boundary.authorize(request, CompositionLayer.CONTEXT, ServingAction.LOOKUP).allowed is False
    assert boundary.receipt_digest == SignedServingBoundary(
        receipt, signer, wall_clock=lambda: NOW
    ).receipt_digest


def test_a_grant_binds_the_exact_request_layer_and_action_it_was_issued_for() -> None:
    signer = make_signer()
    boundary = make_boundary(signer)
    request = make_request()

    grant = boundary.authorize(request, CompositionLayer.ACTION, ServingAction.RESTORE)

    assert grant.request_id == request.request_id
    assert grant.tenant_id == request.tenant_id
    assert grant.principal_digest == request.principal_digest
    assert grant.layer is CompositionLayer.ACTION
    assert grant.action is ServingAction.RESTORE
    assert grant.receipt_digest == boundary.receipt_digest
    assert grant.allowed is True


@pytest.mark.parametrize(
    "actions",
    [
        {},
        {CompositionLayer.ACTION: ()},
        {CompositionLayer.ACTION: (ServingAction.LOOKUP, ServingAction.LOOKUP)},
    ],
)
def test_the_statement_builder_refuses_an_unusable_layer_set(
    actions: Mapping[CompositionLayer, Sequence[ServingAction]],
) -> None:
    with pytest.raises(ContractViolation):
        make_statement(actions=actions)


def test_the_statement_builder_refuses_an_expiry_that_does_not_follow_issuance() -> None:
    with pytest.raises(ContractViolation) as excinfo:
        make_statement(issued_at=100.0, expires_at=100.0)

    assert "expiry must follow issuance" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 6. fail-closed composition types
# ---------------------------------------------------------------------------


def test_every_recorded_refusal_uses_the_modules_closed_vocabulary() -> None:
    harness = build_harness(
        scripts={
            CompositionLayer.ACTION: LayerScript(hit=True, verified=False),
            CompositionLayer.CONTEXT: LayerScript(hit=True, restore_raises=True),
            CompositionLayer.ENVIRONMENT: LayerScript(hit=True, lookup_raises=True),
            CompositionLayer.AFFINITY: LayerScript(populate_succeeds=False),
            CompositionLayer.PROMPT: LayerScript(hit=True, compatible=False),
        }
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    for event in result.events:
        assert isinstance(event.phase, CompositionPhase)
        assert isinstance(event.status, CompositionStatus)
        assert event.layer is None or isinstance(event.layer, CompositionLayer)
        assert event.reason_code == event.reason_code.strip()
        assert event.reason_code
    for edge in result.causal_edges:
        assert isinstance(edge.relation, CausalRelation)
    for reason in harness.latch.reasons:
        assert reason.replace("_", "").isalnum()
    payload = result.to_dict()
    assert payload["schema_version"] == "1.2.0"
    assert payload["certification"] == "NOT_CERTIFIED"
    assert payload["exact_action_reused"] is False
    assert payload["fallback_executed"] is True


@pytest.mark.parametrize(
    "error_type",
    [ContractViolation, PermissionDenied, ProvenanceInvalid, DigestMismatch],
)
def test_the_modules_refusal_types_are_all_typed_engine_errors(error_type: type[ElmosCacheError]) -> None:
    assert issubclass(error_type, ElmosCacheError)
    assert error_type("boom").code


def test_an_unavailable_layer_port_is_refused_rather_than_silently_dropped() -> None:
    ports = {layer: StubPort(layer, LayerScript()) for layer in CompositionLayer}

    with pytest.raises(ContractViolation) as excinfo:
        FiveLayerCacheComposition(
            binding=CompositionRuntimeBinding(TENANT, PROJECT, PRINCIPAL),
            serving_boundary=make_boundary(make_signer()),
            prompt_port=ports[CompositionLayer.PROMPT],
            context_port=ports[CompositionLayer.CONTEXT],
            action_port=cast(CacheLayerPort, None),
            environment_port=ports[CompositionLayer.ENVIRONMENT],
            affinity_port=ports[CompositionLayer.AFFINITY],
            fallback_executor=StubExecutor(),
            outcome_sink=StubSink(),
            rollback_latch=StubLatch(),
        )

    assert "does not expose a closed layer" in str(excinfo.value)


def test_a_port_wired_to_the_wrong_layer_is_refused() -> None:
    ports = {layer: StubPort(layer, LayerScript()) for layer in CompositionLayer}

    with pytest.raises(ContractViolation) as excinfo:
        FiveLayerCacheComposition(
            binding=CompositionRuntimeBinding(TENANT, PROJECT, PRINCIPAL),
            serving_boundary=make_boundary(make_signer()),
            prompt_port=ports[CompositionLayer.CONTEXT],
            context_port=ports[CompositionLayer.CONTEXT],
            action_port=ports[CompositionLayer.ACTION],
            environment_port=ports[CompositionLayer.ENVIRONMENT],
            affinity_port=ports[CompositionLayer.AFFINITY],
            fallback_executor=StubExecutor(),
            outcome_sink=StubSink(),
            rollback_latch=StubLatch(),
        )

    assert "wired to the wrong layer" in str(excinfo.value)


def test_the_composition_cannot_be_built_with_fewer_than_five_layers() -> None:
    ports = {layer: StubPort(layer, LayerScript()) for layer in CompositionLayer}

    with pytest.raises(TypeError):
        FiveLayerCacheComposition(  # type: ignore[call-arg]
            binding=CompositionRuntimeBinding(TENANT, PROJECT, PRINCIPAL),
            serving_boundary=make_boundary(make_signer()),
            prompt_port=ports[CompositionLayer.PROMPT],
            context_port=ports[CompositionLayer.CONTEXT],
            action_port=ports[CompositionLayer.ACTION],
            environment_port=ports[CompositionLayer.ENVIRONMENT],
            fallback_executor=StubExecutor(),
            outcome_sink=StubSink(),
            rollback_latch=StubLatch(),
        )


def test_a_binding_that_is_not_the_closed_type_is_refused() -> None:
    ports = {layer: StubPort(layer, LayerScript()) for layer in CompositionLayer}

    with pytest.raises(ContractViolation) as excinfo:
        FiveLayerCacheComposition(
            binding=cast(CompositionRuntimeBinding, TENANT),
            serving_boundary=make_boundary(make_signer()),
            prompt_port=ports[CompositionLayer.PROMPT],
            context_port=ports[CompositionLayer.CONTEXT],
            action_port=ports[CompositionLayer.ACTION],
            environment_port=ports[CompositionLayer.ENVIRONMENT],
            affinity_port=ports[CompositionLayer.AFFINITY],
            fallback_executor=StubExecutor(),
            outcome_sink=StubSink(),
            rollback_latch=StubLatch(),
        )

    assert "binding has an invalid type" in str(excinfo.value)


def test_a_fallback_executor_returning_an_unknown_type_aborts_the_composition() -> None:
    harness = build_harness(executor=StubExecutor(wrong_type=True))

    with pytest.raises(ContractViolation) as excinfo:
        harness.run()

    assert "unknown result type" in str(excinfo.value)
    assert "FALLBACK_EXECUTION_CONTRACT_INVALID" in harness.latch.reasons
    assert harness.sink.calls == 1


def test_a_fallback_executor_that_skips_unrestored_work_aborts_the_composition() -> None:
    executor = UnderPerformingExecutor()
    harness = build_harness(executor=cast(StubExecutor, executor))

    with pytest.raises(ContractViolation) as excinfo:
        harness.run()

    assert "every layer work item not restored" in str(excinfo.value)
    assert "FALLBACK_WORK_PARTITION_INVALID" in harness.latch.reasons


def test_a_fallback_executor_that_crashes_propagates_after_recording_the_outcome() -> None:
    harness = build_harness(executor=StubExecutor(raises=True))

    with pytest.raises(RuntimeError):
        harness.run()

    assert "FALLBACK_EXECUTION_RUNTIME_FAILED" in harness.latch.reasons
    assert harness.sink.calls == 1
    assert harness.sink.events[-1].phase is CompositionPhase.FALLBACK
    assert harness.sink.events[-1].status is CompositionStatus.ERROR


def test_a_failed_fallback_populates_nothing() -> None:
    harness = build_harness(executor=StubExecutor(succeeds=False))

    result = harness.run()

    assert result.fallback_executed is True
    assert result.fallback_result is not None
    assert result.fallback_result.success is False
    assert result.populations == ()
    assert "FALLBACK_EXECUTION_FAILED" in harness.latch.reasons
    for layer in CompositionLayer:
        assert harness.port_calls()[layer] == ["lookup"]


@pytest.mark.parametrize("layer", list(CompositionLayer))
def test_a_lookup_that_reports_an_error_latches_a_rollback(layer: CompositionLayer) -> None:
    harness = build_harness(scripts={layer: LayerScript(disposition=LookupDisposition.ERROR)})

    result = harness.run()

    assert_execution_happened(result, harness)
    assert "CACHE_LOOKUP_REPORTED_ERROR" in harness.latch.reasons


def test_a_bypassing_layer_never_degrades_the_composition_to_fewer_layers() -> None:
    harness = build_harness(
        scripts={layer: LayerScript(disposition=LookupDisposition.BYPASS) for layer in CompositionLayer}
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert result.fallback_result is not None
    assert set(result.fallback_result.performed_work) == set(LayerWork)
    assert {item.layer for item in result.populations} == set(CompositionLayer)
    assert harness.latch.reasons == []


def test_a_deadline_that_expires_before_restore_bypasses_the_restore() -> None:
    harness = build_harness(
        scripts=hit_scripts(CompositionLayer),
        monotonic=ThresholdClock(trips_after=2),
    )

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.port_calls()[CompositionLayer.ACTION] == ["lookup"]
    assert harness.reasons(CompositionPhase.RESTORE) == ["CACHE_DEADLINE_EXCEEDED"]
    assert result.restored == ()


def test_a_deadline_that_expires_during_population_discards_the_population() -> None:
    harness = build_harness(monotonic=ThresholdClock(trips_after=11))

    result = harness.run()

    assert_execution_happened(result, harness)
    assert harness.port_calls()[CompositionLayer.ACTION] == ["lookup", "populate"]
    assert harness.reasons(CompositionPhase.POPULATE)[0] == "POPULATE_DEADLINE_EXCEEDED"
    assert "CACHE_POPULATE_DEADLINE_EXCEEDED" in harness.latch.reasons
    assert result.populations == ()


# ---------------------------------------------------------------------------
# 6b. the closed types refuse every malformed value they can be handed
# ---------------------------------------------------------------------------

BINDING = make_request().binding_digest


CONTRACT_CASES: list[tuple[str, Callable[[], object], str]] = [
    (
        "request-id-not-an-identifier",
        lambda: make_request(request_id="request 0001"),
        "request_id must be a bounded identifier",
    ),
    (
        "grant-layer-not-closed",
        lambda: VerifiedServingGrant(
            "request-0001", TENANT, PROJECT, PRINCIPAL, AUTHORIZATION, COMPATIBILITY,
            cast(CompositionLayer, "ACTION"), ServingAction.LOOKUP, RECEIPT, True,
        ),
        "serving grant uses an unknown layer",
    ),
    (
        "grant-action-not-closed",
        lambda: VerifiedServingGrant(
            "request-0001", TENANT, PROJECT, PRINCIPAL, AUTHORIZATION, COMPATIBILITY,
            CompositionLayer.ACTION, cast(ServingAction, "LOOKUP"), RECEIPT, True,
        ),
        "serving grant uses an unknown action",
    ),
    (
        "grant-allowed-not-boolean",
        lambda: VerifiedServingGrant(
            "request-0001", TENANT, PROJECT, PRINCIPAL, AUTHORIZATION, COMPATIBILITY,
            CompositionLayer.ACTION, ServingAction.LOOKUP, RECEIPT, cast(bool, 1),
        ),
        "serving grant allowed must be boolean",
    ),
    (
        "statement-layer-not-closed",
        lambda: make_statement(
            actions=cast(
                "Mapping[CompositionLayer, Sequence[ServingAction]]",
                {"ACTION": (ServingAction.LOOKUP,)},
            )
        ),
        "serving boundary contains an unknown layer",
    ),
    (
        "lookup-layer-not-closed",
        lambda: LayerLookup(
            cast(CompositionLayer, "ACTION"), BINDING, LookupDisposition.MISS, "COLD_MISS"
        ),
        "lookup uses an unknown layer",
    ),
    (
        "lookup-disposition-not-closed",
        lambda: LayerLookup(
            CompositionLayer.ACTION, BINDING, cast(LookupDisposition, "MISS"), "COLD_MISS"
        ),
        "lookup uses an unknown disposition",
    ),
    (
        "lookup-verified-not-boolean",
        lambda: LayerLookup(
            CompositionLayer.ACTION, BINDING, LookupDisposition.MISS, "COLD_MISS",
            verified=cast(bool, 1),
        ),
        "verified must be boolean",
    ),
    (
        "hit-without-material",
        lambda: LayerLookup(
            CompositionLayer.ACTION, BINDING, LookupDisposition.HIT, "WARM_MATERIAL",
            verified=True, compatible=True, exact_action_result=True,
        ),
        "cache hit must identify immutable material",
    ),
    (
        "miss-carrying-material",
        lambda: LayerLookup(
            CompositionLayer.ACTION, BINDING, LookupDisposition.MISS, "COLD_MISS",
            material_digest=MATERIAL,
        ),
        "non-hit lookup cannot return reusable material",
    ),
    (
        "restore-layer-not-closed",
        lambda: LayerRestore(
            cast(CompositionLayer, "ACTION"), BINDING, MATERIAL,
            LayerWork.ACTION_EXECUTION, True, "RESTORED", RECEIPT,
        ),
        "restore uses an unknown layer",
    ),
    (
        "restore-of-another-layers-work",
        lambda: LayerRestore(
            CompositionLayer.ACTION, BINDING, MATERIAL,
            LayerWork.PROMPT_PREFIX, True, "RESTORED", RECEIPT,
        ),
        "restore may save only its corresponding layer work",
    ),
    (
        "restore-success-not-boolean",
        lambda: LayerRestore(
            CompositionLayer.ACTION, BINDING, MATERIAL,
            LayerWork.ACTION_EXECUTION, cast(bool, 1), "RESTORED", RECEIPT,
        ),
        "restore success must be boolean",
    ),
    (
        "restore-success-without-receipt",
        lambda: LayerRestore(
            CompositionLayer.ACTION, BINDING, MATERIAL, LayerWork.ACTION_EXECUTION, True, "RESTORED"
        ),
        "successful restore requires an immutable receipt",
    ),
    (
        "restore-failure-with-receipt",
        lambda: LayerRestore(
            CompositionLayer.ACTION, BINDING, MATERIAL,
            LayerWork.ACTION_EXECUTION, False, "MATERIAL_UNAVAILABLE", RECEIPT,
        ),
        "failed restore cannot return a success receipt",
    ),
    (
        "fallback-success-not-boolean",
        lambda: FallbackExecutionResult(cast(bool, 1), "EXECUTED", (), EXECUTION),
        "fallback success must be boolean",
    ),
    (
        "fallback-work-not-closed",
        lambda: FallbackExecutionResult(
            True, "EXECUTED", cast("tuple[LayerWork, ...]", ("ACTION_EXECUTION",)), EXECUTION
        ),
        "fallback performed_work uses an unknown value",
    ),
    (
        "fallback-work-duplicated",
        lambda: FallbackExecutionResult(
            True, "EXECUTED", (LayerWork.ACTION_EXECUTION, LayerWork.ACTION_EXECUTION), EXECUTION
        ),
        "fallback performed_work contains duplicates",
    ),
    (
        "fallback-success-without-digest",
        lambda: FallbackExecutionResult(True, "EXECUTED", (LayerWork.ACTION_EXECUTION,)),
        "successful fallback requires an execution digest",
    ),
    (
        "population-layer-not-closed",
        lambda: LayerPopulation(
            cast(CompositionLayer, "ACTION"), BINDING,
            LayerWork.ACTION_EXECUTION, True, "POPULATED", ARTIFACT,
        ),
        "population uses an unknown layer",
    ),
    (
        "population-of-another-layers-work",
        lambda: LayerPopulation(
            CompositionLayer.ACTION, BINDING, LayerWork.PROMPT_PREFIX, True, "POPULATED", ARTIFACT
        ),
        "population may write only its corresponding layer work",
    ),
    (
        "population-success-not-boolean",
        lambda: LayerPopulation(
            CompositionLayer.ACTION, BINDING,
            LayerWork.ACTION_EXECUTION, cast(bool, 1), "POPULATED", ARTIFACT,
        ),
        "population success must be boolean",
    ),
    (
        "population-success-without-artifact",
        lambda: LayerPopulation(
            CompositionLayer.ACTION, BINDING, LayerWork.ACTION_EXECUTION, True, "POPULATED"
        ),
        "successful population requires an artifact digest",
    ),
    (
        "population-failure-with-artifact",
        lambda: LayerPopulation(
            CompositionLayer.ACTION, BINDING,
            LayerWork.ACTION_EXECUTION, False, "QUOTA_EXCEEDED", ARTIFACT,
        ),
        "failed population cannot return an artifact digest",
    ),
    (
        "event-phase-not-closed",
        lambda: CompositionOutcomeEvent(
            RECEIPT, "request-0001", BINDING,
            cast(CompositionPhase, "REQUEST"), CompositionStatus.SUCCESS, "BOUND_SCOPE_ACCEPTED",
        ),
        "outcome event uses an unknown phase",
    ),
    (
        "event-status-not-closed",
        lambda: CompositionOutcomeEvent(
            RECEIPT, "request-0001", BINDING,
            CompositionPhase.REQUEST, cast(CompositionStatus, "SUCCESS"), "BOUND_SCOPE_ACCEPTED",
        ),
        "outcome event uses an unknown status",
    ),
    (
        "event-layer-not-closed",
        lambda: CompositionOutcomeEvent(
            RECEIPT, "request-0001", BINDING,
            CompositionPhase.REQUEST, CompositionStatus.SUCCESS, "BOUND_SCOPE_ACCEPTED",
            layer=cast(CompositionLayer, "ACTION"),
        ),
        "outcome event uses an unknown layer",
    ),
    (
        "edge-relation-not-closed",
        lambda: MissCausalEdge(RECEIPT, ARTIFACT, cast(CausalRelation, "REQUESTED")),
        "causal edge uses an unknown relation",
    ),
    (
        "result-persisted-not-boolean",
        lambda: CompositionResult(
            "request-0001", BINDING, True, False, None, (), (), (), (), cast(bool, 1)
        ),
        "outcome_persisted must be boolean",
    ),
]


@pytest.mark.parametrize(
    ("factory", "message"),
    [pytest.param(factory, message, id=name) for name, factory, message in CONTRACT_CASES],
)
def test_the_closed_types_refuse_malformed_values(
    factory: Callable[[], object], message: str
) -> None:
    with pytest.raises(ContractViolation) as excinfo:
        factory()

    assert message in str(excinfo.value)


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(
            lambda: LayerLookup(
                CompositionLayer.ACTION, "not-a-digest", LookupDisposition.MISS, "COLD_MISS"
            ),
            id="lookup-binding-digest",
        ),
        pytest.param(
            lambda: CompositionRuntimeBinding(TENANT, PROJECT, "not-a-digest"),
            id="binding-principal-digest",
        ),
        pytest.param(
            lambda: FallbackExecutionResult(False, "FAILED", (), "not-a-digest"),
            id="fallback-execution-digest",
        ),
    ],
)
def test_the_closed_types_refuse_malformed_digests(factory: Callable[[], object]) -> None:
    with pytest.raises(DigestMismatch):
        factory()


def test_a_failed_fallback_may_still_carry_a_well_formed_execution_digest() -> None:
    result = FallbackExecutionResult(False, "COMPILATION_FAILED", (), EXECUTION)

    assert result.success is False
    assert result.execution_digest == EXECUTION
    assert result.performed_work == ()


# ---------------------------------------------------------------------------
# 4b. the invariant as a property: no Action-layer defect may ever skip execution
# ---------------------------------------------------------------------------

CORRUPT_ACTION_SCRIPTS: dict[str, LayerScript] = {
    "cold-miss": LayerScript(hit=False),
    "port-bypass": LayerScript(disposition=LookupDisposition.BYPASS),
    "port-error": LayerScript(disposition=LookupDisposition.ERROR),
    "lookup-raises": LayerScript(hit=True, lookup_raises=True),
    "lookup-returns-nothing": LayerScript(hit=True, lookup_returns_none=True),
    "lookup-wrong-layer": LayerScript(hit=True, lookup_wrong_layer=True),
    "unverified-material": LayerScript(hit=True, verified=False),
    "incompatible-material": LayerScript(hit=True, compatible=False),
    "foreign-trust-namespace": LayerScript(hit=True, foreign_namespace=True),
    "not-an-exact-result": LayerScript(hit=True, claims_exact=False),
    "restore-raises": LayerScript(hit=True, restore_raises=True),
    "restore-returns-nothing": LayerScript(hit=True, restore_returns_none=True),
    "restore-reports-failure": LayerScript(hit=True, restore_succeeds=False),
    "restore-returns-other-material": LayerScript(hit=True, restore_drifts=True),
}


@pytest.mark.parametrize(
    "script",
    [pytest.param(script, id=name) for name, script in CORRUPT_ACTION_SCRIPTS.items()],
)
def test_no_defective_action_entry_can_skip_execution_even_with_every_other_layer_hot(
    script: LayerScript,
) -> None:
    scripts = hit_scripts(NON_ACTION_LAYERS)
    scripts[CompositionLayer.ACTION] = script
    harness = build_harness(scripts=scripts)

    result = harness.run()

    assert_execution_happened(result, harness)
    assert CompositionLayer.ACTION not in {item.layer for item in result.restored}
    completions = [event for event in result.events if event.phase is CompositionPhase.COMPLETE]
    assert completions == []
