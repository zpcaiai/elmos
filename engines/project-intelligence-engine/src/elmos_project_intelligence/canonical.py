"""Deterministic, dependency-free canonical JSON and digest helpers.

The project-intelligence engine uses these functions anywhere an idempotency,
artifact, evidence, or snapshot identity is persisted.  The encoder is
deliberately stricter than :mod:`json`: floats, non-string mapping keys, and
unknown object types are rejected instead of being stringified implicitly.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import hmac
import json
from typing import Any, Mapping, Sequence


type JsonScalar = None | bool | int | str
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented without ambiguity."""


class DigestError(ValueError):
    """Raised when a digest is malformed or uses an unsupported algorithm."""


_ALGORITHM = "sha256"
_HEX_LENGTH = 64


def _checked_string(value: str, *, location: str) -> str:
    if "\x00" in value:
        raise CanonicalizationError(f"NUL is not allowed in {location}")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CanonicalizationError(
            f"invalid Unicode scalar value in {location}"
        ) from exc
    return value


def _normalize(value: Any, *, location: str, active: set[int]) -> JsonValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _checked_string(value, location=location)
    if isinstance(value, float):
        raise CanonicalizationError(
            f"floating-point values are forbidden at {location}; encode an "
            "exact decimal as a string"
        )
    if isinstance(value, Enum):
        return _normalize(value.value, location=location, active=active)

    identity = id(value)
    if identity in active:
        raise CanonicalizationError(f"cyclic value at {location}")

    if is_dataclass(value) and not isinstance(value, type):
        active.add(identity)
        try:
            normalized: dict[str, JsonValue] = {}
            for field in fields(value):
                name = _checked_string(field.name, location=f"{location} key")
                normalized[name] = _normalize(
                    getattr(value, field.name),
                    location=f"{location}.{name}",
                    active=active,
                )
            return normalized
        finally:
            active.remove(identity)

    if isinstance(value, Mapping):
        active.add(identity)
        try:
            normalized_mapping: dict[str, JsonValue] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CanonicalizationError(
                        f"mapping key at {location} must be a string, got "
                        f"{type(key).__name__}"
                    )
                key = _checked_string(key, location=f"{location} key")
                normalized_mapping[key] = _normalize(
                    item,
                    location=f"{location}.{key}",
                    active=active,
                )
            return normalized_mapping
        finally:
            active.remove(identity)

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        active.add(identity)
        try:
            return [
                _normalize(item, location=f"{location}[{index}]", active=active)
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(identity)

    raise CanonicalizationError(
        f"unsupported value at {location}: {type(value).__name__}"
    )


def canonical_value(value: Any) -> JsonValue:
    """Return a JSON-compatible value after strict recursive validation."""

    return _normalize(value, location="$", active=set())


def canonical_json_bytes(value: Any) -> bytes:
    """Encode *value* as stable UTF-8 JSON.

    Key sorting and compact separators make the same logical value byte
    identical across calls.  The trailing newline is intentionally omitted so
    the digest is over only the canonical value.
    """

    normalized = canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", errors="strict")


def canonical_json(value: Any) -> str:
    """Return the canonical JSON representation as text."""

    return canonical_json_bytes(value).decode("utf-8")


def sha256_hex(data: bytes | bytearray | memoryview) -> str:
    """Return the lowercase SHA-256 hexadecimal digest of bytes-like data."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("sha256_hex requires a bytes-like value")
    return hashlib.sha256(bytes(data)).hexdigest()


def digest_bytes(data: bytes | bytearray | memoryview) -> str:
    """Return a self-describing ``sha256:<hex>`` content digest."""

    return f"{_ALGORITHM}:{sha256_hex(data)}"


def canonical_digest(value: Any) -> str:
    """Return the SHA-256 digest of canonical JSON for *value*."""

    return digest_bytes(canonical_json_bytes(value))


def validate_digest(value: str) -> str:
    """Validate and return a normalized self-describing SHA-256 digest."""

    if not isinstance(value, str):
        raise DigestError("digest must be a string")
    prefix, separator, hexadecimal = value.partition(":")
    if separator != ":" or prefix.lower() != _ALGORITHM:
        raise DigestError("digest must use the sha256:<hex> form")
    if len(hexadecimal) != _HEX_LENGTH:
        raise DigestError("SHA-256 digest must contain 64 hexadecimal characters")
    try:
        int(hexadecimal, 16)
    except ValueError as exc:
        raise DigestError("digest contains non-hexadecimal characters") from exc
    return f"{_ALGORITHM}:{hexadecimal.lower()}"


def digest_matches(data: bytes | bytearray | memoryview, expected: str) -> bool:
    """Constant-time comparison between bytes and a validated digest."""

    normalized = validate_digest(expected)
    return hmac.compare_digest(digest_bytes(data), normalized)


__all__ = [
    "CanonicalizationError",
    "DigestError",
    "JsonScalar",
    "JsonValue",
    "canonical_digest",
    "canonical_json",
    "canonical_json_bytes",
    "canonical_value",
    "digest_bytes",
    "digest_matches",
    "sha256_hex",
    "validate_digest",
]
