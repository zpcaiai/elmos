"""Primitive contracts shared by every repository-refactoring Skill handler.

This module is deliberately dependency-free.  Everything downstream of it —
discovery, indexing, planning, transformation, verification, evidence — is built
on the validators, enums and canonical-encoding helpers defined here, so that a
single implementation decides what "valid input" and "stable digest" mean for
the whole package.

Design rules enforced here:

* Fail closed.  Every validator raises :class:`ContractError` with a stable
  machine-readable ``code``; no validator ever coerces an unknown shape into a
  default.
* Deterministic encoding.  :func:`canonical_json` is the only serialiser used
  for digests, so the same logical payload always produces the same digest on
  any host, Python build or dict-insertion order.
* No ambient authority.  Nothing in this module reads the clock implicitly for
  business decisions (callers pass ``now``), touches the filesystem, spawns a
  process or opens a socket.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum, StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContractError(ValueError):
    """A fail-closed contract violation carrying a stable machine code."""

    __slots__ = ("code", "message", "details")

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = dict(self.details)
        return payload


# ---------------------------------------------------------------------------
# Enumerations (all values mirror contracts/*.schema.json exactly)
# ---------------------------------------------------------------------------


class Status(StrEnum):
    """Terminal status of one Skill invocation."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    FAILED = "failed"


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"

    @property
    def rank(self) -> int:
        return int(self.value[1:])

    @classmethod
    def max_of(cls, values: Iterable[RiskClass]) -> RiskClass:
        best = cls.R0
        for value in values:
            if value.rank > best.rank:
                best = value
        return best


class AdapterLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"

    @property
    def rank(self) -> int:
        return int(self.value[1:])


class ExecutionMode(StrEnum):
    ANALYZE_ONLY = "analyze-only"
    PROPOSAL = "proposal"
    SUPERVISED = "supervised"
    AUTONOMOUS_LOW_RISK = "autonomous-low-risk"
    FLEET_WAVE = "fleet-wave"

    @property
    def mutates_workspace(self) -> bool:
        return self in {
            ExecutionMode.PROPOSAL,
            ExecutionMode.SUPERVISED,
            ExecutionMode.AUTONOMOUS_LOW_RISK,
            ExecutionMode.FLEET_WAVE,
        }


class NetworkPolicy(StrEnum):
    DENY = "deny"
    RESTORE_ONLY = "restore-only"
    ALLOWLISTED = "allowlisted"


class RecipeStatus(StrEnum):
    DRAFT = "draft"
    QUARANTINED = "quarantined"
    VERIFIED = "verified"
    CERTIFIED = "certified"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"

    @property
    def autonomous_eligible(self) -> bool:
        return self in {RecipeStatus.VERIFIED, RecipeStatus.CERTIFIED}


class RollbackStrategy(StrEnum):
    REVERSE_PATCH = "reverse-patch"
    SNAPSHOT_RESTORE = "snapshot-restore"
    COMPENSATION = "compensation"
    FORWARD_ONLY = "forward-only"


class PredicateType(StrEnum):
    SEMANTIC_QUERY = "semantic-query"
    BUILD_QUERY = "build-query"
    FILE_QUERY = "file-query"
    VERSION_QUERY = "version-query"
    CONTRACT_QUERY = "contract-query"
    METRIC_QUERY = "metric-query"
    MANUAL = "manual"


class OnUnknown(StrEnum):
    FAIL = "fail"
    WARN = "warn"
    APPROVAL = "approval"


class ConflictPolicy(StrEnum):
    FAIL = "fail"
    SERIALIZE = "serialize"
    MERGE_IF_DISJOINT = "merge-if-disjoint"


class FormatPolicy(StrEnum):
    PRESERVE = "preserve"
    TOUCHED_RANGE = "touched-range"
    FILE = "file"
    REPOSITORY = "repository"


class GateOutcome(StrEnum):
    PASS = "pass"  # noqa: S105 - a gate outcome, not a credential
    FAIL = "fail"
    WAIVED = "waived"
    NOT_APPLICABLE = "not-applicable"


class FailureClass(StrEnum):
    """How the orchestrator must react to a failure."""

    RETRYABLE = "retryable"
    REPAIRABLE = "repairable"
    APPROVAL_REQUIRED = "approval-required"
    ROLLBACK_REQUIRED = "rollback-required"
    TERMINAL = "terminal"


class EntityKind(StrEnum):
    REPOSITORY = "repository"
    MODULE = "module"
    BUILD_TARGET = "build-target"
    SOURCE_FILE = "source-file"
    GENERATED_FILE = "generated-file"
    NAMESPACE = "namespace"
    PACKAGE = "package"
    TYPE = "type"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    FIELD = "field"
    VARIABLE = "variable"
    MACRO = "macro"
    TEMPLATE = "template"
    API_CONTRACT = "api-contract"
    EVENT_CONTRACT = "event-contract"
    DATABASE_OBJECT = "database-object"
    CONFIG_KEY = "config-key"
    TEST = "test"
    DEPLOYMENT_UNIT = "deployment-unit"


class RelationshipType(StrEnum):
    DECLARES = "declares"
    REFERENCES = "references"
    CALLS = "calls"
    OVERRIDES = "overrides"
    IMPLEMENTS = "implements"
    INHERITS = "inherits"
    IMPORTS = "imports"
    EXPORTS = "exports"
    READS = "reads"
    WRITES = "writes"
    PUBLISHES = "publishes"
    SUBSCRIBES = "subscribes"
    SERIALIZES = "serializes"
    PERSISTS = "persists"
    TESTS = "tests"
    OWNS = "owns"
    BUILDS = "builds"
    DEPLOYS = "deploys"
    GENERATES = "generates"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request-changes"
    APPROVE_WITH_CONDITIONS = "approve-with-conditions"


class CompatibilityImpact(StrEnum):
    ADDITIVE = "additive"
    SOURCE_BREAK = "source-break"
    BINARY_BREAK = "binary-break"
    WIRE_BREAK = "wire-break"
    BEHAVIOR_RISK = "behavior-risk"

    @property
    def is_break(self) -> bool:
        return self is not CompatibilityImpact.ADDITIVE


# ---------------------------------------------------------------------------
# Canonical encoding and digests
# ---------------------------------------------------------------------------

DIGEST_PREFIX = "sha256:"
DIGEST_LENGTH = len(DIGEST_PREFIX) + 64
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _canonicalise(value: Any, path: str) -> Any:
    """Reduce ``value`` to a JSON-canonical form or fail closed."""

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ContractError("non_finite_number", f"{path} must be a finite number")
        return format(value.normalize(), "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("non_finite_number", f"{path} must be a finite number")
        # Route floats through Decimal so 1.0 and 1 never collide by accident
        # while 0.1 keeps a stable shortest round-trip representation.
        return format(Decimal(repr(value)).normalize(), "f")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key in value:
            if not isinstance(key, str):
                raise ContractError("non_string_key", f"{path} contains a non-string object key")
            out[unicodedata.normalize("NFC", key)] = _canonicalise(value[key], f"{path}.{key}")
        return {key: out[key] for key in sorted(out)}
    if isinstance(value, (bytes, bytearray)):
        raise ContractError("unencodable_value", f"{path} must not contain raw bytes")
    if isinstance(value, Sequence):
        return [_canonicalise(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, (set, frozenset)):
        raise ContractError("unencodable_value", f"{path} must be an ordered sequence, not a set")
    if isinstance(value, datetime):
        return isoformat_utc(value)
    raise ContractError("unencodable_value", f"{path} has a type that cannot be canonically encoded")


def canonical_json(value: Any) -> str:
    """Serialise ``value`` deterministically (sorted keys, no insignificant space)."""

    return json.dumps(
        _canonicalise(value, "$"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def sha256_payload(value: Any) -> str:
    """Digest of the canonical JSON encoding of ``value``."""

    return DIGEST_PREFIX + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Digest of text content, normalised so CRLF/LF never changes the digest."""

    return sha256_bytes(normalize_newlines(text).encode("utf-8"))


def require_digest(value: Any, field_name: str) -> str:
    text = require_string(value, field_name)
    if not _DIGEST_RE.match(text):
        raise ContractError("invalid_digest", f"{field_name} must be a lowercase sha256:<64hex> digest")
    return text


def is_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_DIGEST_RE.match(value))


def merge_digests(values: Iterable[str]) -> str:
    """Order-independent digest over a set of digests (used for manifests)."""

    ordered = sorted({require_digest(value, "digest") for value in values})
    return sha256_payload({"members": ordered})


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ContractError("naive_timestamp", "timestamps must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any, field_name: str) -> datetime:
    text = require_string(value, field_name)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ContractError("invalid_timestamp", f"{field_name} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError("naive_timestamp", f"{field_name} must carry an explicit UTC offset")
    return parsed.astimezone(UTC)


# ---------------------------------------------------------------------------
# Scalar validators
# ---------------------------------------------------------------------------


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("invalid_object", f"{field_name} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise ContractError("non_string_key", f"{field_name} must use string keys")
    return value


def optional_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    return require_mapping(value, field_name)


def require_string(value: Any, field_name: str, *, min_length: int = 1, max_length: int = 8192) -> str:
    if not isinstance(value, str):
        raise ContractError("invalid_string", f"{field_name} must be a string")
    text = unicodedata.normalize("NFC", value).strip()
    if len(text) < min_length:
        raise ContractError("invalid_string", f"{field_name} must have at least {min_length} character(s)")
    if len(text) > max_length:
        raise ContractError("invalid_string", f"{field_name} must have at most {max_length} character(s)")
    if any(ord(char) < 0x20 and char not in "\t" for char in text):
        raise ContractError("invalid_string", f"{field_name} must not contain control characters")
    return text


def optional_string(value: Any, field_name: str, *, max_length: int = 8192) -> str | None:
    if value is None:
        return None
    return require_string(value, field_name, max_length=max_length)


def optional_text(value: Any, field_name: str, *, max_length: int = 8192) -> str:
    """A string field where empty is a legitimate value.

    Captured process output, a reason with nothing to say and a blank comment
    are all meaningfully empty; forcing them through :func:`require_string`
    would reject valid data.  Control characters are still refused.
    """

    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractError("invalid_string", f"{field_name} must be a string")
    if len(value) > max_length:
        raise ContractError("invalid_string", f"{field_name} must have at most {max_length} character(s)")
    if any(ord(char) < 0x20 and char not in "\t\n\r" for char in value):
        raise ContractError("invalid_string", f"{field_name} must not contain control characters")
    return unicodedata.normalize("NFC", value)


def require_identifier(value: Any, field_name: str, *, max_length: int = 128) -> str:
    text = require_string(value, field_name, max_length=max_length)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", text):
        raise ContractError(
            "invalid_identifier",
            f"{field_name} must match [A-Za-z0-9][A-Za-z0-9._:-]*",
        )
    return text


def require_enum(value: Any, enum_cls: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    if not isinstance(value, str):
        raise ContractError("invalid_enum", f"{field_name} must be a string")
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(sorted(str(member.value) for member in enum_cls))
        raise ContractError("invalid_enum", f"{field_name} must be one of: {allowed}") from exc


def optional_enum(value: Any, enum_cls: type[Enum], field_name: str, default: Any = None) -> Any:
    if value is None:
        return default
    return require_enum(value, enum_cls, field_name)


def integer_value(
    value: Any,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError("invalid_integer", f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise ContractError("integer_out_of_range", f"{field_name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ContractError("integer_out_of_range", f"{field_name} must be <= {maximum}")
    return int(value)


def decimal_value(
    value: Any,
    field_name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    if isinstance(value, bool):
        raise ContractError("invalid_number", f"{field_name} must be a number")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, float):
        parsed = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ContractError("invalid_number", f"{field_name} must be a decimal number") from exc
    else:
        raise ContractError("invalid_number", f"{field_name} must be a number")
    if not parsed.is_finite():
        raise ContractError("invalid_number", f"{field_name} must be finite")
    if minimum is not None and parsed < minimum:
        raise ContractError("number_out_of_range", f"{field_name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ContractError("number_out_of_range", f"{field_name} must be <= {maximum}")
    return parsed


def finite_probability(value: Any, field_name: str) -> Decimal:
    return decimal_value(value, field_name, minimum=Decimal("0"), maximum=Decimal("1"))


def require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError("invalid_boolean", f"{field_name} must be a boolean")
    return value


def optional_bool(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    return require_bool(value, field_name)


def require_sequence(value: Any, field_name: str, *, allow_empty: bool = True) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractError("invalid_array", f"{field_name} must be an array")
    items = tuple(value)
    if not items and not allow_empty:
        raise ContractError("invalid_array", f"{field_name} must not be empty")
    return items


def require_string_sequence(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
    unique: bool = False,
    max_items: int = 100_000,
) -> tuple[str, ...]:
    items = require_sequence(value, field_name, allow_empty=allow_empty)
    if len(items) > max_items:
        raise ContractError("array_too_large", f"{field_name} must have at most {max_items} item(s)")
    parsed = tuple(require_string(item, f"{field_name}[]") for item in items)
    if unique and len(set(parsed)) != len(parsed):
        raise ContractError("duplicate_entry", f"{field_name} must not contain duplicates")
    return parsed


def require_mapping_sequence(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
    max_items: int = 100_000,
) -> tuple[Mapping[str, Any], ...]:
    items = require_sequence(value, field_name, allow_empty=allow_empty)
    if len(items) > max_items:
        raise ContractError("array_too_large", f"{field_name} must have at most {max_items} item(s)")
    return tuple(require_mapping(item, f"{field_name}[]") for item in items)


def reject_unknown_fields(value: Mapping[str, Any], allowed: Iterable[str], field_name: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ContractError(
            "unknown_field",
            f"{field_name} has unknown field(s): " + ", ".join(unknown),
            {"unknown": unknown},
        )


def reject_server_fields(value: Mapping[str, Any], server_owned: Iterable[str], field_name: str) -> None:
    """Callers may never supply server-derived fields; doing so is forgery."""

    forged = sorted(set(value) & set(server_owned))
    if forged:
        raise ContractError(
            "server_field_forgery",
            f"{field_name} may not carry server-derived field(s): " + ", ".join(forged),
            {"fields": forged},
        )


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def normalize_relative_path(value: Any, field_name: str) -> str:
    """Normalise a workspace-relative POSIX path, refusing every escape form.

    Rejects absolute paths, drive letters, UNC prefixes, ``..`` segments, NUL
    bytes, backslash separators, trailing dots/spaces and Windows device names,
    because each of those has been used to escape a sandbox root at some point.
    """

    text = require_string(value, field_name, max_length=4096)
    if "\x00" in text:
        raise ContractError("invalid_path", f"{field_name} must not contain NUL bytes")
    if "\\" in text:
        raise ContractError("invalid_path", f"{field_name} must use '/' as the path separator")
    if text.startswith("/"):
        raise ContractError("invalid_path", f"{field_name} must be workspace-relative")
    if re.match(r"^[A-Za-z]:", text):
        raise ContractError("invalid_path", f"{field_name} must not carry a drive letter")
    segments: list[str] = []
    for segment in text.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise ContractError("path_escape", f"{field_name} must not contain '..' segments")
        if segment != segment.rstrip(". "):
            raise ContractError("invalid_path", f"{field_name} segments must not end with '.' or space")
        if segment.split(".")[0].upper() in _WINDOWS_RESERVED:
            raise ContractError("invalid_path", f"{field_name} must not use a reserved device name")
        segments.append(segment)
    if not segments:
        raise ContractError("invalid_path", f"{field_name} must not be empty after normalisation")
    return "/".join(segments)


def path_within(path: str, prefix: str) -> bool:
    """True when ``path`` is ``prefix`` itself or lives underneath it."""

    if prefix in ("", "."):
        return True
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def match_path_glob(path: str, pattern: str) -> bool:
    """POSIX-style glob with ``**`` support, evaluated segment-wise.

    ``fnmatch`` is unusable here because its ``*`` crosses ``/`` boundaries,
    which would silently widen every Recipe file selector.

    ``**`` spans **zero or more** segments.  That makes ``a/**/b`` match
    ``a/b``, and makes ``a/**`` cover the directory ``a`` itself — the reading
    every directory-prefix rule in this package relies on.
    """

    return _glob_match(path.split("/"), pattern.split("/"))


def _glob_match(path_parts: Sequence[str], pattern_parts: Sequence[str]) -> bool:
    if not pattern_parts:
        return not path_parts
    head, rest = pattern_parts[0], pattern_parts[1:]
    if head == "**":
        if not rest:
            return True
        for index in range(len(path_parts) + 1):
            if _glob_match(path_parts[index:], rest):
                return True
        return False
    if not path_parts:
        return False
    if not _segment_match(path_parts[0], head):
        return False
    return _glob_match(path_parts[1:], rest)


def _segment_match(segment: str, pattern: str) -> bool:
    regex = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            regex.append("[^/]*")
        elif char == "?":
            regex.append("[^/]")
        elif char == "[":
            close = pattern.find("]", index + 1)
            if close == -1:
                regex.append(re.escape(char))
            else:
                body = pattern[index + 1 : close]
                body = body.replace("\\", "\\\\")
                if body.startswith("!"):
                    body = "^" + body[1:]
                regex.append(f"[{body}]")
                index = close
        else:
            regex.append(re.escape(char))
        index += 1
    regex.append("$")
    return re.match("".join(regex), segment) is not None


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_newline(text: str) -> str:
    """Return the dominant newline sequence so writes stay lossless."""

    crlf = text.count("\r\n")
    lone_cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    if crlf and crlf >= lf and crlf >= lone_cr:
        return "\r\n"
    if lone_cr and lone_cr > lf:
        return "\r"
    return "\n"


# ---------------------------------------------------------------------------
# Handler result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HandlerResult:
    """Uniform envelope returned by every Skill handler.

    ``side_effects_performed`` is not decoration: the orchestrator uses it to
    decide whether a failed step needs compensation or can simply be retried.
    """

    skill: str
    status: Status
    output: Mapping[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    canonical_owner: str = ""
    risk_class: RiskClass = RiskClass.R0
    failure_class: FailureClass | None = None
    side_effects_performed: bool = False
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "skill": self.skill,
            "status": self.status.value,
            "risk_class": self.risk_class.value,
            "canonical_owner": self.canonical_owner,
            "side_effects_performed": self.side_effects_performed,
            "output": dict(self.output),
            "reasons": list(self.reasons),
        }
        if self.failure_class is not None:
            payload["failure_class"] = self.failure_class.value
        if self.evidence:
            payload["evidence"] = dict(self.evidence)
        payload["output_digest"] = sha256_payload(payload["output"])
        return payload

    @property
    def ok(self) -> bool:
        return self.status is Status.SUCCEEDED


__all__ = [
    "AdapterLevel",
    "ApprovalDecision",
    "CompatibilityImpact",
    "ConflictPolicy",
    "ContractError",
    "DIGEST_PREFIX",
    "EntityKind",
    "ExecutionMode",
    "FailureClass",
    "FormatPolicy",
    "GateOutcome",
    "HandlerResult",
    "NetworkPolicy",
    "OnUnknown",
    "PredicateType",
    "RecipeStatus",
    "RelationshipType",
    "RiskClass",
    "RollbackStrategy",
    "Status",
    "canonical_json",
    "decimal_value",
    "detect_newline",
    "finite_probability",
    "integer_value",
    "is_digest",
    "isoformat_utc",
    "match_path_glob",
    "merge_digests",
    "normalize_newlines",
    "normalize_relative_path",
    "optional_bool",
    "optional_enum",
    "optional_mapping",
    "optional_string",
    "optional_text",
    "parse_timestamp",
    "path_within",
    "reject_server_fields",
    "reject_unknown_fields",
    "require_bool",
    "require_digest",
    "require_enum",
    "require_identifier",
    "require_mapping",
    "require_mapping_sequence",
    "require_sequence",
    "require_string",
    "require_string_sequence",
    "sha256_bytes",
    "sha256_payload",
    "sha256_text",
    "utc_now",
]
