"""Filesystem-backed adapters.

The repository reader is snapshot-bound on purpose: it captures the file list
and content digests once, at construction, and every later read is checked
against that capture.  A file that changed underneath an in-flight run raises
``STALE_SNAPSHOT`` instead of quietly serving new bytes into a decision that
was justified by the old ones.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..contracts import digest, digest_bytes
from ..errors import KernelError

__all__ = ["FileArtifactStore", "SnapshotRepositoryReader"]

_DEFAULT_EXCLUDES = (
    ".git", "node_modules", "__pycache__", ".venv", "venv", "target",
    "build", "dist", ".mypy_cache", ".pytest_cache", ".ruff_cache",
)


class FileArtifactStore:
    """Content-addressed store on local disk (``<root>/ab/cdef...``)."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path_for(self, artifact_digest: str) -> Path:
        if not artifact_digest.startswith("sha256:") or len(artifact_digest) != 71:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{artifact_digest!r} is not a sha256 content address",
                recommended_action="pass a digest of the form sha256:<64 hex>",
            )
        hex_part = artifact_digest.split(":", 1)[1]
        return self._root / hex_part[:2] / hex_part[2:]

    def put(self, data: bytes, *, media_type: str, expected_digest: str | None = None) -> str:
        computed = digest_bytes(bytes(data))
        if expected_digest is not None and expected_digest != computed:
            raise KernelError(
                code="DIGEST_MISMATCH",
                message=f"claimed {expected_digest}, stored bytes hash to {computed}",
                recommended_action="re-produce the artifact",
            )
        target = self._path_for(computed)
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                # Write to a temp name then rename: a reader must never observe
                # a half-written blob at a content address.
                tmp = target.with_suffix(".partial")
                tmp.write_bytes(data)
                os.replace(tmp, target)
            meta = target.with_suffix(".meta")
            if not meta.exists():
                meta.write_text(media_type, encoding="utf-8")
        return computed

    def get(self, artifact_digest: str) -> bytes:
        target = self._path_for(artifact_digest)
        if not target.exists():
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact or restore from backup",
            )
        data = target.read_bytes()
        if digest_bytes(data) != artifact_digest:
            raise KernelError(
                code="DIGEST_MISMATCH",
                message=f"artifact {artifact_digest} failed re-verification on read",
                recommended_action="treat the store as corrupt and quarantine it",
            )
        return data

    def exists(self, artifact_digest: str) -> bool:
        return self._path_for(artifact_digest).exists()

    def stat(self, artifact_digest: str) -> Mapping[str, Any]:
        target = self._path_for(artifact_digest)
        if not target.exists():
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact",
            )
        meta = target.with_suffix(".meta")
        return {
            "digest": artifact_digest,
            "byteCount": target.stat().st_size,
            "mediaType": (meta.read_text(encoding="utf-8") if meta.exists()
                          else "application/octet-stream"),
        }


class SnapshotRepositoryReader:
    """An immutable, digest-verified view of a working tree."""

    def __init__(self, root: str | os.PathLike[str], *,
                 excludes: Sequence[str] = _DEFAULT_EXCLUDES,
                 max_file_bytes: int = 8 << 20) -> None:
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{self._root} is not a directory",
                recommended_action="point the reader at a repository root",
            )
        self._excludes = tuple(excludes)
        self._max_file_bytes = max_file_bytes
        self._files: dict[str, dict[str, Any]] = {}
        self._scan()
        self._snapshot_sha = digest({
            "files": [
                {"path": path, "digest": meta["digest"], "byteCount": meta["byteCount"]}
                for path, meta in sorted(self._files.items())
            ]
        })

    def _scan(self) -> None:
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = sorted(d for d in dirnames if d not in self._excludes)
            for name in sorted(filenames):
                absolute = Path(dirpath) / name
                if absolute.is_symlink() or not absolute.is_file():
                    continue
                relative = str(absolute.relative_to(self._root))
                size = absolute.stat().st_size
                if size > self._max_file_bytes:
                    # Oversized files are recorded but not hashed by content;
                    # they are marked so that a census cannot silently treat
                    # them as absent.
                    self._files[relative] = {
                        "digest": "", "byteCount": size, "oversized": True,
                    }
                    continue
                data = absolute.read_bytes()
                self._files[relative] = {
                    "digest": digest_bytes(data),
                    "byteCount": size,
                    "oversized": False,
                }

    @property
    def snapshot_sha(self) -> str:
        return self._snapshot_sha

    def list_paths(self) -> Sequence[str]:
        return tuple(sorted(self._files))

    def _resolve(self, path: str) -> Path:
        candidate = (self._root / path).resolve()
        if not candidate.is_relative_to(self._root):
            raise KernelError(
                code="AUTHORITY_SCOPE_MISMATCH",
                message=f"path {path!r} escapes the snapshot root",
                recommended_action="use a repository-relative path",
            )
        return candidate

    def read_bytes(self, path: str) -> bytes:
        meta = self._files.get(path)
        if meta is None:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"{path!r} is not in snapshot {self._snapshot_sha}",
                recommended_action="re-take the snapshot if the file is expected",
            )
        if meta["oversized"]:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"{path!r} exceeds the snapshot content limit",
                recommended_action="stream the file through the artifact store instead",
            )
        data = self._resolve(path).read_bytes()
        if digest_bytes(data) != meta["digest"]:
            raise KernelError(
                code="STALE_SNAPSHOT",
                message=(
                    f"{path!r} changed on disk after snapshot {self._snapshot_sha} was taken"
                ),
                retryable=False,
                recommended_action="abort the step and re-snapshot; do not use the new bytes",
            )
        return data

    def read_text(self, path: str) -> str:
        return self.read_bytes(path).decode("utf-8", errors="replace")

    def stat(self, path: str) -> Mapping[str, Any]:
        meta = self._files.get(path)
        if meta is None:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"{path!r} is not in snapshot {self._snapshot_sha}",
                recommended_action="re-take the snapshot",
            )
        return {"path": path, **meta}
