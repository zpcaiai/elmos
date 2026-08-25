"""BC-14 wiring: the signed five-layer composition reached through real routes.

``test_parity_composition.py`` proves the composition itself.  This file proves
the *wiring*: that a default control plane is untouched by it, that a wired one
routes the skip decision through ``CompositionResult.exact_action_reused`` and
nothing else, and that every refusal the composition can raise leaves the HTTP
seam as a typed error rather than a traceback.

Everything here drives real entry points — ``CacheControlPlane.handle`` with a
real ``ActionCache``, a real ``ParityMetadataRepository`` and a real Ed25519
receipt.  The only deliberately fake objects are the ones a *deployment* is
meant to supply through the wiring seam (a broken port, a broken executor, a
repository whose writes fail), which is exactly what those seams are for.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.action_cache import (
    ActionCache,
    CommitRequest,
    LookupResult,
    MissReason,
)
from elmos_build_cache.api import (
    COMPOSITION_OUTCOME_HEADER,
    COMPOSITION_REQUEST_ID_HEADER,
    CacheControlPlane,
    Request,
)
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import (
    CacheParityConfig,
    EnvironmentSnapshotConfig,
)
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import CacheMode, TrustNamespace, ValidationLevel
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.manifests import ActionResultManifest, ExecutionMetrics
from elmos_build_cache.parity_composition import (
    SERVING_BOUNDARY_KIND,
    CompositionLayer,
    CompositionRequest,
    FallbackExecutionResult,
    LayerLookup,
    LayerPopulation,
    LayerRestore,
    LayerWork,
    LookupDisposition,
    ServingAction,
    SignedServingBoundary,
    serving_boundary_statement,
)
from elmos_build_cache.parity_composition_wiring import (
    ActionCacheLayerProbe,
    LayerProbe,
    LayerProbeFn,
    ScopedCacheLayerPort,
    ServingCompositionWiring,
)
from elmos_build_cache.parity_runtime import (
    SERVING_GATE_KIND,
    ParityRuntime,
    serving_gate_statement,
)
from elmos_build_cache.parity_store import ParityMetadataRepository
from elmos_build_cache.security import Ed25519ProvenanceSigner

ACTION_KEY = digest("7")
PRINCIPAL = digest("9")
AUTHORIZATION = digest("a")
COMPATIBILITY = digest("b")
FOREIGN_BINDING = digest("c")
MATERIAL = digest("d")
EVERY_LAYER = tuple(CompositionLayer)
READ_ONLY = (ServingAction.LOOKUP, ServingAction.RESTORE)


# ---------------------------------------------------------------------------
# deployment-supplied collaborators (the wiring seam's own extension points)
# ---------------------------------------------------------------------------


class ServingControl:
    """Observable serving control, so a rollback latch is visible to a test."""

    def __init__(self) -> None:
        self.enabled = True
        self.rollback_reasons: list[str] = []

    def is_serving(self) -> bool:
        return self.enabled

    def latch_rollback(self, reason_code: str) -> None:
        self.rollback_reasons.append(reason_code)
        self.enabled = False


class MonotonicSteps:
    """Deterministic monotonic clock: never expires within a test."""

    def __init__(self, step: float = 0.001) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


class UnstampedContextPort:
    """A deliberately broken adapter that forgets ``request.binding_digest``.

    Binding-stamp drift is layer-agnostic, and the Action layer can no longer be
    overridden at all (``ServingCompositionWiring`` refuses it), so this proves
    the seam on the Context layer.
    """

    @property
    def layer(self) -> CompositionLayer:
        return CompositionLayer.CONTEXT

    def lookup(
        self,
        request: CompositionRequest,
        deadline_monotonic: float,
    ) -> LayerLookup:
        del request, deadline_monotonic
        return LayerLookup(
            layer=CompositionLayer.CONTEXT,
            binding_digest=FOREIGN_BINDING,
            disposition=LookupDisposition.HIT,
            reason_code="LAYER_MATERIAL_AVAILABLE",
            material_digest=MATERIAL,
            verified=True,
            compatible=True,
        )

    def restore(
        self,
        request: CompositionRequest,
        lookup: LayerLookup,
        deadline_monotonic: float,
    ) -> LayerRestore:
        del deadline_monotonic
        return LayerRestore(
            layer=CompositionLayer.CONTEXT,
            binding_digest=FOREIGN_BINDING,
            material_digest=str(lookup.material_digest),
            work=LayerWork.CONTEXT_REHYDRATION,
            success=True,
            reason_code="LAYER_MATERIAL_CONFIRMED",
            receipt_digest=digest("e"),
        )

    def populate(
        self,
        request: CompositionRequest,
        execution: FallbackExecutionResult,
        deadline_monotonic: float,
    ) -> LayerPopulation:
        del request, execution, deadline_monotonic
        raise AssertionError("a refused lookup must never reach population")


class UnboundHotActionPort:
    """An Action port that reports an exact reuse with no cache behind it.

    This is the shape the wiring seam used to accept: a ``layer_ports[ACTION]``
    entry replaces the whole port, so the request's own ``ActionCacheLayerProbe``
    is discarded and ``exact_action_reused`` stops meaning anything about the
    Action Cache.  It stamps the binding correctly, so nothing downstream in the
    composition objects — the refusal has to happen at construction.
    """

    @property
    def layer(self) -> CompositionLayer:
        return CompositionLayer.ACTION

    def lookup(
        self,
        request: CompositionRequest,
        deadline_monotonic: float,
    ) -> LayerLookup:
        del deadline_monotonic
        return LayerLookup(
            layer=CompositionLayer.ACTION,
            binding_digest=request.binding_digest,
            disposition=LookupDisposition.HIT,
            reason_code="EXACT_RESULT_AVAILABLE",
            material_digest=MATERIAL,
            verified=True,
            compatible=True,
            exact_action_result=True,
        )

    def restore(
        self,
        request: CompositionRequest,
        lookup: LayerLookup,
        deadline_monotonic: float,
    ) -> LayerRestore:
        del deadline_monotonic
        return LayerRestore(
            layer=CompositionLayer.ACTION,
            binding_digest=request.binding_digest,
            material_digest=str(lookup.material_digest),
            work=LayerWork.ACTION_EXECUTION,
            success=True,
            reason_code="LAYER_MATERIAL_CONFIRMED",
            receipt_digest=digest("e"),
        )

    def populate(
        self,
        request: CompositionRequest,
        execution: FallbackExecutionResult,
        deadline_monotonic: float,
    ) -> LayerPopulation:
        del request, execution, deadline_monotonic
        raise AssertionError("an exact reuse must never reach population")


class CrashingExecutor:
    def __init__(self, operation: Callable[[], Any]) -> None:
        del operation

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult:
        del request, restored, cache_deadline_monotonic
        raise RuntimeError("stage execution path exploded")


class WrongTypeExecutor:
    def __init__(self, operation: Callable[[], Any]) -> None:
        del operation

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> Any:
        del request, restored, cache_deadline_monotonic
        return {"success": True}


class UnderPerformingExecutor:
    """Claims success while skipping work no layer restored."""

    def __init__(self, operation: Callable[[], Any]) -> None:
        del operation

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[LayerRestore, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult:
        del request, restored, cache_deadline_monotonic
        return FallbackExecutionResult(
            success=True,
            reason_code="PARTIAL_EXECUTION",
            performed_work=(LayerWork.ACTION_EXECUTION,),
            execution_digest=digest("f"),
        )


class BrokenOutcomeRepository:
    """A real repository whose outcome writes fail, wrapping a real one."""

    def __init__(self, delegate: ParityMetadataRepository) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        del tenant_id, project_id, request_id, event_id, document
        raise OSError("outcome store is unavailable")


# ---------------------------------------------------------------------------
# construction helpers
# ---------------------------------------------------------------------------


def commit_hot_action(
    action_cache: ActionCache,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    *,
    payload: bytes = b"generated output",
) -> str:
    output = cas.put_bytes(payload)
    manifest = ActionResultManifest(
        action_key=ACTION_KEY,
        stage_id="target-code-generation",
        stage_version="1.0.0",
        output_artifacts=(output,),
        required_outputs=(output,),
        metrics=ExecutionMetrics(wall_ms=5000, cpu_ms=4200, compiler_ms=900, model_tokens=12000),
    )
    with store.transaction():
        store.register_artifact(
            TENANT,
            output,
            size_bytes=len(payload),
            media_type="application/octet-stream",
            artifact_kind="stage-output",
            validation_level=ValidationLevel.TEST_VERIFIED,
        )
        action_cache.commit(
            CommitRequest(
                tenant_id=TENANT,
                action_key=ACTION_KEY,
                manifest=manifest,
                trust_namespace=TrustNamespace.BRANCH,
                validation_level=ValidationLevel.TEST_VERIFIED,
                producer_identity="worker-1",
            )
        )
    return output


def make_boundary(
    signer: Ed25519ProvenanceSigner,
    *,
    actions: Mapping[CompositionLayer, Sequence[ServingAction]] | None = None,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    principal_digest: str = PRINCIPAL,
) -> SignedServingBoundary:
    statement = serving_boundary_statement(
        tenant_id=tenant_id,
        project_id=project_id,
        principal_digest=principal_digest,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        actions=actions or {layer: READ_ONLY for layer in EVERY_LAYER},
        issued_at=0.0,
        expires_at=10**9,
    )
    receipt = signer.sign_statement(SERVING_BOUNDARY_KIND, statement)
    return SignedServingBoundary(receipt, signer, wall_clock=lambda: 1_000.0)


def make_wiring(
    signer: Ed25519ProvenanceSigner,
    **overrides: Any,
) -> ServingCompositionWiring:
    boundary = overrides.pop("serving_boundary", None) or make_boundary(signer)
    return ServingCompositionWiring(
        serving_boundary=boundary,
        monotonic=overrides.pop("monotonic", MonotonicSteps()),
        **overrides,
    )


def make_runtime(
    clock: ManualClock,
    control: ServingControl,
    sink: Any,
    *,
    serving: bool = False,
) -> ParityRuntime:
    """A real ``ParityRuntime``: the plane's rollback latch and serving gate."""

    if not serving:
        return ParityRuntime(
            CacheParityConfig(),
            TENANT,
            PROJECT,
            clock=clock,
            serving_controls={"environment_snapshot": control},
        )
    config = replace(
        CacheParityConfig(),
        rollout_phase="internal",
        environment_snapshots=replace(EnvironmentSnapshotConfig(), enabled=True),
    )
    gate_signer = Ed25519ProvenanceSigner.generate("composition-wiring-gate")
    statement = serving_gate_statement(
        config,
        TENANT,
        PROJECT,
        ("environment_snapshot",),
        issued_at=clock.now(),
        expires_at=clock.now() + 3_600,
    )
    return ParityRuntime(
        config,
        TENANT,
        PROJECT,
        sink=sink,
        clock=clock,
        serving_controls={"environment_snapshot": control},
        serving_gate_receipt=gate_signer.sign_statement(SERVING_GATE_KIND, statement),
        serving_gate_verifier=Ed25519ProvenanceSigner.verifier(gate_signer.public_keyset()),
    )


def build_plane(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    *,
    wiring: ServingCompositionWiring | None,
    control: ServingControl | None = None,
    repository: Any | None = None,
    serving: bool = False,
) -> CacheControlPlane:
    resolved_control = control if control is not None else ServingControl()
    resolved_repository = (
        repository if repository is not None else ParityMetadataRepository(store)
    )
    return CacheControlPlane(
        store,
        cas,
        TENANT,
        action_cache=action_cache,
        clock=clock,
        parity_repository=resolved_repository,
        serving_authorizer=(
            None
            if wiring is None
            else make_runtime(clock, resolved_control, resolved_repository, serving=serving)
        ),
        serving_composition=wiring,
    )


def action_lookup(plane: CacheControlPlane, *, request_id: str = "req-wiring-1") -> Any:
    return plane.handle(
        Request(
            "GET",
            f"/cache/actions/{ACTION_KEY.removeprefix('sha256:')}",
            headers={COMPOSITION_REQUEST_ID_HEADER: request_id},
            query={"minimumValidation": "TEST_VERIFIED"},
            authenticated_principal_digest=PRINCIPAL,
        )
    )


def hot_probe(material: str) -> LayerProbeFn:
    def probe(request: CompositionRequest) -> LayerProbe:
        del request
        return LayerProbe.hit(material, reason_code="LAYER_MATERIAL_AVAILABLE")

    return probe


@pytest.fixture
def signer() -> Ed25519ProvenanceSigner:
    return Ed25519ProvenanceSigner.generate("cache-parity-serving")


# ---------------------------------------------------------------------------
# 1. default (unwired) control plane is untouched
# ---------------------------------------------------------------------------


def test_an_unwired_plane_answers_a_hot_action_lookup_exactly_as_before(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
) -> None:
    output = commit_hot_action(action_cache, store, cas)
    plane = build_plane(store, cas, clock, action_cache, wiring=None)

    response = action_lookup(plane)

    assert response.status == 200
    body = response.json()
    assert body["hit"] is True
    assert body["action_key"] == ACTION_KEY
    assert body["result"] is not None
    assert body["result"]["output_artifacts"] == [output]
    assert body["validation_level"] == str(ValidationLevel.TEST_VERIFIED)
    assert response.headers is not None
    assert COMPOSITION_OUTCOME_HEADER not in response.headers


def test_an_unwired_plane_answers_a_cold_action_lookup_exactly_as_before(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
) -> None:
    plane = build_plane(store, cas, clock, action_cache, wiring=None)

    response = action_lookup(plane)

    assert response.status == 404
    body = response.json()
    assert body["hit"] is False
    assert body["miss_reasons"] == ["NO_ENTRY"]
    assert "composition" not in body["detail"]
    assert response.headers is not None
    assert COMPOSITION_OUTCOME_HEADER not in response.headers


def test_an_unwired_plane_still_refuses_the_serving_routes_as_not_wired(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
) -> None:
    plane = build_plane(store, cas, clock, action_cache, wiring=None)

    response = plane.handle(
        Request(
            "GET",
            f"/cache/environments/{digest('3').removeprefix('sha256:')}",
            query={"projectId": PROJECT, "trustNamespace": "branch"},
            authenticated_principal_digest=PRINCIPAL,
        )
    )

    assert response.status == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert response.json()["details"]["state"] == "NOT_WIRED"


def test_a_plane_without_a_rollback_latch_never_reaches_the_composition(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """A partially wired plane is an unwired plane, not a half-composed one."""

    commit_hot_action(action_cache, store, cas)
    plane = CacheControlPlane(
        store,
        cas,
        TENANT,
        action_cache=action_cache,
        clock=clock,
        parity_repository=ParityMetadataRepository(store),
        serving_authorizer=None,
        serving_composition=make_wiring(signer),
    )

    response = action_lookup(plane)

    assert response.status == 200
    assert response.headers is not None
    assert COMPOSITION_OUTCOME_HEADER not in response.headers


# ---------------------------------------------------------------------------
# 2. wired: only an exact Action reuse may skip execution
# ---------------------------------------------------------------------------


def test_a_hot_action_layer_skips_execution_through_the_composed_route(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    output = commit_hot_action(action_cache, store, cas)
    plane = build_plane(store, cas, clock, action_cache, wiring=make_wiring(signer))

    response = action_lookup(plane)

    assert response.status == 200
    assert response.json()["result"]["output_artifacts"] == [output]
    assert response.headers is not None
    assert response.headers[COMPOSITION_OUTCOME_HEADER] == "true"


def test_a_cold_action_layer_still_requires_execution_through_the_composed_route(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    plane = build_plane(store, cas, clock, action_cache, wiring=make_wiring(signer))

    response = action_lookup(plane)

    assert response.status == 404
    assert response.json()["hit"] is False
    assert response.headers is not None
    assert response.headers[COMPOSITION_OUTCOME_HEADER] == "true"


@pytest.mark.parametrize(
    "hot",
    [
        (CompositionLayer.PROMPT,),
        (CompositionLayer.CONTEXT,),
        (CompositionLayer.ENVIRONMENT,),
        (CompositionLayer.AFFINITY,),
        (CompositionLayer.PROMPT, CompositionLayer.CONTEXT),
        (
            CompositionLayer.PROMPT,
            CompositionLayer.CONTEXT,
            CompositionLayer.ENVIRONMENT,
            CompositionLayer.AFFINITY,
        ),
    ],
)
def test_no_combination_of_non_action_hits_can_serve_an_action_lookup(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
    hot: tuple[CompositionLayer, ...],
) -> None:
    wiring = make_wiring(
        signer,
        layer_probes={layer: hot_probe(MATERIAL) for layer in hot},
    )
    plane = build_plane(store, cas, clock, action_cache, wiring=wiring)

    response = action_lookup(plane)

    assert response.status == 404
    assert response.json()["hit"] is False


def test_a_hot_entry_the_boundary_does_not_authorize_is_reported_as_a_miss(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """The composed skip set is a strict subset of the unwired one."""

    commit_hot_action(action_cache, store, cas)
    boundary = make_boundary(signer, actions={CompositionLayer.PROMPT: READ_ONLY})
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer, serving_boundary=boundary),
    )

    response = action_lookup(plane)

    assert response.status == 404
    assert response.json()["detail"]["composition"] == "COMPOSITION_REFUSED_EXACT_ACTION_REUSE"


def test_a_receipt_for_another_principal_cannot_serve_a_hot_entry(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    commit_hot_action(action_cache, store, cas)
    boundary = make_boundary(signer, principal_digest=digest("1"))
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer, serving_boundary=boundary),
    )

    response = action_lookup(plane)

    assert response.status == 404


def test_a_composed_route_without_an_authenticated_principal_fails_closed(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    commit_hot_action(action_cache, store, cas)
    plane = build_plane(store, cas, clock, action_cache, wiring=make_wiring(signer))

    response = plane.handle(
        Request("GET", f"/cache/actions/{ACTION_KEY.removeprefix('sha256:')}")
    )

    assert response.status == 403
    assert response.json()["details"]["state"] == "NO_AUTHENTICATED_PRINCIPAL"


def test_a_wiring_may_not_replace_the_action_layer_port(
    signer: Ed25519ProvenanceSigner,
) -> None:
    """The reported 200-with-null-result no longer even builds.

    ``layer_ports[ACTION]`` replaced the whole port, discarding the request's
    own ``ActionCacheLayerProbe``, so ``exact_action_reused`` had no causal link
    left to the Action Cache: a cold cache with nothing ever committed answered
    ``200 {"hit": true, "result": null}``.  The Action layer is the only one
    whose lookup may skip execution, so its port is not a deployment extension
    point; a wiring that claims it is refused at construction.
    """

    with pytest.raises(ContractViolation) as refusal:
        make_wiring(
            signer,
            layer_ports={CompositionLayer.ACTION: UnboundHotActionPort()},
        )

    assert refusal.value.details["layer"] == CompositionLayer.ACTION.value
    assert refusal.value.http_status == 422


@pytest.mark.parametrize("layer", [layer for layer in EVERY_LAYER if layer is not CompositionLayer.ACTION])
def test_every_other_layer_port_remains_a_deployment_extension_point(
    signer: Ed25519ProvenanceSigner,
    layer: CompositionLayer,
) -> None:
    """Only ACTION is closed: no other layer's lookup can skip execution."""

    wiring = make_wiring(signer, layer_ports={layer: UnstampedContextPort()})

    assert layer in wiring.layer_ports


def test_a_composed_action_lookup_never_serves_a_result_the_cache_did_not_produce(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """Serving requires ``reused AND result.hit``, enforced not inferred.

    The wiring refusal above closes the one configuration that reached this
    state through a route, which leaves the seam itself with no end-to-end
    caller — exactly the shape of guard this session found untested elsewhere.
    So drive the seam directly, with a real plane and the real ``LookupResult``
    a real cold ``ActionCache`` returns: the 200 body is built entirely from
    that result, so ``reused`` alone must never be allowed to open it.
    """

    plane = build_plane(store, cas, clock, action_cache, wiring=make_wiring(signer))
    probe = ActionCacheLayerProbe(
        action_cache,
        tenant_id=TENANT,
        action_key=ACTION_KEY,
        trust_namespace=TrustNamespace.BRANCH,
        minimum_validation=ValidationLevel.TEST_VERIFIED,
        mode=CacheMode.READ_WRITE,
    )
    cold = probe.lookup()
    assert cold.hit is False
    assert cold.result is None

    refused = plane._action_lookup_response(ACTION_KEY, cold, reused=True)

    assert refused.status == 404
    body = refused.json()
    assert body["hit"] is False
    assert body["detail"]["composition"] == "COMPOSITION_CLAIMED_UNBACKED_EXACT_ACTION_REUSE"

    # The unwired plane's answer for the same cold lookup, so the subset
    # property is read off the two responses rather than asserted about one.
    unwired = plane._action_lookup_response(ACTION_KEY, cold, reused=None)
    assert unwired.status == 404
    assert unwired.json()["miss_reasons"] == body["miss_reasons"]


def test_a_composed_action_lookup_still_serves_a_result_the_cache_did_produce(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """The conjunction subtracts nothing from a genuine hit."""

    output = commit_hot_action(action_cache, store, cas)
    plane = build_plane(store, cas, clock, action_cache, wiring=make_wiring(signer))

    response = action_lookup(plane)

    assert response.status == 200
    body = response.json()
    assert body["result"] is not None
    assert body["result_manifest_digest"] is not None
    assert body["result"]["output_artifacts"] == [output]


# ---------------------------------------------------------------------------
# 3. every adapter stamps the request binding
# ---------------------------------------------------------------------------


def composition_request() -> CompositionRequest:
    return CompositionRequest(
        request_id="req-stamp-1",
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=digest("2"),
        cache_deadline_monotonic=10**6,
    )


@pytest.mark.parametrize("layer", EVERY_LAYER)
def test_every_adapter_stamps_the_request_binding_digest(layer: CompositionLayer) -> None:
    request = composition_request()
    port = ScopedCacheLayerPort(
        layer,
        probe=hot_probe(MATERIAL),
        writer=lambda _request, _execution: digest("4"),
    )

    lookup = port.lookup(request, request.cache_deadline_monotonic)
    restore = port.restore(request, lookup, request.cache_deadline_monotonic)
    population = port.populate(
        request,
        FallbackExecutionResult(True, "DONE", tuple(LayerWork), digest("6")),
        request.cache_deadline_monotonic,
    )

    assert lookup.binding_digest == request.binding_digest
    assert restore.binding_digest == request.binding_digest
    assert population.binding_digest == request.binding_digest


@pytest.mark.parametrize("layer", EVERY_LAYER)
def test_an_out_of_scope_layer_bypasses_and_is_still_stamped(
    layer: CompositionLayer,
) -> None:
    request = composition_request()

    lookup = ScopedCacheLayerPort(layer).lookup(request, request.cache_deadline_monotonic)

    assert lookup.disposition is LookupDisposition.BYPASS
    assert lookup.reason_code == "LAYER_OUT_OF_REQUEST_SCOPE"
    assert lookup.binding_digest == request.binding_digest


def test_an_adapter_that_does_not_stamp_the_binding_is_refused_as_scope_drift(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """A port that forgets ``request.binding_digest`` is refused and surfaced.

    The Action layer can no longer be overridden at all
    (``ServingCompositionWiring`` refuses it), so this proves the seam on the
    Context layer -- binding-stamp drift is layer-agnostic.

    The Action cache is left **cold** on purpose.  ``_LAYER_ORDER`` puts ACTION
    first and ``break``s the moment it restores, because it is the only layer
    that may replace execution; every later layer is then never consulted.  So a
    hot Action entry would hide the drift rather than prove it -- the assertion
    would pass on a request where the drifting port was never called.  A cold
    Action layer is what actually reaches CONTEXT.
    """

    action_cache = ActionCache(store, cas, clock=clock)
    control = ServingControl()
    wiring = make_wiring(
        signer,
        layer_ports={CompositionLayer.CONTEXT: UnstampedContextPort()},
    )
    plane = build_plane(store, cas, clock, action_cache, wiring=wiring, control=control)

    response = action_lookup(plane)

    # Nothing may be served: the drifting HIT is discarded, and the caller is
    # told to execute rather than handed material from a foreign binding.
    assert response.status == 404
    assert response.json()["hit"] is False
    assert control.rollback_reasons == ["CACHE_LOOKUP_SCOPE_DRIFT"]


def test_a_hot_action_entry_short_circuits_before_any_later_layer_is_consulted(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """The ACTION ``break`` in ``_LAYER_ORDER`` is load-bearing, so pin it.

    This is the companion to the drift test above: with a hot Action entry the
    same drifting Context port is never called, so no drift is latched.  That is
    correct -- but it is only correct because ACTION short-circuits, and nothing
    else in the suite says so.  If a refactor ever moved ACTION out of first
    position or dropped the ``break``, the drift test above would keep passing
    while this one would fail and name the reason.
    """

    output = commit_hot_action(action_cache, store, cas)
    control = ServingControl()
    wiring = make_wiring(
        signer,
        layer_ports={CompositionLayer.CONTEXT: UnstampedContextPort()},
    )
    plane = build_plane(store, cas, clock, action_cache, wiring=wiring, control=control)

    response = action_lookup(plane)

    assert response.status == 200
    assert response.json()["result"]["output_artifacts"] == [output]
    assert control.rollback_reasons == []


# ---------------------------------------------------------------------------
# 4. a failed outcome sink never reads as a successful audit trail
# ---------------------------------------------------------------------------


def test_a_failed_outcome_sink_is_not_reported_as_a_successful_audit_trail(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    commit_hot_action(action_cache, store, cas)
    control = ServingControl()
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer),
        control=control,
        repository=BrokenOutcomeRepository(ParityMetadataRepository(store)),
    )

    response = action_lookup(plane)

    assert response.status == 200
    assert response.headers is not None
    assert response.headers[COMPOSITION_OUTCOME_HEADER] == "false"
    assert control.rollback_reasons == ["CACHE_OUTCOME_PERSISTENCE_FAILED"]


def test_a_composed_route_writes_the_outcome_graph_the_explain_endpoint_reads(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    repository = ParityMetadataRepository(store)
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer),
        repository=repository,
    )

    response = action_lookup(plane, request_id="req-explain-1")
    assert response.status == 404

    stored = repository.list_cache_outcomes(TENANT, PROJECT, "req-explain-1")
    assert stored
    assert {document["layer"] for document in stored} <= {
        "PROMPT",
        "CONTEXT",
        "ACTION",
        "ENVIRONMENT",
        "COORDINATOR",
    }
    assert all(document["outcome"] != "HIT" for document in stored)

    explained = plane.handle(
        Request(
            "GET",
            "/cache/explain/req-explain-1",
            query={"projectId": PROJECT},
            authenticated_principal_digest=PRINCIPAL,
        )
    )
    assert explained.status == 200
    assert explained.json()["request_id"] == "req-explain-1"


# ---------------------------------------------------------------------------
# 5. the three exception escape paths are handled at the seam
# ---------------------------------------------------------------------------


def test_a_fallback_executor_that_crashes_does_not_leak_an_internal_exception(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    control = ServingControl()
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer, fallback_executor_factory=CrashingExecutor),
        control=control,
    )

    response = plane.handle(
        Request(
            "GET",
            f"/cache/actions/{ACTION_KEY.removeprefix('sha256:')}",
            authenticated_principal_digest=PRINCIPAL,
        )
    )

    assert response.status == 500
    body = response.json()
    assert body["code"] == "INTERNAL"
    assert body["message"] == "RuntimeError"
    assert "exploded" not in repr(body)
    assert control.rollback_reasons == ["FALLBACK_EXECUTION_RUNTIME_FAILED"]


def test_a_fallback_executor_returning_an_unknown_type_is_a_typed_refusal(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    control = ServingControl()
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer, fallback_executor_factory=WrongTypeExecutor),
        control=control,
    )

    response = plane.handle(
        Request(
            "GET",
            f"/cache/actions/{ACTION_KEY.removeprefix('sha256:')}",
            authenticated_principal_digest=PRINCIPAL,
        )
    )

    assert response.status == 422
    assert response.json()["code"] == "CONTRACT_VIOLATION"
    assert control.rollback_reasons == ["FALLBACK_EXECUTION_CONTRACT_INVALID"]


def test_a_fallback_executor_that_skips_unrestored_work_is_a_typed_refusal(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    control = ServingControl()
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer, fallback_executor_factory=UnderPerformingExecutor),
        control=control,
    )

    response = plane.handle(
        Request(
            "GET",
            f"/cache/actions/{ACTION_KEY.removeprefix('sha256:')}",
            authenticated_principal_digest=PRINCIPAL,
        )
    )

    assert response.status == 422
    assert response.json()["code"] == "CONTRACT_VIOLATION"
    assert control.rollback_reasons == ["FALLBACK_WORK_PARTITION_INVALID"]


# ---------------------------------------------------------------------------
# 6. the serving seam still executes its operation
# ---------------------------------------------------------------------------


def test_a_composed_serving_call_always_runs_its_operation(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """No Action probe is in scope on a serving route, so nothing may skip it.

    The environment snapshot does not exist, so the only way this can answer
    ``NOT_FOUND`` is if the real serving operation ran inside the composition —
    and it comes back as a typed engine error, not a traceback.
    """

    repository = ParityMetadataRepository(store)
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=make_wiring(signer),
        repository=repository,
        serving=True,
    )

    response = plane.handle(
        Request(
            "GET",
            f"/cache/environments/{digest('3').removeprefix('sha256:')}",
            headers={COMPOSITION_REQUEST_ID_HEADER: "req-serving-1"},
            query={
                "projectId": PROJECT,
                "trustNamespace": "branch",
                "transferMs": "10",
                "decompressionMs": "5",
                "verificationMs": "5",
                "rebuildMs": "900",
            },
            authenticated_principal_digest=PRINCIPAL,
        )
    )

    assert response.status < 500, response.json()
    assert response.json()["code"] in {"NOT_FOUND", "REMOTE_UNAVAILABLE"}, response.json()
    stored = repository.list_cache_outcomes(TENANT, PROJECT, "req-serving-1")
    assert stored
    assert all(document["outcome"] != "HIT" for document in stored)


# ---------------------------------------------------------------------------
# 8. the two guards that nothing else in the suite makes bite
# ---------------------------------------------------------------------------


def test_a_deployment_action_probe_cannot_make_a_serving_route_skip_its_operation(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    action_cache: ActionCache,
    signer: Ed25519ProvenanceSigner,
) -> None:
    """The ``exact_action_reused`` refusal in ``_composed_serving_call`` bites.

    ``_serving_call`` passes ``probes={}``, and it is tempting to read that as
    "the Action layer is out of scope here, so the refusal below is dead code".
    It is not.  ``CompositionRunner`` merges ``wiring.layer_probes`` *underneath*
    the per-call probes, so a deployment that registers an ACTION probe there
    puts the Action layer in scope on serving routes too — and the composition
    will then short-circuit with ``exact_action_reused=True`` on a route whose
    operation must always run.

    Deleting the guard leaves the rest of the suite green, so this test is the
    only thing standing between that configuration and a serving route that
    answers without ever calling its operation.
    """

    repository = ParityMetadataRepository(store)
    control = ServingControl()
    wiring = make_wiring(
        signer,
        layer_probes={CompositionLayer.ACTION: hot_probe(MATERIAL)},
    )
    plane = build_plane(
        store,
        cas,
        clock,
        action_cache,
        wiring=wiring,
        control=control,
        repository=repository,
        serving=True,
    )

    response = plane.handle(
        Request(
            "GET",
            f"/cache/environments/{digest('3').removeprefix('sha256:')}",
            headers={COMPOSITION_REQUEST_ID_HEADER: "req-serving-guard"},
            query={
                "projectId": PROJECT,
                "trustNamespace": "branch",
                "transferMs": "10",
                "decompressionMs": "5",
                "verificationMs": "5",
                "rebuildMs": "900",
            },
            authenticated_principal_digest=PRINCIPAL,
        )
    )

    # ``handle`` maps the engine's own errors onto the transport, so the refusal
    # arrives as a typed 4xx rather than a traceback -- but it is still a
    # refusal, and the route did not answer from cache.
    body = response.json()
    assert body["code"] == "CONTRACT_VIOLATION"
    assert "may not skip its operation" in body["message"]
    assert control.rollback_reasons == ["SERVING_PATH_SKIPPED_EXECUTION"]


class _NonHitWithDigestCache:
    """An Action Cache that reports a miss while still carrying a digest.

    ``ActionCache.lookup`` never produces this today — ``result_digest`` is only
    set on the hit path — which is exactly why the probe's ``not result.hit``
    test is unfalsifiable through the real cache and why removing it leaves the
    suite green.  A future miss reason that keeps the digest (a restore-cost
    refusal, say) would turn straight into a served hit.  This stub is the only
    way to state that the guard, not the current cache implementation, is what
    holds the line.
    """

    def __init__(self, result: LookupResult) -> None:
        self._result = result
        self.calls = 0

    def lookup(self, request: Any) -> LookupResult:
        del request
        self.calls += 1
        return self._result


def test_the_action_probe_refuses_a_miss_that_still_carries_a_result_digest() -> None:
    cache = _NonHitWithDigestCache(
        LookupResult(hit=False, reasons=(MissReason.NO_ENTRY,), result_digest=MATERIAL)
    )
    probe = ActionCacheLayerProbe(
        cache,
        tenant_id=TENANT,
        action_key=ACTION_KEY,
        trust_namespace=TrustNamespace.BRANCH,
        minimum_validation=ValidationLevel.TEST_VERIFIED,
        mode=CacheMode.READ_ONLY,
    )

    result = probe(composition_request())

    assert result.disposition is not LookupDisposition.HIT
    assert result.material_digest is None
    assert result.reason_code == str(MissReason.NO_ENTRY)
    # And the memoisation still holds: one lookup, however many probe calls.
    probe(composition_request())
    assert cache.calls == 1
