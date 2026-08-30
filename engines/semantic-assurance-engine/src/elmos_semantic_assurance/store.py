"""Tenant/project-scoped durable state for semantic-assurance invocations."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import threading
from pathlib import Path
from typing import Any

from .canonical import canonical_json, digest_value, validate_digest, validate_identifier
from .contracts import ArtifactRecord, AssuranceScope, utc_now


class StoreError(RuntimeError):
    pass


class IdempotencyConflict(StoreError):
    pass


def _stored_object(value: str, label: str) -> dict[str, Any]:
    try:
        document = json.loads(value)
    except json.JSONDecodeError as exc:
        raise StoreError(f"stored {label} is not valid JSON") from exc
    if not isinstance(document, dict):
        raise StoreError(f"stored {label} is not a JSON object")
    return document


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_metadata (
  schema_name TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL CHECK (schema_version = 1)
) STRICT;

CREATE TABLE IF NOT EXISTS invocations (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  skill_name TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  response_digest TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, skill_name, idempotency_key)
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS artifacts (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  skill_name TEXT NOT NULL,
  logical_path TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  media_type TEXT NOT NULL,
  byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
  content_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id, skill_name, logical_path)
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS cache_entries (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  skill_name TEXT NOT NULL,
  cache_key TEXT NOT NULL,
  dependency_digest TEXT NOT NULL,
  result_digest TEXT NOT NULL,
  result_json TEXT NOT NULL,
  stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, skill_name, cache_key)
) WITHOUT ROWID, STRICT;

CREATE TABLE IF NOT EXISTS events (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence > 0),
  event_type TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id, sequence)
) WITHOUT ROWID, STRICT;

CREATE TRIGGER IF NOT EXISTS semantic_events_no_update
BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS semantic_events_no_delete
BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS semantic_artifacts_no_update
BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT, 'artifacts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS semantic_artifacts_no_delete
BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT, 'artifacts are append-only'); END;
"""


def _safe_database_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parent.parts[1:]:
        current /= part
        if current.is_symlink():
            raise StoreError("state database parent path must not contain symlinks")
        if not current.is_dir():
            raise StoreError("state database parent must exist and be a directory")
    if absolute.is_symlink():
        raise StoreError("state database path must not be a symlink")
    if not absolute.exists():
        descriptor = os.open(
            absolute,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
    metadata = absolute.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise StoreError("state database must be one regular, non-hardlinked file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise StoreError("state database mode must be 0600")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise StoreError("state database must be owned by the current user")
    return absolute


class SemanticAssuranceStore:
    """SQLite store with no unscoped query surface."""

    def __init__(self, database: str | os.PathLike[str] = ":memory:") -> None:
        database_text = os.fspath(database)
        if not isinstance(database_text, str) or not database_text:
            raise ValueError("database must be a non-empty path or :memory:")
        if database_text != ":memory:":
            database_text = str(_safe_database_path(Path(database_text)))
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            database_text,
            isolation_level=None,
            check_same_thread=False,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA trusted_schema = OFF")
        if database_text != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.executescript(_SCHEMA)
        self._connection.execute(
            "INSERT OR IGNORE INTO schema_metadata VALUES('semantic-assurance', 1)"
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def replay(
        self,
        scope: AssuranceScope,
        skill_name: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        validate_identifier(skill_name, "skillName")
        validate_identifier(idempotency_key, "idempotencyKey")
        validate_digest(request_digest, "requestDigest")
        with self._lock:
            row = self._connection.execute(
                "SELECT request_digest,response_digest,response_json FROM invocations "
                "WHERE tenant_id=? AND project_id=? AND skill_name=? AND idempotency_key=?",
                (
                    scope.tenant_id,
                    scope.project_id,
                    skill_name,
                    idempotency_key,
                ),
            ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise IdempotencyConflict(
                "idempotency key is already bound to a different request digest"
            )
        response = _stored_object(row["response_json"], "idempotent response")
        if digest_value(response) != row["response_digest"]:
            raise StoreError("stored idempotent response failed integrity validation")
        return response

    def complete(
        self,
        scope: AssuranceScope,
        skill_name: str,
        idempotency_key: str,
        subject_id: str,
        request_digest: str,
        response: dict[str, Any],
        artifact_contents: tuple[tuple[ArtifactRecord, dict[str, Any]], ...],
        *,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        actor = validate_identifier(actor_id or subject_id, "actorId")
        validate_identifier(subject_id, "subjectId")
        response_json = canonical_json(response).decode("utf-8")
        response_digest = digest_value(response)
        created_at = utc_now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT request_digest,response_digest,response_json FROM invocations "
                    "WHERE tenant_id=? AND project_id=? AND skill_name=? AND idempotency_key=?",
                    (
                        scope.tenant_id,
                        scope.project_id,
                        skill_name,
                        idempotency_key,
                    ),
                ).fetchone()
                if row is not None:
                    if row["request_digest"] != request_digest:
                        raise IdempotencyConflict(
                            "idempotency key conflict during atomic completion"
                        )
                    stored = _stored_object(row["response_json"], "response")
                    if digest_value(stored) != row["response_digest"]:
                        raise StoreError("stored response integrity failure")
                    self._connection.execute("COMMIT")
                    return stored
                for artifact, content in artifact_contents:
                    content_json = canonical_json(content).decode("utf-8")
                    observed_digest = digest_value(content)
                    if observed_digest != artifact.content_digest:
                        raise StoreError("artifact content digest mismatch")
                    if len(content_json.encode("utf-8")) != artifact.byte_count:
                        raise StoreError("artifact byte count mismatch")
                    existing_artifact = self._connection.execute(
                        "SELECT content_digest,media_type,byte_count,content_json "
                        "FROM artifacts WHERE tenant_id=? AND project_id=? AND "
                        "run_id=? AND skill_name=? AND logical_path=?",
                        (
                            scope.tenant_id,
                            scope.project_id,
                            scope.run_id,
                            skill_name,
                            artifact.logical_path,
                        ),
                    ).fetchone()
                    if existing_artifact is None:
                        self._connection.execute(
                            "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (
                                scope.tenant_id,
                                scope.project_id,
                                scope.run_id,
                                skill_name,
                                artifact.logical_path,
                                artifact.content_digest,
                                artifact.media_type,
                                artifact.byte_count,
                                content_json,
                                created_at,
                            ),
                        )
                    elif (
                        existing_artifact["content_digest"] != artifact.content_digest
                        or existing_artifact["media_type"] != artifact.media_type
                        or existing_artifact["byte_count"] != artifact.byte_count
                        or existing_artifact["content_json"] != content_json
                    ):
                        raise StoreError("immutable artifact identity conflict")
                self._connection.execute(
                    "INSERT INTO invocations VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        scope.tenant_id,
                        scope.project_id,
                        skill_name,
                        idempotency_key,
                        actor,
                        subject_id,
                        request_digest,
                        response_digest,
                        response_json,
                        created_at,
                    ),
                )
                self._append_event_locked(
                    scope,
                    "skill-invocation-completed",
                    {
                        "skillName": skill_name,
                        "actorId": actor,
                        "subjectId": subject_id,
                        "requestDigest": request_digest,
                        "responseDigest": response_digest,
                    },
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return response

    def verify_event_chain(self, scope: AssuranceScope) -> dict[str, Any]:
        """Verify every scoped audit event against its payload and predecessor."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT sequence,event_type,payload_digest,payload_json,previous_hash,event_hash "
                "FROM events WHERE tenant_id=? AND project_id=? AND run_id=? "
                "ORDER BY sequence",
                (scope.tenant_id, scope.project_id, scope.run_id),
            ).fetchall()
        previous_hash = "sha256:" + "0" * 64
        for expected_sequence, row in enumerate(rows, start=1):
            if row["sequence"] != expected_sequence:
                raise StoreError("event sequence integrity validation failed")
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError as exc:
                raise StoreError("event payload integrity validation failed") from exc
            if digest_value(payload) != row["payload_digest"]:
                raise StoreError("event payload integrity validation failed")
            if row["previous_hash"] != previous_hash:
                raise StoreError("event chain predecessor validation failed")
            event_document = {
                "tenantId": scope.tenant_id,
                "projectId": scope.project_id,
                "runId": scope.run_id,
                "sequence": expected_sequence,
                "eventType": row["event_type"],
                "payloadDigest": row["payload_digest"],
                "previousHash": previous_hash,
            }
            if digest_value(event_document) != row["event_hash"]:
                raise StoreError("event hash integrity validation failed")
            previous_hash = row["event_hash"]
        return {
            "eventCount": len(rows),
            "chainHead": previous_hash,
            "verified": True,
        }

    def put_cache(
        self,
        scope: AssuranceScope,
        skill_name: str,
        cache_key: str,
        dependency_digest: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        validate_digest(cache_key, "cacheKey")
        validate_digest(dependency_digest, "dependencyDigest")
        result_json = canonical_json(result).decode("utf-8")
        result_digest = digest_value(result)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT dependency_digest,result_digest,result_json,stale FROM cache_entries "
                    "WHERE tenant_id=? AND project_id=? AND skill_name=? AND cache_key=?",
                    (
                        scope.tenant_id,
                        scope.project_id,
                        skill_name,
                        cache_key,
                    ),
                ).fetchone()
                if existing is not None and (
                    existing["dependency_digest"] != dependency_digest
                    or existing["result_digest"] != result_digest
                    or existing["result_json"] != result_json
                ):
                    raise StoreError("immutable semantic cache entry conflict")
                if existing is None:
                    self._connection.execute(
                        "INSERT INTO cache_entries VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            scope.tenant_id,
                            scope.project_id,
                            skill_name,
                            cache_key,
                            dependency_digest,
                            result_digest,
                            result_json,
                            0,
                            utc_now(),
                        ),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return {"cacheKey": cache_key, "resultDigest": result_digest, "stale": False}

    def invalidate_cache(
        self,
        scope: AssuranceScope,
        skill_name: str,
        dependency_digest: str,
    ) -> int:
        validate_digest(dependency_digest, "dependencyDigest")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE cache_entries SET stale=1 WHERE tenant_id=? AND project_id=? "
                "AND skill_name=? AND dependency_digest<>? AND stale=0",
                (
                    scope.tenant_id,
                    scope.project_id,
                    skill_name,
                    dependency_digest,
                ),
            )
        return cursor.rowcount

    def artifact(
        self,
        scope: AssuranceScope,
        skill_name: str,
        logical_path: str,
    ) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT content_digest,content_json FROM artifacts WHERE tenant_id=? "
                "AND project_id=? AND run_id=? AND skill_name=? AND logical_path=?",
                (
                    scope.tenant_id,
                    scope.project_id,
                    scope.run_id,
                    skill_name,
                    logical_path,
                ),
            ).fetchone()
        if row is None:
            raise StoreError("unknown scoped artifact")
        value = _stored_object(row["content_json"], "artifact")
        if digest_value(value) != row["content_digest"]:
            raise StoreError("artifact integrity validation failed")
        return value

    def _append_event_locked(
        self,
        scope: AssuranceScope,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        row = self._connection.execute(
            "SELECT sequence,event_hash FROM events WHERE tenant_id=? AND project_id=? "
            "AND run_id=? ORDER BY sequence DESC LIMIT 1",
            (scope.tenant_id, scope.project_id, scope.run_id),
        ).fetchone()
        sequence = 1 if row is None else int(row["sequence"]) + 1
        previous_hash = "sha256:" + "0" * 64 if row is None else row["event_hash"]
        payload_digest = digest_value(payload)
        event_document = {
            "tenantId": scope.tenant_id,
            "projectId": scope.project_id,
            "runId": scope.run_id,
            "sequence": sequence,
            "eventType": event_type,
            "payloadDigest": payload_digest,
            "previousHash": previous_hash,
        }
        self._connection.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                scope.tenant_id,
                scope.project_id,
                scope.run_id,
                sequence,
                event_type,
                payload_digest,
                canonical_json(payload).decode("utf-8"),
                previous_hash,
                digest_value(event_document),
                utc_now(),
            ),
        )


__all__ = [
    "IdempotencyConflict",
    "SemanticAssuranceStore",
    "StoreError",
]
