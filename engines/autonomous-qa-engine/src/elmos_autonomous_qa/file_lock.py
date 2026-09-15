"""Cross-platform advisory locking used by QA lifecycle fences."""

from __future__ import annotations

import errno
import os


if os.name == "nt":  # pragma: no cover - selected by platform
    import msvcrt

    def lock_exclusive_nonblocking(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

    def unlock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

else:  # pragma: no cover - selected by platform
    import fcntl

    def lock_exclusive_nonblocking(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


LOCK_CONTENTION_ERRNOS = frozenset(
    value
    for value in (errno.EACCES, errno.EAGAIN, getattr(errno, "EWOULDBLOCK", None))
    if value is not None
)
