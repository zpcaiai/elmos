"""Small immutable models and canonical serialization helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .errors import ContractError, ErrorInfo


class Status(StrEnum):
    PLANNED = "PLANNED"
    LOCAL_ENGINEERING_VALIDATED = "LOCAL_ENGINEERING_VALIDATED"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    P05_DEPLOYMENT_COMPLETE = "P05_DEPLOYMENT_COMPLETE"
    NOT_CERTIFIED = "NOT_CERTIFIED"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def require_sha256_digest(value: Any, name: str) -> str:
    if not is_sha256_digest(value):
        raise ContractError("DIGEST_INVALID", f"{name} must be sha256 followed by 64 lowercase hex characters")
    return str(value)


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("INVALID_INPUT", f"{name} must be an object")
    return dict(value)


def require_string(value: Any, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ContractError("INVALID_INPUT", f"{name} must be a non-empty string")
    return value


def require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError("INVALID_INPUT", f"{name} must be a boolean")
    return value


def require_int(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError("INVALID_INPUT", f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ContractError("INVALID_INPUT", f"{name} must be >= {minimum}")
    return value


def string_list(value: Any, name: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractError("INVALID_INPUT", f"{name} must be an array of strings")
    result = [require_string(item, f"{name}[]") for item in value]
    if not allow_empty and not result:
        raise ContractError("INVALID_INPUT", f"{name} must not be empty")
    return result


_PATH_PART = re.compile(r"^[^/\\]+$")


def relative_path(value: Any, name: str = "path") -> str:
    path = require_string(value, name).replace("\\", "/")
    if path.startswith(("/", "~")) or ":" in path.split("/")[0]:
        raise ContractError("PATH_OUTSIDE_WORKSPACE", f"{name} must be relative")
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts) or not parts or any(not _PATH_PART.match(part) for part in parts):
        raise ContractError("PATH_OUTSIDE_WORKSPACE", f"{name} contains an unsafe path")
    return "/".join(parts)


def paths_overlap(left: str, right: str) -> bool:
    a, b = left.casefold().rstrip("/"), right.casefold().rstrip("/")
    if any(c in a + b for c in "*?["):
        # A wildcard is conservatively treated as overlapping its fixed prefix.
        a, b = a.split("*", 1)[0].split("?", 1)[0], b.split("*", 1)[0].split("?", 1)[0]
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


@dataclass(frozen=True, slots=True)
class DispatchResult:
    skill: str
    status: Status
    output: dict[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    error: ErrorInfo | None = None
    side_effects_performed: bool = False
    certification: Status = Status.NOT_CERTIFIED
    observed_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "status": self.status.value,
            "output": self.output,
            "reasons": list(self.reasons),
            "error": self.error.to_dict() if self.error else None,
            "sideEffectsPerformed": self.side_effects_performed,
            "certification": self.certification.value,
            "observedAt": self.observed_at,
        }


def error_result(skill: str, info: ErrorInfo, *, status: Status = Status.BLOCKED) -> DispatchResult:
    return DispatchResult(skill=skill, status=status, reasons=(info.code,), error=info)
