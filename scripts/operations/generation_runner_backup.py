#!/usr/bin/env python3
"""Offline, content-addressed backup and restore for the local generation runner."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, BinaryIO, Iterator
import uuid
import zipfile


SCHEMA_VERSION = "elmos.generation-runner-backup.v1"
MAINTENANCE_FILE = ".maintenance.json"
ACTIVE_JOB_STATES = {"QUEUED", "ANALYZING", "GENERATING", "VERIFYING", "ARCHIVING"}
ACTIVE_RUNTIME_STATES = {"STARTING", "RUNNING"}
TERMINAL_JOB_STATES = {"COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED"}
FIXED_ZIP_TIME = (2024, 1, 1, 0, 0, 0)


class BackupError(RuntimeError):
    pass


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_root(raw: str, *, must_exist: bool) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise BackupError("ROOT_MUST_BE_ABSOLUTE")
    resolved = candidate.resolve(strict=must_exist)
    if resolved == Path(resolved.anchor):
        raise BackupError("ROOT_PATH_UNSAFE")
    if must_exist and (not resolved.is_dir() or resolved.is_symlink()):
        raise BackupError("ROOT_NOT_A_DIRECTORY")
    return resolved


def confined_directory(root: Path, destination: Path, *, create: bool) -> Path:
    try:
        relative = destination.relative_to(root)
    except ValueError as error:
        raise BackupError("PATH_CONFINEMENT_FAILED") from error
    current = root
    root_resolved = root.resolve(strict=True)
    root_device = os.lstat(root).st_dev
    for part in relative.parts:
        current = current / part
        if not current.exists():
            if not create:
                raise BackupError("DIRECTORY_MISSING")
            os.mkdir(current, 0o700)
            fsync_directory(current.parent)
        info = os.lstat(current)
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_dev != root_device
        ):
            raise BackupError("DIRECTORY_PATH_UNSAFE")
        resolved = current.resolve(strict=True)
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise BackupError("PATH_CONFINEMENT_FAILED")
    return current


def maintenance(root: Path) -> dict[str, Any]:
    path = root / MAINTENANCE_FILE
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise BackupError("RUNNER_NOT_QUIESCED")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackupError("RUNNER_NOT_QUIESCED") from error
    if (
        not isinstance(value, dict)
        or value.get("status") not in {"QUIESCED", "RESTORED_REQUIRES_RESUME"}
        or not isinstance(value.get("actor"), str)
    ):
        raise BackupError("MAINTENANCE_RECORD_INVALID")
    return value


def quiesce(root: Path, actor: str) -> dict[str, Any]:
    if not actor or len(actor) > 200:
        raise BackupError("ACTOR_INVALID")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {
        "schema_version": SCHEMA_VERSION,
        "status": "QUIESCED",
        "actor": actor,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    marker = root / MAINTENANCE_FILE
    if marker.exists():
        raise BackupError("RUNNER_ALREADY_QUIESCED")
    atomic_json(marker, record)
    return record


def resume(root: Path, actor: str) -> dict[str, Any]:
    record = maintenance(root)
    if record["actor"] != actor:
        raise BackupError("ACTOR_NOT_BOUND_TO_MAINTENANCE_RECORD")
    tenants = root / "tenants"
    if tenants.exists():
        if tenants.is_symlink() or not tenants.is_dir():
            raise BackupError("TENANTS_ROOT_UNSAFE")
        for tenant_root in sorted(tenants.iterdir(), key=lambda item: item.name):
            tenant = tenant_root.name
            if (
                tenant_root.is_symlink()
                or not tenant_root.is_dir()
                or not tenant
                or len(tenant) > 63
                or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in tenant)
            ):
                raise BackupError("TENANT_INVALID")
            if _pending_gc_trash(root, tenant, actor) or _pending_gc_audits(root, tenant, actor):
                raise BackupError("GC_RECOVERY_REQUIRED_BEFORE_RESUME")
    (root / MAINTENANCE_FILE).unlink()
    fsync_directory(root)
    return {"status": "RESUMED", "actor": actor}


def ensure_inactive(root: Path) -> None:
    tenants = root / "tenants"
    if not tenants.exists():
        return
    for job_file in tenants.glob("*/jobs/*/job.json"):
        if job_file.is_symlink():
            raise BackupError("SYMLINK_FORBIDDEN")
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BackupError(f"JOB_RECORD_INVALID:{job_file.relative_to(root)}") from error
        runtime = job.get("runtime") if isinstance(job, dict) else None
        runtime_status = runtime.get("status") if isinstance(runtime, dict) else None
        if job.get("status") in ACTIVE_JOB_STATES or runtime_status in ACTIVE_RUNTIME_STATES:
            raise BackupError(f"RUNNER_NOT_DRAINED:{job_file.relative_to(root)}")


def ensure_no_active_durable_leases(root: Path) -> None:
    leases = root / ".durable-queue" / "leases"
    if not leases.exists():
        return
    now = datetime.now(timezone.utc)
    for lease_file in leases.glob("*/*/*.json"):
        if lease_file.is_symlink() or not lease_file.is_file():
            raise BackupError("DURABLE_LEASE_PATH_UNSAFE")
        try:
            lease = json.loads(lease_file.read_text(encoding="utf-8"))
            expires = datetime.fromisoformat(str(lease["expiresAt"]).replace("Z", "+00:00"))
        except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise BackupError("DURABLE_LEASE_RECORD_INVALID") from error
        if expires.tzinfo is None:
            raise BackupError("DURABLE_LEASE_RECORD_INVALID")
        if expires > now:
            raise BackupError(f"DURABLE_LEASE_ACTIVE:{lease_file.relative_to(root)}")


def payload_files(root: Path) -> list[Path]:
    tenants = root / "tenants"
    if not tenants.exists():
        return []
    confined_directory(root, tenants, create=False)
    files: list[Path] = []
    for current, directories, names in os.walk(tenants, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            if (current_path / directory).is_symlink():
                raise BackupError("SYMLINK_FORBIDDEN")
        for name in names:
            file_path = current_path / name
            if file_path.is_symlink() or not file_path.is_file():
                raise BackupError("NON_REGULAR_FILE_FORBIDDEN")
            files.append(file_path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def safe_archive_path(raw: str) -> PurePosixPath:
    value = PurePosixPath(raw)
    if (
        value.is_absolute()
        or ".." in value.parts
        or not value.parts
        or value.as_posix() != raw
        or len(raw) > 4_096
        or any(character in raw for character in ("\0", "\r", "\n"))
    ):
        raise BackupError("ARCHIVE_PATH_UNSAFE")
    return value


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def backup(root: Path, output: Path, actor: str) -> dict[str, Any]:
    record = maintenance(root)
    if record["actor"] != actor:
        raise BackupError("ACTOR_NOT_BOUND_TO_MAINTENANCE_RECORD")
    ensure_inactive(root)
    ensure_no_active_durable_leases(root)
    output = output.expanduser().resolve(strict=False)
    if output == root or root in output.parents:
        raise BackupError("BACKUP_DESTINATION_INSIDE_RUNNER_ROOT")
    output.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    files = payload_files(root)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for file_path in files:
                relative = file_path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(f"payload/{relative}", FIXED_ZIP_TIME)
                mode = stat.S_IMODE(file_path.stat().st_mode) & 0o777
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with file_path.open("rb") as source, archive.open(info, "w") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                entries.append(
                    {
                        "path": relative,
                        "sha256": sha256_file(file_path),
                        "size": file_path.stat().st_size,
                        "mode": f"{mode:04o}",
                    }
                )
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "created_by": actor,
                "maintenance_created_at": record.get("created_at"),
                "entry_count": len(entries),
                "entries": entries,
            }
            manifest_info = zipfile.ZipInfo("MANIFEST.json", FIXED_ZIP_TIME)
            manifest_info.external_attr = (stat.S_IFREG | 0o600) << 16
            manifest_info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(
                manifest_info,
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags)
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, output)
        fsync_directory(output.parent)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "status": "BACKUP_CREATED",
        "archive": str(output),
        "sha256": sha256_file(output),
        "entry_count": len(entries),
        "bytes": output.stat().st_size,
    }


def _sha256_handle(handle: BinaryIO) -> str:
    handle.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


@contextmanager
def _verified_archive(
    archive_path: Path,
) -> Iterator[tuple[Path, zipfile.ZipFile, dict[str, Any], str]]:
    candidate = archive_path.expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        raise BackupError("BACKUP_ARCHIVE_INVALID")
    resolved = candidate.resolve(strict=True)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(resolved, flags)
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
            raise BackupError("BACKUP_ARCHIVE_INVALID")
        archive_sha256 = _sha256_handle(handle)
        with zipfile.ZipFile(handle, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "MANIFEST.json" not in names:
                raise BackupError("BACKUP_ARCHIVE_STRUCTURE_INVALID")
            try:
                manifest = json.loads(archive.read("MANIFEST.json"))
            except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
                raise BackupError("BACKUP_MANIFEST_INVALID") from error
            if (
                not isinstance(manifest, dict)
                or set(manifest) != {
                    "schema_version",
                    "created_by",
                    "maintenance_created_at",
                    "entry_count",
                    "entries",
                }
                or manifest.get("schema_version") != SCHEMA_VERSION
                or not isinstance(manifest.get("created_by"), str)
                or not 1 <= len(manifest["created_by"]) <= 200
                or not valid_timestamp(manifest.get("maintenance_created_at"))
                or not isinstance(manifest.get("entries"), list)
                or not isinstance(manifest.get("entry_count"), int)
                or isinstance(manifest.get("entry_count"), bool)
                or manifest["entry_count"] < 0
                or manifest.get("entry_count") != len(manifest["entries"])
            ):
                raise BackupError("BACKUP_MANIFEST_INVALID")
            expected_names = {"MANIFEST.json"}
            logical_paths: set[str] = set()
            for entry in manifest["entries"]:
                if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size", "mode"}:
                    raise BackupError("BACKUP_MANIFEST_ENTRY_INVALID")
                raw_path = entry.get("path")
                entry_digest = entry.get("sha256")
                entry_size = entry.get("size")
                entry_mode = entry.get("mode")
                if (
                    not isinstance(raw_path, str)
                    or not isinstance(entry_digest, str)
                    or len(entry_digest) != 64
                    or any(character not in "0123456789abcdef" for character in entry_digest)
                    or not isinstance(entry_size, int)
                    or isinstance(entry_size, bool)
                    or entry_size < 0
                    or entry_size > 1024 * 1024 * 1024 * 1024
                    or not isinstance(entry_mode, str)
                    or len(entry_mode) != 4
                    or entry_mode[0] != "0"
                    or any(character not in "01234567" for character in entry_mode)
                ):
                    raise BackupError("BACKUP_MANIFEST_ENTRY_INVALID")
                relative = safe_archive_path(raw_path)
                logical = relative.as_posix()
                if logical in logical_paths:
                    raise BackupError("BACKUP_MANIFEST_ENTRY_INVALID")
                logical_paths.add(logical)
                member = f"payload/{logical}"
                expected_names.add(member)
                try:
                    info = archive.getinfo(member)
                except KeyError as error:
                    raise BackupError("BACKUP_PAYLOAD_MISSING") from error
                digest = hashlib.sha256()
                size = 0
                with archive.open(info, "r") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                        size += len(chunk)
                if digest.hexdigest() != entry_digest or size != entry_size:
                    raise BackupError("BACKUP_PAYLOAD_DIGEST_MISMATCH")
            if set(names) != expected_names:
                raise BackupError("BACKUP_ARCHIVE_UNDECLARED_ENTRY")
            after = os.fstat(handle.fileno())
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            ):
                raise BackupError("BACKUP_ARCHIVE_CHANGED_DURING_VERIFICATION")
            yield resolved, archive, manifest, archive_sha256


def verify(archive_path: Path) -> dict[str, Any]:
    with _verified_archive(archive_path) as (resolved, _archive, manifest, archive_sha256):
        result = {
            "status": "BACKUP_VERIFIED",
            "archive": str(resolved),
            "sha256": archive_sha256,
            "entry_count": manifest["entry_count"],
        }
    return result


def restore(archive_path: Path, destination: Path, actor: str) -> dict[str, Any]:
    destination = canonical_root(str(destination), must_exist=False)
    if destination.exists():
        raise BackupError("RESTORE_DESTINATION_MUST_NOT_EXIST")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.restore-", dir=destination.parent)
    )
    verification: dict[str, Any]
    try:
        with _verified_archive(archive_path) as (resolved, archive, manifest, archive_sha256):
            verification = {
                "status": "BACKUP_VERIFIED",
                "archive": str(resolved),
                "sha256": archive_sha256,
                "entry_count": manifest["entry_count"],
            }
            for entry in manifest["entries"]:
                relative = safe_archive_path(entry["path"])
                target = temporary.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.open(f"payload/{relative.as_posix()}", "r") as source:
                    with target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                mode = int(entry["mode"], 8) & 0o777
                os.chmod(target, mode)
                if sha256_file(target) != entry["sha256"]:
                    raise BackupError("RESTORED_PAYLOAD_DIGEST_MISMATCH")
        atomic_json(
            temporary / MAINTENANCE_FILE,
            {
                "schema_version": SCHEMA_VERSION,
                "status": "RESTORED_REQUIRES_RESUME",
                "actor": actor,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_archive_sha256": verification["sha256"],
            },
        )
        os.replace(temporary, destination)
        fsync_directory(destination.parent)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "status": "RESTORED_REQUIRES_RESUME",
        "destination": str(destination),
        "archive_sha256": verification["sha256"],
        "entry_count": verification["entry_count"],
    }


def _safe_job_id(raw: str) -> str:
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError) as error:
        raise BackupError("JOB_ID_INVALID") from error
    if str(parsed) != raw.lower():
        raise BackupError("JOB_ID_INVALID")
    return str(parsed)


def _safe_job_files(job_root: Path) -> list[Path]:
    files: list[Path] = []
    root_device = os.lstat(job_root).st_dev
    for current, directories, names in os.walk(job_root, followlinks=False):
        current_path = Path(current)
        current_info = os.lstat(current_path)
        if current_info.st_dev != root_device or not stat.S_ISDIR(current_info.st_mode):
            raise BackupError("JOB_TREE_FILESYSTEM_BOUNDARY_INVALID")
        for directory in directories:
            candidate = current_path / directory
            candidate_info = os.lstat(candidate)
            if (
                stat.S_ISLNK(candidate_info.st_mode)
                or not stat.S_ISDIR(candidate_info.st_mode)
                or candidate_info.st_dev != root_device
            ):
                raise BackupError("SYMLINK_FORBIDDEN")
        for name in names:
            candidate = current_path / name
            candidate_info = os.lstat(candidate)
            if (
                stat.S_ISLNK(candidate_info.st_mode)
                or not stat.S_ISREG(candidate_info.st_mode)
                or candidate_info.st_dev != root_device
                or candidate_info.st_nlink != 1
            ):
                raise BackupError("NON_REGULAR_FILE_FORBIDDEN")
            files.append(candidate)
            if len(files) > 250_000:
                raise BackupError("JOB_FILE_COUNT_LIMIT")
    return sorted(files, key=lambda item: item.relative_to(job_root).as_posix())


def _backup_entries(
    archive_path: Path,
) -> tuple[dict[str, dict[str, Any]], str, dict[str, Any]]:
    with _verified_archive(archive_path) as (_resolved, _archive, manifest, archive_sha256):
        return (
            {entry["path"]: entry for entry in manifest["entries"]},
            archive_sha256,
            manifest,
        )


def _assert_backup_identity(archive_path: Path, expected_sha256: str) -> None:
    if verify(archive_path).get("sha256") != expected_sha256:
        raise BackupError("GC_BACKUP_IDENTITY_CHANGED")


def _bind_candidate_to_backup(
    root: Path,
    files: list[Path],
    entries: dict[str, dict[str, Any]],
    *,
    physical_root: Path | None = None,
    logical_root: PurePosixPath | None = None,
) -> None:
    if (physical_root is None) != (logical_root is None):
        raise BackupError("GC_BACKUP_BINDING_ROOT_INVALID")
    for source in files:
        relative = (
            (logical_root / source.relative_to(physical_root).as_posix()).as_posix()
            if physical_root is not None and logical_root is not None
            else source.relative_to(root).as_posix()
        )
        expected = entries.get(relative)
        if (
            expected is None
            or expected.get("size") != source.stat().st_size
            or expected.get("sha256") != sha256_file(source)
        ):
            raise BackupError(f"GC_BACKUP_BINDING_MISMATCH:{relative}")


def _bind_gc_audit_to_backup(
    audit: dict[str, Any],
    entries: dict[str, dict[str, Any]],
) -> None:
    original = str(audit["original_path"])
    prefix = f"{original}/"
    bound = [entry for path, entry in entries.items() if path.startswith(prefix)]
    job_record = entries.get(f"{original}/job.json")
    if (
        len(bound) != audit["backup_file_count"]
        or sum(int(entry["size"]) for entry in bound) != audit["backup_bytes"]
        or job_record is None
        or job_record.get("sha256") != audit["job_record_sha256"]
    ):
        raise BackupError("GC_AUDIT_BACKUP_BINDING_MISMATCH")


def _backup_job_statistics(
    original_path: str,
    entries: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    prefix = f"{original_path}/"
    bound = [entry for path, entry in entries.items() if path.startswith(prefix)]
    if not bound or f"{original_path}/job.json" not in entries:
        raise BackupError("GC_BACKUP_JOB_INCOMPLETE")
    return len(bound), sum(int(entry["size"]) for entry in bound)


def _gc_audit_statistics_valid(audit: dict[str, Any]) -> bool:
    values = {
        name: audit.get(name)
        for name in (
            "bytes",
            "file_count",
            "backup_bytes",
            "backup_file_count",
            "trash_bytes",
            "trash_file_count",
        )
    }
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values.values()):
        return False
    if (
        values["bytes"] < 0
        or values["file_count"] < 1
        or values["backup_bytes"] < 0
        or values["backup_file_count"] < 1
        or values["trash_bytes"] < 0
        or values["trash_file_count"] < 1
    ):
        return False
    return (
        values["bytes"] == values["backup_bytes"]
        and values["file_count"] == values["backup_file_count"]
        and values["backup_bytes"] >= values["trash_bytes"]
        and values["backup_file_count"] >= values["trash_file_count"]
    )


def _cleanup_rootless_runtime(
    job: dict[str, Any],
    job_root: Path,
    repository_root: Path | None,
    engine: Path | None,
) -> dict[str, Any] | None:
    runtime = job.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("executor") != "ROOTLESS_CONTAINER":
        return None
    if repository_root is None or engine is None:
        raise BackupError("ROOTLESS_GC_REQUIRES_REPOSITORY_ROOT_AND_ENGINE")
    language = runtime.get("language")
    lease_id = runtime.get("leaseId")
    if not isinstance(language, str) or not isinstance(lease_id, str):
        raise BackupError("ROOTLESS_GC_IDENTITY_MISSING")
    helper = repository_root / "scripts" / "operations" / "rootless_project_runner.py"
    if not helper.is_file() or helper.is_symlink() or not engine.is_file() or engine.is_symlink():
        raise BackupError("ROOTLESS_GC_EXECUTION_ASSET_INVALID")
    command = [
        sys.executable,
        str(helper),
        "stop",
        "--engine",
        str(engine),
        "--language",
        language,
        "--job-id",
        str(job.get("id", "")),
        "--state",
        str(job_root / "runtime-state"),
        "--lease-id",
        lease_id,
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=90)
        receipt = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise BackupError("ROOTLESS_GC_CLEANUP_FAILED") from error
    if result.returncode != 0 or receipt.get("status") not in {"STOPPED", "MISSING"}:
        raise BackupError(f"ROOTLESS_GC_CLEANUP_UNVERIFIED:{receipt.get('status', 'UNKNOWN')}")
    if (
        receipt.get("job_id") != job.get("id")
        or receipt.get("language") != language
        or receipt.get("requested_lease_id") != lease_id
    ):
        raise BackupError("ROOTLESS_GC_CLEANUP_RECEIPT_IDENTITY_INVALID")
    receipt["helper_sha256"] = sha256_file(helper)
    receipt["engine_sha256"] = sha256_file(engine)
    return receipt


def _gc_candidates(root: Path, tenant: str, maximum: int) -> list[dict[str, Any]]:
    if not tenant or len(tenant) > 63 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in tenant):
        raise BackupError("TENANT_INVALID")
    jobs_root = root / "tenants" / tenant / "jobs"
    if not jobs_root.exists():
        return []
    confined_directory(root, jobs_root, create=False)
    jobs_device = os.lstat(jobs_root).st_dev
    now = datetime.now(timezone.utc)
    candidates: list[dict[str, Any]] = []
    for job_root in sorted(jobs_root.iterdir(), key=lambda item: item.name):
        if (
            job_root.is_symlink()
            or not job_root.is_dir()
            or os.lstat(job_root).st_dev != jobs_device
        ):
            raise BackupError("JOB_PATH_UNSAFE")
        job_id = _safe_job_id(job_root.name)
        try:
            job = json.loads((job_root / "job.json").read_text(encoding="utf-8"))
            expires = datetime.fromisoformat(
                str(job["retentionExpiresAt"]).replace("Z", "+00:00")
            )
        except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise BackupError(f"GC_JOB_RECORD_INVALID:{job_id}") from error
        runtime = job.get("runtime") if isinstance(job, dict) else None
        publication = job.get("githubPublication") if isinstance(job, dict) else None
        publication_reason = publication.get("reason") if isinstance(publication, dict) else None
        if (
            job.get("id") != job_id
            or job.get("tenantId") != tenant
            or job.get("status") not in TERMINAL_JOB_STATES
            or job.get("legalHold") is not False
            or job.get("retentionPolicyVersion") != "generation-storage-v1"
            or not isinstance(runtime, dict)
            or runtime.get("status") != "STOPPED"
            or expires.tzinfo is None
            or expires > now
            or (isinstance(publication, dict) and publication.get("status") == "CREATING")
            or (isinstance(publication_reason, str) and (
                "RECONCILIATION_REQUIRED" in publication_reason
                or "MANUAL_CLEANUP_REQUIRED" in publication_reason
            ))
        ):
            continue
        files = _safe_job_files(job_root)
        candidates.append(
            {
                "job": job,
                "root": job_root,
                "files": files,
                "bytes": sum(item.stat().st_size for item in files),
            }
        )
        if len(candidates) >= maximum:
            break
    return candidates


def _pending_gc_trash(root: Path, tenant: str, actor: str) -> list[dict[str, Any]]:
    audit_root = root / "tenants" / tenant / "storage-gc" / "audit"
    trash_root = root / "tenants" / tenant / "storage-trash" / "jobs"
    if not trash_root.exists():
        return []
    confined_directory(root, trash_root, create=False)
    confined_directory(root, audit_root, create=False)
    pending: list[dict[str, Any]] = []
    for trash in sorted(trash_root.iterdir(), key=lambda item: item.name):
        if trash.is_symlink() or not trash.is_dir() or len(trash.name) != 73 or trash.name[36] != "-":
            raise BackupError("GC_TRASH_ENTRY_INVALID")
        job_id = _safe_job_id(trash.name[:36])
        deletion_id = _safe_job_id(trash.name[37:])
        audit_path = audit_root / f"{deletion_id}.json"
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BackupError("GC_TRASH_AUDIT_MISSING") from error
        if not isinstance(audit, dict):
            raise BackupError("GC_TRASH_AUDIT_INVALID")
        if (
            audit.get("schema_version") != "elmos.generation-storage-gc.v1"
            or audit.get("tenant_id") != tenant
            or audit.get("job_id") != job_id
            or audit.get("actor") != actor
            or audit.get("status") not in {"PREPARED", "MOVED_TO_TRASH"}
            or not isinstance(audit.get("job_record_sha256"), str)
            or len(audit["job_record_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in audit["job_record_sha256"])
            or audit.get("original_path") != f"tenants/{tenant}/jobs/{job_id}"
            or audit.get("trash_path") != trash.relative_to(root).as_posix()
            or not isinstance(audit.get("backup_sha256"), str)
            or len(audit["backup_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in audit["backup_sha256"])
            or not isinstance(audit.get("maintenance_created_at"), str)
            or not _gc_audit_statistics_valid(audit)
        ):
            raise BackupError("GC_TRASH_AUDIT_INVALID")
        files = _safe_job_files(trash)
        if (
            sha256_file(trash / "job.json") != audit["job_record_sha256"]
            or len(files) != audit["trash_file_count"]
            or sum(item.stat().st_size for item in files) != audit["trash_bytes"]
        ):
            raise BackupError("GC_TRASH_JOB_DIGEST_MISMATCH")
        pending.append(
            {
                "job_id": job_id,
                "root": trash,
                "files": files,
                "logical_root": PurePosixPath(audit["original_path"]),
                "audit": audit,
                "audit_path": audit_path,
            }
        )
    return pending


def _pending_gc_audits(root: Path, tenant: str, actor: str) -> list[dict[str, Any]]:
    audit_root = root / "tenants" / tenant / "storage-gc" / "audit"
    trash_root = root / "tenants" / tenant / "storage-trash" / "jobs"
    jobs_root = root / "tenants" / tenant / "jobs"
    if not audit_root.exists():
        return []
    confined_directory(root, audit_root, create=False)
    if trash_root.exists():
        confined_directory(root, trash_root, create=False)
    pending: list[dict[str, Any]] = []
    for audit_path in sorted(audit_root.iterdir(), key=lambda item: item.name):
        if (
            audit_path.is_symlink()
            or not audit_path.is_file()
            or audit_path.stat().st_size > 64 * 1024
            or not audit_path.name.endswith(".json")
        ):
            raise BackupError("GC_AUDIT_PATH_INVALID")
        deletion_id = _safe_job_id(audit_path.stem)
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BackupError("GC_AUDIT_INVALID") from error
        if not isinstance(audit, dict):
            raise BackupError("GC_AUDIT_INVALID")
        status_value = audit.get("status")
        job_id = _safe_job_id(str(audit.get("job_id", "")))
        expected_original = f"tenants/{tenant}/jobs/{job_id}"
        expected_trash = f"tenants/{tenant}/storage-trash/jobs/{job_id}-{deletion_id}"
        if (
            audit.get("schema_version") != "elmos.generation-storage-gc.v1"
            or audit.get("tenant_id") != tenant
            or audit.get("actor") != actor
            or status_value not in {
                "PREPARED",
                "MOVED_TO_TRASH",
                "VERIFIED_PURGED",
                "ABORTED_BEFORE_MOVE",
            }
            or audit.get("original_path") != expected_original
            or audit.get("trash_path") != expected_trash
            or not isinstance(audit.get("job_record_sha256"), str)
            or len(audit["job_record_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in audit["job_record_sha256"])
            or not isinstance(audit.get("backup_sha256"), str)
            or len(audit["backup_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in audit["backup_sha256"])
            or not isinstance(audit.get("maintenance_created_at"), str)
            or not _gc_audit_statistics_valid(audit)
        ):
            raise BackupError("GC_AUDIT_INVALID")
        if status_value in {"VERIFIED_PURGED", "ABORTED_BEFORE_MOVE"}:
            continue
        trash = trash_root / f"{job_id}-{deletion_id}"
        if trash.exists():
            continue
        job_root = jobs_root / job_id
        if status_value == "PREPARED" and job_root.is_dir() and not job_root.is_symlink():
            recovery = "ABORTED_BEFORE_MOVE"
        elif status_value == "MOVED_TO_TRASH" and not job_root.exists():
            recovery = "PURGED_PENDING_RECEIPT"
        else:
            raise BackupError("GC_AUDIT_STATE_DIVERGED")
        pending.append(
            {
                "job_id": job_id,
                "audit": audit,
                "audit_path": audit_path,
                "recovery": recovery,
            }
        )
    return pending


def garbage_collect(
    root: Path,
    tenant: str,
    actor: str,
    maximum: int,
    *,
    apply: bool,
    backup_archive: Path | None = None,
    repository_root: Path | None = None,
    engine: Path | None = None,
) -> dict[str, Any]:
    record = maintenance(root)
    if record["actor"] != actor:
        raise BackupError("ACTOR_NOT_BOUND_TO_MAINTENANCE_RECORD")
    if maximum < 1 or maximum > 100:
        raise BackupError("GC_MAX_JOBS_INVALID")
    ensure_inactive(root)
    ensure_no_active_durable_leases(root)
    pending_trash = _pending_gc_trash(root, tenant, actor)
    pending_audits = _pending_gc_audits(root, tenant, actor)
    candidates = _gc_candidates(root, tenant, maximum)
    public_candidates = [
        {
            "job_id": candidate["job"]["id"],
            "retention_expires_at": candidate["job"]["retentionExpiresAt"],
            "bytes": candidate["bytes"],
            "artifact_sha256": candidate["job"].get("artifactSha256"),
        }
        for candidate in candidates
    ]
    if not apply:
        return {
            "status": "GC_PLAN_RECOVERY_REQUIRED" if pending_trash or pending_audits else "GC_PLAN_READY",
            "tenant": tenant,
            "pending_recovery_job_ids": sorted(
                {item["job_id"] for item in [*pending_trash, *pending_audits]}
            ),
            "candidate_count": len(candidates),
            "bytes": sum(candidate["bytes"] for candidate in candidates),
            "candidates": public_candidates,
        }
    if backup_archive is None:
        raise BackupError("GC_BACKUP_ARCHIVE_REQUIRED")
    backup_entries, backup_sha256, backup_manifest = _backup_entries(backup_archive)
    if (
        backup_manifest.get("created_by") != actor
        or backup_manifest.get("maintenance_created_at") != record.get("created_at")
    ):
        raise BackupError("GC_BACKUP_MAINTENANCE_BINDING_MISMATCH")
    audit_root = root / "tenants" / tenant / "storage-gc" / "audit"
    trash_root = root / "tenants" / tenant / "storage-trash" / "jobs"
    confined_directory(root, audit_root, create=True)
    confined_directory(root, trash_root, create=True)
    deleted: list[str] = []
    deleted_bytes = 0
    for pending in pending_trash:
        _assert_backup_identity(backup_archive, backup_sha256)
        if pending["audit"]["backup_sha256"] != backup_sha256:
            raise BackupError("GC_RECOVERY_BACKUP_MISMATCH")
        if pending["audit"].get("maintenance_created_at") != record.get("created_at"):
            raise BackupError("GC_RECOVERY_MAINTENANCE_MISMATCH")
        _bind_gc_audit_to_backup(pending["audit"], backup_entries)
        _bind_candidate_to_backup(
            root,
            pending["files"],
            backup_entries,
            physical_root=pending["root"],
            logical_root=pending["logical_root"],
        )
        shutil.rmtree(pending["root"])
        if pending["root"].exists():
            raise BackupError("GC_PURGE_POSTCONDITION_FAILED")
        audit = pending["audit"]
        audit["status"] = "VERIFIED_PURGED"
        audit["purged_at"] = datetime.now(timezone.utc).isoformat()
        audit["recovered_after_interruption"] = True
        atomic_json(pending["audit_path"], audit)
        deleted.append(pending["job_id"])
        deleted_bytes += audit["backup_bytes"]
    for pending in pending_audits:
        audit = pending["audit"]
        if audit["backup_sha256"] != backup_sha256:
            raise BackupError("GC_RECOVERY_BACKUP_MISMATCH")
        if audit.get("maintenance_created_at") != record.get("created_at"):
            raise BackupError("GC_RECOVERY_MAINTENANCE_MISMATCH")
        _bind_gc_audit_to_backup(audit, backup_entries)
        if pending["recovery"] == "ABORTED_BEFORE_MOVE":
            audit["status"] = "ABORTED_BEFORE_MOVE"
            audit["aborted_at"] = datetime.now(timezone.utc).isoformat()
        else:
            _assert_backup_identity(backup_archive, backup_sha256)
            audit["status"] = "VERIFIED_PURGED"
            audit["purged_at"] = datetime.now(timezone.utc).isoformat()
            audit["recovered_after_interruption"] = True
            deleted.append(pending["job_id"])
            deleted_bytes += audit["backup_bytes"]
        atomic_json(pending["audit_path"], audit)
    for candidate in candidates:
        _assert_backup_identity(backup_archive, backup_sha256)
        job = candidate["job"]
        job_root = candidate["root"]
        _bind_candidate_to_backup(root, candidate["files"], backup_entries)
        cleanup_receipt = _cleanup_rootless_runtime(
            job, job_root, repository_root, engine
        )
        if (job_root / "runtime-state").exists():
            raise BackupError("GC_RUNTIME_STATE_CLEANUP_REQUIRED")
        trash_files = _safe_job_files(job_root)
        _bind_candidate_to_backup(root, trash_files, backup_entries)
        original_path = job_root.relative_to(root).as_posix()
        backup_file_count, backup_bytes = _backup_job_statistics(
            original_path, backup_entries
        )
        trash_bytes = sum(item.stat().st_size for item in trash_files)
        deletion_id = str(uuid.uuid4())
        audit_path = audit_root / f"{deletion_id}.json"
        trash = trash_root / f"{job['id']}-{deletion_id}"
        audit = {
            "schema_version": "elmos.generation-storage-gc.v1",
            "status": "PREPARED",
            "tenant_id": tenant,
            "job_id": job["id"],
            "actor": actor,
            "job_record_sha256": sha256_file(job_root / "job.json"),
            "backup_sha256": backup_sha256,
            "maintenance_created_at": record.get("created_at"),
            "bytes": backup_bytes,
            "file_count": backup_file_count,
            "backup_bytes": backup_bytes,
            "backup_file_count": backup_file_count,
            "trash_bytes": trash_bytes,
            "trash_file_count": len(trash_files),
            "original_path": original_path,
            "trash_path": trash.relative_to(root).as_posix(),
            "rootless_cleanup_receipt": cleanup_receipt,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(audit_path, audit)
        os.replace(job_root, trash)
        fsync_directory(job_root.parent)
        fsync_directory(trash.parent)
        audit["status"] = "MOVED_TO_TRASH"
        audit["moved_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(audit_path, audit)
        shutil.rmtree(trash)
        fsync_directory(trash.parent)
        if job_root.exists() or trash.exists():
            raise BackupError("GC_PURGE_POSTCONDITION_FAILED")
        audit["status"] = "VERIFIED_PURGED"
        audit["purged_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(audit_path, audit)
        deleted.append(job["id"])
        deleted_bytes += backup_bytes
    _assert_backup_identity(backup_archive, backup_sha256)
    return {
        "status": "GC_VERIFIED_PURGED",
        "tenant": tenant,
        "deleted_count": len(deleted),
        "deleted_job_ids": deleted,
        "bytes": deleted_bytes,
        "backup_sha256": backup_sha256,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("quiesce", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--root", required=True)
        command.add_argument("--actor", required=True)
    create = commands.add_parser("backup")
    create.add_argument("--root", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--actor", required=True)
    check = commands.add_parser("verify")
    check.add_argument("--archive", required=True)
    recover = commands.add_parser("restore")
    recover.add_argument("--archive", required=True)
    recover.add_argument("--destination", required=True)
    recover.add_argument("--actor", required=True)
    gc = commands.add_parser("gc")
    gc.add_argument("--root", required=True)
    gc.add_argument("--tenant", required=True)
    gc.add_argument("--actor", required=True)
    gc.add_argument("--max-jobs", type=int, default=25)
    gc.add_argument("--apply", action="store_true")
    gc.add_argument("--backup-archive")
    gc.add_argument("--repository-root")
    gc.add_argument("--engine")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "quiesce":
            result = quiesce(canonical_root(args.root, must_exist=False), args.actor)
        elif args.command == "resume":
            result = resume(canonical_root(args.root, must_exist=True), args.actor)
        elif args.command == "backup":
            result = backup(
                canonical_root(args.root, must_exist=True),
                Path(args.output),
                args.actor,
            )
        elif args.command == "verify":
            result = verify(Path(args.archive))
        elif args.command == "restore":
            result = restore(Path(args.archive), Path(args.destination), args.actor)
        else:
            result = garbage_collect(
                canonical_root(args.root, must_exist=True),
                args.tenant,
                args.actor,
                args.max_jobs,
                apply=args.apply,
                backup_archive=Path(args.backup_archive) if args.backup_archive else None,
                repository_root=(
                    canonical_root(args.repository_root, must_exist=True)
                    if args.repository_root
                    else None
                ),
                engine=Path(args.engine).resolve(strict=True) if args.engine else None,
            )
    except (BackupError, OSError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
