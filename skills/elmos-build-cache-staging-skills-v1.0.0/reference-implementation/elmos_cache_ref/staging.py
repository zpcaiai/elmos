from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from .cas import LocalCAS
from .journal import AppendOnlyJournal


VALID_STATUSES = {
    "RESERVED",
    "WRITING",
    "SEALED",
    "CAS_PROMOTED",
    "TREE_INCLUDED",
    "PUBLISHED",
    "ABORTED",
    "QUARANTINED",
}


@dataclass
class StagedFile:
    staged_file_id: str
    run_id: str
    node_id: str
    attempt: int
    logical_path: str
    file_class: str
    status: str
    lease_epoch: int
    version: int = 0
    digest: str | None = None
    size: int | None = None
    artifact_ref: str | None = None
    quarantine_reason: str | None = None


class Workspace:
    def __init__(self, root: Path, run_id: str, cas: LocalCAS):
        self.root = root / run_id
        self.run_id = run_id
        self.cas = cas
        for relative in [
            "control",
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
        ]:
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.journal = AppendOnlyJournal(self.root / "control/journal.ndjson")

    @staticmethod
    def validate_logical_path(logical_path: str) -> str:
        normalized = logical_path.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or not path.parts:
            raise ValueError(f"unsafe logical path: {logical_path}")
        if any(part in ("", ".", "..") for part in path.parts):
            raise ValueError(f"unsafe logical path: {logical_path}")
        if ":" in path.parts[0]:
            raise ValueError(f"unsafe drive path: {logical_path}")
        if any("\x00" in part for part in path.parts):
            raise ValueError("NUL is not allowed in paths")
        return str(path)

    def reserve(
        self,
        node_id: str,
        attempt: int,
        logical_path: str,
        lease_epoch: int,
        file_class: str = "STAGED_INTERMEDIATE",
    ) -> StagedFile:
        logical_path = self.validate_logical_path(logical_path)
        if file_class not in {
            "SCRATCH",
            "STAGED_INTERMEDIATE",
            "SEALED_ARTIFACT",
            "PUBLISH_CANDIDATE",
            "QUARANTINED",
        }:
            raise ValueError(f"invalid file class: {file_class}")

        staged = StagedFile(
            staged_file_id="sf_" + secrets.token_hex(12),
            run_id=self.run_id,
            node_id=node_id,
            attempt=attempt,
            logical_path=logical_path,
            file_class=file_class,
            status="RESERVED",
            lease_epoch=lease_epoch,
        )
        record = self._record_path(staged.staged_file_id)
        if record.exists():
            raise FileExistsError(record)
        self._write_record(staged)
        self.journal.append({"event": "STAGED_FILE_RESERVED", **asdict(staged)})
        return staged

    def write_and_seal(
        self,
        staged: StagedFile,
        source: BinaryIO,
        current_lease_epoch: int,
        max_bytes: int = 2 * 1024 * 1024 * 1024,
    ) -> StagedFile:
        if current_lease_epoch != staged.lease_epoch:
            raise RuntimeError("stale lease epoch")
        if staged.status != "RESERVED":
            raise RuntimeError(f"invalid state: {staged.status}")

        staged.status = "WRITING"
        staged.version += 1
        self._write_record(staged)

        pending = (
            self.root
            / "generated/pending"
            / (
                staged.logical_path
                + f".elmos-tmp-{staged.node_id.replace('/', '_')}"
                + f"-{staged.attempt}-{secrets.token_hex(6)}"
            )
        )
        sealed = self.root / "generated/sealed" / staged.logical_path
        pending.parent.mkdir(parents=True, exist_ok=True)
        sealed.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        size = 0
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(pending, flags, 0o600)

        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("staged file exceeds maximum size")
                    handle.write(chunk)
                    hasher.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            if current_lease_epoch != staged.lease_epoch:
                raise RuntimeError("stale lease epoch before seal")

            os.replace(pending, sealed)
            self._fsync_directory(sealed.parent)

            staged.status = "SEALED"
            staged.digest = "sha256:" + hasher.hexdigest()
            staged.size = size
            staged.version += 1
            self._write_record(staged)
            self.journal.append({"event": "STAGED_FILE_SEALED", **asdict(staged)})
            return staged
        except Exception:
            pending.unlink(missing_ok=True)
            raise

    def promote(self, staged: StagedFile) -> StagedFile:
        if staged.status == "CAS_PROMOTED":
            return staged
        if staged.status != "SEALED":
            raise RuntimeError(f"invalid state: {staged.status}")
        sealed = self.root / "generated/sealed" / staged.logical_path
        digest = self.cas.put_bytes(
            sealed.read_bytes(),
            expected_digest=staged.digest,
        )
        staged.status = "CAS_PROMOTED"
        staged.artifact_ref = f"cas://{digest}"
        staged.version += 1
        self._write_record(staged)
        self.journal.append({"event": "STAGED_FILE_PROMOTED", **asdict(staged)})
        return staged

    def quarantine(self, staged: StagedFile, reason: str) -> StagedFile:
        staged.status = "QUARANTINED"
        staged.quarantine_reason = reason
        staged.version += 1
        self._write_record(staged)
        self.journal.append({"event": "STAGED_FILE_QUARANTINED", **asdict(staged)})
        return staged

    def load(self, staged_file_id: str) -> StagedFile:
        data = json.loads(self._record_path(staged_file_id).read_text(encoding="utf-8"))
        return StagedFile(**data)

    def list_records(self) -> list[StagedFile]:
        records = []
        for path in sorted((self.root / "control").glob("sf_*.json")):
            records.append(StagedFile(**json.loads(path.read_text(encoding="utf-8"))))
        return records

    def _record_path(self, staged_file_id: str) -> Path:
        return self.root / "control" / f"{staged_file_id}.json"

    def _write_record(self, staged: StagedFile) -> None:
        if staged.status not in VALID_STATUSES:
            raise ValueError(staged.status)
        path = self._record_path(staged.staged_file_id)
        temporary = path.with_suffix(".json.tmp")
        data = (
            json.dumps(asdict(staged), sort_keys=True, indent=2).encode("utf-8")
            + b"\n"
        )
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        self._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
