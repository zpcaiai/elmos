"""Shared closed contracts and canonical serialization helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum, IntEnum
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


class ContractError(ValueError):
    """Raised when an untrusted runtime payload violates a closed contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Status(str, Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    LOCAL_ENGINEERING_VALIDATED = "LOCAL_ENGINEERING_VALIDATED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REQUIRES_ADAPTER = "REQUIRES_ADAPTER"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_CERTIFIED = "NOT_CERTIFIED"


class ModelMode(str, Enum):
    SMART = "smart"
    MANUAL = "manual"


class OptimizationProfile(str, Enum):
    COST_PERFORMANCE = "cost_performance"
    LOWEST_COST = "lowest_cost"
    MAX_QUALITY = "max_quality"
    FASTEST = "fastest"


class FallbackPolicy(str, Enum):
    STRICT = "strict"
    SMART_WITHIN_ALLOWLIST = "smart_within_allowlist"


class VerificationPolicy(str, Enum):
    SYSTEM_REQUIRED_VERIFIERS = "system_required_verifiers"
    SELECTED_MODEL_ONLY = "selected_model_only"


class SelectionSource(str, Enum):
    UI = "ui"
    API = "api"
    CLI = "cli"
    RESUME = "resume"


class RiskLevel(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

    @classmethod
    def parse(cls, value: Any, field_name: str) -> "RiskLevel":
        if not isinstance(value, str):
            raise ContractError("invalid_risk", f"{field_name} must be a risk string")
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ContractError("invalid_risk", f"unsupported {field_name}: {value!r}") from exc


class ModelTier(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4

    @classmethod
    def parse(cls, value: Any) -> "ModelTier":
        if isinstance(value, int) and not isinstance(value, bool):
            try:
                return cls(value)
            except ValueError as exc:
                raise ContractError("invalid_model_tier", f"invalid model tier: {value}") from exc
        if isinstance(value, str):
            try:
                return cls[value.strip().upper()]
            except KeyError as exc:
                raise ContractError("invalid_model_tier", f"invalid model tier: {value!r}") from exc
        raise ContractError("invalid_model_tier", "model tier must be L0-L4")


class FailureClass(str, Enum):
    TRANSIENT_TOOL = "transient_tool"
    FORMATTING = "formatting"
    LOCALIZED_TEST_FAILURE = "localized_test_failure"
    REPEATED_TEST_FAILURE = "repeated_test_failure"
    SEMANTIC = "semantic"
    ARCHITECTURAL = "architectural"
    INTEGRATION = "integration"
    CONTEXT_LOSS = "context_loss"
    FORBIDDEN_PATH_WRITE = "forbidden_path_write"
    SECURITY_POLICY_VIOLATION = "security_policy_violation"
    BUDGET_HARD_STOP = "budget_hard_stop"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    SAFETY_REFUSAL = "safety_refusal"
    UNKNOWN = "unknown"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError("invalid_timestamp", f"{field_name} must be an ISO-8601 string")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError("invalid_timestamp", f"invalid {field_name}: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError("invalid_timestamp", f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def decimal_value(value: Any, field_name: str, *, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or value is None:
        raise ContractError("invalid_decimal", f"{field_name} must be an exact string or integer")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError("invalid_decimal", f"invalid {field_name}: {value!r}") from exc
    if not parsed.is_finite():
        raise ContractError("invalid_decimal", f"{field_name} must be finite")
    if minimum is not None and parsed < minimum:
        raise ContractError("invalid_decimal", f"{field_name} must be >= {minimum}")
    return parsed


def integer_value(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError("invalid_integer", f"{field_name} must be an integer >= {minimum}")
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_relative_path(value: Any, field_name: str = "path") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError("invalid_path", f"{field_name} must be a non-empty string")
    raw = unicodedata.normalize("NFC", value.strip())
    if "\\" in raw or raw.startswith("/") or _WINDOWS_DRIVE.match(raw):
        raise ContractError("path_escape", f"{field_name} must be repository-relative POSIX path")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError("path_escape", f"{field_name} contains unsafe path segments")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class HandlerResult:
    skill: str
    status: Status
    output: Mapping[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    canonical_owner: str = ""
    adapter_requirement: str | None = None
    certification: Status = Status.NOT_CERTIFIED
    side_effects_performed: bool = False

    def __post_init__(self) -> None:
        if self.certification is not Status.NOT_CERTIFIED:
            raise ContractError("certification_forbidden", "this runtime can only report NOT_CERTIFIED")
        if self.status is Status.NOT_CERTIFIED:
            raise ContractError("invalid_result_status", "NOT_CERTIFIED belongs in certification, not execution status")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError("invalid_object", f"{field_name} must be an object")
    return value


def require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError("invalid_string", f"{field_name} must be a non-empty string")
    return value.strip()


def require_string_sequence(value: Any, field_name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractError("invalid_array", f"{field_name} must be an array of strings")
    items = tuple(require_string(item, f"{field_name}[]") for item in value)
    if not allow_empty and not items:
        raise ContractError("invalid_array", f"{field_name} must not be empty")
    if len(set(items)) != len(items):
        raise ContractError("duplicate_value", f"{field_name} contains duplicates")
    return items


def finite_probability(value: Any, field_name: str) -> Decimal:
    parsed = decimal_value(value, field_name, minimum=Decimal("0"))
    if parsed > Decimal("1"):
        raise ContractError("invalid_probability", f"{field_name} must be <= 1")
    return parsed


def finite_positive_number(value: Any, field_name: str) -> Decimal:
    parsed = decimal_value(value, field_name, minimum=Decimal("0"))
    if parsed == 0 or not math.isfinite(float(parsed)):
        raise ContractError("invalid_number", f"{field_name} must be positive and finite")
    return parsed

