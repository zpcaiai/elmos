"""Small cross-platform advisory file-lock boundary for Batch 30 mutations."""

from __future__ import annotations

import errno
import os


class FileLockError(OSError):
    """Raised when the platform cannot establish the requested advisory lock."""


if os.name == "nt":  # pragma: no cover - selected by platform
    import msvcrt

    def lock_exclusive(descriptor: int, *, blocking: bool = True) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(descriptor, mode, 1)
        except OSError as exc:
            raise FileLockError(exc.errno or errno.EACCES, "file lock unavailable") from exc

    def unlock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        except OSError as exc:
            raise FileLockError(exc.errno or errno.EACCES, "file unlock unavailable") from exc

else:  # pragma: no cover - selected by platform
    import fcntl

    def lock_exclusive(descriptor: int, *, blocking: bool = True) -> None:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(descriptor, flags)

    def unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
