from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake.canonical import canonical_digest
from elmos_multimodal_intake.content import content_contract_digest
from elmos_multimodal_intake._migrations import migrate_connection
from elmos_multimodal_intake.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from elmos_multimodal_intake.human_review import HumanReviewCorrectionBridge
from elmos_multimodal_intake.human_review_workflow import (
    HumanReviewWorkflow,
    human_review_client_value_digest,
)
from elmos_multimodal_intake.models import AssetStatus, TenantContext
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.store import IntakeStore


def _ready_asset(store: IntakeStore, context: TenantContext):
    store.bootstrap_project(context)
    session = store.create_session(
        context,
        idempotency_key="review-session-0001",
        requested_role="PRIMARY",
    )
    content = b"trusted immutable source\n"
    digest = hashlib.sha256(content).hexdigest()
    asset, upload = store.create_upload(
        context,
        session_id=session.session_id,
        display_name="review/source.txt",
        declared_media_type="text/plain",
        expected_size=len(content),
        expected_sha256=digest,
        part_size=len(content),
        idempotency_key="review-upload-0001",
        request_digest=canonical_digest({"content_digest": digest}),
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    store.record_part(
        context,
        upload.upload_id,
        part_number=0,
        idempotency_key="review-part-0001",
        byte_offset=0,
        byte_size=len(content),
        sha256=digest,
        cas_digest=digest,
    )
    uploaded = store.complete_upload(
        context,
        upload.upload_id,
        commit_idempotency_key="review-commit-0001",
        digest=digest,
        byte_size=len(content),
    )
    return store.set_asset_result(
        context,
        asset.asset_id,
        status=AssetStatus.READY,
        expected_version=uploaded.version,
    )


@pytest.fixture
def review_store(tmp_path: Path):
    store = IntakeStore(tmp_path / "intake.sqlite3")
    context = TenantContext("tenant-a", "project-a", "reviewer-a")
    asset = _ready_asset(store, context)
    try:
        yield store, context, asset
    finally:
        store.close()


def _runtime_context(
    context: TenantContext,
    *,
    key: str,
    policy: bool = True,
) -> RuntimeContext:
    review_policy = {
        "human_review": {
            "version": "review-policy-v1",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "allowed_actions": ["correct"],
            "allowed_actor_ids": [context.actor_id],
        }
    } if policy else {}
    return RuntimeContext(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        actor_id=context.actor_id,
        request_id=f"request-{key}",
        trace_id=f"trace-{key}",
        idempotency_key=key,
        policy=review_policy,
        capabilities={
            # A host snapshot may be stale, but it is never authoritative for
            # mutable correction state; the bridge must overwrite this value.
            "human_review_state": {
                "version": "stale-host-state",
                "tenant_id": "wrong-tenant",
                "project_id": "wrong-project",
                "content_id": "wrong-content",
                "current_version": 999,
                "current_digest": "sha256:" + "0" * 64,
            }
        },
    )


def _payload(asset_id: str, version: int, key: str, value: Any):
    return {
        "operation": "correct",
        "content_id": asset_id,
        "expected_version": version,
        "value": value,
        "reason": "verified human review",
        "idempotency_key": key,
        "trace_id": f"trace-{key}",
    }


def test_bridge_persists_immutable_versions_and_replays_exact_request(review_store) -> None:
    store, context, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)
    first_key = "review-correction-0001"
    first = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(context, key=first_key),
        _payload(
            asset.asset_id,
            asset.version,
            first_key,
            {
                "confidence": 1e-7,
                "label": "Cafe\u0301 人工修正 🧭",
                "values": [0.125, 1234.5],
            },
        ),
    )

    assert first["state"] == "SUCCEEDED"
    assert first["code"] == "CORRECTION_VERSION_CREATED"
    assert first["outputs"]["asset_status"] == "NEEDS_REVIEW"
    assert first["outputs"]["asset_version"] == asset.version + 1
    assert first["outputs"]["approval_state"] == "NOT_RUN"
    assert first["outputs"]["rebuild_state"] == "NOT_RUN"
    assert {item["state"] for item in first["outputs"]["rebuild_tasks"]} == {"NOT_RUN"}
    assert first["outputs"]["original_version_preserved"] is True
    correction_document = dict(first["outputs"]["correction"])
    correction_digest = correction_document.pop("digest")
    assert correction_digest == content_contract_digest(correction_document)
    persisted = store.get_asset(context, asset.asset_id)
    assert persisted.status is AssetStatus.NEEDS_REVIEW
    assert persisted.version == asset.version + 1

    replay = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(context, key=first_key),
        _payload(
            asset.asset_id,
            asset.version,
            first_key,
            {
                "confidence": 1e-7,
                "label": "Cafe\u0301 人工修正 🧭",
                "values": [0.125, 1234.5],
            },
        ),
    )
    assert replay == first

    second_key = "review-correction-0002"
    second = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(context, key=second_key),
        _payload(asset.asset_id, persisted.version, second_key, "reviewed value two"),
    )
    assert second["outputs"]["correction"]["version"] == asset.version + 2
    assert second["outputs"]["correction"]["supersedes_digest"] == first["outputs"]["correction"]["digest"]
    assert store.get_asset(context, asset.asset_id).version == asset.version + 2
    store._validate_human_review_workflow_schema()


def test_legacy_correction_source_publication_is_atomic(
    review_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, context, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)
    original_event = store._event

    def fail_after_source_rows(
        connection,
        event_context,
        aggregate_type,
        aggregate_id,
        event_type,
        idempotency_key,
        payload,
    ):
        if event_type == "human_review.source.registered":
            raise IntegrityError("TEST_CORRECTION_SOURCE_PUBLICATION_FAILED")
        return original_event(
            connection,
            event_context,
            aggregate_type,
            aggregate_id,
            event_type,
            idempotency_key,
            payload,
        )

    monkeypatch.setattr(store, "_event", fail_after_source_rows)
    key = "review-correction-atomic-source-0001"
    with pytest.raises(IntegrityError) as rejected:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(context, key=key),
            _payload(asset.asset_id, asset.version, key, "must roll back"),
        )
    assert rejected.value.code == "TEST_CORRECTION_SOURCE_PUBLICATION_FAILED"
    assert store.get_asset(context, asset.asset_id).version == asset.version
    for table in (
        "human_review_corrections",
        "human_review_source_producer_capabilities",
        "human_review_source_snapshots",
        "human_review_target_heads",
    ):
        count = store._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0


def test_legacy_correct_publishes_authoritative_source_for_exact_enqueue(
    review_store,
) -> None:
    store, context, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)
    workflow = HumanReviewWorkflow(store)
    correction_key = "review-correction-authoritative-source-0001"
    corrected_value = "durable human correction, never a browser source echo"

    corrected = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(context, key=correction_key),
        _payload(
            asset.asset_id,
            asset.version,
            correction_key,
            corrected_value,
        ),
    )
    corrected_version = corrected["outputs"]["asset_version"]
    assert corrected_version == asset.version + 1

    listed = workflow.list_source_heads(
        context,
        asset_id=asset.asset_id,
        expected_asset_version=corrected_version,
        kinds=["TEXT"],
        limit=200,
        cursor=None,
    )
    assert listed["total"] == 1
    assert listed["next_cursor"] is None
    source_summary = listed["sources"][0]
    assert source_summary["content_version"] == corrected_version
    assert source_summary["target_kind"] == "TEXT"
    assert source_summary["target"]["path"].startswith(
        "human_review_corrections/correction-"
    )
    assert source_summary["confidence"] == 1.0
    assert source_summary["head_version"] == 1
    assert source_summary["head_direction"] == "SNAPSHOT"
    assert source_summary["head_correction_version"] == 0

    source = workflow.get_source_head(
        context,
        asset_id=asset.asset_id,
        expected_asset_version=corrected_version,
        target_kind=source_summary["target_kind"],
        target_digest=source_summary["target_digest"],
        expected_head_version=source_summary["head_version"],
    )["source"]
    assert source["original_value"] == corrected_value
    assert source["original_value_client_digest"] == (
        f"sha256:{human_review_client_value_digest(corrected_value)}"
    )
    source_ref = source["source_ref"]
    assert source_ref == source_summary["source_ref"]

    snapshot = store._connection.execute(
        """SELECT * FROM human_review_source_snapshots
            WHERE tenant_id=? AND project_id=? AND snapshot_id=?""",
        (context.tenant_id, context.project_id, source_ref["snapshot_id"]),
    ).fetchone()
    assert snapshot is not None
    provenance = json.loads(snapshot["provenance_json"])
    assert provenance["source_kind"] == "TRUSTED_DERIVATION"
    assert snapshot["producer_actor_id"] == (
        "workload:human-review-correction-store"
    )
    correction_row = store._connection.execute(
        """SELECT * FROM human_review_corrections
            WHERE tenant_id=? AND project_id=? AND asset_id=? AND version=?""",
        (context.tenant_id, context.project_id, asset.asset_id, corrected_version),
    ).fetchone()
    assert correction_row is not None
    assert provenance["source_id"] == correction_row["correction_id"]
    source_fact = store._human_review_correction_source_fact(
        correction_id=correction_row["correction_id"],
        correction_document=corrected["outputs"]["correction"],
        correction_digest=correction_row["correction_digest"],
        source_version=correction_row["source_version"],
        asset_version=correction_row["version"],
    )
    assert provenance["source_digest"] == f"sha256:{canonical_digest(source_fact)}"

    queued = workflow.enqueue_review_task(
        context,
        asset_id=asset.asset_id,
        expected_asset_version=corrected_version,
        target_kind=source["target_kind"],
        target_digest=source["target_digest"],
        expected_head_version=source["head_version"],
        expected_snapshot_id=source_ref["snapshot_id"],
        expected_snapshot_digest=source_ref["snapshot_digest"],
        expected_head_value_digest=source_ref["head_value_digest"],
        original_value_digest=source["original_value_client_digest"],
        reason="review the durable legacy correction",
        idempotency_key="review-enqueue-after-legacy-correct-0001",
        request_digest=canonical_digest({"case": "correct-to-enqueue"}),
    )
    assert queued["task"]["original_value"] == corrected_value
    assert queued["task"]["source_ref"] == source_ref

    with pytest.raises(ConflictError) as forged:
        workflow.enqueue_review_task(
            context,
            asset_id=asset.asset_id,
            expected_asset_version=corrected_version,
            target_kind=source["target_kind"],
            target_digest=source["target_digest"],
            expected_head_version=source["head_version"],
            expected_snapshot_id=source_ref["snapshot_id"],
            expected_snapshot_digest=source_ref["snapshot_digest"],
            expected_head_value_digest=source_ref["head_value_digest"],
            original_value_digest=(
                f"sha256:{human_review_client_value_digest('browser-forged-source')}"
            ),
            reason="must fail before task insertion",
            idempotency_key="review-enqueue-forged-source-0001",
            request_digest=canonical_digest({"case": "forged-enqueue-echo"}),
        )
    assert forged.value.code == "HUMAN_REVIEW_SOURCE_DRIFT"
    store._validate_human_review_workflow_schema()


def test_bridge_rejects_idempotency_drift_stale_versions_and_browser_state_spoofing(
    review_store,
) -> None:
    store, context, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)
    key = "review-correction-0010"
    bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(context, key=key),
        _payload(asset.asset_id, asset.version, key, "first reviewed value"),
    )

    with pytest.raises(ConflictError) as drift:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(context, key=key),
            _payload(asset.asset_id, asset.version, key, "changed reviewed value"),
        )
    assert drift.value.code == "HUMAN_REVIEW_IDEMPOTENCY_CONFLICT"

    stale_key = "review-correction-0011"
    with pytest.raises(ConflictError) as stale:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(context, key=stale_key),
            _payload(asset.asset_id, asset.version, stale_key, "stale version"),
        )
    assert stale.value.code == "OPTIMISTIC_LOCK_CONFLICT"

    spoofed = _payload(
        asset.asset_id,
        asset.version + 1,
        "review-correction-0012",
        "browser intent only",
    )
    spoofed["current"] = {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "value": "browser-forged-current",
        "digest": "sha256:" + "f" * 64,
    }
    with pytest.raises(ValidationError) as spoof:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(context, key="review-correction-0012"),
            spoofed,
        )
    assert spoof.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"


def test_bridge_optionally_binds_exact_current_digest_before_append(review_store) -> None:
    store, context, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)
    current, _state, _replay = store.prepare_human_review_correction(
        context,
        asset_id=asset.asset_id,
        idempotency_key="review-digest-probe-0001",
        request_digest=canonical_digest({"probe": "current-digest"}),
    )
    assert current is not None

    stale_key = "review-correction-digest-stale-0001"
    stale = _payload(asset.asset_id, asset.version, stale_key, "must not persist")
    stale["expected_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ConflictError) as rejected:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(context, key=stale_key),
            stale,
        )
    assert rejected.value.code == "HUMAN_REVIEW_CURRENT_DRIFT"
    assert store.get_asset(context, asset.asset_id).version == asset.version
    assert store._connection.execute(
        "SELECT count(*) FROM human_review_corrections"
    ).fetchone()[0] == 0

    key = "review-correction-digest-exact-0001"
    exact = _payload(asset.asset_id, asset.version, key, "digest-bound value")
    exact["expected_digest"] = current["digest"]
    persisted = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(context, key=key),
        exact,
    )
    assert persisted["state"] == "SUCCEEDED"
    row = store._connection.execute(
        "SELECT source_json,approval_state,rebuild_state FROM human_review_corrections"
    ).fetchone()
    assert row is not None
    assert json.loads(row["source_json"])["digest"] == current["digest"]
    assert (row["approval_state"], row["rebuild_state"]) == ("NOT_RUN", "NOT_RUN")


def test_bridge_enforces_review_acl_host_policy_and_exact_scope(review_store) -> None:
    store, owner, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)

    missing_policy_key = "review-correction-0020"
    blocked = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=missing_policy_key, policy=False),
        _payload(asset.asset_id, asset.version, missing_policy_key, "not authorized"),
    )
    assert blocked["state"] == "BLOCKED"
    assert blocked["code"] == "HUMAN_REVIEW_POLICY_UNAVAILABLE"
    assert store.get_asset(owner, asset.asset_id).version == asset.version

    store.grant_permissions(owner, "reader-a", [store.READ])
    reader = TenantContext(owner.tenant_id, owner.project_id, "reader-a")
    reader_key = "review-correction-0021"
    with pytest.raises(AuthorizationError) as unauthorized:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(reader, key=reader_key),
            _payload(asset.asset_id, asset.version, reader_key, "reader cannot review"),
        )
    assert unauthorized.value.code == "INTAKE_PROJECT_ACCESS_DENIED"

    other = TenantContext("tenant-b", "project-b", "reviewer-b")
    store.bootstrap_project(other)
    other_key = "review-correction-0022"
    with pytest.raises(NotFoundError) as wrong_scope:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(other, key=other_key),
            _payload(asset.asset_id, asset.version, other_key, "cross scope"),
        )
    assert wrong_scope.value.code == "INPUT_ASSET_NOT_FOUND"


def test_bridge_rejects_non_json_non_finite_unsafe_and_unbounded_values(
    review_store,
) -> None:
    store, context, asset = review_store
    bridge = HumanReviewCorrectionBridge(store)
    too_deep: Any = "leaf"
    for _ in range(40):
        too_deep = {"child": too_deep}
    cases = (
        (float("nan"), "HUMAN_REVIEW_CORRECTION_JSON_INVALID"),
        (b"not-json", "HUMAN_REVIEW_CORRECTION_JSON_INVALID"),
        ((1 << 53) + 1, "HUMAN_REVIEW_CORRECTION_JSON_INVALID"),
        (too_deep, "HUMAN_REVIEW_CORRECTION_JSON_LIMIT_EXCEEDED"),
        ("x" * (2 * 1024 * 1024), "HUMAN_REVIEW_CORRECTION_JSON_LIMIT_EXCEEDED"),
    )
    for ordinal, (value, expected_code) in enumerate(cases):
        key = f"review-correction-bounded-{ordinal:02d}"
        with pytest.raises(ValidationError) as rejected:
            bridge.handle(
                HumanReviewCorrectionBridge.SKILL,
                _runtime_context(context, key=key),
                _payload(asset.asset_id, asset.version, key, value),
            )
        assert rejected.value.code == expected_code
    assert store.get_asset(context, asset.asset_id).version == asset.version


def test_store_fails_closed_when_v10_immutable_trigger_drifts(tmp_path: Path) -> None:
    database = tmp_path / "trigger-drift.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER human_review_corrections_no_update")

    with pytest.raises(IntegrityError) as rejected:
        IntakeStore(database)
    assert rejected.value.code == "HUMAN_REVIEW_CORRECTION_IMMUTABILITY_INVALID"


def test_store_fails_closed_when_v11_trigger_is_conditionally_disabled(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workflow-trigger-when-zero.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            DROP TRIGGER human_review_correction_versions_no_delete;
            CREATE TRIGGER human_review_correction_versions_no_delete
            BEFORE DELETE ON human_review_correction_versions
            WHEN 0
            BEGIN
                SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
            END;
            """
        )

    with pytest.raises(IntegrityError) as rejected:
        IntakeStore(database)
    assert rejected.value.code == "HUMAN_REVIEW_WORKFLOW_IMMUTABILITY_INVALID"


def test_store_fails_closed_when_v14_snapshot_trigger_is_conditionally_disabled(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source-snapshot-trigger-when-zero.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            DROP TRIGGER human_review_source_snapshots_no_delete;
            CREATE TRIGGER human_review_source_snapshots_no_delete
            BEFORE DELETE ON human_review_source_snapshots
            WHEN 0
            BEGIN
                SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_SNAPSHOT_IMMUTABLE');
            END;
            """
        )

    with pytest.raises(IntegrityError) as rejected:
        IntakeStore(database)
    assert rejected.value.code == "HUMAN_REVIEW_WORKFLOW_IMMUTABILITY_INVALID"


def _rebuild_empty_human_review_table(
    database: Path,
    *,
    table: str,
    remove_sql: str,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        tampered_sql = table_sql.replace(remove_sql, "", 1)
        assert tampered_sql != table_sql
        owned_objects = connection.execute(
            """SELECT type,name,sql FROM sqlite_master
                 WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL
                 ORDER BY type,name""",
            (table,),
        ).fetchall()
        for object_type, name, _sql in owned_objects:
            connection.execute(f'DROP {object_type.upper()} "{name}"')
        connection.execute(f'ALTER TABLE "{table}" RENAME TO "{table}_old"')
        connection.execute(tampered_sql)
        for _object_type, _name, object_sql in owned_objects:
            connection.execute(object_sql)
        connection.execute(f'DROP TABLE "{table}_old"')


@pytest.mark.parametrize(
    ("table", "remove_sql"),
    (
        (
            "human_review_operation_receipts",
            " CHECK (length(request_digest) = 64)",
        ),
        (
            "human_review_audit_log",
            "    UNIQUE (tenant_id, project_id, audit_id),\n",
        ),
        (
            "human_review_source_snapshots",
            " CHECK (length(snapshot_digest) = 64)",
        ),
        (
            "human_review_source_producer_capabilities",
            "        OR (revoked_at IS NOT NULL AND version = 2)\n",
        ),
        (
            "human_review_target_heads",
            "        OR (direction = 'REVERT' AND source_decision_id IS NOT NULL)\n",
        ),
    ),
)
def test_store_fails_closed_when_human_review_check_or_unique_contract_is_removed(
    tmp_path: Path,
    table: str,
    remove_sql: str,
) -> None:
    database = tmp_path / f"workflow-{table}-contract-drift.sqlite3"
    store = IntakeStore(database)
    store.close()
    _rebuild_empty_human_review_table(
        database,
        table=table,
        remove_sql=remove_sql,
    )

    with pytest.raises(IntegrityError) as rejected:
        IntakeStore(database)
    assert rejected.value.code == "HUMAN_REVIEW_WORKFLOW_SCHEMA_INVALID"


def test_v14_authoritative_source_migration_is_exactly_mirrored() -> None:
    engine_root = Path(__file__).resolve().parents[1]
    source = engine_root / "migrations" / "014_human_review_authoritative_sources.sql"
    packaged = (
        engine_root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "014_human_review_authoritative_sources.sql"
    )
    assert source.read_bytes() == packaged.read_bytes()
    sql = source.read_text(encoding="utf-8")
    assert "CREATE TABLE human_review_source_producer_capabilities" in sql
    assert "CREATE TABLE human_review_source_snapshots" in sql
    assert "CREATE TABLE human_review_target_heads" in sql
    assert "PRAGMA user_version = 14" in sql


def test_v13_database_upgrades_to_v14_authoritative_source_schema(
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(tmp_path / "upgrade-v13-v14.sqlite3", isolation_level=None)
    try:
        assert migrate_connection(connection, target_version=13) == 13
        assert migrate_connection(connection, target_version=14) == 14
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        assert {
            "human_review_source_producer_capabilities",
            "human_review_source_snapshots",
            "human_review_target_heads",
        } <= tables
    finally:
        connection.close()


def test_v16_target_head_reservation_migration_is_exactly_mirrored() -> None:
    engine_root = Path(__file__).resolve().parents[1]
    source = (
        engine_root
        / "migrations"
        / "016_human_review_target_head_reservations.sql"
    )
    packaged = (
        engine_root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "016_human_review_target_head_reservations.sql"
    )
    assert source.read_bytes() == packaged.read_bytes()
    sql = source.read_text(encoding="utf-8")
    assert "CREATE TABLE human_review_target_head_reservations" in sql
    assert "human_review_decisions_require_target_head_reservation" in sql
    assert "human_review_propagations_require_target_head_reservation" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "PRAGMA user_version = 16" in sql


def test_v15_database_upgrades_to_v16_target_head_reservation_schema(
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(tmp_path / "upgrade-v15-v16.sqlite3", isolation_level=None)
    try:
        assert migrate_connection(connection, target_version=15) == 15
        assert migrate_connection(connection, target_version=16) == 16
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        assert "human_review_target_head_reservations" in tables
    finally:
        connection.close()


def test_intake_store_rejects_a_future_schema_version(tmp_path: Path) -> None:
    database = tmp_path / "future-intake-schema.sqlite3"
    store = IntakeStore(database)
    store.close()
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 25")

    with pytest.raises(IntegrityError) as rejected:
        IntakeStore(database)
    assert rejected.value.code == "INTAKE_SCHEMA_VERSION_UNSUPPORTED"
