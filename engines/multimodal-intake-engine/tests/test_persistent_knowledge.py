from __future__ import annotations

import hashlib
import inspect
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import elmos_multimodal_intake.persistent_knowledge as persistent_knowledge_module
from elmos_multimodal_intake.canonical import canonical_digest, canonical_json
from elmos_multimodal_intake.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    ValidationError,
)
from elmos_multimodal_intake.knowledge_worker import KnowledgeWorker
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.persistent_knowledge import PersistentKnowledgeStore
from elmos_multimodal_intake.store import IntakeStore


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _open(
    tmp_path: Path,
    *,
    worker_capability: object | None = None,
) -> tuple[IntakeStore, PersistentKnowledgeStore, TenantContext]:
    store = IntakeStore(tmp_path / "intake.sqlite3")
    context = TenantContext("tenant-a", "project-a", "actor-a")
    store.bootstrap_project(context)
    return store, PersistentKnowledgeStore(
        store,
        worker_capability=worker_capability,
    ), context


def _bind_source(
    store: IntakeStore,
    context: TenantContext,
    *,
    asset_id: str,
    source_digest: str,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    session_id = f"session-{asset_id}"
    with store.transaction() as connection:
        connection.execute(
            """
            INSERT INTO input_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                session_id,
                context.tenant_id,
                context.project_id,
                context.actor_id,
                "PROJECT_PACKAGE",
                "READY",
                f"source-session-{asset_id}",
                "0" * 64,
                f"trace-{asset_id}",
                1,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO input_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                asset_id,
                session_id,
                context.tenant_id,
                context.project_id,
                f"{asset_id}.txt",
                "text/plain",
                "text/plain",
                "TEXT",
                1,
                source_digest,
                source_digest,
                "READY",
                "ALLOW",
                None,
                1,
                now,
                now,
            ),
        )


def _worker_receipt(binding: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schema_version": "1.0.0",
        **binding,
        "executor_id": "knowledge-worker-1",
        "completed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    return {**body, "receipt_digest": canonical_digest(body)}


def _bind_anchor(
    store: IntakeStore,
    context: TenantContext,
    *,
    asset_id: str,
    source_digest: str,
    block_id: str,
    anchor_id: str,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with store.transaction() as connection:
        connection.execute(
            "INSERT INTO content_blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                block_id,
                context.tenant_id,
                context.project_id,
                asset_id,
                1,
                "1.0.0",
                0,
                "TEXT",
                "anchored text",
                '{"_elmos_trust_label":"UNTRUSTED_CONTENT"}',
                1.0,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO source_anchors VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                anchor_id,
                context.tenant_id,
                context.project_id,
                block_id,
                asset_id,
                source_digest,
                "line",
                None,
                None,
                1,
                1,
                None,
                None,
                None,
                None,
                _sha("anchored text"),
                now,
            ),
        )


class _RecordingTransport:
    def __init__(self, *, corrupt_digest: bool = False) -> None:
        self.corrupt_digest = corrupt_digest
        self.calls: list[dict[str, Any]] = []

    def deliver(
        self,
        event: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.calls.append({"event": dict(event), "idempotency_key": idempotency_key})
        corrupt_digest = "0" * 64
        if event["payload_digest"] == corrupt_digest:
            corrupt_digest = "1" * 64
        return {
            "event_id": event["event_id"],
            "payload_digest": corrupt_digest if self.corrupt_digest else event["payload_digest"],
            "delivery_state": "DELIVERED",
            "provider_message_id": f"provider-{event['event_id']}",
        }


def test_document_upsert_is_durable_versioned_and_idempotent(tmp_path: Path) -> None:
    store, knowledge, context = _open(tmp_path)
    text = "durable alpha knowledge"
    _bind_source(store, context, asset_id="asset-1", source_digest=_sha(text))
    first = knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="document-1",
        text=text,
        content_digest=_sha(text),
        source_digest=_sha(text),
        source_anchor={"asset_id": "asset-1"},
        required_permissions=["intake:read"],
        idempotency_key="document-write-1",
        expected_version=0,
    )
    replay = knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="document-1",
        text=text,
        content_digest=_sha(text),
        source_digest=_sha(text),
        source_anchor={"asset_id": "asset-1"},
        required_permissions=["intake:read"],
        idempotency_key="document-write-1",
        expected_version=0,
    )
    assert replay == first
    assert first["persisted"] is True
    assert first["version"] == 1
    assert first["retrieval_mode"] == "LEXICAL_LOCAL_SQLITE"

    with pytest.raises(ConflictError, match="KNOWLEDGE_IDEMPOTENCY_CONFLICT"):
        knowledge.upsert_document(
            context,
            branch="main",
            package_version="package-v1",
            document_id="document-1",
            text="different",
            content_digest=_sha("different"),
            source_digest=_sha("different"),
            source_anchor={"asset_id": "asset-1"},
            required_permissions=["intake:read"],
            idempotency_key="document-write-1",
        )

    store.close()
    reopened_store = IntakeStore(tmp_path / "intake.sqlite3")
    assert reopened_store._connection.execute("PRAGMA user_version").fetchone()[0] == 24
    reopened = PersistentKnowledgeStore(reopened_store)
    result = reopened.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="alpha",
    )
    assert [item["document_id"] for item in result["results"]] == ["document-1"]
    assert result["persistence_state"] == "LOCAL_DURABLE"
    assert result["vector_execution"] == "NOT_RUN"
    reopened_store.close()


def test_exact_scope_predicates_prevent_tenant_project_actor_branch_and_package_leakage(
    tmp_path: Path,
) -> None:
    store, knowledge, owner = _open(tmp_path)
    text = "scope sentinel"
    _bind_source(store, owner, asset_id="asset-scope", source_digest=_sha(text))
    knowledge.upsert_document(
        owner,
        branch="main",
        package_version="package-v1",
        document_id="scope-document",
        text=text,
        content_digest=_sha(text),
        source_digest=_sha(text),
        source_anchor={"asset_id": "asset-scope"},
        required_permissions=["intake:read"],
        idempotency_key="scope-document-write",
    )

    actor_b = TenantContext("tenant-a", "project-a", "actor-b")
    store.grant_permissions(owner, "actor-b", ["intake:read", "intake:write"])
    other_project = TenantContext("tenant-a", "project-b", "actor-a")
    store.bootstrap_project(other_project)
    other_tenant = TenantContext("tenant-b", "project-a", "actor-a")
    store.bootstrap_project(other_tenant)

    for context, branch, package_version in (
        (actor_b, "main", "package-v1"),
        (other_project, "main", "package-v1"),
        (other_tenant, "main", "package-v1"),
        (owner, "feature", "package-v1"),
        (owner, "main", "package-v2"),
    ):
        result = knowledge.query_documents(
            context,
            branch=branch,
            package_version=package_version,
            query="sentinel",
        )
        assert result["results"] == []
    store.close()


def test_acl_is_authoritative_and_content_cannot_grant_permissions(tmp_path: Path) -> None:
    store, knowledge, owner = _open(tmp_path)
    writer = TenantContext("tenant-a", "project-a", "actor-writer")
    store.grant_permissions(owner, "actor-writer", ["intake:read", "intake:write"])
    text = "permission protected"
    _bind_source(store, writer, asset_id="asset-protected", source_digest=_sha(text))

    with pytest.raises(AuthorizationError, match="KNOWLEDGE_REQUIRED_PERMISSION_DENIED"):
        knowledge.upsert_document(
            writer,
            branch="main",
            package_version="package-v1",
            document_id="protected-document",
            text=text,
            content_digest=_sha(text),
            source_digest=_sha(text),
            source_anchor={"asset_id": "asset-protected"},
            required_permissions=["intake:admin"],
            idempotency_key="protected-write",
        )

    unauthorized = TenantContext("tenant-a", "project-a", "actor-unknown")
    with pytest.raises(AuthorizationError, match="KNOWLEDGE_PROJECT_ACCESS_DENIED"):
        knowledge.query_documents(
            unauthorized,
            branch="main",
            package_version="package-v1",
            query="permission",
        )
    store.close()


def test_project_memory_persists_versions_and_never_crosses_package_scope(tmp_path: Path) -> None:
    store, knowledge, context = _open(tmp_path)
    source_digest = _sha("source-one")
    _bind_source(store, context, asset_id="asset-design", source_digest=source_digest)
    first = knowledge.write_memory(
        context,
        branch="main",
        package_version="package-v1",
        memory_key="architecture.database",
        value={"engine": "sqlite", "durable": True},
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-design"},
        required_permissions=["intake:read"],
        idempotency_key="memory-write-1",
        expected_version=0,
    )
    second = knowledge.write_memory(
        context,
        branch="main",
        package_version="package-v1",
        memory_key="architecture.database",
        value={"engine": "postgresql", "durable": True},
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-design"},
        required_permissions=["intake:read"],
        idempotency_key="memory-write-2",
        expected_version=1,
        memory_kind="DECISION",
        semantic_state="CONFLICTING",
        confidence=0.75,
    )
    assert first["version"] == 1
    assert second["version"] == 2

    current = knowledge.query_memory(
        context,
        branch="main",
        package_version="package-v1",
        query="postgresql",
    )
    assert len(current["results"]) == 1
    assert current["results"][0]["version"] == 2
    assert current["results"][0]["value"]["engine"] == "postgresql"
    assert current["results"][0]["memory_kind"] == "DECISION"
    assert current["results"][0]["semantic_state"] == "CONFLICTING"
    assert current["results"][0]["confidence"] == 0.75
    assert current["persistent_read_performed"] is True

    other_package = knowledge.query_memory(
        context,
        branch="main",
        package_version="package-v2",
        query="postgresql",
    )
    assert other_package["results"] == []
    store.close()


def test_source_delete_is_atomic_visible_immediately_and_tracks_rebuild_outbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_capability = object()
    store, knowledge, context = _open(
        tmp_path,
        worker_capability=worker_capability,
    )
    source = "shared source"
    source_digest = _sha("original asset bytes")
    _bind_source(store, context, asset_id="asset-delete", source_digest=source_digest)
    knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="delete-document",
        text=source,
        content_digest=_sha(source),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-delete"},
        required_permissions=["intake:read"],
        idempotency_key="delete-document-write",
    )
    knowledge.write_memory(
        context,
        branch="main",
        package_version="package-v1",
        memory_key="delete.memory",
        value={"note": "shared source"},
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-delete"},
        required_permissions=["intake:read"],
        idempotency_key="delete-memory-write",
    )

    deleted = knowledge.delete_by_source_digest(
        context,
        branch="main",
        package_version="package-v1",
        source_digest=source_digest,
        idempotency_key="delete-source-1",
    )
    assert deleted["affected_document_count"] == 1
    assert deleted["affected_memory_count"] == 1
    assert deleted["affected_record_count"] == 2
    assert deleted["source_tombstone_state"] == "ACTIVE"
    assert deleted["local_visibility_state"] == "COMPLETE"
    assert deleted["deletion_propagation_state"] == "PENDING"
    assert len(deleted["rebuild_ids"]) == 2
    assert knowledge.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="shared",
    )["results"] == []
    assert knowledge.query_memory(
        context,
        branch="main",
        package_version="package-v1",
        query="shared",
    )["results"] == []

    pending = knowledge.list_rebuild_jobs(
        context,
        branch="main",
        package_version="package-v1",
        status="PENDING",
    )
    assert {item["target"] for item in pending} == {"content-index", "project-memory"}
    selected_rebuild = deleted["rebuild_ids"][0]
    selected_job = next(item for item in pending if item["rebuild_id"] == selected_rebuild)
    running_receipt = _worker_receipt(
        {
            "rebuild_id": selected_rebuild,
            "cause_digest": selected_job["cause_digest"],
            "from_state": "PENDING",
            "target_state": "RUNNING",
            "failure_code": None,
        }
    )
    with pytest.raises(AuthorizationError, match="KNOWLEDGE_WORKER_AUTHORITY_REQUIRED"):
        knowledge.transition_rebuild(
            context,
            rebuild_id=selected_rebuild,
            target_state="RUNNING",
            idempotency_key="rebuild-running-denied",
            worker_capability=object(),
            execution_receipt=running_receipt,
        )
    running = knowledge.transition_rebuild(
        context,
        rebuild_id=selected_rebuild,
        target_state="RUNNING",
        idempotency_key="rebuild-running-1",
        worker_capability=worker_capability,
        execution_receipt=running_receipt,
    )
    assert running["status"] == "RUNNING"
    assert running["attempt"] == 1
    assert knowledge.transition_rebuild(
        context,
        rebuild_id=selected_rebuild,
        target_state="RUNNING",
        idempotency_key="rebuild-running-1",
        worker_capability=worker_capability,
        execution_receipt=running_receipt,
    ) == running

    class _FutureDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime.now(tz or UTC) + timedelta(days=2)

    with monkeypatch.context() as patch:
        patch.setattr(persistent_knowledge_module, "datetime", _FutureDateTime)
        assert knowledge.transition_rebuild(
            context,
            rebuild_id=selected_rebuild,
            target_state="RUNNING",
            idempotency_key="rebuild-running-1",
            worker_capability=worker_capability,
            execution_receipt=running_receipt,
        ) == running
        with pytest.raises(ValidationError, match="KNOWLEDGE_WORKER_RECEIPT_INVALID"):
            knowledge.transition_rebuild(
                context,
                rebuild_id=selected_rebuild,
                target_state="RUNNING",
                idempotency_key="rebuild-running-expired-new-key",
                worker_capability=worker_capability,
                execution_receipt=running_receipt,
            )
    rebuilt = knowledge.rebuild_lexical_index(
        context,
        branch="main",
        package_version="package-v1",
        target=selected_job["target"],
        idempotency_key="rebuild-executed-1",
    )
    assert rebuilt["rebuild_state"] == "SUCCEEDED"
    assert rebuilt["rebuilt_digest"]
    completed = knowledge.list_rebuild_jobs(
        context,
        branch="main",
        package_version="package-v1",
        status="SUCCEEDED",
    )
    selected_completion = next(
        item for item in completed if item["rebuild_id"] == selected_rebuild
    )
    assert selected_completion["target"] == selected_job["target"]
    assert selected_completion["cause_digest"] == selected_job["cause_digest"]
    assert selected_completion["rebuilt_digest"] == rebuilt["rebuilt_digest"]
    assert selected_completion["completion_event_id"]
    assert selected_completion["completed_at"]
    events = knowledge.outbox_events(context)
    assert {item["event_type"] for item in events} >= {
        "KNOWLEDGE_DOCUMENT_UPSERTED",
        "PROJECT_MEMORY_WRITTEN",
        "KNOWLEDGE_SOURCE_TOMBSTONED",
    }
    claim_token = "knowledge-claim-persistent-test"
    claimed_event = knowledge.claim_next_outbox_event(
        context,
        worker_capability=worker_capability,
        claim_token=claim_token,
        executor_id="knowledge-worker-1",
    )
    assert claimed_event is not None
    knowledge.mark_outbox_dispatching(
        context,
        claimed_event["event_id"],
        worker_capability=worker_capability,
        claim_token=claim_token,
    )
    transport_receipt = {
        "event_id": claimed_event["event_id"],
        "payload_digest": claimed_event["payload_digest"],
        "delivery_state": "DELIVERED",
        "provider_message_id": "provider-message-1",
    }
    delivery_receipt = _worker_receipt(
        {
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "actor_id": context.actor_id,
            "event_id": claimed_event["event_id"],
            "event_type": claimed_event["event_type"],
            "aggregate_id": claimed_event["aggregate_id"],
            "payload_digest": claimed_event["payload_digest"],
            "delivery_state": "DELIVERED",
            "provider_message_id": "provider-message-1",
            "attempt": claimed_event["delivery_attempt"],
            "claim_token_digest": claimed_event["claim_token_digest"],
            "transport_receipt_digest": canonical_digest(transport_receipt),
        }
    )
    publication = knowledge.mark_outbox_published(
        context,
        claimed_event["event_id"],
        worker_capability=worker_capability,
        delivery_receipt=delivery_receipt,
        claim_token=claim_token,
        transport_receipt=transport_receipt,
    )
    assert publication["published_at"]
    assert knowledge.mark_outbox_published(
        context,
        claimed_event["event_id"],
        worker_capability=worker_capability,
        delivery_receipt=delivery_receipt,
        claim_token=claim_token,
        transport_receipt=transport_receipt,
    ) == publication
    with monkeypatch.context() as patch:
        patch.setattr(persistent_knowledge_module, "datetime", _FutureDateTime)
        assert knowledge.mark_outbox_published(
            context,
            claimed_event["event_id"],
            worker_capability=worker_capability,
            delivery_receipt=delivery_receipt,
            claim_token=claim_token,
            transport_receipt=transport_receipt,
        ) == publication
    store.close()


def test_stored_json_digest_tampering_fails_closed(tmp_path: Path) -> None:
    store, knowledge, context = _open(tmp_path)
    text = "integrity marker"
    _bind_source(store, context, asset_id="asset-integrity", source_digest=_sha(text))
    knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="integrity-document",
        text=text,
        content_digest=_sha(text),
        source_digest=_sha(text),
        source_anchor={"asset_id": "asset-integrity"},
        required_permissions=["intake:read"],
        idempotency_key="integrity-write",
    )
    with store.transaction() as connection:
        connection.execute(
            """
            UPDATE knowledge_documents SET source_anchor_json='{}'
             WHERE tenant_id='tenant-a' AND project_id='project-a'
               AND actor_id='actor-a' AND document_id='integrity-document'
            """
        )
    with pytest.raises(IntegrityError, match="KNOWLEDGE_STORED_DIGEST_MISMATCH"):
        knowledge.query_documents(
            context,
            branch="main",
            package_version="package-v1",
            query="integrity",
        )
    store.close()


def test_rebuild_repairs_the_exact_local_lexical_index(tmp_path: Path) -> None:
    store, knowledge, context = _open(tmp_path)
    text = "repairable lexical marker"
    _bind_source(
        store,
        context,
        asset_id="asset-repair",
        source_digest=_sha("repair-source"),
    )
    knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="repair-document",
        text=text,
        content_digest=_sha(text),
        source_digest=_sha("repair-source"),
        source_anchor={"asset_id": "asset-repair"},
        required_permissions=["intake:read"],
        idempotency_key="repair-write",
    )
    with store.transaction() as connection:
        connection.execute(
            """
            DELETE FROM knowledge_document_terms
             WHERE tenant_id='tenant-a' AND project_id='project-a'
               AND actor_id='actor-a' AND document_id='repair-document'
            """
        )
    assert knowledge.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="repairable",
    )["results"] == []

    rebuilt = knowledge.rebuild_lexical_index(
        context,
        branch="main",
        package_version="package-v1",
        target="content-index",
        idempotency_key="repair-rebuild",
    )
    assert rebuilt["rebuild_state"] == "SUCCEEDED"
    assert rebuilt["record_count"] == 1
    assert rebuilt["term_count"] >= 2
    assert knowledge.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="repairable",
    )["results"][0]["document_id"] == "repair-document"
    store.close()


def test_raw_empty_database_migrates_to_v24_and_remains_intake_store_compatible(
    tmp_path: Path,
) -> None:
    database = tmp_path / "raw.sqlite3"
    connection = sqlite3.connect(database, isolation_level=None)
    PersistentKnowledgeStore(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 24
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        ).fetchall()
    }
    assert {
        "input_sessions",
        "knowledge_documents",
        "knowledge_outbox_publications",
        "knowledge_outbox_delivery_states",
        "knowledge_source_tombstones",
        "knowledge_rebuild_completions",
    }.issubset(tables)
    connection.execute("PRAGMA user_version = 25")
    with pytest.raises(IntegrityError, match="KNOWLEDGE_SCHEMA_VERSION_UNSUPPORTED"):
        PersistentKnowledgeStore(connection)
    connection.execute("PRAGMA user_version = 24")
    connection.close()

    store = IntakeStore(database)
    context = TenantContext("tenant-raw", "project-raw", "actor-raw")
    store.bootstrap_project(context)
    PersistentKnowledgeStore(store)
    assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 24
    store.close()


def test_v13_core_outbox_migration_keeps_legacy_payload_unbound(
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(tmp_path / "legacy-core-outbox.sqlite3", isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE outbox_events (
            event_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            published_at TEXT,
            UNIQUE (tenant_id, project_id, event_id),
            UNIQUE (tenant_id, project_id, idempotency_key)
        );
        INSERT INTO outbox_events VALUES (
            'evt-legacy','tenant-a','project-a','input_session','session-a',
            'input.session.created','legacy-key','{"status":"DRAFT"}',
            '2026-08-22T00:00:00+00:00',NULL
        );
        PRAGMA user_version = 12;
        """
    )
    engine_root = Path(__file__).resolve().parents[1]
    source_sql = (engine_root / "migrations" / "013_core_outbox_payload_integrity.sql").read_text(
        encoding="utf-8"
    )
    packaged_sql = (
        engine_root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "013_core_outbox_payload_integrity.sql"
    ).read_text(encoding="utf-8")
    assert packaged_sql == source_sql
    connection.executescript(source_sql)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
    row = connection.execute("SELECT * FROM outbox_events").fetchone()
    assert row["payload_digest"] is None
    with pytest.raises(ConflictError, match="OUTBOX_EVENT_RECONCILIATION_REQUIRED") as raised:
        IntakeStore._materialize_core_outbox_row(
            row,
            expected_tenant_id="tenant-a",
            expected_project_id="project-a",
        )
    assert raised.value.retryable is False
    connection.close()


def test_migration_refuses_an_active_caller_transaction_without_rolling_it_back(
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(tmp_path / "active.sqlite3", isolation_level=None)
    connection.execute("CREATE TABLE transaction_probe (value TEXT NOT NULL)")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO transaction_probe VALUES ('uncommitted')")
    with pytest.raises(IntegrityError, match="MIGRATION_ACTIVE_TRANSACTION_FORBIDDEN"):
        PersistentKnowledgeStore(connection)
    assert connection.in_transaction is True
    assert connection.execute("SELECT count(*) FROM transaction_probe").fetchone()[0] == 1
    connection.rollback()
    assert connection.execute("SELECT count(*) FROM transaction_probe").fetchone()[0] == 0
    connection.close()


def test_schema_definition_drift_fails_even_when_expected_index_name_exists(
    tmp_path: Path,
) -> None:
    database = tmp_path / "drift.sqlite3"
    connection = sqlite3.connect(database, isolation_level=None)
    PersistentKnowledgeStore(connection)
    connection.close()

    drifted = sqlite3.connect(database, isolation_level=None)
    drifted.execute("DROP INDEX knowledge_documents_current_idx")
    drifted.execute(
        "CREATE INDEX knowledge_documents_current_idx ON project_acl (tenant_id)"
    )
    with pytest.raises(IntegrityError, match="KNOWLEDGE_SCHEMA_DEFINITION_DRIFT"):
        PersistentKnowledgeStore(drifted)
    drifted.close()


def test_query_filters_a_source_revoked_after_persistence(tmp_path: Path) -> None:
    store, knowledge, context = _open(tmp_path)
    source_digest = _sha("revocable-source")
    _bind_source(
        store,
        context,
        asset_id="asset-revocable",
        source_digest=source_digest,
    )
    knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="revocable-document",
        text="revocable knowledge marker",
        content_digest=_sha("revocable knowledge marker"),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-revocable"},
        required_permissions=["intake:read"],
        idempotency_key="revocable-write",
    )
    assert knowledge.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="revocable",
    )["results"]
    with store.transaction() as connection:
        connection.execute(
            """
            UPDATE input_assets
               SET status='QUARANTINED',security_decision='QUARANTINE',version=version+1
             WHERE tenant_id=? AND project_id=? AND asset_id=?
            """,
            (context.tenant_id, context.project_id, "asset-revocable"),
        )
    result = knowledge.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="revocable",
    )
    assert result["results"] == []
    assert result["source_revoked_filtered_count"] == 1
    store.close()


def test_source_anchor_accepts_only_exact_asset_or_bound_anchor_shapes(
    tmp_path: Path,
) -> None:
    store, knowledge, context = _open(tmp_path)
    source_digest = _sha("anchored-source")
    _bind_source(
        store,
        context,
        asset_id="asset-anchor",
        source_digest=source_digest,
    )
    _bind_anchor(
        store,
        context,
        asset_id="asset-anchor",
        source_digest=source_digest,
        block_id="block-anchor",
        anchor_id="anchor-1",
    )
    persisted = knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="anchored-document",
        text="strict anchored marker",
        content_digest=_sha("strict anchored marker"),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-anchor", "anchor_id": "anchor-1"},
        required_permissions=["intake:read"],
        idempotency_key="anchored-write",
    )
    assert persisted["persisted"] is True

    with pytest.raises(ValidationError, match="KNOWLEDGE_SOURCE_ANCHOR_FIELDS_INVALID"):
        knowledge.upsert_document(
            context,
            branch="main",
            package_version="package-v1",
            document_id="anchor-extra-field",
            text="extra anchor field marker",
            content_digest=_sha("extra anchor field marker"),
            source_digest=source_digest,
            source_anchor={
                "asset_id": "asset-anchor",
                "anchor_id": "anchor-1",
                "page": 1,
            },
            required_permissions=["intake:read"],
            idempotency_key="anchor-extra-field-write",
        )
    with pytest.raises(IntegrityError, match="KNOWLEDGE_SOURCE_ANCHOR_NOT_FOUND"):
        knowledge.upsert_document(
            context,
            branch="main",
            package_version="package-v1",
            document_id="anchor-missing",
            text="missing anchor marker",
            content_digest=_sha("missing anchor marker"),
            source_digest=source_digest,
            source_anchor={"asset_id": "asset-anchor", "anchor_id": "anchor-missing"},
            required_permissions=["intake:read"],
            idempotency_key="anchor-missing-write",
        )
    store.close()


def test_source_delete_streams_more_than_five_hundred_records_without_truncation(
    tmp_path: Path,
) -> None:
    store, knowledge, context = _open(tmp_path)
    source_digest = _sha("bulk-source")
    _bind_source(store, context, asset_id="asset-bulk", source_digest=source_digest)
    anchor_json = canonical_json({"asset_id": "asset-bulk"})
    permissions_json = canonical_json(["intake:read"])
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    documents: list[tuple[Any, ...]] = []
    terms: list[tuple[Any, ...]] = []
    for ordinal in range(501):
        document_id = f"bulk-document-{ordinal:03d}"
        text = f"bulk marker {ordinal}"
        documents.append(
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                "main",
                "package-v1",
                document_id,
                1,
                "CURRENT",
                text,
                _sha(text),
                source_digest,
                anchor_json,
                _sha(anchor_json),
                permissions_json,
                _sha(permissions_json),
                1.0,
                now,
                now,
            )
        )
        terms.append(
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                "main",
                "package-v1",
                document_id,
                1,
                "marker",
            )
        )
    with store.transaction() as connection:
        connection.executemany(
            "INSERT INTO knowledge_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            documents,
        )
        connection.executemany(
            "INSERT INTO knowledge_document_terms VALUES (?,?,?,?,?,?,?,?)",
            terms,
        )

    deleted = knowledge.delete_by_source_digest(
        context,
        branch="main",
        package_version="package-v1",
        source_digest=source_digest,
        idempotency_key="bulk-delete",
    )
    assert deleted["affected_document_count"] == 501
    assert deleted["affected_record_count"] == 501
    assert len(deleted["record_set_digest"]) == 64
    with store.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge_documents WHERE status='DELETED'"
        ).fetchone()[0] == 501
        assert connection.execute(
            "SELECT count(*) FROM knowledge_document_terms"
        ).fetchone()[0] == 0
        tombstone = connection.execute(
            "SELECT record_count FROM knowledge_source_tombstones WHERE source_digest=?",
            (source_digest,),
        ).fetchone()
        assert tombstone["record_count"] == 501
    store.close()


def test_source_reintroduction_clears_tombstone_and_creates_new_generation(
    tmp_path: Path,
) -> None:
    store, knowledge, context = _open(tmp_path)
    source_digest = _sha("reintroduced-source")
    text = "reintroduced generation marker"
    _bind_source(
        store,
        context,
        asset_id="asset-reintroduced",
        source_digest=source_digest,
    )
    first_write = knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="reintroduced-document",
        text=text,
        content_digest=_sha(text),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-reintroduced"},
        required_permissions=["intake:read"],
        idempotency_key="reintroduced-write-1",
        expected_version=0,
    )
    first_delete = knowledge.delete_by_source_digest(
        context,
        branch="main",
        package_version="package-v1",
        source_digest=source_digest,
        idempotency_key="reintroduced-delete-1",
    )
    second_write = knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="reintroduced-document",
        text=text,
        content_digest=_sha(text),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-reintroduced"},
        required_permissions=["intake:read"],
        idempotency_key="reintroduced-write-2",
        expected_version=1,
    )
    assert first_write["version"] == 1
    assert second_write["version"] == 2
    assert second_write["source_tombstone_cleared"] is True
    assert second_write["rebuild_id"] != first_write["rebuild_id"]
    assert knowledge.query_documents(
        context,
        branch="main",
        package_version="package-v1",
        query="reintroduced",
    )["results"][0]["version"] == 2
    assert store._connection.execute(
        "SELECT count(*) FROM knowledge_source_tombstones WHERE source_digest=?",
        (source_digest,),
    ).fetchone()[0] == 0

    second_delete = knowledge.delete_by_source_digest(
        context,
        branch="main",
        package_version="package-v1",
        source_digest=source_digest,
        idempotency_key="reintroduced-delete-2",
    )
    assert second_delete["affected_record_count"] == 1
    assert second_delete["record_set_digest"] != first_delete["record_set_digest"]
    assert (
        second_delete["deletion_generation_digest"]
        != first_delete["deletion_generation_digest"]
    )
    assert set(second_delete["rebuild_ids"]).isdisjoint(first_delete["rebuild_ids"])
    store.close()


def test_runtime_owned_worker_bounds_rebuild_and_delivers_each_polled_event_once(
    tmp_path: Path,
) -> None:
    worker_capability = object()
    store, knowledge, context = _open(
        tmp_path,
        worker_capability=worker_capability,
    )
    source_digest = _sha("worker-source")
    _bind_source(store, context, asset_id="asset-worker", source_digest=source_digest)
    write = knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="worker-document",
        text="worker rebuild marker",
        content_digest=_sha("worker rebuild marker"),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-worker"},
        required_permissions=["intake:read"],
        idempotency_key="worker-write",
    )
    transport = _RecordingTransport()
    worker = KnowledgeWorker(
        knowledge,
        context=context,
        branch="main",
        package_version="package-v1",
        worker_capability=worker_capability,
        transport=transport,
        executor_id="knowledge-worker-1",
        max_rebuild_targets=1,
        max_outbox_events=2,
    )
    assert inspect.signature(worker.run_once).parameters == {}

    first = worker.run_once()
    assert first["state"] == "SUCCEEDED"
    assert len(first["rebuild_results"]) == 1
    assert len(first["publication_results"]) == 2
    assert first["rebuild_results"][0]["rebuild_id"] == write["rebuild_id"]
    first_body = dict(first)
    first_digest = first_body.pop("receipt_digest")
    assert first_digest == canonical_digest(first_body)

    second = worker.run_once()
    assert second["state"] == "SUCCEEDED"
    assert second["rebuild_results"] == []
    assert len(second["publication_results"]) == 2
    third = worker.run_once()
    assert third["state"] == "IDLE"
    assert third["rebuild_results"] == []
    assert third["publication_results"] == []
    assert knowledge.outbox_events(context, unpublished_only=True) == []
    delivered_event_ids = [call["event"]["event_id"] for call in transport.calls]
    assert len(delivered_event_ids) == len(set(delivered_event_ids)) == 4
    assert len({call["idempotency_key"] for call in transport.calls}) == 4
    assert all("command" not in call["event"] for call in transport.calls)
    store.close()


def test_worker_rejects_untrusted_authority_and_transport_evidence_fail_closed(
    tmp_path: Path,
) -> None:
    worker_capability = object()
    store, knowledge, context = _open(
        tmp_path,
        worker_capability=worker_capability,
    )
    source_digest = _sha("worker-invalid-source")
    _bind_source(
        store,
        context,
        asset_id="asset-worker-invalid",
        source_digest=source_digest,
    )
    knowledge.upsert_document(
        context,
        branch="main",
        package_version="package-v1",
        document_id="worker-invalid-document",
        text="worker invalid evidence marker",
        content_digest=_sha("worker invalid evidence marker"),
        source_digest=source_digest,
        source_anchor={"asset_id": "asset-worker-invalid"},
        required_permissions=["intake:read"],
        idempotency_key="worker-invalid-write",
    )
    with pytest.raises(AuthorizationError, match="KNOWLEDGE_WORKER_AUTHORITY_REQUIRED"):
        KnowledgeWorker(
            knowledge,
            context=context,
            branch="main",
            package_version="package-v1",
            worker_capability=object(),
            transport=_RecordingTransport(),
            executor_id="knowledge-worker-untrusted",
        )

    worker = KnowledgeWorker(
        knowledge,
        context=context,
        branch="main",
        package_version="package-v1",
        worker_capability=worker_capability,
        transport=_RecordingTransport(corrupt_digest=True),
        executor_id="knowledge-worker-invalid-evidence",
    )
    with pytest.raises(IntegrityError, match="KNOWLEDGE_OUTBOX_TRANSPORT_EVIDENCE_INVALID"):
        worker.run_once()
    unpublished = knowledge.outbox_events(context, unpublished_only=True)
    assert unpublished
    assert all(event["published_at"] is None for event in unpublished)
    assert knowledge.outbox_events(context, unpublished_only=False)[0][
        "publication_receipt"
    ] is None
    store.close()
