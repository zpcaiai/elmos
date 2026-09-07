"""Descriptor-relative helpers for lexical paths that must not traverse symlinks.

The caller spelling is made absolute without resolving any component. The
helpers keep that lexical path and the opened descriptor distinct so a later
lookup can be rebound to the exact directory or file that was authorized.
Callers using a platform alias such as macOS ``/var`` must canonicalize it
before entering this strict no-symlink boundary.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
import stat


class UnsafePathError(OSError):
    """Raised when a path cannot be opened without following symlinks."""


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_BASE_FLAGS = os.O_CLOEXEC | os.O_NOFOLLOW


def _absolute(path: str | os.PathLike[str]) -> Path:
    lexical = Path(path).absolute()
    if not lexical.anchor:
        raise UnsafePathError("safe path must be absolute")
    return lexical


def same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    """Return whether two metadata records identify the same filesystem object."""

    return (left.st_dev, left.st_ino, stat.S_IFMT(left.st_mode)) == (
        right.st_dev,
        right.st_ino,
        stat.S_IFMT(right.st_mode),
    )


def open_directory_no_symlinks(
    path: str | os.PathLike[str],
    *,
    create: bool = False,
    final_mode: int = 0o700,
) -> tuple[Path, int, bool]:
    """Open an absolute directory one component at a time with ``O_NOFOLLOW``.

    When ``create`` is true, missing components are created descriptor-relative.
    Only the final component uses ``final_mode``; intermediate directories use
    the conventional mkdir mode and are still subject to the process umask.
    """

    absolute = _absolute(path)
    descriptor = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    final_created = False
    try:
        components = absolute.parts[1:]
        for index, component in enumerate(components):
            if component in {"", ".", ".."} or "/" in component or "\x00" in component:
                raise UnsafePathError("safe path contains an unsafe component")
            is_final = index == len(components) - 1
            created = False
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(
                        component,
                        mode=final_mode if is_final else 0o777,
                        dir_fd=descriptor,
                    )
                    created = True
                except FileExistsError:
                    pass
                try:
                    child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
                except OSError as exc:
                    raise UnsafePathError(
                        "directory cannot be opened without following symlinks"
                    ) from exc
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise UnsafePathError(
                        "directory ancestry cannot contain symlinks"
                    ) from exc
                raise
            opened = os.fstat(child)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(child)
                raise UnsafePathError("safe path component is not a directory")
            if created:
                os.fsync(child)
                os.fsync(descriptor)
                if is_final:
                    final_created = True
            os.close(descriptor)
            descriptor = child
        return absolute, descriptor, final_created
    except BaseException:
        os.close(descriptor)
        raise


def open_file_no_symlinks(
    path: str | os.PathLike[str],
    flags: int,
    *,
    mode: int = 0o600,
) -> tuple[Path, int, int]:
    """Open a file relative to a safely opened lexical parent directory."""

    absolute = _absolute(path)
    if absolute.name in {"", ".", ".."}:
        raise UnsafePathError("safe file path has no final name")
    _, parent_fd, _ = open_directory_no_symlinks(absolute.parent)
    try:
        descriptor = os.open(
            absolute.name,
            flags | _FILE_BASE_FLAGS,
            mode,
            dir_fd=parent_fd,
        )
    except BaseException:
        os.close(parent_fd)
        raise
    return absolute, parent_fd, descriptor


def verify_file_path_binding(
    path: str | os.PathLike[str],
    *,
    parent_fd: int,
    file_fd: int,
    flags: int = os.O_RDONLY,
) -> None:
    """Require the lexical parent and final name to retain their opened identities."""

    absolute = _absolute(path)
    _, rebound_parent_fd, _ = open_directory_no_symlinks(absolute.parent)
    try:
        if not same_identity(os.fstat(parent_fd), os.fstat(rebound_parent_fd)):
            raise UnsafePathError("safe file parent identity changed")
        rebound_file_fd = os.open(
            absolute.name,
            flags | _FILE_BASE_FLAGS,
            dir_fd=rebound_parent_fd,
        )
        try:
            if not same_identity(os.fstat(file_fd), os.fstat(rebound_file_fd)):
                raise UnsafePathError("safe file path identity changed")
        finally:
            os.close(rebound_file_fd)
    finally:
        os.close(rebound_parent_fd)


__all__ = [
    "UnsafePathError",
    "open_directory_no_symlinks",
    "open_file_no_symlinks",
    "same_identity",
    "verify_file_path_binding",
]
