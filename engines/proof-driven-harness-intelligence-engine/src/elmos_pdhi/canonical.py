"""Strict canonical JSON and domain-separated SHA-256 digests."""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Mapping

from .errors import IntegrityError, ValidationError


SHA256_PREFIX = "sha256:"
_DOMAIN_PREFIX = b"elmos.pdhi.v1\x00"
_DIGEST_LENGTH = len(SHA256_PREFIX) + 64


def utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_string(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise ValidationError(
            "string is not Unicode NFC", code="NON_CANONICAL_UNICODE"
        )
    return value


def _normalize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError(
                "naive datetime is not canonical", code="NON_CANONICAL_DATETIME"
            )
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValidationError(
                "non-finite Decimal is not canonical", code="NON_CANONICAL_NUMBER"
            )
        return format(value, "f")
    if isinstance(value, PurePath):
        return _canonical_string(value.as_posix())
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(
                    "canonical object keys must be strings",
                    code="NON_CANONICAL_KEY",
                )
            result[_canonical_string(key)] = _normalize(item)
        return result
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(
                "non-finite float is not canonical", code="NON_CANONICAL_NUMBER"
            )
        return value
    if isinstance(value, str):
        return _canonical_string(value)
    if value is None or isinstance(value, (int, bool)):
        return value
    raise ValidationError(
        "value is not canonicalizable",
        code="NON_CANONICAL_TYPE",
        details={"type": type(value).__name__},
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_text(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


canonical_json = canonical_json_text


def strict_json_loads(payload: bytes | str, *, source: str = "JSON") -> Any:
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                f"{source} is not UTF-8", code="INVALID_UTF8"
            ) from exc
    elif isinstance(payload, str):
        text = payload
    else:
        raise ValidationError(
            f"{source} must be bytes or text", code="INVALID_JSON_INPUT"
        )

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValidationError(
                    f"{source} contains duplicate object key {key!r}",
                    code="DUPLICATE_JSON_KEY",
                    details={"key": key},
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValidationError(
            f"{source} contains non-finite number {value}",
            code="NON_CANONICAL_NUMBER",
        )

    try:
        value = json.loads(
            text, object_pairs_hook=pairs, parse_constant=reject_constant
        )
    except ValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{source} is invalid JSON",
            code="INVALID_JSON",
            details={"line": exc.lineno, "column": exc.colno},
        ) from exc
    _normalize(value)
    return value


def freeze_json(value: Any) -> Any:
    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            return MappingProxyType(
                {key: freeze(child) for key, child in item.items()}
            )
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)
        return item

    return freeze(_normalize(value))


def digest_bytes(
    content: bytes | bytearray | memoryview, *, domain: str = "artifact"
) -> str:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise ValidationError("content must be bytes", code="CONTENT_NOT_BYTES")
    if not isinstance(domain, str) or not domain or "\x00" in domain:
        raise ValidationError("digest domain is invalid", code="INVALID_DIGEST_DOMAIN")
    digest = hashlib.sha256(
        _DOMAIN_PREFIX + domain.encode("utf-8") + b"\x00" + bytes(content)
    ).hexdigest()
    return SHA256_PREFIX + digest


def digest_object(value: Any, *, domain: str) -> str:
    return digest_bytes(canonical_json_bytes(value), domain=domain)


def is_sha256_digest(value: object) -> bool:
    if (
        not isinstance(value, str)
        or len(value) != _DIGEST_LENGTH
        or not value.startswith(SHA256_PREFIX)
    ):
        return False
    suffix = value[len(SHA256_PREFIX) :]
    try:
        int(suffix, 16)
    except ValueError:
        return False
    return suffix == suffix.lower()


def require_sha256_digest(value: str, *, field: str = "digest") -> str:
    if not is_sha256_digest(value):
        raise ValidationError(
            f"{field} must be a lowercase sha256 digest",
            code="INVALID_DIGEST",
            details={"field": field},
        )
    return value


def verify_digest(
    content: bytes | bytearray | memoryview,
    claimed: str,
    *,
    domain: str = "artifact",
) -> None:
    require_sha256_digest(claimed)
    actual = digest_bytes(content, domain=domain)
    if not hmac.compare_digest(actual, claimed):
        raise IntegrityError(
            "content digest mismatch",
            code="DIGEST_MISMATCH",
            details={"claimed": claimed, "actual": actual, "domain": domain},
        )
