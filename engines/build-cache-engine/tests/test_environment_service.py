"""Production environment snapshot service contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db.store import MetadataStore
from elmos_build_cache.enums import ArtifactStorageState
from elmos_build_cache.environment_cache import (
    EnvironmentKeyInputs,
    PlatformIdentity,
    RestoreAction,
    RestoreReason,
    build_environment_snapshot_key,
    fingerprint_approved_environment,
    fingerprint_secret_references,
)
from elmos_build_cache.environment_service import (
    EnvironmentLayerPayload,
    EnvironmentLayerType,
    EnvironmentSnapshotLimits,
    EnvironmentSnapshotService,
    RestoreCostPolicy,
    WarmLayerInventory,
)
from elmos_build_cache.errors import (
    ContractViolation,
    IdempotencyConflict,
    NotFound,
    TenantMismatch,
)
from elmos_build_cache.parity_store import ParityMetadataRepository
from elmos_build_cache.schemas import validate

TENANT = "tenant-test"
PROJECT = "project-test"
TRUST = "tenant/project/toolchain"


def d(character: str) -> str:
    return "sha256:" + character * 64


def key_inputs(**changes: object) -> EnvironmentKeyInputs:
    values: dict[str, object] = {
        "base_image_digest": d("1"),
        "setup_script_digests": (d("2"),),
        "maintenance_script_digests": (d("3"),),
        "lockfile_digests": (("requirements.lock", d("4")),),
        "package_manager_digest": d("5"),
        "toolchain_digests": (("python", d("6")),),
        "platform": PlatformIdentity("linux", "arm64", "glibc", d("7")),
        "approved_environment_digests": (("BUILD_MODE", d("8")),),
        "secret_reference_versions": ((d("9"), d("a")),),
    }
    values.update(changes)
    return EnvironmentKeyInputs(**values)  # type: ignore[arg-type]


def layer_payloads(*, dependency: bytes = b"dependency-layer") -> tuple[EnvironmentLayerPayload, ...]:
    return (
        EnvironmentLayerPayload(EnvironmentLayerType.TOOLCHAIN, b"toolchain-layer"),
        EnvironmentLayerPayload(EnvironmentLayerType.DEPENDENCIES, dependency),
    )


@pytest.fixture
def repository(store: MetadataStore) -> ParityMetadataRepository:
    return ParityMetadataRepository(store)


@pytest.fixture
def service(
    store: MetadataStore,
    cas: ContentAddressableStore,
    repository: ParityMetadataRepository,
    clock: ManualClock,
) -> EnvironmentSnapshotService:
    return EnvironmentSnapshotService(store, cas, repository, clock)


def cheap_policy(**changes: float) -> RestoreCostPolicy:
    values = {
        "rebuild_ms": 500.0,
        "transfer_bytes_per_ms": 10_000.0,
        "decompression_bytes_per_ms": 10_000.0,
        "verification_bytes_per_ms": 10_000.0,
        "minimum_savings_ms": 1.0,
        "maximum_restore_ratio": 0.9,
    }
    values.update(changes)
    return RestoreCostPolicy(**values)


def test_seal_persists_schema_valid_content_free_manifest_and_registered_cas_layers(
    service: EnvironmentSnapshotService,
    store: MetadataStore,
    cas: ContentAddressableStore,
    repository: ParityMetadataRepository,
) -> None:
    inputs = key_inputs(
        approved_environment_digests=fingerprint_approved_environment(
            {"BUILD_MODE": "release-value-must-not-persist"}
        ),
        secret_reference_versions=fingerprint_secret_references(
            {"vault://team/raw-secret-reference": "secret-version-42"}
        ),
    )
    sealed = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())

    validate("environment-snapshot", sealed.manifest)
    encoded = json.dumps(sealed.manifest, sort_keys=True)
    assert "release-value-must-not-persist" not in encoded
    assert "vault://team/raw-secret-reference" not in encoded
    assert "secret-version-42" not in encoded
    assert sealed.effective_status == "AVAILABLE"
    assert sealed.key == build_environment_snapshot_key(inputs)
    assert cas.get_document(sealed.manifest_digest) == sealed.manifest
    assert [ref.layer_type for ref in sealed.layers] == [
        EnvironmentLayerType.TOOLCHAIN,
        EnvironmentLayerType.DEPENDENCIES,
    ]

    for ref, expected in zip(sealed.layers, (b"toolchain-layer", b"dependency-layer"), strict=True):
        assert cas.get_bytes(ref.digest, verify=True) == expected
        artifact = store.get_artifact(TENANT, ref.digest)
        assert artifact is not None
        assert artifact.size_bytes == len(expected)
        assert artifact.storage_state is ArtifactStorageState.LOCAL
    assert store.get_artifact(TENANT, sealed.manifest_digest) is not None
    assert set(store.artifact_targets(TENANT, "environment-snapshot", sealed.snapshot_id)) == {
        sealed.manifest_digest,
        *(ref.digest for ref in sealed.layers),
    }

    state = repository.get_environment_snapshot_state(TENANT, PROJECT, sealed.key.digest)
    assert state is not None
    assert state["manifest_digest"] == sealed.manifest_digest
    assert state["effective_status"] == "AVAILABLE"


def test_seal_is_exactly_idempotent_and_same_key_layer_drift_conflicts(
    service: EnvironmentSnapshotService,
    store: MetadataStore,
    cas: ContentAddressableStore,
) -> None:
    inputs = key_inputs()
    first = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    replay = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    assert replay.manifest == first.manifest
    assert replay.manifest_digest == first.manifest_digest
    assert replay.snapshot_id == first.snapshot_id

    before_accounting = cas.accounting()
    before_rows = {
        "artifacts": store.query_one("SELECT COUNT(*) FROM artifacts")[0],
        "artifact_refs": store.query_one("SELECT COUNT(*) FROM artifact_refs")[0],
        "snapshots": store.query_one(
            "SELECT COUNT(*) FROM environment_snapshot_manifests"
        )[0],
    }
    with pytest.raises(IdempotencyConflict, match="different layers"):
        service.seal(
            TENANT,
            PROJECT,
            TRUST,
            inputs,
            layer_payloads(dependency=b"nondeterministic-dependency-layer"),
        )
    assert cas.accounting() == before_accounting
    assert {
        "artifacts": store.query_one("SELECT COUNT(*) FROM artifacts")[0],
        "artifact_refs": store.query_one("SELECT COUNT(*) FROM artifact_refs")[0],
        "snapshots": store.query_one(
            "SELECT COUNT(*) FROM environment_snapshot_manifests"
        )[0],
    } == before_rows


@pytest.mark.parametrize(
    ("limits", "layers", "message"),
    [
        (
            EnvironmentSnapshotLimits(max_layers=1, max_layer_bytes=10, max_total_bytes=10),
            (
                EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"a"),
                EnvironmentLayerPayload(EnvironmentLayerType.INDEX, b"b"),
            ),
            "layer-count limit",
        ),
        (
            EnvironmentSnapshotLimits(max_layers=2, max_layer_bytes=3, max_total_bytes=10),
            (EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"four"),),
            "layer exceeds",
        ),
        (
            EnvironmentSnapshotLimits(max_layers=2, max_layer_bytes=4, max_total_bytes=6),
            (
                EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"aaaa"),
                EnvironmentLayerPayload(EnvironmentLayerType.INDEX, b"bbbb"),
            ),
            "total-byte limit",
        ),
    ],
)
def test_seal_limits_fail_before_any_cas_or_artifact_write(
    store: MetadataStore,
    cas: ContentAddressableStore,
    repository: ParityMetadataRepository,
    clock: ManualClock,
    limits: EnvironmentSnapshotLimits,
    layers: tuple[EnvironmentLayerPayload, ...],
    message: str,
) -> None:
    bounded = EnvironmentSnapshotService(store, cas, repository, clock, limits)
    before_accounting = cas.accounting()
    before_artifacts = store.query_one("SELECT COUNT(*) FROM artifacts")[0]

    with pytest.raises(ContractViolation, match=message):
        bounded.seal(TENANT, PROJECT, TRUST, key_inputs(), layers)

    assert cas.accounting() == before_accounting
    assert store.query_one("SELECT COUNT(*) FROM artifacts")[0] == before_artifacts


def test_seal_rejects_cross_tenant_project_before_any_cas_or_metadata_write(
    service: EnvironmentSnapshotService,
    store: MetadataStore,
    cas: ContentAddressableStore,
) -> None:
    before_cas = cas.accounting()
    before_artifacts = store.query_one(
        "SELECT COUNT(*) FROM artifacts WHERE tenant_id=?",
        ("tenant-attacker",),
    )

    with pytest.raises(TenantMismatch):
        service.seal(
            "tenant-attacker",
            PROJECT,
            TRUST,
            key_inputs(),
            layer_payloads(),
        )

    assert cas.accounting() == before_cas
    assert store.query_one(
        "SELECT COUNT(*) FROM artifacts WHERE tenant_id=?",
        ("tenant-attacker",),
    ) == before_artifacts
    assert store.query_one(
        "SELECT tenant_id FROM tenants WHERE tenant_id=?",
        ("tenant-attacker",),
    ) is None


def test_restore_returns_verified_bytes_and_refs_without_materialising_a_workspace(
    service: EnvironmentSnapshotService,
    tmp_path: Path,
) -> None:
    inputs = key_inputs()
    sealed = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    before = set(tmp_path.rglob("*"))

    restored = service.restore(TENANT, PROJECT, TRUST, inputs, cheap_policy())

    assert restored.decision.action is RestoreAction.RESTORE
    assert restored.decision.reason is RestoreReason.RESTORE_VERIFIED
    assert restored.layer_refs == sealed.layers
    assert [layer.content for layer in restored.verified_layers] == [
        b"toolchain-layer",
        b"dependency-layer",
    ]
    # The only mutations are metadata/CAS access.  The service has no
    # destination argument and cannot lay bytes into a caller workspace.
    after = set(tmp_path.rglob("*"))
    assert all("workspace" not in str(path) for path in after - before)


def test_restore_reuses_inspection_artifact_binding_checks_before_returning_bytes(
    service: EnvironmentSnapshotService,
    store: MetadataStore,
    repository: ParityMetadataRepository,
) -> None:
    inputs = key_inputs()
    sealed = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    with store.transaction():
        store.execute(
            "DELETE FROM artifact_refs WHERE tenant_id=? AND source_kind=?"
            " AND source_id=? AND target_digest=?",
            (
                TENANT,
                "environment-snapshot",
                sealed.snapshot_id,
                sealed.layers[0].digest,
            ),
        )

    result = service.restore(TENANT, PROJECT, TRUST, inputs, cheap_policy())

    assert result.decision.action is RestoreAction.REBUILD
    assert result.verified_layers == ()
    state = repository.get_environment_snapshot_state(TENANT, PROJECT, sealed.key.digest)
    assert state is not None
    assert state["effective_status"] == "QUARANTINED"


def test_restore_verifies_manifest_cas_before_returning_any_layer_bytes(
    service: EnvironmentSnapshotService,
    store: MetadataStore,
    cas: ContentAddressableStore,
) -> None:
    inputs = key_inputs()
    sealed = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    manifest_path = cas.path_for(sealed.manifest_digest)
    os.chmod(manifest_path, 0o644)
    manifest_path.write_bytes(b"tampered-manifest")

    result = service.restore(TENANT, PROJECT, TRUST, inputs, cheap_policy())

    assert result.decision.action is RestoreAction.REBUILD
    assert result.verified_layers == ()
    artifact = store.get_artifact(TENANT, sealed.manifest_digest)
    assert artifact is not None
    assert artifact.storage_state is ArtifactStorageState.QUARANTINED


def test_lookup_is_exact_for_tenant_project_key_and_trust(
    service: EnvironmentSnapshotService,
) -> None:
    inputs = key_inputs()
    service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())

    wrong_trust = service.restore(TENANT, PROJECT, "official", inputs, cheap_policy())
    assert wrong_trust.decision.action is RestoreAction.REBUILD
    assert wrong_trust.decision.reason is RestoreReason.TRUST_NAMESPACE_MISMATCH
    assert wrong_trust.verified_layers == ()

    with pytest.raises(NotFound, match="exact tenant/project"):
        service.restore("tenant-other", PROJECT, TRUST, inputs, cheap_policy())
    with pytest.raises(NotFound, match="exact tenant/project"):
        service.restore(TENANT, "project-other", TRUST, inputs, cheap_policy())
    with pytest.raises(NotFound, match="exact tenant/project"):
        service.restore(
            TENANT,
            PROJECT,
            TRUST,
            key_inputs(base_image_digest=d("f")),
            cheap_policy(),
        )


def test_expired_and_explicitly_revoked_snapshots_fail_closed(
    service: EnvironmentSnapshotService,
    clock: ManualClock,
    repository: ParityMetadataRepository,
) -> None:
    expiring = key_inputs(base_image_digest=d("b"))
    service.seal(
        TENANT,
        PROJECT,
        TRUST,
        expiring,
        layer_payloads(),
        expires_at=clock.now() + 60.0,
    )
    expired = service.restore(
        TENANT,
        PROJECT,
        TRUST,
        expiring,
        cheap_policy(),
        now=clock.now() + 60.0,
    )
    assert expired.decision.reason is RestoreReason.SNAPSHOT_EXPIRED
    assert expired.decision.fail_closed is True

    inputs = key_inputs()
    sealed = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    event = service.revoke(
        TENANT,
        PROJECT,
        TRUST,
        inputs,
        event_id="operator-revoke-1",
        reason_digest=d("e"),
    )
    assert event["new_status"] == "REVOKED"
    assert service.revoke(
        TENANT,
        PROJECT,
        TRUST,
        inputs,
        event_id="operator-revoke-1",
        reason_digest=d("e"),
    ) == event
    state = repository.get_environment_snapshot_state(TENANT, PROJECT, sealed.key.digest)
    assert state is not None
    assert state["effective_status"] == "REVOKED"
    revoked = service.restore(TENANT, PROJECT, TRUST, inputs, cheap_policy())
    assert revoked.decision.reason is RestoreReason.SNAPSHOT_REVOKED
    assert revoked.verified_layers == ()


def test_corrupt_layer_is_cas_quarantined_and_snapshot_gets_append_only_terminal_event(
    service: EnvironmentSnapshotService,
    store: MetadataStore,
    cas: ContentAddressableStore,
    repository: ParityMetadataRepository,
) -> None:
    inputs = key_inputs()
    sealed = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    corrupt_ref = sealed.layers[0]
    path = cas.path_for(corrupt_ref.digest)
    os.chmod(path, 0o644)
    path.write_bytes(b"tampered-layer")

    result = service.restore(TENANT, PROJECT, TRUST, inputs, cheap_policy())

    assert result.decision.action is RestoreAction.REBUILD
    assert result.decision.reason is RestoreReason.LAYER_VERIFICATION_FAILED
    assert result.verified_layers == ()
    assert cas.is_quarantined(corrupt_ref.digest) is True
    artifact = store.get_artifact(TENANT, corrupt_ref.digest)
    assert artifact is not None
    assert artifact.storage_state is ArtifactStorageState.QUARANTINED
    state = repository.get_environment_snapshot_state(TENANT, PROJECT, sealed.key.digest)
    assert state is not None
    assert state["effective_status"] == "QUARANTINED"
    latest = state["latest_status_event"]
    assert latest is not None
    assert latest["new_status"] == "QUARANTINED"

    second = service.restore(TENANT, PROJECT, TRUST, inputs, cheap_policy())
    assert second.decision.reason is RestoreReason.SNAPSHOT_QUARANTINED


def test_restore_cost_includes_transfer_decompression_verification_and_safe_warm_inventory(
    service: EnvironmentSnapshotService,
) -> None:
    inputs = key_inputs()
    sealed = service.seal(
        TENANT,
        PROJECT,
        TRUST,
        inputs,
        (
            EnvironmentLayerPayload(EnvironmentLayerType.TOOLCHAIN, b"a" * 80),
            EnvironmentLayerPayload(EnvironmentLayerType.DEPENDENCIES, b"b" * 70),
        ),
    )
    policy = cheap_policy(
        rebuild_ms=100.0,
        transfer_bytes_per_ms=1.0,
        decompression_bytes_per_ms=1_000_000.0,
        verification_bytes_per_ms=1_000_000.0,
        minimum_savings_ms=0.0,
        maximum_restore_ratio=1.0,
    )

    cold = service.restore(TENANT, PROJECT, TRUST, inputs, policy)
    assert cold.decision.reason is RestoreReason.RESTORE_MORE_EXPENSIVE_THAN_REBUILD
    assert cold.decision.restore_ms > 100.0

    cross_tenant_writable = WarmLayerInventory(
        "tenant-other",
        PROJECT,
        TRUST,
        tuple(ref.digest for ref in sealed.layers),
        writable=True,
    )
    unsafe = service.restore(
        TENANT,
        PROJECT,
        TRUST,
        inputs,
        policy,
        warm_inventory=(cross_tenant_writable,),
    )
    assert unsafe.decision.action is RestoreAction.REBUILD
    assert unsafe.warm_inventory_digests == ()

    safe = WarmLayerInventory(
        TENANT,
        PROJECT,
        TRUST,
        tuple(ref.digest for ref in sealed.layers),
        writable=False,
    )
    warm = service.restore(
        TENANT,
        PROJECT,
        TRUST,
        inputs,
        policy,
        warm_inventory=(safe,),
    )
    assert warm.decision.action is RestoreAction.RESTORE
    assert warm.decision.restore_ms < 1.0
    assert warm.warm_inventory_digests == tuple(sorted(ref.digest for ref in sealed.layers))


def test_layer_contract_rejects_mutable_unknown_duplicate_and_ambiguous_payloads(
    service: EnvironmentSnapshotService,
) -> None:
    with pytest.raises(ContractViolation, match="immutable bytes"):
        EnvironmentLayerPayload(EnvironmentLayerType.BASE, bytearray(b"mutable"))  # type: ignore[arg-type]
    with pytest.raises(ContractViolation, match="duplicate layer type"):
        service.seal(
            TENANT,
            PROJECT,
            TRUST,
            key_inputs(),
            (
                EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"one"),
                EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"two"),
            ),
        )
    with pytest.raises(ContractViolation, match="distinct byte identities"):
        service.seal(
            TENANT,
            PROJECT,
            TRUST,
            key_inputs(),
            (
                EnvironmentLayerPayload(EnvironmentLayerType.BASE, b"same"),
                EnvironmentLayerPayload(EnvironmentLayerType.INDEX, b"same"),
            ),
        )
    with pytest.raises(ContractViolation, match="requires at least one layer"):
        service.seal(TENANT, PROJECT, TRUST, key_inputs(), ())


def test_revoke_requires_exact_trust_and_does_not_revive_terminal_snapshot(
    service: EnvironmentSnapshotService,
) -> None:
    inputs = key_inputs()
    service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    with pytest.raises(ContractViolation, match="bounded identifier"):
        service.revoke(
            TENANT,
            PROJECT,
            "",
            inputs,
            event_id="revoke-invalid-trust",
            reason_digest=d("d"),
        )
    service.revoke(
        TENANT,
        PROJECT,
        TRUST,
        inputs,
        event_id="revoke-final",
        reason_digest=d("d"),
    )
    replay = service.seal(TENANT, PROJECT, TRUST, inputs, layer_payloads())
    assert replay.effective_status == "REVOKED"
