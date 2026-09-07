#!/usr/bin/env python3
"""Tenant-isolated durable jobs for the Precision Migration adapter runtime."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.adapters import AdapterError, execute, validate_request_contract


IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
JOB_ID = re.compile(r"^pmj-[0-9a-f]{32}$")
TERMINAL = {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}
MAX_REQUEST_BYTES = 1024 * 1024


class JobError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def tenant_digest(tenant_id: str) -> str:
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()


def validate_identity(value: str, label: str) -> str:
    if not IDENTITY.fullmatch(value):
        raise JobError(f"{label} is invalid")
    return value


def validate_job_id(value: str) -> str:
    if not JOB_ID.fullmatch(value):
        raise JobError("job_id is invalid")
    return value


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary.write_bytes(encoded)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+b") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class JobStore:
    def __init__(
        self,
        root: Path,
        *,
        max_active: int = 2,
        max_jobs: int = 100,
        max_bytes: int = 1024 * 1024 * 1024,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.max_active = max_active
        self.max_jobs = max_jobs
        self.max_bytes = max_bytes
        if not 1 <= max_active <= 64 or not 1 <= max_jobs <= 100_000 or max_bytes < MAX_REQUEST_BYTES:
            raise JobError("job quota configuration is invalid")

    def tenant_root(self, tenant_id: str) -> Path:
        validate_identity(tenant_id, "tenant_id")
        path = self.root / "tenants" / tenant_digest(tenant_id)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
        return path

    def job_root(self, tenant_id: str, job_id: str) -> Path:
        return self.tenant_root(tenant_id) / "jobs" / validate_job_id(job_id)

    def _metadata_path(self, tenant_id: str, job_id: str) -> Path:
        return self.job_root(tenant_id, job_id) / "job.json"

    def read(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        path = self._metadata_path(tenant_id, job_id)
        if not path.is_file():
            raise JobError("job not found")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("tenant_id") != tenant_id or payload.get("job_id") != job_id:
            raise JobError("job identity mismatch")
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        atomic_json(self._metadata_path(payload["tenant_id"], payload["job_id"]), payload)

    def _usage(self, tenant_id: str) -> tuple[int, int, int]:
        jobs_root = self.tenant_root(tenant_id) / "jobs"
        jobs = list(jobs_root.glob("pmj-*/job.json")) if jobs_root.is_dir() else []
        active = 0
        total_bytes = 0
        for metadata in jobs:
            try:
                item = json.loads(metadata.read_text(encoding="utf-8"))
                if item.get("status") in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
                    active += 1
            except (OSError, json.JSONDecodeError):
                active += 1
            for path in metadata.parent.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    total_bytes += path.stat().st_size
        return active, len(jobs), total_bytes

    def audit(self, tenant_id: str, event: dict[str, Any]) -> None:
        base = self.tenant_root(tenant_id)
        path = base / "audit.jsonl"
        with locked(base / ".audit.lock"):
            _, previous = self._verify_audit_path(path)
            body = {"occurred_at": now(), "previous_hash": previous, **event}
            body["entry_hash"] = "sha256:" + hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(path, 0o600)

    @staticmethod
    def _verify_audit_path(path: Path) -> tuple[int, str]:
        previous = "sha256:" + "0" * 64
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line] if path.is_file() else []
        for index, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JobError(f"audit chain contains invalid JSON at entry {index}") from exc
            if not isinstance(entry, dict):
                raise JobError(f"audit chain entry {index} is not an object")
            claimed = entry.pop("entry_hash", None)
            if entry.get("previous_hash") != previous:
                raise JobError(f"audit chain previous hash mismatch at entry {index}")
            observed = "sha256:" + hashlib.sha256(
                json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if claimed != observed:
                raise JobError(f"audit chain entry hash mismatch at entry {index}")
            previous = observed
        return len(lines), previous

    def verify_audit(self, tenant_id: str) -> tuple[int, str]:
        base = self.tenant_root(tenant_id)
        with locked(base / ".audit.lock"):
            return self._verify_audit_path(base / "audit.jsonl")

    def submit(
        self,
        request: dict[str, Any],
        *,
        tenant_id: str,
        actor: str,
        retry_of: str | None = None,
    ) -> dict[str, Any]:
        validate_identity(actor, "actor")
        if not isinstance(request, dict):
            raise JobError("request root must be an object")
        # Authenticated job identity is authoritative.  A caller-supplied
        # request_actor must never be able to detach approvals from the actor
        # that actually submitted or retried the job.
        request = json.loads(json.dumps(request, ensure_ascii=False))
        policy = request.get("policy") if isinstance(request.get("policy"), dict) else {}
        request["policy"] = {**policy, "request_actor": actor}
        try:
            validate_request_contract(request)
        except AdapterError as exc:
            raise JobError(str(exc)) from exc
        encoded = json.dumps(request, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise JobError("request exceeds the job input budget")
        base = self.tenant_root(tenant_id)
        with locked(base / ".jobs.lock"):
            active, count, total_bytes = self._usage(tenant_id)
            if active >= self.max_active:
                raise JobError("tenant active-job quota exceeded")
            if count >= self.max_jobs:
                raise JobError("tenant retained-job quota exceeded")
            if total_bytes + len(encoded) > self.max_bytes:
                raise JobError("tenant evidence-storage quota exceeded")
            job_id = "pmj-" + uuid.uuid4().hex
            job_root = self.job_root(tenant_id, job_id)
            job_root.mkdir(parents=True, exist_ok=False, mode=0o700)
            request_path = job_root / "request.json"
            atomic_json(request_path, request)
            created = now()
            payload = {
                "schema_version": 1,
                "job_id": job_id,
                "tenant_id": tenant_id,
                "actor": actor,
                "status": "QUEUED",
                "progress": 0,
                "created_at": created,
                "updated_at": created,
                "request_digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
                "retry_of": retry_of,
                "cancel_requested": False,
                "result": None,
                "artifacts": [],
            }
            self._write(payload)
        self.audit(tenant_id, {"event": "JOB_SUBMITTED", "job_id": job_id, "actor": actor})
        return payload

    def start_worker(
        self,
        payload: dict[str, Any],
        *,
        evidence_roots: list[Path],
        trust_store: Path | None,
    ) -> None:
        job_root = self.job_root(payload["tenant_id"], payload["job_id"])
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "run",
            "--root",
            str(self.root),
            "--tenant",
            payload["tenant_id"],
            "--job-id",
            payload["job_id"],
        ]
        for root in evidence_roots:
            command.extend(["--evidence-root", str(root)])
        if trust_store:
            command.extend(["--trust-store", str(trust_store)])
        log_path = job_root / "worker.log"
        try:
            with log_path.open("ab") as log:
                os.chmod(log_path, 0o600)
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as exc:
            with locked(job_root / ".job.lock"):
                current = self.read(payload["tenant_id"], payload["job_id"])
                if current["status"] == "QUEUED":
                    current.update(
                        {
                            "status": "FAILED",
                            "progress": 100,
                            "updated_at": now(),
                            "result": {
                                "status": "FAILED",
                                "error": "WORKER_START_FAILED",
                                "message": type(exc).__name__,
                            },
                        }
                    )
                    self._write(current)
            self.audit(
                payload["tenant_id"],
                {"event": "JOB_FAILED", "job_id": payload["job_id"], "actor": payload["actor"]},
            )
            raise JobError("worker start failed") from exc

    def run(self, tenant_id: str, job_id: str, *, evidence_roots: list[Path], trust_store: Path | None) -> dict[str, Any]:
        payload = self.read(tenant_id, job_id)
        job_root = self.job_root(tenant_id, job_id)
        with locked(job_root / ".job.lock"):
            payload = self.read(tenant_id, job_id)
            if payload["status"] not in {"QUEUED", "CANCEL_REQUESTED"}:
                raise JobError("job is not queued")
            if payload["status"] == "CANCEL_REQUESTED" or (job_root / "cancel.requested").exists():
                payload.update({"status": "CANCELLED", "progress": 100, "updated_at": now(), "cancel_requested": True})
                self._write(payload)
                self.audit(tenant_id, {"event": "JOB_CANCELLED", "job_id": job_id, "actor": payload["actor"]})
                return payload
            payload.update({"status": "RUNNING", "progress": 10, "updated_at": now()})
            self._write(payload)
        self.audit(tenant_id, {"event": "JOB_STARTED", "job_id": job_id, "actor": payload["actor"]})
        request = json.loads((job_root / "request.json").read_text(encoding="utf-8"))
        output = job_root / "artifacts"
        try:
            result = execute(request, output, evidence_roots=evidence_roots, trust_store=trust_store)
        except Exception as exc:  # worker boundary must persist a terminal record
            result = {"status": "FAILED", "error": type(exc).__name__, "message": str(exc)}
        with locked(job_root / ".job.lock"):
            payload = self.read(tenant_id, job_id)
            cancelled = payload["status"] == "CANCEL_REQUESTED" or (job_root / "cancel.requested").exists()
            execution_state = result.get("execution_state")
            if cancelled:
                status = "CANCELLED"
            elif execution_state == "LOCAL_EXECUTED":
                status = "SUCCEEDED"
            elif execution_state in {"REQUIRES_ADAPTER", "CONDITIONALLY_VERIFIED", "REQUIRES_HUMAN_REVIEW", "UNSUPPORTED", "INCONCLUSIVE"}:
                status = "BLOCKED"
            else:
                status = "FAILED"
            payload.update(
                {
                    "status": status,
                    "progress": 100,
                    "updated_at": now(),
                    "cancel_requested": cancelled,
                    "result": result,
                    "artifacts": result.get("artifacts", []),
                }
            )
            self._write(payload)
        self.audit(tenant_id, {"event": f"JOB_{payload['status']}", "job_id": job_id, "actor": payload["actor"]})
        return payload

    def cancel(self, tenant_id: str, actor: str, job_id: str) -> dict[str, Any]:
        job_root = self.job_root(tenant_id, job_id)
        with locked(job_root / ".job.lock"):
            payload = self.read(tenant_id, job_id)
            if payload["status"] in TERMINAL:
                return payload
            marker = job_root / "cancel.requested"
            marker.write_text(now() + "\n", encoding="utf-8")
            os.chmod(marker, 0o600)
            payload.update({"status": "CANCEL_REQUESTED", "cancel_requested": True, "updated_at": now()})
            self._write(payload)
        self.audit(tenant_id, {"event": "JOB_CANCEL_REQUESTED", "job_id": job_id, "actor": actor})
        return payload

    def retry(self, tenant_id: str, actor: str, job_id: str) -> dict[str, Any]:
        original = self.read(tenant_id, job_id)
        if original["status"] not in TERMINAL:
            raise JobError("only terminal jobs can be retried")
        request = json.loads((self.job_root(tenant_id, job_id) / "request.json").read_text(encoding="utf-8"))
        return self.submit(request, tenant_id=tenant_id, actor=actor, retry_of=job_id)

    def list(self, tenant_id: str) -> dict[str, Any]:
        jobs_root = self.tenant_root(tenant_id) / "jobs"
        jobs = []
        for path in sorted(jobs_root.glob("pmj-*/job.json"), reverse=True) if jobs_root.is_dir() else []:
            try:
                jobs.append(self.read(tenant_id, path.parent.name))
            except JobError:
                continue
        active, count, total_bytes = self._usage(tenant_id)
        states: dict[str, int] = {}
        for job in jobs:
            states[job["status"]] = states.get(job["status"], 0) + 1
        audit_events, audit_head = self.verify_audit(tenant_id)
        return {
            "jobs": jobs,
            "quota": {
                "active": active,
                "active_limit": self.max_active,
                "retained": count,
                "retained_limit": self.max_jobs,
                "bytes": total_bytes,
                "bytes_limit": self.max_bytes,
            },
            "observability": {
                "job_states": dict(sorted(states.items())),
                "audit_events": audit_events,
                "audit_chain": "HASH_CHAINED_VALID",
                "audit_head": audit_head,
                "external_monitoring": "NOT_CONFIGURED",
            },
        }

    def gc(self, tenant_id: str, actor: str, older_than_seconds: int) -> dict[str, Any]:
        if older_than_seconds < 3600:
            raise JobError("GC retention must be at least one hour")
        cutoff = time.time() - older_than_seconds
        archive = self.tenant_root(tenant_id) / "archive"
        archive.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(archive, 0o700)
        moved = []
        with locked(self.tenant_root(tenant_id) / ".jobs.lock"):
            for job in self.list(tenant_id)["jobs"]:
                source = self.job_root(tenant_id, job["job_id"])
                if job["status"] in TERMINAL and source.stat().st_mtime < cutoff:
                    destination = archive / f"{job['job_id']}-{uuid.uuid4().hex}"
                    shutil.move(str(source), str(destination))
                    moved.append(job["job_id"])
        self.audit(tenant_id, {"event": "JOB_GC_ARCHIVED", "actor": actor, "job_ids": moved})
        return {"archived": moved, "recoverable_root": str(archive)}


def store_from_args(args: argparse.Namespace) -> JobStore:
    return JobStore(
        args.root,
        max_active=args.max_active,
        max_jobs=args.max_jobs,
        max_bytes=args.max_bytes,
    )


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--actor", default="worker")
    parser.add_argument("--max-active", type=int, default=2)
    parser.add_argument("--max-jobs", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    add_common(submit)
    submit.add_argument("--request", type=Path, required=True)
    submit.add_argument("--start", action="store_true")
    submit.add_argument("--evidence-root", type=Path, action="append", default=[])
    submit.add_argument("--trust-store", type=Path)
    run_parser = sub.add_parser("run")
    add_common(run_parser)
    run_parser.add_argument("--job-id", required=True)
    run_parser.add_argument("--evidence-root", type=Path, action="append", default=[])
    run_parser.add_argument("--trust-store", type=Path)
    status = sub.add_parser("status")
    add_common(status)
    status.add_argument("--job-id", required=True)
    listing = sub.add_parser("list")
    add_common(listing)
    cancel = sub.add_parser("cancel")
    add_common(cancel)
    cancel.add_argument("--job-id", required=True)
    retry = sub.add_parser("retry")
    add_common(retry)
    retry.add_argument("--job-id", required=True)
    retry.add_argument("--start", action="store_true")
    retry.add_argument("--evidence-root", type=Path, action="append", default=[])
    retry.add_argument("--trust-store", type=Path)
    gc = sub.add_parser("gc")
    add_common(gc)
    gc.add_argument("--older-than-seconds", type=int, required=True)
    args = parser.parse_args()
    try:
        store = store_from_args(args)
        if args.command == "submit":
            request = json.loads(args.request.read_text(encoding="utf-8"))
            payload = store.submit(request, tenant_id=args.tenant, actor=args.actor)
            if args.start:
                store.start_worker(payload, evidence_roots=args.evidence_root, trust_store=args.trust_store)
        elif args.command == "run":
            payload = store.run(args.tenant, args.job_id, evidence_roots=args.evidence_root, trust_store=args.trust_store)
        elif args.command == "status":
            payload = store.read(args.tenant, args.job_id)
        elif args.command == "list":
            payload = store.list(args.tenant)
        elif args.command == "cancel":
            payload = store.cancel(args.tenant, args.actor, args.job_id)
        elif args.command == "retry":
            payload = store.retry(args.tenant, args.actor, args.job_id)
            if args.start:
                store.start_worker(payload, evidence_roots=args.evidence_root, trust_store=args.trust_store)
        else:
            payload = store.gc(args.tenant, args.actor, args.older_than_seconds)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except (JobError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
