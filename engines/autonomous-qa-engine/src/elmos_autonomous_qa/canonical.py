"""Strict canonical JSON, SHA-256, and filesystem path primitives."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, TypeAlias


JSONScalar: TypeAlias = bool | int | float | str | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

_SAFE_INTEGER_MAX = (1 << 53) - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


class CanonicalizationError(ValueError):
    """Raised when a value is not strict, portable JSON."""


class UnsafePathError(ValueError):
    """Raised when an artifact path can escape or alias its declared root."""


def _validate_string(value: str, location: str) -> None:
    if "\x00" in value:
        raise CanonicalizationError(f"NUL is forbidden at {location}")
    if unicodedata.normalize("NFC", value) != value:
        raise CanonicalizationError(f"non-NFC string at {location}")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalizationError(f"surrogate code point at {location}")


def _validated_json(value: Any, location: str = "$") -> JSONValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        _validate_string(value, location)
        return value
    if isinstance(value, int):
        if abs(value) > _SAFE_INTEGER_MAX:
            raise CanonicalizationError(f"integer outside portable JSON range at {location}")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"non-finite number at {location}")
        if value == 0:
            return 0
        return value
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"non-string object key at {location}")
            _validate_string(key, f"{location}.<key>")
            result[key] = _validated_json(item, f"{location}.{key}")
        return result
    if isinstance(value, list):
        return [_validated_json(item, f"{location}[{index}]") for index, item in enumerate(value)]
    raise CanonicalizationError(f"unsupported JSON value {type(value).__name__} at {location}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON after strict portable-value validation."""

    try:
        validated = _validated_json(value)
        return (
            json.dumps(
                validated,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except RecursionError as exc:
        raise CanonicalizationError("JSON nesting exceeds the canonicalization limit") from exc


def parse_json_strict(raw: str | bytes) -> JSONValue:
    """Parse JSON while rejecting duplicate keys, constants, and nonportable values."""

    def reject_constant(value: str) -> None:
        raise CanonicalizationError(f"invalid JSON number {value}")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CanonicalizationError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        decoded = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CanonicalizationError(str(exc)) from exc
    try:
        return _validated_json(decoded)
    except RecursionError as exc:
        raise CanonicalizationError("JSON nesting exceeds the canonicalization limit") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    source = Path(path)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise UnsafePathError("safe non-symlink file opens are unavailable")

    def identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    descriptor: int | None = None
    try:
        named_before = os.stat(source, follow_symlinks=False)
        if not stat.S_ISREG(named_before.st_mode):
            raise UnsafePathError(f"not a regular non-symlink file: {source}")
        flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(source, flags)
        opened_before = os.fstat(descriptor)
        if not stat.S_ISREG(opened_before.st_mode):
            raise UnsafePathError(f"not a regular non-symlink file: {source}")
        if identity(opened_before) != identity(named_before):
            raise UnsafePathError(f"file changed while opening: {source}")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = None
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            opened_after = os.fstat(stream.fileno())
        named_after = os.stat(source, follow_symlinks=False)
        if (
            not stat.S_ISREG(named_after.st_mode)
            or identity(opened_before) != identity(opened_after)
            or identity(opened_after) != identity(named_after)
        ):
            raise UnsafePathError(f"file changed while hashing: {source}")
        return digest.hexdigest()
    except UnsafePathError:
        raise
    except OSError as exc:
        raise UnsafePathError(f"could not safely hash file: {source}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def canonical_digest(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def require_sha256(value: str, *, field: str = "digest") -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CanonicalizationError(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def normalize_relative_path(raw: str, *, max_bytes: int = 1024) -> str:
    """Return a portable POSIX relative path or raise ``UnsafePathError``."""

    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise UnsafePathError(f"unsafe relative path: {raw!r}")
    if unicodedata.normalize("NFC", raw) != raw:
        raise UnsafePathError(f"path is not NFC normalized: {raw!r}")
    if len(raw.encode("utf-8")) > max_bytes:
        raise UnsafePathError(f"path exceeds {max_bytes} UTF-8 bytes: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or path.as_posix() != raw:
        raise UnsafePathError(f"path is not a canonical POSIX relative path: {raw!r}")
    for part in path.parts:
        if part in {"", ".", ".."} or part.endswith((".", " ")):
            raise UnsafePathError(f"unsafe path component {part!r}")
        if part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED:
            raise UnsafePathError(f"reserved path component {part!r}")
        if any(ord(character) < 32 or ord(character) == 127 for character in part):
            raise UnsafePathError(f"control character in path component {part!r}")
    return path.as_posix()


def path_collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", normalize_relative_path(path)).casefold()


def validate_unique_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    keys: dict[str, str] = {}
    for raw in paths:
        path = normalize_relative_path(raw)
        key = path_collision_key(path)
        if key in keys:
            raise UnsafePathError(f"path collision: {keys[key]!r} and {path!r}")
        keys[key] = path
        normalized.append(path)
    return tuple(normalized)


def safe_join(root: str | os.PathLike[str], relative_path: str) -> Path:
    """Join below ``root`` while rejecting symlinked path components."""

    base = Path(root)
    if base.is_symlink():
        raise UnsafePathError(f"root may not be a symlink: {base}")
    base_resolved = base.resolve(strict=False)
    relative = normalize_relative_path(relative_path)
    cursor = base
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise UnsafePathError(f"symlink path component is forbidden: {cursor}")
    candidate = cursor.resolve(strict=False)
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes root: {relative!r}") from exc
    return candidate
