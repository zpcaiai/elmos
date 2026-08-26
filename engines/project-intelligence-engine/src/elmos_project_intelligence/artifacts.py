"""Private content-addressed artifact store for Project Intelligence results.

This store is intentionally scoped to the new engine and does not depend on or
modify the shared ELMOS CAS modules. Objects are immutable, digest-verified,
atomically promoted, and never executed.
"""

from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import secrets
import stat
from typing import Iterator

from .safe_paths import open_directory_no_symlinks, same_identity


class ArtifactStoreError(RuntimeError):
    """Raised when an artifact path or object violates the CAS contract."""


def _digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


class ContentAddressedArtifactStore:
    """Small immutable filesystem CAS with descriptor-relative promotion."""

    _DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    _FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW

    def __init__(self, root: str | Path) -> None:
        try:
            self.root, root_fd, created = open_directory_no_symlinks(
                root, create=True, final_mode=0o700
            )
        except OSError as exc:
            raise ArtifactStoreError("artifact root cannot be opened safely") from exc
        try:
            if created:
                os.fchmod(root_fd, 0o700)
            root_stat = self._validate_private_directory(root_fd, "artifact root")
            self._root_identity = (root_stat.st_dev, root_stat.st_ino)
            if created:
                os.fsync(root_fd)

            objects_fd = self._open_directory_at(root_fd, "objects", create=True)
            try:
                sha_fd = self._open_directory_at(objects_fd, "sha256", create=True)
                os.close(sha_fd)
            finally:
                os.close(objects_fd)
        finally:
            os.close(root_fd)
        self.objects = self.root / "objects" / "sha256"

    @staticmethod
    def _validate_private_directory(descriptor: int, label: str) -> os.stat_result:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ArtifactStoreError(f"{label} must be a directory")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ArtifactStoreError(
                f"{label} must not be accessible by group or other"
            )
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise ArtifactStoreError(f"{label} must be owned by the current user")
        return metadata

    @classmethod
    def _open_directory_at(cls, parent_fd: int, name: str, *, create: bool) -> int:
        created = False
        try:
            descriptor = os.open(name, cls._DIRECTORY_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            if not create:
                raise
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                created = True
            except FileExistsError:
                pass
            try:
                descriptor = os.open(name, cls._DIRECTORY_FLAGS, dir_fd=parent_fd)
            except OSError as exc:
                raise ArtifactStoreError(
                    "artifact directory cannot be opened safely"
                ) from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise ArtifactStoreError(
                    "artifact directory ancestry contains a symlink"
                ) from exc
            raise ArtifactStoreError(
                "artifact directory cannot be opened safely"
            ) from exc
        try:
            if created:
                os.fchmod(descriptor, 0o700)
            cls._validate_private_directory(descriptor, "artifact directory")
            if created:
                os.fsync(descriptor)
                os.fsync(parent_fd)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    @contextmanager
    def _sha_directory(self) -> Iterator[int]:
        try:
            _, root_fd, _ = open_directory_no_symlinks(self.root)
        except OSError as exc:
            raise ArtifactStoreError("artifact root cannot be reopened safely") from exc
        try:
            root_stat = self._validate_private_directory(root_fd, "artifact root")
            if (root_stat.st_dev, root_stat.st_ino) != self._root_identity:
                raise ArtifactStoreError("artifact root identity changed")
            objects_fd = self._open_directory_at(root_fd, "objects", create=False)
            try:
                sha_fd = self._open_directory_at(objects_fd, "sha256", create=False)
                try:
                    sha_stat = os.fstat(sha_fd)
                    yield sha_fd
                    rebound_objects_fd = self._open_directory_at(
                        root_fd, "objects", create=False
                    )
                    try:
                        rebound_sha_fd = self._open_directory_at(
                            rebound_objects_fd, "sha256", create=False
                        )
                        try:
                            rebound_sha_stat = os.fstat(rebound_sha_fd)
                            if (
                                rebound_sha_stat.st_dev,
                                rebound_sha_stat.st_ino,
                            ) != (sha_stat.st_dev, sha_stat.st_ino):
                                raise ArtifactStoreError(
                                    "artifact directory identity changed"
                                )
                        finally:
                            os.close(rebound_sha_fd)
                    finally:
                        os.close(rebound_objects_fd)
                    try:
                        _, rebound_root_fd, _ = open_directory_no_symlinks(self.root)
                    except OSError as exc:
                        raise ArtifactStoreError(
                            "artifact root cannot be rebound safely"
                        ) from exc
                    try:
                        if not same_identity(
                            os.fstat(root_fd), os.fstat(rebound_root_fd)
                        ):
                            raise ArtifactStoreError("artifact root identity changed")
                    finally:
                        os.close(rebound_root_fd)
                finally:
                    os.close(sha_fd)
            finally:
                os.close(objects_fd)
        finally:
            os.close(root_fd)

    @staticmethod
    def _digest_parts(digest: str) -> tuple[str, str]:
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ArtifactStoreError("artifact digest must use sha256:<hex>")
        value = digest.removeprefix("sha256:")
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ArtifactStoreError("artifact digest is malformed")
        return value[:2], value[2:]

    def _path(self, digest: str) -> Path:
        prefix, name = self._digest_parts(digest)
        return self.objects / prefix / name

    @classmethod
    def _verify_directory_binding(
        cls, parent_fd: int, name: str, expected_fd: int
    ) -> None:
        rebound_fd = cls._open_directory_at(parent_fd, name, create=False)
        try:
            expected = os.fstat(expected_fd)
            rebound = os.fstat(rebound_fd)
            if (expected.st_dev, expected.st_ino) != (rebound.st_dev, rebound.st_ino):
                raise ArtifactStoreError("artifact digest directory identity changed")
        finally:
            os.close(rebound_fd)

    @classmethod
    def _read_file_at(cls, parent_fd: int, name: str, digest: str) -> bytes | None:
        try:
            descriptor = os.open(name, cls._FILE_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ArtifactStoreError("artifact object cannot be opened safely") from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ArtifactStoreError("artifact object is not a regular file")
            if stat.S_IMODE(before.st_mode) != 0o600:
                raise ArtifactStoreError("artifact object mode must be 0600")
            if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
                raise ArtifactStoreError(
                    "artifact object must be owned by the current user"
                )
            if before.st_nlink != 1:
                raise ArtifactStoreError(
                    "artifact object must have exactly one filesystem link"
                )
            captured = bytearray()
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                captured.extend(chunk)
            after = os.fstat(descriptor)
            stable_before = (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_size,
                before.st_nlink,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            stable_after = (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_nlink,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if (
                stable_before != stable_after
                or after.st_nlink != 1
                or len(captured) != before.st_size
            ):
                raise ArtifactStoreError("artifact object changed while it was read")
            content = bytes(captured)
            observed = _digest_bytes(content)
            if observed != digest:
                raise ArtifactStoreError(
                    f"artifact digest mismatch: expected={digest} actual={observed}"
                )
            return content
        finally:
            os.close(descriptor)

    @classmethod
    def _create_temporary_at(cls, parent_fd: int) -> tuple[int, str]:
        for _ in range(64):
            name = f".artifact-{secrets.token_hex(16)}"
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            return descriptor, name
        raise ArtifactStoreError("cannot allocate a unique artifact temporary file")

    def put(self, content: bytes) -> str:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        digest = _digest_bytes(content)
        prefix, name = self._digest_parts(digest)
        with self._sha_directory() as sha_fd:
            prefix_fd = self._open_directory_at(sha_fd, prefix, create=True)
            try:
                observed = self._read_file_at(prefix_fd, name, digest)
                if observed is not None:
                    if observed != content:
                        raise ArtifactStoreError(
                            "existing content-addressed artifact is corrupt"
                        )
                    self._verify_directory_binding(sha_fd, prefix, prefix_fd)
                    return digest

                descriptor, temporary_name = self._create_temporary_at(prefix_fd)
                temporary_exists = True
                try:
                    try:
                        remaining = memoryview(content)
                        while remaining:
                            written = os.write(descriptor, remaining)
                            if written <= 0:
                                raise ArtifactStoreError(
                                    "artifact write made no progress"
                                )
                            remaining = remaining[written:]
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)

                    try:
                        os.link(
                            temporary_name,
                            name,
                            src_dir_fd=prefix_fd,
                            dst_dir_fd=prefix_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        concurrent = self._read_file_at(prefix_fd, name, digest)
                        if concurrent != content:
                            raise ArtifactStoreError(
                                "concurrent artifact promotion produced different bytes"
                            )
                    os.unlink(temporary_name, dir_fd=prefix_fd)
                    temporary_exists = False
                    os.fsync(prefix_fd)
                    self._verify_directory_binding(sha_fd, prefix, prefix_fd)
                finally:
                    if temporary_exists:
                        try:
                            os.unlink(temporary_name, dir_fd=prefix_fd)
                            os.fsync(prefix_fd)
                        except FileNotFoundError:
                            pass
            finally:
                os.close(prefix_fd)
        return digest

    def _read_digest(self, digest: str) -> bytes | None:
        prefix, name = self._digest_parts(digest)
        with self._sha_directory() as sha_fd:
            try:
                prefix_fd = self._open_directory_at(sha_fd, prefix, create=False)
            except FileNotFoundError:
                return None
            try:
                content = self._read_file_at(prefix_fd, name, digest)
                self._verify_directory_binding(sha_fd, prefix, prefix_fd)
                return content
            finally:
                os.close(prefix_fd)

    def read(self, digest: str) -> bytes:
        content = self._read_digest(digest)
        if content is None:
            raise ArtifactStoreError(f"artifact is missing: {self._path(digest)}")
        return content

    def contains(self, digest: str) -> bool:
        return self._read_digest(digest) is not None


__all__ = ["ArtifactStoreError", "ContentAddressedArtifactStore"]
