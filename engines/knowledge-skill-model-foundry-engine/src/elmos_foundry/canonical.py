"""Bounded canonical JSON and SHA-256 primitives for Foundry trust bindings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, TypeAlias

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class CanonicalError(ValueError):
    """A value is ambiguous, unsupported, or outside canonical bounds."""


@dataclass(frozen=True, slots=True)
class CanonicalLimits:
    max_document_bytes: int = 1024 * 1024
    max_string_bytes: int = 256 * 1024
    max_key_bytes: int = 512
    max_depth: int = 64
    max_items: int = 100_000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_LIMITS = CanonicalLimits()
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,255}")


def _text(value: Any, label: str, maximum: int, *, content: bool = False) -> str:
    if not isinstance(value, str) or unicodedata.normalize("NFC", value) != value:
        raise CanonicalError(f"{label} must be an NFC-normalized string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise CanonicalError(f"{label} is not strict UTF-8") from exc
    if len(encoded) > maximum:
        raise CanonicalError(f"{label} exceeds its byte limit")
    allowed = {0x09, 0x0A, 0x0D} if content else set()
    if any((ord(char) < 0x20 and ord(char) not in allowed) or ord(char) == 0x7F for char in value):
        raise CanonicalError(f"{label} contains a forbidden control character")
    return value


def require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise CanonicalError(f"{field} must be a bounded identifier")
    return _text(value, field, 256)


def validate_digest(value: Any, field: str = "digest") -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise CanonicalError(f"{field} must use sha256:<64 lowercase hex>")
    return value


def canonical_value(value: Any, *, limits: CanonicalLimits = DEFAULT_LIMITS) -> JsonValue:
    count = 0

    def visit(item: Any, depth: int) -> JsonValue:
        nonlocal count
        if depth > limits.max_depth:
            raise CanonicalError("canonical value exceeds the nesting limit")
        count += 1
        if count > limits.max_items:
            raise CanonicalError("canonical value exceeds the item limit")
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, int):
            if not -(2**63) <= item <= 2**63 - 1:
                raise CanonicalError("integer is outside signed 64-bit range")
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise CanonicalError("non-finite numbers are forbidden")
            return 0.0 if item == 0.0 else item
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise CanonicalError("non-finite decimals are forbidden")
            converted = float(item)
            if Decimal(str(converted)) != item.normalize():
                raise CanonicalError("decimal cannot be represented without loss")
            return 0.0 if converted == 0.0 else converted
        if isinstance(item, str):
            return _text(item, "string", limits.max_string_bytes, content=True)
        if isinstance(item, Mapping):
            normalized: dict[str, JsonValue] = {}
            folded: set[str] = set()
            for raw_key, raw_value in item.items():
                key = _text(raw_key, "object key", limits.max_key_bytes)
                if key.casefold() in folded:
                    raise CanonicalError("object contains a case-insensitive key collision")
                folded.add(key.casefold())
                normalized[key] = visit(raw_value, depth + 1)
            return {key: normalized[key] for key in sorted(normalized)}
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray, memoryview)):
            return [visit(child, depth + 1) for child in item]
        raise CanonicalError(f"unsupported canonical value type: {type(item).__name__}")

    normalized = visit(value, 0)
    if len(_encode(normalized)) > limits.max_document_bytes:
        raise CanonicalError("canonical document exceeds the byte limit")
    return normalized


def _encode(value: JsonValue) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_json_bytes(value: Any, *, limits: CanonicalLimits = DEFAULT_LIMITS) -> bytes:
    encoded = _encode(canonical_value(value, limits=limits))
    if len(encoded) > limits.max_document_bytes:
        raise CanonicalError("canonical document exceeds the byte limit")
    return encoded


def canonical_json(value: Any, *, limits: CanonicalLimits = DEFAULT_LIMITS) -> str:
    return canonical_json_bytes(value, limits=limits).decode("utf-8")


def digest_bytes(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise TypeError("digest input must be bytes")
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_digest(value: Any, *, limits: CanonicalLimits = DEFAULT_LIMITS) -> str:
    return digest_bytes(canonical_json_bytes(value, limits=limits))


def strict_json_loads(value: bytes | str, *, limits: CanonicalLimits = DEFAULT_LIMITS) -> JsonValue:
    if isinstance(value, bytes):
        if len(value) > limits.max_document_bytes:
            raise CanonicalError("JSON document exceeds the byte limit")
        try:
            text = value.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise CanonicalError("JSON document is not UTF-8") from exc
    elif isinstance(value, str):
        text = value
        if len(text.encode("utf-8")) > limits.max_document_bytes:
            raise CanonicalError("JSON document exceeds the byte limit")
    else:
        raise TypeError("JSON input must be bytes or text")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise CanonicalError(f"duplicate JSON key: {key!r}")
            result[key] = item
        return result

    def invalid(token: str) -> Any:
        raise CanonicalError(f"non-finite JSON number is forbidden: {token}")

    try:
        parsed = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    except json.JSONDecodeError as exc:
        raise CanonicalError("invalid JSON document") from exc
    return canonical_value(parsed, limits=limits)


__all__ = [
    "CanonicalError",
    "CanonicalLimits",
    "DEFAULT_LIMITS",
    "JsonValue",
    "canonical_digest",
    "canonical_json",
    "canonical_json_bytes",
    "canonical_value",
    "digest_bytes",
    "require_identifier",
    "strict_json_loads",
    "validate_digest",
]
