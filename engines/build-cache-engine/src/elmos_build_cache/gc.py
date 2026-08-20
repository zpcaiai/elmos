"""Retention and garbage collection.

Two-phase, idempotent, and protective by default. The root set is built from
things that are *still needed* -- active runs, checkpoints, pins, published
trees, valid certificates and legal holds -- and anything reachable from a root
is untouchable regardless of age.

Eviction value is not TTL. A large artifact that is cheap to recompute and
rarely reused is a better candidate than a small one that cost an hour of model
tokens, and the scoring makes that explicit.

Deletion is: emit a dry-run plan -> wait a grace period -> delete with receipts.
An interrupted pass resumes from its receipts, so re-running it is safe.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .cache_policy import CacheObject, CachePolicy
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .db import MetadataStore
from .enums import ArtifactStorageState, CacheEntryStatus, CheckpointStatus, RunStatus, StagedFileStatus
from .errors import ConflictError, NotFound, PermissionDenied

SCHEMA_VERSION = "1.0.0"

ACTIVE_RUN_STATES = frozenset(
    {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.RECOVERING, RunStatus.STALE}
)


@dataclass(frozen=True)
class RetentionPolicy:
    successful_run_days: int = 90
    failed_run_days: int = 14
    quarantine_days: int = 30
    grace_hours: int = 24
    protect_published: bool = True
    protect_checkpoints: bool = True
    protect_certificates: bool = True
    quota_bytes: int | None = None
    legal_holds: tuple[str, ...] = ()

    @property
    def grace_seconds(self) -> float:
        return self.grace_hours * 3600.0


@dataclass(frozen=True)
class RootReason:
    digest: str
    kind: str
    source_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"digest": self.digest, "kind": self.kind, "source_id": self.source_id}


@dataclass(frozen=True)
class Candidate:
    digest: str
    size_bytes: int
    age_seconds: float
    validation_level: str
    recompute_cost_ms: int
    expected_reuse: float
    restore_cost_ms: float
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "age_seconds": round(self.age_seconds, 1),
            "validation_level": self.validation_level,
            "recompute_cost_ms": self.recompute_cost_ms,
            "expected_reuse": round(self.expected_reuse, 3),
            "restore_cost_ms": round(self.restore_cost_ms, 2),
            "score": round(self.score, 4),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GcPlan:
    plan_id: str
    tenant_id: str
    protected: tuple[RootReason, ...]
    candidates: tuple[Candidate, ...]
    reclaimable_bytes: int
    created_at: float
    quota_pressure: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "tenant_id": self.tenant_id,
            "protected_count": len(self.protected),
            "protected": [root.to_dict() for root in self.protected[:200]],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "reclaimable_bytes": self.reclaimable_bytes,
            "created_at": self.created_at,
            "quota_pressure": round(self.quota_pressure, 3),
        }


@dataclass
class GarbageCollector:
    store: MetadataStore
    cas: ContentAddressableStore
    tenant_id: str
    policy: RetentionPolicy = field(default_factory=RetentionPolicy)
    clock: Clock = SYSTEM_CLOCK
    #: Optional replacement policy used to *order* deletion candidates.
    #: It never decides what is protected -- the root set does that, and the
    #: policy is told about every root before it is asked anything. A policy
    #: that disagrees with the root set loses.
    replacement: CachePolicy | None = None

    # -- root set ---------------------------------------------------------
    def live_roots(self) -> list[RootReason]:
        """Everything that must survive, with the reason it survives."""
        roots: list[RootReason] = []

        for run in self.store.list_runs(self.tenant_id):
            if run.status in ACTIVE_RUN_STATES:
                for digest in self.store.artifact_targets(self.tenant_id, "run", run.run_id):
                    roots.append(RootReason(digest, "active_run", run.run_id))
                for record in self.store.list_staged_files(run.run_id):
                    if record.artifact_digest and record.status is not StagedFileStatus.ABORTED:
                        roots.append(RootReason(record.artifact_digest, "active_run", run.run_id))
            if run.published_tree_digest and self.policy.protect_published:
                for digest in self.store.artifact_targets(
                    self.tenant_id, "file_tree", run.published_tree_digest
                ):
                    roots.append(RootReason(digest, "published_tree", run.published_tree_digest))
                if run.evidence_bundle_digest:
                    roots.append(
                        RootReason(run.evidence_bundle_digest, "published_tree", run.run_id)
                    )
            if self.policy.protect_checkpoints:
                for checkpoint in self.store.list_checkpoints(run.run_id):
                    if checkpoint.status in (CheckpointStatus.ACTIVE, CheckpointStatus.SUPERSEDED):
                        roots.append(
                            RootReason(checkpoint.manifest_digest, "checkpoint", checkpoint.checkpoint_id)
                        )
                        for digest in self.store.artifact_targets(
                            self.tenant_id, "checkpoint", checkpoint.checkpoint_id
                        ):
                            roots.append(RootReason(digest, "checkpoint", checkpoint.checkpoint_id))

        if self.policy.protect_published:
            for tree_digest in self.store.published_trees(self.tenant_id):
                for digest in self.store.artifact_targets(self.tenant_id, "file_tree", tree_digest):
                    roots.append(RootReason(digest, "published_tree", tree_digest))

        for pin in self.store.list_pins(self.tenant_id, self.clock.now()):
            for digest in self.store.artifact_targets(self.tenant_id, pin["source_kind"], pin["source_id"]):
                roots.append(RootReason(digest, "pin", pin["pin_id"]))
            if pin["source_kind"] == "artifact":
                roots.append(RootReason(pin["source_id"], "pin", pin["pin_id"]))

        for entry in self.store.list_action_entries(self.tenant_id):
            if entry.status is CacheEntryStatus.ACTIVE:
                roots.append(RootReason(entry.result_manifest_digest, "action_cache", entry.action_key))

        for digest in self.policy.legal_holds:
            roots.append(RootReason(digest, "legal_hold", "policy"))

        if self.policy.protect_certificates:
            now = self.clock.now()
            for tree_digest in self.store.published_trees(self.tenant_id):
                for certificate_id in self.store.certificates_for_tree(self.tenant_id, tree_digest):
                    certificate = self.store.get_certificate(certificate_id)
                    if certificate and certificate["status"] == "VALID" and certificate["expires_at"] > now:
                        roots.append(RootReason(certificate["evidence_digest"], "certificate", certificate_id))
                        roots.append(RootReason(tree_digest, "certificate", certificate_id))
        return roots

    def reachable(self, roots: Iterable[RootReason]) -> dict[str, RootReason]:
        """Transitive closure over every recorded reference edge."""
        found: dict[str, RootReason] = {}
        frontier: list[RootReason] = []
        for root in roots:
            if root.digest not in found:
                found[root.digest] = root
                frontier.append(root)
        while frontier:
            current = frontier.pop()
            for kind in ("action_result", "file_tree", "checkpoint", "run", "staged_file"):
                for digest in self.store.artifact_targets(self.tenant_id, kind, current.digest):
                    if digest not in found:
                        reason = RootReason(digest, current.kind, current.source_id)
                        found[digest] = reason
                        frontier.append(reason)
        return found

    # -- scoring ----------------------------------------------------------
    def _score(self, digest: str, metadata: dict[str, Any], size: int, age: float) -> tuple[float, str]:
        """Higher score = better deletion candidate.

        Combines recompute cost, expected reuse, size, restore latency,
        validation level and quota pressure -- TTL alone is not enough.
        """
        recompute_ms = int(metadata.get("recompute_cost_ms", 1000))
        reuse = float(metadata.get("expected_reuse", 0.1))
        try:
            restore_ms = self.cas.estimate_restore(digest).estimated_restore_ms
        except (NotFound, ConflictError):
            restore_ms = 1.0
        validation_weight = {
            "PRODUCTION_CERTIFIED": 8.0,
            "BEHAVIOR_VERIFIED": 4.0,
            "TEST_VERIFIED": 2.0,
            "COMPILE_VERIFIED": 1.5,
            "UNVERIFIED": 1.0,
            "QUARANTINED": 0.2,
        }.get(str(metadata.get("validation_level", "UNVERIFIED")), 1.0)

        keep_value = (recompute_ms * max(reuse, 0.01) * validation_weight) / max(restore_ms, 0.05)
        storage_pressure = size / (1024 * 1024)
        age_factor = 1.0 + age / (86400.0 * 30)
        score = (storage_pressure * age_factor) / max(keep_value, 0.001)
        reason = (
            f"recompute={recompute_ms}ms reuse={reuse:.2f} weight={validation_weight} "
            f"restore={restore_ms:.2f}ms size={size}B"
        )
        return score, reason

    def _order_by_replacement_policy(
        self, candidates: list[Candidate], protected: Mapping[str, RootReason]
    ) -> list[Candidate]:
        """Re-rank deletion candidates using the configured replacement policy.

        The retention score above answers "what is cheapest to lose"; a policy
        such as SIEVE or GDSF additionally knows what the access pattern has
        actually been. Where the two disagree the policy wins on *ordering
        only*: membership of the candidate list is decided entirely by the root
        set, which is fed to the policy first, so no policy can make a
        protected object collectable. An object the policy could not even hold
        at this capacity is the first to go.
        """
        if self.replacement is None or not candidates:
            return candidates
        policy = self.replacement
        for digest in protected:
            policy.protect(digest)
        for candidate in candidates:
            policy.put(
                CacheObject(
                    key=candidate.digest,
                    size_bytes=max(candidate.size_bytes, 1),
                    recompute_ms=float(candidate.recompute_cost_ms),
                    restore_ms=float(candidate.restore_cost_ms),
                    validation_level=candidate.validation_level,
                )
            )
        rank = {key: index for index, key in enumerate(policy.keys())}
        evicted_rank = -1  # sorts ahead of every resident object

        def order(item: Candidate) -> tuple[int, float, str]:
            return (rank.get(item.digest, evicted_rank), -item.score, item.digest)

        return [
            replace(
                candidate,
                reason=(
                    f"{candidate.reason} policy={policy.name.value} "
                    f"rank={rank[candidate.digest]}"
                    if candidate.digest in rank
                    else f"{candidate.reason} policy={policy.name.value} not-resident"
                ),
            )
            for candidate in sorted(candidates, key=order)
        ]

    # -- phase one: plan --------------------------------------------------
    def plan(self, additional_protected: Iterable[str] = ()) -> GcPlan:
        now = self.clock.now()
        roots = self.live_roots()
        roots.extend(RootReason(digest, "explicit", "caller") for digest in additional_protected)
        protected = self.reachable(roots)

        total_bytes = 0
        candidates: list[Candidate] = []
        for artifact in self.store.list_artifacts(self.tenant_id):
            total_bytes += artifact.size_bytes
            if artifact.digest in protected:
                continue
            if artifact.storage_state in (ArtifactStorageState.DELETED, ArtifactStorageState.DELETING):
                continue
            created = artifact.metadata.get("created_at_epoch")
            age = float(now - created) if isinstance(created, int | float) else 0.0
            score, reason = self._score(artifact.digest, artifact.metadata, artifact.size_bytes, age)
            candidates.append(
                Candidate(
                    digest=artifact.digest,
                    size_bytes=artifact.size_bytes,
                    age_seconds=age,
                    validation_level=str(artifact.validation_level),
                    recompute_cost_ms=int(artifact.metadata.get("recompute_cost_ms", 1000)),
                    expected_reuse=float(artifact.metadata.get("expected_reuse", 0.1)),
                    restore_cost_ms=(
                        self.cas.estimate_restore(artifact.digest).estimated_restore_ms
                        if self.cas.contains(artifact.digest)
                        else 0.0
                    ),
                    score=score,
                    reason=reason,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.digest))
        candidates = self._order_by_replacement_policy(candidates, protected)
        quota_pressure = (
            total_bytes / self.policy.quota_bytes if self.policy.quota_bytes else 0.0
        )

        payload = {
            "candidates": [candidate.to_dict() for candidate in candidates],
            "protected": [root.to_dict() for root in protected.values()],
            "created_at": now,
            "quota_pressure": quota_pressure,
        }
        plan_id = self.store.create_gc_plan(self.tenant_id, payload)
        return GcPlan(
            plan_id=plan_id,
            tenant_id=self.tenant_id,
            protected=tuple(protected.values()),
            candidates=tuple(candidates),
            reclaimable_bytes=sum(candidate.size_bytes for candidate in candidates),
            created_at=now,
            quota_pressure=quota_pressure,
        )

    def approve(self, plan_id: str) -> None:
        record = self.store.get_gc_plan(plan_id)
        if record is None:
            raise NotFound("gc plan does not exist", plan_id=plan_id)
        if record["status"] not in ("DRY_RUN", "APPROVED"):
            raise ConflictError("gc plan is not approvable", plan_id=plan_id, status=record["status"])
        self.store.set_gc_plan_status(plan_id, "APPROVED")

    # -- phase two: apply -------------------------------------------------
    def apply(
        self, plan_id: str, principal_can_gc: bool = True, limit: int | None = None
    ) -> dict[str, Any]:
        """Delete with receipts. Re-running after an interruption is a no-op."""
        if not principal_can_gc:
            raise PermissionDenied("garbage collection requires an authorised principal")
        record = self.store.get_gc_plan(plan_id)
        if record is None:
            raise NotFound("gc plan does not exist", plan_id=plan_id)
        if record["status"] not in ("APPROVED", "APPLIED"):
            raise ConflictError("gc plan has not been approved", plan_id=plan_id, status=record["status"])

        now = self.clock.now()
        if now - float(record["created_at"]) < self.policy.grace_seconds:
            raise ConflictError(
                "gc grace period has not elapsed",
                plan_id=plan_id,
                remaining_seconds=self.policy.grace_seconds - (now - float(record["created_at"])),
            )

        # Re-derive protection at apply time: a run may have started since.
        protected = self.reachable(self.live_roots())
        already = {receipt["digest"] for receipt in self.store.gc_receipts(plan_id)}

        deleted = 0
        skipped = 0
        freed = 0
        candidates = record["payload"]["candidates"]
        for candidate in candidates if limit is None else candidates[:limit]:
            digest = candidate["digest"]
            if digest in already:
                continue
            if digest in protected:
                self.store.add_gc_receipt(plan_id, digest, "PROTECTED", "became reachable after planning")
                skipped += 1
                continue
            # Invalidate cache visibility before deleting bytes, never after.
            self.store.set_artifact_state(self.tenant_id, digest, ArtifactStorageState.DELETING)
            removed = self.cas.delete(digest)
            self.store.set_artifact_state(self.tenant_id, digest, ArtifactStorageState.DELETED)
            self.store.delete_artifact_row(self.tenant_id, digest)
            self.store.add_gc_receipt(
                plan_id, digest, "DELETED" if removed else "ALREADY_ABSENT", candidate["reason"]
            )
            deleted += 1
            freed += int(candidate["size_bytes"])

        self.store.set_gc_plan_status(plan_id, "APPLIED", now)
        return {
            "plan_id": plan_id,
            "deleted": deleted,
            "skipped_protected": skipped,
            "freed_bytes": freed,
            "receipts": len(self.store.gc_receipts(plan_id)),
        }

    def abandon(self, plan_id: str) -> None:
        self.store.set_gc_plan_status(plan_id, "ABANDONED")

    # -- reconciliation ---------------------------------------------------
    def reconcile_orphans(self) -> dict[str, list[str]]:
        """Blobs with no metadata row, and rows with no blob. Reported, not deleted."""
        known = {artifact.digest for artifact in self.store.list_artifacts(self.tenant_id)}
        on_disk = set(self.cas.iter_digests())
        return {
            "orphan_blobs": sorted(on_disk - known),
            "orphan_metadata": sorted(known - on_disk),
        }

    def quarantine_retention(self) -> list[str]:
        """Quarantined evidence follows explicit forensic retention, not GC."""
        now = self.clock.now()
        expired: list[str] = []
        for path in sorted(self.cas.quarantine_root.glob("*.blob")):
            age_days = (now - path.stat().st_mtime) / 86400.0
            if age_days > self.policy.quarantine_days:
                expired.append("sha256:" + path.stem)
        return expired

    # -- reporting --------------------------------------------------------
    def report(self) -> dict[str, Any]:
        artifacts = self.store.list_artifacts(self.tenant_id)
        protected = self.reachable(self.live_roots())
        by_reason: dict[str, int] = {}
        for root in protected.values():
            by_reason[root.kind] = by_reason.get(root.kind, 0) + 1
        return {
            "tenant_id": self.tenant_id,
            "artifacts": len(artifacts),
            "artifact_bytes": sum(artifact.size_bytes for artifact in artifacts),
            "protected": len(protected),
            "protected_by_reason": dict(sorted(by_reason.items())),
            "cas": self.cas.accounting(),
            "orphans": {key: len(value) for key, value in self.reconcile_orphans().items()},
            "quota_bytes": self.policy.quota_bytes,
        }


def explain_retention(collector: GarbageCollector, digest: str) -> dict[str, Any]:
    """Answer 'why is this still here?' or 'why was it a candidate?'."""
    protected = collector.reachable(collector.live_roots())
    root = protected.get(digest)
    if root is not None:
        return {"digest": digest, "retained": True, "reason": root.kind, "source_id": root.source_id}
    artifact = collector.store.get_artifact(collector.tenant_id, digest)
    if artifact is None:
        return {"digest": digest, "retained": False, "reason": "unknown artifact"}
    score, reason = collector._score(digest, artifact.metadata, artifact.size_bytes, 0.0)
    return {"digest": digest, "retained": False, "reason": reason, "score": round(score, 4)}


def pin_for_investigation(
    store: MetadataStore, tenant_id: str, digests: Sequence[str], reason: str, expires_at: float | None
) -> list[str]:
    pins: list[str] = []
    for digest in digests:
        pins.append(store.add_pin(tenant_id, "artifact", digest, reason, expires_at))
    return pins
