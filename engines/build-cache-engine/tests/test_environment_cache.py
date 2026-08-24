from __future__ import annotations

import json

import pytest

from elmos_build_cache.environment_cache import (
    EnvironmentKeyInputs,
    EnvironmentSnapshotManifest,
    PlatformIdentity,
    RestoreAction,
    RestoreContext,
    RestoreEstimate,
    RestoreReason,
    SnapshotStatus,
    assess_restore,
    build_environment_snapshot_key,
    fingerprint_approved_environment,
    fingerprint_secret_references,
)
from elmos_build_cache.errors import ContractViolation


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
        "platform": PlatformIdentity("linux", "x86_64", "glibc", d("7")),
        "approved_environment_digests": (("BUILD_MODE", d("8")),),
        "secret_reference_versions": ((d("9"), d("a")),),
    }
    values.update(changes)
    return EnvironmentKeyInputs(**values)  # type: ignore[arg-type]


def manifest(**changes: object) -> EnvironmentSnapshotManifest:
    values: dict[str, object] = {
        "snapshot_id": d("b"),
        "key": build_environment_snapshot_key(key_inputs()),
        "tenant_scope_digest": d("c"),
        "trust_namespace": "branch",
        "layer_digests": (d("d"), d("e")),
        "status": SnapshotStatus.READY,
        "size_bytes": 1_000,
        "created_at": 100.0,
        "expires_at": 500.0,
    }
    values.update(changes)
    return EnvironmentSnapshotManifest(**values)  # type: ignore[arg-type]


def context(item: EnvironmentSnapshotManifest, **changes: object) -> RestoreContext:
    values: dict[str, object] = {
        "expected_key_digest": item.key.digest,
        "tenant_scope_digest": item.tenant_scope_digest,
        "trust_namespace": item.trust_namespace,
        "observed_manifest_digest": item.manifest_digest,
        "verified_layer_digests": item.layer_digests,
        "now": 200.0,
    }
    values.update(changes)
    return RestoreContext(**values)  # type: ignore[arg-type]


def estimate(**changes: object) -> RestoreEstimate:
    values: dict[str, object] = {
        "transfer_ms": 10.0,
        "decompression_ms": 5.0,
        "verification_ms": 5.0,
        "rebuild_ms": 200.0,
        "minimum_savings_ms": 50.0,
        "maximum_restore_ratio": 0.9,
    }
    values.update(changes)
    return RestoreEstimate(**values)  # type: ignore[arg-type]


def test_every_declared_environment_dimension_moves_the_key() -> None:
    baseline = build_environment_snapshot_key(key_inputs()).digest
    variants = (
        {"base_image_digest": d("f")},
        {"setup_script_digests": (d("f"),)},
        {"maintenance_script_digests": (d("f"),)},
        {"lockfile_digests": (("requirements.lock", d("f")),)},
        {"package_manager_digest": d("f")},
        {"toolchain_digests": (("python", d("f")),)},
        {"platform": PlatformIdentity("linux", "arm64", "glibc", d("7"))},
        {"approved_environment_digests": (("BUILD_MODE", d("f")),)},
        {"secret_reference_versions": ((d("9"), d("f")),)},
        {"schema_version": "elmos.environment-key/v2"},
    )
    assert all(build_environment_snapshot_key(key_inputs(**change)).digest != baseline for change in variants)


def test_key_canonicalizes_named_inputs_and_rejects_duplicates() -> None:
    left = build_environment_snapshot_key(
        key_inputs(toolchain_digests=(("python", d("6")), ("java", d("7"))))
    )
    right = build_environment_snapshot_key(
        key_inputs(toolchain_digests=(("java", d("7")), ("python", d("6"))))
    )
    assert left.digest == right.digest

    with pytest.raises(ContractViolation, match="duplicate name"):
        key_inputs(toolchain_digests=(("python", d("6")), ("python", d("7"))))


def test_environment_and_secret_helpers_never_persist_raw_values() -> None:
    environment = fingerprint_approved_environment({"BUILD_MODE": "release"})
    secret_refs = fingerprint_secret_references({"vault://team/api": "version-42"})
    item = key_inputs(
        approved_environment_digests=environment,
        secret_reference_versions=secret_refs,
    )
    encoded = json.dumps(item.document(), sort_keys=True)
    assert "release" not in encoded
    assert "vault://team/api" not in encoded
    assert "version-42" not in encoded

    with pytest.raises(ContractViolation, match="secret-like environment name"):
        fingerprint_approved_environment({"API_TOKEN": "do-not-store"})


def test_restore_requires_exact_identity_and_verified_bytes() -> None:
    item = manifest()
    decision = assess_restore(item, context(item), estimate())
    assert decision.action is RestoreAction.RESTORE
    assert decision.reason is RestoreReason.RESTORE_VERIFIED
    assert decision.net_savings_ms == 180.0

    wrong_key = assess_restore(item, context(item, expected_key_digest=d("0")), estimate())
    assert wrong_key.fail_closed is True
    assert wrong_key.reason is RestoreReason.KEY_MISMATCH

    wrong_tenant = assess_restore(item, context(item, tenant_scope_digest=d("0")), estimate())
    assert wrong_tenant.reason is RestoreReason.TENANT_MISMATCH
    assert wrong_tenant.fail_closed is True

    wrong_trust = assess_restore(item, context(item, trust_namespace="official"), estimate())
    assert wrong_trust.reason is RestoreReason.TRUST_NAMESPACE_MISMATCH

    wrong_manifest = assess_restore(item, context(item, observed_manifest_digest=d("0")), estimate())
    assert wrong_manifest.reason is RestoreReason.MANIFEST_DIGEST_MISMATCH

    wrong_layers = assess_restore(item, context(item, verified_layer_digests=(d("d"),)), estimate())
    assert wrong_layers.reason is RestoreReason.LAYER_VERIFICATION_FAILED


@pytest.mark.parametrize(
    ("status", "extra", "reason"),
    [
        (SnapshotStatus.BUILDING, {}, RestoreReason.SNAPSHOT_NOT_READY),
        (SnapshotStatus.SEALED, {}, RestoreReason.SNAPSHOT_NOT_READY),
        (SnapshotStatus.EXPIRED, {}, RestoreReason.SNAPSHOT_EXPIRED),
        (SnapshotStatus.REVOKED, {"revoked_at": 150.0}, RestoreReason.SNAPSHOT_REVOKED),
        (SnapshotStatus.CORRUPT, {}, RestoreReason.SNAPSHOT_CORRUPT),
        (SnapshotStatus.QUARANTINED, {}, RestoreReason.SNAPSHOT_QUARANTINED),
    ],
)
def test_non_ready_statuses_fail_closed(
    status: SnapshotStatus,
    extra: dict[str, float],
    reason: RestoreReason,
) -> None:
    item = manifest(status=status, **extra)
    decision = assess_restore(item, context(item), estimate())
    assert decision.action is RestoreAction.REBUILD
    assert decision.reason is reason
    assert decision.fail_closed is True


def test_wall_clock_expiry_fails_even_if_stored_status_is_ready() -> None:
    item = manifest()
    decision = assess_restore(item, context(item, now=500.0), estimate())
    assert decision.reason is RestoreReason.SNAPSHOT_EXPIRED
    assert decision.fail_closed is True


def test_restore_vs_rebuild_is_net_of_verification_and_policy_floor() -> None:
    item = manifest()
    expensive = assess_restore(
        item,
        context(item),
        estimate(transfer_ms=80.0, decompression_ms=10.0, verification_ms=10.0, rebuild_ms=100.0),
    )
    assert expensive.action is RestoreAction.REBUILD
    assert expensive.reason is RestoreReason.RESTORE_MORE_EXPENSIVE_THAN_REBUILD
    assert expensive.eligible is True

    below_floor = assess_restore(
        item,
        context(item),
        estimate(
            transfer_ms=30.0,
            decompression_ms=10.0,
            verification_ms=10.0,
            rebuild_ms=100.0,
            minimum_savings_ms=60.0,
        ),
    )
    assert below_floor.reason is RestoreReason.SAVINGS_BELOW_POLICY_FLOOR
    assert below_floor.fail_closed is False
