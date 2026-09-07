"""Content-addressed local artifact storage with no-follow path boundaries."""

from __future__ import annotations

import os
import secrets
import stat
import threading
from datetime import datetime
from pathlib import Path

from .canonical import digest_bytes, require_digest, verify_digest
from .contracts import Artifact, Scope, utc_now
from .errors import ContractError, IntegrityError, NotFoundError
from .trusted_paths import (
    FileIdentity,
    PathBoundaryError,
    ensure_private_directory,
    open_owned_regular,
    read_regular_bytes,
    verify_directory_identity,
    verify_regular_identity,
)

_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def _read_descriptor(descriptor: int, *, maximum: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise IntegrityError("artifact exceeds the bounded size limit", code="ARTIFACT_SIZE_LIMIT")
    return b"".join(chunks)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ContentAddressedArtifactStore:
    def __init__(self, root: str | Path) -> None:
        try:
            candidate, identity = ensure_private_directory(
                root,
                label="artifact root",
                forbid_protected_root=True,
            )
        except PathBoundaryError as exc:
            raise ContractError(str(exc), code="ARTIFACT_PATH_INVALID") from exc
        self.root = candidate
        self._root_identity: FileIdentity = identity
        self._lock = threading.RLock()
        self.__access_capability = object()

    def _assert_runtime_access(self, candidate: object) -> None:
        if candidate is not self.__access_capability:
            raise ContractError(
                "artifact access requires the authenticated runtime capability",
                code="ARTIFACT_ACCESS_CAPABILITY_REQUIRED",
            )

    def _verify_root(self) -> None:
        try:
            verify_directory_identity(self.root, self._root_identity, label="artifact root")
        except PathBoundaryError as exc:
            raise IntegrityError(str(exc), code="ARTIFACT_PATH_INVALID") from exc

    def _directory(self, path: Path, *, label: str) -> None:
        self._verify_root()
        try:
            ensure_private_directory(path, label=label)
        except PathBoundaryError as exc:
            raise IntegrityError(str(exc), code="ARTIFACT_PATH_INVALID") from exc
        self._verify_root()

    def _recover_linked_stage(self, target: Path, digest: str) -> bool:
        """Finish a publish interrupted after no-replace link creation."""

        try:
            target_info = os.lstat(target)
        except FileNotFoundError:
            return False
        if (
            not stat.S_ISREG(target_info.st_mode)
            or target_info.st_uid != os.geteuid()
            or target_info.st_nlink != 2
            or target_info.st_mode & 0o077
        ):
            raise IntegrityError("artifact final object is unsafe", code="ARTIFACT_PATH_INVALID")
        prefix = f".stage-{target.name}-"
        linked_stages: list[Path] = []
        with os.scandir(target.parent) as entries:
            for entry in entries:
                if not entry.name.startswith(prefix):
                    continue
                candidate = target.parent / entry.name
                candidate_info = os.lstat(candidate)
                if (candidate_info.st_dev, candidate_info.st_ino) == (
                    target_info.st_dev,
                    target_info.st_ino,
                ):
                    linked_stages.append(candidate)
        if len(linked_stages) != 1:
            raise IntegrityError("artifact publish linkage is ambiguous", code="ARTIFACT_PATH_INVALID")
        descriptor = os.open(target, os.O_RDONLY | _NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_nlink) != (
                target_info.st_dev,
                target_info.st_ino,
                2,
            ):
                raise IntegrityError("artifact publish identity changed", code="ARTIFACT_PATH_INVALID")
            verify_digest(
                _read_descriptor(descriptor, maximum=_MAX_ARTIFACT_BYTES),
                digest,
                domain="artifact-content",
            )
        finally:
            os.close(descriptor)
        os.unlink(linked_stages[0])
        _fsync_directory(target.parent)
        return True

    def _quarantine_corrupt(self, target: Path) -> None:
        """Move a corrupt owner-only final inode aside for forensic recovery."""

        secured, descriptor, identity, _ = open_owned_regular(
            target,
            label="corrupt artifact object",
            create=False,
            read_only=True,
        )
        try:
            verify_regular_identity(secured, descriptor, identity, label="corrupt artifact object")
            quarantine = target.parent / f".corrupt-{target.name}-{secrets.token_hex(16)}"
            os.rename(target, quarantine)
            _fsync_directory(target.parent)
        finally:
            os.close(descriptor)

    def _existing_valid(self, target: Path, digest: str) -> bool:
        try:
            payload = read_regular_bytes(
                target,
                label="artifact object",
                maximum=_MAX_ARTIFACT_BYTES,
            )
        except FileNotFoundError:
            return False
        except PathBoundaryError:
            if not self._recover_linked_stage(target, digest):
                return False
            payload = read_regular_bytes(
                target,
                label="artifact object",
                maximum=_MAX_ARTIFACT_BYTES,
            )
        try:
            verify_digest(payload, digest, domain="artifact-content")
        except IntegrityError:
            self._quarantine_corrupt(target)
            return False
        return True

    def _path(self, scope: Scope, digest: str) -> Path:
        if not isinstance(scope, Scope):
            raise ContractError("artifact access requires a trusted Scope")
        require_digest(digest, "artifact digest")
        scope_digest = scope.digest.removeprefix("sha256:")
        hex_digest = digest.removeprefix("sha256:")
        return self.root / "scopes" / scope_digest / "sha256" / hex_digest[:2] / hex_digest

    def _put(
        self,
        scope: Scope,
        content: bytes | bytearray | memoryview,
        *,
        media_type: str,
        kind: str,
        producer_id: str,
        created_at: datetime | None = None,
        _runtime_capability: object,
    ) -> Artifact:
        self._assert_runtime_access(_runtime_capability)
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise ContractError("artifact content must be bytes")
        payload = bytes(content)
        if len(payload) > _MAX_ARTIFACT_BYTES:
            raise ContractError("artifact exceeds the bounded size limit", code="ARTIFACT_SIZE_LIMIT")
        digest = digest_bytes(payload, domain="artifact-content")
        target = self._path(scope, digest)
        with self._lock:
            scope_root = self.root / "scopes" / scope.digest.removeprefix("sha256:")
            self._directory(self.root / "scopes", label="artifact scope namespace")
            self._directory(scope_root, label="artifact trusted scope")
            self._directory(scope_root / "sha256", label="artifact namespace")
            self._directory(target.parent, label="artifact shard")
            if self._existing_valid(target, digest):
                return Artifact(
                    digest=digest,
                    media_type=media_type,
                    size_bytes=len(payload),
                    kind=kind,
                    producer_id=producer_id,
                    created_at=created_at or utc_now(),
                    uri=(
                        "elmos-cas://scope/"
                        f"{scope.digest.removeprefix('sha256:')}/sha256/"
                        f"{digest.removeprefix('sha256:')}"
                    ),
                )
            stage = target.parent / f".stage-{target.name}-{secrets.token_hex(16)}"
            try:
                secured, descriptor, identity, created = open_owned_regular(
                    stage,
                    label="artifact stage object",
                    create=True,
                    read_only=False,
                )
            except PathBoundaryError as exc:
                raise IntegrityError(str(exc), code="ARTIFACT_PATH_INVALID") from exc
            try:
                if not created:
                    raise IntegrityError("artifact stage collision", code="ARTIFACT_WRITE_FAILED")
                remaining = memoryview(payload)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise IntegrityError("artifact write did not progress", code="ARTIFACT_WRITE_FAILED")
                    remaining = remaining[written:]
                os.fsync(descriptor)
                observed = _read_descriptor(descriptor, maximum=_MAX_ARTIFACT_BYTES)
                verify_digest(observed, digest, domain="artifact-content")
                verify_regular_identity(
                    secured,
                    descriptor,
                    identity,
                    label="artifact object",
                )
                self._verify_root()
            finally:
                os.close(descriptor)
            try:
                os.link(stage, target, follow_symlinks=False)
            except FileExistsError as exc:
                os.unlink(stage)
                _fsync_directory(target.parent)
                if not self._existing_valid(target, digest):
                    raise IntegrityError(
                        "raced artifact final object was corrupt",
                        code="ARTIFACT_DIGEST_MISMATCH",
                    ) from exc
            else:
                os.unlink(stage)
                _fsync_directory(target.parent)
            self._verify_root()
        return Artifact(
            digest=digest,
            media_type=media_type,
            size_bytes=len(payload),
            kind=kind,
            producer_id=producer_id,
            created_at=created_at or utc_now(),
            uri=(
                "elmos-cas://scope/"
                f"{scope.digest.removeprefix('sha256:')}/sha256/{digest.removeprefix('sha256:')}"
            ),
        )

    def _get(
        self,
        scope: Scope,
        digest: str,
        *,
        _runtime_capability: object,
    ) -> bytes:
        self._assert_runtime_access(_runtime_capability)
        target = self._path(scope, digest)
        with self._lock:
            self._verify_root()
            try:
                payload = read_regular_bytes(
                    target,
                    label="artifact object",
                    maximum=_MAX_ARTIFACT_BYTES,
                )
            except PathBoundaryError as exc:
                try:
                    os.lstat(target)
                except FileNotFoundError:
                    raise NotFoundError("artifact not found", details={"digest": digest}) from exc
                raise IntegrityError(str(exc), code="ARTIFACT_PATH_INVALID") from exc
            verify_digest(payload, digest, domain="artifact-content")
            self._verify_root()
            return payload

    def _verify(
        self,
        scope: Scope,
        artifact: Artifact,
        *,
        _runtime_capability: object,
    ) -> None:
        self._assert_runtime_access(_runtime_capability)
        payload = self._get(
            scope,
            artifact.digest,
            _runtime_capability=_runtime_capability,
        )
        if len(payload) != artifact.size_bytes:
            raise IntegrityError("artifact byte length mismatch", code="ARTIFACT_SIZE_MISMATCH")


class _RuntimeArtifactAccess:
    """Scope-bound artifact access handed only to the authenticated runtime."""

    __slots__ = ("__capability", "__store")

    def __init__(self, store: ContentAddressedArtifactStore, capability: object) -> None:
        store._assert_runtime_access(capability)
        self.__store = store
        self.__capability = capability

    def put(
        self,
        scope: Scope,
        content: bytes | bytearray | memoryview,
        *,
        media_type: str,
        kind: str,
        producer_id: str,
        created_at: datetime | None = None,
    ) -> Artifact:
        return self.__store._put(
            scope,
            content,
            media_type=media_type,
            kind=kind,
            producer_id=producer_id,
            created_at=created_at,
            _runtime_capability=self.__capability,
        )

    def get(self, scope: Scope, digest: str) -> bytes:
        return self.__store._get(
            scope,
            digest,
            _runtime_capability=self.__capability,
        )

    def verify(self, scope: Scope, artifact: Artifact) -> None:
        self.__store._verify(
            scope,
            artifact,
            _runtime_capability=self.__capability,
        )


def _bind_runtime_artifact_access(store: ContentAddressedArtifactStore) -> _RuntimeArtifactAccess:
    """Internal bootstrap seam; supported callers never receive this access object."""

    capability = object.__getattribute__(store, "_ContentAddressedArtifactStore__access_capability")
    return _RuntimeArtifactAccess(store, capability)
