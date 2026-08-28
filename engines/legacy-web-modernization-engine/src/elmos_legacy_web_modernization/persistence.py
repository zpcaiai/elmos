"""Tenant-scoped SQLite control plane and private content-addressed artifacts."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Mapping

from .canonical import canonical_bytes, canonical_digest, finite_json
from .contracts import ArtifactEnvelope, RuntimeRequest, identifier, utc_now


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS modernization_run (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  state TEXT NOT NULL, policy_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
  owner_environment_id TEXT NOT NULL, current_phase TEXT, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, job_id)
);
CREATE TABLE IF NOT EXISTS idempotency_record (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  skill_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, input_hash TEXT NOT NULL,
  response_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, job_id, skill_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS control_event (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL, job_id TEXT NOT NULL, event_type TEXT NOT NULL,
  payload_digest TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_index (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  artifact_digest TEXT NOT NULL, artifact_type TEXT NOT NULL, schema_version TEXT NOT NULL,
  producer_skill TEXT NOT NULL, uri TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  state TEXT NOT NULL, policy_hash TEXT NOT NULL, environment_id TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, job_id, artifact_digest, artifact_type)
);
CREATE TABLE IF NOT EXISTS execution_checkpoint (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  skill_id TEXT NOT NULL, input_hash TEXT NOT NULL, policy_hash TEXT NOT NULL,
  fencing_token INTEGER NOT NULL, state TEXT NOT NULL, cursor_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, job_id, skill_id, input_hash, policy_hash)
);
CREATE TABLE IF NOT EXISTS execution_lease (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  skill_id TEXT NOT NULL, lease_id TEXT NOT NULL, fencing_token INTEGER NOT NULL,
  expires_at TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, job_id, skill_id, fencing_token),
  UNIQUE (tenant_id, project_id, job_id, skill_id, lease_id)
);
CREATE TABLE IF NOT EXISTS change_set (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  change_set_id TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
  fencing_token INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, job_id, change_set_id)
);
"""


class PersistenceError(RuntimeError):
    pass


class ContentAddressedStore:
    """Private local stand-in for object storage; never follows symlinks."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise PersistenceError("artifact root must be a real directory")
        for part in self.root.parents:
            if part == Path(part.anchor):
                break
            if part.is_symlink():
                raise PersistenceError("artifact root ancestry contains a symlink")

    def put(self, value: Mapping[str, Any]) -> tuple[str, int]:
        data = canonical_bytes(dict(value))
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        relative = Path(digest.removeprefix("sha256:")[:2]) / (digest.removeprefix("sha256:") + ".json")
        destination = self.root / relative
        destination.parent.mkdir(exist_ok=True)
        if destination.exists() and destination.is_symlink():
            raise PersistenceError("artifact destination is a symlink")
        if destination.exists():
            if destination.read_bytes() != data:
                raise PersistenceError("content-addressed artifact collision")
        else:
            temp = destination.parent / (".staging-" + secrets.token_hex(12))
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(temp, flags, 0o600)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, destination)
            finally:
                if temp.exists():
                    temp.unlink()
        return "artifact://local/" + digest, len(data)

    def get(self, digest: str) -> bytes:
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise PersistenceError("invalid artifact digest")
        path = self.root / digest[7:9] / (digest[7:] + ".json")
        if path.is_symlink() or not path.is_file():
            raise PersistenceError("artifact is missing or unsafe")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest[7:]:
            raise PersistenceError("artifact digest mismatch")
        return data


class StateStore:
    def __init__(self, database: str | os.PathLike[str], artifact_root: str | os.PathLike[str] | None = None) -> None:
        self.database = Path(database).absolute()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts = ContentAddressedStore(artifact_root or self.database.parent / "artifacts")
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, isolation_level="IMMEDIATE")
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _scope(request: RuntimeRequest) -> tuple[str, str, str]:
        return request.tenant_id, request.project_id, request.job_id

    def record_run(self, request: RuntimeRequest, *, state: str, phase: str | None = None) -> None:
        tenant, project, job = self._scope(request)
        now = utc_now()
        with self._connection() as db:
            db.execute("""INSERT INTO modernization_run(tenant_id,project_id,job_id,state,policy_hash,owner_environment_id,current_phase,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,project_id,job_id) DO UPDATE SET state=excluded.state, current_phase=excluded.current_phase, updated_at=excluded.updated_at, version=modernization_run.version+1""", (tenant, project, job, state, canonical_digest(request.policy), request.authority.environment_id, phase, now, now))

    def lookup_idempotency(self, request: RuntimeRequest) -> dict[str, Any] | None:
        input_hash = canonical_digest(request.inputs)
        with self._connection() as db:
            row = db.execute("SELECT input_hash,response_json FROM idempotency_record WHERE tenant_id=? AND project_id=? AND job_id=? AND skill_id=? AND idempotency_key=?", (*self._scope(request), request.skill_id, request.idempotency_key)).fetchone()
        if row is None:
            return None
        if row["input_hash"] != input_hash:
            raise PersistenceError("idempotency key was reused with different inputs")
        return json.loads(row["response_json"])

    def store_idempotency(self, request: RuntimeRequest, response: Mapping[str, Any]) -> None:
        payload = finite_json(dict(response))
        with self._connection() as db:
            db.execute("INSERT OR IGNORE INTO idempotency_record(tenant_id,project_id,job_id,skill_id,idempotency_key,input_hash,response_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (*self._scope(request), request.skill_id, request.idempotency_key, canonical_digest(request.inputs), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), utc_now()))

    def append_event(self, request: RuntimeRequest, event_type: str, payload: Mapping[str, Any]) -> None:
        payload = finite_json(dict(payload))
        with self._connection() as db:
            db.execute("INSERT INTO control_event(tenant_id,project_id,job_id,event_type,payload_digest,payload_json,created_at) VALUES(?,?,?,?,?,?,?)", (*self._scope(request), event_type, canonical_digest(payload), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), utc_now()))

    def acquire_lease(self, request: RuntimeRequest, *, ttl_seconds: int = 300) -> tuple[str, int]:
        if ttl_seconds < 1 or ttl_seconds > 86_400:
            raise PersistenceError("lease TTL is outside the bounded policy")
        tenant, project, job = self._scope(request)
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        now_value = now.isoformat().replace("+00:00", "Z")
        with self._connection() as db:
            rows = db.execute("SELECT lease_id,fencing_token,expires_at,state FROM execution_lease WHERE tenant_id=? AND project_id=? AND job_id=? AND skill_id=? ORDER BY fencing_token DESC", (tenant, project, job, request.skill_id)).fetchall()
            for row in rows:
                if row["state"] == "ACTIVE" and row["expires_at"] > now_value:
                    raise PersistenceError("an active lease already owns this job step")
            token = (int(rows[0]["fencing_token"]) + 1) if rows else 1
            lease_id = "lease-" + secrets.token_hex(16)
            db.execute("INSERT INTO execution_lease(tenant_id,project_id,job_id,skill_id,lease_id,fencing_token,expires_at,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (tenant, project, job, request.skill_id, lease_id, token, expires, "ACTIVE", now_value))
        return lease_id, token

    def verify_lease(self, request: RuntimeRequest, *, lease_id: str, fencing_token: int) -> None:
        with self._connection() as db:
            row = db.execute("SELECT expires_at,state,fencing_token FROM execution_lease WHERE tenant_id=? AND project_id=? AND job_id=? AND skill_id=? AND lease_id=?", (*self._scope(request), request.skill_id, lease_id)).fetchone()
        now = utc_now()
        if row is None or row["state"] != "ACTIVE" or int(row["fencing_token"]) != fencing_token or row["expires_at"] <= now:
            raise PersistenceError("lease is missing, expired, or fenced")

    def release_lease(self, request: RuntimeRequest, *, lease_id: str, fencing_token: int, state: str = "RELEASED") -> None:
        self.verify_lease(request, lease_id=lease_id, fencing_token=fencing_token)
        with self._connection() as db:
            db.execute("UPDATE execution_lease SET state=? WHERE tenant_id=? AND project_id=? AND job_id=? AND skill_id=? AND lease_id=? AND fencing_token=?", (state, *self._scope(request), request.skill_id, lease_id, fencing_token))

    def publish_artifact(self, request: RuntimeRequest, artifact: ArtifactEnvelope) -> dict[str, Any]:
        uri, size = self.artifacts.put(artifact.to_dict())
        with self._connection() as db:
            db.execute("INSERT OR IGNORE INTO artifact_index(tenant_id,project_id,job_id,artifact_digest,artifact_type,schema_version,producer_skill,uri,size_bytes,state,policy_hash,environment_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (*self._scope(request), artifact.digest, artifact.artifact_type, artifact.schema_version, artifact.producer_skill, uri, size, "PUBLISHED", artifact.policy_snapshot_hash, artifact.environment_id, artifact.created_at))
        self.append_event(request, "artifact.produced", {"type": artifact.artifact_type, "digest": artifact.digest, "uri": uri})
        return {"digest": artifact.digest, "uri": uri, "sizeBytes": size, "type": artifact.artifact_type}

    def checkpoint(self, request: RuntimeRequest, *, state: str, cursor: Mapping[str, Any], lease_id: str | None = None, fencing_token: int | None = None) -> None:
        if lease_id is not None or fencing_token is not None:
            if lease_id is None or fencing_token is None:
                raise PersistenceError("lease_id and fencing_token must be supplied together")
            self.verify_lease(request, lease_id=lease_id, fencing_token=fencing_token)
        else:
            fencing_token = request.authority.fencing_token
        with self._connection() as db:
            db.execute("INSERT OR REPLACE INTO execution_checkpoint(tenant_id,project_id,job_id,skill_id,input_hash,policy_hash,fencing_token,state,cursor_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (*self._scope(request), request.skill_id, canonical_digest(request.inputs), canonical_digest(request.policy), fencing_token, state, json.dumps(finite_json(dict(cursor)), sort_keys=True, separators=(",", ":")), utc_now()))

    def save_change_set(self, request: RuntimeRequest, payload: Mapping[str, Any], *, fencing_token: int | None = None) -> None:
        values = finite_json(dict(payload))
        change_set_id = str(values.get("changeSetId", ""))
        digest = str(values.get("digest", ""))
        if not change_set_id or not digest:
            raise PersistenceError("change set id and digest are required")
        with self._connection() as db:
            db.execute("INSERT OR IGNORE INTO change_set(tenant_id,project_id,job_id,change_set_id,digest,state,fencing_token,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (*self._scope(request), change_set_id, digest, values.get("state", "STAGED"), request.authority.fencing_token if fencing_token is None else fencing_token, json.dumps(values, sort_keys=True, separators=(",", ":")), utc_now()))
