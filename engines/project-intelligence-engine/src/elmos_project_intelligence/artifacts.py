"""Private content-addressed artifact store for Project Intelligence results.

This store is intentionally scoped to the new engine and does not depend on or
modify the shared ELMOS CAS modules. Objects are immutable, digest-verified,
atomically promoted, and never executed.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile


class ArtifactStoreError(RuntimeError):
    """Raised when an artifact path or object violates the CAS contract."""


def _digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


class ContentAddressedArtifactStore:
    """Small immutable filesystem CAS with same-filesystem atomic promotion."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if self.root.exists() and (self.root.is_symlink() or not self.root.is_dir()):
            raise ArtifactStoreError("artifact root must be a real directory")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.objects = self.root / "objects" / "sha256"
        self.objects.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, digest: str) -> Path:
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ArtifactStoreError("artifact digest must use sha256:<hex>")
        value = digest.removeprefix("sha256:")
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ArtifactStoreError("artifact digest is malformed")
        path = self.objects / value[:2] / value[2:]
        try:
            path.parent.resolve(strict=False).relative_to(
                self.root.resolve(strict=True)
            )
        except (OSError, ValueError) as exc:
            raise ArtifactStoreError("artifact path escapes its root") from exc
        return path

    @staticmethod
    def _verify_regular(path: Path) -> None:
        try:
            metadata = path.lstat()
        except FileNotFoundError as exc:
            raise ArtifactStoreError(f"artifact is missing: {path}") from exc
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise ArtifactStoreError(f"artifact is not a regular file: {path}")

    def put(self, content: bytes) -> str:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        digest = _digest_bytes(content)
        destination = self._path(digest)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if destination.exists() or destination.is_symlink():
            self._verify_regular(destination)
            observed = self.read(digest)
            if observed != content:
                raise ArtifactStoreError(
                    "existing content-addressed artifact is corrupt"
                )
            return digest
        descriptor, temporary = tempfile.mkstemp(
            prefix=".artifact-", dir=destination.parent
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            if destination.exists() or destination.is_symlink():
                observed = self.read(digest)
                if observed != content:
                    raise ArtifactStoreError(
                        "concurrent artifact promotion produced different bytes"
                    )
                temporary_path.unlink(missing_ok=True)
                return digest
            os.replace(temporary_path, destination)
            directory_descriptor = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return digest

    def read(self, digest: str) -> bytes:
        path = self._path(digest)
        self._verify_regular(path)
        content = path.read_bytes()
        observed = _digest_bytes(content)
        if observed != digest:
            raise ArtifactStoreError(
                f"artifact digest mismatch: expected={digest} actual={observed}"
            )
        return content

    def contains(self, digest: str) -> bool:
        path = self._path(digest)
        if not path.exists() and not path.is_symlink():
            return False
        self.read(digest)
        return True


__all__ = ["ArtifactStoreError", "ContentAddressedArtifactStore"]
