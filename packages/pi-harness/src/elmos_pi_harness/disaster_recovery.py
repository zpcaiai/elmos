"""Content-addressed backup and isolated disaster-recovery rehearsal."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
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
        if (
            digest_bytes(self.path.read_bytes()) != self.sha256
            or self.path.stat().st_size != self.size_bytes
        ):
            raise ValueError("backup object digest or size mismatch")
        if not self.encrypted or not self.key_reference:
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
        if not self.objects:
            raise ValueError("backup manifest cannot be empty")
        if len({item.logical_name for item in self.objects}) != len(self.objects):
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
        self.adapters = {item.component: item for item in adapters}
        if not self.adapters:
            raise ValueError("at least one disaster-recovery adapter is required")

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
        if not destination.is_absolute() or destination.is_symlink():
            raise ValueError("backup destination must be an absolute non-symlink path")
        destination.mkdir(parents=True, exist_ok=False)
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
        latest_recovery_point = max(
            _parse_time(item.recovery_point) for item in manifest.objects
        )
        rpo_seconds = max(
            0.0, (datetime.now(timezone.utc) - latest_recovery_point).total_seconds()
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
            if item.path.is_symlink() or not item.path.is_file():
                raise ConflictError("backup object disappeared or became a symlink")
            if (
                digest_bytes(item.path.read_bytes()) != item.sha256
                or item.path.stat().st_size != item.size_bytes
            ):
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
    required_major: int = 16
    key_reference: str = ""

    def __post_init__(self) -> None:
        require_nonempty(self.source_service, "source_service", 128)
        require_nonempty(self.restore_service, "restore_service", 128)
        require_nonempty(self.key_reference, "key_reference", 512)
        require_nonempty(self.age_recipient, "age_recipient", 512)
        if self.source_service == self.restore_service:
            raise ValueError(
                "PostgreSQL restore service must differ from source service"
            )
        for path in (self.pg_dump, self.pg_restore, self.age_binary, self.age_identity):
            if not path.is_absolute() or not path.is_file() or path.is_symlink():
                raise ValueError(
                    "PostgreSQL/age backup paths must be absolute regular files"
                )


class PostgresLogicalBackupAdapter:
    component = "postgresql"

    def __init__(self, config: PostgresBackupConfig) -> None:
        self.config = config
        version = subprocess.run(
            [str(config.pg_dump), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        if f" {config.required_major}." not in version:
            raise ConflictError(
                "pg_dump major version does not match the pinned profile"
            )

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
                    f"--file={plaintext}",
                ],
                check=True,
                capture_output=True,
                timeout=3600,
                env={"PATH": os.environ.get("PATH", ""), "PGCONNECT_TIMEOUT": "10"},
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
        if not output.read_bytes().startswith(b"age-encryption.org/v1"):
            raise ConflictError(
                "age backup output does not contain the expected encrypted format"
            )
        return (
            BackupObject(
                self.component,
                "postgresql-logical-dump",
                output,
                digest_bytes(output.read_bytes()),
                output.stat().st_size,
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
                    "--no-owner",
                    "--no-acl",
                    str(plaintext),
                ],
                check=False,
                capture_output=True,
                timeout=3600,
                env={"PATH": os.environ.get("PATH", ""), "PGCONNECT_TIMEOUT": "10"},
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


def _atomic_write(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".manifest-", delete=False
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
