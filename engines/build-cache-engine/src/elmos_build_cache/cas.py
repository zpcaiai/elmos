"""Content-addressable storage.

Invariants enforced here, not by callers:

* a canonical digest maps to exactly one byte sequence;
* a write is invisible until digest, size, ``fsync`` and atomic link all
  succeed, so a kill mid-write leaves no partial canonical object;
* objects are immutable -- an "update" is a new digest;
* a corrupt object is quarantined and refuses to serve, even if a caller asks
  for it by digest.

Concurrent identical writers converge without a global lock because the commit
step is ``os.link`` (create-if-absent): the loser's ``FileExistsError`` is the
success signal, not an error.
"""

from __future__ import annotations

import gzip
import os
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .atomic import try_reflink
from .canonical import (
    DIGEST_PREFIX,
    canonical_json_bytes,
    digest_hex,
    fsync_directory,
    require_digest,
    sha256_bytes,
    sha256_file,
)
from .errors import ContractViolation, CorruptObject, DigestMismatch, NotFound, QuotaExceeded

CHUNK = 1024 * 1024
COMPRESSION_MIN_BYTES = 4096
COMPRESSION_MIN_RATIO = 0.9

#: CAS blobs are stored read-only. Immutability is a contract, not a hope.
BLOB_MODE = 0o444


@dataclass(frozen=True)
class ObjectInfo:
    digest: str
    size: int
    stored_size: int
    compression: str
    path: Path

    @property
    def compressed(self) -> bool:
        return self.compression != "none"


@dataclass(frozen=True)
class RestoreEstimate:
    """Inputs for the recompute-versus-restore decision."""

    digest: str
    size: int
    stored_size: int
    estimated_restore_ms: float

    def cheaper_than(self, estimated_recompute_ms: float) -> bool:
        return self.estimated_restore_ms < estimated_recompute_ms


class ContentAddressableStore:
    """Local filesystem CAS with sidecar metadata and quarantine."""

    def __init__(
        self,
        root: Path,
        compression: str = "none",
        max_bytes: int | None = None,
        restore_bytes_per_ms: float = 200_000.0,
    ) -> None:
        self.root = Path(root)
        self.objects_root = self.root / "cas"
        self.quarantine_root = self.root / "quarantine"
        self.compression = compression
        self.max_bytes = max_bytes
        self.restore_bytes_per_ms = restore_bytes_per_ms
        for directory in (self.objects_root, self.quarantine_root):
            directory.mkdir(parents=True, exist_ok=True)

    # -- layout -----------------------------------------------------------
    def _shard(self, digest: str) -> Path:
        value = digest_hex(digest)
        return self.objects_root / "sha256" / value[:2] / value[2:4]

    def path_for(self, digest: str) -> Path:
        return self._shard(digest) / f"{digest_hex(digest)}.blob"

    def _sidecar(self, digest: str) -> Path:
        return self._shard(digest) / f"{digest_hex(digest)}.json"

    def _quarantine_path(self, digest: str) -> Path:
        return self.quarantine_root / f"{digest_hex(digest)}.blob"

    # -- queries ----------------------------------------------------------
    def contains(self, digest: str) -> bool:
        require_digest(digest)
        return self.path_for(digest).exists() and not self.is_quarantined(digest)

    def is_quarantined(self, digest: str) -> bool:
        return self._quarantine_path(digest).exists()

    def info(self, digest: str) -> ObjectInfo:
        require_digest(digest)
        if self.is_quarantined(digest):
            raise CorruptObject("object is quarantined", digest=digest)
        path = self.path_for(digest)
        if not path.exists():
            raise NotFound("object is not present in the local CAS", digest=digest)
        meta = self._read_sidecar(digest)
        return ObjectInfo(
            digest=digest,
            size=int(meta["size"]),
            stored_size=path.stat().st_size,
            compression=str(meta.get("compression", "none")),
            path=path,
        )

    def _read_sidecar(self, digest: str) -> dict[str, Any]:
        import json

        sidecar = self._sidecar(digest)
        if sidecar.exists():
            loaded: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
            return loaded
        # A blob without a sidecar predates metadata or lost it: recover
        # conservatively by treating it as uncompressed and re-deriving size.
        return {"size": self.path_for(digest).stat().st_size, "compression": "none"}

    def total_bytes(self) -> int:
        total = 0
        for path in self.objects_root.rglob("*.blob"):
            total += path.stat().st_size
        return total

    # -- writes -----------------------------------------------------------
    def put_bytes(self, data: bytes, expected_digest: str | None = None, artifact_kind: str = "blob") -> str:
        digest = sha256_bytes(data)
        if expected_digest is not None and require_digest(expected_digest) != digest:
            raise DigestMismatch(
                "content does not match the declared digest", expected=expected_digest, actual=digest
            )
        if self.contains(digest):
            return digest
        self._check_quota(len(data))
        destination = self.path_for(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload, compression = self._maybe_compress(data)
        self._commit(destination, payload)
        self._write_sidecar(digest, len(data), compression, artifact_kind)
        return digest

    def put_stream(
        self, stream: BinaryIO, expected_digest: str | None = None, artifact_kind: str = "blob"
    ) -> str:
        """Stream to a temporary file, hashing as we go; never buffer whole objects."""
        import hashlib

        staging = self.objects_root / ".incoming"
        staging.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        size = 0
        fd, name = tempfile.mkstemp(prefix=".elmos-cas-in-", dir=staging)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    self._check_quota(size)
                    hasher.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            digest = DIGEST_PREFIX + hasher.hexdigest()
            if expected_digest is not None and require_digest(expected_digest) != digest:
                raise DigestMismatch(
                    "stream does not match the declared digest", expected=expected_digest, actual=digest
                )
            if self.contains(digest):
                return digest
            destination = self.path_for(digest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if self.compression == "none" or size < COMPRESSION_MIN_BYTES:
                self._link_commit(temporary, destination)
                self._write_sidecar(digest, size, "none", artifact_kind)
            else:
                payload, compression = self._maybe_compress(temporary.read_bytes())
                self._commit(destination, payload)
                self._write_sidecar(digest, size, compression, artifact_kind)
            return digest
        finally:
            temporary.unlink(missing_ok=True)

    def put_file(self, path: Path, expected_digest: str | None = None, artifact_kind: str = "blob") -> str:
        with Path(path).open("rb") as handle:
            return self.put_stream(handle, expected_digest, artifact_kind)

    def put_document(self, document: Any, artifact_kind: str = "manifest") -> str:
        return self.put_bytes(canonical_json_bytes(document), artifact_kind=artifact_kind)

    def _maybe_compress(self, data: bytes) -> tuple[bytes, str]:
        if self.compression in ("none", "") or len(data) < COMPRESSION_MIN_BYTES:
            return data, "none"
        if self.compression in ("gzip", "zstd"):
            # gzip is used as the portable stand-in when python-zstandard is
            # absent; the sidecar records what was actually applied.
            compressed = gzip.compress(data, mtime=0)
            if len(compressed) < len(data) * COMPRESSION_MIN_RATIO:
                return compressed, "gzip"
            return data, "none"
        return data, "none"

    def _commit(self, destination: Path, payload: bytes) -> None:
        fd, name = tempfile.mkstemp(prefix=".elmos-cas-", dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._link_commit(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _link_commit(temporary: Path, destination: Path) -> None:
        try:
            os.chmod(temporary, BLOB_MODE)
        except OSError:  # pragma: no cover - platform dependent
            pass
        try:
            os.link(temporary, destination)
        except FileExistsError:
            # Another writer produced the identical object first. Converged.
            return
        except OSError:
            # Different filesystem or a platform without hard links.
            os.replace(temporary, destination)
        fsync_directory(destination.parent)

    def _write_sidecar(self, digest: str, size: int, compression: str, artifact_kind: str) -> None:
        sidecar = self._sidecar(digest)
        if sidecar.exists():
            return
        payload = canonical_json_bytes(
            {
                "digest": digest,
                "size": size,
                "compression": compression,
                "artifact_kind": artifact_kind,
                "hash": "sha256",
            }
        )
        fd, name = tempfile.mkstemp(prefix=".elmos-side-", dir=sidecar.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(payload + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, sidecar)
            fsync_directory(sidecar.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _check_quota(self, incoming: int) -> None:
        if self.max_bytes is None:
            return
        if incoming > self.max_bytes:
            raise QuotaExceeded("object exceeds the configured CAS budget", size=incoming)

    # -- reads ------------------------------------------------------------
    def get_bytes(self, digest: str, verify: bool = True) -> bytes:
        info = self.info(digest)
        raw = info.path.read_bytes()
        data = gzip.decompress(raw) if info.compressed else raw
        if verify:
            actual = sha256_bytes(data)
            if actual != digest:
                self.quarantine(digest, f"digest mismatch on read: {actual}")
                raise CorruptObject("stored object is corrupt", digest=digest, actual=actual)
        return data

    def get_document(self, digest: str) -> Any:
        import json

        return json.loads(self.get_bytes(digest).decode("utf-8"))

    def open_stream(self, digest: str) -> Iterator[bytes]:
        info = self.info(digest)
        if info.compressed:
            yield from _chunks(gzip.decompress(info.path.read_bytes()))
            return
        with info.path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK)
                if not chunk:
                    break
                yield chunk

    def verify(self, digest: str) -> bool:
        """Verify one object. Quarantines and returns ``False`` when corrupt."""
        try:
            self.get_bytes(digest, verify=True)
        except CorruptObject:
            return False
        except NotFound:
            return False
        return True

    def estimate_restore(self, digest: str) -> RestoreEstimate:
        info = self.info(digest)
        return RestoreEstimate(
            digest=digest,
            size=info.size,
            stored_size=info.stored_size,
            estimated_restore_ms=max(0.05, info.stored_size / self.restore_bytes_per_ms),
        )

    # -- materialisation --------------------------------------------------
    def materialize(
        self,
        digest: str,
        destination: Path,
        mode: int = 0o644,
        verify: bool = True,
        share: str = "auto",
    ) -> Path:
        """Place the object at ``destination`` atomically.

        ``share`` controls how the bytes get there:

        ``auto`` (default)
            reflink when the filesystem supports it, otherwise copy. Both are
            safe: a later in-place write to the destination cannot reach back
            into the CAS object.
        ``link``
            hardlink. Only for callers that guarantee the destination is never
            written in place -- a hardlink shares the inode, so an in-place
            write *would* corrupt the canonical object.
        ``copy``
            always copy.
        """
        if share not in ("auto", "link", "copy"):
            raise ContractViolation("unknown materialize sharing mode", share=share)
        info = self.info(digest)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.elmos-mat-{os.getpid()}-{os.urandom(4).hex()}"
        temporary.unlink(missing_ok=True)
        try:
            if info.compressed:
                data = self.get_bytes(digest, verify=verify)
                with temporary.open("wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            else:
                hardlinked = False
                if share == "link":
                    try:
                        os.link(info.path, temporary)
                        hardlinked = True
                    except OSError:
                        pass
                if not hardlinked:
                    if not (share in ("auto", "link") and try_reflink(info.path, temporary)):
                        shutil.copyfile(info.path, temporary)
                if verify:
                    actual, size = sha256_file(temporary)
                    if actual != digest:
                        temporary.unlink(missing_ok=True)
                        self.quarantine(digest, f"digest mismatch on materialize: {actual}")
                        raise CorruptObject("object is corrupt", digest=digest, actual=actual)
                    if size != info.size:
                        temporary.unlink(missing_ok=True)
                        raise CorruptObject("object size mismatch", digest=digest, actual=size)
                if not hardlinked:
                    with temporary.open("rb") as handle:
                        os.fsync(handle.fileno())
            if share != "link":
                try:
                    os.chmod(temporary, mode)
                except OSError:  # pragma: no cover - platform dependent
                    pass
            os.replace(temporary, destination)
            fsync_directory(destination.parent)
            return destination
        finally:
            temporary.unlink(missing_ok=True)

    # -- integrity --------------------------------------------------------
    def quarantine(self, digest: str, reason: str) -> Path:
        """Move a suspect object out of the servable set, keeping the bytes."""
        source = self.path_for(digest)
        target = self._quarantine_path(digest)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        if source.exists():
            try:
                os.replace(source, target)
            except OSError:  # pragma: no cover - cross device
                shutil.copyfile(source, target)
                source.unlink(missing_ok=True)
        else:
            target.touch()
        note = target.with_suffix(".reason.json")
        note.write_text(
            canonical_json_bytes({"digest": digest, "reason": reason}).decode("utf-8") + "\n",
            encoding="utf-8",
        )
        return target

    def repair_from(self, digest: str, replica: ContentAddressableStore) -> bool:
        """Re-fetch a quarantined object from a verified replica."""
        try:
            data = replica.get_bytes(digest, verify=True)
        except (NotFound, CorruptObject):
            return False
        if sha256_bytes(data) != digest:
            return False
        quarantined = self._quarantine_path(digest)
        destination = self.path_for(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload, compression = self._maybe_compress(data)
        destination.unlink(missing_ok=True)
        self._commit(destination, payload)
        self._sidecar(digest).unlink(missing_ok=True)
        self._write_sidecar(digest, len(data), compression, "blob")
        quarantined.unlink(missing_ok=True)
        quarantined.with_suffix(".reason.json").unlink(missing_ok=True)
        return True

    def scrub(self, digests: Iterable[str] | None = None) -> dict[str, list[str]]:
        """Verify every (or the given) object; report healthy and corrupt sets."""
        targets = list(digests) if digests is not None else list(self.iter_digests())
        healthy: list[str] = []
        corrupt: list[str] = []
        for digest in targets:
            if self.verify(digest):
                healthy.append(digest)
            else:
                corrupt.append(digest)
        return {"healthy": sorted(healthy), "corrupt": sorted(corrupt)}

    def iter_digests(self) -> Iterator[str]:
        for path in sorted(self.objects_root.rglob("*.blob")):
            yield DIGEST_PREFIX + path.stem

    def delete(self, digest: str) -> bool:
        """Remove an object. Only the GC may call this, after protection checks."""
        removed = False
        for path in (self.path_for(digest), self._sidecar(digest)):
            if path.exists():
                path.unlink()
                removed = True
        return removed

    def accounting(self) -> dict[str, int]:
        objects = list(self.objects_root.rglob("*.blob"))
        logical = 0
        for path in objects:
            digest = DIGEST_PREFIX + path.stem
            try:
                logical += self.info(digest).size
            except (NotFound, CorruptObject):
                continue
        return {
            "object_count": len(objects),
            "stored_bytes": sum(path.stat().st_size for path in objects),
            "logical_bytes": logical,
            "quarantined_count": len(list(self.quarantine_root.glob("*.blob"))),
        }


def _chunks(data: bytes, size: int = CHUNK) -> Iterator[bytes]:
    for offset in range(0, len(data), size):
        yield data[offset : offset + size]
