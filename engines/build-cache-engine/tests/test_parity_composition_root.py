"""Production-root tests for durable non-Action parity layer bindings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.errors import ContractViolation, IdempotencyConflict
from elmos_build_cache.gc import GarbageCollector
from elmos_build_cache.parity_composition import (
    SERVING_BOUNDARY_KIND,
    CompositionLayer,
    CompositionRequest,
    FallbackExecutionResult,
    LayerWork,
    ServingAction,
    SignedServingBoundary,
    serving_boundary_statement,
)
from elmos_build_cache.parity_composition_root import (
    PARITY_LAYER_BINDING_SOURCE_KIND,
    FiveLayerProductionCompositionRoot,
    PersistentLayerMaterialRegistry,
    build_production_serving_composition,
)
from elmos_build_cache.parity_composition_wiring import CompositionRunner, LayerProbe
from elmos_build_cache.security import Ed25519ProvenanceSigner

PRINCIPAL = digest("9")
AUTHORIZATION = digest("a")
COMPATIBILITY = digest("b")
WORK = digest("c")
LAYERS = (
    CompositionLayer.PROMPT,
    CompositionLayer.CONTEXT,
    CompositionLayer.ENVIRONMENT,
    CompositionLayer.AFFINITY,
)


class _Sink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def persist(self, request: Any, events: tuple[object, ...], edges: tuple[object, ...]) -> None:
        del request, edges
        self.events.extend(events)


class _Latch:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    def latch_rollback(self, reason_code: str) -> None:
        self.reasons.append(reason_code)


class _Fallback:
    def __init__(self, operation: Any) -> None:
        self.operation = operation
        self.value: Any = None

    def execute(
        self,
        request: CompositionRequest,
        restored: tuple[Any, ...],
        cache_deadline_monotonic: float,
    ) -> FallbackExecutionResult:
        del request, cache_deadline_monotonic
        self.value = self.operation()
        restored_work = {item.work for item in restored}
        performed = tuple(item for item in LayerWork if item not in restored_work)
        return FallbackExecutionResult(
            success=True,
            reason_code="FALLBACK_EXECUTED",
            performed_work=performed,
            execution_digest=digest("e"),
        )


def _boundary(signer: Ed25519ProvenanceSigner) -> SignedServingBoundary:
    statement = serving_boundary_statement(
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        actions={layer: (ServingAction.LOOKUP, ServingAction.RESTORE) for layer in (*LAYERS, CompositionLayer.ACTION)},
        issued_at=0.0,
        expires_at=10**9,
    )
    return SignedServingBoundary(
        signer.sign_statement(SERVING_BOUNDARY_KIND, statement),
        signer,
        wall_clock=lambda: 1.0,
    )


def _request() -> CompositionRequest:
    return CompositionRequest(
        request_id="req-root",
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=WORK,
        cache_deadline_monotonic=100.0,
    )


def _register_all(registry: PersistentLayerMaterialRegistry) -> dict[CompositionLayer, str]:
    result: dict[CompositionLayer, str] = {}
    for layer in LAYERS:
        item = registry.register(
            layer=layer,
            tenant_id=TENANT,
            project_id=PROJECT,
            principal_digest=PRINCIPAL,
            authorization_digest=AUTHORIZATION,
            compatibility_digest=COMPATIBILITY,
            work_digest=WORK,
            material=f"verified-{layer.value}".encode("ascii"),
        )
        result[layer] = item.material_digest
    return result


def test_production_root_wires_all_non_action_layers_and_keeps_action_per_request(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    registry = PersistentLayerMaterialRegistry(store, cas)
    materials = _register_all(registry)
    signer = Ed25519ProvenanceSigner.generate("composition-root")
    wiring = build_production_serving_composition(
        serving_boundary=_boundary(signer),
        layer_registry=registry,
        monotonic=lambda: 0.0,
    )
    assert set(wiring.layer_probes) == set(LAYERS)
    assert CompositionLayer.ACTION not in wiring.layer_probes
    request = _request()
    for layer in LAYERS:
        probe = wiring.layer_probes[layer](request)
        assert probe.material_digest == materials[layer]
        assert probe.verified is True and probe.compatible is True


def test_non_action_hits_restore_work_but_action_miss_still_executes(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    registry = PersistentLayerMaterialRegistry(store, cas)
    _register_all(registry)
    signer = Ed25519ProvenanceSigner.generate("composition-root")
    wiring = FiveLayerProductionCompositionRoot(
        serving_boundary=_boundary(signer),
        layer_registry=registry,
        monotonic=lambda: 0.0,
    ).build()
    sink = _Sink()
    fallback = _Fallback(lambda: "executed")
    runner = CompositionRunner(
        wiring,
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        request_id="req-root-run",
        work_digest=WORK,
        outcome_sink=sink,
        rollback_latch=_Latch(),
        probes={CompositionLayer.ACTION: lambda request: LayerProbe.miss("ACTION_CACHE_MISS")},
    )
    outcome = runner.run(lambda: fallback.operation())
    assert outcome.result.exact_action_reused is False
    assert outcome.result.fallback_executed is True
    assert {item.layer for item in outcome.result.restored} == set(LAYERS)
    assert outcome.result.fallback_result is not None
    assert outcome.result.fallback_result.performed_work == (LayerWork.ACTION_EXECUTION,)


def test_registry_reopens_and_reverifies_durable_material(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    metadata_path = root / "index.sqlite"
    cas_root = root / "cas"
    clock = ManualClock()
    first_store = SqliteMetadataStore.open(metadata_path, clock)
    with first_store.transaction():
        first_store.ensure_project(TENANT, PROJECT)
    first_cas = ContentAddressableStore(cas_root)
    first = PersistentLayerMaterialRegistry(first_store, first_cas)
    registered = first.register(
        layer=CompositionLayer.CONTEXT,
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=WORK,
        material=b"restart-safe-context",
    )
    first_store.close()

    second_store = SqliteMetadataStore.open(metadata_path, clock)
    second = PersistentLayerMaterialRegistry(second_store, ContentAddressableStore(cas_root))
    probe = second.probe(_request(), CompositionLayer.CONTEXT)
    assert probe.material_digest == registered.material_digest
    assert probe.verified is True
    second_store.close()


def test_scope_and_corruption_never_become_hits(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    registry = PersistentLayerMaterialRegistry(store, cas)
    registered = registry.register(
        layer=CompositionLayer.PROMPT,
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=WORK,
        material=b"prompt-material",
    )
    foreign = CompositionRequest(
        request_id="req-foreign",
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=digest("f"),
        cache_deadline_monotonic=100.0,
    )
    assert registry.probe(foreign, CompositionLayer.PROMPT).disposition.value == "MISS"
    tampered_path = cas.path_for(registered.material_digest)
    tampered_path.chmod(0o600)
    tampered_path.write_bytes(b"tampered")
    corrupted = registry.probe(_request(), CompositionLayer.PROMPT)
    assert corrupted.disposition.value == "ERROR"
    assert cas.is_quarantined(registered.material_digest)


def test_action_registration_and_same_binding_drift_are_refused(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    registry = PersistentLayerMaterialRegistry(store, cas)
    kwargs = {
        "tenant_id": TENANT,
        "project_id": PROJECT,
        "principal_digest": PRINCIPAL,
        "authorization_digest": AUTHORIZATION,
        "compatibility_digest": COMPATIBILITY,
        "work_digest": WORK,
    }
    with pytest.raises(ContractViolation):
        registry.register(layer=CompositionLayer.ACTION, material=b"action", **kwargs)
    registry.register(layer=CompositionLayer.PROMPT, material=b"one", **kwargs)
    with pytest.raises(IdempotencyConflict):
        registry.register(layer=CompositionLayer.PROMPT, material=b"two", **kwargs)


def test_artifact_kind_media_and_binding_metadata_are_part_of_the_verified_hit(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    registry = PersistentLayerMaterialRegistry(store, cas)
    registered = registry.register(
        layer=CompositionLayer.CONTEXT,
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=WORK,
        material=b"metadata-bound-context",
    )
    with store.transaction():
        store.execute(
            "UPDATE artifacts SET artifact_kind=? WHERE tenant_id=? AND digest=?",
            ("untrusted-kind", TENANT, registered.manifest_digest),
        )
    probe = registry.probe(_request(), CompositionLayer.CONTEXT)
    assert probe.disposition.value == "ERROR"
    assert probe.reason_code == "LAYER_MANIFEST_METADATA_DRIFT"


def test_gc_treats_registered_layer_manifest_as_a_root(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    registry = PersistentLayerMaterialRegistry(store, cas)
    registered = registry.register(
        layer=CompositionLayer.AFFINITY,
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_digest=AUTHORIZATION,
        compatibility_digest=COMPATIBILITY,
        work_digest=WORK,
        material=b"affinity-material",
    )
    binding_source = registry.store.query_one(
        "SELECT source_id FROM artifact_refs WHERE tenant_id=? AND source_kind=?",
        (TENANT, PARITY_LAYER_BINDING_SOURCE_KIND),
    )[0]
    roots = GarbageCollector(store, cas, TENANT, clock=ManualClock()).live_roots()
    assert any(root.digest == registered.manifest_digest and root.source_id == binding_source for root in roots)
    assert registered.material_digest in {
        item.digest
        for item in GarbageCollector(store, cas, TENANT, clock=ManualClock()).reachable(roots).values()
    }
