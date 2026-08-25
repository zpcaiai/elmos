from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


class DigestMismatch(ValueError):
    pass


class LocalCAS:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _hex(digest: str) -> str:
        prefix = "sha256:"
        if not digest.startswith(prefix):
            raise ValueError("only sha256 digests are supported")
        value = digest[len(prefix):]
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("invalid sha256 digest")
        return value

    def path_for(self, digest: str) -> Path:
        value = self._hex(digest)
        return self.root / "sha256" / value[:2] / value[2:4] / f"{value}.blob"

    def put_bytes(self, data: bytes, expected_digest: str | None = None) -> str:
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if expected_digest is not None and expected_digest != digest:
            raise DigestMismatch(f"expected {expected_digest}, got {digest}")

        destination = self.path_for(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            self.verify(digest)
            return digest

        fd, name = tempfile.mkstemp(prefix=".elmos-cas-", dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())

            # Hard-link creation is create-if-absent and does not overwrite a winner.
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass

            self._fsync_directory(destination.parent)
            self.verify(digest)
            return digest
        finally:
            temporary.unlink(missing_ok=True)

    def get_bytes(self, digest: str, verify: bool = True) -> bytes:
        data = self.path_for(digest).read_bytes()
        if verify:
            actual = "sha256:" + hashlib.sha256(data).hexdigest()
            if actual != digest:
                raise DigestMismatch(
                    f"corrupt object {digest}; actual digest is {actual}"
                )
        return data

    def verify(self, digest: str) -> None:
        self.get_bytes(digest, verify=True)

    def materialize(self, digest: str, destination: Path) -> None:
        source = self.path_for(digest)
        self.verify(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / (
            f".{destination.name}.elmos-materialize-{os.getpid()}"
        )
        temporary.unlink(missing_ok=True)
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copyfile(source, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        self._fsync_directory(destination.parent)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
