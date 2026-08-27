"""JSON reference lifecycle with CAS, pause/resume and fencing semantics."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None


class RunState(str, Enum):
    PLANNED = "PLANNED"; PREPARING = "PREPARING"; BASELINING = "BASELINING"; TRANSFORMING = "TRANSFORMING"; GENERATING = "GENERATING"; BUILDING = "BUILDING"; VALIDATING = "VALIDATING"; SCORING = "SCORING"; PUBLISHING = "PUBLISHING"; PAUSING = "PAUSING"; PAUSED = "PAUSED"; RESUMING = "RESUMING"; CANCELLING = "CANCELLING"; COMPENSATING = "COMPENSATING"; COMPLETED = "COMPLETED"; CANCELLED = "CANCELLED"; FAILED = "FAILED"; BLOCKED = "BLOCKED"


TERMINAL_STATES = {RunState.COMPLETED, RunState.CANCELLED, RunState.FAILED, RunState.BLOCKED}
_ACTIVE = {RunState.PREPARING, RunState.BASELINING, RunState.TRANSFORMING, RunState.GENERATING, RunState.BUILDING, RunState.VALIDATING, RunState.SCORING, RunState.PUBLISHING}
ALLOWED_TRANSITIONS = {
    RunState.PLANNED: {RunState.PREPARING, RunState.CANCELLING, RunState.BLOCKED},
    RunState.PREPARING: {RunState.BASELINING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.BASELINING: {RunState.TRANSFORMING, RunState.GENERATING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.TRANSFORMING: {RunState.BUILDING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.GENERATING: {RunState.BUILDING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.BUILDING: {RunState.VALIDATING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.VALIDATING: {RunState.SCORING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.SCORING: {RunState.PUBLISHING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.PUBLISHING: {RunState.COMPLETED, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.PAUSING: {RunState.PAUSED, RunState.COMPENSATING, RunState.FAILED}, RunState.PAUSED: {RunState.RESUMING, RunState.CANCELLING, RunState.BLOCKED},
    RunState.RESUMING: _ACTIVE | {RunState.FAILED, RunState.BLOCKED}, RunState.CANCELLING: {RunState.COMPENSATING, RunState.CANCELLED, RunState.FAILED},
    RunState.COMPENSATING: {RunState.CANCELLED, RunState.FAILED, RunState.BLOCKED}, RunState.COMPLETED: set(), RunState.CANCELLED: set(), RunState.FAILED: set(), RunState.BLOCKED: set(),
}


class StateConflict(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


class JsonRunStateStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(value in run_id for value in ("/", "\\", "..")): raise ValueError("unsafe run_id")
        return self.directory / f"{run_id}.json"

    @contextmanager
    def _lock(self, run_id: str) -> Iterator[None]:
        with (self.directory / f".{run_id}.lock").open("a+") as handle:
            if fcntl is not None: fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try: yield
            finally:
                if fcntl is not None: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, path)
        finally: Path(name).unlink(missing_ok=True)

    def create(self, *, run_id: str, owner_id: str, tenant_id: str, candidate_digest: str, plan_digest: str, lease_seconds: int = 300, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._path(run_id)
        with self._lock(run_id):
            if path.exists(): raise StateConflict(f"run already exists: {run_id}")
            now = utc_now(); record = {"schema_version": "1.1", "run_id": run_id, "tenant_id": tenant_id, "candidate_digest": candidate_digest, "plan_digest": plan_digest, "state": "PLANNED", "resume_state": None, "revision": 0, "owner_id": owner_id, "fencing_token": 1, "lease_expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=lease_seconds)).isoformat(), "checkpoint_digest": None, "created_at": now, "updated_at": now, "metadata": metadata or {}, "history": [{"revision": 0, "from": None, "to": "PLANNED", "at": now, "owner_id": owner_id, "fencing_token": 1, "reason": "created"}]}
            self._write(path, record); return record

    def load(self, run_id: str) -> dict[str, Any]:
        return json.loads(self._path(run_id).read_text(encoding="utf-8"))

    def acquire(self, *, run_id: str, owner_id: str, expected_revision: int, lease_seconds: int = 300, allow_takeover_after_expiry: bool = True) -> dict[str, Any]:
        path = self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id)
            if record["revision"] != expected_revision: raise StateConflict("revision mismatch")
            expired = _time(record["lease_expires_at"]) <= dt.datetime.now(dt.timezone.utc)
            if record["owner_id"] != owner_id and not (allow_takeover_after_expiry and expired): raise StateConflict("run is owned by another live executor")
            record["owner_id"] = owner_id; record["fencing_token"] += 1; record["revision"] += 1; record["lease_expires_at"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=lease_seconds)).isoformat(); record["updated_at"] = utc_now(); record["history"].append({"revision": record["revision"], "from": record["state"], "to": record["state"], "at": record["updated_at"], "owner_id": owner_id, "fencing_token": record["fencing_token"], "reason": "lease-acquired"}); self._write(path, record); return record

    def heartbeat(self, *, run_id: str, owner_id: str, fencing_token: int, lease_seconds: int = 300) -> dict[str, Any]:
        path = self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id); self._assert_authority(record, owner_id, fencing_token); record["lease_expires_at"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=lease_seconds)).isoformat(); record["updated_at"] = utc_now(); self._write(path, record); return record

    @staticmethod
    def _assert_authority(record: dict[str, Any], owner_id: str, fencing_token: int) -> None:
        if record["owner_id"] != owner_id: raise StateConflict("owner mismatch")
        if record["fencing_token"] != fencing_token: raise StateConflict("stale fencing token")
        if _time(record["lease_expires_at"]) <= dt.datetime.now(dt.timezone.utc): raise StateConflict("executor lease expired")

    def transition(self, *, run_id: str, expected_state: RunState | str, target_state: RunState | str, owner_id: str, fencing_token: int, expected_revision: int, reason: str, checkpoint_digest: str | None = None, resume_state: RunState | str | None = None) -> dict[str, Any]:
        source, target, path = RunState(expected_state), RunState(target_state), self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id); self._assert_authority(record, owner_id, fencing_token)
            if record["revision"] != expected_revision or RunState(record["state"]) != source: raise StateConflict("revision or current state mismatch")
            if target not in ALLOWED_TRANSITIONS[source]: raise StateConflict(f"illegal transition: {source.value} -> {target.value}")
            if source in _ACTIVE and target == RunState.PAUSING: record["resume_state"] = source.value
            elif target == RunState.RESUMING and record.get("resume_state") is None: raise StateConflict("no resume state recorded")
            elif source == RunState.RESUMING and target in _ACTIVE:
                if target.value != record.get("resume_state"): raise StateConflict("resume target mismatch")
                record["resume_state"] = None
            elif resume_state is not None: record["resume_state"] = RunState(resume_state).value
            record["state"] = target.value; record["revision"] += 1; record["updated_at"] = utc_now(); record["checkpoint_digest"] = checkpoint_digest or record.get("checkpoint_digest"); record["history"].append({"revision": record["revision"], "from": source.value, "to": target.value, "at": record["updated_at"], "owner_id": owner_id, "fencing_token": fencing_token, "reason": reason, "checkpoint_digest": checkpoint_digest}); self._write(path, record); return record

    def record_checkpoint(self, *, run_id: str, checkpoint_digest: str, owner_id: str, fencing_token: int, expected_revision: int, phase: str | None = None) -> dict[str, Any]:
        if not checkpoint_digest.startswith("sha256:"): raise ValueError("checkpoint_digest must be sha256:<hex>")
        path = self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id); self._assert_authority(record, owner_id, fencing_token)
            if record["revision"] != expected_revision: raise StateConflict("revision mismatch")
            record["checkpoint_digest"] = checkpoint_digest; record["revision"] += 1; record["updated_at"] = utc_now(); record["history"].append({"revision": record["revision"], "from": record["state"], "to": record["state"], "at": record["updated_at"], "owner_id": owner_id, "fencing_token": fencing_token, "reason": "checkpoint-recorded", "phase": phase, "checkpoint_digest": checkpoint_digest}); self._write(path, record); return record

    @staticmethod
    def is_terminal(record: dict[str, Any]) -> bool:
        return RunState(record["state"]) in TERMINAL_STATES
