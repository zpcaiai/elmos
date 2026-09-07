"""Content-addressed backup and isolated disaster-recovery rehearsal."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from .canonical import (
    canonical_bytes,
    digest,
    digest_bytes,
    require_nonempty,
    require_uuid,
    utc_now,
)
from .models import ConflictError, PolicyDeniedError
from .production import ApprovalGrant, ExactTarget


@dataclass(frozen=True)
class BackupObject:
    component: str
    logical_name: str
    path: Path
    sha256: str
    size_bytes: int
    recovery_point: str
    encrypted: bool
    key_reference: str | None

    def __post_init__(self) -> None:
        require_nonempty(self.component, "component", 128)
        require_nonempty(self.logical_name, "logical_name", 512)
        if (
            not self.path.is_absolute()
            or self.path.is_symlink()
            or not self.path.is_file()
        ):
            raise ValueError("backup object must be an absolute regular file")
        actual_digest, actual_size = _file_digest_and_size(self.path)
        if actual_digest != self.sha256 or actual_size != self.size_bytes:
            raise ValueError("backup object digest or size mismatch")
        _parse_time(self.recovery_point)
        if not self.encrypted or not isinstance(self.key_reference, str) or not self.key_reference.strip():
            raise PolicyDeniedError(
                "production backup objects must be encrypted with a key reference"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "logical_name": self.logical_name,
            "file_name": self.path.name,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "recovery_point": self.recovery_point,
            "encrypted": self.encrypted,
            "key_reference": self.key_reference,
        }


class BackupAdapter(Protocol):
    component: str

    def capture(
        self, destination: Path, *, authorization_id: str
    ) -> Sequence[BackupObject]: ...
    def restore(
        self,
        objects: Sequence[BackupObject],
        target: ExactTarget,
        *,
        authorization_id: str,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    source: ExactTarget
    created_at: str
    objects: tuple[BackupObject, ...]
    authorization_id: str

    def __post_init__(self) -> None:
        require_uuid(self.backup_id, "backup_id")
        require_nonempty(self.authorization_id, "authorization_id", 256)
        _parse_time(self.created_at)
        objects = tuple(self.objects)
        object.__setattr__(self, "objects", objects)
        if not objects:
            raise ValueError("backup manifest cannot be empty")
        if len({item.logical_name for item in objects}) != len(objects):
            raise ValueError("backup object logical names must be unique")

    def to_dict(self) -> dict[str, Any]:
        value = {
            "backup_id": self.backup_id,
            "source": self.source.to_dict(),
            "created_at": self.created_at,
            "objects": [item.to_dict() for item in self.objects],
            "authorization_id": self.authorization_id,
        }
        return value | {"manifest_digest": digest(value)}


class DisasterRecoveryOrchestrator:
    def __init__(self, adapters: Sequence[BackupAdapter]) -> None:
        values = list(adapters)
        self.adapters = {item.component: item for item in values}
        if not self.adapters:
            raise ValueError("at least one disaster-recovery adapter is required")
        if len(self.adapters) != len(values):
            raise ValueError("disaster-recovery adapter components must be unique")
        for component in self.adapters:
            require_nonempty(component, "adapter.component", 128)

    def capture(
        self,
        *,
        backup_id: str,
        source: ExactTarget,
        destination: Path,
        authorization_id: str,
    ) -> BackupManifest:
        require_uuid(backup_id, "backup_id")
        require_nonempty(authorization_id, "authorization_id", 256)
        _assert_safe_new_directory(destination)
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        objects: list[BackupObject] = []
        try:
            for component, adapter in sorted(self.adapters.items()):
                component_dir = destination / component
                component_dir.mkdir(mode=0o700)
                captured = list(
                    adapter.capture(component_dir, authorization_id=authorization_id)
                )
                if not captured or any(
                    item.component != component for item in captured
                ):
                    raise ConflictError(
                        f"backup adapter {component} returned an invalid object set"
                    )
                objects.extend(captured)
            manifest = BackupManifest(
                backup_id, source, utc_now(), tuple(objects), authorization_id
            )
            _atomic_write(
                destination / "manifest.json", canonical_bytes(manifest.to_dict())
            )
            return manifest
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def rehearse_restore(
        self,
        manifest: BackupManifest,
        *,
        restore_operation_id: str,
        target: ExactTarget,
        grant: ApprovalGrant,
        actor_id: str,
        verifiers: Sequence[Callable[[ExactTarget], Mapping[str, Any]]],
        maximum_rpo_seconds: int,
        maximum_rto_seconds: int,
    ) -> dict[str, Any]:
        restore_operation_id = require_uuid(
            restore_operation_id, "restore_operation_id"
        )
        for name, value in (
            ("maximum_rpo_seconds", maximum_rpo_seconds),
            ("maximum_rto_seconds", maximum_rto_seconds),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if target.environment.lower() in {"prod", "production"}:
            raise PolicyDeniedError(
                "DR rehearsal target must be isolated and non-production"
            )
        if target.to_dict() == manifest.source.to_dict():
            raise PolicyDeniedError("DR rehearsal cannot overwrite the source target")
        request = {
            "backup_id": manifest.backup_id,
            "manifest_digest": manifest.to_dict()["manifest_digest"],
        }
        grant.assert_valid(
            operation_id=restore_operation_id,
            request_digest=digest(request),
            target=target,
            action="dr_restore",
            actor_id=actor_id,
        )
        self._verify_objects(manifest)
        started = time.monotonic()
        component_results: dict[str, Any] = {}
        by_component: dict[str, list[BackupObject]] = {}
        for item in manifest.objects:
            by_component.setdefault(item.component, []).append(item)
        for component, objects in sorted(by_component.items()):
            adapter = self.adapters.get(component)
            if adapter is None:
                raise ConflictError(f"restore adapter is missing for {component}")
            result = dict(
                adapter.restore(objects, target, authorization_id=grant.approval_id)
            )
            if result.get("status") != "PASS":
                return {
                    "status": "FAILED",
                    "certified": False,
                    "component_results": component_results | {component: result},
                    "external_evidence": "EXECUTED",
                }
            component_results[component] = result
        verification_results = [dict(verifier(target)) for verifier in verifiers]
        if not verification_results or any(
            item.get("status") != "PASS" or not item.get("evidence_digest")
            for item in verification_results
        ):
            return {
                "status": "FAILED",
                "certified": False,
                "component_results": component_results,
                "verification_results": verification_results,
                "external_evidence": "EXECUTED",
            }
        rto_seconds = time.monotonic() - started
        recovery_points = [
            _parse_time(item.recovery_point) for item in manifest.objects
        ]
        observed_at = datetime.now(timezone.utc)
        if any(point > observed_at + timedelta(minutes=5) for point in recovery_points):
            raise ConflictError("backup recovery point is implausibly in the future")
        # A multi-component restore is only as fresh as its oldest component.
        effective_recovery_point = min(recovery_points)
        rpo_seconds = max(
            0.0, (observed_at - effective_recovery_point).total_seconds()
        )
        objectives_met = (
            rpo_seconds <= maximum_rpo_seconds and rto_seconds <= maximum_rto_seconds
        )
        return {
            "status": "PASS" if objectives_met else "FAILED",
            "certified": False,
            "backup_id": manifest.backup_id,
            "restore_operation_id": restore_operation_id,
            "target": target.to_dict(),
            "rpo_seconds": round(rpo_seconds, 3),
            "rto_seconds": round(rto_seconds, 3),
            "objectives": {
                "maximum_rpo_seconds": maximum_rpo_seconds,
                "maximum_rto_seconds": maximum_rto_seconds,
                "met": objectives_met,
            },
            "component_results": component_results,
            "verification_results": verification_results,
            "external_evidence": "EXECUTED",
        }

    @staticmethod
    def _verify_objects(manifest: BackupManifest) -> None:
        for item in manifest.objects:
            try:
                actual_digest, actual_size = _file_digest_and_size(item.path)
            except (OSError, PolicyDeniedError) as exc:
                raise ConflictError(
                    "backup object disappeared or became unsafe"
                ) from exc
            if actual_digest != item.sha256 or actual_size != item.size_bytes:
                raise ConflictError("backup object failed integrity verification")


@dataclass(frozen=True)
class PostgresBackupConfig:
    source_service: str
    restore_service: str
    pg_dump: Path
    pg_restore: Path
    age_binary: Path
    age_recipient: str
    age_identity: Path
    pg_service_file: Path
    restore_target_digest: str
    pg_dump_digest: str
    pg_restore_digest: str
    age_binary_digest: str
    pg_service_file_digest: str
    required_major: int = 16
    key_reference: str = ""

    def __post_init__(self) -> None:
        require_nonempty(self.source_service, "source_service", 128)
        require_nonempty(self.restore_service, "restore_service", 128)
        require_nonempty(self.key_reference, "key_reference", 512)
        recipient = require_nonempty(self.age_recipient, "age_recipient", 512)
        if re.fullmatch(r"age1[0-9a-z]+", recipient) is None:
            raise ValueError("age_recipient must be an exact native age recipient")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.source_service) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+", self.restore_service
        ):
            raise ValueError("PostgreSQL service names contain unsupported characters")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.restore_target_digest):
            raise ValueError("restore_target_digest must be a lowercase SHA-256 digest")
        for name in (
            "pg_dump_digest",
            "pg_restore_digest",
            "age_binary_digest",
            "pg_service_file_digest",
        ):
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", getattr(self, name)):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if (
            not isinstance(self.required_major, int)
            or isinstance(self.required_major, bool)
            or self.required_major < 12
        ):
            raise ValueError("required_major must be a supported PostgreSQL major")
        if self.source_service == self.restore_service:
            raise ValueError(
                "PostgreSQL restore service must differ from source service"
            )
        for path in (
            self.pg_dump,
            self.pg_restore,
            self.age_binary,
            self.age_identity,
            self.pg_service_file,
        ):
            if not path.is_absolute() or not path.is_file() or path.is_symlink():
                raise ValueError(
                    "PostgreSQL/age backup paths must be absolute regular files"
                )
        for executable in (self.pg_dump, self.pg_restore, self.age_binary):
            if not os.access(executable, os.X_OK):
                raise ValueError(f"backup executable is not executable: {executable}")
        for path, expected in (
            (self.pg_dump, self.pg_dump_digest),
            (self.pg_restore, self.pg_restore_digest),
            (self.age_binary, self.age_binary_digest),
            (self.pg_service_file, self.pg_service_file_digest),
        ):
            actual, _size = _file_digest_and_size(path)
            if actual != expected:
                raise ConflictError(f"backup dependency digest mismatch: {path.name}")
        if self.age_identity.stat().st_mode & 0o077:
            raise PolicyDeniedError("age identity must not be group/world accessible")
        if self.pg_service_file.stat().st_mode & 0o077:
            raise PolicyDeniedError(
                "PostgreSQL service file must not be group/world accessible"
            )


class PostgresLogicalBackupAdapter:
    component = "postgresql"

    def __init__(self, config: PostgresBackupConfig) -> None:
        self.config = config
        for executable in (config.pg_dump, config.pg_restore):
            version = subprocess.run(
                [str(executable), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            if f" {config.required_major}." not in version:
                raise ConflictError(
                    "PostgreSQL backup tool major version does not match the pinned profile"
                )

    def _postgres_environment(self) -> dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", ""),
            "PGCONNECT_TIMEOUT": "10",
            "PGSERVICEFILE": str(self.config.pg_service_file),
        }

    def capture(
        self, destination: Path, *, authorization_id: str
    ) -> Sequence[BackupObject]:
        require_nonempty(authorization_id, "authorization_id", 256)
        plaintext = destination / ".pi-harness.dump"
        output = destination / "pi-harness.dump.age"
        try:
            subprocess.run(
                [
                    str(self.config.pg_dump),
                    f"--dbname=service={self.config.source_service}",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--serializable-deferrable",
                    f"--file={plaintext}",
                ],
                check=True,
                capture_output=True,
                timeout=3600,
                env=self._postgres_environment(),
            )
            subprocess.run(
                [
                    str(self.config.age_binary),
                    "--recipient",
                    self.config.age_recipient,
                    "--output",
                    str(output),
                    str(plaintext),
                ],
                check=True,
                capture_output=True,
                timeout=3600,
                env={"PATH": os.environ.get("PATH", "")},
            )
        finally:
            plaintext.unlink(missing_ok=True)
        with output.open("rb") as encrypted:
            header = encrypted.read(21)
        if not header.startswith(b"age-encryption.org/v1"):
            raise ConflictError(
                "age backup output does not contain the expected encrypted format"
            )
        output_digest, output_size = _file_digest_and_size(output)
        return (
            BackupObject(
                self.component,
                "postgresql-logical-dump",
                output,
                output_digest,
                output_size,
                utc_now(),
                True,
                self.config.key_reference,
            ),
        )

    def restore(
        self,
        objects: Sequence[BackupObject],
        target: ExactTarget,
        *,
        authorization_id: str,
    ) -> Mapping[str, Any]:
        require_nonempty(authorization_id, "authorization_id", 256)
        if target.environment.lower() in {"prod", "production"}:
            raise PolicyDeniedError("logical restore target cannot be production")
        if len(objects) != 1:
            raise ConflictError("PostgreSQL restore requires exactly one logical dump")
        if digest(target.to_dict()) != self.config.restore_target_digest:
            raise PolicyDeniedError(
                "logical restore target does not match the approved exact target"
            )
        actual_digest, actual_size = _file_digest_and_size(objects[0].path)
        if (
            actual_digest != objects[0].sha256
            or actual_size != objects[0].size_bytes
        ):
            raise ConflictError("PostgreSQL backup object failed integrity verification")
        with tempfile.TemporaryDirectory(
            prefix="pi-harness-pg-restore-"
        ) as temporary_root:
            plaintext = Path(temporary_root) / "restore.dump"
            decrypt = subprocess.run(
                [
                    str(self.config.age_binary),
                    "--decrypt",
                    "--identity",
                    str(self.config.age_identity),
                    "--output",
                    str(plaintext),
                    str(objects[0].path),
                ],
                check=False,
                capture_output=True,
                timeout=3600,
                env={"PATH": os.environ.get("PATH", "")},
            )
            if decrypt.returncode != 0:
                evidence = {
                    "returncode": decrypt.returncode,
                    "stderr_digest": digest_bytes(decrypt.stderr),
                    "phase": "decrypt",
                }
                return {
                    "status": "FAIL",
                    "evidence_digest": digest(evidence),
                    "native": evidence,
                }
            result = subprocess.run(
                [
                    str(self.config.pg_restore),
                    f"--dbname=service={self.config.restore_service}",
                    "--clean",
                    "--if-exists",
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                    "--no-acl",
                    str(plaintext),
                ],
                check=False,
                capture_output=True,
                timeout=3600,
                env=self._postgres_environment(),
            )
        evidence = {
            "returncode": result.returncode,
            "stdout_digest": digest_bytes(result.stdout),
            "stderr_digest": digest_bytes(result.stderr),
        }
        return {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "evidence_digest": digest(evidence),
            "native": evidence,
        }


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("recovery point must include timezone")
    return parsed.astimezone(timezone.utc)


def _assert_safe_new_directory(path: Path) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("backup destination must be a new absolute non-symlink path")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("backup destination parent must be an existing safe directory")
    current = Path(path.anchor)
    for part in parent.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise PolicyDeniedError(
                "backup destination path must not traverse symbolic links"
            )


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    if not path.is_absolute() or path.is_symlink():
        raise PolicyDeniedError("backup object must be an absolute non-symlink file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PolicyDeniedError("backup object must be a regular file")
        hasher = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
        return "sha256:" + hasher.hexdigest(), metadata.st_size
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".manifest-", delete=False
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
