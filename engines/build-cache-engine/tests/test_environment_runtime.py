"""Focused local environment materialization tests; no activation or network."""

from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db.store import MetadataStore
from elmos_build_cache.environment_cache import EnvironmentKeyInputs, PlatformIdentity, RestoreAction
from elmos_build_cache.environment_runtime import (
    EnvironmentLayerDestination,
    LocalEnvironmentLayerMaterializer,
    verify_environment_materialization_receipt,
)
from elmos_build_cache.environment_service import (
    EnvironmentLayerPayload,
    EnvironmentLayerType,
    EnvironmentRestoreResult,
    EnvironmentSnapshotService,
    RestoreCostPolicy,
)
from elmos_build_cache.errors import ContractViolation, UnsafePath

TENANT = "tenant-test"
PROJECT = "project-test"
TRUST = "tenant/project/toolchain"


def d(character: str) -> str:
    return "sha256:" + character * 64


def key_inputs() -> EnvironmentKeyInputs:
    return EnvironmentKeyInputs(
        base_image_digest=d("1"),
        setup_script_digests=(d("2"),),
        maintenance_script_digests=(d("3"),),
        lockfile_digests=(("requirements.lock", d("4")),),
        package_manager_digest=d("5"),
        toolchain_digests=(("python", d("6")),),
        platform=PlatformIdentity("linux", "arm64", "glibc", d("7")),
        approved_environment_digests=(("BUILD_MODE", d("8")),),
        secret_reference_versions=((d("9"), d("a")),),
    )


def cheap_policy() -> RestoreCostPolicy:
    return RestoreCostPolicy(
        rebuild_ms=500.0,
        transfer_bytes_per_ms=10_000.0,
        decompression_bytes_per_ms=10_000.0,
        verification_bytes_per_ms=10_000.0,
        minimum_savings_ms=1.0,
        maximum_restore_ratio=0.9,
    )


def seal_and_restore(
    service: EnvironmentSnapshotService,
    tmp_path: Path,
) -> tuple[bytes, bytes, EnvironmentRestoreResult]:
    source = tmp_path / "cold-environment"
    source.mkdir()
    toolchain = b"verified-toolchain-layer\x00"
    dependencies = b"verified-dependencies-layer\x00"
    (source / "toolchain.layer").write_bytes(toolchain)
    (source / "dependencies.layer").write_bytes(dependencies)
    service.seal(
        TENANT,
        PROJECT,
        TRUST,
        key_inputs(),
        (
            EnvironmentLayerPayload(
                EnvironmentLayerType.TOOLCHAIN,
                (source / "toolchain.layer").read_bytes(),
            ),
            EnvironmentLayerPayload(
                EnvironmentLayerType.DEPENDENCIES,
                (source / "dependencies.layer").read_bytes(),
            ),
        ),
    )
    shutil.rmtree(source)
    assert not source.exists()
    restored = service.restore(TENANT, PROJECT, TRUST, key_inputs(), cheap_policy())
    assert restored.decision.action is RestoreAction.RESTORE
    return toolchain, dependencies, restored


def destinations() -> tuple[EnvironmentLayerDestination, ...]:
    return (
        EnvironmentLayerDestination(
            EnvironmentLayerType.TOOLCHAIN,
            "layers/toolchain.layer",
        ),
        EnvironmentLayerDestination(
            EnvironmentLayerType.DEPENDENCIES,
            "layers/dependencies.layer",
        ),
    )


def test_cold_seal_destroy_restore_and_materialize_is_byte_identical(
    store: MetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    tmp_path: Path,
) -> None:
    service = EnvironmentSnapshotService(store, cas, clock=clock)
    toolchain, dependencies, restored = seal_and_restore(service, tmp_path)
    workspace = tmp_path / "disposable-workspace"
    workspace.mkdir()

    receipt = LocalEnvironmentLayerMaterializer().materialize(
        tenant_id=TENANT,
        project_id=PROJECT,
        restored=restored,
        workspace_root=workspace,
        destinations=destinations(),
    )

    assert (workspace / "layers/toolchain.layer").read_bytes() == toolchain
    assert (workspace / "layers/dependencies.layer").read_bytes() == dependencies
    for path in (workspace / "layers").iterdir():
        assert path.stat().st_mode & 0o111 == 0
    document = receipt.to_dict()
    verify_environment_materialization_receipt(document)
    assert document["activation_performed"] is False
    assert document["mount_performed"] is False
    assert document["network_access_performed"] is False
    assert document["snapshot_key"] == restored.snapshot_key


def test_materializer_rejects_escape_symlink_and_executable_destinations(
    store: MetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    tmp_path: Path,
) -> None:
    service = EnvironmentSnapshotService(store, cas, clock=clock)
    _, _, restored = seal_and_restore(service, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(UnsafePath, match="traversal"):
        EnvironmentLayerDestination(EnvironmentLayerType.TOOLCHAIN, "../escape.layer")
    with pytest.raises(ContractViolation, match="executable activation is forbidden"):
        EnvironmentLayerDestination(
            EnvironmentLayerType.TOOLCHAIN,
            "toolchain.layer",
            executable=True,
        )

    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "linked").symlink_to(outside, target_is_directory=True)
    unsafe = (
        EnvironmentLayerDestination(
            EnvironmentLayerType.TOOLCHAIN,
            "linked/toolchain.layer",
        ),
        EnvironmentLayerDestination(
            EnvironmentLayerType.DEPENDENCIES,
            "layers/dependencies.layer",
        ),
    )
    with pytest.raises(UnsafePath, match="symlink|escapes"):
        LocalEnvironmentLayerMaterializer().materialize(
            tenant_id=TENANT,
            project_id=PROJECT,
            restored=restored,
            workspace_root=workspace,
            destinations=unsafe,
        )
    assert list(outside.iterdir()) == []
    assert not (workspace / "layers/dependencies.layer").exists()
    assert not (workspace / "layers").exists()


def test_materializer_refuses_overwrite_and_receipt_tampering(
    store: MetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    tmp_path: Path,
) -> None:
    service = EnvironmentSnapshotService(store, cas, clock=clock)
    _, _, restored = seal_and_restore(service, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    materializer = LocalEnvironmentLayerMaterializer()
    receipt = materializer.materialize(
        tenant_id=TENANT,
        project_id=PROJECT,
        restored=restored,
        workspace_root=workspace,
        destinations=destinations(),
    )

    before = (workspace / "layers/toolchain.layer").read_bytes()
    with pytest.raises(UnsafePath, match="overwrite"):
        materializer.materialize(
            tenant_id=TENANT,
            project_id=PROJECT,
            restored=restored,
            workspace_root=workspace,
            destinations=destinations(),
        )
    assert (workspace / "layers/toolchain.layer").read_bytes() == before

    tampered = copy.deepcopy(receipt.to_dict())
    raw_layers = tampered["layers"]
    assert isinstance(raw_layers, list)
    first = raw_layers[0]
    assert isinstance(first, dict)
    first["logical_path"] = "layers/tampered.layer"
    with pytest.raises(ContractViolation, match="destination binding"):
        verify_environment_materialization_receipt(tampered)


def test_workspace_root_symlink_is_rejected_before_any_write(
    store: MetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    tmp_path: Path,
) -> None:
    service = EnvironmentSnapshotService(store, cas, clock=clock)
    _, _, restored = seal_and_restore(service, tmp_path)
    real_workspace = tmp_path / "real-workspace"
    real_workspace.mkdir()
    linked_workspace = tmp_path / "linked-workspace"
    os.symlink(real_workspace, linked_workspace, target_is_directory=True)

    with pytest.raises(UnsafePath, match="root cannot be a symlink"):
        LocalEnvironmentLayerMaterializer().materialize(
            tenant_id=TENANT,
            project_id=PROJECT,
            restored=restored,
            workspace_root=linked_workspace,
            destinations=destinations(),
        )
    assert list(real_workspace.iterdir()) == []
