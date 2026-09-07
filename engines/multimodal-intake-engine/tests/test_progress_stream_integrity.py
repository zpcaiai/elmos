from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import elmos_multimodal_intake.store as store_module
from elmos_multimodal_intake._migrations import migrate_connection
from elmos_multimodal_intake.canonical import canonical_digest, canonical_json, sha256_bytes
from elmos_multimodal_intake.errors import ConflictError, IntegrityError
from elmos_multimodal_intake.models import JobStatus, ResultStatus, TenantContext
from elmos_multimodal_intake.progress_stream import ProgressStreamReader, job_progress_sequence
from elmos_multimodal_intake.store import IntakeStore


def _runtime_store(tmp_path: Path, name: str = "intake.sqlite3") -> tuple[IntakeStore, TenantContext, str]:
    store = IntakeStore(tmp_path / name)
    context = TenantContext("tenant-progress", "project-progress", "actor-progress")
    store.bootstrap_project(context)
    session = store.create_session(context, idempotency_key=f"session-{name}")
    return store, context, session.session_id


def _create_job(
    store: IntakeStore,
    context: TenantContext,
    session_id: str,
    suffix: str,
):
    return store.create_job(
        context,
        session_id,
        idempotency_key=f"job-{suffix}",
        request_digest=(suffix[0] * 64),
    )


def _transition(
    store: IntakeStore,
    context: TenantContext,
    task_id: str,
    key: str,
    target: str,
    *,
    current: str | None = None,
) -> dict[str, Any]:
    event, replayed = store.apply_durable_transition(
        context,
        task_id=task_id,
        idempotency_key=key,
        target_state=target,
        current_state=current,
        payload={"opaque": key},
    )
    assert replayed is False
    return event


def test_formal_v7_migration_backfills_existing_jobs_and_mirrors_source(tmp_path: Path) -> None:
    database = tmp_path / "legacy-v1.sqlite3"
    connection = sqlite3.connect(database, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    assert migrate_connection(connection, target_version=1) == 1
    now = "2026-08-22T12:00:00+00:00"
    connection.execute(
        "INSERT INTO project_acl VALUES (?,?,?,?,?,?)",
        (
            "tenant-progress",
            "project-progress",
            "actor-progress",
            "intake:read",
            "actor-progress",
            now,
        ),
    )
    connection.execute(
        """INSERT INTO input_sessions (
            session_id,tenant_id,project_id,created_by,requested_role,status,
            idempotency_key,request_digest,trace_id,version,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "legacy-session",
            "tenant-progress",
            "project-progress",
            "actor-progress",
            "PRIMARY",
            "DRAFT",
            "legacy-session-key",
            "a" * 64,
            "legacy-trace",
            1,
            now,
            now,
        ),
    )
    connection.execute(
        """INSERT INTO processing_jobs (
            job_id,tenant_id,project_id,session_id,idempotency_key,request_digest,
            status,stage,attempt,max_attempts,result_status,failure_code,
            lease_owner,lease_expires_at,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,?)""",
        (
            "legacy-job",
            "tenant-progress",
            "project-progress",
            "legacy-session",
            "legacy-job-key",
            "b" * 64,
            "QUEUED",
            "queued",
            0,
            3,
            "NOT_RUN",
            None,
            now,
            now,
        ),
    )
    connection.close()

    store = IntakeStore(database)
    try:
        context = TenantContext("tenant-progress", "project-progress", "actor-progress")
        job = store.get_job(context, "legacy-job")
        assert store._connection.execute("PRAGMA user_version").fetchone()[0] == 24
        assert getattr(job, "version") == 1
        assert job_progress_sequence(job) == 1
        columns = {
            row["name"]: row
            for row in store._connection.execute("PRAGMA table_info(processing_jobs)")
        }
        assert columns["version"]["type"] == "INTEGER"
        assert columns["version"]["notnull"] == 1
        assert columns["version"]["dflt_value"] == "1"
    finally:
        store.close()

    engine_root = Path(__file__).resolve().parents[1]
    assert (
        engine_root / "migrations" / "007_progress_job_version.sql"
    ).read_bytes() == (
        engine_root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "007_progress_job_version.sql"
    ).read_bytes()


def test_job_versions_are_monotone_for_same_second_and_clock_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, context, session_id = _runtime_store(tmp_path)
    try:
        queued = _create_job(store, context, session_id, "aaaa")
        claimed = store.claim_job(
            context,
            queued.job_id,
            owner_token="progress-worker",
            lease_seconds=300,
        )
        monkeypatch.setattr(
            store_module,
            "utc_now",
            lambda: "2000-01-01T00:00:00+00:00",
        )
        renewed = store.renew_job_lease(
            context,
            queued.job_id,
            owner_token="progress-worker",
            lease_seconds=300,
        )
        completed = store.update_job(
            context,
            queued.job_id,
            status=JobStatus.COMPLETED,
            stage="completed",
            result_status=ResultStatus.PASSED,
            lease_owner="progress-worker",
        )
        assert [job_progress_sequence(job) for job in (queued, claimed, renewed, completed)] == [
            1,
            2,
            3,
            4,
        ]
        assert renewed.updated_at < claimed.updated_at
        assert completed.updated_at == renewed.updated_at
    finally:
        store.close()


def test_job_state_graph_rejects_invalid_edges_and_terminal_regression(tmp_path: Path) -> None:
    store, context, session_id = _runtime_store(tmp_path)
    try:
        queued = _create_job(store, context, session_id, "bbbb")
        with pytest.raises(ConflictError, match="PROCESSING_JOB_STATE_TRANSITION_INVALID"):
            store.update_job(
                context,
                queued.job_id,
                status=JobStatus.COMPLETED,
                stage="completed",
                result_status=ResultStatus.PASSED,
            )
        running = store.claim_job(
            context,
            queued.job_id,
            owner_token="terminal-worker",
        )
        terminal = store.update_job(
            context,
            queued.job_id,
            status=JobStatus.COMPLETED,
            stage="completed",
            result_status=ResultStatus.PASSED,
            lease_owner="terminal-worker",
        )
        with pytest.raises(ConflictError, match="PROCESSING_JOB_TERMINAL"):
            store.update_job(
                context,
                terminal.job_id,
                status=JobStatus.RUNNING,
                stage="resurrected",
                result_status=ResultStatus.NOT_RUN,
                lease_owner="terminal-worker",
            )
        replay = store.update_job(
            context,
            terminal.job_id,
            status=JobStatus.COMPLETED,
            stage="completed",
            result_status=ResultStatus.PASSED,
        )
        claimed_again = store.claim_job(
            context,
            terminal.job_id,
            owner_token="different-worker",
        )
        assert job_progress_sequence(replay) == job_progress_sequence(terminal)
        assert job_progress_sequence(claimed_again) == job_progress_sequence(terminal)
        assert running.status is JobStatus.RUNNING
    finally:
        store.close()


def test_job_cursor_binds_exact_job_version_and_digest(tmp_path: Path) -> None:
    store, context, session_id = _runtime_store(tmp_path)
    try:
        first = _create_job(store, context, session_id, "cccc")
        second = _create_job(store, context, session_id, "dddd")
        reader = ProgressStreamReader(store)
        first_batch = reader.job_events(context, first.job_id, cursor=None)
        first_cursor = str(first_batch.documents[0]["cursor"])
        with pytest.raises(ConflictError, match="PROGRESS_CURSOR_DIVERGED"):
            reader.job_events(context, second.job_id, cursor=first_cursor)

        store.claim_job(context, first.job_id, owner_token="cursor-worker")
        with pytest.raises(ConflictError, match="PROGRESS_CURSOR_DIVERGED"):
            reader.job_events(context, first.job_id, cursor=first_cursor)
        current = reader.job_events(context, first.job_id, cursor=None).documents[0]
        assert current["sequence_number"] == 2
        current_cursor = str(current["cursor"])
        heartbeat = reader.job_events(context, first.job_id, cursor=current_cursor)
        assert heartbeat.documents == ()
        assert heartbeat.heartbeat is not None
        assert heartbeat.heartbeat["cursor"] == current_cursor
    finally:
        store.close()


def test_task_cursor_binds_resource_and_full_row_event_fields(tmp_path: Path) -> None:
    store, context, _session_id = _runtime_store(tmp_path)
    try:
        _transition(store, context, "task-a", "task-a-running", "RUNNING")
        _transition(store, context, "task-b", "task-b-running", "RUNNING")
        reader = ProgressStreamReader(store)
        cursor = str(reader.task_events(context, "task-a", cursor=None).documents[0]["cursor"])
        with pytest.raises(ConflictError, match="PROGRESS_CURSOR_DIVERGED"):
            reader.task_events(context, "task-b", cursor=cursor)

        row = store._connection.execute(
            """SELECT transition_id FROM durable_transitions
            WHERE tenant_id=? AND project_id=? AND task_id=?""",
            (context.tenant_id, context.project_id, "task-a"),
        ).fetchone()
        store._connection.execute(
            "UPDATE durable_transitions SET actor_id=? WHERE transition_id=?",
            ("actor-tampered", row["transition_id"]),
        )
        with pytest.raises(IntegrityError, match="DURABLE_TRANSITION_ROW_EVENT_MISMATCH"):
            reader.task_events(context, "task-a", cursor=None)
    finally:
        store.close()


def test_task_reader_rejects_a_row_valid_but_disconnected_state_chain(tmp_path: Path) -> None:
    store, context, _session_id = _runtime_store(tmp_path)
    try:
        _transition(store, context, "task-chain", "chain-running", "RUNNING")
        second = _transition(
            store,
            context,
            "task-chain",
            "chain-paused",
            "PAUSED",
            current="RUNNING",
        )
        row = store._connection.execute(
            "SELECT * FROM durable_transitions WHERE transition_id=?",
            (second["event_id"],),
        ).fetchone()
        event = json.loads(row["event_json"])
        event["from_state"] = "PENDING"
        event["target_state"] = "CANCELLED"
        event["event_id"] = (
            "transition-"
            + canonical_digest(
                {key: value for key, value in event.items() if key != "event_id"}
            )[:32]
        )
        encoded = canonical_json(event)
        store._connection.execute(
            """UPDATE durable_transitions
               SET transition_id=?,from_state=?,target_state=?,event_json=?,event_sha256=?
             WHERE transition_id=?""",
            (
                event["event_id"],
                event["from_state"],
                event["target_state"],
                encoded,
                sha256_bytes(encoded.encode("utf-8")),
                second["event_id"],
            ),
        )
        previous_outbox = store._connection.execute(
            "SELECT * FROM outbox_events WHERE event_id=?",
            (row["outbox_event_id"],),
        ).fetchone()
        outbox_payload_digest = sha256_bytes(encoded.encode("utf-8"))
        replacement_outbox_id = store._core_outbox_event_id(  # noqa: SLF001
            tenant_id=previous_outbox["tenant_id"],
            project_id=previous_outbox["project_id"],
            aggregate_type=previous_outbox["aggregate_type"],
            aggregate_id=previous_outbox["aggregate_id"],
            event_type=previous_outbox["event_type"],
            idempotency_key=previous_outbox["idempotency_key"],
            payload_digest=outbox_payload_digest,
            occurred_at=previous_outbox["occurred_at"],
        )
        store._connection.execute("BEGIN IMMEDIATE")
        store._connection.execute("PRAGMA defer_foreign_keys = ON")
        store._connection.execute(
            """UPDATE outbox_events
                  SET event_id=?,payload_json=?,payload_digest=?
                WHERE event_id=?""",
            (
                replacement_outbox_id,
                encoded,
                outbox_payload_digest,
                row["outbox_event_id"],
            ),
        )
        store._connection.execute(
            "UPDATE durable_transitions SET outbox_event_id=? WHERE transition_id=?",
            (replacement_outbox_id, event["event_id"]),
        )
        store._connection.execute("COMMIT")
        with pytest.raises(IntegrityError, match="DURABLE_TRANSITION_CHAIN_CORRUPT"):
            ProgressStreamReader(store).task_events(context, "task-chain", cursor=None)
    finally:
        store.close()


def test_task_page_latest_and_cursor_are_from_one_sqlite_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, context, _session_id = _runtime_store(tmp_path)
    writer = IntakeStore(store.database)
    try:
        _transition(store, context, "task-snapshot", "snapshot-running", "RUNNING")
        original = store._durable_progress_event
        wrote = False

        def interleaved(row: sqlite3.Row) -> dict[str, Any]:
            nonlocal wrote
            if not wrote:
                wrote = True
                _transition(
                    writer,
                    context,
                    "task-snapshot",
                    "snapshot-paused",
                    "PAUSED",
                    current="RUNNING",
                )
            return original(row)

        monkeypatch.setattr(store, "_durable_progress_event", interleaved)
        reader = ProgressStreamReader(store)
        first = reader.task_events(context, "task-snapshot", cursor=None)
        assert wrote is True
        assert [document["sequence_number"] for document in first.documents] == [1]
        cursor = str(first.documents[-1]["cursor"])

        second = reader.task_events(context, "task-snapshot", cursor=cursor)
        assert [document["sequence_number"] for document in second.documents] == [2]
        assert second.documents[0]["previous_state"] == "RUNNING"
        assert second.documents[0]["state"] == "PAUSED"
    finally:
        writer.close()
        store.close()
