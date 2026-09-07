from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical_digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


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


class CheckpointConflict(RuntimeError):
    pass


class CheckpointStore:
    """Durable local reference for phase checkpoints and side-effect receipts."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(x in run_id for x in ("/", "\\", "..")):
            raise ValueError("unsafe run_id")
        return self.directory / f"{run_id}.checkpoint.json"

    def save(
        self,
        *,
        run_id: str,
        phase: str,
        candidate_digest: str,
        plan_digest: str,
        environment_digest: str,
        fencing_token: int,
        workspace_digest: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        side_effects: list[dict[str, Any]] | None = None,
        resume_payload: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        path = self._path(run_id)
        previous: dict[str, Any] | None = None
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if expected_revision is not None and previous["revision"] != expected_revision:
                raise CheckpointConflict("checkpoint revision mismatch")
            if fencing_token < previous["fencing_token"]:
                raise CheckpointConflict("stale fencing token")
            if previous["candidate_digest"] != candidate_digest or previous["plan_digest"] != plan_digest:
                raise CheckpointConflict("candidate or plan changed")
        elif expected_revision not in {None, -1}:
            raise CheckpointConflict("checkpoint does not exist")

        record: dict[str, Any] = {
            "schema_version": "1.1",
            "run_id": run_id,
            "phase": phase,
            "revision": 0 if previous is None else previous["revision"] + 1,
            "candidate_digest": candidate_digest,
            "plan_digest": plan_digest,
            "environment_digest": environment_digest,
            "workspace_digest": workspace_digest,
            "fencing_token": fencing_token,
            "artifacts": artifacts or [],
            "side_effects": side_effects or [],
            "resume_payload": resume_payload or {},
            "created_at": previous["created_at"] if previous else utc_now(),
            "updated_at": utc_now(),
            "previous_checkpoint_digest": previous.get("checkpoint_digest") if previous else None,
        }
        material = dict(record)
        record["checkpoint_digest"] = canonical_digest(material)
        _atomic_write(path, record)
        return record

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def verify(
        self,
        run_id: str,
        *,
        candidate_digest: str | None = None,
        plan_digest: str | None = None,
        minimum_fencing_token: int | None = None,
    ) -> dict[str, Any]:
        record = self.load(run_id)
        material = dict(record)
        recorded = material.pop("checkpoint_digest", None)
        actual = canonical_digest(material)
        errors: list[str] = []
        if recorded != actual:
            errors.append("checkpoint digest mismatch")
        if candidate_digest is not None and record["candidate_digest"] != candidate_digest:
            errors.append("candidate digest mismatch")
        if plan_digest is not None and record["plan_digest"] != plan_digest:
            errors.append("plan digest mismatch")
        if minimum_fencing_token is not None and record["fencing_token"] < minimum_fencing_token:
            errors.append("checkpoint written by stale fencing token")
        artifact_errors: list[str] = []
        for artifact in record.get("artifacts", []):
            path_value = artifact.get("path")
            digest = artifact.get("sha256")
            if path_value and digest:
                path = Path(path_value)
                if not path.exists():
                    artifact_errors.append(f"missing artifact: {path}")
                elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    artifact_errors.append(f"artifact digest mismatch: {path}")
        errors.extend(artifact_errors)
        return {"valid": not errors, "record": record, "errors": errors}

    def resume_contract(
        self,
        run_id: str,
        *,
        candidate_digest: str,
        plan_digest: str,
        current_fencing_token: int,
    ) -> dict[str, Any]:
        verification = self.verify(
            run_id,
            candidate_digest=candidate_digest,
            plan_digest=plan_digest,
            minimum_fencing_token=1,
        )
        if not verification["valid"]:
            return {"resumable": False, "reason": verification["errors"], "checkpoint": verification["record"]}
        checkpoint = verification["record"]
        if current_fencing_token <= checkpoint["fencing_token"]:
            return {
                "resumable": False,
                "reason": ["resume requires a newly acquired fencing token"],
                "checkpoint": checkpoint,
            }
        return {
            "resumable": True,
            "resume_phase": checkpoint["phase"],
            "resume_payload": checkpoint.get("resume_payload", {}),
            "side_effect_receipts": checkpoint.get("side_effects", []),
            "checkpoint_digest": checkpoint["checkpoint_digest"],
        }
