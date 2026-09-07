"""Fail-closed local filesystem boundaries for durable engine state.

The helpers never resolve through symlinks.  They inspect every existing path
component with ``lstat``, require a trusted owner for every directory, and use
``O_NOFOLLOW`` descriptors for final identity checks.  SQLite still receives a
path string, so callers must re-check the returned descriptor identity after
opening the database connection.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class PathBoundaryError(RuntimeError):
    """A local state path escaped the owner-controlled boundary."""


@dataclass(frozen=True, slots=True)
class FileIdentity:
    device: int
    inode: int
    mode: int
    owner: int
    links: int


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def absolute_path(value: str | Path, *, label: str) -> Path:
    """Return a lexical absolute path without following any component."""

    if not isinstance(value, (str, Path)):
        raise PathBoundaryError(f"{label} must be text or Path")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise PathBoundaryError(f"{label} must be absolute")
    normalized = Path(os.path.normpath(os.fspath(candidate)))
    if normalized == Path(normalized.anchor):
        raise PathBoundaryError(f"{label} must not be a filesystem root")
    return normalized


def _require_nofollow() -> None:
    if not _NOFOLLOW:
        raise PathBoundaryError("O_NOFOLLOW is required for durable local state")


def _chain(path: Path) -> tuple[Path, ...]:
    current = Path(path.anchor)
    values = [current]
    for part in path.parts[1:]:
        current = current / part
        values.append(current)
    return tuple(values)


def _identity(info: os.stat_result) -> FileIdentity:
    return FileIdentity(
        device=info.st_dev,
        inode=info.st_ino,
        mode=info.st_mode,
        owner=info.st_uid,
        links=info.st_nlink,
    )


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _validate_directory_info(path: Path, info: os.stat_result, *, leaf: bool) -> None:
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PathBoundaryError(f"directory path component is not a real directory: {path}")
    current_uid = os.geteuid()
    if info.st_uid not in {0, current_uid}:
        raise PathBoundaryError(f"directory path component has an untrusted owner: {path}")
    writable_by_others = bool(info.st_mode & (stat.S_IWGRP | stat.S_IWOTH))
    trusted_sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
    if writable_by_others and not trusted_sticky_root:
        raise PathBoundaryError(f"directory path component is writable by another principal: {path}")
    if leaf and info.st_uid != current_uid:
        raise PathBoundaryError(f"state directory is not owned by the current user: {path}")


def _open_directory(path: Path, *, label: str) -> tuple[int, os.stat_result]:
    _require_nofollow()
    try:
        observed = os.lstat(path)
        _validate_directory_info(path, observed, leaf=False)
        descriptor = os.open(path, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
    except OSError as exc:
        raise PathBoundaryError(f"cannot securely open {label}: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not _same_object(observed, opened) or not stat.S_ISDIR(opened.st_mode):
            raise PathBoundaryError(f"{label} changed during validation: {path}")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor, opened


def _repository_roots() -> frozenset[Path]:
    roots: set[Path] = set()
    starts = (Path.cwd(), Path(__file__).absolute())
    for start in starts:
        directory = start if start.is_dir() else start.parent
        for candidate in (directory, *directory.parents):
            try:
                os.lstat(candidate / ".git")
            except OSError:
                continue
            roots.add(candidate)
    return frozenset(roots)


def _reject_protected_directory(path: Path, *, label: str) -> None:
    if path == Path.cwd() or path in _repository_roots():
        raise PathBoundaryError(f"{label} must not be the current working directory or a repository root")


def ensure_private_directory(
    value: str | Path,
    *,
    label: str,
    forbid_protected_root: bool = False,
    create: bool = True,
    tighten_mode: bool = True,
) -> tuple[Path, FileIdentity]:
    """Create a private directory component-by-component and bind its inode."""

    path = absolute_path(value, label=label)
    if forbid_protected_root:
        _reject_protected_directory(path, label=label)
    components = _chain(path)
    for index, component in enumerate(components):
        leaf = index == len(components) - 1
        try:
            info = os.lstat(component)
        except FileNotFoundError:
            if not create:
                raise PathBoundaryError(f"{label} component does not exist: {component}") from None
            try:
                os.mkdir(component, 0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise PathBoundaryError(f"cannot create {label} component: {component}") from exc
            try:
                info = os.lstat(component)
            except OSError as exc:
                raise PathBoundaryError(f"cannot inspect created {label} component: {component}") from exc
        except OSError as exc:
            raise PathBoundaryError(f"cannot inspect {label} component: {component}") from exc
        _validate_directory_info(component, info, leaf=leaf)
        descriptor, opened = _open_directory(component, label=label)
        try:
            if leaf:
                if tighten_mode:
                    os.fchmod(descriptor, 0o700)
                    opened = os.fstat(descriptor)
                if opened.st_mode & 0o077:
                    raise PathBoundaryError(f"{label} is not private: {component}")
        finally:
            os.close(descriptor)
    final_info = os.lstat(path)
    _validate_directory_info(path, final_info, leaf=True)
    return path, _identity(final_info)


def verify_directory_identity(path: Path, expected: FileIdentity, *, label: str) -> None:
    """Fail if a previously trusted directory path now names another inode."""

    for component in _chain(path):
        try:
            info = os.lstat(component)
        except OSError as exc:
            raise PathBoundaryError(f"cannot revalidate {label} component: {component}") from exc
        _validate_directory_info(component, info, leaf=component == path)
    descriptor, opened = _open_directory(path, label=label)
    try:
        if (opened.st_dev, opened.st_ino) != (expected.device, expected.inode):
            raise PathBoundaryError(f"{label} identity changed: {path}")
        if opened.st_uid != os.geteuid() or opened.st_mode & 0o077:
            raise PathBoundaryError(f"{label} is no longer private: {path}")
    finally:
        os.close(descriptor)


def _validate_regular_info(info: os.stat_result, *, label: str) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise PathBoundaryError(f"{label} must be a regular file")
    if info.st_uid != os.geteuid():
        raise PathBoundaryError(f"{label} must be owned by the current user")
    if info.st_nlink != 1:
        raise PathBoundaryError(f"{label} must not be hard linked")


def open_owned_regular(
    value: str | Path,
    *,
    label: str,
    create: bool,
    read_only: bool = False,
) -> tuple[Path, int, FileIdentity, bool]:
    """Open one owner-only regular file without following the final component."""

    path = absolute_path(value, label=label)
    ensure_private_directory(
        path.parent,
        label=f"{label} parent",
        create=not read_only,
        tighten_mode=not read_only,
    )
    _require_nofollow()
    access = os.O_RDONLY if read_only else os.O_RDWR
    created = False
    try:
        observed = os.lstat(path)
    except FileNotFoundError:
        if not create or read_only:
            raise PathBoundaryError(f"{label} does not exist") from None
        try:
            descriptor = os.open(path, access | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
            created = True
        except FileExistsError:
            try:
                observed = os.lstat(path)
                descriptor = os.open(path, access | _NOFOLLOW)
            except OSError as exc:
                raise PathBoundaryError(f"cannot securely open raced {label}") from exc
        except OSError as exc:
            raise PathBoundaryError(f"cannot securely create {label}") from exc
    except OSError as exc:
        raise PathBoundaryError(f"cannot inspect {label}") from exc
    else:
        if stat.S_ISLNK(observed.st_mode):
            raise PathBoundaryError(f"{label} must not be a symlink")
        _validate_regular_info(observed, label=label)
        try:
            descriptor = os.open(path, access | _NOFOLLOW)
        except OSError as exc:
            raise PathBoundaryError(f"cannot securely open {label}") from exc
    try:
        opened = os.fstat(descriptor)
        _validate_regular_info(opened, label=label)
        if not read_only:
            os.fchmod(descriptor, 0o600)
            opened = os.fstat(descriptor)
        elif opened.st_mode & 0o077:
            raise PathBoundaryError(f"read-only {label} must already be owner-only")
        identity = _identity(opened)
        verify_regular_identity(path, descriptor, identity, label=label)
    except Exception:
        os.close(descriptor)
        raise
    return path, descriptor, identity, created


def verify_regular_identity(
    path: Path,
    descriptor: int,
    expected: FileIdentity,
    *,
    label: str,
) -> None:
    """Compare path, held descriptor, ownership, mode and link count."""

    try:
        observed = os.lstat(path)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise PathBoundaryError(f"cannot revalidate {label}") from exc
    if stat.S_ISLNK(observed.st_mode):
        raise PathBoundaryError(f"{label} became a symlink")
    _validate_regular_info(observed, label=label)
    _validate_regular_info(opened, label=label)
    identities = {
        (observed.st_dev, observed.st_ino),
        (opened.st_dev, opened.st_ino),
        (expected.device, expected.inode),
    }
    if len(identities) != 1:
        raise PathBoundaryError(f"{label} identity changed during open")
    if observed.st_mode & 0o077 or opened.st_mode & 0o077:
        raise PathBoundaryError(f"{label} is not owner-only")


def read_regular_bytes(path: Path, *, label: str, maximum: int = 1_048_576) -> bytes:
    """Read a bounded owner-only regular file through its no-follow descriptor."""

    secured, descriptor, identity, _ = open_owned_regular(
        path,
        label=label,
        create=False,
        read_only=True,
    )
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise PathBoundaryError(f"{label} exceeds the bounded read limit")
        verify_regular_identity(secured, descriptor, identity, label=label)
        return b"".join(chunks)
    finally:
        os.close(descriptor)
