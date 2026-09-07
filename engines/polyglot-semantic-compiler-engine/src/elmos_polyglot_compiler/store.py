"""Durable tenant/project-scoped idempotency state for Skill execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Mapping, cast

from .contracts import IdempotencyConflict, RuntimeRequest, canonical_json, digest_json


class StateStoreError(RuntimeError):
    pass


class SqliteExecutionStore:
    def __init__(self, path: Path):
        if not Path(path).is_absolute():
            raise StateStoreError("state database path must be absolute")
        self.path = Path(os.path.abspath(path))
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (
            self.path.parent.is_symlink()
            or self.path.parent.resolve(strict=True) != self.path.parent
            or not self.path.parent.is_dir()
        ):
            raise StateStoreError("state database parent must have no symlink ancestors")
        parent_mode = stat.S_IMODE(self.path.parent.stat(follow_symlinks=False).st_mode)
        if parent_mode & 0o022:
            raise StateStoreError("state database parent may not be group/world writable")
        try:
            existing = self.path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None and (
            stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
        ):
            raise StateStoreError("state database path must be a regular file")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise StateStoreError("state database requires O_NOFOLLOW support")
        try:
            descriptor = os.open(
                self.path,
                os.O_RDWR | os.O_CREAT | int(nofollow) | int(getattr(os, "O_CLOEXEC", 0)),
                0o600,
            )
        except OSError as exc:
            raise StateStoreError("state database could not be opened without following links") from exc
        try:
            os.fchmod(descriptor, 0o600)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise StateStoreError("state database descriptor is not a regular file")
            self._database_identity = (metadata.st_dev, metadata.st_ino)
        finally:
            os.close(descriptor)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        before = self.path.stat(follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or (
            before.st_dev,
            before.st_ino,
        ) != self._database_identity:
            raise StateStoreError("state database identity changed before connect")
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        after = self.path.stat(follow_symlinks=False)
        if (after.st_dev, after.st_ino) != self._database_identity:
            connection.close()
            raise StateStoreError("state database identity changed during connect")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        os.chmod(self.path, 0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            try:
                sidecar_metadata = sidecar.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(sidecar_metadata.st_mode) or not stat.S_ISREG(
                sidecar_metadata.st_mode
            ):
                connection.close()
                raise StateStoreError("state database sidecar is not a regular file")
            os.chmod(sidecar, 0o600)
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS polyglot_execution (
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    skill_name TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    result_json BLOB NOT NULL,
                    result_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, project_id, skill_name, idempotency_key),
                    CHECK (length(tenant_id) > 0),
                    CHECK (length(project_id) > 0),
                    CHECK (length(skill_name) > 0),
                    CHECK (length(idempotency_key) > 0)
                )
                """
            )

    @staticmethod
    def request_digest(
        skill_name: str,
        request: RuntimeRequest,
        *,
        runtime_contract_digest: str,
    ) -> str:
        return digest_json(
            {
                "skill": skill_name,
                "runtime_contract_digest": runtime_contract_digest,
                "request": request.to_dict(),
            }
        )

    def lookup(
        self,
        *,
        skill_name: str,
        request: RuntimeRequest,
        request_digest: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT request_digest, result_json, result_digest
                FROM polyglot_execution
                WHERE tenant_id = ? AND project_id = ? AND skill_name = ?
                  AND idempotency_key = ?
                """,
                (
                    request.tenant_id,
                    request.project_id,
                    skill_name,
                    request.idempotency_key,
                ),
            ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise IdempotencyConflict(
                "idempotency key is already bound to different canonical input"
            )
        try:
            result = json.loads(bytes(row["result_json"]))
        except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise StateStoreError("stored execution result is corrupt") from exc
        if digest_json(result) != row["result_digest"]:
            raise StateStoreError("stored execution result digest mismatch")
        if not isinstance(result, dict):
            raise StateStoreError("stored execution result must be an object")
        return result

    def commit(
        self,
        *,
        skill_name: str,
        request: RuntimeRequest,
        request_digest: str,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        result_bytes = canonical_json(dict(result))
        result_digest = digest_json(dict(result))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT request_digest, result_json, result_digest
                FROM polyglot_execution
                WHERE tenant_id = ? AND project_id = ? AND skill_name = ?
                  AND idempotency_key = ?
                """,
                (
                    request.tenant_id,
                    request.project_id,
                    skill_name,
                    request.idempotency_key,
                ),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict(
                        "idempotency key is already bound to different canonical input"
                    )
                stored = json.loads(bytes(row["result_json"]))
                if not isinstance(stored, dict) or any(
                    not isinstance(key, str) for key in stored
                ):
                    raise StateStoreError("stored execution result is not an object")
                if digest_json(stored) != row["result_digest"]:
                    raise StateStoreError("stored execution result digest mismatch")
                connection.execute("COMMIT")
                return cast(dict[str, Any], stored)
            connection.execute(
                """
                INSERT INTO polyglot_execution (
                    tenant_id, project_id, skill_name, idempotency_key,
                    request_digest, result_json, result_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.tenant_id,
                    request.project_id,
                    skill_name,
                    request.idempotency_key,
                    request_digest,
                    result_bytes,
                    result_digest,
                ),
            )
            connection.execute("COMMIT")
            return dict(result)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
