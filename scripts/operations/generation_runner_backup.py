#!/usr/bin/env python3
"""Offline, content-addressed backup and restore for the local generation runner."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from typing import Any
import zipfile


SCHEMA_VERSION = "elmos.generation-runner-backup.v1"
MAINTENANCE_FILE = ".maintenance.json"
ACTIVE_JOB_STATES = {"QUEUED", "ANALYZING", "GENERATING", "VERIFYING", "ARCHIVING"}
ACTIVE_RUNTIME_STATES = {"STARTING", "RUNNING"}
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


def maintenance(root: Path) -> dict[str, Any]:
    path = root / MAINTENANCE_FILE
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
    (root / MAINTENANCE_FILE).unlink()
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


def payload_files(root: Path) -> list[Path]:
    tenants = root / "tenants"
    if not tenants.exists():
        return []
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
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise BackupError("ARCHIVE_PATH_UNSAFE")
    return value


def backup(root: Path, output: Path, actor: str) -> dict[str, Any]:
    record = maintenance(root)
    if record["actor"] != actor:
        raise BackupError("ACTOR_NOT_BOUND_TO_MAINTENANCE_RECORD")
    ensure_inactive(root)
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
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
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


def verify(archive_path: Path) -> dict[str, Any]:
    archive_path = archive_path.expanduser().resolve(strict=True)
    if not archive_path.is_file() or archive_path.is_symlink():
        raise BackupError("BACKUP_ARCHIVE_INVALID")
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "MANIFEST.json" not in names:
            raise BackupError("BACKUP_ARCHIVE_STRUCTURE_INVALID")
        try:
            manifest = json.loads(archive.read("MANIFEST.json"))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BackupError("BACKUP_MANIFEST_INVALID") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != SCHEMA_VERSION
            or not isinstance(manifest.get("entries"), list)
            or manifest.get("entry_count") != len(manifest["entries"])
        ):
            raise BackupError("BACKUP_MANIFEST_INVALID")
        expected_names = {"MANIFEST.json"}
        for entry in manifest["entries"]:
            if not isinstance(entry, dict):
                raise BackupError("BACKUP_MANIFEST_ENTRY_INVALID")
            relative = safe_archive_path(str(entry.get("path", "")))
            member = f"payload/{relative.as_posix()}"
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
            if (
                digest.hexdigest() != entry.get("sha256")
                or size != entry.get("size")
            ):
                raise BackupError("BACKUP_PAYLOAD_DIGEST_MISMATCH")
        if set(names) != expected_names:
            raise BackupError("BACKUP_ARCHIVE_UNDECLARED_ENTRY")
    return {
        "status": "BACKUP_VERIFIED",
        "archive": str(archive_path),
        "sha256": sha256_file(archive_path),
        "entry_count": manifest["entry_count"],
    }


def restore(archive_path: Path, destination: Path, actor: str) -> dict[str, Any]:
    verification = verify(archive_path)
    destination = canonical_root(str(destination), must_exist=False)
    if destination.exists():
        raise BackupError("RESTORE_DESTINATION_MUST_NOT_EXIST")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.restore-", dir=destination.parent)
    )
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            manifest = json.loads(archive.read("MANIFEST.json"))
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
                "source_archive_sha256": verification["sha256"],
            },
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "status": "RESTORED_REQUIRES_RESUME",
        "destination": str(destination),
        "archive_sha256": verification["sha256"],
        "entry_count": verification["entry_count"],
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
        else:
            result = restore(Path(args.archive), Path(args.destination), args.actor)
    except (BackupError, OSError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
