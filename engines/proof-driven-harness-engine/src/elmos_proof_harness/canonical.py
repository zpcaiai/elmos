"""Canonical serialization and domain-separated content digests.

``canonical_json_bytes`` accepts only JSON-shaped values plus the explicitly
supported typed values (dataclasses, enums, UTC datetimes and paths).  Floats
must be finite.  The byte representation is stable across processes and is
used for request idempotency, evidence envelopes and signed certificates.

Raw artifact bytes are *never* canonicalized before hashing; use
``digest_bytes`` so the digest is bound to exactly the bytes that were stored.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
from datetime import UTC, datetime
from enum import Enum
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Mapping

from .errors import IntegrityError, ValidationError


SHA256_PREFIX = "sha256:"
_DIGEST_LENGTH = len(SHA256_PREFIX) + 64
_DOMAIN_PREFIX = b"elmos.proof-harness.v1\x00"


def _normalize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _normalize(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("naive datetime is not canonical", code="NON_CANONICAL_DATETIME")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError("canonical object keys must be strings", code="NON_CANONICAL_KEY")
            result[key] = _normalize(item)
        return result
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("non-finite float is not canonical", code="NON_CANONICAL_NUMBER")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValidationError(
        "value is not canonicalizable",
        code="NON_CANONICAL_TYPE",
        details={"type": type(value).__name__},
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return strict UTF-8 canonical JSON bytes for ``value``."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def freeze_json(value: Any) -> Any:
    """Return a deeply immutable canonical JSON-shaped snapshot.

    Signed and digest-bound value objects use this helper so nested caller
    dictionaries/lists cannot change after their digest was calculated.
    """

    def freeze(normalized: Any) -> Any:
        if isinstance(normalized, Mapping):
            return MappingProxyType({key: freeze(item) for key, item in normalized.items()})
        if isinstance(normalized, list):
            return tuple(freeze(item) for item in normalized)
        return normalized

    return freeze(_normalize(value))


def digest_bytes(content: bytes | bytearray | memoryview, *, domain: str = "artifact") -> str:
    """Hash exact bytes with a required semantic domain separator."""

    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise ValidationError("content must be bytes", code="CONTENT_NOT_BYTES")
    if not domain or "\x00" in domain:
        raise ValidationError("digest domain is invalid", code="INVALID_DIGEST_DOMAIN")
    payload = bytes(content)
    digest = hashlib.sha256(_DOMAIN_PREFIX + domain.encode("utf-8") + b"\x00" + payload).hexdigest()
    return SHA256_PREFIX + digest


def digest_object(value: Any, *, domain: str) -> str:
    return digest_bytes(canonical_json_bytes(value), domain=domain)


def is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str) or len(value) != _DIGEST_LENGTH or not value.startswith(SHA256_PREFIX):
        return False
    try:
        int(value[len(SHA256_PREFIX) :], 16)
    except ValueError:
        return False
    return value[len(SHA256_PREFIX) :] == value[len(SHA256_PREFIX) :].lower()


def require_sha256_digest(value: str, *, field: str = "digest") -> str:
    if not is_sha256_digest(value):
        raise ValidationError(f"{field} must be a canonical sha256 digest", code="INVALID_DIGEST", details={"field": field})
    return value


def verify_digest(content: bytes | bytearray | memoryview, claimed: str, *, domain: str = "artifact") -> None:
    require_sha256_digest(claimed)
    actual = digest_bytes(content, domain=domain)
    if not hmac.compare_digest(actual, claimed):
        raise IntegrityError(
            "content digest mismatch",
            code="DIGEST_MISMATCH",
            details={"claimed": claimed, "actual": actual, "domain": domain},
        )
