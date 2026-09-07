"""Canonical serialisation, digests and logical-path safety.

Two invariants live here:

* ``canonical_json_bytes`` is the only serialisation used for anything that is
  hashed. It is typed, sorted, NFC-normalised and rejects non-finite numbers,
  so an ActionKey computed on macOS equals the one computed on Linux.
* ``normalize_logical_path`` is the only place that decides whether a
  generator-supplied path may exist. Everything else calls it.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from .errors import DigestMismatch, UnsafePath

DIGEST_PREFIX = "sha256:"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CAS_URI_RE = re.compile(r"^cas://sha256[:/]([0-9a-f]{64})$")
EMPTY_DIGEST = DIGEST_PREFIX + hashlib.sha256(b"").hexdigest()

#: Windows reserved device names, matched case-insensitively on the stem.
RESERVED_DEVICE_NAMES = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{i}" for i in range(1, 10)]
    + [f"lpt{i}" for i in range(1, 10)]
)

#: Characters that are illegal in a portable logical path.
_ILLEGAL_PATH_CHARS = frozenset('\x00<>:"|?*')

#: Unicode categories that must never appear in a logical path: format
#: characters (RLO/LRO spoofing), surrogates, private use and unassigned.
_ILLEGAL_UNICODE_CATEGORIES = frozenset({"Cf", "Cs", "Co", "Cn", "Cc"})

MAX_PATH_SEGMENTS = 128
MAX_SEGMENT_LENGTH = 255
MAX_LOGICAL_PATH_LENGTH = 4096


# --------------------------------------------------------------------------
# canonical JSON
# --------------------------------------------------------------------------
def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, list | tuple):
        return [_normalize(v) for v in value]
    if isinstance(value, set | frozenset):
        return [_normalize(v) for v in sorted(value, key=repr)]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not canonical")
        if value == int(value) and abs(value) < 2**53:
            return int(value)
        return value
    # Enums defined in .enums are str subclasses and are caught above.
    raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, NFC strings."""
    import json

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_text(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


# --------------------------------------------------------------------------
# digests
# --------------------------------------------------------------------------
def sha256_bytes(data: bytes) -> str:
    return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_stream(stream: BinaryIO, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Return ``(digest, size)`` without holding the payload in memory."""
    hasher = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        size += len(chunk)
        hasher.update(chunk)
    return DIGEST_PREFIX + hasher.hexdigest(), size


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    with path.open("rb") as handle:
        return sha256_stream(handle, chunk_size)


def digest_of(value: Any) -> str:
    """Content address of a structured document."""
    return sha256_bytes(canonical_json_bytes(value))


def require_digest(digest: str) -> str:
    if not isinstance(digest, str) or not DIGEST_RE.match(digest):
        raise DigestMismatch(f"malformed digest: {digest!r}", digest=digest)
    return digest


def digest_hex(digest: str) -> str:
    return require_digest(digest)[len(DIGEST_PREFIX) :]


def cas_uri(digest: str) -> str:
    return f"cas://sha256:{digest_hex(digest)}"


def digest_from_cas_uri(uri: str) -> str:
    match = CAS_URI_RE.match(uri)
    if not match:
        raise DigestMismatch(f"malformed CAS reference: {uri!r}", uri=uri)
    return DIGEST_PREFIX + match.group(1)


def merkle_node_digest(kind: str, entries: Iterable[tuple[str, str]]) -> str:
    """Digest of a sorted ``(name, child_digest)`` list under a node kind."""
    payload = {"kind": kind, "entries": [list(item) for item in sorted(entries)]}
    return digest_of(payload)


# --------------------------------------------------------------------------
# logical paths
# --------------------------------------------------------------------------
def normalize_logical_path(logical_path: str) -> str:
    """Validate and normalise a generator-supplied output path.

    Rejects absolute paths, drive letters, UNC prefixes, traversal, empty or
    dot segments, NUL and control characters, bidi/format spoofing, Windows
    reserved device names, trailing dots/spaces and over-long segments.
    """
    if not isinstance(logical_path, str) or not logical_path:
        raise UnsafePath("logical path must be a non-empty string", logical_path=logical_path)
    if len(logical_path) > MAX_LOGICAL_PATH_LENGTH:
        raise UnsafePath("logical path is too long", logical_path=logical_path[:80])

    candidate = unicodedata.normalize("NFC", logical_path).replace("\\", "/")

    if candidate.startswith("//"):
        raise UnsafePath("UNC-style paths are rejected", logical_path=logical_path)
    if candidate.startswith("/"):
        raise UnsafePath("absolute paths are rejected", logical_path=logical_path)
    if candidate.startswith("~"):
        raise UnsafePath("home-relative paths are rejected", logical_path=logical_path)

    pure = PurePosixPath(candidate)
    parts = pure.parts
    if not parts:
        raise UnsafePath("empty logical path", logical_path=logical_path)
    if len(parts) > MAX_PATH_SEGMENTS:
        raise UnsafePath("too many path segments", logical_path=logical_path)

    for part in parts:
        if part in ("", ".", ".."):
            raise UnsafePath("path traversal or empty segment", logical_path=logical_path, segment=part)
        if len(part) > MAX_SEGMENT_LENGTH:
            raise UnsafePath("path segment too long", logical_path=logical_path, segment=part[:40])
        if len(part) >= 2 and part[1] == ":":
            raise UnsafePath("drive-letter segment", logical_path=logical_path, segment=part)
        for char in part:
            if char in _ILLEGAL_PATH_CHARS:
                raise UnsafePath("illegal character in path", logical_path=logical_path, character=hex(ord(char)))
            if unicodedata.category(char) in _ILLEGAL_UNICODE_CATEGORIES:
                raise UnsafePath(
                    "unsafe unicode category in path",
                    logical_path=logical_path,
                    character=hex(ord(char)),
                )
        if part != part.rstrip(" .") and part not in (".", ".."):
            raise UnsafePath("trailing dot or space is unportable", logical_path=logical_path, segment=part)
        stem = part.split(".", 1)[0].lower()
        if stem in RESERVED_DEVICE_NAMES:
            raise UnsafePath("reserved device name", logical_path=logical_path, segment=part)

    return "/".join(parts)


def case_fold_key(logical_path: str) -> str:
    """Collision key for case-insensitive filesystems (APFS, NTFS)."""
    return unicodedata.normalize("NFC", logical_path).casefold()


def detect_path_collisions(paths: Iterable[str]) -> list[tuple[str, str, str]]:
    """Return ``(kind, first, second)`` for duplicate/case/parent conflicts."""
    collisions: list[tuple[str, str, str]] = []
    exact: dict[str, str] = {}
    folded: dict[str, str] = {}
    for raw in paths:
        path = normalize_logical_path(raw)
        if path in exact:
            collisions.append(("DUPLICATE", exact[path], path))
            continue
        key = case_fold_key(path)
        if key in folded:
            collisions.append(("CASE_COLLISION", folded[key], path))
        exact[path] = path
        folded[key] = path

    # A file cannot also be a directory prefix of another entry.
    ordered = sorted(exact)
    for index, path in enumerate(ordered):
        prefix = path + "/"
        for other in ordered[index + 1 :]:
            if not other.startswith(prefix):
                break
            collisions.append(("FILE_DIRECTORY_CONFLICT", path, other))
    return collisions


def resolve_within(root: Path, logical_path: str) -> Path:
    """Join ``logical_path`` under ``root`` and prove it cannot escape.

    Existing parents are resolved so a pre-existing symlink cannot redirect the
    write outside the sandbox root.
    """
    normalized = normalize_logical_path(logical_path)
    root_resolved = root.resolve()
    target = root_resolved.joinpath(normalized)

    probe = target
    while True:
        if probe.exists() or probe.is_symlink():
            break
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    try:
        real = probe.resolve()
    except OSError as exc:  # pragma: no cover - platform dependent
        raise UnsafePath("cannot resolve target path", logical_path=logical_path, error=str(exc)) from exc

    if real != root_resolved and root_resolved not in real.parents:
        raise UnsafePath("path escapes the workspace root", logical_path=logical_path, resolved=str(real))
    if probe.is_symlink():
        raise UnsafePath("symlink on the write path", logical_path=logical_path, at=str(probe))
    return target


def fsync_directory(path: Path) -> None:
    """Best-effort directory fsync; a no-op where the platform forbids it."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - e.g. some network filesystems
        pass
    finally:
        os.close(fd)
