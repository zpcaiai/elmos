"""Persistent repository-context ledger invariants."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.context_ledger import ContextEventType, RepositoryContextLedger
from elmos_build_cache.db.store import SqliteMetadataStore
from elmos_build_cache.errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    IdempotencyConflict,
    VersionConflict,
)


def make_ledger(
    store: SqliteMetadataStore,
    *,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    stream_id: str = "context-stream-1",
    branch_lineage: str = "refs/heads/main@abc123",
    repository_snapshot_digest: str = digest("1"),
) -> RepositoryContextLedger:
    return RepositoryContextLedger(
        store,
        tenant_id,
        project_id,
        stream_id,
        branch_lineage,
        repository_snapshot_digest,
    )


def test_append_is_hash_linked_and_exactly_idempotent(store: SqliteMetadataStore) -> None:
    ledger = make_ledger(store)
    first = ledger.append(
        ContextEventType.FILE_READ,
        {"logical_path": "src/main.py", "content_digest": digest("a")},
        idempotency_key="read-main-v1",
        expected_sequence=0,
    )
    second = ledger.append(
        ContextEventType.TOOL_OBSERVED,
        {"tool": "pytest", "result_digest": digest("b")},
        idempotency_key="tool-pytest-v1",
        expected_sequence=1,
        expected_head_digest=first.event_digest,
    )

    replay = ledger.append(
        ContextEventType.FILE_READ,
        {"content_digest": digest("a"), "logical_path": "src/main.py"},
        idempotency_key="read-main-v1",
        # An ambiguous-response retry is exact even though the stream advanced.
        expected_sequence=0,
    )

    assert replay == first
    assert second.sequence == 2
    assert second.previous_event_digest == first.event_digest
    assert second.tenant_id == TENANT
    assert second.project_id == PROJECT
    assert second.branch_lineage == "refs/heads/main@abc123"
    assert second.repository_snapshot_digest == digest("1")
    assert ledger.position().head_event_digest == second.event_digest
    ledger.validate_chain()
    assert ledger.chain_is_valid()


def test_idempotency_payload_conflicts_fail_closed(store: SqliteMetadataStore) -> None:
    ledger = make_ledger(store)
    ledger.append(
        ContextEventType.FILE_READ,
        {"logical_path": "src/main.py", "content_digest": digest("a")},
        idempotency_key="read-main",
    )

    with pytest.raises(IdempotencyConflict):
        ledger.append(
            ContextEventType.FILE_READ,
            {"logical_path": "src/main.py", "content_digest": digest("b")},
            idempotency_key="read-main",
        )
    with pytest.raises(IdempotencyConflict):
        ledger.append(
            ContextEventType.CONTENT_REREAD,
            {"logical_path": "src/main.py", "content_digest": digest("a")},
            idempotency_key="read-main",
        )

    assert ledger.position().sequence == 1


def test_stale_projection_requires_a_reread_to_become_current(
    store: SqliteMetadataStore,
) -> None:
    ledger = make_ledger(store)
    ledger.append(
        ContextEventType.CONTENT_CHANGED,
        {"logical_path": "unread.py", "content_digest": digest("b")},
        idempotency_key="unread-change",
    )
    read = ledger.append(
        ContextEventType.FILE_READ,
        {"logical_path": "src/main.py", "content_digest": digest("a")},
        idempotency_key="read-main",
    )
    changed = ledger.append(
        ContextEventType.CONTENT_CHANGED,
        {"logical_path": "src/main.py", "content_digest": digest("b")},
        idempotency_key="change-main",
        supersedes_event_id=read.event_id,
    )

    stale = ledger.project_files()
    assert not stale.fresh
    assert len(stale.stale) == 1
    assert stale.stale[0].logical_path == "src/main.py"
    assert stale.stale[0].stale_event_id == changed.event_id
    assert stale.stale[0].changed_content_digest == digest("b")

    reread = ledger.append(
        ContextEventType.CONTENT_REREAD,
        {"logical_path": "src/main.py", "content_digest": digest("b")},
        idempotency_key="reread-main",
        supersedes_event_id=changed.event_id,
    )
    current = ledger.project_files()
    assert not current.stale
    assert len(current.fresh) == 1
    assert current.fresh[0].content_digest == digest("b")
    assert current.fresh[0].source_event_id == reread.event_id


def test_stale_expected_sequence_rejects_a_competing_writer(
    store: SqliteMetadataStore,
) -> None:
    writer_one = make_ledger(store)
    writer_two = make_ledger(store)
    writer_one.append(
        ContextEventType.SNAPSHOT_BOUND,
        {"snapshot_digest": digest("1")},
        idempotency_key="bind-snapshot",
        expected_sequence=0,
    )

    with pytest.raises(VersionConflict) as error:
        writer_two.append(
            ContextEventType.TOOL_OBSERVED,
            {"tool": "git-status"},
            idempotency_key="stale-writer",
            expected_sequence=0,
        )

    assert error.value.details == {
        "stream_id": "context-stream-1",
        "expected": 0,
        "actual": 1,
    }
    assert writer_one.position().sequence == 1


def test_stream_scope_cannot_switch_branch_or_snapshot(store: SqliteMetadataStore) -> None:
    make_ledger(store)
    with pytest.raises(ConflictError):
        make_ledger(store, branch_lineage="refs/heads/release@def456")
    with pytest.raises(ConflictError):
        make_ledger(store, repository_snapshot_digest=digest("2"))

    other_project = make_ledger(store, project_id="project-other")
    other_project.append(
        ContextEventType.TOOL_OBSERVED,
        {"tool": "project-isolated"},
        idempotency_key="same-key-is-project-scoped",
    )
    assert other_project.position().sequence == 1
    assert make_ledger(store).position().sequence == 0


def test_context_ledger_cannot_claim_an_existing_project_cross_tenant(
    store: SqliteMetadataStore,
) -> None:
    make_ledger(store)

    with pytest.raises(ConflictError, match="tenant scope conflict"):
        make_ledger(
            store,
            tenant_id="tenant-attacker",
            project_id=PROJECT,
            stream_id="attacker-stream",
        )

    assert store.query_one(
        "SELECT 1 FROM context_ledger_streams WHERE tenant_id=? AND project_id=?",
        ("tenant-attacker", PROJECT),
    ) is None
    assert store.query_one(
        "SELECT 1 FROM tenants WHERE tenant_id=?", ("tenant-attacker",)
    ) is None


@pytest.mark.parametrize(
    "injected",
    [
        {"source": "print('raw source')"},
        {"raw_prompt": "do everything"},
        {"secret_value": "plaintext-secret"},
        {"credential": "password"},
        {"access_token": "token"},
        {"metadata": {"prompt": "nested raw content"}},
        {"source_event_ids": [{"secret": "nested"}]},
    ],
)
def test_direct_ledger_append_rejects_raw_or_nested_content_fields(
    store: SqliteMetadataStore,
    injected: dict[str, object],
) -> None:
    ledger = make_ledger(store)
    payload: dict[str, object] = {
        "logical_path": "src/main.py",
        "content_digest": digest("a"),
        **injected,
    }

    with pytest.raises(ContractViolation):
        ledger.append(
            ContextEventType.FILE_READ,
            payload,  # type: ignore[arg-type] - hostile runtime input is intentional
            idempotency_key="raw-content-injection",
        )

    assert ledger.position().sequence == 0


def test_event_payload_contract_is_closed_even_for_benign_unknown_metadata(
    store: SqliteMetadataStore,
) -> None:
    ledger = make_ledger(store)
    with pytest.raises(ContractViolation, match="closed contract"):
        ledger.append(
            ContextEventType.TOOL_OBSERVED,
            {"tool": "pytest", "metadata": "unapproved"},
            idempotency_key="unknown-metadata",
        )

    assert ledger.position().sequence == 0


def test_content_free_identifier_fields_cannot_smuggle_raw_text(
    store: SqliteMetadataStore,
) -> None:
    ledger = make_ledger(store)
    with pytest.raises(ContractViolation, match="content-free identifier"):
        ledger.append(
            ContextEventType.TOOL_OBSERVED,
            {"tool": "paste raw prompt here"},
            idempotency_key="raw-tool-text",
        )

    assert ledger.position().sequence == 0


def test_chain_validation_detects_tampering(store: SqliteMetadataStore) -> None:
    ledger = make_ledger(store)
    event = ledger.append(
        ContextEventType.FILE_READ,
        {"logical_path": "src/main.py", "content_digest": digest("a")},
        idempotency_key="read-main",
    )

    tampered = (replace(event, payload={"logical_path": "src/other.py"}),)
    with pytest.raises(CorruptObject, match="payload digest"):
        ledger.validate_chain(tampered)


def test_committed_events_are_database_append_only(store: SqliteMetadataStore) -> None:
    ledger = make_ledger(store)
    event = ledger.append(
        ContextEventType.TOOL_OBSERVED,
        {"tool": "pytest"},
        idempotency_key="tool-observed",
    )

    with pytest.raises(sqlite3.IntegrityError, match="CONTEXT_LEDGER_APPEND_ONLY"):
        with store.transaction():
            store.execute(
                "UPDATE context_ledger_events SET payload=? WHERE event_id=?",
                ('{"rewritten":true}', event.event_id),
            )
    with pytest.raises(sqlite3.IntegrityError, match="CONTEXT_LEDGER_APPEND_ONLY"):
        with store.transaction():
            store.execute("DELETE FROM context_ledger_events WHERE event_id=?", (event.event_id,))

    assert ledger.events() == (event,)


def test_sqlite_migration_installs_context_tables_and_immutable_triggers(
    store: SqliteMetadataStore,
) -> None:
    applied = {str(row[0]) for row in store.query("SELECT name FROM schema_migrations")}
    assert "0003_context_ledger.sql" in applied
    objects = {
        (str(row[0]), str(row[1]))
        for row in store.query(
            "SELECT name, type FROM sqlite_master WHERE name LIKE 'context_%'"
        )
    }
    assert ("context_ledger_streams", "table") in objects
    assert ("context_ledger_events", "table") in objects
    assert ("context_checkpoints", "table") in objects
    assert ("context_ledger_events_no_update", "trigger") in objects
    assert ("context_ledger_events_no_delete", "trigger") in objects


def test_v1_2_sqlite_migration_is_additive_for_an_existing_v1_1_database(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "v1-1.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);"
    )
    for migration in ("0001_init.sql", "0002_saved_compiler_ms.sql"):
        connection.executescript(
            (root / "migrations" / "sqlite" / migration).read_text(encoding="utf-8")
        )
        connection.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (migration, "2026-08-20T00:00:00Z"),
        )
    connection.execute(
        "INSERT INTO tenants (tenant_id, created_at) VALUES (?, ?)",
        (TENANT, "2026-08-20T00:00:00Z"),
    )
    connection.execute(
        "INSERT INTO projects (project_id, tenant_id, name, created_at) VALUES (?, ?, ?, ?)",
        (PROJECT, TENANT, PROJECT, "2026-08-20T00:00:00Z"),
    )
    connection.commit()
    connection.close()

    upgraded = SqliteMetadataStore.open(database, clock)
    assert upgraded.query_one(
        "SELECT tenant_id FROM projects WHERE project_id=?", (PROJECT,)
    )[0] == TENANT
    assert upgraded.query_one(
        "SELECT name FROM schema_migrations WHERE name='0003_context_ledger.sql'"
    ) is not None
    ledger = make_ledger(upgraded)
    assert ledger.position().sequence == 0
    upgraded.close()


def test_postgres_migration_declares_scoped_jsonb_tables_and_append_only_guards() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = (root / "migrations" / "postgres" / "0005_context_ledger.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS context_ledger_streams" in sql
    assert "CREATE TABLE IF NOT EXISTS context_ledger_events" in sql
    assert "CREATE TABLE IF NOT EXISTS context_checkpoints" in sql
    assert "PRIMARY KEY (tenant_id, project_id, stream_id, sequence)" in sql
    assert "payload                    jsonb NOT NULL" in sql
    assert "sections                   jsonb NOT NULL" in sql
    assert "CONTEXT_LEDGER_APPEND_ONLY" in sql
    assert "context_ledger_events_no_update" in sql
    assert "context_ledger_events_no_delete" in sql
