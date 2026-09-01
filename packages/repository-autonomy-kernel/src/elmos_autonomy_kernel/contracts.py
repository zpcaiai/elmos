"""Canonical value handling: digests, identifiers, envelopes, strict decoding.

Everything the kernel hashes, signs, caches or compares goes through
:func:`canonical_json`.  Two structurally equal payloads must produce one byte
string on every machine and every Python version, or content addressing is a
lie.  The rules are: sorted keys, no insignificant whitespace, UTF-8 without
escaping, ``Decimal`` rendered losslessly as a string, and no float ever.

Floats are rejected rather than coerced.  ``0.1 + 0.2`` must not be able to
produce two different cache keys on two machines.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from .errors import KernelError

__all__ = [
    "Status",
    "canonical_json",
    "digest",
    "digest_bytes",
    "SkillResult",
    "Observability",
    "require_mapping",
    "require_str",
    "require_int",
    "require_decimal",
    "require_bool",
    "require_str_seq",
    "reject_unknown_fields",
    "utc_now",
    "parse_timestamp",
    "format_timestamp",
    "IDENTIFIER_RE",
    "require_identifier",
]

#: Identifiers are ASCII, bounded and path-safe.  They end up in file names,
#: SQL keys, OTel attributes and cache keys; a permissive identifier is a
#: traversal bug waiting to happen.
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

_MAX_STRING = 1 << 20  # 1 MiB per individual string field
_MAX_DEPTH = 64


class Status(StrEnum):
    """Outcome of a skill invocation.

    The four failure-ish states are *not* interchangeable, and nothing in this
    package is permitted to widen one into another:

    ``PARTIAL``
        Real work landed and real work did not.  Never renderable as success.
    ``INTERRUPTED``
        Execution stopped without a verdict.  The work may or may not have
        landed; the caller must reconcile, not retry blindly.
    ``FAILED``
        A verdict was reached and it is negative.
    ``NOT_APPLICABLE``
        The input contract was not met.  Nothing was attempted.
    """

    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    @property
    def is_success(self) -> bool:
        return self is Status.SUCCEEDED


# --- canonical encoding ------------------------------------------------------


def _canonicalise(value: Any, *, depth: int = 0, path: str = "$") -> Any:
    if depth > _MAX_DEPTH:
        raise KernelError(
            code="INPUT_TOO_LARGE",
            message=f"payload nested deeper than {_MAX_DEPTH} levels at {path}",
            recommended_action="flatten the payload",
        )
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"float at {path} is not canonically representable; "
                "use Decimal or an integer of the smallest unit"
            ),
            recommended_action="replace the float with Decimal or a scaled integer",
        )
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"non-finite Decimal at {path}",
                recommended_action="supply a finite quantity",
            )
        # ``normalize`` collapses 1.10 and 1.1 to one representation; the
        # exponent is then rendered without scientific notation so that the
        # string form is stable and comparable.
        normalised = value.normalize()
        sign, digits, exponent = normalised.as_tuple()
        if isinstance(exponent, int) and exponent > 0:
            normalised = normalised.quantize(Decimal(1))
        return format(normalised, "f")
    if isinstance(value, str):
        if len(value) > _MAX_STRING:
            raise KernelError(
                code="INPUT_TOO_LARGE",
                message=f"string at {path} exceeds {_MAX_STRING} bytes",
                recommended_action="store the blob as an artifact and reference its digest",
            )
        # NFC keeps visually identical strings from hashing differently.
        return unicodedata.normalize("NFC", value)
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key in value:
            if not isinstance(key, str):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"non-string mapping key {key!r} at {path}",
                    recommended_action="use string keys",
                )
            out[unicodedata.normalize("NFC", key)] = _canonicalise(
                value[key], depth=depth + 1, path=f"{path}.{key}"
            )
        return dict(sorted(out.items()))
    if isinstance(value, (list, tuple)):
        return [
            _canonicalise(item, depth=depth + 1, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, (set, frozenset)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"set at {path} has no canonical order",
            recommended_action="sort the set into a list before hashing",
        )
    raise KernelError(
        code="MALFORMED_INPUT",
        message=f"value of type {type(value).__name__} at {path} is not canonicalisable",
        recommended_action="convert the value to a JSON-native type first",
    )


def canonical_json(value: Any) -> str:
    """Return the canonical JSON text for ``value``."""

    return json.dumps(
        _canonicalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    """Content address of ``value`` as ``sha256:<hex>``."""

    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_bytes(data: bytes) -> str:
    """Content address of raw bytes as ``sha256:<hex>``."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- time --------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def format_timestamp(value: datetime) -> str:
    """RFC3339 in UTC with microsecond precision and a ``Z`` suffix."""

    if value.tzinfo is None:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="naive datetime has no canonical form",
            recommended_action="attach a timezone (UTC) before serialising",
        )
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def parse_timestamp(value: Any, field_name: str = "timestamp") -> datetime:
    text = require_str(value, field_name)
    normalised = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} is not an RFC3339 timestamp: {text!r}",
            recommended_action="use RFC3339, e.g. 2026-01-01T00:00:00.000000Z",
        ) from exc
    if parsed.tzinfo is None:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} lacks a timezone offset",
            recommended_action="include an explicit offset or Z",
        )
    return parsed.astimezone(UTC)


# --- strict decoding ---------------------------------------------------------


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be an object, got {type(value).__name__}",
            recommended_action=f"supply {field_name} as a JSON object",
        )
    return value


def require_str(value: Any, field_name: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be a non-empty string",
            recommended_action=f"supply {field_name}",
        )
    if len(value) > max_length:
        raise KernelError(
            code="INPUT_TOO_LARGE",
            message=f"{field_name} exceeds {max_length} characters",
            recommended_action="shorten the value or pass an artifact reference",
        )
    return unicodedata.normalize("NFC", value)


def require_identifier(value: Any, field_name: str) -> str:
    text = require_str(value, field_name, max_length=128)
    if not IDENTIFIER_RE.match(text):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={text!r} is not a valid identifier",
            recommended_action="use [A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        )
    return text


def require_int(value: Any, field_name: str, *, minimum: int | None = None,
                maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be an integer",
            recommended_action=f"supply {field_name} as an integer",
        )
    if minimum is not None and value < minimum:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={value} is below the minimum {minimum}",
            recommended_action=f"supply {field_name} >= {minimum}",
        )
    if maximum is not None and value > maximum:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={value} exceeds the maximum {maximum}",
            recommended_action=f"supply {field_name} <= {maximum}",
        )
    return value


def require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be a boolean",
            recommended_action=f"supply {field_name} as true or false",
        )
    return value


def require_decimal(value: Any, field_name: str, *, minimum: Decimal | None = None) -> Decimal:
    """Decode a quantity.

    Floats are refused on the way in, not silently accepted and rounded: a
    quantity that arrived as a float has already lost the guarantee that two
    parties agree on its value.
    """

    if isinstance(value, bool) or isinstance(value, float):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be a decimal string or integer, not a float",
            recommended_action="send the quantity as a JSON string, e.g. \"1.25\"",
        )
    try:
        parsed = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} is not a decimal: {value!r}",
            recommended_action=f"supply {field_name} as a decimal string",
        ) from exc
    if not parsed.is_finite():
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be finite",
            recommended_action=f"supply a finite {field_name}",
        )
    if minimum is not None and parsed < minimum:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name}={parsed} is below the minimum {minimum}",
            recommended_action=f"supply {field_name} >= {minimum}",
        )
    return parsed


def require_str_seq(value: Any, field_name: str, *, allow_empty: bool = True,
                    max_items: int = 4096) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"{field_name} must be an array of strings",
            recommended_action=f"supply {field_name} as a JSON array",
        )
    if len(value) > max_items:
        raise KernelError(
            code="INPUT_TOO_LARGE",
            message=f"{field_name} exceeds {max_items} items",
            recommended_action="paginate the input",
        )
    items = tuple(require_str(item, f"{field_name}[{index}]") for index, item in enumerate(value))
    if not items and not allow_empty:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message=f"{field_name} must not be empty",
            recommended_action=f"supply at least one {field_name} entry",
        )
    return items


def reject_unknown_fields(payload: Mapping[str, Any], known: Iterable[str], *,
                          field_name: str = "payload") -> None:
    """Fail closed on fields the kernel does not understand.

    Silently ignoring an unknown field is how a caller ends up believing a
    constraint was applied when it was dropped.
    """

    unknown = sorted(set(payload) - set(known))
    if unknown:
        raise KernelError(
            code="UNKNOWN_FIELD",
            message=f"{field_name} contains unsupported fields: {unknown}",
            recommended_action="remove the fields or upgrade the kernel",
            details={"unknown": unknown, "supported": sorted(set(known))},
        )


# --- observability & result envelope ----------------------------------------


@dataclass(frozen=True, slots=True)
class Observability:
    """The identity every kernel emission must carry.

    Each SKILL.md lists these as mandatory.  They are a dataclass rather than a
    free dict so that a missing tenant or a missing policy snapshot hash is a
    construction error at the call site instead of an absent OTel attribute
    discovered during an incident.
    """

    tenant_id: str
    account_id: str
    run_id: str
    step_id: str
    attempt_no: int
    task_spec_version: str
    repo_snapshot_sha: str
    workflow_version: str
    skill_version: str
    workspace_id: str
    environment_id: str
    permission_profile_id: str
    policy_snapshot_hash: str
    fencing_token: int

    def __post_init__(self) -> None:
        for name in (
            "tenant_id", "account_id", "run_id", "step_id", "task_spec_version",
            "repo_snapshot_sha", "workflow_version", "skill_version",
            "workspace_id", "environment_id", "permission_profile_id",
            "policy_snapshot_hash",
        ):
            require_str(getattr(self, name), name)
        require_int(self.attempt_no, "attempt_no", minimum=1)
        require_int(self.fencing_token, "fencing_token", minimum=1)

    def to_payload(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "accountId": self.account_id,
            "runId": self.run_id,
            "stepId": self.step_id,
            "attemptNo": self.attempt_no,
            "taskSpecVersion": self.task_spec_version,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "workflowVersion": self.workflow_version,
            "skillVersion": self.skill_version,
            "workspaceId": self.workspace_id,
            "environmentId": self.environment_id,
            "permissionProfileId": self.permission_profile_id,
            "policySnapshotHash": self.policy_snapshot_hash,
            "fencingToken": self.fencing_token,
        }


@dataclass(frozen=True, slots=True)
class SkillResult:
    """The envelope every capability returns.

    ``machine_wall_clock_ms`` is machine time, never a human-equivalent
    estimate; the two are reported in different fields by
    :mod:`.costeta` precisely so that neither can be mistaken for the other.
    """

    skill: str
    status: Status
    outputs: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None
    evidence_ids: tuple[str, ...] = ()
    machine_wall_clock_ms: int = 0
    observability: Observability | None = None

    def __post_init__(self) -> None:
        require_identifier(self.skill, "skill")
        require_int(self.machine_wall_clock_ms, "machine_wall_clock_ms", minimum=0)
        if self.status is Status.SUCCEEDED and self.error is not None:
            raise ValueError("a SUCCEEDED result must not carry an error")
        if self.status is not Status.SUCCEEDED and self.status is not Status.PARTIAL:
            if self.error is None:
                raise ValueError(f"a {self.status} result must carry an error payload")

    @property
    def succeeded(self) -> bool:
        """True only for ``SUCCEEDED``.

        ``PARTIAL`` and ``INTERRUPTED`` are deliberately excluded; this
        property is what release gating reads.
        """

        return self.status is Status.SUCCEEDED

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "skill": self.skill,
            "status": str(self.status),
            "outputs": dict(self.outputs),
            "evidenceIds": list(self.evidence_ids),
            "machineWallClockMs": self.machine_wall_clock_ms,
        }
        if self.error is not None:
            payload["error"] = dict(self.error)
        if self.observability is not None:
            payload["observability"] = self.observability.to_payload()
        return payload

    @classmethod
    def failure(cls, skill: str, error: KernelError, *,
                status: Status = Status.FAILED,
                outputs: Mapping[str, Any] | None = None,
                machine_wall_clock_ms: int = 0,
                observability: Observability | None = None) -> SkillResult:
        if status is Status.SUCCEEDED:
            raise ValueError("failure() cannot produce SUCCEEDED")
        return cls(
            skill=skill,
            status=status,
            outputs=outputs or {},
            error=error.to_payload(),
            evidence_ids=error.evidence_ids,
            machine_wall_clock_ms=machine_wall_clock_ms,
            observability=observability,
        )
