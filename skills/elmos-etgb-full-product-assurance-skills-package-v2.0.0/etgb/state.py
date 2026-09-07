from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator

try:  # pragma: no cover - Windows fallback is intentionally lock-free.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None


class RunState(StrEnum):
    PLANNED = "PLANNED"
    PREPARING = "PREPARING"
    BASELINING = "BASELINING"
    TRANSFORMING = "TRANSFORMING"
    GENERATING = "GENERATING"
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    SCORING = "SCORING"
    PUBLISHING = "PUBLISHING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    CANCELLING = "CANCELLING"
    COMPENSATING = "COMPENSATING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


TERMINAL_STATES = {
    RunState.COMPLETED,
    RunState.CANCELLED,
    RunState.FAILED,
    RunState.BLOCKED,
}

_ACTIVE_PHASES = {
    RunState.PREPARING,
    RunState.BASELINING,
    RunState.TRANSFORMING,
    RunState.GENERATING,
    RunState.BUILDING,
    RunState.VALIDATING,
    RunState.SCORING,
    RunState.PUBLISHING,
}

ALLOWED_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.PLANNED: {RunState.PREPARING, RunState.CANCELLING, RunState.BLOCKED},
    RunState.PREPARING: {RunState.BASELINING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.BASELINING: {RunState.TRANSFORMING, RunState.GENERATING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.TRANSFORMING: {RunState.BUILDING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.GENERATING: {RunState.BUILDING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.BUILDING: {RunState.VALIDATING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.VALIDATING: {RunState.SCORING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.SCORING: {RunState.PUBLISHING, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.PUBLISHING: {RunState.COMPLETED, RunState.PAUSING, RunState.CANCELLING, RunState.FAILED, RunState.BLOCKED},
    RunState.PAUSING: {RunState.PAUSED, RunState.COMPENSATING, RunState.FAILED},
    RunState.PAUSED: {RunState.RESUMING, RunState.CANCELLING, RunState.BLOCKED},
    RunState.RESUMING: _ACTIVE_PHASES | {RunState.FAILED, RunState.BLOCKED},
    RunState.CANCELLING: {RunState.COMPENSATING, RunState.CANCELLED, RunState.FAILED},
    RunState.COMPENSATING: {RunState.CANCELLED, RunState.FAILED, RunState.BLOCKED},
    RunState.COMPLETED: set(),
    RunState.CANCELLED: set(),
    RunState.FAILED: set(),
    RunState.BLOCKED: set(),
}


class StateConflict(RuntimeError):
    """Raised when ownership, fencing, revision, or transition checks fail."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


class JsonRunStateStore:
    """A small reference state store with CAS, leases, and fencing.

    Production Elmos should map the same invariants to PostgreSQL/Temporal. This
    implementation is intentionally usable for local tests and adapter SDK work.
    """

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(x in run_id for x in ("/", "\\", "..")):
            raise ValueError("unsafe run_id")
        return self.directory / f"{run_id}.json"

    @contextmanager
    def _lock(self, run_id: str) -> Iterator[None]:
        lock_path = self.directory / f".{run_id}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as fh:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _atomic_write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def create(
        self,
        *,
        run_id: str,
        owner_id: str,
        tenant_id: str,
        candidate_digest: str,
        plan_digest: str,
        lease_seconds: int = 300,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = self._path(run_id)
        with self._lock(run_id):
            if path.exists():
                raise StateConflict(f"run already exists: {run_id}")
            now = dt.datetime.now(dt.timezone.utc)
            record: dict[str, Any] = {
                "schema_version": "1.1",
                "run_id": run_id,
                "tenant_id": tenant_id,
                "candidate_digest": candidate_digest,
                "plan_digest": plan_digest,
                "state": RunState.PLANNED.value,
                "resume_state": None,
                "revision": 0,
                "owner_id": owner_id,
                "fencing_token": 1,
                "lease_expires_at": (now + dt.timedelta(seconds=lease_seconds)).isoformat(),
                "checkpoint_digest": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "metadata": metadata or {},
                "history": [
                    {
                        "revision": 0,
                        "from": None,
                        "to": RunState.PLANNED.value,
                        "at": now.isoformat(),
                        "owner_id": owner_id,
                        "fencing_token": 1,
                        "reason": "created",
                    }
                ],
            }
            self._atomic_write(path, record)
            return record

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def acquire(
        self,
        *,
        run_id: str,
        owner_id: str,
        expected_revision: int,
        lease_seconds: int = 300,
        allow_takeover_after_expiry: bool = True,
    ) -> dict[str, Any]:
        path = self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id)
            if record["revision"] != expected_revision:
                raise StateConflict("revision mismatch")
            expired = _parse_time(record["lease_expires_at"]) <= dt.datetime.now(dt.timezone.utc)
            if record["owner_id"] != owner_id and not (allow_takeover_after_expiry and expired):
                raise StateConflict("run is owned by another live executor")
            record["owner_id"] = owner_id
            record["fencing_token"] += 1
            record["revision"] += 1
            record["lease_expires_at"] = (
                dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=lease_seconds)
            ).isoformat()
            record["updated_at"] = utc_now()
            record["history"].append(
                {
                    "revision": record["revision"],
                    "from": record["state"],
                    "to": record["state"],
                    "at": record["updated_at"],
                    "owner_id": owner_id,
                    "fencing_token": record["fencing_token"],
                    "reason": "lease-acquired",
                }
            )
            self._atomic_write(path, record)
            return record

    def heartbeat(
        self,
        *,
        run_id: str,
        owner_id: str,
        fencing_token: int,
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        path = self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id)
            self._assert_authority(record, owner_id, fencing_token)
            record["lease_expires_at"] = (
                dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=lease_seconds)
            ).isoformat()
            record["updated_at"] = utc_now()
            self._atomic_write(path, record)
            return record

    @staticmethod
    def _assert_authority(record: dict[str, Any], owner_id: str, fencing_token: int) -> None:
        if record["owner_id"] != owner_id:
            raise StateConflict("owner mismatch")
        if record["fencing_token"] != fencing_token:
            raise StateConflict("stale fencing token")
        if _parse_time(record["lease_expires_at"]) <= dt.datetime.now(dt.timezone.utc):
            raise StateConflict("executor lease expired")

    def transition(
        self,
        *,
        run_id: str,
        expected_state: RunState | str,
        target_state: RunState | str,
        owner_id: str,
        fencing_token: int,
        expected_revision: int,
        reason: str,
        checkpoint_digest: str | None = None,
        resume_state: RunState | str | None = None,
    ) -> dict[str, Any]:
        path = self._path(run_id)
        source = RunState(expected_state)
        target = RunState(target_state)
        with self._lock(run_id):
            record = self.load(run_id)
            self._assert_authority(record, owner_id, fencing_token)
            if record["revision"] != expected_revision:
                raise StateConflict("revision mismatch")
            if RunState(record["state"]) != source:
                raise StateConflict(f"expected {source.value}, found {record['state']}")
            if target not in ALLOWED_TRANSITIONS[source]:
                raise StateConflict(f"illegal transition: {source.value} -> {target.value}")
            if source in _ACTIVE_PHASES and target == RunState.PAUSING:
                record["resume_state"] = source.value
            elif target == RunState.RESUMING and record.get("resume_state") is None:
                raise StateConflict("no resume state recorded")
            elif source == RunState.RESUMING and target in _ACTIVE_PHASES:
                expected_resume = RunState(record["resume_state"])
                if target != expected_resume:
                    raise StateConflict(
                        f"resume target mismatch: expected {expected_resume.value}, got {target.value}"
                    )
                record["resume_state"] = None
            elif resume_state is not None:
                record["resume_state"] = RunState(resume_state).value

            record["state"] = target.value
            record["revision"] += 1
            record["updated_at"] = utc_now()
            if checkpoint_digest is not None:
                record["checkpoint_digest"] = checkpoint_digest
            record["history"].append(
                {
                    "revision": record["revision"],
                    "from": source.value,
                    "to": target.value,
                    "at": record["updated_at"],
                    "owner_id": owner_id,
                    "fencing_token": fencing_token,
                    "reason": reason,
                    "checkpoint_digest": checkpoint_digest,
                }
            )
            self._atomic_write(path, record)
            return record

    def record_checkpoint(
        self,
        *,
        run_id: str,
        checkpoint_digest: str,
        owner_id: str,
        fencing_token: int,
        expected_revision: int,
        phase: str | None = None,
    ) -> dict[str, Any]:
        """Atomically bind the latest durable checkpoint to the run record.

        This is intentionally separate from a state transition: a phase can
        finish, persist its evidence/checkpoint, and only then advance. CAS and
        fencing prevent a stale executor from overwriting a newer checkpoint.
        """
        if not checkpoint_digest.startswith("sha256:"):
            raise ValueError("checkpoint_digest must be sha256:<hex>")
        path = self._path(run_id)
        with self._lock(run_id):
            record = self.load(run_id)
            self._assert_authority(record, owner_id, fencing_token)
            if record["revision"] != expected_revision:
                raise StateConflict("revision mismatch")
            record["checkpoint_digest"] = checkpoint_digest
            record["revision"] += 1
            record["updated_at"] = utc_now()
            record["history"].append(
                {
                    "revision": record["revision"],
                    "from": record["state"],
                    "to": record["state"],
                    "at": record["updated_at"],
                    "owner_id": owner_id,
                    "fencing_token": fencing_token,
                    "reason": "checkpoint-recorded",
                    "phase": phase,
                    "checkpoint_digest": checkpoint_digest,
                }
            )
            self._atomic_write(path, record)
            return record

    @staticmethod
    def is_terminal(record: dict[str, Any]) -> bool:
        return RunState(record["state"]) in TERMINAL_STATES
