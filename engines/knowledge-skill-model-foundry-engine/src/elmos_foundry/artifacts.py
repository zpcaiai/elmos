"""Tenant/project-isolated private content-addressed artifact storage."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import os
from pathlib import Path
import secrets
import stat

from .canonical import canonical_digest, digest_bytes, validate_digest
from .domain import ContentDigest, TenantScope


class ArtifactStoreError(RuntimeError):
    pass


class ArtifactSecurityError(ArtifactStoreError):
    pass


class ArtifactIntegrityError(ArtifactStoreError):
    pass


class ArtifactNotFound(ArtifactStoreError):
    pass


DEFAULT_MAX_OBJECT_BYTES = 64 * 1024 * 1024


class ContentAddressedArtifactStore:
    READ_CAPABILITY = "foundry.artifact.read"
    WRITE_CAPABILITY = "foundry.artifact.write"

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        context_verifier: Callable[[TenantScope, str | None], TenantScope] | None,
        max_object_bytes: int = DEFAULT_MAX_OBJECT_BYTES,
    ) -> None:
        if (
            not isinstance(max_object_bytes, int)
            or isinstance(max_object_bytes, bool)
            or not 1 <= max_object_bytes <= 1024**3
        ):
            raise ValueError("max_object_bytes must be in [1, 1 GiB]")
        raw = Path(root).expanduser()
        if raw.exists() and raw.is_symlink():
            raise ArtifactSecurityError("artifact root must not be a symbolic link")
        self.root = raw.resolve(strict=False)
        self._verifier = context_verifier
        self.max_object_bytes = max_object_bytes
        self._ensure_directory(self.root)

    @staticmethod
    def _ensure_directory(path: Path) -> None:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        status = os.lstat(path)
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.geteuid()
            or stat.S_IMODE(status.st_mode) != 0o700
        ):
            raise ArtifactSecurityError(
                "artifact directories must be current-user real directories with mode 0700"
            )

    @staticmethod
    def _validate_file(status: os.stat_result) -> None:
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.geteuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
        ):
            raise ArtifactSecurityError(
                "artifact must be a current-user regular file with nlink=1 and mode 0600"
            )

    def _authorize(self, scope: TenantScope, capability: str) -> TenantScope:
        if self._verifier is None:
            raise ArtifactSecurityError("no trusted context verifier is configured")
        try:
            verified = self._verifier(scope, capability)
        except Exception as exc:
            raise ArtifactSecurityError("host context verification failed") from exc
        if (
            not isinstance(verified, TenantScope)
            or not verified.authenticated
            or verified.binding_digest != scope.binding_digest
        ):
            raise ArtifactSecurityError("context verifier returned a mismatched scope")
        return verified

    def _path(self, scope: TenantScope, digest: ContentDigest, *, create: bool) -> Path:
        namespace = canonical_digest(
            {
                "schema_version": "elmos.foundry.artifact-namespace.v1",
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
            }
        ).removeprefix("sha256:")
        directories = (
            self.root / namespace[:2],
            self.root / namespace[:2] / namespace,
            self.root / namespace[:2] / namespace / digest.value[:2],
        )
        if create:
            for directory in directories:
                self._ensure_directory(directory)
        return directories[-1] / digest.value

    @staticmethod
    def _digest(value: ContentDigest | str) -> ContentDigest:
        if isinstance(value, ContentDigest):
            return value
        validate_digest(value, "artifact_digest")
        return ContentDigest.parse(value)

    def put(
        self, scope: TenantScope, data: bytes, *, expected_digest: ContentDigest | str | None = None
    ) -> ContentDigest:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        if not isinstance(data, bytes):
            raise TypeError("artifact data must be immutable bytes")
        if len(data) > self.max_object_bytes:
            raise ArtifactStoreError("artifact exceeds configured object limit")
        observed = ContentDigest.of(data)
        if expected_digest is not None and self._digest(expected_digest) != observed:
            raise ArtifactIntegrityError("artifact does not match expected digest")
        destination = self._path(scope, observed, create=True)
        if destination.exists() or destination.is_symlink():
            self._verify(destination, observed)
            return observed
        temporary = destination.parent / f".tmp-{os.getpid()}-{secrets.token_hex(16)}"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = -1
        try:
            descriptor = os.open(temporary, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            view, offset = memoryview(data), 0
            while offset < len(view):
                written = os.write(descriptor, view[offset:])
                if written <= 0:
                    raise ArtifactStoreError("short artifact write")
                offset += written
            os.fsync(descriptor)
            if os.fstat(descriptor).st_size != len(data):
                raise ArtifactIntegrityError("artifact write length mismatch")
            os.close(descriptor)
            descriptor = -1
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError:
                self._verify(destination, observed)
            else:
                directory = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        self._verify(destination, observed)
        return observed

    def _verify(self, path: Path, digest: ContentDigest) -> None:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ArtifactSecurityError("cannot securely open artifact") from exc
        try:
            before = os.fstat(descriptor)
            self._validate_file(before)
            if before.st_size > self.max_object_bytes:
                raise ArtifactIntegrityError("stored artifact exceeds configured limit")
            hasher, size = hashlib.sha256(), 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_object_bytes:
                    raise ArtifactIntegrityError("stored artifact exceeds configured limit")
                hasher.update(chunk)
            if size != before.st_size or hasher.hexdigest() != digest.value:
                raise ArtifactIntegrityError("stored artifact digest or size mismatch")
            after = os.lstat(path)
            self._validate_file(after)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ArtifactSecurityError("artifact path identity changed")
        finally:
            os.close(descriptor)

    def read(self, scope: TenantScope, digest: ContentDigest | str) -> bytes:
        scope = self._authorize(scope, self.READ_CAPABILITY)
        parsed = self._digest(digest)
        path = self._path(scope, parsed, create=False)
        if not path.exists() and not path.is_symlink():
            raise ArtifactNotFound("artifact was not found in authenticated scope")
        self._verify(path, parsed)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            status = os.fstat(descriptor)
            self._validate_file(status)
            chunks, remaining = [], status.st_size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise ArtifactIntegrityError("artifact was truncated")
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if digest_bytes(data) != str(parsed):
                raise ArtifactIntegrityError("artifact changed during read")
            return data
        finally:
            os.close(descriptor)

    def contains(self, scope: TenantScope, digest: ContentDigest | str) -> bool:
        scope = self._authorize(scope, self.READ_CAPABILITY)
        parsed = self._digest(digest)
        path = self._path(scope, parsed, create=False)
        if not path.exists() and not path.is_symlink():
            return False
        self._verify(path, parsed)
        return True


ArtifactStore = ContentAddressedArtifactStore
__all__ = [
    "ArtifactIntegrityError",
    "ArtifactNotFound",
    "ArtifactSecurityError",
    "ArtifactStore",
    "ArtifactStoreError",
    "ContentAddressedArtifactStore",
    "DEFAULT_MAX_OBJECT_BYTES",
]
