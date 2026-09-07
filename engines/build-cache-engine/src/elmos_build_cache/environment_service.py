"""Production environment-snapshot storage and verified restore service.

The service deliberately stops at immutable bytes and references.  It never
executes setup scripts and never writes into a caller workspace.  Snapshot
identity is derived solely from :class:`EnvironmentKeyInputs`; layer bytes are
sealed in the CAS, independently verified, tenant-registered, and described by
the imported ``environment-snapshot`` contract.

The persisted manifest is content-free.  Environment and secret material may
only appear through the digests already enforced by ``EnvironmentKeyInputs``.
Terminal revocation and corruption decisions are appended to the parity
metadata ledger instead of mutating the sealed manifest.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .canonical import canonical_json_bytes, digest_of, require_digest, sha256_bytes
from .cas import ContentAddressableStore, ObjectInfo
from .clock import SYSTEM_CLOCK, Clock, iso
from .db.store import MetadataStore
from .enums import ArtifactStorageState, ValidationLevel
from .environment_cache import (
    EnvironmentKeyInputs,
    EnvironmentSnapshotKey,
    EnvironmentSnapshotManifest,
    RestoreAction,
    RestoreContext,
    RestoreDecision,
    RestoreEstimate,
    RestoreReason,
    SnapshotStatus,
    assess_restore,
    build_environment_snapshot_key,
)
from .errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    DigestMismatch,
    IdempotencyConflict,
    NotFound,
    SchemaInvalid,
    TenantMismatch,
    TrustNamespaceMismatch,
)
from .parity_store import ParityMetadataRepository, validate_environment_manifest_document

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_LAYER_ORDER = {
    "BASE": 0,
    "TOOLCHAIN": 1,
    "DEPENDENCIES": 2,
    "INDEX": 3,
    "PROJECT_WARM_STATE": 4,
}


class EnvironmentLayerType(StrEnum):
    """Closed layer vocabulary from the imported v1.2 schema."""

    BASE = "BASE"
    TOOLCHAIN = "TOOLCHAIN"
    DEPENDENCIES = "DEPENDENCIES"
    INDEX = "INDEX"
    PROJECT_WARM_STATE = "PROJECT_WARM_STATE"


@dataclass(frozen=True)
class EnvironmentSnapshotLimits:
    """Hard in-memory sealing bounds, injectable per deployment profile."""

    max_layers: int = len(_LAYER_ORDER)
    max_layer_bytes: int = 256 * 1024 * 1024
    max_total_bytes: int = 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        for field in ("max_layers", "max_layer_bytes", "max_total_bytes"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ContractViolation(f"{field} must be a positive integer")


@dataclass(frozen=True)
class EnvironmentLayerPayload:
    """One immutable, typed layer supplied for sealing."""

    layer_type: EnvironmentLayerType
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.layer_type, EnvironmentLayerType):
            raise ContractViolation("environment layer type is outside the closed vocabulary")
        if not isinstance(self.content, bytes):
            raise ContractViolation("environment layer content must be immutable bytes")


@dataclass(frozen=True)
class EnvironmentLayerRef:
    layer_type: EnvironmentLayerType
    digest: str
    size_bytes: int
    stored_size: int
    compression: str

    def __post_init__(self) -> None:
        require_digest(self.digest)
        for field in ("size_bytes", "stored_size"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractViolation(f"{field} must be a non-negative integer")
        if self.compression not in {"none", "gzip"}:
            raise ContractViolation("environment layer compression is unsupported")

    def manifest_entry(self) -> dict[str, object]:
        return {
            "layer_type": self.layer_type.value,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class VerifiedEnvironmentLayer:
    """Digest-verified bytes returned to a caller without materialisation."""

    ref: EnvironmentLayerRef
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise ContractViolation("verified environment content must be immutable bytes")
        if len(self.content) != self.ref.size_bytes or sha256_bytes(self.content) != self.ref.digest:
            raise ContractViolation("verified environment layer bytes do not match their reference")


@dataclass(frozen=True)
class WarmLayerInventory:
    """Advisory target inventory used only for transfer-cost estimation.

    Writable inventories are never trusted.  An inventory influences a restore
    decision only when tenant, project and trust namespace all match exactly.
    It grants no access to bytes and cannot bypass CAS verification.
    """

    tenant_id: str
    project_id: str
    trust_namespace: str
    layer_digests: tuple[str, ...]
    writable: bool = False

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        _identifier(self.trust_namespace, "trust_namespace")
        for digest in self.layer_digests:
            require_digest(digest)
        if len(self.layer_digests) != len(set(self.layer_digests)):
            raise ContractViolation("warm inventory contains duplicate layer digests")
        object.__setattr__(self, "layer_digests", tuple(sorted(self.layer_digests)))

    def reusable_digests(
        self,
        tenant_id: str,
        project_id: str,
        trust_namespace: str,
    ) -> frozenset[str]:
        if self.writable:
            return frozenset()
        if (
            self.tenant_id != tenant_id
            or self.project_id != project_id
            or self.trust_namespace != trust_namespace
        ):
            return frozenset()
        return frozenset(self.layer_digests)


@dataclass(frozen=True)
class RestoreCostPolicy:
    """Measured rates used for the restore-versus-rebuild choice."""

    rebuild_ms: float
    transfer_bytes_per_ms: float = 200_000.0
    decompression_bytes_per_ms: float = 500_000.0
    verification_bytes_per_ms: float = 750_000.0
    minimum_savings_ms: float = 0.0
    maximum_restore_ratio: float = 1.0

    def __post_init__(self) -> None:
        for field in (
            "rebuild_ms",
            "transfer_bytes_per_ms",
            "decompression_bytes_per_ms",
            "verification_bytes_per_ms",
            "minimum_savings_ms",
            "maximum_restore_ratio",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ContractViolation(f"{field} must be numeric")
            number = float(value)
            if not math.isfinite(number) or number < 0:
                raise ContractViolation(f"{field} must be finite and non-negative")
            object.__setattr__(self, field, number)
        if self.rebuild_ms <= 0:
            raise ContractViolation("rebuild_ms must be greater than zero")
        for field in (
            "transfer_bytes_per_ms",
            "decompression_bytes_per_ms",
            "verification_bytes_per_ms",
        ):
            if getattr(self, field) <= 0:
                raise ContractViolation(f"{field} must be greater than zero")
        if self.maximum_restore_ratio > 1.0:
            raise ContractViolation("maximum_restore_ratio cannot exceed 1.0")

    def empty_estimate(self) -> RestoreEstimate:
        return RestoreEstimate(
            transfer_ms=0.0,
            decompression_ms=0.0,
            verification_ms=0.0,
            rebuild_ms=self.rebuild_ms,
            minimum_savings_ms=self.minimum_savings_ms,
            maximum_restore_ratio=self.maximum_restore_ratio,
        )

    def estimate(
        self,
        layer_info: Sequence[tuple[EnvironmentLayerRef, ObjectInfo]],
        warm_digests: frozenset[str],
    ) -> RestoreEstimate:
        transferred = sum(
            info.stored_size for ref, info in layer_info if ref.digest not in warm_digests
        )
        decompressed = sum(info.size for _, info in layer_info if info.compressed)
        verified = sum(info.size for _, info in layer_info)
        return RestoreEstimate(
            transfer_ms=transferred / self.transfer_bytes_per_ms,
            decompression_ms=decompressed / self.decompression_bytes_per_ms,
            verification_ms=verified / self.verification_bytes_per_ms,
            rebuild_ms=self.rebuild_ms,
            minimum_savings_ms=self.minimum_savings_ms,
            maximum_restore_ratio=self.maximum_restore_ratio,
        )


@dataclass(frozen=True)
class SealedEnvironmentSnapshot:
    key: EnvironmentSnapshotKey
    snapshot_id: str
    manifest: Mapping[str, Any]
    manifest_digest: str
    layers: tuple[EnvironmentLayerRef, ...]
    effective_status: str


@dataclass(frozen=True)
class EnvironmentRestoreResult:
    decision: RestoreDecision
    snapshot_key: str
    manifest_digest: str
    layer_refs: tuple[EnvironmentLayerRef, ...]
    verified_layers: tuple[VerifiedEnvironmentLayer, ...]
    warm_inventory_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_digest(self.snapshot_key)
        require_digest(self.manifest_digest)
        if self.decision.action is RestoreAction.RESTORE:
            if tuple(item.ref for item in self.verified_layers) != self.layer_refs:
                raise ContractViolation("a restore result must contain every verified layer")
        elif self.verified_layers:
            raise ContractViolation("a rebuild decision cannot return layer bytes")


@dataclass(frozen=True)
class EnvironmentSnapshotInspection:
    """Server-verified lookup result that never returns environment bytes."""

    decision: RestoreDecision
    snapshot_key: str
    manifest: Mapping[str, Any]
    manifest_digest: str
    layer_refs: tuple[EnvironmentLayerRef, ...]
    verified_layer_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        require_digest(self.snapshot_key)
        require_digest(self.manifest_digest)
        if self.verified_layer_digests != tuple(ref.digest for ref in self.layer_refs):
            raise ContractViolation("an inspection must verify every referenced environment layer")


class EnvironmentSnapshotService:
    """Seal, look up, revoke, and verify environment snapshots."""

    def __init__(
        self,
        store: MetadataStore,
        cas: ContentAddressableStore,
        repository: ParityMetadataRepository | None = None,
        clock: Clock = SYSTEM_CLOCK,
        limits: EnvironmentSnapshotLimits | None = None,
    ) -> None:
        self.store = store
        self.cas = cas
        self.repository = repository or ParityMetadataRepository(store)
        self.clock = clock
        self.limits = limits or EnvironmentSnapshotLimits()
        if not isinstance(self.limits, EnvironmentSnapshotLimits):
            raise ContractViolation("limits must be EnvironmentSnapshotLimits")
        if self.repository.store is not store:
            raise ContractViolation("environment repository and metadata store must share a transaction domain")

    def _ensure_project_scope(self, tenant_id: str, project_id: str) -> None:
        """Claim a missing project or reject a conflicting owner before CAS writes."""

        with self.store.transaction():
            row = self.store.query_one(
                "SELECT tenant_id FROM projects WHERE project_id=?",
                (project_id,),
            )
            if row is None:
                self.store.ensure_project(tenant_id, project_id)
                row = self.store.query_one(
                    "SELECT tenant_id FROM projects WHERE project_id=?",
                    (project_id,),
                )
            if row is None or str(row[0]) != tenant_id:
                raise TenantMismatch(
                    "project does not exist in the requested tenant scope",
                    tenant_id=tenant_id,
                    project_id=project_id,
                )

    def seal(
        self,
        tenant_id: str,
        project_id: str,
        trust_namespace: str,
        key_inputs: EnvironmentKeyInputs,
        layers: Sequence[EnvironmentLayerPayload],
        *,
        expires_at: float | None = None,
    ) -> SealedEnvironmentSnapshot:
        """Seal typed bytes and persist one immutable, schema-valid manifest."""

        _scope(tenant_id, project_id, trust_namespace)
        if not isinstance(key_inputs, EnvironmentKeyInputs):
            raise ContractViolation("key_inputs must be EnvironmentKeyInputs")
        now = self.clock.now()
        if expires_at is not None:
            _finite_timestamp(expires_at, "expires_at")
            if expires_at <= now:
                raise ContractViolation("environment snapshot expiry must be in the future")
        ordered_payloads = _ordered_payloads(layers, self.limits)
        key = build_environment_snapshot_key(key_inputs)
        prospective_refs = tuple(
            EnvironmentLayerRef(
                payload.layer_type,
                sha256_bytes(payload.content),
                len(payload.content),
                len(payload.content),
                "none",
            )
            for payload in ordered_payloads
        )
        prospective_manifest = _manifest_document(
            tenant_id,
            project_id,
            trust_namespace,
            key,
            prospective_refs,
            expires_at,
        )
        validate_environment_manifest_document(prospective_manifest)

        # Input byte digests and sizes fully determine the immutable manifest.
        # Resolve a completed key before any CAS or artifact mutation so drift
        # cannot leave orphan objects or tenant metadata behind.
        existing = self.repository.get_environment_snapshot(
            tenant_id,
            project_id,
            key.digest,
        )
        if existing is not None:
            if existing != prospective_manifest:
                raise IdempotencyConflict(
                    "environment snapshot key was replayed with different layers or policy",
                    snapshot_key=key.digest,
                )
            state = self.repository.get_environment_snapshot_state(
                tenant_id,
                project_id,
                key.digest,
            )
            if state is None:  # pragma: no cover - immutable repository invariant
                raise NotFound("sealed environment snapshot disappeared")
            manifest_digest = require_digest(str(state["manifest_digest"]))
            if manifest_digest != digest_of(existing):
                raise CorruptObject("stored environment manifest digest does not match its bytes")
            return SealedEnvironmentSnapshot(
                key=key,
                snapshot_id=str(existing["snapshot_id"]),
                manifest=dict(existing),
                manifest_digest=manifest_digest,
                layers=_refs_from_manifest(existing, self.cas),
                effective_status=str(state["effective_status"]),
            )

        self._ensure_project_scope(tenant_id, project_id)

        refs: list[EnvironmentLayerRef] = []
        for payload in ordered_payloads:
            digest = self.cas.put_bytes(
                payload.content,
                artifact_kind=f"environment-snapshot-{payload.layer_type.value.lower()}",
            )
            # ``put_bytes`` converges when an object already exists.  Always
            # read it back so convergence cannot conceal pre-existing damage.
            observed = self.cas.get_bytes(digest, verify=True)
            if observed != payload.content:
                self.cas.quarantine(digest, "environment layer replay returned different bytes")
                raise CorruptObject("environment layer replay returned different bytes", digest=digest)
            info = self.cas.info(digest)
            ref = _ref(payload.layer_type, info)
            refs.append(ref)
            self._register_layer(tenant_id, key.digest, ref)

        layer_refs = tuple(refs)
        manifest = prospective_manifest
        manifest_digest = self.cas.put_document(
            manifest,
            artifact_kind="environment-snapshot-manifest",
        )
        if manifest_digest != digest_of(manifest) or not self.cas.verify(manifest_digest):
            raise CorruptObject("environment snapshot manifest failed CAS verification")

        stored = self.repository.put_environment_snapshot(
            tenant_id,
            project_id,
            key.digest,
            manifest,
        )
        if stored != manifest:
            raise IdempotencyConflict("persisted environment snapshot differs from the sealed manifest")

        with self.store.transaction():
            self.store.register_artifact(
                tenant_id,
                manifest_digest,
                len(self.cas.get_bytes(manifest_digest, verify=True)),
                "application/json",
                "environment-snapshot-manifest",
                storage_state=ArtifactStorageState.LOCAL,
                validation_level=ValidationLevel.UNVERIFIED,
                metadata={"snapshot_key": key.digest, "content_free": True},
            )
            self.store.add_artifact_ref(
                tenant_id,
                "environment-snapshot",
                str(manifest["snapshot_id"]),
                manifest_digest,
                "manifest",
            )
            for ref in layer_refs:
                self.store.add_artifact_ref(
                    tenant_id,
                    "environment-snapshot",
                    str(manifest["snapshot_id"]),
                    ref.digest,
                    f"layer:{ref.layer_type.value}",
                )

        state = self.repository.get_environment_snapshot_state(
            tenant_id,
            project_id,
            key.digest,
        )
        if state is None:  # pragma: no cover - persistence contract guard
            raise NotFound("sealed environment snapshot disappeared")
        return SealedEnvironmentSnapshot(
            key=key,
            snapshot_id=str(manifest["snapshot_id"]),
            manifest=dict(manifest),
            manifest_digest=manifest_digest,
            layers=layer_refs,
            effective_status=str(state["effective_status"]),
        )

    def inspect(
        self,
        tenant_id: str,
        project_id: str,
        trust_namespace: str,
        snapshot_key: str,
        estimate: RestoreEstimate,
        *,
        now: float | None = None,
    ) -> EnvironmentSnapshotInspection:
        """Verify one stored snapshot by key and return metadata plus economics.

        This is the control-plane lookup path. It deliberately derives all
        integrity observations from tenant-bound metadata and verified CAS
        reads; callers provide only the economic estimate.
        """

        _scope(tenant_id, project_id, trust_namespace)
        key = require_digest(snapshot_key)
        if not isinstance(estimate, RestoreEstimate):
            raise ContractViolation("estimate must be a RestoreEstimate")
        moment = self.clock.now() if now is None else _finite_timestamp(now, "now")
        state = self.repository.get_environment_snapshot_state(
            tenant_id,
            project_id,
            key,
        )
        if state is None:
            raise NotFound(
                "environment snapshot is not present in the exact tenant/project scope",
                snapshot_key=key,
            )
        effective_status = str(state.get("effective_status"))
        if effective_status != "AVAILABLE":
            raise ConflictError(
                "environment snapshot is not available",
                snapshot_key=key,
                status=effective_status,
            )

        raw_manifest = state.get("manifest")
        if not isinstance(raw_manifest, Mapping):
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "MANIFEST_NOT_OBJECT",
            )
            raise CorruptObject("stored environment snapshot manifest is malformed")
        manifest = dict(raw_manifest)
        try:
            validate_environment_manifest_document(manifest)
        except (ContractViolation, SchemaInvalid) as exc:
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "MANIFEST_SHAPE_INVALID",
            )
            raise CorruptObject("stored environment snapshot manifest is malformed") from exc
        if manifest.get("snapshot_key") != key:
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "SNAPSHOT_KEY_MISMATCH",
            )
            raise CorruptObject("environment snapshot key does not match the lookup key")
        if manifest.get("trust_namespace") != trust_namespace:
            raise TrustNamespaceMismatch(
                "environment snapshot trust namespace does not match",
                expected=trust_namespace,
                actual=manifest.get("trust_namespace"),
            )
        expires_at = _optional_timestamp(manifest.get("expires_at"), "expires_at")
        if expires_at is not None and moment >= expires_at:
            raise ConflictError("environment snapshot has expired", snapshot_key=key)

        try:
            manifest_digest = require_digest(str(state.get("manifest_digest")))
        except DigestMismatch as exc:
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "MANIFEST_DIGEST_INVALID",
            )
            raise CorruptObject("environment manifest digest is invalid") from exc
        canonical_manifest = canonical_json_bytes(manifest)
        if manifest_digest != digest_of(manifest):
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "MANIFEST_DIGEST_MISMATCH",
            )
            raise CorruptObject("environment manifest digest verification failed")

        try:
            refs = _refs_from_manifest(manifest, self.cas)
        except (ContractViolation, DigestMismatch) as exc:
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "LAYER_REFERENCE_INVALID",
            )
            raise CorruptObject("environment layer references are invalid") from exc
        snapshot_id = str(manifest["snapshot_id"])
        targets = set(
            self.store.artifact_targets(
                tenant_id,
                "environment-snapshot",
                snapshot_id,
            )
        )
        expected_targets = {manifest_digest, *(ref.digest for ref in refs)}
        if not expected_targets <= targets:
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "ARTIFACT_REFERENCE_MISSING",
            )
            raise CorruptObject("environment snapshot artifact binding is incomplete")

        manifest_artifact = self.store.get_artifact(tenant_id, manifest_digest)
        if (
            manifest_artifact is None
            or manifest_artifact.size_bytes != len(canonical_manifest)
            or manifest_artifact.storage_state is not ArtifactStorageState.LOCAL
            or manifest_artifact.validation_level is ValidationLevel.QUARANTINED
        ):
            self._record_integrity_failure(
                tenant_id,
                project_id,
                key,
                "MANIFEST_ARTIFACT_NOT_SERVABLE",
            )
            raise CorruptObject("environment manifest artifact is not tenant-bound and servable")
        try:
            stored_manifest = self.cas.get_bytes(manifest_digest, verify=True)
        except (NotFound, CorruptObject, OSError, ValueError, KeyError) as exc:
            self._quarantine_corruption(
                tenant_id,
                project_id,
                key,
                manifest_digest,
                type(exc).__name__,
            )
            raise CorruptObject("environment manifest CAS verification failed") from exc
        if stored_manifest != canonical_manifest:
            self._quarantine_corruption(
                tenant_id,
                project_id,
                key,
                manifest_digest,
                "CANONICAL_MANIFEST_MISMATCH",
            )
            raise CorruptObject("environment manifest CAS bytes are not canonical")

        verified_digests: list[str] = []
        for ref in refs:
            artifact = self.store.get_artifact(tenant_id, ref.digest)
            if (
                artifact is None
                or artifact.size_bytes != ref.size_bytes
                or artifact.storage_state is not ArtifactStorageState.LOCAL
                or artifact.validation_level is ValidationLevel.QUARANTINED
            ):
                self._record_integrity_failure(
                    tenant_id,
                    project_id,
                    key,
                    "LAYER_ARTIFACT_NOT_SERVABLE",
                    ref.digest,
                )
                raise CorruptObject(
                    "environment layer artifact is not tenant-bound and servable",
                    digest=ref.digest,
                )
            try:
                content = self.cas.get_bytes(ref.digest, verify=True)
            except (NotFound, CorruptObject, OSError, ValueError, KeyError) as exc:
                self._quarantine_corruption(
                    tenant_id,
                    project_id,
                    key,
                    ref.digest,
                    type(exc).__name__,
                )
                raise CorruptObject(
                    "environment layer CAS verification failed",
                    digest=ref.digest,
                ) from exc
            if len(content) != ref.size_bytes:
                self._record_integrity_failure(
                    tenant_id,
                    project_id,
                    key,
                    "LAYER_SIZE_MISMATCH",
                    ref.digest,
                )
                raise CorruptObject(
                    "environment layer size verification failed",
                    digest=ref.digest,
                )
            verified_digests.append(ref.digest)

        decision = _economic_restore_decision(estimate)
        return EnvironmentSnapshotInspection(
            decision=decision,
            snapshot_key=key,
            manifest=manifest,
            manifest_digest=manifest_digest,
            layer_refs=refs,
            verified_layer_digests=tuple(verified_digests),
        )

    def restore(
        self,
        tenant_id: str,
        project_id: str,
        trust_namespace: str,
        key_inputs: EnvironmentKeyInputs,
        cost_policy: RestoreCostPolicy,
        *,
        warm_inventory: Sequence[WarmLayerInventory] = (),
        now: float | None = None,
    ) -> EnvironmentRestoreResult:
        """Return verified bytes when identity, state, integrity and cost pass."""

        _scope(tenant_id, project_id, trust_namespace)
        if not isinstance(key_inputs, EnvironmentKeyInputs):
            raise ContractViolation("key_inputs must be EnvironmentKeyInputs")
        if not isinstance(cost_policy, RestoreCostPolicy):
            raise ContractViolation("cost_policy must be RestoreCostPolicy")
        moment = self.clock.now() if now is None else _finite_timestamp(now, "now")
        key = build_environment_snapshot_key(key_inputs)
        state = self.repository.get_environment_snapshot_state(
            tenant_id,
            project_id,
            key.digest,
        )
        if state is None:
            raise NotFound(
                "environment snapshot is not present in the exact tenant/project scope",
                snapshot_key=key.digest,
            )
        document = state["manifest"]
        if not isinstance(document, Mapping):
            raise ContractViolation("stored environment snapshot manifest is malformed")
        manifest = dict(document)
        validate_environment_manifest_document(manifest)
        manifest_digest = str(state["manifest_digest"])
        require_digest(manifest_digest)
        if str(manifest.get("snapshot_key")) != key.digest:
            return self._failed_result(
                RestoreReason.KEY_MISMATCH,
                cost_policy,
                key.digest,
                manifest_digest,
            )

        refs = _refs_from_manifest(manifest, self.cas)
        internal = _internal_manifest(
            tenant_id,
            project_id,
            key,
            manifest,
            refs,
            str(state["effective_status"]),
            moment,
        )
        preflight = assess_restore(
            internal,
            RestoreContext(
                expected_key_digest=key.digest,
                tenant_scope_digest=_tenant_scope_digest(tenant_id, project_id),
                trust_namespace=trust_namespace,
                observed_manifest_digest=internal.manifest_digest,
                verified_layer_digests=internal.layer_digests,
                now=moment,
            ),
            cost_policy.empty_estimate(),
        )
        if preflight.action is RestoreAction.REBUILD:
            return EnvironmentRestoreResult(
                decision=preflight,
                snapshot_key=key.digest,
                manifest_digest=manifest_digest,
                layer_refs=refs,
                verified_layers=(),
            )

        expected_document = _manifest_document(
            tenant_id,
            project_id,
            internal.trust_namespace,
            key,
            refs,
            _optional_timestamp(manifest.get("expires_at"), "expires_at"),
        )
        if manifest != expected_document or manifest_digest != digest_of(manifest):
            return self._failed_result(
                RestoreReason.MANIFEST_DIGEST_MISMATCH,
                cost_policy,
                key.digest,
                manifest_digest,
                refs,
            )

        # Restore may return bytes only after passing the exact same manifest
        # CAS, tenant artifact-reference, artifact-state, and all-layer checks
        # used by the control-plane inspection path. Layers are read again
        # below so a post-inspection race still cannot return unverified bytes.
        try:
            inspection = self.inspect(
                tenant_id,
                project_id,
                trust_namespace,
                key.digest,
                cost_policy.empty_estimate(),
                now=moment,
            )
        except CorruptObject:
            return self._failed_result(
                RestoreReason.LAYER_VERIFICATION_FAILED,
                cost_policy,
                key.digest,
                manifest_digest,
                refs,
            )
        manifest_digest = inspection.manifest_digest
        refs = inspection.layer_refs

        verified: list[VerifiedEnvironmentLayer] = []
        info: list[tuple[EnvironmentLayerRef, ObjectInfo]] = []
        failed_digest: str | None = None
        for ref in refs:
            artifact = self.store.get_artifact(tenant_id, ref.digest)
            if (
                artifact is None
                or artifact.size_bytes != ref.size_bytes
                or artifact.storage_state is not ArtifactStorageState.LOCAL
                or artifact.validation_level is ValidationLevel.QUARANTINED
            ):
                failed_digest = ref.digest
                continue
            try:
                content = self.cas.get_bytes(ref.digest, verify=True)
                observed_info = self.cas.info(ref.digest)
                verified.append(VerifiedEnvironmentLayer(ref, content))
                info.append((ref, observed_info))
            except NotFound:
                failed_digest = ref.digest
            except (CorruptObject, OSError, ValueError, KeyError) as exc:
                self._quarantine_corruption(
                    tenant_id,
                    project_id,
                    key.digest,
                    ref.digest,
                    type(exc).__name__,
                )
                failed_digest = ref.digest

        if failed_digest is not None or len(verified) != len(refs):
            reason_digest = digest_of(
                {
                    "kind": "environment-layer-verification-failed",
                    "snapshot_key": key.digest,
                    "layer_digest": failed_digest,
                }
            )
            self._append_quarantine(
                tenant_id,
                project_id,
                key.digest,
                reason_digest,
            )
            return self._failed_result(
                RestoreReason.LAYER_VERIFICATION_FAILED,
                cost_policy,
                key.digest,
                manifest_digest,
                refs,
            )

        warm_digests = frozenset().union(
            *(
                inventory.reusable_digests(tenant_id, project_id, trust_namespace)
                for inventory in warm_inventory
            )
        )
        warm_digests &= frozenset(ref.digest for ref in refs)
        estimate = cost_policy.estimate(info, warm_digests)
        decision = assess_restore(
            internal,
            RestoreContext(
                expected_key_digest=key.digest,
                tenant_scope_digest=_tenant_scope_digest(tenant_id, project_id),
                trust_namespace=trust_namespace,
                observed_manifest_digest=internal.manifest_digest,
                verified_layer_digests=tuple(item.ref.digest for item in verified),
                now=moment,
            ),
            estimate,
        )
        return EnvironmentRestoreResult(
            decision=decision,
            snapshot_key=key.digest,
            manifest_digest=manifest_digest,
            layer_refs=refs,
            verified_layers=tuple(verified) if decision.action is RestoreAction.RESTORE else (),
            warm_inventory_digests=tuple(sorted(warm_digests)),
        )

    def revoke(
        self,
        tenant_id: str,
        project_id: str,
        trust_namespace: str,
        key_inputs: EnvironmentKeyInputs,
        *,
        event_id: str,
        reason_digest: str,
    ) -> Mapping[str, Any]:
        """Append an explicit, irreversible revocation for the exact scope."""

        _scope(tenant_id, project_id, trust_namespace)
        _identifier(event_id, "event_id")
        require_digest(reason_digest)
        key = build_environment_snapshot_key(key_inputs)
        state = self.repository.get_environment_snapshot_state(
            tenant_id,
            project_id,
            key.digest,
        )
        if state is None:
            raise NotFound("environment snapshot is not present in the exact scope")
        manifest = state["manifest"]
        if not isinstance(manifest, Mapping):
            raise ContractViolation("stored environment snapshot manifest is malformed")
        actual_trust = manifest.get("trust_namespace")
        if actual_trust != trust_namespace:
            raise TrustNamespaceMismatch(
                "environment snapshot trust namespace does not match",
                expected=trust_namespace,
                actual=actual_trust,
            )
        return self.repository.append_environment_snapshot_status(
            tenant_id,
            project_id,
            key.digest,
            event_id,
            "AVAILABLE",
            "REVOKED",
            reason_digest,
        )

    def _register_layer(
        self,
        tenant_id: str,
        snapshot_key: str,
        ref: EnvironmentLayerRef,
    ) -> None:
        with self.store.transaction():
            record = self.store.register_artifact(
                tenant_id,
                ref.digest,
                ref.size_bytes,
                "application/octet-stream",
                "environment-snapshot-layer",
                storage_state=ArtifactStorageState.LOCAL,
                validation_level=ValidationLevel.UNVERIFIED,
                metadata={
                    "snapshot_key": snapshot_key,
                    "layer_type": ref.layer_type.value,
                    "immutable": True,
                },
            )
        if record.size_bytes != ref.size_bytes:
            raise IdempotencyConflict(
                "artifact metadata disagrees with environment layer bytes",
                digest=ref.digest,
            )

    def _record_integrity_failure(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
        failure: str,
        artifact_digest: str | None = None,
    ) -> None:
        reason_digest = digest_of(
            {
                "kind": "environment-snapshot-integrity-failure",
                "snapshot_key": snapshot_key,
                "artifact_digest": artifact_digest,
                "failure": failure,
            }
        )
        self._append_quarantine(tenant_id, project_id, snapshot_key, reason_digest)

    def _quarantine_corruption(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
        layer_digest: str,
        failure: str,
    ) -> None:
        if not self.cas.is_quarantined(layer_digest):
            self.cas.quarantine(layer_digest, f"environment restore verification failed: {failure}")
        with self.store.transaction():
            self.store.set_artifact_state(
                tenant_id,
                layer_digest,
                ArtifactStorageState.QUARANTINED,
            )
        reason_digest = digest_of(
            {
                "kind": "environment-layer-corruption",
                "snapshot_key": snapshot_key,
                "layer_digest": layer_digest,
                "failure": failure,
            }
        )
        self._append_quarantine(tenant_id, project_id, snapshot_key, reason_digest)

    def _append_quarantine(
        self,
        tenant_id: str,
        project_id: str,
        snapshot_key: str,
        reason_digest: str,
    ) -> None:
        state = self.repository.get_environment_snapshot_state(
            tenant_id,
            project_id,
            snapshot_key,
        )
        if state is None or state["effective_status"] != "AVAILABLE":
            return
        event_id = f"env-quarantine-{reason_digest.removeprefix('sha256:')[:40]}"
        self.repository.append_environment_snapshot_status(
            tenant_id,
            project_id,
            snapshot_key,
            event_id,
            "AVAILABLE",
            "QUARANTINED",
            reason_digest,
        )

    @staticmethod
    def _failed_result(
        reason: RestoreReason,
        policy: RestoreCostPolicy,
        snapshot_key: str,
        manifest_digest: str,
        refs: tuple[EnvironmentLayerRef, ...] = (),
    ) -> EnvironmentRestoreResult:
        estimate = policy.empty_estimate()
        decision = RestoreDecision(
            action=RestoreAction.REBUILD,
            reason=reason,
            eligible=False,
            restore_ms=estimate.restore_ms,
            rebuild_ms=estimate.rebuild_ms,
            net_savings_ms=estimate.rebuild_ms - estimate.restore_ms,
        )
        return EnvironmentRestoreResult(
            decision=decision,
            snapshot_key=snapshot_key,
            manifest_digest=manifest_digest,
            layer_refs=refs,
            verified_layers=(),
        )


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _scope(tenant_id: str, project_id: str, trust_namespace: str) -> None:
    _identifier(tenant_id, "tenant_id")
    _identifier(project_id, "project_id")
    _identifier(trust_namespace, "trust_namespace")


def _finite_timestamp(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContractViolation(f"{field} must be finite and non-negative")
    return number


def _economic_restore_decision(estimate: RestoreEstimate) -> RestoreDecision:
    savings = estimate.rebuild_ms - estimate.restore_ms
    if estimate.restore_ms >= estimate.rebuild_ms * estimate.maximum_restore_ratio:
        return RestoreDecision(
            RestoreAction.REBUILD,
            RestoreReason.RESTORE_MORE_EXPENSIVE_THAN_REBUILD,
            True,
            estimate.restore_ms,
            estimate.rebuild_ms,
            savings,
        )
    if savings < estimate.minimum_savings_ms:
        return RestoreDecision(
            RestoreAction.REBUILD,
            RestoreReason.SAVINGS_BELOW_POLICY_FLOOR,
            True,
            estimate.restore_ms,
            estimate.rebuild_ms,
            savings,
        )
    return RestoreDecision(
        RestoreAction.RESTORE,
        RestoreReason.RESTORE_VERIFIED,
        True,
        estimate.restore_ms,
        estimate.rebuild_ms,
        savings,
    )


def _optional_timestamp(value: object, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an RFC3339 timestamp or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractViolation(f"{field} is not a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractViolation(f"{field} must include a timezone")
    return parsed.astimezone(UTC).timestamp()


def _ordered_payloads(
    layers: Sequence[EnvironmentLayerPayload],
    limits: EnvironmentSnapshotLimits,
) -> tuple[EnvironmentLayerPayload, ...]:
    if not layers:
        raise ContractViolation("an environment snapshot requires at least one layer")
    if len(layers) > limits.max_layers:
        raise ContractViolation(
            "environment snapshot exceeds the configured layer-count limit",
            layer_count=len(layers),
            max_layers=limits.max_layers,
        )
    observed: set[EnvironmentLayerType] = set()
    ordered: list[EnvironmentLayerPayload] = []
    digests: set[str] = set()
    total_bytes = 0
    for item in layers:
        if not isinstance(item, EnvironmentLayerPayload):
            raise ContractViolation("layers must contain EnvironmentLayerPayload values")
        size_bytes = len(item.content)
        if size_bytes > limits.max_layer_bytes:
            raise ContractViolation(
                "environment layer exceeds the configured byte limit",
                layer_type=item.layer_type.value,
                size_bytes=size_bytes,
                max_layer_bytes=limits.max_layer_bytes,
            )
        total_bytes += size_bytes
        if total_bytes > limits.max_total_bytes:
            raise ContractViolation(
                "environment snapshot exceeds the configured total-byte limit",
                total_bytes=total_bytes,
                max_total_bytes=limits.max_total_bytes,
            )
        if item.layer_type in observed:
            raise ContractViolation("environment snapshot contains a duplicate layer type")
        content_digest = sha256_bytes(item.content)
        if content_digest in digests:
            raise ContractViolation("environment snapshot layers must have distinct byte identities")
        observed.add(item.layer_type)
        digests.add(content_digest)
        ordered.append(item)
    return tuple(sorted(ordered, key=lambda item: _LAYER_ORDER[item.layer_type.value]))


def _ref(layer_type: EnvironmentLayerType, info: ObjectInfo) -> EnvironmentLayerRef:
    return EnvironmentLayerRef(
        layer_type=layer_type,
        digest=info.digest,
        size_bytes=info.size,
        stored_size=info.stored_size,
        compression=info.compression,
    )


def _tenant_scope_digest(tenant_id: str, project_id: str) -> str:
    return digest_of({"tenant_id": tenant_id, "project_id": project_id})


def _manifest_document(
    tenant_id: str,
    project_id: str,
    trust_namespace: str,
    key: EnvironmentSnapshotKey,
    refs: tuple[EnvironmentLayerRef, ...],
    expires_at: float | None,
) -> dict[str, Any]:
    expiry_text = None if expires_at is None else iso(expires_at)
    identity = {
        "tenant_scope_digest": _tenant_scope_digest(tenant_id, project_id),
        "snapshot_key": key.digest,
        "trust_namespace": trust_namespace,
        "layers": [ref.manifest_entry() for ref in refs],
        "expires_at": expiry_text,
    }
    document: dict[str, Any] = {
        "schema_version": "1.2.0",
        "snapshot_id": digest_of({"kind": "environment-snapshot", **identity}),
        "snapshot_key": key.digest,
        "platform": {
            "os": key.inputs.platform.operating_system,
            "arch": key.inputs.platform.architecture,
            "libc": key.inputs.platform.libc,
        },
        "base_image_digest": key.inputs.base_image_digest,
        "lockfile_digests": [digest for _, digest in key.inputs.lockfile_digests],
        "toolchain_digests": [digest for _, digest in key.inputs.toolchain_digests],
        "layers": [ref.manifest_entry() for ref in refs],
        "trust_namespace": trust_namespace,
        "status": "AVAILABLE",
    }
    if key.inputs.setup_script_digests:
        document["setup_script_digest"] = digest_of(list(key.inputs.setup_script_digests))
    if key.inputs.maintenance_script_digests:
        document["maintenance_script_digest"] = digest_of(
            list(key.inputs.maintenance_script_digests)
        )
    if key.inputs.approved_environment_digests:
        document["approved_environment_digest"] = digest_of(
            dict(key.inputs.approved_environment_digests)
        )
    if key.inputs.secret_reference_versions:
        document["secret_reference_digest"] = digest_of(
            [list(pair) for pair in key.inputs.secret_reference_versions]
        )
    if expiry_text is not None:
        document["expires_at"] = expiry_text
    return document


def _refs_from_manifest(
    document: Mapping[str, Any],
    cas: ContentAddressableStore,
) -> tuple[EnvironmentLayerRef, ...]:
    raw_layers = document.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ContractViolation("environment snapshot manifest has no layers")
    refs: list[EnvironmentLayerRef] = []
    observed: set[EnvironmentLayerType] = set()
    for raw in raw_layers:
        if not isinstance(raw, Mapping):
            raise ContractViolation("environment snapshot layer entry is malformed")
        try:
            layer_type = EnvironmentLayerType(str(raw["layer_type"]))
            digest = require_digest(str(raw["digest"]))
            size = raw["size_bytes"]
        except (KeyError, ValueError) as exc:
            raise ContractViolation("environment snapshot layer entry is malformed") from exc
        if layer_type in observed:
            raise ContractViolation("environment snapshot manifest contains a duplicate layer type")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ContractViolation("environment snapshot layer size is invalid")
        try:
            info = cas.info(digest)
        except (NotFound, CorruptObject):
            # Preserve the declared reference so the service can fail closed
            # through its normal verification/quarantine path.
            info = ObjectInfo(digest, size, size, "none", cas.path_for(digest))
        if info.size != size:
            info = ObjectInfo(digest, size, info.stored_size, info.compression, info.path)
        refs.append(_ref(layer_type, info))
        observed.add(layer_type)
    digests = [ref.digest for ref in refs]
    if len(digests) != len(set(digests)):
        raise ContractViolation("environment snapshot manifest contains duplicate layer digests")
    return tuple(sorted(refs, key=lambda ref: _LAYER_ORDER[ref.layer_type.value]))


def _internal_manifest(
    tenant_id: str,
    project_id: str,
    key: EnvironmentSnapshotKey,
    external: Mapping[str, Any],
    refs: tuple[EnvironmentLayerRef, ...],
    effective_status: str,
    now: float,
) -> EnvironmentSnapshotManifest:
    status = {
        "BUILDING": SnapshotStatus.BUILDING,
        "SEALED": SnapshotStatus.SEALED,
        "AVAILABLE": SnapshotStatus.READY,
        "QUARANTINED": SnapshotStatus.QUARANTINED,
        "REVOKED": SnapshotStatus.REVOKED,
    }.get(effective_status)
    if status is None:
        raise ContractViolation("environment snapshot effective status is unknown")
    expires_at = _optional_timestamp(external.get("expires_at"), "expires_at")
    trust_namespace = external.get("trust_namespace")
    if not isinstance(trust_namespace, str):
        raise ContractViolation("environment snapshot trust namespace is malformed")
    return EnvironmentSnapshotManifest(
        snapshot_id=require_digest(str(external.get("snapshot_id"))),
        key=key,
        tenant_scope_digest=_tenant_scope_digest(tenant_id, project_id),
        trust_namespace=trust_namespace,
        layer_digests=tuple(ref.digest for ref in refs),
        status=status,
        size_bytes=sum(ref.size_bytes for ref in refs),
        created_at=0.0,
        expires_at=expires_at,
        revoked_at=now if status is SnapshotStatus.REVOKED else None,
    )
