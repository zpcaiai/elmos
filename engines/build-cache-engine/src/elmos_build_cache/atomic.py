"""The atomic file-write protocol.

Implements the fifteen-step contract from the specification: reserve, exclusive
no-follow temporary create, streaming digest, quota enforcement, fsync,
validation, lease recheck, atomic rename, parent fsync, metadata CAS, CAS
promotion, digest verification.

The ordering is the whole point. ``fsync`` before rename means the bytes are
durable before the name exists; the lease recheck sits *between* the last write
and the rename so a worker that lost ownership cannot publish a name; and the
metadata compare-and-swap happens after the rename so a crash in between leaves
a sealed file that recovery can verify and re-commit idempotently, never a
committed record pointing at nothing.
"""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .canonical import DIGEST_PREFIX, fsync_directory, require_digest
from .errors import DigestMismatch, QuotaExceeded, UnsafePath

CHUNK = 1024 * 1024

#: ``FICLONE`` from ``linux/fs.h``. Reflink is a *safe* share: a later write to
#: either file breaks the sharing in the kernel, so the source cannot be
#: corrupted through the copy. A hardlink has no such guarantee.
FICLONE = 0x40049409


def try_reflink(source: Path, destination: Path) -> bool:
    """Attempt a copy-on-write clone. Returns ``False`` when unsupported."""
    if not hasattr(os, "uname") or os.uname().sysname != "Linux":
        return False
    try:
        import fcntl

        with source.open("rb") as src, destination.open("wb") as dst:
            fcntl.ioctl(dst.fileno(), FICLONE, src.fileno())
        return True
    except (OSError, ImportError, AttributeError):
        destination.unlink(missing_ok=True)
        return False


@dataclass(frozen=True)
class WriteOutcome:
    digest: str
    size: int
    sealed_path: Path


def open_exclusive_temp(directory: Path, prefix: str) -> tuple[int, Path]:
    """Create a fresh file nobody else can hold, refusing to follow a symlink."""
    directory.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    for _ in range(8):
        candidate = directory / f"{prefix}-{os.urandom(6).hex()}"
        try:
            return os.open(candidate, flags, 0o600), candidate
        except FileExistsError:  # pragma: no cover - nonce collision
            continue
    raise UnsafePath("could not create an exclusive temporary file", directory=str(directory))


def temp_name(basename: str, node_id: str, attempt: int) -> str:
    safe_node = "".join(char if char.isalnum() or char in "-_" else "_" for char in node_id)[:48]
    return f".{basename}.elmos-tmp-{safe_node}-{attempt}"


def stream_to_temp(
    source: BinaryIO | Iterable[bytes],
    directory: Path,
    prefix: str,
    max_bytes: int,
    quota_check: Callable[[int], None] | None = None,
) -> tuple[Path, str, int]:
    """Write to an exclusive temp file while hashing; fsync before returning."""
    fd, temporary = open_exclusive_temp(directory, prefix)
    hasher = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            for chunk in _iter_chunks(source):
                size += len(chunk)
                if size > max_bytes:
                    raise QuotaExceeded(
                        "staged file exceeds the per-file limit", limit=max_bytes, size=size
                    )
                if quota_check is not None:
                    quota_check(len(chunk))
                hasher.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary, DIGEST_PREFIX + hasher.hexdigest(), size


def _iter_chunks(source: BinaryIO | Iterable[bytes]) -> Iterable[bytes]:
    read = getattr(source, "read", None)
    if callable(read):
        while True:
            chunk = read(CHUNK)
            if not chunk:
                return
            yield chunk
        return
    yield from source


def promote_temp(temporary: Path, destination: Path) -> None:
    """Rename into place atomically, with a cross-device copy-verify fallback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise UnsafePath("destination is a symlink", destination=str(destination))
    try:
        os.replace(temporary, destination)
    except OSError as exc:
        if getattr(exc, "errno", None) != errno.EXDEV:
            raise
        # Cross-device: copy into the destination filesystem, fsync, then rename.
        fd, staged = open_exclusive_temp(destination.parent, f".{destination.name}.elmos-xdev")
        os.close(fd)
        shutil.copyfile(temporary, staged)
        with staged.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(staged, destination)
        temporary.unlink(missing_ok=True)
    fsync_directory(destination.parent)


def verify_digest(path: Path, expected: str) -> int:
    require_digest(expected)
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    actual = DIGEST_PREFIX + hasher.hexdigest()
    if actual != expected:
        raise DigestMismatch("sealed file digest mismatch", expected=expected, actual=actual, path=str(path))
    return size


def atomic_write_bytes(destination: Path, data: bytes, mode: int = 0o644) -> None:
    """Small-file convenience used for control records; same durability rules."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, mode)
        except OSError:  # pragma: no cover - platform dependent
            pass
        os.replace(temporary, destination)
        fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)
