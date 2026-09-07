"""Durable staging for every file ELMOS generates.

The rule this module exists to enforce: *file existence never equals
completion*. A generator cannot write into the source repository or the live
published output. It reserves a logical path, streams bytes into a private
pending area, and only a sealed, digest-verified, CAS-promoted file that is
reachable from a validated tree manifest ever becomes visible.

Workspace layout (per tenant/project/run)::

    control/  source/  overlay/  scratch/
    generated/pending/  generated/sealed/
    artifacts/  checkpoints/  quarantine/  publish/  logs/
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from .atomic import atomic_write_bytes, promote_temp, stream_to_temp, temp_name, verify_digest
from .canonical import (
    canonical_json_bytes,
    case_fold_key,
    normalize_logical_path,
    require_digest,
    resolve_within,
)
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .config import WorkspaceConfig
from .db import MetadataStore
from .db.records import StagedFileRecord
from .db.store import new_id
from .enums import (
    ArtifactStorageState,
    FileClass,
    Ownership,
    SecretScanStatus,
    StagedFileStatus,
    ValidationLevel,
)
from .errors import (
    ConflictError,
    ContractViolation,
    QuotaExceeded,
    SecretDetected,
    StaleLease,
    UnsafePath,
)

WORKSPACE_DIRECTORIES: tuple[str, ...] = (
    "control",
    "control/leases",
    "source",
    "overlay",
    "scratch",
    "generated/pending",
    "generated/sealed",
    "artifacts",
    "checkpoints",
    "quarantine",
    "publish",
    "logs",
)

#: Roots a stage may be granted write access to. Everything else is read-only.
WRITABLE_ROOTS: frozenset[str] = frozenset({"overlay", "scratch", "generated/pending", "logs"})


@dataclass(frozen=True)
class WorkspaceUsage:
    bytes_used: int
    file_count: int

    def check(self, config: WorkspaceConfig, incoming_bytes: int = 0) -> None:
        if self.bytes_used + incoming_bytes > config.quota_bytes:
            raise QuotaExceeded(
                "workspace byte quota exceeded",
                used=self.bytes_used,
                incoming=incoming_bytes,
                quota=config.quota_bytes,
            )
        if self.file_count >= config.max_files_per_run:
            raise QuotaExceeded(
                "workspace file quota exceeded", files=self.file_count, quota=config.max_files_per_run
            )


@dataclass(frozen=True)
class RecoveryAction:
    staged_file_id: str
    logical_path: str
    status: StagedFileStatus
    action: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "staged_file_id": self.staged_file_id,
            "logical_path": self.logical_path,
            "status": str(self.status),
            "action": self.action,
            "detail": self.detail,
        }


class Workspace:
    """A run-scoped, tenant-isolated workspace with an explicit file lifecycle."""

    def __init__(
        self,
        root: Path,
        tenant_id: str,
        project_id: str,
        run_id: str,
        store: MetadataStore,
        cas: ContentAddressableStore,
        config: WorkspaceConfig | None = None,
        clock: Clock = SYSTEM_CLOCK,
        secret_scanner: Any | None = None,
    ) -> None:
        self.config = config or WorkspaceConfig()
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.run_id = run_id
        self.store = store
        self.cas = cas
        self.clock = clock
        self.secret_scanner = secret_scanner
        self.root = Path(root) / tenant_id / project_id / run_id
        for relative in WORKSPACE_DIRECTORIES:
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self._write_control_record()

    # -- layout -----------------------------------------------------------
    @property
    def source_root(self) -> Path:
        return self.root / "source"

    @property
    def overlay_root(self) -> Path:
        return self.root / "overlay"

    @property
    def scratch_root(self) -> Path:
        return self.root / "scratch"

    @property
    def pending_root(self) -> Path:
        return self.root / "generated" / "pending"

    @property
    def sealed_root(self) -> Path:
        return self.root / "generated" / "sealed"

    @property
    def quarantine_root(self) -> Path:
        return self.root / "quarantine"

    @property
    def publish_root(self) -> Path:
        return self.root / "publish"

    @property
    def checkpoint_root(self) -> Path:
        return self.root / "checkpoints"

    def _write_control_record(self) -> None:
        atomic_write_bytes(
            self.root / "control" / "run.json",
            canonical_json_bytes(
                {
                    "schema_version": "1.0.0",
                    "tenant_id": self.tenant_id,
                    "project_id": self.project_id,
                    "run_id": self.run_id,
                    "writable_roots": sorted(WRITABLE_ROOTS),
                    "undeclared_output_policy": self.config.undeclared_output_policy,
                }
            )
            + b"\n",
        )

    def writable_path(self, root: str, logical_path: str) -> Path:
        """Resolve a path inside a declared writable root, or refuse."""
        if root not in WRITABLE_ROOTS:
            raise UnsafePath("root is not writable by a stage", root=root)
        return resolve_within(self.root / root, logical_path)

    def usage(self) -> WorkspaceUsage:
        total = 0
        count = 0
        for base in (self.overlay_root, self.scratch_root, self.pending_root, self.sealed_root):
            for path in base.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
                    count += 1
        return WorkspaceUsage(bytes_used=total, file_count=count)

    # -- lifecycle: reserve -----------------------------------------------
    def reserve(
        self,
        node_id: str,
        attempt: int,
        logical_path: str,
        lease_epoch: int,
        file_class: FileClass = FileClass.STAGED_INTERMEDIATE,
        overwrite_policy: str = "reject",
        ownership: Ownership = Ownership.GENERATED,
        media_type: str | None = None,
        artifact_kind: str | None = None,
        action_key: str | None = None,
        expected_size: int | None = None,
        lease_id: str | None = None,
        mode: int = 0o644,
    ) -> StagedFileRecord:
        """Transactionally claim a logical output path before any bytes exist."""
        path = normalize_logical_path(logical_path)
        if overwrite_policy not in ("reject", "replace", "merge"):
            raise ContractViolation("invalid overwrite policy", policy=overwrite_policy)

        existing = self.store.find_live_staged_file(self.run_id, path)
        if existing is not None:
            if overwrite_policy == "reject":
                raise ConflictError(
                    "logical path is already reserved in this run",
                    logical_path=path,
                    holder=existing.staged_file_id,
                    holder_status=str(existing.status),
                )
            if existing.status not in (StagedFileStatus.RESERVED, StagedFileStatus.ABORTED):
                raise ConflictError(
                    "cannot overwrite a path that is already sealed or published",
                    logical_path=path,
                    holder_status=str(existing.status),
                )
            self.store.update_staged_file(existing, StagedFileStatus.ABORTED, existing.version)

        for other in self.store.list_staged_files(
            self.run_id,
            [
                StagedFileStatus.RESERVED,
                StagedFileStatus.WRITING,
                StagedFileStatus.SEALED,
                StagedFileStatus.CAS_PROMOTED,
                StagedFileStatus.TREE_INCLUDED,
                StagedFileStatus.PUBLISHED,
            ],
        ):
            if other.logical_path != path and case_fold_key(other.logical_path) == case_fold_key(path):
                raise ConflictError(
                    "logical path collides case-insensitively with an existing reservation",
                    logical_path=path,
                    existing=other.logical_path,
                )

        self.usage().check(self.config, expected_size or 0)

        previous = self.store.find_staged_file(self.run_id, node_id, attempt, path)
        if previous is not None:
            if previous.status is not StagedFileStatus.ABORTED:
                raise ConflictError(
                    "this producer already has a staged file for the path",
                    logical_path=path,
                    status=str(previous.status),
                )
            # Same producer retrying its own failed write: reopen the row
            # rather than creating a second record for one logical path.
            return self.store.update_staged_file(
                previous,
                StagedFileStatus.RESERVED,
                previous.version,
                digest=None,
                actual_size=None,
                artifact_digest=None,
                internal_temp_path=None,
                internal_sealed_path=None,
                quarantine_reason=None,
                file_class=file_class,
            )

        record = StagedFileRecord(
            staged_file_id=new_id("sf"),
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            run_id=self.run_id,
            node_id=node_id,
            attempt=attempt,
            logical_path=path,
            file_class=file_class,
            status=StagedFileStatus.RESERVED,
            lease_epoch=lease_epoch,
            version=0,
            overwrite_policy=overwrite_policy,
            ownership=ownership,
            lease_id=lease_id,
            expected_size=expected_size,
            media_type=media_type,
            artifact_kind=artifact_kind,
            action_key=action_key,
            mode=mode,
        )
        self.store.insert_staged_file(record)
        return record

    # -- lifecycle: write and seal ----------------------------------------
    def write_and_seal(
        self,
        record: StagedFileRecord,
        source: BinaryIO | Iterable[bytes] | bytes,
        current_lease_epoch: int,
        expected_digest: str | None = None,
        validate: Any | None = None,
    ) -> StagedFileRecord:
        """Steps 4-12 of the atomic write protocol.

        The lease epoch is rechecked immediately before the rename *and* the
        metadata commit, because recovery may have reassigned this node while
        the bytes were streaming.
        """
        if record.status is not StagedFileStatus.RESERVED:
            raise ConflictError(
                "staged file is not reserved", staged_file_id=record.staged_file_id, status=str(record.status)
            )
        self._assert_lease(record, current_lease_epoch)

        record = self.store.update_staged_file(
            record, StagedFileStatus.WRITING, record.version, lease_epoch=current_lease_epoch
        )

        payload: BinaryIO | Iterable[bytes]
        payload = [source] if isinstance(source, bytes) else source

        basename = PurePosixPath(record.logical_path).name
        pending_dir = self.pending_root / PurePosixPath(record.logical_path).parent
        usage = self.usage()

        def quota_check(delta: int) -> None:
            if usage.bytes_used + delta > self.config.quota_bytes:
                raise QuotaExceeded("workspace byte quota exceeded during write", quota=self.config.quota_bytes)

        try:
            temporary, digest, size = stream_to_temp(
                payload,
                pending_dir,
                temp_name(basename, record.node_id, record.attempt),
                self.config.max_single_file_bytes,
                quota_check,
            )
        except BaseException as exc:
            failed = self.store.get_staged_file(record.staged_file_id)
            self.store.update_staged_file(
                failed,
                StagedFileStatus.ABORTED,
                failed.version,
                quarantine_reason=f"write failed: {exc}",
            )
            # Durable before the raise: the caller's transaction will roll back,
            # and recovery must see ABORTED rather than a RESERVED row that
            # looks like nothing was ever attempted.
            self.store.commit()
            raise

        try:
            if expected_digest is not None and require_digest(expected_digest) != digest:
                raise ConflictError(
                    "written content does not match the expected digest",
                    expected=expected_digest,
                    actual=digest,
                )
            if record.expected_size is not None and record.expected_size != size:
                raise ConflictError(
                    "written size does not match reservation",
                    expected=record.expected_size,
                    actual=size,
                )
            if validate is not None:
                validate(temporary, digest, size)
            if self.secret_scanner is not None:
                finding = self.secret_scanner.scan_file(temporary, record.logical_path)
                if finding:
                    raise SecretDetected(
                        "secret material detected in generated output",
                        logical_path=record.logical_path,
                        rules=sorted({item.rule for item in finding}),
                    )

            # Re-check ownership *after* validation and before the rename.
            self._assert_lease(record, current_lease_epoch)

            sealed = resolve_within(self.sealed_root, record.logical_path)
            promote_temp(temporary, sealed)
            try:
                os.chmod(sealed, record.mode)
            except OSError:  # pragma: no cover - platform dependent
                pass

            current = self.store.get_staged_file(record.staged_file_id)
            updated = self.store.update_staged_file(
                current,
                StagedFileStatus.SEALED,
                current.version,
                lease_epoch=current_lease_epoch,
                digest=digest,
                actual_size=size,
                internal_sealed_path=str(sealed.relative_to(self.root)),
                internal_temp_path=None,
                secret_scan_status=(
                    SecretScanStatus.PASS if self.secret_scanner is not None else SecretScanStatus.NOT_RUN
                ),
            )
            return updated
        except BaseException as exc:
            temporary.unlink(missing_ok=True)
            current = self.store.get_staged_file(record.staged_file_id)
            if current.status is StagedFileStatus.WRITING:
                target = (
                    StagedFileStatus.QUARANTINED
                    if isinstance(exc, SecretDetected)
                    else StagedFileStatus.ABORTED
                )
                self.store.update_staged_file(
                    current,
                    target,
                    current.version,
                    quarantine_reason=str(exc),
                    secret_scan_status=(
                        SecretScanStatus.FAIL if isinstance(exc, SecretDetected) else SecretScanStatus.NOT_RUN
                    ),
                )
                self.store.commit()
            raise

    def _assert_lease(self, record: StagedFileRecord, epoch: int) -> None:
        if record.lease_epoch != epoch:
            raise StaleLease(
                "worker no longer owns this staged file",
                staged_file_id=record.staged_file_id,
                held=epoch,
                current=record.lease_epoch,
            )
        node = self.store.try_get_node(self.run_id, record.node_id, record.attempt)
        if node is not None and node.lease_epoch != epoch:
            raise StaleLease(
                "node lease epoch advanced; refusing to seal",
                node_id=record.node_id,
                held=epoch,
                current=node.lease_epoch,
            )

    # -- lifecycle: CAS promotion -----------------------------------------
    def promote(self, record: StagedFileRecord) -> StagedFileRecord:
        """Idempotent: re-running after a crash converges instead of duplicating."""
        if record.status is StagedFileStatus.CAS_PROMOTED:
            return record
        if record.status is not StagedFileStatus.SEALED:
            raise ConflictError(
                "only sealed files can be promoted",
                staged_file_id=record.staged_file_id,
                status=str(record.status),
            )
        sealed = self.sealed_path(record)
        assert record.digest is not None
        verify_digest(sealed, record.digest)
        digest = self.cas.put_file(
            sealed,
            expected_digest=record.digest,
            artifact_kind=record.artifact_kind or "generated-file",
        )
        self.store.register_artifact(
            self.tenant_id,
            digest,
            size_bytes=record.actual_size or sealed.stat().st_size,
            media_type=record.media_type or "application/octet-stream",
            artifact_kind=record.artifact_kind or "generated-file",
            storage_state=ArtifactStorageState.LOCAL,
            validation_level=record.validation_level,
        )
        self.store.add_artifact_ref(self.tenant_id, "run", self.run_id, digest, "staged-file")
        self.store.add_artifact_ref(
            self.tenant_id, "staged_file", record.staged_file_id, digest, "content"
        )
        return self.store.update_staged_file(
            record, StagedFileStatus.CAS_PROMOTED, record.version, artifact_digest=digest
        )

    def sealed_path(self, record: StagedFileRecord) -> Path:
        return resolve_within(self.sealed_root, record.logical_path)

    # -- restore from cache -----------------------------------------------
    def restore_from_cache(
        self,
        node_id: str,
        attempt: int,
        lease_epoch: int,
        logical_path: str,
        artifact_digest: str,
        file_class: FileClass = FileClass.PUBLISH_CANDIDATE,
        media_type: str | None = None,
        artifact_kind: str | None = None,
        action_key: str | None = None,
        ownership: Ownership = Ownership.GENERATED,
        mode: int = 0o644,
        source_map_digest: str | None = None,
    ) -> StagedFileRecord:
        """Adopt a cached artifact as this run's staged file.

        A restore still walks the full lifecycle -- reserve, seal with the
        verified digest, promote -- so a restored file is indistinguishable
        from a freshly generated one to everything downstream, including tree
        assembly, checkpoints and the GC root set.
        """
        require_digest(artifact_digest)
        if not self.cas.contains(artifact_digest):
            raise ConflictError(
                "cannot restore: the artifact is not present in the local CAS",
                logical_path=logical_path,
                artifact_digest=artifact_digest,
            )
        record = self.reserve(
            node_id,
            attempt,
            logical_path,
            lease_epoch,
            file_class=file_class,
            ownership=ownership,
            media_type=media_type,
            artifact_kind=artifact_kind,
            action_key=action_key,
            mode=mode,
        )
        sealed = resolve_within(self.sealed_root, record.logical_path)
        self.cas.materialize(artifact_digest, sealed, mode=mode, verify=True)
        size = sealed.stat().st_size

        record = self.store.update_staged_file(
            record, StagedFileStatus.WRITING, record.version, lease_epoch=lease_epoch
        )
        record = self.store.update_staged_file(
            record,
            StagedFileStatus.SEALED,
            record.version,
            lease_epoch=lease_epoch,
            digest=artifact_digest,
            actual_size=size,
            internal_sealed_path=str(sealed.relative_to(self.root)),
            source_map_digest=source_map_digest,
        )
        return self.promote(record)

    # -- quarantine and abort ---------------------------------------------
    def quarantine(self, record: StagedFileRecord, reason: str) -> StagedFileRecord:
        """Move the bytes aside, keep the evidence, and drop it from the tree."""
        target = self.quarantine_root / record.staged_file_id / record.logical_path
        target.parent.mkdir(parents=True, exist_ok=True)
        for candidate in (self.sealed_root / record.logical_path,):
            if candidate.exists() and not candidate.is_symlink():
                try:
                    os.replace(candidate, target)
                except OSError:  # pragma: no cover - cross device
                    shutil.copyfile(candidate, target)
                    candidate.unlink(missing_ok=True)
        atomic_write_bytes(
            self.quarantine_root / record.staged_file_id / "reason.json",
            canonical_json_bytes(
                {
                    "staged_file_id": record.staged_file_id,
                    "logical_path": record.logical_path,
                    "reason": reason,
                    "previous_status": str(record.status),
                }
            )
            + b"\n",
        )
        return self.store.update_staged_file(
            record,
            StagedFileStatus.QUARANTINED,
            record.version,
            quarantine_reason=reason,
            file_class=FileClass.QUARANTINED,
        )

    # -- undeclared output -------------------------------------------------
    def scan_undeclared(self) -> list[str]:
        """Files present in the generated roots that no reservation covers."""
        declared = {
            record.logical_path
            for record in self.store.list_staged_files(self.run_id)
            if record.status
            not in (StagedFileStatus.ABORTED, StagedFileStatus.QUARANTINED)
        }
        found: list[str] = []
        for path in sorted(self.sealed_root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.sealed_root).as_posix()
            if relative not in declared:
                found.append(relative)
        return found

    def handle_undeclared(self, node_id: str = "unknown", attempt: int = 1) -> list[str]:
        """Quarantine (or reject) anything a stage produced without declaring it."""
        undeclared = self.scan_undeclared()
        if not undeclared:
            return []
        if self.config.undeclared_output_policy == "reject":
            raise ContractViolation("stage produced undeclared output", paths=undeclared[:20])
        for relative in undeclared:
            holding = self.quarantine_root / "undeclared" / relative
            holding.parent.mkdir(parents=True, exist_ok=True)
            source = self.sealed_root / relative
            try:
                os.replace(source, holding)
            except OSError:  # pragma: no cover - cross device
                shutil.copyfile(source, holding)
                source.unlink(missing_ok=True)
        atomic_write_bytes(
            self.quarantine_root / "undeclared" / "manifest.json",
            canonical_json_bytes(
                {"run_id": self.run_id, "node_id": node_id, "attempt": attempt, "paths": undeclared}
            )
            + b"\n",
        )
        return undeclared

    # -- recovery ---------------------------------------------------------
    def plan_recovery(self, active_lease_epochs: dict[str, int] | None = None) -> list[RecoveryAction]:
        """Decide, per staged file, what a restarted process must do.

        Conservative by construction: anything that was mid-write when the
        process died is never trusted as complete.
        """
        epochs = active_lease_epochs or {}
        plan: list[RecoveryAction] = []
        for record in self.store.list_staged_files(self.run_id):
            stale = epochs.get(record.node_id, record.lease_epoch) != record.lease_epoch
            if record.status is StagedFileStatus.RESERVED:
                action, detail = ("RELEASE_OR_REASSIGN", "no bytes written")
            elif record.status is StagedFileStatus.WRITING:
                action, detail = (
                    "QUARANTINE_OR_DELETE_PARTIAL",
                    "partial bytes are never trusted as complete",
                )
            elif record.status is StagedFileStatus.SEALED:
                action, detail = ("VERIFY_AND_PROMOTE", "verify digest, then promote idempotently")
            elif record.status is StagedFileStatus.CAS_PROMOTED:
                action, detail = ("INCLUDE_IN_TREE_IF_REQUIRED", "artifact reference is durable")
            elif record.status is StagedFileStatus.TREE_INCLUDED:
                action, detail = ("RECONSTRUCT_AND_VALIDATE_TREE", "publish candidate must be rebuilt")
            elif record.status is StagedFileStatus.PUBLISHED:
                action, detail = ("VERIFY_PUBLISHED_POINTER", "leave content unchanged")
            elif record.status in (StagedFileStatus.ABORTED, StagedFileStatus.QUARANTINED):
                action, detail = ("RETAIN_OR_GC_BY_POLICY", "terminal state")
            else:  # pragma: no cover - closed enum
                action, detail = ("QUARANTINE_UNKNOWN_STATE", "unrecognised state")
            if stale and record.status in (StagedFileStatus.RESERVED, StagedFileStatus.WRITING):
                detail += "; owning lease is stale"
            plan.append(
                RecoveryAction(
                    staged_file_id=record.staged_file_id,
                    logical_path=record.logical_path,
                    status=record.status,
                    action=action,
                    detail=detail,
                )
            )
        return plan

    def recover(self, active_lease_epochs: dict[str, int] | None = None) -> dict[str, Any]:
        """Execute the recovery plan. Converges or fails explicitly; never loops."""
        summary: dict[str, Any] = {
            "released": [],
            "discarded": [],
            "promoted": [],
            "verified": [],
            "quarantined": [],
            "undeclared": [],
            "failed": [],
        }
        for action in self.plan_recovery(active_lease_epochs):
            record = self.store.get_staged_file(action.staged_file_id)
            try:
                if action.action == "RELEASE_OR_REASSIGN":
                    self.store.update_staged_file(record, StagedFileStatus.ABORTED, record.version)
                    summary["released"].append(record.logical_path)
                elif action.action == "QUARANTINE_OR_DELETE_PARTIAL":
                    self._discard_pending(record)
                    self.store.update_staged_file(
                        record,
                        StagedFileStatus.ABORTED,
                        record.version,
                        quarantine_reason="partial write discarded during recovery",
                    )
                    summary["discarded"].append(record.logical_path)
                elif action.action == "VERIFY_AND_PROMOTE":
                    sealed = self.sealed_path(record)
                    if not sealed.exists() or record.digest is None:
                        self.quarantine(record, "sealed file missing at recovery")
                        summary["quarantined"].append(record.logical_path)
                        continue
                    verify_digest(sealed, record.digest)
                    self.promote(self.store.get_staged_file(record.staged_file_id))
                    summary["promoted"].append(record.logical_path)
                elif action.action in ("INCLUDE_IN_TREE_IF_REQUIRED", "VERIFY_PUBLISHED_POINTER"):
                    if record.artifact_digest and not self.cas.contains(record.artifact_digest):
                        self.quarantine(record, "CAS artifact missing at recovery")
                        summary["quarantined"].append(record.logical_path)
                    else:
                        summary["verified"].append(record.logical_path)
                elif action.action == "RECONSTRUCT_AND_VALIDATE_TREE":
                    summary["verified"].append(record.logical_path)
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                summary["failed"].append({"logical_path": record.logical_path, "error": str(exc)})

        summary["undeclared"] = self.handle_undeclared()
        # Pending temporaries never belong to a converged workspace.
        for path in sorted(self.pending_root.rglob("*")):
            if path.is_file():
                path.unlink(missing_ok=True)
        return summary

    def _discard_pending(self, record: StagedFileRecord) -> None:
        basename = PurePosixPath(record.logical_path).name
        directory = self.pending_root / PurePosixPath(record.logical_path).parent
        if not directory.exists():
            return
        prefix = temp_name(basename, record.node_id, record.attempt)
        for path in directory.glob(prefix + "*"):
            path.unlink(missing_ok=True)

    # -- queries ----------------------------------------------------------
    def publishable(self) -> list[StagedFileRecord]:
        return [
            record
            for record in self.store.list_staged_files(
                self.run_id, [StagedFileStatus.CAS_PROMOTED, StagedFileStatus.TREE_INCLUDED]
            )
            if record.file_class in (FileClass.SEALED_ARTIFACT, FileClass.PUBLISH_CANDIDATE)
        ]

    def protected_digests(self) -> set[str]:
        """Artifacts this workspace still needs; the GC must not touch them."""
        digests: set[str] = set()
        for record in self.store.list_staged_files(self.run_id):
            if record.artifact_digest and record.status not in (
                StagedFileStatus.ABORTED,
            ):
                digests.add(record.artifact_digest)
        return digests

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self.store.list_staged_files(self.run_id):
            counts[str(record.status)] = counts.get(str(record.status), 0) + 1
        usage = self.usage()
        return {
            "run_id": self.run_id,
            "root": str(self.root),
            "staged_files": dict(sorted(counts.items())),
            "bytes_used": usage.bytes_used,
            "file_count": usage.file_count,
            "undeclared": self.scan_undeclared(),
        }


def stage_all(
    workspace: Workspace,
    node_id: str,
    attempt: int,
    lease_epoch: int,
    outputs: Sequence[tuple[str, bytes]],
    file_class: FileClass = FileClass.PUBLISH_CANDIDATE,
    action_key: str | None = None,
    media_type: str = "text/plain",
) -> list[StagedFileRecord]:
    """Reserve, write, seal and promote a batch of generated files."""
    records: list[StagedFileRecord] = []
    for logical_path, payload in outputs:
        record = workspace.reserve(
            node_id,
            attempt,
            logical_path,
            lease_epoch,
            file_class=file_class,
            action_key=action_key,
            media_type=media_type,
            artifact_kind="generated-source",
        )
        record = workspace.write_and_seal(record, payload, lease_epoch)
        records.append(workspace.promote(record))
    return records


__all__ = [
    "RecoveryAction",
    "WORKSPACE_DIRECTORIES",
    "WRITABLE_ROOTS",
    "Workspace",
    "WorkspaceUsage",
    "stage_all",
    "replace",
    "ValidationLevel",
]
