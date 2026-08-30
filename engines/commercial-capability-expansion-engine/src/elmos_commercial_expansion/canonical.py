"""Bounded canonical JSON and domain-separated content digests.

The engine intentionally uses a small JSON profile instead of accepting
arbitrary Python objects.  Parsed documents reject duplicate keys, invalid
UTF-8, non-finite numbers and documents exceeding byte, depth or node limits.
The same validation is applied before canonical serialization so request and
receipt digests cannot diverge from the data that the runtime executes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePath
from types import MappingProxyType
from typing import Any

from .errors import ContractError, IntegrityError

SHA256_PREFIX = "sha256:"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DOMAIN_PREFIX = b"elmos.commercial-expansion.v2\x00"


@dataclass(frozen=True, slots=True)
class JSONLimits:
    max_bytes: int = 1_048_576
    max_depth: int = 32
    max_nodes: int = 100_000
    max_members: int = 10_000
    max_string_bytes: int = 262_144
    max_key_bytes: int = 512

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ContractError(f"{field.name} must be a positive integer")


DEFAULT_LIMITS = JSONLimits()


def _reject_constant(token: str) -> None:
    raise ContractError(
        "non-finite JSON numbers are forbidden",
        code="NON_CANONICAL_NUMBER",
        details={"token": token},
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(
                "duplicate JSON object key",
                code="DUPLICATE_JSON_KEY",
                details={"key": key},
            )
        result[key] = value
    return result


def _validate_json_shape(value: Any, limits: JSONLimits) -> Any:
    nodes = 0
    encoded_bytes = 0
    active: set[int] = set()

    def add_bytes(amount: int) -> None:
        nonlocal encoded_bytes
        encoded_bytes += amount
        if encoded_bytes > limits.max_bytes:
            raise ContractError("JSON byte limit exceeded", code="JSON_BYTE_LIMIT")

    def encoded_scalar(item: Any) -> bytes:
        try:
            return json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise ContractError("value is not canonical JSON", code="NON_CANONICAL_TYPE") from exc

    def visit(item: Any, *, depth: int) -> Any:
        nonlocal nodes
        if isinstance(item, Enum):
            item = item.value
        if isinstance(item, datetime):
            if item.tzinfo is None or item.utcoffset() is None:
                raise ContractError("naive datetime is not canonical", code="INVALID_TIMESTAMP")
            item = item.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        if isinstance(item, PurePath):
            item = item.as_posix()

        nodes += 1
        if nodes > limits.max_nodes:
            raise ContractError("JSON node limit exceeded", code="JSON_NODE_LIMIT")
        if depth > limits.max_depth:
            raise ContractError("JSON nesting depth exceeded", code="JSON_DEPTH_LIMIT")

        if item is None or isinstance(item, (bool, int)):
            add_bytes(len(encoded_scalar(item)))
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ContractError("non-finite JSON number", code="NON_CANONICAL_NUMBER")
            add_bytes(len(encoded_scalar(item)))
            return item
        if isinstance(item, str):
            try:
                raw_length = len(item.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ContractError("JSON must be valid UTF-8", code="INVALID_UTF8") from exc
            if raw_length > limits.max_string_bytes:
                raise ContractError("JSON string limit exceeded", code="JSON_STRING_LIMIT")
            add_bytes(len(encoded_scalar(item)))
            return item

        object_id = id(item)
        if object_id in active:
            raise ContractError("cyclic value is not JSON", code="CYCLIC_JSON")

        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            field_values = dataclasses.fields(item)
            if len(field_values) > limits.max_members:
                raise ContractError("JSON member limit exceeded", code="JSON_MEMBER_LIMIT")
            active.add(object_id)
            try:
                add_bytes(2)
                result: dict[str, Any] = {}
                for index, field_value in enumerate(field_values):
                    if index:
                        add_bytes(1)
                    key = field_value.name
                    child = getattr(item, key)
                    add_bytes(len(encoded_scalar(key)) + 1)
                    result[key] = visit(child, depth=depth + 1)
                return result
            finally:
                active.remove(object_id)

        if isinstance(item, Mapping):
            try:
                if len(item) > limits.max_members:
                    raise ContractError("JSON member limit exceeded", code="JSON_MEMBER_LIMIT")
            except ContractError:
                raise
            except Exception as exc:
                raise ContractError("JSON mapping length is invalid", code="INVALID_JSON_INPUT") from exc
            active.add(object_id)
            try:
                add_bytes(2)
                result = {}
                for index, key in enumerate(item):
                    if index >= limits.max_members:
                        raise ContractError("JSON member limit exceeded", code="JSON_MEMBER_LIMIT")
                    if index:
                        add_bytes(1)
                    if not isinstance(key, str):
                        raise ContractError("JSON object keys must be strings", code="INVALID_JSON_KEY")
                    try:
                        key_length = len(key.encode("utf-8"))
                    except UnicodeEncodeError as exc:
                        raise ContractError("JSON key must be valid UTF-8", code="INVALID_UTF8") from exc
                    if key_length > limits.max_key_bytes:
                        raise ContractError("JSON key limit exceeded", code="JSON_KEY_LIMIT")
                    if key in result:
                        raise ContractError("duplicate JSON object key", code="DUPLICATE_JSON_KEY")
                    add_bytes(len(encoded_scalar(key)) + 1)
                    result[key] = visit(item[key], depth=depth + 1)
                return result
            finally:
                active.remove(object_id)

        if isinstance(item, (list, tuple, set, frozenset)):
            if len(item) > limits.max_members:
                raise ContractError("JSON array limit exceeded", code="JSON_MEMBER_LIMIT")
            active.add(object_id)
            try:
                add_bytes(2 + max(0, len(item) - 1))
                normalized = [visit(child, depth=depth + 1) for child in item]
                if isinstance(item, (set, frozenset)):
                    normalized.sort(
                        key=lambda child: json.dumps(
                            child,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                return normalized
            finally:
                active.remove(object_id)

        raise ContractError(
            "value is not strict JSON",
            code="NON_CANONICAL_TYPE",
            details={"type": type(item).__name__},
        )

    return visit(value, depth=0)


def strict_json_loads(
    document: str | bytes | bytearray | memoryview,
    *,
    limits: JSONLimits = DEFAULT_LIMITS,
) -> Any:
    """Parse one bounded JSON document and reject ambiguous encodings."""

    if isinstance(document, str):
        try:
            raw = document.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractError("JSON must be valid UTF-8", code="INVALID_UTF8") from exc
    elif isinstance(document, (bytes, bytearray, memoryview)):
        raw = bytes(document)
    else:
        raise ContractError("JSON input must be text or bytes", code="INVALID_JSON_INPUT")
    if len(raw) > limits.max_bytes:
        raise ContractError("JSON byte limit exceeded", code="JSON_BYTE_LIMIT")
    try:
        text = raw.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ContractError("invalid JSON document", code="INVALID_JSON") from exc
    return _validate_json_shape(parsed, limits)


def to_jsonable(value: Any, *, limits: JSONLimits = DEFAULT_LIMITS) -> Any:
    return _validate_json_shape(value, limits)


def canonical_json_bytes(value: Any, *, limits: JSONLimits = DEFAULT_LIMITS) -> bytes:
    normalized = to_jsonable(value, limits=limits)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > limits.max_bytes:
        raise ContractError("canonical JSON byte limit exceeded", code="JSON_BYTE_LIMIT")
    return encoded


def canonical_json(value: Any, *, limits: JSONLimits = DEFAULT_LIMITS) -> str:
    return canonical_json_bytes(value, limits=limits).decode("utf-8")


def freeze_json(value: Any, *, limits: JSONLimits = DEFAULT_LIMITS) -> Any:
    """Take a deeply immutable, validated snapshot of a JSON-shaped value."""

    def freeze(item: Any) -> Any:
        if isinstance(item, dict):
            return MappingProxyType({key: freeze(child) for key, child in item.items()})
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)
        return item

    return freeze(to_jsonable(value, limits=limits))


def digest_bytes(content: bytes | bytearray | memoryview, *, domain: str) -> str:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise ContractError("digest content must be bytes", code="INVALID_DIGEST_CONTENT")
    if not isinstance(domain, str) or not domain or "\x00" in domain:
        raise ContractError("digest domain is invalid", code="INVALID_DIGEST_DOMAIN")
    payload = _DOMAIN_PREFIX + domain.encode("utf-8") + b"\x00" + bytes(content)
    return SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


def digest_object(value: Any, *, domain: str, limits: JSONLimits = DEFAULT_LIMITS) -> str:
    return digest_bytes(canonical_json_bytes(value, limits=limits), domain=domain)


def require_digest(value: Any, field: str = "digest") -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ContractError(
            f"{field} must be a lowercase sha256 digest",
            code="INVALID_DIGEST",
            details={"field": field},
        )
    return value


def verify_digest(content: bytes | bytearray | memoryview, claimed: str, *, domain: str) -> None:
    require_digest(claimed)
    actual = digest_bytes(content, domain=domain)
    if not hmac.compare_digest(actual, claimed):
        raise IntegrityError(
            "content digest mismatch",
            code="DIGEST_MISMATCH",
            details={"claimed": claimed, "actual": actual, "domain": domain},
        )
