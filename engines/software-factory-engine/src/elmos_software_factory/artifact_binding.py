"""Bounded content-addressed reads for local qualification evidence.

Evidence paths are untrusted input.  This module only resolves repository-relative
regular files below an explicitly supplied root, rejects every symlink component,
and verifies both the byte count and SHA-256 digest from one open descriptor.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import is_sha256_digest
from .evidence_models import EvidenceContractError


MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9._/-]{1,1024}$")


class ArtifactBindingError(EvidenceContractError):
    """Raised when a content reference is unsafe, stale, or malformed."""


def _exact_keys(document: dict[str, Any], expected: frozenset[str], label: str) -> None:
    if set(document) != expected:
        missing = sorted(expected - set(document))
        extra = sorted(set(document) - expected)
        raise ArtifactBindingError(f"{label} fields differ: missing={missing} extra={extra}")


def _relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or _RELATIVE_PATH.fullmatch(value) is None:
        raise ArtifactBindingError(f"{label} must be a bounded portable relative path")
    if "\\" in value or value.startswith("/"):
        raise ArtifactBindingError(f"{label} must be repository-relative")
    parsed = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in parsed.parts):
        raise ArtifactBindingError(f"{label} contains an unsafe path segment")
    return parsed.as_posix()


@dataclass(frozen=True)
class ContentReference:
    """An exact local artifact reference; paths never imply execution authority."""

    path: str
    sha256: str
    size_bytes: int
    media_type: str

    @classmethod
    def from_mapping(cls, value: object) -> "ContentReference":
        if not isinstance(value, dict):
            raise ArtifactBindingError("content reference must be an object")
        _exact_keys(value, frozenset({"path", "sha256", "size_bytes", "media_type"}), "content reference")
        digest = value.get("sha256")
        if not is_sha256_digest(digest):
            raise ArtifactBindingError("content reference sha256 must be lowercase sha256")
        size = value.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_EVIDENCE_BYTES:
            raise ArtifactBindingError(f"content reference size_bytes must be in [0, {MAX_EVIDENCE_BYTES}]")
        media_type = value.get("media_type")
        if not isinstance(media_type, str) or not media_type or len(media_type) > 128:
            raise ArtifactBindingError("content reference media_type is invalid")
        return cls(
            path=_relative_path(value.get("path"), "content reference.path"),
            sha256=digest,
            size_bytes=size,
            media_type=media_type,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
        }


def _safe_root(root: Path) -> Path:
    supplied_root = root.expanduser()
    if supplied_root.is_symlink():
        raise ArtifactBindingError("approved artifact root must not be a symlink")
    resolved_root = supplied_root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ArtifactBindingError("approved artifact root must be a directory")
    return resolved_root


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArtifactBindingError(f"safe artifact binding requires {name}")
    return value


def _require_dir_fd_support() -> None:
    supported = getattr(os, "supports_dir_fd", None)
    if not isinstance(supported, set) or os.open not in supported:
        raise ArtifactBindingError("safe artifact binding requires os.open dir_fd support")


def _open_beneath(root: Path, relative: str) -> int:
    """Open a file beneath root with no-follow traversal for every component."""

    no_follow = _required_open_flag("O_NOFOLLOW")
    directory = _required_open_flag("O_DIRECTORY")
    _require_dir_fd_support()
    resolved_root = _safe_root(root)
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow | directory
    try:
        current = os.open(resolved_root, directory_flags)
    except OSError as exc:
        raise ArtifactBindingError("approved artifact root cannot be opened safely") from exc
    parts = PurePosixPath(relative).parts
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=current)
            except OSError as exc:
                raise ArtifactBindingError(f"artifact parent is unsafe: {relative}") from exc
            os.close(current)
            current = child
        file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow | getattr(os, "O_NONBLOCK", 0)
        try:
            return os.open(parts[-1], file_flags, dir_fd=current)
        except OSError as exc:
            raise ArtifactBindingError(f"content reference cannot be opened safely: {relative}") from exc
    finally:
        os.close(current)


def read_content_reference(
    reference: ContentReference | object,
    root: Path,
    *,
    maximum: int = MAX_EVIDENCE_BYTES,
) -> bytes:
    """Read and verify one reference without following the final symlink."""

    parsed = (
        reference if isinstance(reference, ContentReference) else ContentReference.from_mapping(reference)
    )
    if parsed.size_bytes > maximum:
        raise ArtifactBindingError("content reference exceeds the caller byte budget")
    descriptor = _open_beneath(root, parsed.path)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ArtifactBindingError("content reference must resolve to a regular file")
        if metadata.st_size != parsed.size_bytes:
            raise ArtifactBindingError(
                f"content byte count mismatch: expected {parsed.size_bytes}, observed {metadata.st_size}"
            )
        if metadata.st_size > maximum:
            raise ArtifactBindingError("content reference exceeds the caller byte budget")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ArtifactBindingError("content reference changed while being read")
            digest.update(chunk)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ArtifactBindingError("content reference changed while being read")
    finally:
        os.close(descriptor)
    observed_digest = "sha256:" + digest.hexdigest()
    if observed_digest != parsed.sha256:
        raise ArtifactBindingError(
            f"content digest mismatch: expected {parsed.sha256}, observed {observed_digest}"
        )
    return b"".join(chunks)
