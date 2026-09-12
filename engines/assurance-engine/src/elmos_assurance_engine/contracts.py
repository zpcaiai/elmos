"""Normative contracts, RevisionSet, canonical serialization, and state definitions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

MAX_JSON_INTEGER = 2**53 - 1
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")

REVISION_FIELDS = (
    "source",
    "target",
    "artifact",
    "scope",
    "contract",
    "policy",
    "environment",
    "toolchain",
    "suite",
    "data",
    "comparator",
    "rules",
)

GATE_LEVELS = {
    "E0": {"build"},
    "E1": {"build", "contract"},
    "E2": {"build", "contract", "smoke"},
    "E3": {"build", "contract", "smoke", "regression"},
    "E4": {"build", "contract", "smoke", "regression", "differential", "mutation"},
    "E5": {"build", "contract", "smoke", "regression", "differential", "mutation", "proof", "audit"},
}


class GateDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExecutionStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    INFRA_ERROR = "INFRA_ERROR"
    NOT_RUN = "NOT_RUN"


class ObligationStatus(str, Enum):
    REQUIRED = "REQUIRED"
    APPROVED_NOT_APPLICABLE = "APPROVED_NOT_APPLICABLE"
    OPTIONAL = "OPTIONAL"


def canonical_json_bytes(value: Any) -> bytes:
    """Produces canonical JSON bytes per elmos.assurance/v4.

    Rejects floats, non-string dictionary keys, and integers exceeding 53 bits.
    Decimal values must be serialized as strings.
    """
    def check(v: Any, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("JSON_DEPTH_LIMIT_EXCEEDED")
        if v is None or isinstance(v, (str, bool)):
            return
        if isinstance(v, int):
            if abs(v) > MAX_JSON_INTEGER:
                raise ValueError("JSON_INTEGER_OVERFLOW")
            return
        if isinstance(v, float):
            raise ValueError("FLOAT_NOT_ALLOWED_IN_CANONICAL_JSON")
        if isinstance(v, (list, tuple)):
            for item in v:
                check(item, depth + 1)
            return
        if isinstance(v, dict):
            for k, val in v.items():
                if not isinstance(k, str):
                    raise ValueError("NON_STRING_KEY_IN_CANONICAL_JSON")
                check(val, depth + 1)
            return
        raise ValueError(f"UNSUPPORTED_CANONICAL_TYPE: {type(v)}")

    check(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    """Compute sha256 hex digest of canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_sha256_hex(val: str, field_name: str = "field") -> str:
    if not isinstance(val, str) or not SHA256_HEX_PATTERN.fullmatch(val):
        raise ValueError(f"INVALID_SHA256_DIGEST: {field_name}={val}")
    return val


@dataclass(frozen=True)
class RevisionSet:
    """Immutable, content-addressed binding across all 12 validation facets."""
    source: str
    target: str
    artifact: str
    scope: str
    contract: str
    policy: str
    environment: str
    toolchain: str
    suite: str
    data: str
    comparator: str
    rules: str

    def __post_init__(self) -> None:
        for f in REVISION_FIELDS:
            val = getattr(self, f)
            require_sha256_hex(val, f)

    def to_dict(self) -> dict[str, str]:
        return {f: getattr(self, f) for f in REVISION_FIELDS}

    def digest(self) -> str:
        return sha256_digest(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> RevisionSet:
        for f in REVISION_FIELDS:
            if f not in data:
                raise ValueError(f"MISSING_REVISION_FIELD: {f}")
        return cls(**{f: data[f] for f in REVISION_FIELDS})


@dataclass(frozen=True)
class AssertionIR:
    """Finite assertion representation for wire/runtime validation."""
    assertion_id: str
    assertion_type: str
    pointer: str
    expected: Any
    severity: str = "critical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "assertion_type": self.assertion_type,
            "pointer": self.pointer,
            "expected": self.expected,
            "severity": self.severity,
        }


@dataclass
class ContractSnapshot:
    """Versioned contract snapshot with separation of declared, observed, and approved."""
    snapshot_id: str
    version: str
    declared_interfaces: dict[str, Any] = field(default_factory=dict)
    observed_interfaces: dict[str, Any] = field(default_factory=dict)
    inferred_interfaces: dict[str, Any] = field(default_factory=dict)
    approved_normative_interfaces: dict[str, Any] = field(default_factory=dict)
    assertions: list[AssertionIR] = field(default_factory=list)

    def digest(self) -> str:
        return sha256_digest({
            "snapshot_id": self.snapshot_id,
            "version": self.version,
            "declared": self.declared_interfaces,
            "observed": self.observed_interfaces,
            "inferred": self.inferred_interfaces,
            "approved": self.approved_normative_interfaces,
            "assertions": [a.to_dict() for a in self.assertions],
        })
