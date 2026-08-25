"""Tenant-scoped SQLite persistence for project-intelligence runs.

All mutations use ``BEGIN IMMEDIATE`` transactions.  Idempotency keys are
bound to canonical request digests, artifacts/evidence/checkpoints are
append-only, and database triggers make run events immutable even to callers
that obtain the underlying database file.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading

from .canonical import (
    JsonValue,
    canonical_digest,
    canonical_json,
    canonical_value,
    validate_digest,
)
from .contracts import (
    ArtifactInput,
    ArtifactRecord,
    CheckpointRecord,
    CreateRunRequest,
    EventRecord,
    EvidenceInput,
    EvidenceRecord,
    EvidenceState,
    IdempotencyDecision,
    IdempotencyDisposition,
    ProjectRecord,
    RunRecord,
    RunStatus,
    require_identifier,
    require_operation,
)


class StoreError(RuntimeError):
    """Base class for expected persistence failures."""


class StoreClosed(StoreError):
    pass


class RecordNotFound(StoreError):
    pass


class RecordConflict(StoreError):
    pass


class IdempotencyConflict(RecordConflict):
    """The same scoped idempotency key was used for a different request."""


class StateTransitionError(RecordConflict):
    pass


class CheckpointConflict(RecordConflict):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    schema_name TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0)
) STRICT;

CREATE TABLE IF NOT EXISTS projects (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    metadata_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id)
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS runs (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    response_json TEXT,
    response_digest TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects (tenant_id, project_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK ((response_json IS NULL) = (response_digest IS NULL))
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS idempotency_keys (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES runs (tenant_id, project_id, run_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS artifacts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    media_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    metadata_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id, artifact_id),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES runs (tenant_id, project_id, run_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS evidence (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('NOT_RUN', 'COLLECTED', 'VERIFIED', 'REJECTED', 'INCONCLUSIVE')
    ),
    details_json TEXT NOT NULL,
    details_digest TEXT NOT NULL,
    artifact_id TEXT,
    verifier TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id, evidence_id),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES runs (tenant_id, project_id, run_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (tenant_id, project_id, run_id, artifact_id)
        REFERENCES artifacts (tenant_id, project_id, run_id, artifact_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (
        (state IN ('VERIFIED', 'REJECTED') AND verifier IS NOT NULL)
        OR (state NOT IN ('VERIFIED', 'REJECTED'))
    ),
    CHECK (state <> 'NOT_RUN' OR verifier IS NULL)
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS checkpoints (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    state_digest TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id, sequence),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES runs (tenant_id, project_id, run_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS events (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id, sequence),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES runs (tenant_id, project_id, run_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) WITHOUT ROWID, STRICT;

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS artifacts_no_update
BEFORE UPDATE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifacts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS artifacts_no_delete
BEFORE DELETE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifacts are append-only');
END;

CREATE TRIGGER IF NOT EXISTS evidence_no_update
BEFORE UPDATE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence is append-only');
END;

CREATE TRIGGER IF NOT EXISTS evidence_no_delete
BEFORE DELETE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence is append-only');
END;

CREATE TRIGGER IF NOT EXISTS checkpoints_no_update
BEFORE UPDATE ON checkpoints
BEGIN
    SELECT RAISE(ABORT, 'checkpoints are append-only');
END;

CREATE TRIGGER IF NOT EXISTS checkpoints_no_delete
BEFORE DELETE ON checkpoints
BEGIN
    SELECT RAISE(ABORT, 'checkpoints are append-only');
END;
"""


_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _load_json(value: str | None) -> JsonValue | None:
    if value is None:
        return None
    return canonical_value(json.loads(value))


class ProjectIntelligenceStore:
    """Atomic tenant/project-scoped state store.

    The class deliberately has no unscoped lookup methods: every project, run,
    artifact, evidence, checkpoint, event, and idempotency query requires both
    ``tenant_id`` and ``project_id``.
    """

    def __init__(
        self,
        database: str | os.PathLike[str],
        *,
        clock: Callable[[], str] = _utc_now,
        timeout_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("timeout_seconds must be in the range (0, 300]")
        self._clock = clock
        self._lock = threading.RLock()
        self._closed = False

        database_text = os.fspath(database)
        if not isinstance(database_text, str) or not database_text:
            raise ValueError("database must be a non-empty filesystem path")
        is_memory = database_text == ":memory:"
        existed = False
        if not is_memory:
            path = Path(database_text).absolute()
            if not path.parent.is_dir():
                raise ValueError("database parent directory must already exist")
            if path.is_symlink():
                raise ValueError("database path cannot be a symlink")
            existed = path.exists()
            if existed and not path.is_file():
                raise ValueError("database path must be a regular file")
            database_text = str(path)

        self._connection = sqlite3.connect(
            database_text,
            timeout=timeout_seconds,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}"
            )
            if not is_memory:
                self._connection.execute("PRAGMA journal_mode = WAL").fetchone()
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.execute("PRAGMA trusted_schema = OFF")
            self._connection.executescript(_SCHEMA)
            with self._transaction() as cursor:
                row = cursor.execute(
                    "SELECT schema_version FROM schema_metadata WHERE schema_name = ?",
                    ("project-intelligence-core",),
                ).fetchone()
                if row is None:
                    cursor.execute(
                        "INSERT INTO schema_metadata (schema_name, schema_version) "
                        "VALUES (?, ?)",
                        ("project-intelligence-core", 1),
                    )
                elif row["schema_version"] != 1:
                    raise StoreError("unsupported project-intelligence schema version")
        except Exception:
            self._connection.close()
            self._closed = True
            raise

        if not is_memory and not existed:
            os.chmod(database_text, 0o600)

    def __enter__(self) -> "ProjectIntelligenceStore":
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise StoreClosed("store is closed")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            self._ensure_open()
            cursor = self._connection.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                yield cursor
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()
            finally:
                cursor.close()

    def _read_one(self, sql: str, values: tuple[object, ...]) -> sqlite3.Row | None:
        with self._lock:
            self._ensure_open()
            return self._connection.execute(sql, values).fetchone()

    def _read_all(self, sql: str, values: tuple[object, ...]) -> list[sqlite3.Row]:
        with self._lock:
            self._ensure_open()
            return list(self._connection.execute(sql, values).fetchall())

    def register_project(
        self,
        tenant_id: str,
        project_id: str,
        *,
        metadata: JsonValue | None = None,
    ) -> ProjectRecord:
        require_identifier(tenant_id, field_name="tenant_id")
        require_identifier(project_id, field_name="project_id")
        normalized = canonical_value({} if metadata is None else metadata)
        metadata_json = canonical_json(normalized)
        metadata_digest = canonical_digest(normalized)
        created_at = self._clock()
        with self._transaction() as cursor:
            existing = cursor.execute(
                "SELECT * FROM projects WHERE tenant_id = ? AND project_id = ?",
                (tenant_id, project_id),
            ).fetchone()
            if existing is not None:
                if existing["metadata_digest"] != metadata_digest:
                    raise RecordConflict(
                        "project already exists with different canonical metadata"
                    )
                return self._project_from_row(existing)
            cursor.execute(
                "INSERT INTO projects "
                "(tenant_id, project_id, metadata_json, metadata_digest, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    project_id,
                    metadata_json,
                    metadata_digest,
                    created_at,
                ),
            )
        return ProjectRecord(tenant_id, project_id, normalized, created_at)

    def get_project(self, tenant_id: str, project_id: str) -> ProjectRecord:
        require_identifier(tenant_id, field_name="tenant_id")
        require_identifier(project_id, field_name="project_id")
        row = self._read_one(
            "SELECT * FROM projects WHERE tenant_id = ? AND project_id = ?",
            (tenant_id, project_id),
        )
        if row is None:
            raise RecordNotFound("project not found in tenant scope")
        return self._project_from_row(row)

    def create_run(self, request: CreateRunRequest) -> IdempotencyDecision:
        if not isinstance(request, CreateRunRequest):
            raise TypeError("request must be CreateRunRequest")
        request_digest = canonical_digest(request.request)
        timestamp = self._clock()
        with self._transaction() as cursor:
            project = cursor.execute(
                "SELECT 1 FROM projects WHERE tenant_id = ? AND project_id = ?",
                (request.tenant_id, request.project_id),
            ).fetchone()
            if project is None:
                raise RecordNotFound("project not found in tenant scope")

            existing_key = cursor.execute(
                "SELECT request_digest, run_id FROM idempotency_keys "
                "WHERE tenant_id = ? AND project_id = ? AND operation = ? "
                "AND idempotency_key = ?",
                (
                    request.tenant_id,
                    request.project_id,
                    request.operation,
                    request.idempotency_key,
                ),
            ).fetchone()
            if existing_key is not None:
                if existing_key["request_digest"] != request_digest:
                    raise IdempotencyConflict(
                        "idempotency key is already bound to a different request digest"
                    )
                row = cursor.execute(
                    "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? "
                    "AND run_id = ?",
                    (
                        request.tenant_id,
                        request.project_id,
                        existing_key["run_id"],
                    ),
                ).fetchone()
                if row is None:
                    raise StoreError("idempotency record references a missing run")
                return IdempotencyDecision(
                    disposition=IdempotencyDisposition.REPLAYED,
                    run=self._run_from_row(row),
                )

            existing_run = cursor.execute(
                "SELECT 1 FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (request.tenant_id, request.project_id, request.run_id),
            ).fetchone()
            if existing_run is not None:
                raise RecordConflict("run_id already exists in tenant/project scope")

            cursor.execute(
                "INSERT INTO runs "
                "(tenant_id, project_id, run_id, operation, request_digest, status, "
                "response_json, response_digest, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
                (
                    request.tenant_id,
                    request.project_id,
                    request.run_id,
                    request.operation,
                    request_digest,
                    RunStatus.PENDING.value,
                    timestamp,
                    timestamp,
                ),
            )
            cursor.execute(
                "INSERT INTO idempotency_keys "
                "(tenant_id, project_id, operation, idempotency_key, request_digest, "
                "run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    request.tenant_id,
                    request.project_id,
                    request.operation,
                    request.idempotency_key,
                    request_digest,
                    request.run_id,
                    timestamp,
                ),
            )
            self._append_event_in_transaction(
                cursor,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                run_id=request.run_id,
                event_type="run.created",
                payload={
                    "operation": request.operation,
                    "request_digest": request_digest,
                },
                created_at=timestamp,
            )
            row = cursor.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (request.tenant_id, request.project_id, request.run_id),
            ).fetchone()
            assert row is not None
            return IdempotencyDecision(
                disposition=IdempotencyDisposition.CREATED,
                run=self._run_from_row(row),
            )

    def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord:
        self._validate_scope(tenant_id, project_id, run_id)
        row = self._read_one(
            "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
            (tenant_id, project_id, run_id),
        )
        if row is None:
            raise RecordNotFound("run not found in tenant/project scope")
        return self._run_from_row(row)

    def set_run_status(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        status: RunStatus,
        *,
        response: JsonValue | None = None,
    ) -> RunRecord:
        self._validate_scope(tenant_id, project_id, run_id)
        if not isinstance(status, RunStatus):
            raise TypeError("status must be RunStatus")
        if status is RunStatus.SUCCEEDED and response is None:
            raise ValueError("SUCCEEDED requires a canonical response")
        if status in {RunStatus.PENDING, RunStatus.RUNNING} and response is not None:
            raise ValueError("non-terminal run status cannot carry a response")
        normalized_response = None if response is None else canonical_value(response)
        response_json = (
            None if normalized_response is None else canonical_json(normalized_response)
        )
        response_digest = (
            None
            if normalized_response is None
            else canonical_digest(normalized_response)
        )
        timestamp = self._clock()
        with self._transaction() as cursor:
            row = cursor.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (tenant_id, project_id, run_id),
            ).fetchone()
            if row is None:
                raise RecordNotFound("run not found in tenant/project scope")
            current = RunStatus(row["status"])
            if current is status:
                if row["response_digest"] != response_digest:
                    raise StateTransitionError(
                        "repeated status transition has a different response digest"
                    )
                return self._run_from_row(row)
            if status not in _RUN_TRANSITIONS[current]:
                raise StateTransitionError(
                    f"run status transition {current.value} -> {status.value} is forbidden"
                )
            cursor.execute(
                "UPDATE runs SET status = ?, response_json = ?, response_digest = ?, "
                "updated_at = ? WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (
                    status.value,
                    response_json,
                    response_digest,
                    timestamp,
                    tenant_id,
                    project_id,
                    run_id,
                ),
            )
            self._append_event_in_transaction(
                cursor,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                event_type="run.status-changed",
                payload={
                    "from": current.value,
                    "to": status.value,
                    "response_digest": response_digest,
                },
                created_at=timestamp,
            )
            updated = cursor.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (tenant_id, project_id, run_id),
            ).fetchone()
            assert updated is not None
            return self._run_from_row(updated)

    def put_artifact(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        artifact: ArtifactInput,
    ) -> ArtifactRecord:
        self._validate_scope(tenant_id, project_id, run_id)
        if not isinstance(artifact, ArtifactInput):
            raise TypeError("artifact must be ArtifactInput")
        metadata_json = canonical_json(artifact.metadata)
        metadata_digest = canonical_digest(artifact.metadata)
        timestamp = self._clock()
        with self._transaction() as cursor:
            self._require_run(cursor, tenant_id, project_id, run_id)
            existing = cursor.execute(
                "SELECT * FROM artifacts WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? AND artifact_id = ?",
                (tenant_id, project_id, run_id, artifact.artifact_id),
            ).fetchone()
            if existing is not None:
                record = self._artifact_from_row(existing)
                if (
                    record.kind != artifact.kind
                    or record.content_digest != artifact.content_digest
                    or record.byte_count != artifact.byte_count
                    or record.media_type != artifact.media_type
                    or existing["metadata_digest"] != metadata_digest
                ):
                    raise RecordConflict(
                        "artifact_id already exists with different immutable content"
                    )
                return record
            cursor.execute(
                "INSERT INTO artifacts "
                "(tenant_id, project_id, run_id, artifact_id, kind, content_digest, "
                "byte_count, media_type, metadata_json, metadata_digest, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    project_id,
                    run_id,
                    artifact.artifact_id,
                    artifact.kind,
                    artifact.content_digest,
                    artifact.byte_count,
                    artifact.media_type,
                    metadata_json,
                    metadata_digest,
                    timestamp,
                ),
            )
            self._append_event_in_transaction(
                cursor,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                event_type="artifact.recorded",
                payload={
                    "artifact_id": artifact.artifact_id,
                    "kind": artifact.kind,
                    "content_digest": artifact.content_digest,
                    "byte_count": artifact.byte_count,
                },
                created_at=timestamp,
            )
            row = cursor.execute(
                "SELECT * FROM artifacts WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? AND artifact_id = ?",
                (tenant_id, project_id, run_id, artifact.artifact_id),
            ).fetchone()
            assert row is not None
            return self._artifact_from_row(row)

    def put_evidence(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        evidence: EvidenceInput,
    ) -> EvidenceRecord:
        self._validate_scope(tenant_id, project_id, run_id)
        if not isinstance(evidence, EvidenceInput):
            raise TypeError("evidence must be EvidenceInput")
        details_json = canonical_json(evidence.details)
        details_digest = canonical_digest(evidence.details)
        timestamp = self._clock()
        with self._transaction() as cursor:
            self._require_run(cursor, tenant_id, project_id, run_id)
            if evidence.artifact_id is not None:
                artifact = cursor.execute(
                    "SELECT 1 FROM artifacts WHERE tenant_id = ? AND project_id = ? "
                    "AND run_id = ? AND artifact_id = ?",
                    (tenant_id, project_id, run_id, evidence.artifact_id),
                ).fetchone()
                if artifact is None:
                    raise RecordNotFound(
                        "evidence artifact not found in tenant/project/run scope"
                    )
            existing = cursor.execute(
                "SELECT * FROM evidence WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? AND evidence_id = ?",
                (tenant_id, project_id, run_id, evidence.evidence_id),
            ).fetchone()
            if existing is not None:
                record = self._evidence_from_row(existing)
                if (
                    record.kind != evidence.kind
                    or record.subject_digest != evidence.subject_digest
                    or record.state is not evidence.state
                    or existing["details_digest"] != details_digest
                    or record.artifact_id != evidence.artifact_id
                    or record.verifier != evidence.verifier
                ):
                    raise RecordConflict(
                        "evidence_id already exists with different immutable content"
                    )
                return record
            cursor.execute(
                "INSERT INTO evidence "
                "(tenant_id, project_id, run_id, evidence_id, kind, subject_digest, "
                "state, details_json, details_digest, artifact_id, verifier, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    project_id,
                    run_id,
                    evidence.evidence_id,
                    evidence.kind,
                    evidence.subject_digest,
                    evidence.state.value,
                    details_json,
                    details_digest,
                    evidence.artifact_id,
                    evidence.verifier,
                    timestamp,
                ),
            )
            self._append_event_in_transaction(
                cursor,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                event_type="evidence.recorded",
                payload={
                    "evidence_id": evidence.evidence_id,
                    "kind": evidence.kind,
                    "state": evidence.state.value,
                    "subject_digest": evidence.subject_digest,
                },
                created_at=timestamp,
            )
            row = cursor.execute(
                "SELECT * FROM evidence WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? AND evidence_id = ?",
                (tenant_id, project_id, run_id, evidence.evidence_id),
            ).fetchone()
            assert row is not None
            return self._evidence_from_row(row)

    def append_checkpoint(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: JsonValue,
        *,
        expected_previous_sequence: int | None = None,
    ) -> CheckpointRecord:
        self._validate_scope(tenant_id, project_id, run_id)
        if expected_previous_sequence is not None and expected_previous_sequence < 0:
            raise ValueError("expected_previous_sequence cannot be negative")
        normalized = canonical_value(state)
        state_json = canonical_json(normalized)
        state_digest = canonical_digest(normalized)
        timestamp = self._clock()
        with self._transaction() as cursor:
            self._require_run(cursor, tenant_id, project_id, run_id)
            row = cursor.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS current_sequence FROM checkpoints "
                "WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (tenant_id, project_id, run_id),
            ).fetchone()
            assert row is not None
            previous = int(row["current_sequence"])
            if (
                expected_previous_sequence is not None
                and expected_previous_sequence != previous
            ):
                raise CheckpointConflict(
                    "checkpoint sequence changed since caller observation"
                )
            sequence = previous + 1
            cursor.execute(
                "INSERT INTO checkpoints "
                "(tenant_id, project_id, run_id, sequence, state_digest, state_json, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    project_id,
                    run_id,
                    sequence,
                    state_digest,
                    state_json,
                    timestamp,
                ),
            )
            self._append_event_in_transaction(
                cursor,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                event_type="checkpoint.recorded",
                payload={"sequence": sequence, "state_digest": state_digest},
                created_at=timestamp,
            )
            return CheckpointRecord(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                sequence=sequence,
                state_digest=state_digest,
                state=normalized,
                created_at=timestamp,
            )

    def append_event(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_type: str,
        payload: JsonValue,
    ) -> EventRecord:
        self._validate_scope(tenant_id, project_id, run_id)
        require_operation(event_type)
        normalized = canonical_value(payload)
        timestamp = self._clock()
        with self._transaction() as cursor:
            self._require_run(cursor, tenant_id, project_id, run_id)
            return self._append_event_in_transaction(
                cursor,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                event_type=event_type,
                payload=normalized,
                created_at=timestamp,
            )

    def list_artifacts(
        self, tenant_id: str, project_id: str, run_id: str
    ) -> tuple[ArtifactRecord, ...]:
        self._validate_scope(tenant_id, project_id, run_id)
        return tuple(
            self._artifact_from_row(row)
            for row in self._read_all(
                "SELECT * FROM artifacts WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? ORDER BY artifact_id",
                (tenant_id, project_id, run_id),
            )
        )

    def list_evidence(
        self, tenant_id: str, project_id: str, run_id: str
    ) -> tuple[EvidenceRecord, ...]:
        self._validate_scope(tenant_id, project_id, run_id)
        return tuple(
            self._evidence_from_row(row)
            for row in self._read_all(
                "SELECT * FROM evidence WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? ORDER BY evidence_id",
                (tenant_id, project_id, run_id),
            )
        )

    def list_checkpoints(
        self, tenant_id: str, project_id: str, run_id: str
    ) -> tuple[CheckpointRecord, ...]:
        self._validate_scope(tenant_id, project_id, run_id)
        return tuple(
            self._checkpoint_from_row(row)
            for row in self._read_all(
                "SELECT * FROM checkpoints WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? ORDER BY sequence",
                (tenant_id, project_id, run_id),
            )
        )

    def list_events(
        self, tenant_id: str, project_id: str, run_id: str
    ) -> tuple[EventRecord, ...]:
        self._validate_scope(tenant_id, project_id, run_id)
        return tuple(
            self._event_from_row(row)
            for row in self._read_all(
                "SELECT * FROM events WHERE tenant_id = ? AND project_id = ? "
                "AND run_id = ? ORDER BY sequence",
                (tenant_id, project_id, run_id),
            )
        )

    @staticmethod
    def _validate_scope(tenant_id: str, project_id: str, run_id: str) -> None:
        require_identifier(tenant_id, field_name="tenant_id")
        require_identifier(project_id, field_name="project_id")
        require_identifier(run_id, field_name="run_id")

    @staticmethod
    def _require_run(
        cursor: sqlite3.Cursor, tenant_id: str, project_id: str, run_id: str
    ) -> None:
        row = cursor.execute(
            "SELECT 1 FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
            (tenant_id, project_id, run_id),
        ).fetchone()
        if row is None:
            raise RecordNotFound("run not found in tenant/project scope")

    @staticmethod
    def _append_event_in_transaction(
        cursor: sqlite3.Cursor,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_type: str,
        payload: JsonValue,
        created_at: str,
    ) -> EventRecord:
        require_operation(event_type)
        normalized = canonical_value(payload)
        payload_json = canonical_json(normalized)
        payload_digest = canonical_digest(normalized)
        row = cursor.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS current_sequence FROM events "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
            (tenant_id, project_id, run_id),
        ).fetchone()
        assert row is not None
        sequence = int(row["current_sequence"]) + 1
        cursor.execute(
            "INSERT INTO events "
            "(tenant_id, project_id, run_id, sequence, event_type, payload_digest, "
            "payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                project_id,
                run_id,
                sequence,
                event_type,
                payload_digest,
                payload_json,
                created_at,
            ),
        )
        return EventRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload_digest=payload_digest,
            payload=normalized,
            created_at=created_at,
        )

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> ProjectRecord:
        metadata = _load_json(row["metadata_json"])
        assert metadata is not None
        return ProjectRecord(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            metadata=metadata,
            created_at=row["created_at"],
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> RunRecord:
        request_digest = validate_digest(row["request_digest"])
        response = _load_json(row["response_json"])
        if row["response_digest"] is not None:
            if response is None or canonical_digest(response) != validate_digest(
                row["response_digest"]
            ):
                raise StoreError("stored run response digest mismatch")
        return RunRecord(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            operation=row["operation"],
            request_digest=request_digest,
            status=RunStatus(row["status"]),
            response=response,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> ArtifactRecord:
        metadata = _load_json(row["metadata_json"])
        assert metadata is not None
        if canonical_digest(metadata) != validate_digest(row["metadata_digest"]):
            raise StoreError("stored artifact metadata digest mismatch")
        return ArtifactRecord(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            artifact_id=row["artifact_id"],
            kind=row["kind"],
            content_digest=validate_digest(row["content_digest"]),
            byte_count=row["byte_count"],
            media_type=row["media_type"],
            metadata=metadata,
            created_at=row["created_at"],
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> EvidenceRecord:
        details = _load_json(row["details_json"])
        assert details is not None
        if canonical_digest(details) != validate_digest(row["details_digest"]):
            raise StoreError("stored evidence details digest mismatch")
        return EvidenceRecord(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            evidence_id=row["evidence_id"],
            kind=row["kind"],
            subject_digest=validate_digest(row["subject_digest"]),
            state=EvidenceState(row["state"]),
            details=details,
            artifact_id=row["artifact_id"],
            verifier=row["verifier"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row) -> CheckpointRecord:
        state = _load_json(row["state_json"])
        assert state is not None
        state_digest = validate_digest(row["state_digest"])
        if canonical_digest(state) != state_digest:
            raise StoreError("stored checkpoint state digest mismatch")
        return CheckpointRecord(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            sequence=row["sequence"],
            state_digest=state_digest,
            state=state,
            created_at=row["created_at"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> EventRecord:
        payload = _load_json(row["payload_json"])
        assert payload is not None
        payload_digest = validate_digest(row["payload_digest"])
        if canonical_digest(payload) != payload_digest:
            raise StoreError("stored event payload digest mismatch")
        return EventRecord(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            sequence=row["sequence"],
            event_type=row["event_type"],
            payload_digest=payload_digest,
            payload=payload,
            created_at=row["created_at"],
        )


__all__ = [
    "CheckpointConflict",
    "IdempotencyConflict",
    "ProjectIntelligenceStore",
    "RecordConflict",
    "RecordNotFound",
    "StateTransitionError",
    "StoreClosed",
    "StoreError",
]
