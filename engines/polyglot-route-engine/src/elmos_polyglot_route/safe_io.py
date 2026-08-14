"""Bounded, no-follow file I/O for conversion evidence and artifacts."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from .models import RouteError


def _validate_parent(path: Path, error_code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise RouteError(error_code)


def _validate_destination(path: Path, error_code: str) -> None:
    if path.is_symlink():
        raise RouteError(error_code)
    if path.exists():
        status = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise RouteError(error_code)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def atomic_output_file(
    path: Path,
    *,
    max_bytes: int,
    unsafe_error: str,
    limit_error: str,
) -> Iterator[BinaryIO]:
    """Yield a private same-directory file and atomically publish it on success."""

    _validate_parent(path, unsafe_error)
    _validate_destination(path, unsafe_error)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    handle = os.fdopen(descriptor, "w+b")
    published = False
    try:
        os.fchmod(handle.fileno(), 0o600)
        yield handle
        handle.flush()
        os.fsync(handle.fileno())
        status = os.fstat(handle.fileno())
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise RouteError(unsafe_error)
        if status.st_size > max_bytes:
            raise RouteError(limit_error)
        handle.close()
        _validate_destination(path, unsafe_error)
        os.replace(temporary, path)
        published = True
        _fsync_directory(path.parent)
        final_status = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not stat.S_ISREG(final_status.st_mode)
            or final_status.st_nlink != 1
            or final_status.st_size != status.st_size
        ):
            raise RouteError(unsafe_error)
    finally:
        if not handle.closed:
            handle.close()
        if not published and os.path.lexists(temporary):
            temporary.unlink()


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    max_bytes: int,
    unsafe_error: str,
    limit_error: str,
) -> None:
    if len(content) > max_bytes:
        raise RouteError(limit_error)
    with atomic_output_file(
        path,
        max_bytes=max_bytes,
        unsafe_error=unsafe_error,
        limit_error=limit_error,
    ) as handle:
        written = handle.write(content)
        if written != len(content):
            raise RouteError(unsafe_error)


def _open_stable(path: Path, *, max_bytes: int, unsafe_error: str, limit_error: str) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RouteError(unsafe_error) from error
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
        os.close(descriptor)
        raise RouteError(unsafe_error)
    if status.st_size > max_bytes:
        os.close(descriptor)
        raise RouteError(limit_error)
    return descriptor, status


def _verify_stable_path(path: Path, before: os.stat_result, descriptor: int, changed_error: str) -> None:
    after = os.fstat(descriptor)
    try:
        current = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RouteError(changed_error) from error
    def identity(value: os.stat_result) -> tuple[int, int, int, int]:
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns

    if identity(before) != identity(after) or identity(before) != identity(current):
        raise RouteError(changed_error)


def stable_file_digest(
    path: Path,
    *,
    max_bytes: int,
    unsafe_error: str,
    changed_error: str,
    limit_error: str,
) -> tuple[int, str]:
    descriptor, before = _open_stable(
        path,
        max_bytes=max_bytes,
        unsafe_error=unsafe_error,
        limit_error=limit_error,
    )
    digest = hashlib.sha256()
    observed = 0
    try:
        while chunk := os.read(descriptor, 64 * 1024):
            observed += len(chunk)
            if observed > max_bytes:
                raise RouteError(limit_error)
            digest.update(chunk)
        _verify_stable_path(path, before, descriptor, changed_error)
    finally:
        os.close(descriptor)
    if observed != before.st_size:
        raise RouteError(changed_error)
    return observed, digest.hexdigest()


def stable_read_bytes(
    path: Path,
    *,
    max_bytes: int,
    unsafe_error: str,
    changed_error: str,
    limit_error: str,
) -> bytes:
    descriptor, before = _open_stable(
        path,
        max_bytes=max_bytes,
        unsafe_error=unsafe_error,
        limit_error=limit_error,
    )
    content = bytearray()
    try:
        while chunk := os.read(descriptor, 64 * 1024):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise RouteError(limit_error)
        _verify_stable_path(path, before, descriptor, changed_error)
    finally:
        os.close(descriptor)
    if len(content) != before.st_size:
        raise RouteError(changed_error)
    return bytes(content)
