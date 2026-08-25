"""Deterministic identity, JSON, path, and text helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from .errors import ValidationError

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ACTOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")
MAX_SAFE_JSON_INTEGER = (1 << 53) - 1
CANONICAL_JSON_VERSION = "rfc8785-ijson-safeint-v1"
CANONICAL_JSON_SHA256_CONTRACT = f"sha256:{CANONICAL_JSON_VERSION}"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    require_resource_id(prefix, "id prefix")
    return f"{prefix}-{uuid4()}"


def require_resource_id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("RESOURCE_ID_INVALID", f"{field} is not a safe resource identifier")
    candidate = value.strip()
    if not _RESOURCE_ID.fullmatch(candidate):
        raise ValidationError("RESOURCE_ID_INVALID", f"{field} is not a safe resource identifier")
    return candidate


def require_actor_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("ACTOR_ID_INVALID", "actor_id is not a safe identifier")
    candidate = value.strip()
    if not _ACTOR_ID.fullmatch(candidate):
        raise ValidationError("ACTOR_ID_INVALID", "actor_id is not a safe identifier")
    return candidate


def require_idempotency_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("IDEMPOTENCY_KEY_INVALID", "A bounded printable idempotency key is required")
    candidate = value.strip()
    if (
        not candidate
        or len(candidate.encode("utf-8")) > 200
        or any(ord(character) < 32 or ord(character) == 127 for character in candidate)
    ):
        raise ValidationError("IDEMPOTENCY_KEY_INVALID", "A bounded printable idempotency key is required")
    return candidate


def normalize_sha256(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("SHA256_INVALID", "Expected a lowercase SHA-256 digest")
    candidate = value.lower().removeprefix("sha256:")
    if not _DIGEST.fullmatch(candidate):
        raise ValidationError("SHA256_INVALID", "Expected a lowercase SHA-256 digest")
    return candidate


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_chunks(chunks: Iterable[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in chunks:
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        if isinstance(value, type):
            raise ValidationError("CANONICAL_JSON_DATACLASS_TYPE_INVALID")
        return _json_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValidationError("CANONICAL_JSON_NAIVE_DATETIME", "Canonical dates require a timezone")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError("CANONICAL_JSON_OBJECT_KEY_INVALID")
            try:
                key.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise ValidationError("CANONICAL_JSON_UNICODE_INVALID") from error
            result[key] = _json_value(item)
        return result
    if isinstance(value, (tuple, list, set, frozenset)):
        values = [_json_value(item) for item in value]
        return sorted(values, key=_canonical_encode) if isinstance(value, (set, frozenset)) else values
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ValidationError(
                "CANONICAL_JSON_INTEGER_UNSAFE",
                "Canonical integers must be exactly representable by I-JSON consumers",
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("CANONICAL_JSON_NON_FINITE", "Non-finite numbers are not canonical")
        if value.is_integer() and abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ValidationError(
                "CANONICAL_JSON_INTEGER_UNSAFE",
                "Canonical integers must be exactly representable by I-JSON consumers",
            )
        # JSON has one zero value. Normalizing negative zero avoids a digest
        # difference between Python and ECMAScript serializers.
        return 0 if value == 0 else value
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("CANONICAL_JSON_UNICODE_INVALID") from error
        return value
    raise ValidationError("CANONICAL_JSON_UNSUPPORTED", f"Unsupported canonical value: {type(value).__name__}")


def _canonical_number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    if value == 0:
        return "0"
    rendered = repr(value).lower()
    if "e" not in rendered:
        return rendered.removesuffix(".0")
    mantissa, raw_exponent = rendered.split("e", 1)
    exponent = int(raw_exponent)
    sign = ""
    if mantissa.startswith("-"):
        sign = "-"
        mantissa = mantissa[1:]
    digits = mantissa.replace(".", "")
    if -6 <= exponent < 21:
        point = exponent + 1
        if point <= 0:
            return f"{sign}0.{('0' * -point)}{digits}"
        if point >= len(digits):
            return f"{sign}{digits}{'0' * (point - len(digits))}"
        return f"{sign}{digits[:point]}.{digits[point:]}"
    coefficient = digits[0] + (f".{digits[1:]}" if len(digits) > 1 else "")
    exponent_text = f"+{exponent}" if exponent >= 0 else str(exponent)
    return f"{sign}{coefficient}e{exponent_text}"


def _canonical_encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonical_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16be"))
        return "{" + ",".join(
            f"{_canonical_encode(key)}:{_canonical_encode(value[key])}" for key in keys
        ) + "}"
    raise ValidationError("CANONICAL_JSON_UNSUPPORTED", f"Unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize RFC 8785-compatible JSON with an explicit safe-integer profile."""

    return _canonical_encode(_json_value(value))


def canonical_value(value: Any) -> Any:
    """Return the JSON-native value used by :func:`canonical_json`."""

    return _json_value(value)


def canonical_digest(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.removeprefix("\ufeff"))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        character
        for character in normalized
        if character in "\n\t" or ord(character) >= 32 and ord(character) != 127
    )
    return "\n".join(line.rstrip() for line in normalized.split("\n"))


def normalize_relative_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("RELATIVE_PATH_INVALID", "A non-empty relative path is required")
    raw = unicodedata.normalize("NFC", value).replace("\\", "/").strip()
    if not raw or raw.startswith("/") or "\x00" in raw:
        raise ValidationError("RELATIVE_PATH_INVALID", "A non-empty relative path is required")
    path = PurePosixPath(raw)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts) or path.parts[0].endswith(":"):
        raise ValidationError("RELATIVE_PATH_TRAVERSAL", "Relative path contains an unsafe segment")
    canonical = path.as_posix()
    if len(canonical.encode("utf-8")) > 1024:
        raise ValidationError("RELATIVE_PATH_TOO_LONG", "Relative path exceeds policy")
    return canonical
