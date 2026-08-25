from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import elmos_multimodal_intake.store as store_module
from elmos_multimodal_intake.canonical import canonical_json
from elmos_multimodal_intake.errors import AuthorizationError, ConflictError, IntegrityError, ValidationError
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.store import IntakeStore


def _configured_store(
    database: Path,
) -> tuple[IntakeStore, TenantContext, object, object]:
    publisher = object()
    response_verifier = object()
    store = IntakeStore(
        database,
        outbox_publisher_capability=publisher,
        outbox_response_verifier_capability=response_verifier,
    )
    context = TenantContext("tenant-outbox", "project-outbox", "actor-outbox")
    store.bootstrap_project(context)
    return store, context, publisher, response_verifier


def _event(store: IntakeStore, context: TenantContext, suffix: str) -> dict[str, object]:
    with store.transaction() as connection:
        event_id = store._event(
            connection,
            context,
            "test_aggregate",
            f"aggregate-{suffix}",
            "test.aggregate.changed",
            f"core-outbox-{suffix}",
            {"state": "READY", "suffix": suffix},
        )
    return next(item for item in store.outbox_events(context) if item["event_id"] == event_id)


def _receipt(event: dict[str, object], *, delivered_at: str | None = None) -> dict[str, object]:
    return {
        "schema_version": "core-outbox-transport-receipt-v1",
        "event_id": event["event_id"],
        "payload_digest": event["payload_digest"],
        "transport": "test-transport",
        "delivery_id": f"delivery-{str(event['event_id'])[-20:]}",
        "status": "DELIVERED",
        "delivered_at": delivered_at or event["occurred_at"],
        "response_digest": "f" * 64,
    }


def test_v24_migration_is_mirrored_and_scope_bound() -> None:
    engine_root = Path(__file__).resolve().parents[1]
    root = engine_root / "migrations" / "024_core_outbox_delivery_receipts.sql"
    packaged = (
        engine_root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "024_core_outbox_delivery_receipts.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
    sql = "".join(root.read_text(encoding="utf-8").lower().split())
    assert "foreignkey(tenant_id,project_id,event_id)" in sql
    assert "referencesoutbox_events(tenant_id,project_id,event_id)" in sql
    assert "actor_idtextnotnull" in sql
    assert "verified_response_digesttextnotnull" in sql
    assert "response_verifier_capability_idtextnotnull" in sql


def test_v23_validator_rejects_removed_cancel_requested_check(tmp_path: Path) -> None:
    database = tmp_path / "v23-check-removed.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='processing_jobs'"
        ).fetchone()[0]
        weakened_sql, replacement_count = re.subn(
            r"\s+CHECK\s*\(\s*cancel_requested\s+IN\s*\(\s*0\s*,\s*1\s*\)\s*\)",
            "",
            table_sql,
            count=1,
            flags=re.IGNORECASE,
        )
        assert replacement_count == 1
        schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
        connection.execute("PRAGMA writable_schema = ON")
        try:
            connection.execute(
                "UPDATE sqlite_master SET sql=? WHERE type='table' AND name='processing_jobs'",
                (weakened_sql,),
            )
        finally:
            connection.execute("PRAGMA writable_schema = OFF")
        connection.commit()
        connection.execute(f"PRAGMA schema_version = {schema_version + 1}")

    with pytest.raises(
        IntegrityError,
        match="PROCESSING_JOB_CANCELLATION_SCHEMA_INVALID",
    ):
        IntakeStore(database)


def test_core_outbox_receipt_requires_verifier_and_persists_strong_binding(
    tmp_path: Path,
) -> None:
    store, context, publisher, verifier = _configured_store(tmp_path / "receipt.sqlite3")
    try:
        event = _event(store, context, "verified")
        receipt = _receipt(event)
        with pytest.raises(
            AuthorizationError,
            match="OUTBOX_RESPONSE_VERIFIER_AUTHORITY_REQUIRED",
        ):
            store.mark_outbox_published(
                context,
                str(event["event_id"]),
                publisher_capability=publisher,
                response_verifier_capability=object(),
                transport_receipt=receipt,
            )

        published = store.mark_outbox_published(
            context,
            str(event["event_id"]),
            publisher_capability=publisher,
            response_verifier_capability=verifier,
            transport_receipt=receipt,
        )
        assert published["verified_response_digest"] == receipt["response_digest"]
        row = store._connection.execute(
            "SELECT * FROM core_outbox_delivery_receipts WHERE event_id=?",
            (event["event_id"],),
        ).fetchone()
        assert row["tenant_id"] == context.tenant_id
        assert row["project_id"] == context.project_id
        assert row["actor_id"] == context.actor_id
        assert row["verified_response_digest"] == receipt["response_digest"]
        assert row["receipt_json"] == canonical_json(receipt)
        assert row["publisher_capability_id"] != row["response_verifier_capability_id"]

        other_actor = TenantContext(context.tenant_id, context.project_id, "actor-outbox-admin")
        store.grant_permissions(context, other_actor.actor_id, (store.WRITE,))
        with pytest.raises(ConflictError, match="OUTBOX_TRANSPORT_RECEIPT_CONFLICT"):
            store.mark_outbox_published(
                other_actor,
                str(event["event_id"]),
                publisher_capability=publisher,
                response_verifier_capability=verifier,
                transport_receipt=receipt,
            )
    finally:
        store.close()


def test_core_outbox_receipt_rejects_unreasonable_future_delivery(tmp_path: Path) -> None:
    store, context, publisher, verifier = _configured_store(tmp_path / "future.sqlite3")
    try:
        event = _event(store, context, "future")
        future = (datetime.now(UTC) + timedelta(minutes=6)).replace(microsecond=0).isoformat()
        with pytest.raises(ValidationError, match="OUTBOX_TRANSPORT_RECEIPT_INVALID"):
            store.mark_outbox_published(
                context,
                str(event["event_id"]),
                publisher_capability=publisher,
                response_verifier_capability=verifier,
                transport_receipt=_receipt(event, delivered_at=future),
            )
    finally:
        store.close()


@pytest.mark.parametrize("object_kind", ("index", "trigger"))
def test_v24_validator_rejects_same_name_noop_schema_objects(
    tmp_path: Path,
    object_kind: str,
) -> None:
    database = tmp_path / f"noop-{object_kind}.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        if object_kind == "index":
            connection.executescript(
                """
                DROP INDEX core_outbox_delivery_scope_idx;
                CREATE INDEX core_outbox_delivery_scope_idx
                    ON core_outbox_delivery_receipts (event_id);
                """
            )
        else:
            connection.executescript(
                """
                DROP TRIGGER core_outbox_delivery_receipts_no_update;
                CREATE TRIGGER core_outbox_delivery_receipts_no_update
                BEFORE UPDATE ON core_outbox_delivery_receipts
                WHEN 0
                BEGIN
                    SELECT RAISE(ABORT, 'core outbox delivery receipt immutable');
                END;
                """
            )

    with pytest.raises(IntegrityError, match="CORE_OUTBOX_DELIVERY_SCHEMA_INVALID"):
        IntakeStore(database)


def test_v24_validator_rejects_single_column_foreign_key(tmp_path: Path) -> None:
    database = tmp_path / "weak-fk.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        table_sql = connection.execute(
            """SELECT sql FROM sqlite_master
                WHERE type='table' AND name='core_outbox_delivery_receipts'"""
        ).fetchone()[0]
        strong_fk = (
            "FOREIGN KEY (tenant_id, project_id, event_id)\n"
            "        REFERENCES outbox_events (tenant_id, project_id, event_id)"
        )
        weak_fk = "FOREIGN KEY (event_id) REFERENCES outbox_events (event_id)"
        tampered_sql = table_sql.replace(strong_fk, weak_fk, 1)
        assert tampered_sql != table_sql
        objects = connection.execute(
            """SELECT type,name,sql FROM sqlite_master
                WHERE tbl_name='core_outbox_delivery_receipts'
                  AND type IN ('index','trigger') AND sql IS NOT NULL"""
        ).fetchall()
        for object_type, name, _sql in objects:
            connection.execute(f'DROP {object_type.upper()} "{name}"')
        connection.execute(
            'ALTER TABLE core_outbox_delivery_receipts RENAME TO core_outbox_delivery_receipts_old'
        )
        connection.execute(tampered_sql)
        for _object_type, _name, object_sql in objects:
            connection.execute(object_sql)
        connection.execute("DROP TABLE core_outbox_delivery_receipts_old")

    with pytest.raises(IntegrityError, match="CORE_OUTBOX_DELIVERY_SCHEMA_INVALID"):
        IntakeStore(database)


def test_v24_validator_scans_cross_scope_history(tmp_path: Path) -> None:
    database = tmp_path / "cross-scope.sqlite3"
    store, context, publisher, verifier = _configured_store(database)
    event = _event(store, context, "cross-scope")
    store.mark_outbox_published(
        context,
        str(event["event_id"]),
        publisher_capability=publisher,
        response_verifier_capability=verifier,
        transport_receipt=_receipt(event),
    )
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TRIGGER core_outbox_delivery_receipts_no_update")
        connection.execute(
            "UPDATE core_outbox_delivery_receipts SET tenant_id='tenant-other'"
        )
        connection.executescript(
            """
            CREATE TRIGGER core_outbox_delivery_receipts_no_update
            BEFORE UPDATE ON core_outbox_delivery_receipts
            BEGIN
                SELECT RAISE(ABORT, 'core outbox delivery receipt immutable');
            END;
            """
        )

    with pytest.raises(IntegrityError, match="CORE_OUTBOX_DELIVERY_SCHEMA_INVALID"):
        IntakeStore(database)


def test_store_closes_connection_without_masking_migration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[sqlite3.Connection] = []
    original_connect = store_module.sqlite3.connect

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)
        captured.append(connection)
        return connection

    class ExactMigrationFailure(RuntimeError):
        pass

    failure = ExactMigrationFailure("exact migration failure")
    monkeypatch.setattr(store_module.sqlite3, "connect", recording_connect)
    monkeypatch.setattr(
        store_module,
        "migrate_connection",
        lambda _connection, *, target_version: (_ for _ in ()).throw(failure),
    )
    with pytest.raises(ExactMigrationFailure) as rejected:
        IntakeStore(tmp_path / "migration-failure.sqlite3")
    assert rejected.value is failure
    assert len(captured) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        captured[0].execute("SELECT 1")


def test_store_closes_connection_without_masking_schema_validator_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[sqlite3.Connection] = []
    original_connect = store_module.sqlite3.connect

    def recording_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)
        captured.append(connection)
        return connection

    class ExactValidatorFailure(RuntimeError):
        pass

    failure = ExactValidatorFailure("exact validator failure")
    monkeypatch.setattr(store_module.sqlite3, "connect", recording_connect)
    monkeypatch.setattr(
        IntakeStore,
        "_validate_core_outbox_delivery_schema",
        lambda _self: (_ for _ in ()).throw(failure),
    )
    with pytest.raises(ExactValidatorFailure) as rejected:
        IntakeStore(tmp_path / "validator-failure.sqlite3")
    assert rejected.value is failure
    assert len(captured) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        captured[0].execute("SELECT 1")
