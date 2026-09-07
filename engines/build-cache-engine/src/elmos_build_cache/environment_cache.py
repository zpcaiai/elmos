"""Fail-closed environment snapshot identities and restore decisions.

Environment reuse is safe only when the key describes *all* result-affecting
inputs and the restored bytes are independently verified.  This module owns
that pure decision contract; snapshot storage and process execution live at
the edges of the system.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .canonical import digest_of, normalize_logical_path, require_digest, sha256_bytes
from .errors import ContractViolation

ENVIRONMENT_KEY_SCHEMA = "elmos.environment-key/v1"
ENVIRONMENT_MANIFEST_SCHEMA = "elmos.environment-snapshot/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")
_SECRET_MARKERS = ("secret", "token", "password", "credential", "private", "api_key")


class _ValueEnum(StrEnum):
    pass


class SnapshotStatus(_ValueEnum):
    BUILDING = "BUILDING"
    SEALED = "SEALED"
    READY = "READY"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CORRUPT = "CORRUPT"
    QUARANTINED = "QUARANTINED"


class RestoreAction(_ValueEnum):
    RESTORE = "RESTORE"
    REBUILD = "REBUILD"


class RestoreReason(_ValueEnum):
    RESTORE_VERIFIED = "RESTORE_VERIFIED"
    KEY_MISMATCH = "KEY_MISMATCH"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    TRUST_NAMESPACE_MISMATCH = "TRUST_NAMESPACE_MISMATCH"
    SNAPSHOT_NOT_READY = "SNAPSHOT_NOT_READY"
    SNAPSHOT_EXPIRED = "SNAPSHOT_EXPIRED"
    SNAPSHOT_REVOKED = "SNAPSHOT_REVOKED"
    SNAPSHOT_CORRUPT = "SNAPSHOT_CORRUPT"
    SNAPSHOT_QUARANTINED = "SNAPSHOT_QUARANTINED"
    MANIFEST_DIGEST_MISMATCH = "MANIFEST_DIGEST_MISMATCH"
    LAYER_VERIFICATION_FAILED = "LAYER_VERIFICATION_FAILED"
    RESTORE_MORE_EXPENSIVE_THAN_REBUILD = "RESTORE_MORE_EXPENSIVE_THAN_REBUILD"
    SAVINGS_BELOW_POLICY_FLOOR = "SAVINGS_BELOW_POLICY_FLOOR"


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _finite_non_negative(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be numeric", field=field)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContractViolation(f"{field} must be finite and non-negative", field=field)
    return number


def _digest_sequence(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    for value in values:
        require_digest(value)
    if len(values) != len(set(values)):
        raise ContractViolation(f"{field} contains duplicate digests", field=field)
    return tuple(sorted(values))


def _named_digests(
    values: tuple[tuple[str, str], ...],
    field: str,
    *,
    path_names: bool = False,
    forbid_secret_names: bool = False,
) -> tuple[tuple[str, str], ...]:
    names: set[str] = set()
    result: list[tuple[str, str]] = []
    for name, value_digest in values:
        normalised = normalize_logical_path(name) if path_names else _identifier(name, field)
        if forbid_secret_names and any(marker in normalised.casefold() for marker in _SECRET_MARKERS):
            raise ContractViolation(
                "secret-like environment variables must use secret references",
                field=field,
                name=normalised,
            )
        if normalised in names:
            raise ContractViolation(f"{field} contains a duplicate name", field=field, name=normalised)
        require_digest(value_digest)
        names.add(normalised)
        result.append((normalised, value_digest))
    return tuple(sorted(result))


@dataclass(frozen=True)
class PlatformIdentity:
    operating_system: str
    architecture: str
    libc: str
    runtime_digest: str

    def __post_init__(self) -> None:
        _identifier(self.operating_system, "operating_system")
        _identifier(self.architecture, "architecture")
        _identifier(self.libc, "libc")
        require_digest(self.runtime_digest)

    def document(self) -> dict[str, str]:
        return {
            "operating_system": self.operating_system,
            "architecture": self.architecture,
            "libc": self.libc,
            "runtime_digest": self.runtime_digest,
        }


@dataclass(frozen=True)
class EnvironmentKeyInputs:
    """Complete, secret-safe inputs to an environment snapshot key.

    All values that might contain customer data are supplied as digests.  A
    secret is represented only by an opaque reference digest plus its version
    digest; the secret value itself can never enter this document.
    """

    base_image_digest: str
    setup_script_digests: tuple[str, ...]
    maintenance_script_digests: tuple[str, ...]
    lockfile_digests: tuple[tuple[str, str], ...]
    package_manager_digest: str
    toolchain_digests: tuple[tuple[str, str], ...]
    platform: PlatformIdentity
    approved_environment_digests: tuple[tuple[str, str], ...]
    secret_reference_versions: tuple[tuple[str, str], ...]
    schema_version: str = ENVIRONMENT_KEY_SCHEMA

    def __post_init__(self) -> None:
        require_digest(self.base_image_digest)
        object.__setattr__(
            self,
            "setup_script_digests",
            _digest_sequence(self.setup_script_digests, "setup_script_digests"),
        )
        object.__setattr__(
            self,
            "maintenance_script_digests",
            _digest_sequence(self.maintenance_script_digests, "maintenance_script_digests"),
        )
        object.__setattr__(
            self,
            "lockfile_digests",
            _named_digests(self.lockfile_digests, "lockfile_digests", path_names=True),
        )
        require_digest(self.package_manager_digest)
        object.__setattr__(
            self,
            "toolchain_digests",
            _named_digests(self.toolchain_digests, "toolchain_digests"),
        )
        if not self.toolchain_digests:
            raise ContractViolation("at least one toolchain digest is required")
        if not isinstance(self.platform, PlatformIdentity):
            raise ContractViolation("platform must be a PlatformIdentity")
        object.__setattr__(
            self,
            "approved_environment_digests",
            _named_digests(
                self.approved_environment_digests,
                "approved_environment_digests",
                forbid_secret_names=True,
            ),
        )

        references: list[tuple[str, str]] = []
        seen_references: set[str] = set()
        for reference_digest, version_digest in self.secret_reference_versions:
            require_digest(reference_digest)
            require_digest(version_digest)
            if reference_digest in seen_references:
                raise ContractViolation("duplicate secret reference digest")
            seen_references.add(reference_digest)
            references.append((reference_digest, version_digest))
        object.__setattr__(self, "secret_reference_versions", tuple(sorted(references)))
        _identifier(self.schema_version, "schema_version")

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_image_digest": self.base_image_digest,
            "setup_script_digests": list(self.setup_script_digests),
            "maintenance_script_digests": list(self.maintenance_script_digests),
            "lockfile_digests": dict(self.lockfile_digests),
            "package_manager_digest": self.package_manager_digest,
            "toolchain_digests": dict(self.toolchain_digests),
            "platform": self.platform.document(),
            "approved_environment_digests": dict(self.approved_environment_digests),
            "secret_reference_versions": [list(item) for item in self.secret_reference_versions],
        }


@dataclass(frozen=True)
class EnvironmentSnapshotKey:
    digest: str
    inputs: EnvironmentKeyInputs

    def __post_init__(self) -> None:
        require_digest(self.digest)
        expected = digest_of(self.inputs.document())
        if self.digest != expected:
            raise ContractViolation("environment snapshot key does not match its inputs")

    def document(self) -> dict[str, Any]:
        return {"key_digest": self.digest, "inputs": self.inputs.document()}


def build_environment_snapshot_key(inputs: EnvironmentKeyInputs) -> EnvironmentSnapshotKey:
    return EnvironmentSnapshotKey(digest=digest_of(inputs.document()), inputs=inputs)


def fingerprint_approved_environment(values: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Hash approved non-secret environment values without retaining them."""

    result: list[tuple[str, str]] = []
    for name, value in values.items():
        _identifier(name, "approved_environment")
        if any(marker in name.casefold() for marker in _SECRET_MARKERS):
            raise ContractViolation("secret-like environment name must use a secret reference", name=name)
        if not isinstance(value, str):
            raise ContractViolation("approved environment values must be text", name=name)
        result.append((name, sha256_bytes(value.encode("utf-8"))))
    return _named_digests(tuple(result), "approved_environment", forbid_secret_names=True)


def fingerprint_secret_references(values: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Return only opaque reference/version digests, never a secret value."""

    result: list[tuple[str, str]] = []
    for reference, version in values.items():
        if not isinstance(reference, str) or not isinstance(version, str):
            raise ContractViolation("secret reference and version must be text")
        result.append(
            (
                sha256_bytes(reference.encode("utf-8")),
                sha256_bytes(version.encode("utf-8")),
            )
        )
    return tuple(sorted(result))


@dataclass(frozen=True)
class EnvironmentSnapshotManifest:
    snapshot_id: str
    key: EnvironmentSnapshotKey
    tenant_scope_digest: str
    trust_namespace: str
    layer_digests: tuple[str, ...]
    status: SnapshotStatus
    size_bytes: int
    created_at: float
    expires_at: float | None = None
    revoked_at: float | None = None

    def __post_init__(self) -> None:
        require_digest(self.snapshot_id)
        if not isinstance(self.key, EnvironmentSnapshotKey):
            raise ContractViolation("snapshot key must be an EnvironmentSnapshotKey")
        require_digest(self.tenant_scope_digest)
        _identifier(self.trust_namespace, "trust_namespace")
        object.__setattr__(
            self,
            "layer_digests",
            _digest_sequence(self.layer_digests, "layer_digests"),
        )
        if not self.layer_digests:
            raise ContractViolation("an environment snapshot requires at least one immutable layer")
        if not isinstance(self.status, SnapshotStatus):
            raise ContractViolation("snapshot status must use the closed vocabulary")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ContractViolation("snapshot size must be a non-negative integer")
        _finite_non_negative(self.created_at, "created_at")
        if self.expires_at is not None:
            _finite_non_negative(self.expires_at, "expires_at")
            if self.expires_at <= self.created_at:
                raise ContractViolation("snapshot expiry must be after creation")
        if self.revoked_at is not None:
            _finite_non_negative(self.revoked_at, "revoked_at")
            if self.revoked_at < self.created_at:
                raise ContractViolation("snapshot revocation predates creation")
        if self.status is SnapshotStatus.REVOKED and self.revoked_at is None:
            raise ContractViolation("a revoked snapshot requires revoked_at")
        if self.status is SnapshotStatus.READY and self.revoked_at is not None:
            raise ContractViolation("a ready snapshot cannot carry a revocation timestamp")

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": ENVIRONMENT_MANIFEST_SCHEMA,
            "snapshot_id": self.snapshot_id,
            "key_digest": self.key.digest,
            "tenant_scope_digest": self.tenant_scope_digest,
            "trust_namespace": self.trust_namespace,
            "layer_digests": list(self.layer_digests),
            "status": self.status.value,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
        }

    @property
    def manifest_digest(self) -> str:
        return digest_of(self.document())


@dataclass(frozen=True)
class RestoreContext:
    expected_key_digest: str
    tenant_scope_digest: str
    trust_namespace: str
    observed_manifest_digest: str
    verified_layer_digests: tuple[str, ...]
    now: float

    def __post_init__(self) -> None:
        require_digest(self.expected_key_digest)
        require_digest(self.tenant_scope_digest)
        _identifier(self.trust_namespace, "trust_namespace")
        require_digest(self.observed_manifest_digest)
        object.__setattr__(
            self,
            "verified_layer_digests",
            _digest_sequence(self.verified_layer_digests, "verified_layer_digests"),
        )
        _finite_non_negative(self.now, "now")


@dataclass(frozen=True)
class RestoreEstimate:
    transfer_ms: float
    decompression_ms: float
    verification_ms: float
    rebuild_ms: float
    minimum_savings_ms: float = 0.0
    maximum_restore_ratio: float = 1.0

    def __post_init__(self) -> None:
        for field in (
            "transfer_ms",
            "decompression_ms",
            "verification_ms",
            "rebuild_ms",
            "minimum_savings_ms",
        ):
            object.__setattr__(self, field, _finite_non_negative(getattr(self, field), field))
        ratio = _finite_non_negative(self.maximum_restore_ratio, "maximum_restore_ratio")
        if ratio > 1.0:
            raise ContractViolation("maximum_restore_ratio cannot exceed 1.0")
        object.__setattr__(self, "maximum_restore_ratio", ratio)

    @property
    def restore_ms(self) -> float:
        return self.transfer_ms + self.decompression_ms + self.verification_ms


@dataclass(frozen=True)
class RestoreDecision:
    action: RestoreAction
    reason: RestoreReason
    eligible: bool
    restore_ms: float
    rebuild_ms: float
    net_savings_ms: float

    @property
    def fail_closed(self) -> bool:
        return self.action is RestoreAction.REBUILD and not self.eligible

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason.value,
            "eligible": self.eligible,
            "fail_closed": self.fail_closed,
            "restore_ms": self.restore_ms,
            "rebuild_ms": self.rebuild_ms,
            "net_savings_ms": self.net_savings_ms,
        }


def _rebuild(
    reason: RestoreReason,
    estimate: RestoreEstimate,
    *,
    eligible: bool,
) -> RestoreDecision:
    return RestoreDecision(
        action=RestoreAction.REBUILD,
        reason=reason,
        eligible=eligible,
        restore_ms=estimate.restore_ms,
        rebuild_ms=estimate.rebuild_ms,
        net_savings_ms=estimate.rebuild_ms - estimate.restore_ms,
    )


def assess_restore(
    manifest: EnvironmentSnapshotManifest,
    context: RestoreContext,
    estimate: RestoreEstimate,
) -> RestoreDecision:
    """Select restore only after identity, state, integrity, and economics pass."""

    if manifest.key.digest != context.expected_key_digest:
        return _rebuild(RestoreReason.KEY_MISMATCH, estimate, eligible=False)
    if manifest.tenant_scope_digest != context.tenant_scope_digest:
        return _rebuild(RestoreReason.TENANT_MISMATCH, estimate, eligible=False)
    if manifest.trust_namespace != context.trust_namespace:
        return _rebuild(RestoreReason.TRUST_NAMESPACE_MISMATCH, estimate, eligible=False)

    state_reason = {
        SnapshotStatus.BUILDING: RestoreReason.SNAPSHOT_NOT_READY,
        SnapshotStatus.SEALED: RestoreReason.SNAPSHOT_NOT_READY,
        SnapshotStatus.EXPIRED: RestoreReason.SNAPSHOT_EXPIRED,
        SnapshotStatus.REVOKED: RestoreReason.SNAPSHOT_REVOKED,
        SnapshotStatus.CORRUPT: RestoreReason.SNAPSHOT_CORRUPT,
        SnapshotStatus.QUARANTINED: RestoreReason.SNAPSHOT_QUARANTINED,
    }.get(manifest.status)
    if state_reason is not None:
        return _rebuild(state_reason, estimate, eligible=False)
    if manifest.status is not SnapshotStatus.READY:
        return _rebuild(RestoreReason.SNAPSHOT_NOT_READY, estimate, eligible=False)
    if manifest.expires_at is not None and context.now >= manifest.expires_at:
        return _rebuild(RestoreReason.SNAPSHOT_EXPIRED, estimate, eligible=False)
    if context.observed_manifest_digest != manifest.manifest_digest:
        return _rebuild(RestoreReason.MANIFEST_DIGEST_MISMATCH, estimate, eligible=False)
    if context.verified_layer_digests != manifest.layer_digests:
        return _rebuild(RestoreReason.LAYER_VERIFICATION_FAILED, estimate, eligible=False)

    if estimate.restore_ms >= estimate.rebuild_ms * estimate.maximum_restore_ratio:
        return _rebuild(
            RestoreReason.RESTORE_MORE_EXPENSIVE_THAN_REBUILD,
            estimate,
            eligible=True,
        )
    savings = estimate.rebuild_ms - estimate.restore_ms
    if savings < estimate.minimum_savings_ms:
        return _rebuild(RestoreReason.SAVINGS_BELOW_POLICY_FLOOR, estimate, eligible=True)
    return RestoreDecision(
        action=RestoreAction.RESTORE,
        reason=RestoreReason.RESTORE_VERIFIED,
        eligible=True,
        restore_ms=estimate.restore_ms,
        rebuild_ms=estimate.rebuild_ms,
        net_savings_ms=savings,
    )
