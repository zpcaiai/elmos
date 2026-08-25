"""GC-001..002: protection by reachability and idempotent, resumable deletion."""

from __future__ import annotations

import pytest

from conftest import TENANT, claim_node
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.db.records import CheckpointRecord
from elmos_build_cache.enums import CheckpointStatus, FileClass, ValidationLevel
from elmos_build_cache.errors import ConflictError, PermissionDenied
from elmos_build_cache.gc import GarbageCollector, RetentionPolicy, explain_retention
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.manifests import EvidenceBundle
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.staging import Workspace, stage_all

POLICY = RetentionPolicy(grace_hours=1, quota_bytes=1024**3)


def register(store: SqliteMetadataStore, cas: ContentAddressableStore, payload: bytes, **metadata):
    digest = cas.put_bytes(payload)
    with store.transaction():
        store.register_artifact(
            TENANT, digest, cas.info(digest).size, "application/octet-stream", "blob", metadata=metadata
        )
    return digest


def collector(store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock) -> GarbageCollector:
    return GarbageCollector(store, cas, TENANT, POLICY, clock)


def test_gc_001_checkpoint_referenced_artifact_is_protected(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock, run: str
) -> None:
    """GC-001: reachable from a checkpoint means untouchable."""
    keep = register(store, cas, b"referenced by a checkpoint")
    drop = register(store, cas, b"orphan" * 200, recompute_cost_ms=5, expected_reuse=0.001)
    with store.transaction():
        store.insert_checkpoint(
            CheckpointRecord("cp1", TENANT, "project-test", run, "gen", 1, 1, 1, keep, 10, CheckpointStatus.ACTIVE)
        )
        store.add_artifact_ref(TENANT, "checkpoint", "cp1", keep, "artifact")

    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
    candidates = {candidate.digest for candidate in plan.candidates}
    assert keep not in candidates
    assert drop in candidates
    assert explain_retention(gc, keep)["retained"] is True


def test_published_tree_and_pins_are_protected(
    workspace: Workspace,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    clock: ManualClock,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        records = stage_all(
            workspace, "gen", 1, lease.epoch, [("a.cs", b"a")], file_class=FileClass.PUBLISH_CANDIDATE
        )
    tree = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    evidence = EvidenceBundle(
        tree.root_digest, ValidationLevel.TEST_VERIFIED, ({"kind": "test"},), "worker-1", ("ci",)
    )
    with store.transaction():
        evidence.store(cas)
        publisher.publish(publisher.materialize(tree), evidence)

    pinned = register(store, cas, b"explicitly pinned")
    with store.transaction():
        store.add_pin(TENANT, "artifact", pinned, "under investigation")

    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
    candidates = {candidate.digest for candidate in plan.candidates}
    assert records[0].artifact_digest not in candidates
    assert pinned not in candidates


def test_gc_002_interrupted_pass_resumes_idempotently(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    """GC-002: partial application resumes from receipts and never double-deletes."""
    first = register(store, cas, b"junk-one" * 50, recompute_cost_ms=1, expected_reuse=0.0)
    second = register(store, cas, b"junk-two" * 50, recompute_cost_ms=1, expected_reuse=0.0)
    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
        gc.approve(plan.plan_id)
    clock.advance(3700)

    with store.transaction():
        partial = gc.apply(plan.plan_id, limit=1)
    assert partial["deleted"] == 1
    with store.transaction():
        rest = gc.apply(plan.plan_id)
    assert rest["deleted"] == 1
    with store.transaction():
        again = gc.apply(plan.plan_id)
    assert again["deleted"] == 0
    assert {receipt["digest"] for receipt in store.gc_receipts(plan.plan_id)} == {first, second}
    assert not cas.contains(first) and not cas.contains(second)


def test_grace_period_must_elapse(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    register(store, cas, b"junk" * 100, recompute_cost_ms=1, expected_reuse=0.0)
    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
        gc.approve(plan.plan_id)
    with pytest.raises(ConflictError, match="grace"), store.transaction():
        gc.apply(plan.plan_id)


def test_unapproved_plan_cannot_be_applied(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    register(store, cas, b"junk" * 100)
    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
    clock.advance(3700)
    with pytest.raises(ConflictError, match="approved"), store.transaction():
        gc.apply(plan.plan_id)


def test_authorisation_is_required(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
        gc.approve(plan.plan_id)
    clock.advance(3700)
    with pytest.raises(PermissionDenied), store.transaction():
        gc.apply(plan.plan_id, principal_can_gc=False)


def test_artifact_that_becomes_reachable_after_planning_is_spared(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock, run: str
) -> None:
    """Protection is re-derived at apply time, not trusted from the plan."""
    digest = register(store, cas, b"about to be referenced" * 20, recompute_cost_ms=1, expected_reuse=0.0)
    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
        gc.approve(plan.plan_id)
    assert digest in {candidate.digest for candidate in plan.candidates}

    with store.transaction():
        store.insert_checkpoint(
            CheckpointRecord(
                "cp-late", TENANT, "project-test", run, "gen", 1, 1, 1, digest, 5, CheckpointStatus.ACTIVE
            )
        )
        store.add_artifact_ref(TENANT, "checkpoint", "cp-late", digest, "artifact")
    clock.advance(3700)
    with store.transaction():
        outcome = gc.apply(plan.plan_id)
    assert outcome["skipped_protected"] == 1
    assert cas.contains(digest)


def test_scoring_prefers_cheap_to_recompute_artifacts(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    cheap = register(store, cas, b"c" * 100_000, recompute_cost_ms=5, expected_reuse=0.01)
    expensive = register(store, cas, b"e" * 100_000, recompute_cost_ms=900_000, expected_reuse=0.9)
    gc = collector(store, cas, clock)
    with store.transaction():
        plan = gc.plan()
    order = [candidate.digest for candidate in plan.candidates]
    assert order.index(cheap) < order.index(expensive)


def test_orphan_reconciliation_reports_both_directions(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    tracked = register(store, cas, b"tracked")
    cas.put_bytes(b"untracked blob")
    cas.delete(tracked)
    orphans = collector(store, cas, clock).reconcile_orphans()
    assert tracked in orphans["orphan_metadata"]
    assert len(orphans["orphan_blobs"]) == 1


def test_quarantine_retention_is_separate_from_gc(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    digest = register(store, cas, b"suspect")
    cas.quarantine(digest, "digest mismatch")
    gc = collector(store, cas, clock)
    assert gc.quarantine_retention() == []


def test_report_explains_protection_reasons(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock, run: str
) -> None:
    keep = register(store, cas, b"kept")
    with store.transaction():
        store.add_pin(TENANT, "artifact", keep, "legal hold")
    report = collector(store, cas, clock).report()
    assert report["protected_by_reason"].get("pin") == 1
    assert report["artifacts"] >= 1
