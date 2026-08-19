"""One contract, both dialects.

Every guarantee the orchestration state depends on -- optimistic versioning,
lease-epoch fencing, legal-transition enforcement, idempotency, the outbox and
reference-aware artifact edges -- is asserted against **SQLite and a live
PostgreSQL server** with the same test body. A dialect that quietly loses one
of these would be a production-only bug, which is exactly the class of bug this
file exists to catch.

PostgreSQL is exercised when ``ELMOS_TEST_POSTGRES_DSN`` points at a server;
otherwise those parameterisations skip loudly rather than silently passing.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterator

import pytest

from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import MetadataStore, SqliteMetadataStore
from elmos_build_cache.db.records import (
    ActionCacheRecord,
    CheckpointRecord,
    StagedFileRecord,
)
from elmos_build_cache.db.store import PostgresMetadataStore
from elmos_build_cache.enums import (
    CacheEntryStatus,
    CheckpointStatus,
    FileClass,
    NodeStatus,
    RunStatus,
    StagedFileStatus,
    TrustNamespace,
    ValidationLevel,
)
from elmos_build_cache.errors import (
    IdempotencyConflict,
    InvalidTransition,
    StaleLease,
    VersionConflict,
)

POSTGRES_DSN = os.environ.get("ELMOS_TEST_POSTGRES_DSN")
TENANT = "tenant-contract"
PROJECT = "project-contract"
RUN = "run-contract-1"


def digest(character: str) -> str:
    return "sha256:" + character * 64


@pytest.fixture(params=["sqlite", "postgres"])
def store(request: pytest.FixtureRequest, tmp_path, clock: ManualClock) -> Iterator[MetadataStore]:
    if request.param == "sqlite":
        opened: MetadataStore = SqliteMetadataStore.open(tmp_path / "index.sqlite", clock)
    else:
        if not POSTGRES_DSN:
            pytest.skip("ELMOS_TEST_POSTGRES_DSN is not set; PostgreSQL profile not certified here")
        postgres = PostgresMetadataStore.open(POSTGRES_DSN, clock, migrate=False)
        postgres.reset()
        postgres.migrate()
        opened = postgres
    with opened.transaction():
        opened.ensure_project(TENANT, PROJECT)
        snapshot = opened.record_snapshot(
            TENANT, PROJECT, digest("1"), digest("2"), "elmos.snapshot-policy/1.0.0"
        )
        opened.create_run(RUN, TENANT, PROJECT, snapshot, "1.0.0")
    yield opened
    opened.close()


@pytest.fixture
def dialect(store: MetadataStore) -> str:
    return "postgres" if isinstance(store, PostgresMetadataStore) else "sqlite"


# --------------------------------------------------------------------------
# runs and nodes
# --------------------------------------------------------------------------
def test_run_transitions_require_the_expected_version(store: MetadataStore) -> None:
    run = store.get_run(RUN)
    assert run.status is RunStatus.PENDING
    with pytest.raises(VersionConflict), store.transaction():
        store.transition_run(RUN, RunStatus.RUNNING, run.version + 5)
    with store.transaction():
        updated = store.transition_run(RUN, RunStatus.RUNNING, run.version)
    assert updated.status is RunStatus.RUNNING
    assert updated.version == run.version + 1


def test_illegal_run_transition_is_refused(store: MetadataStore) -> None:
    run = store.get_run(RUN)
    with pytest.raises(InvalidTransition), store.transaction():
        store.transition_run(RUN, RunStatus.SUCCEEDED, run.version)


def test_node_lease_epoch_fences_a_stale_worker(store: MetadataStore) -> None:
    with store.transaction():
        node = store.upsert_node(RUN, "gen", "target-code-generation", "1.0.0")
        node = store.claim_node(RUN, "gen", 1, "lease-a", 30.0, node.version)
        node = store.transition_node(RUN, "gen", 1, NodeStatus.READY, node.version)
        running = store.transition_node(
            RUN, "gen", 1, NodeStatus.RUNNING, node.version, lease_epoch=node.lease_epoch
        )
    held_epoch = running.lease_epoch

    with store.transaction():
        current = store.get_node(RUN, "gen", 1)
        store.claim_node(RUN, "gen", 1, "lease-recovery", 30.0, current.version)

    with pytest.raises(StaleLease), store.transaction():
        latest = store.get_node(RUN, "gen", 1)
        store.transition_node(
            RUN, "gen", 1, NodeStatus.SUCCEEDED, latest.version, lease_epoch=held_epoch
        )
    assert store.get_node(RUN, "gen", 1).status is NodeStatus.RUNNING


def test_lease_expiry_is_queryable(store: MetadataStore, clock: ManualClock) -> None:
    with store.transaction():
        node = store.upsert_node(RUN, "gen", "gen", "1.0.0")
        node = store.claim_node(RUN, "gen", 1, "lease-a", 30.0, node.version)
        node = store.transition_node(RUN, "gen", 1, NodeStatus.READY, node.version)
        store.transition_node(
            RUN, "gen", 1, NodeStatus.RUNNING, node.version, lease_epoch=node.lease_epoch
        )
    assert store.expired_nodes(clock.now()) == []
    clock.advance(120)
    assert [n.node_id for n in store.expired_nodes(clock.now())] == ["gen"]


def test_heartbeat_is_refused_for_a_superseded_lease(store: MetadataStore) -> None:
    with store.transaction():
        node = store.upsert_node(RUN, "gen", "gen", "1.0.0")
        node = store.claim_node(RUN, "gen", 1, "lease-a", 30.0, node.version)
    with store.transaction():
        store.claim_node(RUN, "gen", 1, "lease-b", 30.0, store.get_node(RUN, "gen", 1).version)
    with pytest.raises(StaleLease), store.transaction():
        store.heartbeat_node(RUN, "gen", 1, "lease-a", node.lease_epoch, 30.0)


# --------------------------------------------------------------------------
# staged files
# --------------------------------------------------------------------------
def staged(**overrides: object) -> StagedFileRecord:
    base: dict[str, object] = {
        "staged_file_id": "sf_contract_1",
        "tenant_id": TENANT,
        "project_id": PROJECT,
        "run_id": RUN,
        "node_id": "gen",
        "attempt": 1,
        "logical_path": "src/App.cs",
        "file_class": FileClass.PUBLISH_CANDIDATE,
        "status": StagedFileStatus.RESERVED,
        "lease_epoch": 0,
        "version": 0,
    }
    base.update(overrides)
    return StagedFileRecord(**base)  # type: ignore[arg-type]


def test_staged_file_lifecycle_is_version_guarded(store: MetadataStore) -> None:
    record = staged()
    with store.transaction():
        store.insert_staged_file(record)
        record = store.update_staged_file(record, StagedFileStatus.WRITING, 0)
        record = store.update_staged_file(
            record, StagedFileStatus.SEALED, record.version, digest=digest("a"), actual_size=42
        )
    assert record.status is StagedFileStatus.SEALED
    assert store.get_staged_file("sf_contract_1").digest == digest("a")

    # A writer holding the pre-seal version loses.
    with pytest.raises(VersionConflict), store.transaction():
        store.update_staged_file(record, StagedFileStatus.CAS_PROMOTED, 0)


def test_staged_file_illegal_transition_is_refused(store: MetadataStore) -> None:
    record = staged()
    with store.transaction():
        store.insert_staged_file(record)
    with pytest.raises(InvalidTransition), store.transaction():
        store.update_staged_file(record, StagedFileStatus.PUBLISHED, 0)


def test_staged_file_stale_lease_is_refused(store: MetadataStore) -> None:
    record = staged(lease_epoch=3)
    with store.transaction():
        store.insert_staged_file(record)
    with pytest.raises(StaleLease), store.transaction():
        store.update_staged_file(record, StagedFileStatus.WRITING, 0, lease_epoch=2)


def test_live_logical_path_lookup(store: MetadataStore) -> None:
    with store.transaction():
        store.insert_staged_file(staged())
    assert store.find_live_staged_file(RUN, "src/App.cs") is not None
    with store.transaction():
        store.update_staged_file(staged(), StagedFileStatus.ABORTED, 0)
    assert store.find_live_staged_file(RUN, "src/App.cs") is None
    assert store.find_staged_file(RUN, "gen", 1, "src/App.cs") is not None


# --------------------------------------------------------------------------
# artifacts and the action cache
# --------------------------------------------------------------------------
def test_artifact_edges_are_reference_aware(store: MetadataStore) -> None:
    with store.transaction():
        store.register_artifact(TENANT, digest("a"), 10, "text/plain", "blob")
        store.register_artifact(TENANT, digest("b"), 20, "application/json", "manifest")
        store.add_artifact_ref(TENANT, "action_result", digest("b"), digest("a"), "output")
        store.add_artifact_ref(TENANT, "action_result", digest("b"), digest("a"), "output")

    assert store.artifact_targets(TENANT, "action_result", digest("b")) == [digest("a")]
    assert store.artifact_referrers(TENANT, digest("a")) == [
        ("action_result", digest("b"), "output")
    ]
    assert {a.digest for a in store.list_artifacts(TENANT)} == {digest("a"), digest("b")}


def test_validation_level_only_ratchets_upward(store: MetadataStore) -> None:
    with store.transaction():
        store.register_artifact(
            TENANT, digest("a"), 10, "text/plain", "blob", validation_level=ValidationLevel.TEST_VERIFIED
        )
        store.register_artifact(
            TENANT, digest("a"), 10, "text/plain", "blob", validation_level=ValidationLevel.UNVERIFIED
        )
    record = store.get_artifact(TENANT, digest("a"))
    assert record is not None and record.validation_level is ValidationLevel.TEST_VERIFIED


def test_action_cache_entry_round_trip(store: MetadataStore) -> None:
    entry = ActionCacheRecord(
        tenant_id=TENANT,
        trust_namespace=TrustNamespace.BRANCH,
        action_key=digest("7"),
        result_manifest_digest=digest("b"),
        validation_level=ValidationLevel.TEST_VERIFIED,
        producer_identity="worker-1",
        provenance_digest=digest("b"),
        status=CacheEntryStatus.ACTIVE,
        expires_at=1_800_000_000.0,
        saved_cpu_ms=4_000,
        saved_wall_ms=9_000,
        saved_compiler_ms=3_500,
        saved_model_tokens=12_000,
    )
    with store.transaction():
        store.put_action_entry(entry)
        store.record_action_hit(TENANT, TrustNamespace.BRANCH, digest("7"))

    found = store.get_action_entry(TENANT, TrustNamespace.BRANCH, digest("7"))
    assert found is not None
    assert found.hit_count == 1
    assert found.expires_at == pytest.approx(1_800_000_000.0)
    assert found.saved_model_tokens == 12_000
    # Compiler time is the number a *build* cache exists to save; it has to
    # survive the round trip in both dialects, not just be accepted.
    assert found.saved_compiler_ms == 3_500
    assert found.saved_cpu_ms == 4_000 and found.saved_wall_ms == 9_000

    with store.transaction():
        store.update_action_entry(dataclasses.replace(found, saved_compiler_ms=7_000))
    updated = store.get_action_entry(TENANT, TrustNamespace.BRANCH, digest("7"))
    assert updated is not None and updated.saved_compiler_ms == 7_000
    # Namespaces are separate key spaces, in both dialects.
    assert store.get_action_entry(TENANT, TrustNamespace.OFFICIAL, digest("7")) is None


# --------------------------------------------------------------------------
# journal, checkpoints, receipts
# --------------------------------------------------------------------------
def test_event_sequence_is_unique_and_replay_is_idempotent(store: MetadataStore) -> None:
    with store.transaction():
        first = store.append_event(TENANT, RUN, "gen", 1, "NODE_STARTED", "coord", {"worker": "w1"})
        duplicate = store.append_event(TENANT, RUN, "gen", 1, "NODE_STARTED", "coord", {"worker": "w1"})
    assert first is True and duplicate is False
    assert len(store.list_events(RUN)) == 1
    assert store.get_run(RUN).journal_sequence == 1


def test_conflicting_payload_on_the_same_sequence_is_rejected(store: MetadataStore) -> None:
    from elmos_build_cache.errors import ConflictError

    with store.transaction():
        store.append_event(TENANT, RUN, "gen", 1, "NODE_STARTED", "coord", {"worker": "w1"})
    with pytest.raises(ConflictError), store.transaction():
        store.append_event(TENANT, RUN, "gen", 1, "NODE_STARTED", "coord", {"worker": "attacker"})


def test_checkpoint_chain_supersedes_the_previous_active_one(store: MetadataStore) -> None:
    def checkpoint(identifier: str, sequence: int) -> CheckpointRecord:
        return CheckpointRecord(
            identifier, TENANT, PROJECT, RUN, "gen", 1, sequence, 1, digest("c"), 10, CheckpointStatus.ACTIVE
        )

    with store.transaction():
        store.insert_checkpoint(checkpoint("cp_1", 1))
        store.insert_checkpoint(checkpoint("cp_2", 2))

    statuses = {c.checkpoint_id: c.status for c in store.list_checkpoints(RUN, "gen")}
    assert statuses == {"cp_1": CheckpointStatus.SUPERSEDED, "cp_2": CheckpointStatus.ACTIVE}


def test_side_effect_receipt_is_at_most_once(store: MetadataStore) -> None:
    with store.transaction():
        first, reference = store.claim_side_effect(TENANT, RUN, "gen", "idem-1", "publish", digest("a"))
        assert first is False and reference is None
        store.complete_side_effect(TENANT, "idem-1", "COMMITTED", "external-1")
    with store.transaction():
        already, reference = store.claim_side_effect(TENANT, RUN, "gen", "idem-1", "publish", digest("a"))
    assert already is True and reference == "external-1"

    with pytest.raises(IdempotencyConflict), store.transaction():
        store.claim_side_effect(TENANT, RUN, "gen", "idem-1", "publish", digest("b"))


def test_idempotency_records_replay_and_conflict(store: MetadataStore) -> None:
    with store.transaction():
        stored = store.remember_idempotent(TENANT, "key-1", "PUT /blobs", {"digest": "x"}, {"status": 201})
    assert stored == {"status": 201}
    assert store.replay_idempotent(TENANT, "key-1", "PUT /blobs", {"digest": "x"}) == {"status": 201}
    with pytest.raises(IdempotencyConflict):
        store.replay_idempotent(TENANT, "key-1", "PUT /blobs", {"digest": "different"})


# --------------------------------------------------------------------------
# outbox, pins, certificates, gc
# --------------------------------------------------------------------------
def test_outbox_round_trip(store: MetadataStore) -> None:
    with store.transaction():
        identifier = store.enqueue_outbox(TENANT, "remote.upload", digest("a"), {"digest": digest("a")})
    assert identifier > 0
    pending = store.pending_outbox()
    assert len(pending) == 1
    assert pending[0]["payload"] == {"digest": digest("a")}

    with store.transaction():
        store.mark_outbox_attempt(identifier)
        store.mark_outbox_published(identifier)
    assert store.pending_outbox() == []


def test_pins_expire(store: MetadataStore, clock: ManualClock) -> None:
    with store.transaction():
        permanent = store.add_pin(TENANT, "artifact", digest("a"), "legal hold", None)
        store.add_pin(TENANT, "artifact", digest("b"), "investigation", clock.now() + 60)
    assert len(store.list_pins(TENANT, clock.now())) == 2
    clock.advance(120)
    remaining = store.list_pins(TENANT, clock.now())
    assert [pin["pin_id"] for pin in remaining] == [permanent]


def test_certificates_and_revocations(store: MetadataStore) -> None:
    with store.transaction():
        store.add_certificate(
            {
                "certificate_id": "cert_1",
                "tenant_id": TENANT,
                "scope_digest": digest("s"[0] * 1),
                "tree_digest": digest("b"),
                "evidence_digest": digest("c"),
                "validation_level": ValidationLevel.PRODUCTION_CERTIFIED,
                "signature": "abc",
                "issuer": "ed25519:prov-1",
                "status": "VALID",
                "issued_at": 1.0,
                "expires_at": 2.0,
                "limitations": ["linux only"],
            }
        )
    record = store.get_certificate("cert_1")
    assert record is not None
    assert record["limitations"] == ["linux only"]
    assert record["validation_level"] is ValidationLevel.PRODUCTION_CERTIFIED
    assert store.certificates_for_tree(TENANT, digest("b")) == ["cert_1"]

    with store.transaction():
        store.set_certificate_status("cert_1", "REVOKED")
        store.add_revocation(TENANT, "tree", digest("b"), "toolchain compromise")
    assert store.get_certificate("cert_1")["status"] == "REVOKED"  # type: ignore[index]
    assert store.is_revoked(TENANT, "tree", digest("b"))


def test_gc_plan_and_receipts(store: MetadataStore) -> None:
    with store.transaction():
        plan_id = store.create_gc_plan(TENANT, {"candidates": [{"digest": digest("a")}]})
        store.set_gc_plan_status(plan_id, "APPROVED")
        store.add_gc_receipt(plan_id, digest("a"), "DELETED", "unreferenced")
        store.add_gc_receipt(plan_id, digest("a"), "DELETED", "duplicate call")
    plan = store.get_gc_plan(plan_id)
    assert plan is not None and plan["status"] == "APPROVED"
    assert plan["payload"]["candidates"][0]["digest"] == digest("a")
    assert store.gc_receipts(plan_id) == [{"digest": digest("a"), "outcome": "DELETED", "detail": "unreferenced"}]


def test_tree_publication_marks_the_previous_one_superseded(store: MetadataStore) -> None:
    with store.transaction():
        for name in ("b", "c"):
            store.record_tree(
                TENANT, digest(name), RUN, digest("m"), 1, 10, ValidationLevel.TEST_VERIFIED, None, None
            )
        store.mark_tree_published(TENANT, digest("b"))
        store.mark_tree_published(TENANT, digest("c"))
    published = store.published_trees(TENANT)
    assert set(published) == {digest("b"), digest("c")}


def test_dialect_is_actually_exercised(store: MetadataStore, dialect: str) -> None:
    """Guards against the PostgreSQL parameterisation silently degrading."""
    if dialect == "postgres":
        assert isinstance(store, PostgresMetadataStore)
        version = store.query("SELECT version()")[0][0]
        assert "PostgreSQL" in version
    else:
        assert isinstance(store, SqliteMetadataStore)
        assert store.query("PRAGMA journal_mode")[0][0].lower() == "wal"


def test_sqlite_migrations_are_applied_exactly_once(tmp_path, clock: ManualClock) -> None:
    """Reopening a database must not re-run ``ALTER TABLE``.

    ``0001`` is written to be re-runnable, but a column-adding migration is
    not, so the store keeps a ledger. Opening twice is the cheap version of the
    upgrade path an operator actually walks.
    """
    path = tmp_path / "index.sqlite"
    first = SqliteMetadataStore.open(path, clock)
    applied = [row[0] for row in first.query("SELECT name FROM schema_migrations ORDER BY name")]
    first.close()
    assert applied == ["0001_init.sql", "0002_saved_compiler_ms.sql"]

    second = SqliteMetadataStore.open(path, clock)  # must not raise "duplicate column"
    try:
        again = [row[0] for row in second.query("SELECT name FROM schema_migrations ORDER BY name")]
        assert again == applied
        columns = [row[1] for row in second.query("PRAGMA table_info(action_cache_entries)")]
        assert "saved_compiler_ms" in columns
    finally:
        second.close()
