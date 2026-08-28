"""Digest- and inode-guarded workspace transformations using directory FDs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import difflib
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import threading
from typing import Any, Iterator, Sequence
import unicodedata


class TransformationError(RuntimeError):
    pass


class TransformationConflict(TransformationError):
    pass


class UnsafeTransformationPath(TransformationError):
    pass


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    expected_digest: str | None
    new_content: bytes | None
    mode: int = 0o644

    @classmethod
    def text(
        cls,
        path: str,
        new_content: str | None,
        *,
        expected_digest: str | None,
        mode: int = 0o644,
    ) -> "FileChange":
        return cls(
            path,
            expected_digest,
            None if new_content is None else new_content.encode("utf-8"),
            mode,
        )

    @property
    def operation(self) -> str:
        if self.new_content is None:
            return "delete"
        if self.expected_digest is None:
            return "create"
        return "replace"

    @property
    def new_digest(self) -> str | None:
        return (
            hashlib.sha256(self.new_content).hexdigest()
            if self.new_content is not None
            else None
        )

    def __post_init__(self) -> None:
        _normalize(self.path)
        if self.expected_digest is not None and (
            len(self.expected_digest) != 64
            or any(
                char not in "0123456789abcdef" for char in self.expected_digest
            )
        ):
            raise ValueError("expected_digest must be lowercase SHA-256")
        if self.new_content is None and self.expected_digest is None:
            raise ValueError("delete requires an expected digest")
        if self.mode < 0 or self.mode > 0o777:
            raise ValueError("mode must be a permission mask")


@dataclass(frozen=True, slots=True)
class ChangeSet:
    changes: tuple[FileChange, ...]
    reason: str
    request_id: str

    def __post_init__(self) -> None:
        if not self.changes:
            raise ValueError("change set cannot be empty")
        normalized = [_normalize(change.path) for change in self.changes]
        collision_keys = [
            unicodedata.normalize("NFC", path).casefold() for path in normalized
        ]
        if len(set(normalized)) != len(normalized):
            raise ValueError("change set contains duplicate paths")
        if len(set(collision_keys)) != len(collision_keys):
            raise ValueError("change set contains casefold/NFC path collisions")
        if not self.reason or not self.request_id:
            raise ValueError("reason and request_id are required")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "changes": [
                    {
                        "path": _normalize(change.path),
                        "expected_digest": change.expected_digest,
                        "new_digest": change.new_digest,
                        "mode": change.mode,
                    }
                    for change in sorted(self.changes, key=lambda item: item.path)
                ],
                "reason": self.reason,
                "request_id": self.request_id,
            }
        )


@dataclass(frozen=True, slots=True)
class PlannedChange:
    path: str
    operation: str
    before_digest: str | None
    after_digest: str | None
    patch: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "operation": self.operation,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "patch": self.patch,
        }


@dataclass(frozen=True, slots=True)
class TransformationPlan:
    plan_id: str
    change_set_digest: str
    changes: tuple[PlannedChange, ...]
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "change_set_digest": self.change_set_digest,
            "dry_run": self.dry_run,
            "changes": [item.to_dict() for item in self.changes],
        }


@dataclass(frozen=True, slots=True)
class AppliedChange:
    path: str
    before_digest: str | None
    after_digest: str | None
    before_mode: int | None
    before_content: bytes | None = field(repr=False, compare=False)
    before_device: int | None = None
    before_inode: int | None = None
    after_device: int | None = None
    after_inode: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "before_mode": self.before_mode,
            "before_device": self.before_device,
            "before_inode": self.before_inode,
            "after_device": self.after_device,
            "after_inode": self.after_inode,
        }


@dataclass(frozen=True, slots=True)
class TransformationReceipt:
    receipt_id: str
    plan_id: str
    change_set_digest: str
    applied: tuple[AppliedChange, ...]
    rolled_back: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "plan_id": self.plan_id,
            "change_set_digest": self.change_set_digest,
            "rolled_back": self.rolled_back,
            "applied": [item.to_dict() for item in self.applied],
        }


@dataclass(frozen=True, slots=True)
class _CurrentFile:
    content: bytes
    mode: int
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @property
    def digest(self) -> str:
        return _bytes_digest(self.content)

    @property
    def identity(self) -> tuple[int, int, int, int, int]:
        return (
            self.device,
            self.inode,
            self.size,
            self.mtime_ns,
            self.ctime_ns,
        )


class WorkspaceTransformer:
    """Transactional, no-follow transformation within one exact root inode."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_change_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if os.name != "posix" or not getattr(os, "O_NOFOLLOW", 0):
            raise UnsafeTransformationPath(
                "safe directory-FD transformations are unsupported on this platform"
            )
        path = Path(root)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeTransformationPath(
                "workspace root must be a non-symlink directory"
            )
        if max_change_bytes <= 0:
            raise ValueError("max_change_bytes must be positive")
        self.root = path.resolve(strict=True)
        resolved = self.root.lstat()
        self._root_identity = (resolved.st_dev, resolved.st_ino)
        self.max_change_bytes = max_change_bytes
        self._lock = threading.RLock()

    def plan(self, change_set: ChangeSet) -> TransformationPlan:
        with self._workspace_lock(shared=True) as root_fd:
            return self._plan_unlocked(root_fd, change_set)

    def apply(self, change_set: ChangeSet) -> TransformationReceipt:
        with self._workspace_lock(shared=False) as root_fd:
            plan = self._plan_unlocked(root_fd, change_set)
            applied: list[AppliedChange] = []
            created_directories: list[str] = []
            try:
                for change in sorted(change_set.changes, key=lambda item: item.path):
                    path = _normalize(change.path)
                    opened = self._open_parent(root_fd, path, create=True)
                    assert opened is not None
                    parent_fd, leaf, created = opened
                    created_directories.extend(created)
                    try:
                        parent_identity = _directory_identity(os.fstat(parent_fd))
                        if not self._parent_binding_matches(
                            root_fd, path, parent_identity
                        ):
                            raise TransformationConflict(
                                f"parent path changed before mutation: {path}"
                            )
                        before = self._read_current_at(parent_fd, leaf, path)
                        before_digest = before.digest if before else None
                        self._verify_expected(change, before_digest)
                        if change.new_content is None:
                            assert before is not None
                            self._delete_exact_at(parent_fd, leaf, before, path)
                            after = None
                        else:
                            after = self._install_content_at(
                                parent_fd,
                                leaf,
                                change.new_content,
                                change.mode,
                                before,
                                path,
                            )
                        if not self._parent_binding_matches(
                            root_fd, path, parent_identity
                        ):
                            raise TransformationConflict(
                                f"parent path changed during mutation: {path}"
                            )
                        applied.append(
                            AppliedChange(
                                path=path,
                                before_digest=before_digest,
                                after_digest=change.new_digest,
                                before_mode=before.mode if before else None,
                                before_content=before.content if before else None,
                                before_device=before.device if before else None,
                                before_inode=before.inode if before else None,
                                after_device=after.device if after else None,
                                after_inode=after.inode if after else None,
                            )
                        )
                    finally:
                        os.close(parent_fd)
            except Exception:
                self._restore(
                    root_fd,
                    tuple(reversed(applied)),
                    created_directories,
                    check_current=True,
                )
                raise
            receipt_id = "receipt:sha256:" + _digest(
                {
                    "plan": plan.plan_id,
                    "applied": [item.to_dict() for item in applied],
                }
            )
            return TransformationReceipt(
                receipt_id,
                plan.plan_id,
                change_set.digest,
                tuple(applied),
            )

    def _plan_unlocked(
        self,
        root_fd: int,
        change_set: ChangeSet,
    ) -> TransformationPlan:
        planned: list[PlannedChange] = []
        total = 0
        for change in sorted(change_set.changes, key=lambda item: item.path):
            path = _normalize(change.path)
            opened = self._open_parent(root_fd, path, create=False)
            if opened is None:
                before = None
            else:
                parent_fd, leaf, _ = opened
                try:
                    before = self._read_current_at(parent_fd, leaf, path)
                finally:
                    os.close(parent_fd)
            before_digest = before.digest if before else None
            self._verify_expected(change, before_digest)
            if change.new_content is not None:
                total += len(change.new_content)
                if total > self.max_change_bytes:
                    raise TransformationError("change set exceeds max_change_bytes")
            planned.append(
                PlannedChange(
                    path,
                    change.operation,
                    before_digest,
                    change.new_digest,
                    _make_patch(
                        path,
                        before.content if before else None,
                        change.new_content,
                    ),
                )
            )
        plan_id = "plan:sha256:" + _digest(
            {
                "change_set": change_set.digest,
                "changes": [item.to_dict() for item in planned],
            }
        )
        return TransformationPlan(plan_id, change_set.digest, tuple(planned))

    def rollback(self, receipt: TransformationReceipt) -> TransformationReceipt:
        if receipt.rolled_back:
            return receipt
        with self._workspace_lock(shared=False) as root_fd:
            self._restore(
                root_fd,
                tuple(reversed(receipt.applied)),
                (),
                check_current=True,
            )
            return TransformationReceipt(
                receipt.receipt_id,
                receipt.plan_id,
                receipt.change_set_digest,
                receipt.applied,
                True,
            )

    def _restore(
        self,
        root_fd: int,
        items: Sequence[AppliedChange],
        created_directories: Sequence[str],
        *,
        check_current: bool,
    ) -> None:
        for item in items:
            opened = self._open_parent(root_fd, item.path, create=True)
            assert opened is not None
            parent_fd, leaf, _ = opened
            try:
                current = self._read_current_at(parent_fd, leaf, item.path)
                current_digest = current.digest if current else None
                if check_current and current_digest != item.after_digest:
                    raise TransformationConflict(
                        f"cannot rollback modified path {item.path}: "
                        f"expected {item.after_digest}, got {current_digest}"
                    )
                if check_current and current is not None and (
                    current.device != item.after_device
                    or current.inode != item.after_inode
                ):
                    raise TransformationConflict(
                        f"cannot rollback inode-replaced path {item.path}"
                    )
                if item.before_content is None:
                    if current is not None:
                        self._delete_exact_at(parent_fd, leaf, current, item.path)
                else:
                    self._install_content_at(
                        parent_fd,
                        leaf,
                        item.before_content,
                        item.before_mode or 0o644,
                        current,
                        item.path,
                    )
            finally:
                os.close(parent_fd)
        for directory in sorted(
            set(created_directories),
            key=lambda value: len(PurePosixPath(value).parts),
            reverse=True,
        ):
            self._remove_empty_directory(root_fd, directory)

    @staticmethod
    def _verify_expected(
        change: FileChange,
        current_digest: str | None,
    ) -> None:
        if change.expected_digest is None:
            if current_digest is not None:
                raise TransformationConflict(
                    f"create target already exists: {change.path}"
                )
        elif current_digest != change.expected_digest:
            raise TransformationConflict(
                f"digest conflict for {change.path}: "
                f"expected {change.expected_digest}, got {current_digest}"
            )

    def _open_parent(
        self,
        root_fd: int,
        relative: str,
        *,
        create: bool,
    ) -> tuple[int, str, tuple[str, ...]] | None:
        parts = PurePosixPath(_normalize(relative)).parts
        current = os.dup(root_fd)
        created: list[str] = []
        accumulated: list[str] = []
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        try:
            for part in parts[:-1]:
                accumulated.append(part)
                try:
                    next_fd = os.open(part, flags, dir_fd=current)
                except FileNotFoundError:
                    if not create:
                        os.close(current)
                        return None
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=current)
                    except FileExistsError:
                        pass
                    os.fsync(current)
                    try:
                        next_fd = os.open(part, flags, dir_fd=current)
                    except OSError as exc:
                        raise UnsafeTransformationPath(
                            f"cannot safely open created parent {relative}: {exc}"
                        ) from exc
                    created.append("/".join(accumulated))
                except OSError as exc:
                    raise UnsafeTransformationPath(
                        f"unsafe parent path for {relative}: {exc}"
                    ) from exc
                metadata = os.fstat(next_fd)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(next_fd)
                    raise UnsafeTransformationPath(
                        f"parent is not a directory: {relative}"
                    )
                os.close(current)
                current = next_fd
            return current, parts[-1], tuple(created)
        except Exception:
            try:
                os.close(current)
            except OSError:
                pass
            raise

    def _read_current_at(
        self,
        parent_fd: int,
        leaf: str,
        display_path: str,
    ) -> _CurrentFile | None:
        try:
            descriptor = os.open(
                leaf,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise UnsafeTransformationPath(
                f"cannot safely read target {display_path}: {exc}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise UnsafeTransformationPath(
                    f"target is not a regular file: {display_path}"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_change_bytes:
                    raise TransformationError(
                        f"existing file exceeds max_change_bytes: {display_path}"
                    )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if _file_identity(before) != _file_identity(after):
                raise TransformationConflict(
                    f"target changed during read: {display_path}"
                )
            content = b"".join(chunks)
            if len(content) != after.st_size:
                raise TransformationConflict(
                    f"target size changed during read: {display_path}"
                )
            return _CurrentFile(
                content,
                stat.S_IMODE(after.st_mode),
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        finally:
            os.close(descriptor)

    def _install_content_at(
        self,
        parent_fd: int,
        leaf: str,
        content: bytes,
        mode: int,
        expected_current: _CurrentFile | None,
        display_path: str,
    ) -> _CurrentFile:
        temporary = self._write_temporary(parent_fd, content, mode)
        backup: str | None = None
        try:
            if expected_current is not None:
                self._verify_target_identity(
                    parent_fd, leaf, expected_current, display_path
                )
                backup = self._reserve_name(parent_fd, ".elmos-backup-")
                os.rename(
                    leaf,
                    backup,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                moved = self._read_current_at(parent_fd, backup, display_path)
                if moved is None or (
                    (moved.device, moved.inode)
                    != (expected_current.device, expected_current.inode)
                    or moved.digest != expected_current.digest
                ):
                    self._restore_moved_entry(parent_fd, backup, leaf, display_path)
                    backup = None
                    raise TransformationConflict(
                        f"target inode changed before replace: {display_path}"
                    )
            try:
                os.link(
                    temporary,
                    leaf,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                if backup is not None:
                    self._restore_moved_entry(
                        parent_fd, backup, leaf, display_path
                    )
                    backup = None
                raise TransformationConflict(
                    f"target was concurrently created: {display_path}"
                ) from exc
            os.unlink(temporary, dir_fd=parent_fd)
            temporary = ""
            installed = self._read_current_at(parent_fd, leaf, display_path)
            if installed is None or installed.digest != _bytes_digest(content):
                raise TransformationConflict(
                    f"installed bytes could not be verified: {display_path}"
                )
            if backup is not None:
                os.unlink(backup, dir_fd=parent_fd)
                backup = None
            os.fsync(parent_fd)
            return installed
        finally:
            if temporary:
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            if backup is not None:
                # Never silently discard the exact previous inode. Restore it
                # only when the canonical name is still unoccupied.
                self._restore_moved_entry(parent_fd, backup, leaf, display_path)

    def _delete_exact_at(
        self,
        parent_fd: int,
        leaf: str,
        expected: _CurrentFile,
        display_path: str,
    ) -> None:
        self._verify_target_identity(parent_fd, leaf, expected, display_path)
        backup = self._reserve_name(parent_fd, ".elmos-delete-")
        try:
            os.rename(
                leaf,
                backup,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            moved = self._read_current_at(parent_fd, backup, display_path)
            if moved is None or (
                (moved.device, moved.inode) != (expected.device, expected.inode)
                or moved.digest != expected.digest
            ):
                self._restore_moved_entry(parent_fd, backup, leaf, display_path)
                backup = ""
                raise TransformationConflict(
                    f"target inode changed before delete: {display_path}"
                )
            try:
                os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                self._restore_moved_entry(parent_fd, backup, leaf, display_path)
                backup = ""
                raise TransformationConflict(
                    f"target was concurrently recreated: {display_path}"
                )
            os.unlink(backup, dir_fd=parent_fd)
            backup = ""
            os.fsync(parent_fd)
        finally:
            if backup:
                self._restore_moved_entry(parent_fd, backup, leaf, display_path)

    @staticmethod
    def _verify_target_identity(
        parent_fd: int,
        leaf: str,
        expected: _CurrentFile,
        display_path: str,
    ) -> None:
        try:
            current = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise TransformationConflict(
                f"target disappeared before mutation: {display_path}"
            ) from exc
        if not stat.S_ISREG(current.st_mode) or _file_identity(current) != expected.identity:
            raise TransformationConflict(
                f"target inode changed before mutation: {display_path}"
            )

    @staticmethod
    def _write_temporary(parent_fd: int, content: bytes, mode: int) -> str:
        temporary = WorkspaceTransformer._reserve_name(
            parent_fd, ".elmos-transform-"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        except Exception:
            os.close(descriptor)
            os.unlink(temporary, dir_fd=parent_fd)
            raise
        os.close(descriptor)
        return temporary

    @staticmethod
    def _reserve_name(parent_fd: int, prefix: str) -> str:
        for _ in range(128):
            name = prefix + secrets.token_hex(16)
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            os.close(descriptor)
            return name
        raise TransformationError("could not allocate a safe temporary name")

    @staticmethod
    def _restore_moved_entry(
        parent_fd: int,
        backup: str,
        leaf: str,
        display_path: str,
    ) -> None:
        try:
            os.link(
                backup,
                leaf,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise TransformationConflict(
                f"cannot restore previous inode because target is occupied: {display_path}"
            ) from exc
        os.unlink(backup, dir_fd=parent_fd)
        os.fsync(parent_fd)

    def _parent_binding_matches(
        self,
        root_fd: int,
        relative: str,
        expected: tuple[int, int],
    ) -> bool:
        try:
            opened = self._open_parent(root_fd, relative, create=False)
        except UnsafeTransformationPath:
            return False
        if opened is None:
            return False
        descriptor, _, _ = opened
        try:
            return _directory_identity(os.fstat(descriptor)) == expected
        finally:
            os.close(descriptor)

    def _remove_empty_directory(self, root_fd: int, relative: str) -> None:
        parent_relative = PurePosixPath(relative).parent.as_posix()
        leaf = PurePosixPath(relative).name
        if parent_relative == ".":
            parent_fd = os.dup(root_fd)
        else:
            opened = self._open_parent(
                root_fd,
                parent_relative + "/placeholder",
                create=False,
            )
            if opened is None:
                return
            parent_fd, _, _ = opened
        try:
            try:
                os.rmdir(leaf, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError as exc:
                if exc.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
                    raise
        finally:
            os.close(parent_fd)

    @contextmanager
    def _workspace_lock(self, *, shared: bool) -> Iterator[int]:
        with self._lock:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
            root_fd = os.open(self.root, flags)
            try:
                if _directory_identity(os.fstat(root_fd)) != self._root_identity:
                    raise UnsafeTransformationPath(
                        "workspace root identity changed"
                    )
                try:
                    import fcntl
                except ImportError:
                    fcntl = None  # type: ignore[assignment]
                if fcntl is not None:
                    fcntl.flock(
                        root_fd,
                        fcntl.LOCK_SH if shared else fcntl.LOCK_EX,
                    )
                yield root_fd
                if _directory_identity(os.fstat(root_fd)) != self._root_identity:
                    raise UnsafeTransformationPath(
                        "workspace root identity changed during operation"
                    )
            finally:
                if "fcntl" in locals() and fcntl is not None:
                    fcntl.flock(root_fd, fcntl.LOCK_UN)
                os.close(root_fd)


def _normalize(path: str) -> str:
    raw = path.replace("\\", "/")
    candidate = PurePosixPath(raw)
    if (
        not raw
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or "\x00" in raw
    ):
        raise UnsafeTransformationPath(f"unsafe relative path: {path!r}")
    return candidate.as_posix()


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _bytes_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _make_patch(path: str, before: bytes | None, after: bytes | None) -> str:
    before_bytes = before or b""
    after_bytes = after or b""
    try:
        before_text = before_bytes.decode("utf-8")
        after_text = after_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return (
            f"Binary files differ: sha256:{_bytes_digest(before_bytes)} -> "
            f"sha256:{_bytes_digest(after_bytes)}"
        )
    return "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}" if before is not None else "/dev/null",
            tofile=f"b/{path}" if after is not None else "/dev/null",
            lineterm="\n",
        )
    )


__all__ = [
    "AppliedChange",
    "ChangeSet",
    "FileChange",
    "PlannedChange",
    "TransformationConflict",
    "TransformationError",
    "TransformationPlan",
    "TransformationReceipt",
    "UnsafeTransformationPath",
    "WorkspaceTransformer",
]
