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
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import MetadataStore, SqliteMetadataStore
from elmos_build_cache.db import store as store_module
from elmos_build_cache.db.records import (
    ActionCacheRecord,
    CheckpointRecord,
    StagedFileRecord,
)
from elmos_build_cache.db.store import (
    POSTGRES_MIGRATIONS,
    SQLITE_MIGRATIONS,
    PostgresMetadataStore,
)
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
    ConflictError,
    ContractViolation,
    IdempotencyConflict,
    IdempotencyOutcomeUnknown,
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


def test_idempotency_claim_is_fenced_and_pending_never_reexecutes(
    store: MetadataStore,
) -> None:
    request = {"method": "POST", "path": "/effects", "body_digest": digest("a")}
    with store.transaction():
        claim = store.claim_idempotent(TENANT, "claim-1", "POST /effects", request)
    assert claim.claimed
    assert claim.owner_token is not None
    assert claim.fence == 1

    with pytest.raises(IdempotencyOutcomeUnknown, match="must be reconciled"), store.transaction():
        store.claim_idempotent(TENANT, "claim-1", "POST /effects", request)

    response = {"status": 202, "headers": {"X-Receipt": "receipt-1"}}
    with store.transaction():
        completed = store.complete_idempotent(
            TENANT,
            "claim-1",
            "POST /effects",
            request,
            claim.owner_token,
            claim.fence,
            response,
        )
    assert completed == response

    with store.transaction():
        replay = store.claim_idempotent(TENANT, "claim-1", "POST /effects", request)
    assert replay.replayed
    assert replay.response == response

    with store.transaction():
        stale_completion = store.complete_idempotent(
            TENANT,
            "claim-1",
            "POST /effects",
            request,
            "different-owner",
            claim.fence,
            {"status": 500},
        )
    assert stale_completion == response


def test_pending_idempotency_requires_explicit_audited_reconciliation(
    store: MetadataStore,
) -> None:
    request = {"method": "POST", "path": "/effects", "body_digest": digest("b")}
    with store.transaction():
        claim = store.claim_idempotent(TENANT, "claim-reconcile", "POST /effects", request)
    assert claim.claimed

    response = {"status": 201, "body": {"receipt_id": "external-7"}}
    with store.transaction():
        assert (
            store.reconcile_idempotent(
                TENANT,
                "claim-reconcile",
                "POST /effects",
                request,
                response,
                reconciler_identity="operator@example.test",
            )
            == response
        )

    row = store.query_one(
        "SELECT state, fence, reconciled_by FROM idempotency_records"
        " WHERE tenant_id=? AND idempotency_key=?",
        (TENANT, "claim-reconcile"),
    )
    assert row == ("COMPLETE", claim.fence + 1, "operator@example.test")
    assert store.replay_idempotent(
        TENANT, "claim-reconcile", "POST /effects", request
    ) == response


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


def test_project_identity_cannot_be_claimed_by_another_tenant(store: MetadataStore) -> None:
    with pytest.raises(ConflictError, match="tenant scope conflict"), store.transaction():
        store.ensure_project("tenant-attacker", PROJECT)

    owner = store.query_one("SELECT tenant_id FROM projects WHERE project_id=?", (PROJECT,))
    assert owner is not None and str(owner[0]) == TENANT
    assert store.query_one(
        "SELECT tenant_id FROM tenants WHERE tenant_id=?", ("tenant-attacker",)
    ) is None


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
    assert applied == sorted(SQLITE_MIGRATIONS)

    second = SqliteMetadataStore.open(path, clock)  # must not raise "duplicate column"
    try:
        again = [row[0] for row in second.query("SELECT name FROM schema_migrations ORDER BY name")]
        assert again == applied
        columns = [row[1] for row in second.query("PRAGMA table_info(action_cache_entries)")]
        assert "saved_compiler_ms" in columns
    finally:
        second.close()


def test_sqlite_migration_statements_and_ledger_are_one_transaction(
    tmp_path, clock: ManualClock
) -> None:
    path = tmp_path / "faulted.sqlite"

    class FaultAfterDdlStore(SqliteMetadataStore):
        def _after_sqlite_migration_statements(self, name: str) -> None:
            if name == "0002_saved_compiler_ms.sql":
                raise RuntimeError("fault after DDL before ledger")

    with pytest.raises(RuntimeError, match="fault after DDL"):
        FaultAfterDdlStore.open(path, clock)

    connection = sqlite3.connect(path)
    try:
        applied = {
            str(row[0])
            for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
        }
        columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info(action_cache_entries)").fetchall()
        ]
    finally:
        connection.close()
    assert applied == {"0001_init.sql"}
    assert "saved_compiler_ms" not in columns

    recovered = SqliteMetadataStore.open(path, clock)
    recovered.close()
    reopened = SqliteMetadataStore.open(path, clock)
    try:
        columns = [
            str(row[1])
            for row in reopened.query("PRAGMA table_info(action_cache_entries)")
        ]
        applied = [
            str(row[0])
            for row in reopened.query("SELECT name FROM schema_migrations ORDER BY name")
        ]
        assert columns.count("saved_compiler_ms") == 1
        assert applied == sorted(SQLITE_MIGRATIONS)
    finally:
        reopened.close()


class _FakePostgresCursor:
    def __init__(self, connection: _FakePostgresConnection) -> None:
        self.connection = connection
        self.rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _FakePostgresCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> _FakePostgresCursor:
        sql = statement.strip()
        self.rows = []
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            self.connection.lock_calls += 1
        elif sql.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            self.connection.pending_ledger = True
        elif sql == "SELECT name FROM schema_migrations ORDER BY name":
            self.rows = [(name,) for name in sorted(self.connection.effective_applied)]
        elif sql.startswith("SELECT table_name FROM information_schema.tables"):
            names = set(self.connection.tables)
            if self.connection.ledger_exists or self.connection.pending_ledger:
                names.add("schema_migrations")
            self.rows = [(name,) for name in sorted(names)]
        elif sql.startswith("SELECT table_name, column_name, data_type, column_default"):
            self.rows = [
                (table, column, data_type, default)
                for (table, column), (data_type, default) in sorted(
                    self.connection.columns.items()
                )
            ]
        elif sql.startswith("SELECT 1 FROM schema_migrations WHERE name="):
            self.rows = [(1,)] if str(params[0]) in self.connection.effective_applied else []
        elif sql.startswith("INSERT INTO schema_migrations"):
            self.connection.pending_applied.add(str(params[0]))
        elif statement in self.connection.script_names:
            name = self.connection.script_names[statement]
            if name == self.connection.fail_on:
                raise RuntimeError(f"injected migration failure: {name}")
            self.connection.pending_scripts.append(name)
        else:  # pragma: no cover - makes a changed migration protocol fail loudly
            raise AssertionError(f"unexpected fake PostgreSQL statement: {sql[:100]}")
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None


class _FakePostgresConnection:
    def __init__(
        self,
        *,
        applied: set[str] | None = None,
        tables: set[str] | None = None,
        columns: dict[tuple[str, str], tuple[str, str | None]] | None = None,
        fail_on: str | None = None,
    ) -> None:
        self.applied = set(applied or ())
        self.tables = set(tables or ())
        self.columns = dict(columns or {})
        self.fail_on = fail_on
        self.ledger_exists = bool(applied)
        self.pending_ledger = False
        self.pending_applied: set[str] = set()
        self.pending_scripts: list[str] = []
        self.executed_scripts: list[str] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.lock_calls = 0
        self.script_names = {
            (store_module.MIGRATIONS_DIR / "postgres" / name).read_text(encoding="utf-8"): name
            for name in POSTGRES_MIGRATIONS
        }

    @property
    def effective_applied(self) -> set[str]:
        return self.applied | self.pending_applied

    def cursor(self) -> _FakePostgresCursor:
        return _FakePostgresCursor(self)

    def commit(self) -> None:
        self.ledger_exists = self.ledger_exists or self.pending_ledger
        self.applied.update(self.pending_applied)
        self.executed_scripts.extend(self.pending_scripts)
        self.pending_ledger = False
        self.pending_applied.clear()
        self.pending_scripts.clear()
        self.commit_count += 1

    def rollback(self) -> None:
        self.pending_ledger = False
        self.pending_applied.clear()
        self.pending_scripts.clear()
        self.rollback_count += 1


def _legacy_v1_postgres_inventory() -> tuple[
    set[str], dict[tuple[str, str], tuple[str, str | None]]
]:
    tables = set(store_module._POSTGRES_V1_TABLES | store_module._POSTGRES_V2_TABLES)
    columns = {column: ("text", None) for column in store_module._POSTGRES_V2_COLUMNS}
    columns.update(
        {
            column: (data_type, None)
            for column, data_type in store_module._POSTGRES_V3_COLUMN_TYPES.items()
        }
    )
    columns[("action_cache_entries", "saved_compiler_ms")] = ("bigint", None)
    return tables, columns


def test_postgres_migrations_are_transactional_locked_and_idempotent(
    clock: ManualClock,
) -> None:
    connection = _FakePostgresConnection()
    store = PostgresMetadataStore(connection, clock)
    store.migrate()

    assert connection.applied == set(POSTGRES_MIGRATIONS)
    assert connection.executed_scripts == list(POSTGRES_MIGRATIONS)
    assert connection.lock_calls == 1 + len(POSTGRES_MIGRATIONS)

    # Re-entry on the same store/connection executes no migration SQL.
    store.migrate()
    assert connection.applied == set(POSTGRES_MIGRATIONS)
    assert connection.executed_scripts == list(POSTGRES_MIGRATIONS)
    assert connection.lock_calls == 2 * (1 + len(POSTGRES_MIGRATIONS))

    # A second store startup over the same database is equally idempotent.
    PostgresMetadataStore(connection, clock).migrate()
    assert connection.applied == set(POSTGRES_MIGRATIONS)
    assert connection.executed_scripts == list(POSTGRES_MIGRATIONS)
    assert connection.lock_calls == 3 * (1 + len(POSTGRES_MIGRATIONS))


def test_postgres_failed_migration_rolls_back_without_a_ledger_entry(
    clock: ManualClock,
) -> None:
    failed = POSTGRES_MIGRATIONS[3]
    connection = _FakePostgresConnection(fail_on=failed)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        PostgresMetadataStore(connection, clock).migrate()

    assert connection.applied == set(POSTGRES_MIGRATIONS[:3])
    assert failed not in connection.executed_scripts
    assert connection.rollback_count == 1

    connection.fail_on = None
    PostgresMetadataStore(connection, clock).migrate()
    assert connection.applied == set(POSTGRES_MIGRATIONS)
    assert connection.executed_scripts == list(POSTGRES_MIGRATIONS)


def test_postgres_preledger_v1_database_is_safely_baselined(
    clock: ManualClock,
) -> None:
    tables, columns = _legacy_v1_postgres_inventory()
    connection = _FakePostgresConnection(tables=tables, columns=columns)
    PostgresMetadataStore(connection, clock).migrate()

    assert connection.applied == set(POSTGRES_MIGRATIONS)
    assert connection.executed_scripts == list(POSTGRES_MIGRATIONS[4:])
    assert POSTGRES_MIGRATIONS[0] not in connection.executed_scripts


def test_postgres_preledger_partial_schema_fails_closed(clock: ManualClock) -> None:
    connection = _FakePostgresConnection(tables={"tenants"})
    with pytest.raises(ContractViolation, match="partial 0001"):
        PostgresMetadataStore(connection, clock).migrate()

    assert not connection.applied
    assert not connection.ledger_exists
    assert connection.rollback_count == 1


V12_PROJECT_SCOPED_TABLES = (
    "context_ledger_streams",
    "context_ledger_events",
    "context_checkpoints",
    "prompt_prefix_manifests",
    "provider_cache_usage",
    "environment_snapshot_manifests",
    "environment_snapshot_status_events",
    "cache_outcome_events_v12",
    "cache_affinity_decisions_v12",
    "cache_parity_reports_v12",
)


def test_project_scope_migrations_are_contiguous_and_packaged_byte_exactly() -> None:
    assert SQLITE_MIGRATIONS[-1] == "0006_project_tenant_scope.sql"
    assert POSTGRES_MIGRATIONS[-1] == "0008_project_tenant_scope.sql"
    assert [int(name[:4]) for name in SQLITE_MIGRATIONS] == list(
        range(1, len(SQLITE_MIGRATIONS) + 1)
    )
    assert [int(name[:4]) for name in POSTGRES_MIGRATIONS] == list(
        range(1, len(POSTGRES_MIGRATIONS) + 1)
    )

    repository_migrations = Path(__file__).resolve().parents[1] / "migrations"
    for dialect, name in (
        ("sqlite", SQLITE_MIGRATIONS[-1]),
        ("postgres", POSTGRES_MIGRATIONS[-1]),
    ):
        assert (repository_migrations / dialect / name).read_bytes() == (
            store_module.MIGRATIONS_DIR / dialect / name
        ).read_bytes()


def test_sqlite_v12_tables_reject_cross_tenant_project_inserts_and_updates(
    tmp_path: Path, clock: ManualClock
) -> None:
    store = SqliteMetadataStore.open(tmp_path / "scoped.sqlite", clock)
    owner = "tenant-owner"
    attacker = "tenant-attacker"
    project = "project-owned"
    try:
        with store.transaction():
            store.ensure_project(owner, project)
            store.ensure_tenant(attacker)

        installed = {
            str(row[0])
            for row in store.query(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
                " AND name LIKE '%_project_scope_%'"
            )
        }
        expected = {
            f"{table}_project_scope_{operation}"
            for table in V12_PROJECT_SCOPED_TABLES
            for operation in ("insert", "update")
        }
        assert expected.issubset(installed)

        # BEFORE INSERT scope guards run before the remaining NOT NULL checks,
        # so this minimal statement exercises every audited table directly.
        for table in V12_PROJECT_SCOPED_TABLES:
            with pytest.raises(
                sqlite3.IntegrityError,
                match="PROJECT_TENANT_SCOPE_MISMATCH",
            ), store.transaction():
                store.execute(
                    # Static allowlist above; SQLite identifiers cannot be bound.
                    f"INSERT INTO {table} (tenant_id, project_id) VALUES (?, ?)",  # noqa: S608
                    (attacker, project),
                )

        with store.transaction():
            store.execute(
                "INSERT INTO context_ledger_streams (tenant_id, project_id, stream_id,"
                " branch_lineage, repository_snapshot_digest, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (owner, project, "stream-1", "main", digest("a"), clock.now(), clock.now()),
            )
            store.execute(
                "INSERT INTO prompt_prefix_manifests (tenant_id, project_id, manifest_id,"
                " manifest_digest, provider_namespace, compatibility_group,"
                " stable_prefix_digest, document, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    owner,
                    project,
                    "manifest-1",
                    digest("b"),
                    "provider-namespace",
                    "compatibility-group",
                    digest("c"),
                    "{}",
                    clock.now(),
                ),
            )

        for statement, params in (
            (
                "UPDATE context_ledger_streams SET tenant_id=?"
                " WHERE tenant_id=? AND project_id=? AND stream_id=?",
                (attacker, owner, project, "stream-1"),
            ),
            (
                "UPDATE prompt_prefix_manifests SET tenant_id=?"
                " WHERE tenant_id=? AND project_id=? AND manifest_id=?",
                (attacker, owner, project, "manifest-1"),
            ),
        ):
            with pytest.raises(
                sqlite3.IntegrityError,
                match="PROJECT_TENANT_SCOPE_MISMATCH",
            ), store.transaction():
                store.execute(statement, params)
    finally:
        store.close()


def test_sqlite_project_scope_upgrade_rejects_legacy_drift_without_ledger_entry(
    tmp_path: Path, clock: ManualClock
) -> None:
    path = tmp_path / "legacy-drift.sqlite"
    connection = sqlite3.connect(path)
    try:
        for name in SQLITE_MIGRATIONS[:-1]:
            connection.executescript(
                (store_module.MIGRATIONS_DIR / "sqlite" / name).read_text(encoding="utf-8")
            )
        connection.execute(
            "CREATE TABLE schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            ((name, "legacy") for name in SQLITE_MIGRATIONS[:-1]),
        )
        connection.executemany(
            "INSERT INTO tenants (tenant_id, created_at) VALUES (?, ?)",
            (("tenant-owner", "legacy"), ("tenant-attacker", "legacy")),
        )
        connection.execute(
            "INSERT INTO projects (project_id, tenant_id, name, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("project-owned", "tenant-owner", "owned", "legacy"),
        )
        connection.execute(
            "INSERT INTO prompt_prefix_manifests (tenant_id, project_id, manifest_id,"
            " manifest_digest, provider_namespace, compatibility_group,"
            " stable_prefix_digest, document, recorded_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "tenant-attacker",
                "project-owned",
                "legacy-drift",
                digest("d"),
                "provider-namespace",
                "compatibility-group",
                digest("e"),
                "{}",
                clock.now(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        SqliteMetadataStore.open(path, clock)

    connection = sqlite3.connect(path)
    try:
        applied = {
            str(row[0])
            for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
        }
        trigger = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger'"
            " AND name='prompt_prefix_manifests_project_scope_insert'"
        ).fetchone()
        assert applied == set(SQLITE_MIGRATIONS[:-1])
        assert trigger is None
        connection.execute(
            "UPDATE prompt_prefix_manifests SET tenant_id=? WHERE manifest_id=?",
            ("tenant-owner", "legacy-drift"),
        )
        connection.commit()
    finally:
        connection.close()

    recovered = SqliteMetadataStore.open(path, clock)
    try:
        applied = {
            str(row[0]) for row in recovered.query("SELECT name FROM schema_migrations")
        }
        assert applied == set(SQLITE_MIGRATIONS)
        assert recovered.query_one(
            "SELECT 1 FROM sqlite_master WHERE type='trigger'"
            " AND name='prompt_prefix_manifests_project_scope_insert'"
        ) == (1,)
    finally:
        recovered.close()


def test_postgres_project_scope_migration_has_exact_composite_fk_contract() -> None:
    sql = (store_module.MIGRATIONS_DIR / "postgres" / POSTGRES_MIGRATIONS[-1]).read_text(
        encoding="utf-8"
    )
    constraints = {
        "context_ledger_streams": "fk_context_ledger_streams_project_scope",
        "context_ledger_events": "fk_context_ledger_events_project_scope",
        "context_checkpoints": "fk_context_checkpoints_project_scope",
        "prompt_prefix_manifests": "fk_prompt_prefix_manifests_project_scope",
        "provider_cache_usage": "fk_provider_cache_usage_project_scope",
        "environment_snapshot_manifests": (
            "fk_environment_snapshot_manifests_project_scope"
        ),
        "environment_snapshot_status_events": (
            "fk_environment_snapshot_status_events_project_scope"
        ),
        "cache_outcome_events_v12": "fk_cache_outcome_events_v12_project_scope",
        "cache_affinity_decisions_v12": (
            "fk_cache_affinity_decisions_v12_project_scope"
        ),
        "cache_parity_reports_v12": "fk_cache_parity_reports_v12_project_scope",
    }
    assert set(constraints) == set(V12_PROJECT_SCOPED_TABLES)
    assert (
        "ALTER TABLE projects\n"
        "  ADD CONSTRAINT projects_tenant_project_key\n"
        "  UNIQUE (tenant_id, project_id);"
    ) in sql
    for table, constraint in constraints.items():
        assert (
            f"ALTER TABLE {table}\n"
            f"  ADD CONSTRAINT {constraint}\n"
            "  FOREIGN KEY (tenant_id, project_id)\n"
            "  REFERENCES projects (tenant_id, project_id)\n"
            "  ON UPDATE RESTRICT ON DELETE RESTRICT\n"
            "  NOT VALID;"
        ) in sql
        assert (
            f"ALTER TABLE {table}\n  VALIDATE CONSTRAINT {constraint};"
        ) in sql
    assert sql.count("FOREIGN KEY (tenant_id, project_id)") == len(constraints)
    assert sql.count("NOT VALID;") == len(constraints)
    upper_sql = sql.upper()
    assert "ROW LEVEL SECURITY" not in upper_sql
    assert "CREATE POLICY" not in upper_sql
    assert "CURRENT_SETTING" not in upper_sql


def test_postgres_project_scope_migration_failure_is_retryable_and_contiguous(
    clock: ManualClock,
) -> None:
    failed = POSTGRES_MIGRATIONS[-1]
    connection = _FakePostgresConnection(fail_on=failed)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        PostgresMetadataStore(connection, clock).migrate()

    assert connection.applied == set(POSTGRES_MIGRATIONS[:-1])
    assert failed not in connection.executed_scripts
    assert connection.rollback_count == 1

    connection.fail_on = None
    PostgresMetadataStore(connection, clock).migrate()
    assert connection.applied == set(POSTGRES_MIGRATIONS)
    assert connection.executed_scripts == list(POSTGRES_MIGRATIONS)
