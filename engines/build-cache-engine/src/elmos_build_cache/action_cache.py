"""The Action Cache: ActionKey -> immutable ActionResult manifest.

Entries reference CAS manifests, never a mutable output folder, so a hit
restores exactly the bytes that were validated. A lookup is a *policy*
decision, not just a dictionary probe: schema compatibility, tenancy, trust
namespace, provenance, expiry, revocation, artifact presence and validation
level are all checked, and every rejection produces a structured miss reason
rather than a bare ``None``.

Nondeterminism handling is the sharp edge. If one ActionKey ever maps to two
different result-manifest digests, the stage lied about being deterministic:
both results are quarantined and the key is poisoned until a human intervenes.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .canonical import require_digest
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .db.records import ActionCacheRecord
from .enums import (
    ArtifactStorageState,
    CacheEntryStatus,
    CacheMode,
    MissReason,
    TrustNamespace,
    ValidationLevel,
)
from .errors import ConflictError, NondeterministicStage
from .manifests import ActionResultManifest, ExecutionMetrics

RESULT_SCHEMA = "elmos.action-result/v1"


@dataclass(frozen=True)
class LookupRequest:
    tenant_id: str
    action_key: str
    trust_namespace: TrustNamespace = TrustNamespace.BRANCH
    minimum_validation: ValidationLevel = ValidationLevel.TEST_VERIFIED
    accepted_schemas: tuple[str, ...] = (RESULT_SCHEMA,)
    mode: CacheMode = CacheMode.READ_WRITE
    estimated_recompute_ms: float | None = None
    require_artifacts_present: bool = True


@dataclass(frozen=True)
class LookupResult:
    hit: bool
    reasons: tuple[MissReason, ...] = ()
    entry: ActionCacheRecord | None = None
    result: dict[str, Any] | None = None
    result_digest: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def missed(self) -> bool:
        return not self.hit


@dataclass(frozen=True)
class CommitRequest:
    tenant_id: str
    action_key: str
    manifest: ActionResultManifest
    trust_namespace: TrustNamespace = TrustNamespace.BRANCH
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED
    producer_identity: str = "unknown"
    provenance_digest: str | None = None
    expires_at: float | None = None
    mode: CacheMode = CacheMode.READ_WRITE


@dataclass(frozen=True)
class CommitResult:
    committed: bool
    result_digest: str
    conflict: bool = False
    reason: str | None = None


class HotIndex:
    """Bounded in-memory acceleration. Never authoritative: it only skips a
    database read for keys we have already resolved in this process."""

    def __init__(self, capacity: int = 4096) -> None:
        self.capacity = capacity
        self._entries: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, tenant: str, namespace: str, key: str) -> str | None:
        composite = (tenant, namespace, key)
        if composite in self._entries:
            self._entries.move_to_end(composite)
            self.hits += 1
            return self._entries[composite]
        self.misses += 1
        return None

    def put(self, tenant: str, namespace: str, key: str, result_digest: str) -> None:
        composite = (tenant, namespace, key)
        self._entries[composite] = result_digest
        self._entries.move_to_end(composite)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)

    def invalidate(self, tenant: str, namespace: str, key: str) -> None:
        self._entries.pop((tenant, namespace, key), None)


class ActionCache:
    def __init__(
        self,
        store: MetadataStore,
        cas: ContentAddressableStore,
        clock: Clock = SYSTEM_CLOCK,
        negative_ttl_seconds: float = 900.0,
        hot_index: HotIndex | None = None,
    ) -> None:
        self.store = store
        self.cas = cas
        self.clock = clock
        self.negative_ttl_seconds = negative_ttl_seconds
        self.hot_index = hot_index if hot_index is not None else HotIndex()

    # -- lookup -----------------------------------------------------------
    def lookup(self, request: LookupRequest) -> LookupResult:
        require_digest(request.action_key)
        if request.mode is CacheMode.BYPASS or not request.mode.may_read:
            return LookupResult(False, (MissReason.POLICY_BYPASS,))
        if request.mode is CacheMode.REFRESH:
            return LookupResult(False, (MissReason.POLICY_BYPASS,), detail={"mode": "refresh"})

        entry = self.store.get_action_entry(
            request.tenant_id, request.trust_namespace, request.action_key
        )
        if entry is None:
            # Same tenant only: probing another tenant would leak existence.
            for namespace in TrustNamespace:
                if namespace is request.trust_namespace:
                    continue
                other = self.store.get_action_entry(request.tenant_id, namespace, request.action_key)
                if other is not None and not namespace.satisfies(request.trust_namespace):
                    return LookupResult(
                        False,
                        (MissReason.TRUST_NAMESPACE_MISMATCH,),
                        detail={"found_in": str(namespace), "required": str(request.trust_namespace)},
                    )
            return LookupResult(False, (MissReason.NO_ENTRY,))

        reasons = self._policy_reasons(entry, request)
        if reasons:
            return LookupResult(False, tuple(reasons), entry=entry)

        try:
            document = self.cas.get_document(entry.result_manifest_digest)
        except Exception as exc:  # noqa: BLE001 - normalised into a miss reason
            reason = (
                MissReason.ARTIFACT_CORRUPT
                if exc.__class__.__name__ == "CorruptObject"
                else MissReason.ARTIFACT_MISSING
            )
            return LookupResult(False, (reason,), entry=entry, detail={"error": str(exc)})

        if not isinstance(document, dict) or document.get("kind") not in request.accepted_schemas:
            return LookupResult(
                False,
                (MissReason.SCHEMA_INCOMPATIBLE,),
                entry=entry,
                detail={"kind": document.get("kind") if isinstance(document, dict) else None},
            )

        if entry.entry_kind == "NEGATIVE":
            return LookupResult(
                False,
                (MissReason.NO_ENTRY,),
                entry=entry,
                detail={"negative_cache": True, "failure_code": entry.failure_code},
            )

        if request.require_artifacts_present:
            outputs = document.get("output_artifacts", [])
            # Corruption is checked first: a quarantined object is present on
            # disk but unusable, and reporting it as "missing" would send an
            # operator looking for the wrong problem.
            corrupt = [digest for digest in outputs if self.cas.is_quarantined(digest)]
            if corrupt:
                return LookupResult(
                    False, (MissReason.ARTIFACT_CORRUPT,), entry=entry, detail={"corrupt": corrupt[:10]}
                )
            missing = [digest for digest in outputs if not self.cas.contains(digest)]
            if missing:
                return LookupResult(
                    False, (MissReason.ARTIFACT_MISSING,), entry=entry, detail={"missing": missing[:10]}
                )

        if request.estimated_recompute_ms is not None:
            restore_ms = sum(
                self.cas.estimate_restore(digest).estimated_restore_ms
                for digest in document.get("output_artifacts", [])
                if self.cas.contains(digest)
            )
            if restore_ms > request.estimated_recompute_ms:
                return LookupResult(
                    False,
                    (MissReason.RESTORE_COST_EXCEEDS_RECOMPUTE,),
                    entry=entry,
                    detail={"restore_ms": restore_ms, "recompute_ms": request.estimated_recompute_ms},
                )

        self.store.record_action_hit(request.tenant_id, request.trust_namespace, request.action_key)
        for digest in document.get("output_artifacts", []):
            self.store.touch_artifact(request.tenant_id, digest)
        self.hot_index.put(
            request.tenant_id,
            str(request.trust_namespace),
            request.action_key,
            entry.result_manifest_digest,
        )
        return LookupResult(
            True,
            (),
            entry=entry,
            result=document,
            result_digest=entry.result_manifest_digest,
            detail={"validation_level": str(entry.validation_level)},
        )

    def _policy_reasons(self, entry: ActionCacheRecord, request: LookupRequest) -> list[MissReason]:
        reasons: list[MissReason] = []
        now = self.clock.now()
        if entry.tenant_id != request.tenant_id:
            reasons.append(MissReason.TENANT_MISMATCH)
        if not entry.trust_namespace.satisfies(request.trust_namespace):
            reasons.append(MissReason.TRUST_NAMESPACE_MISMATCH)
        if entry.status is CacheEntryStatus.QUARANTINED:
            reasons.append(MissReason.ENTRY_QUARANTINED)
        if entry.status is CacheEntryStatus.REVOKED:
            reasons.append(MissReason.ENTRY_REVOKED)
        if entry.status is CacheEntryStatus.EXPIRED:
            reasons.append(MissReason.ENTRY_EXPIRED)
        if entry.expires_at is not None and entry.expires_at <= now:
            reasons.append(MissReason.ENTRY_EXPIRED)
        if self.store.is_revoked(entry.tenant_id, "action_key", entry.action_key):
            reasons.append(MissReason.ENTRY_REVOKED)
        if self.store.is_revoked(entry.tenant_id, "artifact", entry.result_manifest_digest):
            reasons.append(MissReason.ENTRY_REVOKED)
        if not entry.provenance_digest:
            reasons.append(MissReason.PROVENANCE_INVALID)
        if entry.entry_kind == "POSITIVE" and not entry.validation_level.satisfies(
            request.minimum_validation
        ):
            reasons.append(MissReason.VALIDATION_TOO_LOW)
        # Deduplicate while keeping first-seen order.
        seen: list[MissReason] = []
        for reason in reasons:
            if reason not in seen:
                seen.append(reason)
        return seen

    # -- commit -----------------------------------------------------------
    def commit(self, request: CommitRequest) -> CommitResult:
        require_digest(request.action_key)
        if not request.mode.may_write:
            return CommitResult(False, "", reason="cache mode forbids writes")
        if request.manifest.action_key != request.action_key:
            raise ConflictError(
                "result manifest declares a different ActionKey",
                declared=request.manifest.action_key,
                requested=request.action_key,
            )

        result_digest = request.manifest.store(self.cas)
        self.store.register_artifact(
            request.tenant_id,
            result_digest,
            size_bytes=len(self.cas.get_bytes(result_digest)),
            media_type="application/json",
            artifact_kind="action-result",
            storage_state=ArtifactStorageState.LOCAL,
            validation_level=request.validation_level,
        )
        self.store.add_artifact_ref(
            request.tenant_id, "action_cache", request.action_key, result_digest, "result"
        )
        for digest in request.manifest.output_artifacts:
            # Register before referencing: an edge to an unknown artifact would
            # make the GC reachability walk unsound.
            if self.store.get_artifact(request.tenant_id, digest) is None:
                info = self.cas.info(digest)
                self.store.register_artifact(
                    request.tenant_id,
                    digest,
                    size_bytes=info.size,
                    media_type="application/octet-stream",
                    artifact_kind="stage-output",
                    storage_state=ArtifactStorageState.LOCAL,
                    validation_level=request.validation_level,
                )
            self.store.add_artifact_ref(
                request.tenant_id, "action_result", result_digest, digest, "output"
            )

        existing = self.store.get_action_entry(
            request.tenant_id, request.trust_namespace, request.action_key
        )
        provenance = request.provenance_digest or result_digest
        metrics = request.manifest.metrics

        if existing is None:
            self.store.put_action_entry(
                ActionCacheRecord(
                    tenant_id=request.tenant_id,
                    trust_namespace=request.trust_namespace,
                    action_key=request.action_key,
                    result_manifest_digest=result_digest,
                    validation_level=request.validation_level,
                    producer_identity=request.producer_identity,
                    provenance_digest=provenance,
                    status=CacheEntryStatus.ACTIVE,
                    entry_kind="POSITIVE",
                    expires_at=request.expires_at,
                    saved_cpu_ms=metrics.cpu_ms,
                    saved_wall_ms=metrics.wall_ms,
                    saved_compiler_ms=metrics.compiler_ms,
                    saved_model_tokens=metrics.model_tokens,
                )
            )
            self.hot_index.put(
                request.tenant_id, str(request.trust_namespace), request.action_key, result_digest
            )
            return CommitResult(True, result_digest)

        if existing.result_manifest_digest == result_digest:
            # Idempotent re-commit: only the validation level may ratchet up.
            if request.validation_level.satisfies(existing.validation_level) and (
                request.validation_level != existing.validation_level
            ):
                self.store.update_action_entry(
                    replace(existing, validation_level=request.validation_level)
                )
            return CommitResult(True, result_digest)

        if existing.entry_kind == "NEGATIVE":
            # A real result supersedes a negative-cached deterministic failure.
            self.store.update_action_entry(
                replace(
                    existing,
                    result_manifest_digest=result_digest,
                    validation_level=request.validation_level,
                    producer_identity=request.producer_identity,
                    provenance_digest=provenance,
                    status=CacheEntryStatus.ACTIVE,
                    entry_kind="POSITIVE",
                    failure_code=None,
                    expires_at=request.expires_at,
                )
            )
            return CommitResult(True, result_digest)

        return self._quarantine_nondeterminism(existing, result_digest)

    def _quarantine_nondeterminism(
        self, existing: ActionCacheRecord, new_result_digest: str
    ) -> CommitResult:
        reason = (
            "same ActionKey produced two different result manifests: "
            f"{existing.result_manifest_digest} and {new_result_digest}"
        )
        self.store.update_action_entry(
            replace(
                existing,
                status=CacheEntryStatus.QUARANTINED,
                quarantine_reason=reason,
            )
        )
        for digest in (existing.result_manifest_digest, new_result_digest):
            self.store.set_artifact_state(existing.tenant_id, digest, ArtifactStorageState.QUARANTINED)
            self.cas.quarantine(digest, reason)
        self.hot_index.invalidate(
            existing.tenant_id, str(existing.trust_namespace), existing.action_key
        )
        # Durable before the raise: the caller's transaction context will roll
        # back on the exception, and the quarantine must outlive that rollback.
        self.store.commit()
        raise NondeterministicStage(
            reason,
            action_key=existing.action_key,
            previous=existing.result_manifest_digest,
            current=new_result_digest,
        )

    # -- negative caching -------------------------------------------------
    def commit_negative(
        self,
        tenant_id: str,
        action_key: str,
        failure_code: str,
        deterministic: bool,
        trust_namespace: TrustNamespace = TrustNamespace.BRANCH,
        producer_identity: str = "unknown",
        ttl_seconds: float | None = None,
    ) -> CommitResult:
        """Cache a *deterministic* failure for a bounded time.

        Transient failures (network, quota, rate limit, availability) are never
        cached: they would turn a blip into a sticky error.
        """
        if not deterministic:
            return CommitResult(False, "", reason="transient failures are not negative-cached")
        manifest = ActionResultManifest(
            action_key=action_key,
            stage_id="negative",
            stage_version="0",
            output_artifacts=(),
            exit_status="FAILURE",
            failure_code=failure_code,
            determinism="DETERMINISTIC",
        )
        result_digest = manifest.store(self.cas)
        expires_at = self.clock.now() + (
            ttl_seconds if ttl_seconds is not None else self.negative_ttl_seconds
        )
        existing = self.store.get_action_entry(tenant_id, trust_namespace, action_key)
        record = ActionCacheRecord(
            tenant_id=tenant_id,
            trust_namespace=trust_namespace,
            action_key=action_key,
            result_manifest_digest=result_digest,
            validation_level=ValidationLevel.UNVERIFIED,
            producer_identity=producer_identity,
            provenance_digest=result_digest,
            status=CacheEntryStatus.ACTIVE,
            entry_kind="NEGATIVE",
            failure_code=failure_code,
            expires_at=expires_at,
        )
        if existing is None:
            self.store.put_action_entry(record)
        else:
            self.store.update_action_entry(record)
        return CommitResult(True, result_digest)

    # -- administration ---------------------------------------------------
    def quarantine(self, tenant_id: str, trust_namespace: TrustNamespace, action_key: str, reason: str) -> None:
        entry = self.store.get_action_entry(tenant_id, trust_namespace, action_key)
        if entry is None:
            return
        self.store.update_action_entry(
            replace(entry, status=CacheEntryStatus.QUARANTINED, quarantine_reason=reason)
        )
        self.hot_index.invalidate(tenant_id, str(trust_namespace), action_key)

    def revoke(self, tenant_id: str, trust_namespace: TrustNamespace, action_key: str, reason: str) -> None:
        entry = self.store.get_action_entry(tenant_id, trust_namespace, action_key)
        if entry is not None:
            self.store.update_action_entry(replace(entry, status=CacheEntryStatus.REVOKED))
        self.store.add_revocation(tenant_id, "action_key", action_key, reason)
        self.hot_index.invalidate(tenant_id, str(trust_namespace), action_key)

    def promote_validation(
        self,
        tenant_id: str,
        trust_namespace: TrustNamespace,
        action_key: str,
        level: ValidationLevel,
        verifier_identity: str,
    ) -> ActionCacheRecord | None:
        """Raise an entry's validation level after an independent verifier passed.

        The verifier must differ from the producer: a stage cannot certify its
        own output.
        """
        entry = self.store.get_action_entry(tenant_id, trust_namespace, action_key)
        if entry is None:
            return None
        if entry.status is not CacheEntryStatus.ACTIVE:
            return entry
        if verifier_identity == entry.producer_identity and level.rank >= ValidationLevel.TEST_VERIFIED.rank:
            raise ConflictError(
                "producer-only evidence cannot raise validation level",
                producer=entry.producer_identity,
                level=str(level),
            )
        if not level.satisfies(entry.validation_level):
            return entry
        updated = replace(entry, validation_level=level)
        self.store.update_action_entry(updated)
        return updated

    def statistics(self, tenant_id: str) -> dict[str, Any]:
        entries = self.store.list_action_entries(tenant_id)
        by_status: dict[str, int] = {}
        for entry in entries:
            by_status[str(entry.status)] = by_status.get(str(entry.status), 0) + 1
        return {
            "entries": len(entries),
            "by_status": dict(sorted(by_status.items())),
            "total_hits": sum(entry.hit_count for entry in entries),
            "saved_cpu_ms": sum(entry.saved_cpu_ms * entry.hit_count for entry in entries),
            "saved_wall_ms": sum(entry.saved_wall_ms * entry.hit_count for entry in entries),
            "saved_compiler_ms": sum(entry.saved_compiler_ms * entry.hit_count for entry in entries),
            "saved_model_tokens": sum(entry.saved_model_tokens * entry.hit_count for entry in entries),
            "hot_index": {"hits": self.hot_index.hits, "misses": self.hot_index.misses},
        }


def metrics_from(
    wall_ms: int = 0,
    cpu_ms: int = 0,
    compiler_ms: int = 0,
    model_tokens: int = 0,
    network_bytes: int = 0,
    peak_memory_bytes: int = 0,
) -> ExecutionMetrics:
    return ExecutionMetrics(
        wall_ms=wall_ms,
        cpu_ms=cpu_ms,
        compiler_ms=compiler_ms,
        model_tokens=model_tokens,
        network_bytes=network_bytes,
        peak_memory_bytes=peak_memory_bytes,
    )


def restore_outputs(
    cache: ActionCache, result: dict[str, Any], destination_of: Sequence[tuple[str, Any]]
) -> list[str]:
    """Materialise a hit's outputs; returns the digests actually restored."""
    restored: list[str] = []
    mapping = dict(destination_of)
    for digest in result.get("output_artifacts", []):
        target = mapping.get(digest)
        if target is None:
            continue
        cache.cas.materialize(digest, target)
        restored.append(digest)
    return restored
