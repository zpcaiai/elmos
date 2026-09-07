#!/usr/bin/env python3
"""Independent rootless runtime lease reaper for the generation Runner host."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any
import uuid


TENANT = re.compile(r"[a-z][a-z0-9-]{2,62}")
LEASE_ID = re.compile(r"[0-9a-f]{32}")
LANGUAGES = {"java", "python", "csharp", "typescript", "go", "kotlin", "php", "rust"}
HEARTBEAT_SCHEMA = "elmos.generation-runtime-reaper-heartbeat.v2"
RUNTIME_LEASE_SECONDS = 600
PROVISIONING_LEASE_SECONDS = 300
# The rootless helper emits one 300-second provisioning marker and replaces it
# with the authoritative 600-second browser-runtime marker after health passes.
# No other marker window is valid.
MAX_TENANT_SCAN_ENTRIES = 10_000
MAX_JOB_SCAN_ENTRIES = 1_000
MAX_TOTAL_JOB_SCAN_ENTRIES = 10_000


class ReaperError(RuntimeError):
    pass


def _absolute_file(raw: str, reason: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ReaperError(reason)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ReaperError(reason)
    return resolved


def _absolute_directory(raw: str, reason: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ReaperError(reason)
    resolved = candidate.resolve(strict=True)
    if resolved == Path(resolved.anchor) or not resolved.is_dir():
        raise ReaperError(reason)
    return resolved


def _engine_kind(engine: Path) -> str:
    if engine.name == "podman":
        return "podman"
    if engine.name == "docker":
        return "docker"
    raise ReaperError("RUNTIME_REAPER_ENGINE_NOT_ALLOWLISTED")


def _engine_home(root: Path) -> Path:
    try:
        canonical_root = root.resolve(strict=True)
    except OSError as error:
        raise ReaperError("RUNTIME_REAPER_ENGINE_HOME_INVALID") from error
    home = canonical_root / "home"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if home.is_symlink():
        raise ReaperError("RUNTIME_REAPER_ENGINE_HOME_INVALID")
    try:
        resolved = home.resolve(strict=True)
        info = home.stat()
    except OSError as error:
        raise ReaperError("RUNTIME_REAPER_ENGINE_HOME_INVALID") from error
    if (
        resolved != home
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ReaperError("RUNTIME_REAPER_ENGINE_HOME_INVALID")
    return home


def _engine_runtime_directory(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ReaperError("RUNTIME_REAPER_ENGINE_XDG_RUNTIME_DIR_INVALID")
    try:
        resolved = candidate.resolve(strict=True)
        info = candidate.stat()
    except OSError as error:
        raise ReaperError("RUNTIME_REAPER_ENGINE_XDG_RUNTIME_DIR_INVALID") from error
    if (
        resolved != candidate
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ReaperError("RUNTIME_REAPER_ENGINE_XDG_RUNTIME_DIR_INVALID")
    return candidate


def _docker_unix_socket(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ReaperError("RUNTIME_REAPER_DOCKER_UNIX_SOCKET_INVALID")
    try:
        resolved = candidate.resolve(strict=True)
        info = candidate.stat()
    except OSError as error:
        raise ReaperError("RUNTIME_REAPER_DOCKER_UNIX_SOCKET_INVALID") from error
    if (
        resolved != candidate
        or not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o002
    ):
        raise ReaperError("RUNTIME_REAPER_DOCKER_UNIX_SOCKET_INVALID")
    return candidate


def _engine_environment(
    root: Path,
    engine: Path,
    source: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], str]:
    inherited = os.environ if source is None else source
    kind = _engine_kind(engine)
    home = _engine_home(root)
    xdg_raw = inherited.get("ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR", "").strip()
    socket_raw = inherited.get("ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET", "").strip()
    xdg_runtime = _engine_runtime_directory(xdg_raw) if xdg_raw else None
    docker_socket = _docker_unix_socket(socket_raw) if socket_raw else None
    if kind == "docker" and docker_socket is None:
        raise ReaperError("RUNTIME_REAPER_DOCKER_UNIX_SOCKET_NOT_CONFIGURED")
    if kind != "docker" and docker_socket is not None:
        raise ReaperError("RUNTIME_REAPER_DOCKER_UNIX_SOCKET_ENGINE_MISMATCH")
    environment = {
        "PATH": inherited.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": inherited.get("LANG", "en_US.UTF-8"),
        "LC_ALL": inherited.get("LC_ALL", "en_US.UTF-8"),
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    if xdg_runtime is not None:
        environment["XDG_RUNTIME_DIR"] = str(xdg_runtime)
    if docker_socket is not None:
        environment["DOCKER_HOST"] = f"unix://{docker_socket}"
    digest = hashlib.sha256()
    for value in (str(engine), str(home), str(xdg_runtime or ""), str(docker_socket or "")):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return environment, digest.hexdigest()


def _job_id(raw: str) -> str:
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError) as error:
        raise ReaperError("RUNTIME_REAPER_JOB_ID_INVALID") from error
    if str(parsed) != raw.lower():
        raise ReaperError("RUNTIME_REAPER_JOB_ID_INVALID")
    return str(parsed)


def _atomic_json(
    destination: Path,
    value: dict[str, Any],
    *,
    replace: bool = True,
) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    directory = os.open(destination.parent, directory_flags)
    temporary_name = f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    temporary_created = False
    try:
        directory_info = os.fstat(directory)
        if not stat.S_ISDIR(directory_info.st_mode):
            raise ReaperError("RUNTIME_REAPER_ATOMIC_PARENT_INVALID")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory)
        temporary_created = True
        try:
            os.fchmod(descriptor, 0o600)
            payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("RUNTIME_REAPER_ATOMIC_SHORT_WRITE")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        created = True
        if replace:
            os.replace(
                temporary_name,
                destination.name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
            )
            temporary_created = False
        else:
            try:
                os.link(
                    temporary_name,
                    destination.name,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
            except FileExistsError:
                created = False
            os.unlink(temporary_name, dir_fd=directory)
            temporary_created = False
        os.fsync(directory)
        return created
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory)
                os.fsync(directory)
            except OSError:
                pass
        os.close(directory)


def _bounded_sorted_entries(
    directory: Path,
    limit: int,
    *,
    limit_reason: str,
    read_reason: str,
) -> list[Path]:
    entries: list[Path] = []
    try:
        for entry in directory.iterdir():
            if len(entries) >= limit:
                raise ReaperError(limit_reason)
            entries.append(entry)
    except OSError as error:
        raise ReaperError(read_reason) from error
    return sorted(entries, key=lambda item: item.name)


def _safe_receipt_directory(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = root
    for part in destination.relative_to(root).parts:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ReaperError("RUNTIME_REAPER_RECEIPT_PATH_INVALID")
    resolved_root = root.resolve(strict=True)
    resolved = destination.resolve(strict=True)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ReaperError("RUNTIME_REAPER_RECEIPT_PATH_INVALID")


def _lease_marker(job_root: Path) -> dict[str, Any] | None:
    state = job_root / "runtime-state"
    if not state.exists():
        return None
    if state.is_symlink() or not state.is_dir() or state.stat().st_mode & 0o077:
        raise ReaperError("RUNTIME_REAPER_STATE_INVALID")
    marker = state / "lease.json"
    if not marker.exists():
        return None
    if (
        marker.is_symlink()
        or not marker.is_file()
        or marker.stat().st_nlink != 1
        or marker.stat().st_mode & 0o077
        or marker.stat().st_size < 2
        or marker.stat().st_size > 64 * 1024
    ):
        raise ReaperError("RUNTIME_REAPER_MARKER_INVALID")
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReaperError("RUNTIME_REAPER_MARKER_INVALID") from error
    started = value.get("lease_started_epoch") if isinstance(value, dict) else None
    expires = value.get("lease_expires_epoch") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("job_id") != job_root.name
        or value.get("language") not in LANGUAGES
        or not isinstance(value.get("lease_id"), str)
        or LEASE_ID.fullmatch(value["lease_id"]) is None
        or value.get("phase") != "RUNNING"
        or not isinstance(started, int)
        or isinstance(started, bool)
        or not isinstance(expires, int)
        or isinstance(expires, bool)
        or expires - started not in {PROVISIONING_LEASE_SECONDS, RUNTIME_LEASE_SECONDS}
    ):
        raise ReaperError("RUNTIME_REAPER_MARKER_INVALID")
    return value


def _invoke_helper(
    helper: Path,
    engine: Path,
    job_root: Path,
    job_id: str,
    language: str,
    lease_id: str,
    environment: dict[str, str],
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(helper),
        "stop",
        "--engine",
        str(engine),
        "--language",
        language,
        "--job-id",
        job_id,
        "--state",
        str(job_root / "runtime-state"),
        "--lease-id",
        lease_id,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
            env=environment,
        )
        receipt = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ReaperError("RUNTIME_REAPER_HELPER_FAILED") from error
    if result.returncode != 0 or not isinstance(receipt, dict):
        raise ReaperError("RUNTIME_REAPER_CLEANUP_BLOCKED")
    if (
        receipt.get("job_id") != job_id
        or receipt.get("language") != language
        or receipt.get("requested_lease_id") != lease_id
    ):
        raise ReaperError("RUNTIME_REAPER_CLEANUP_RECEIPT_IDENTITY_INVALID")
    return receipt


def _runtime_candidate(
    job: dict[str, Any],
    now: datetime,
    job_root: Path,
) -> tuple[str, str, str] | None:
    runtime = job.get("runtime")
    cleanup_required = isinstance(runtime, dict) and runtime.get("reason") == "RUNTIME_LEASE_CLEANUP_FAILED"
    marker = _lease_marker(job_root)
    if marker is not None:
        language = str(marker["language"])
        lease_id = str(marker["lease_id"])
        started = int(marker["lease_started_epoch"])
        expires = int(marker["lease_expires_epoch"])
        now_epoch = int(now.timestamp())
        duration = expires - started
        runtime_claims_running = (
            isinstance(runtime, dict)
            and runtime.get("executor") == "ROOTLESS_CONTAINER"
            and runtime.get("status") == "RUNNING"
        )
        provisioning_state_diverged = (
            duration == PROVISIONING_LEASE_SECONDS and runtime_claims_running
        )
        if (
            not cleanup_required
            and not provisioning_state_diverged
            and started <= now_epoch + 5
            and expires > now_epoch
        ):
            return None
        trigger = "CLEANUP_RETRY" if cleanup_required else (
            "PROVISIONING_LEASE_EXPIRED"
            if duration == PROVISIONING_LEASE_SECONDS
            else "LEASE_EXPIRED"
        )
        if started > now_epoch + 5 or provisioning_state_diverged:
            trigger = "LEASE_STATE_DIVERGED"
        return language, lease_id, trigger
    if not isinstance(runtime, dict) or runtime.get("executor") != "ROOTLESS_CONTAINER":
        return None
    language = runtime.get("language")
    lease_id = runtime.get("leaseId")
    if language not in LANGUAGES or not isinstance(lease_id, str) or LEASE_ID.fullmatch(lease_id) is None:
        raise ReaperError("RUNTIME_REAPER_LEASE_IDENTITY_INVALID")
    if cleanup_required or runtime.get("status") in {"STARTING", "RUNNING"}:
        return language, lease_id, "CLEANUP_RETRY" if cleanup_required else "LEASE_MARKER_MISSING"
    return None


def _terminal_receipt_outcome(
    receipt: Path,
    tenant: str,
    job_id: str,
    lease_id: str,
) -> str | None:
    if not receipt.exists():
        return None
    if (
        receipt.is_symlink()
        or not receipt.is_file()
        or receipt.stat().st_nlink != 1
        or receipt.stat().st_mode & 0o077
        or receipt.stat().st_size < 2
        or receipt.stat().st_size > 64 * 1024
    ):
        raise ReaperError("RUNTIME_REAPER_RECEIPT_INVALID")
    try:
        value = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReaperError("RUNTIME_REAPER_RECEIPT_INVALID") from error
    try:
        observed_at = datetime.fromisoformat(
            str(value.get("observed_at") if isinstance(value, dict) else "").replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ReaperError("RUNTIME_REAPER_RECEIPT_INVALID") from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "elmos.generation-runtime-reaper.v1"
        or value.get("tenant_id") != tenant
        or value.get("job_id") != job_id
        or value.get("lease_id") != lease_id
        or value.get("trigger") not in {
            "CLEANUP_RETRY",
            "PROVISIONING_LEASE_EXPIRED",
            "LEASE_EXPIRED",
            "LEASE_STATE_DIVERGED",
            "LEASE_MARKER_MISSING",
        }
        or observed_at.tzinfo is None
        or (
            value.get("outcome"),
            value.get("helper_status"),
        ) not in {
            ("CLEANUP_VERIFIED", "STOPPED"),
            ("CLEANUP_VERIFIED", "MISSING"),
            ("NEWER_LEASE_PRESERVED", "SUPERSEDED"),
        }
    ):
        raise ReaperError("RUNTIME_REAPER_RECEIPT_INVALID")
    return str(value["outcome"])


def sweep(
    root: Path,
    repository_root: Path,
    engine: Path,
    engine_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    if engine_environment is None:
        engine_environment, _ = _engine_environment(root, engine)
    helper = repository_root / "scripts" / "operations" / "rootless_project_runner.py"
    if not helper.is_file() or helper.is_symlink():
        raise ReaperError("RUNTIME_REAPER_HELPER_INVALID")
    maintenance = root / ".maintenance.json"
    if maintenance.exists():
        if maintenance.is_symlink() or not maintenance.is_file() or maintenance.stat().st_size > 64 * 1024:
            raise ReaperError("RUNTIME_REAPER_MAINTENANCE_RECORD_INVALID")
        try:
            record = json.loads(maintenance.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReaperError("RUNTIME_REAPER_MAINTENANCE_RECORD_INVALID") from error
        if not isinstance(record, dict) or record.get("status") not in {
            "QUIESCED",
            "RESTORED_REQUIRES_RESUME",
        }:
            raise ReaperError("RUNTIME_REAPER_MAINTENANCE_RECORD_INVALID")
        return {"status": "REAPER_QUIESCED", "examined": 0, "cleaned": 0, "blocked": 0}
    tenants_root = root / "tenants"
    if not tenants_root.exists():
        return {"status": "REAPER_IDLE", "examined": 0, "cleaned": 0, "blocked": 0}
    if tenants_root.is_symlink() or not tenants_root.is_dir():
        raise ReaperError("RUNTIME_REAPER_TENANTS_ROOT_INVALID")
    now = datetime.now(timezone.utc)
    examined = 0
    cleaned = 0
    blocked = 0
    total_job_entries = 0
    error_root = root / "runtime-reaper-errors"
    _safe_receipt_directory(root, error_root)
    try:
        tenant_entries = _bounded_sorted_entries(
            tenants_root,
            MAX_TENANT_SCAN_ENTRIES,
            limit_reason="RUNTIME_REAPER_TENANT_SCAN_LIMIT",
            read_reason="RUNTIME_REAPER_TENANT_SCAN_FAILED",
        )
    except ReaperError as error:
        _atomic_json(
            error_root / "tenant-scan-blocked.json",
            {
                "schema_version": "elmos.generation-runtime-reaper.v1",
                "outcome": "BLOCKED",
                "reason": str(error),
                "observed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {"status": "BLOCKED", "examined": 0, "cleaned": 0, "blocked": 1}
    for tenant_root in tenant_entries:
        try:
            if (
                tenant_root.is_symlink()
                or not tenant_root.is_dir()
                or TENANT.fullmatch(tenant_root.name) is None
            ):
                raise ReaperError("RUNTIME_REAPER_TENANT_PATH_INVALID")
            jobs_root = tenant_root / "jobs"
            if not jobs_root.exists():
                continue
            if jobs_root.is_symlink() or not jobs_root.is_dir():
                raise ReaperError("RUNTIME_REAPER_JOBS_ROOT_INVALID")
            receipt_root = tenant_root / "runtime-reaper"
            _safe_receipt_directory(root, receipt_root)
            job_entries = _bounded_sorted_entries(
                jobs_root,
                MAX_JOB_SCAN_ENTRIES,
                limit_reason="RUNTIME_REAPER_JOB_SCAN_LIMIT",
                read_reason="RUNTIME_REAPER_JOB_SCAN_FAILED",
            )
            if total_job_entries + len(job_entries) > MAX_TOTAL_JOB_SCAN_ENTRIES:
                raise ReaperError("RUNTIME_REAPER_TOTAL_JOB_SCAN_LIMIT")
            total_job_entries += len(job_entries)
        except (OSError, ReaperError) as error:
            blocked += 1
            entry_digest = hashlib.sha256(tenant_root.name.encode("utf-8")).hexdigest()
            reason = str(error) if isinstance(error, ReaperError) else "RUNTIME_REAPER_TENANT_ACCESS_FAILED"
            _atomic_json(
                error_root / f"tenant-{entry_digest}.json",
                {
                    "schema_version": "elmos.generation-runtime-reaper.v1",
                    "tenant_entry_sha256": entry_digest,
                    "outcome": "BLOCKED",
                    "reason": reason,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            continue
        for job_root in job_entries:
            job_id: str | None = None
            try:
                if job_root.is_symlink() or not job_root.is_dir():
                    raise ReaperError("RUNTIME_REAPER_JOB_PATH_INVALID")
                job_id = _job_id(job_root.name)
                job_file = job_root / "job.json"
                if (
                    job_file.is_symlink()
                    or not job_file.is_file()
                    or job_file.stat().st_size > 4 * 1024 * 1024
                ):
                    raise ReaperError("RUNTIME_REAPER_JOB_RECORD_INVALID")
                try:
                    job = json.loads(job_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise ReaperError("RUNTIME_REAPER_JOB_RECORD_INVALID") from error
                if (
                    not isinstance(job, dict)
                    or job.get("id") != job_id
                    or job.get("tenantId") != tenant_root.name
                ):
                    raise ReaperError("RUNTIME_REAPER_JOB_IDENTITY_INVALID")
                examined += 1
                candidate = _runtime_candidate(job, now, job_root)
                if candidate is None:
                    continue
                language, lease_id, trigger = candidate
                success_receipt = receipt_root / f"{job_id}-{lease_id}.json"
                existing_outcome = _terminal_receipt_outcome(
                    success_receipt,
                    tenant_root.name,
                    job_id,
                    lease_id,
                )
                if existing_outcome == "CLEANUP_VERIFIED":
                    continue
                if existing_outcome == "NEWER_LEASE_PRESERVED":
                    raise ReaperError("RUNTIME_REAPER_NEWER_LEASE_PRESERVED")
                receipt = _invoke_helper(
                    helper,
                    engine,
                    job_root,
                    job_id,
                    language,
                    lease_id,
                    engine_environment,
                )
                status = receipt.get("status")
                if status not in {"STOPPED", "MISSING", "SUPERSEDED"}:
                    raise ReaperError("RUNTIME_REAPER_CLEANUP_UNVERIFIED")
                outcome = "NEWER_LEASE_PRESERVED" if status == "SUPERSEDED" else "CLEANUP_VERIFIED"
                created = _atomic_json(
                    success_receipt,
                    {
                        "schema_version": "elmos.generation-runtime-reaper.v1",
                        "tenant_id": tenant_root.name,
                        "job_id": job_id,
                        "lease_id": lease_id,
                        "trigger": trigger,
                        "outcome": outcome,
                        "helper_status": status,
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    replace=False,
                )
                if not created:
                    existing_outcome = _terminal_receipt_outcome(
                        success_receipt,
                        tenant_root.name,
                        job_id,
                        lease_id,
                    )
                    if existing_outcome is None:
                        raise ReaperError("RUNTIME_REAPER_RECEIPT_RACE")
                    if existing_outcome == "CLEANUP_VERIFIED":
                        continue
                    if existing_outcome == "NEWER_LEASE_PRESERVED":
                        raise ReaperError("RUNTIME_REAPER_NEWER_LEASE_PRESERVED")
                if status == "SUPERSEDED":
                    raise ReaperError("RUNTIME_REAPER_NEWER_LEASE_PRESERVED")
                if created:
                    cleaned += 1
            except (OSError, ReaperError) as error:
                blocked += 1
                safe_receipt_id = job_id or hashlib.sha256(job_root.name.encode("utf-8")).hexdigest()
                reason = str(error) if isinstance(error, ReaperError) else "RUNTIME_REAPER_JOB_ACCESS_FAILED"
                _atomic_json(
                    receipt_root / f"{safe_receipt_id}-blocked.json",
                    {
                        "schema_version": "elmos.generation-runtime-reaper.v1",
                        "tenant_id": tenant_root.name,
                        "job_id": job_id,
                        "job_entry_sha256": hashlib.sha256(job_root.name.encode("utf-8")).hexdigest(),
                        "outcome": "BLOCKED",
                        "reason": reason,
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
    return {
        "status": "BLOCKED" if blocked else "REAPER_SWEEP_COMPLETE",
        "examined": examined,
        "cleaned": cleaned,
        "blocked": blocked,
    }


def _write_heartbeat(
    root: Path,
    result: dict[str, Any],
    engine_context_sha256: str,
) -> None:
    _atomic_json(
        root / ".runtime-reaper-heartbeat.json",
        {
            "schema_version": HEARTBEAT_SCHEMA,
            "engine_context_sha256": engine_context_sha256,
            "pid": os.getpid(),
            "sweep_status": result.get("status"),
            "examined": result.get("examined", 0),
            "cleaned": result.get("cleaned", 0),
            "blocked": result.get("blocked", 0),
            "observed_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", required=True)
    result.add_argument("--repository-root", required=True)
    result.add_argument("--engine", required=True)
    result.add_argument("--interval-seconds", type=float, default=1.0)
    result.add_argument("--once", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        root = _absolute_directory(args.root, "RUNTIME_REAPER_ROOT_INVALID")
        repository_root = _absolute_directory(
            args.repository_root, "RUNTIME_REAPER_REPOSITORY_ROOT_INVALID"
        )
        engine = _absolute_file(args.engine, "RUNTIME_REAPER_ENGINE_INVALID")
        if args.interval_seconds < 0.25 or args.interval_seconds > 10:
            raise ReaperError("RUNTIME_REAPER_INTERVAL_INVALID")
        lock_flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        descriptor = os.open(root / ".runtime-reaper.lock", lock_flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            lock_info = os.fstat(descriptor)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1:
                raise ReaperError("RUNTIME_REAPER_LOCK_INVALID")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                while True:
                    engine_environment, engine_context_sha256 = _engine_environment(root, engine)
                    result = sweep(root, repository_root, engine, engine_environment)
                    _write_heartbeat(root, result, engine_context_sha256)
                    print(json.dumps(result, sort_keys=True), flush=True)
                    if args.once:
                        return 2 if result["status"] == "BLOCKED" else 0
                    time.sleep(args.interval_seconds)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    except (BlockingIOError, OSError, ReaperError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
