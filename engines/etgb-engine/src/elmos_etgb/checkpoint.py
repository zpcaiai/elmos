"""Digest-verified checkpoint storage for long-running ETGB phases."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def utc_now() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CheckpointConflict(RuntimeError):
    pass


class CheckpointStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(value in run_id for value in ("/", "\\", "..")): raise ValueError("unsafe run_id")
        return self.directory / f"{run_id}.checkpoint.json"

    @staticmethod
    def _atomic_write(path: Path, value: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, path)
        finally: Path(name).unlink(missing_ok=True)

    def save(self, *, run_id: str, phase: str, candidate_digest: str, plan_digest: str, environment_digest: str, fencing_token: int, workspace_digest: str | None = None, artifacts: list[dict[str, Any]] | None = None, side_effects: list[dict[str, Any]] | None = None, resume_payload: dict[str, Any] | None = None, expected_revision: int | None = None) -> dict[str, Any]:
        path = self._path(run_id); previous = None
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if expected_revision is not None and previous["revision"] != expected_revision: raise CheckpointConflict("checkpoint revision mismatch")
            if fencing_token < previous["fencing_token"]: raise CheckpointConflict("stale fencing token")
            if previous["candidate_digest"] != candidate_digest or previous["plan_digest"] != plan_digest: raise CheckpointConflict("candidate or plan changed")
        elif expected_revision not in {None, -1}: raise CheckpointConflict("checkpoint does not exist")
        record = {"schema_version": "1.1", "run_id": run_id, "phase": phase, "revision": 0 if previous is None else previous["revision"] + 1, "candidate_digest": candidate_digest, "plan_digest": plan_digest, "environment_digest": environment_digest, "workspace_digest": workspace_digest, "fencing_token": fencing_token, "artifacts": artifacts or [], "side_effects": side_effects or [], "resume_payload": resume_payload or {}, "updated_at": utc_now()}
        record["checkpoint_digest"] = canonical_digest({key: value for key, value in record.items() if key != "checkpoint_digest"})
        self._atomic_write(path, record); return record

    def load(self, run_id: str) -> dict[str, Any]:
        return json.loads(self._path(run_id).read_text(encoding="utf-8"))

    def verify(self, run_id: str) -> dict[str, Any]:
        try: record = self.load(run_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc: return {"valid": False, "errors": [str(exc)]}
        errors: list[str] = []
        expected = canonical_digest({key: value for key, value in record.items() if key != "checkpoint_digest"})
        if record.get("checkpoint_digest") != expected: errors.append("checkpoint digest mismatch")
        for artifact in record.get("artifacts", []):
            path = artifact.get("path")
            if not path or not Path(path).is_file(): errors.append(f"missing checkpoint artifact: {path}"); continue
            actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if artifact.get("sha256") not in {actual, "sha256:" + actual}: errors.append(f"checkpoint artifact digest mismatch: {path}")
        return {"valid": not errors, "errors": errors, "checkpoint_digest": record.get("checkpoint_digest"), "revision": record.get("revision")}

    def resume_contract(self, run_id: str, *, candidate_digest: str, plan_digest: str, current_fencing_token: int) -> dict[str, Any]:
        record = self.load(run_id); report = self.verify(run_id); errors = list(report.get("errors", []))
        if record.get("candidate_digest") != candidate_digest: errors.append("candidate digest changed")
        if record.get("plan_digest") != plan_digest: errors.append("plan digest changed")
        if current_fencing_token <= int(record.get("fencing_token", 0)): errors.append("resume requires a fresh fencing token")
        return {"resumable": not errors, "errors": errors, "phase": record.get("phase"), "resume_payload": record.get("resume_payload", {})}
