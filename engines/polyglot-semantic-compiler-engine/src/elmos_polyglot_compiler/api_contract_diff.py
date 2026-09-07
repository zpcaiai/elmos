"""Strict normalized API-contract compatibility diffing.

The helper has no sample specifications. Callers must supply two complete,
validated normalized specs; missing or malformed inputs fail closed.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional

try:
    from .native_contract_diff_bridge import diff_specs_native
except Exception:
    diff_specs_native = None


_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
)
_FIELD_TYPES = frozenset(
    {"string", "integer", "number", "boolean", "object", "array", "null"}
)
_FIELD_KEYS = frozenset({"type", "required", "nullable", "format"})
_ENDPOINT_KEYS = frozenset({"request_fields", "response_fields"})
_SPEC_KEYS = frozenset({"schema_version", "endpoints"})
_FIELD_NAME = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")


class ContractSpecError(ValueError):
    """A normalized contract does not meet the exact comparison contract."""


@dataclass
class ContractDiffItem:
    endpoint: str
    category: str
    severity: str
    description: str
    field_name: Optional[str] = None


@dataclass
class ContractDiffReport:
    total_changes: int
    breaking_changes_count: int
    warnings_count: int
    non_breaking_count: int
    is_backward_compatible: bool
    duration_ms: float
    changes: List[ContractDiffItem]


def _validate_endpoint_key(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 2_048:
        raise ContractSpecError(f"{label} is invalid")
    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0] not in _METHODS or not parts[1].startswith("/"):
        raise ContractSpecError(
            f"{label} must use the normalized 'METHOD /absolute-path' form"
        )
    if any(character.isspace() or ord(character) < 32 for character in parts[1]):
        raise ContractSpecError(f"{label} path contains unsupported whitespace")
    if "?" in parts[1] or "#" in parts[1] or "//" in parts[1]:
        raise ContractSpecError(f"{label} path is not a normalized route template")
    return value


def _validate_fields(value: Any, label: str) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise ContractSpecError(f"{label} must be an object")
    if len(value) > 10_000:
        raise ContractSpecError(f"{label} exceeds the field limit")
    normalized: Dict[str, Dict[str, Any]] = {}
    for field_name, raw_schema in value.items():
        if not isinstance(field_name, str) or _FIELD_NAME.fullmatch(field_name) is None:
            raise ContractSpecError(f"{label} contains an invalid field name")
        if not isinstance(raw_schema, Mapping):
            raise ContractSpecError(f"{label}.{field_name} must be an object")
        unknown = set(raw_schema) - _FIELD_KEYS
        missing = {"type", "required"} - set(raw_schema)
        if unknown or missing:
            raise ContractSpecError(
                f"{label}.{field_name} fields differ: "
                f"missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        field_type = raw_schema.get("type")
        if field_type not in _FIELD_TYPES:
            raise ContractSpecError(f"{label}.{field_name}.type is unsupported")
        required = raw_schema.get("required")
        if type(required) is not bool:
            raise ContractSpecError(f"{label}.{field_name}.required must be boolean")
        nullable = raw_schema.get("nullable", False)
        if type(nullable) is not bool:
            raise ContractSpecError(f"{label}.{field_name}.nullable must be boolean")
        field_format = raw_schema.get("format")
        if field_format is not None and (
            not isinstance(field_format, str)
            or not field_format
            or len(field_format.encode("utf-8")) > 128
        ):
            raise ContractSpecError(f"{label}.{field_name}.format is invalid")
        normalized[field_name] = {
            "type": field_type,
            "required": required,
            "nullable": nullable,
            "format": field_format,
        }
    return normalized


def _validate_spec(value: Any, label: str) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != _SPEC_KEYS:
        raise ContractSpecError(
            f"{label} must contain exactly schema_version and endpoints"
        )
    if value.get("schema_version") != "1.0":
        raise ContractSpecError(f"{label}.schema_version must be '1.0'")
    raw_endpoints = value.get("endpoints")
    if not isinstance(raw_endpoints, Mapping) or not raw_endpoints:
        raise ContractSpecError(f"{label}.endpoints must be a non-empty object")
    if len(raw_endpoints) > 10_000:
        raise ContractSpecError(f"{label}.endpoints exceeds the endpoint limit")
    endpoints: Dict[str, Dict[str, Any]] = {}
    for endpoint_key, raw_endpoint in raw_endpoints.items():
        endpoint_key = _validate_endpoint_key(
            endpoint_key, f"{label}.endpoints key"
        )
        if not isinstance(raw_endpoint, Mapping) or set(raw_endpoint) != _ENDPOINT_KEYS:
            raise ContractSpecError(
                f"{label}.endpoints[{endpoint_key}] must contain exactly "
                "request_fields and response_fields"
            )
        endpoints[endpoint_key] = {
            "request_fields": _validate_fields(
                raw_endpoint["request_fields"],
                f"{label}.endpoints[{endpoint_key}].request_fields",
            ),
            "response_fields": _validate_fields(
                raw_endpoint["response_fields"],
                f"{label}.endpoints[{endpoint_key}].response_fields",
            ),
        }
    return endpoints


class ApiContractDiffer:
    """Compare two exact, normalized API interface schemas."""

    def compare_specs(
        self,
        source_spec: Dict[str, Any],
        target_spec: Dict[str, Any],
    ) -> ContractDiffReport:
        started = time.perf_counter()
        source_endpoints = _validate_spec(source_spec, "source_spec")
        target_endpoints = _validate_spec(target_spec, "target_spec")

        if diff_specs_native is not None:
            try:
                native_rep = diff_specs_native(source_spec, target_spec)
                if native_rep and "changes" in native_rep:
                    items = [
                        ContractDiffItem(
                            endpoint=c["endpoint"],
                            category=c["category"],
                            severity=c["severity"],
                            description=c["description"],
                            field_name=c.get("field_name"),
                        )
                        for c in native_rep["changes"]
                    ]
                    return ContractDiffReport(
                        total_changes=native_rep["total_changes"],
                        breaking_changes_count=native_rep["breaking_changes_count"],
                        warnings_count=native_rep["warnings_count"],
                        non_breaking_count=native_rep["non_breaking_count"],
                        is_backward_compatible=native_rep["is_backward_compatible"],
                        duration_ms=round((time.perf_counter() - started) * 1000, 3),
                        changes=items,
                    )
            except Exception:
                pass

        changes: List[ContractDiffItem] = []

        for endpoint_key, source_endpoint in source_endpoints.items():
            target_endpoint = target_endpoints.get(endpoint_key)
            if target_endpoint is None:
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint_key,
                        category="ENDPOINT_REMOVED",
                        severity="BREAKING",
                        description=f"Endpoint '{endpoint_key}' was removed",
                    )
                )
                continue
            self._compare_field_direction(
                endpoint_key,
                source_endpoint["request_fields"],
                target_endpoint["request_fields"],
                channel="request",
                changes=changes,
            )
            self._compare_field_direction(
                endpoint_key,
                source_endpoint["response_fields"],
                target_endpoint["response_fields"],
                channel="response",
                changes=changes,
            )

        for endpoint_key in target_endpoints:
            if endpoint_key not in source_endpoints:
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint_key,
                        category="ENDPOINT_ADDED",
                        severity="NON_BREAKING",
                        description=f"Endpoint '{endpoint_key}' was added",
                    )
                )

        breaking_count = sum(item.severity == "BREAKING" for item in changes)
        warnings_count = sum(item.severity == "WARNING" for item in changes)
        non_breaking_count = sum(
            item.severity == "NON_BREAKING" for item in changes
        )
        return ContractDiffReport(
            total_changes=len(changes),
            breaking_changes_count=breaking_count,
            warnings_count=warnings_count,
            non_breaking_count=non_breaking_count,
            is_backward_compatible=breaking_count == 0,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            changes=changes,
        )

    @staticmethod
    def _compare_field_direction(
        endpoint: str,
        source_fields: Mapping[str, Mapping[str, Any]],
        target_fields: Mapping[str, Mapping[str, Any]],
        *,
        channel: str,
        changes: List[ContractDiffItem],
    ) -> None:
        for field_name, source_field in source_fields.items():
            target_field = target_fields.get(field_name)
            if target_field is None:
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint,
                        category="FIELD_REMOVED",
                        severity="BREAKING",
                        field_name=field_name,
                        description=(
                            f"{channel.title()} field '{field_name}' was removed"
                        ),
                    )
                )
                continue
            if source_field["type"] != target_field["type"]:
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint,
                        category="TYPE_CHANGED",
                        severity="BREAKING",
                        field_name=field_name,
                        description=(
                            f"{channel.title()} field '{field_name}' changed type "
                            f"from {source_field['type']} to {target_field['type']}"
                        ),
                    )
                )
            if source_field["format"] != target_field["format"]:
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint,
                        category="FORMAT_CHANGED",
                        severity="BREAKING",
                        field_name=field_name,
                        description=(
                            f"{channel.title()} field '{field_name}' changed format "
                            f"from {source_field['format']} to {target_field['format']}"
                        ),
                    )
                )
            if source_field["required"] != target_field["required"]:
                is_breaking = (
                    not source_field["required"] and target_field["required"]
                    if channel == "request"
                    else source_field["required"] and not target_field["required"]
                )
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint,
                        category="OPTIONALITY_CHANGED",
                        severity="BREAKING" if is_breaking else "NON_BREAKING",
                        field_name=field_name,
                        description=(
                            f"{channel.title()} field '{field_name}' required changed "
                            f"from {source_field['required']} to {target_field['required']}"
                        ),
                    )
                )
            if source_field["nullable"] != target_field["nullable"]:
                is_breaking = (
                    source_field["nullable"] and not target_field["nullable"]
                    if channel == "request"
                    else not source_field["nullable"] and target_field["nullable"]
                )
                changes.append(
                    ContractDiffItem(
                        endpoint=endpoint,
                        category="NULLABILITY_CHANGED",
                        severity="BREAKING" if is_breaking else "NON_BREAKING",
                        field_name=field_name,
                        description=(
                            f"{channel.title()} field '{field_name}' nullable changed "
                            f"from {source_field['nullable']} to {target_field['nullable']}"
                        ),
                    )
                )

        for field_name, target_field in target_fields.items():
            if field_name in source_fields:
                continue
            breaking = channel == "request" and target_field["required"]
            changes.append(
                ContractDiffItem(
                    endpoint=endpoint,
                    category="FIELD_ADDED",
                    severity="BREAKING" if breaking else "NON_BREAKING",
                    field_name=field_name,
                    description=f"{channel.title()} field '{field_name}' was added",
                )
            )


_contract_differ = ApiContractDiffer()


def run_api_contract_diff(
    source_spec: Optional[Dict[str, Any]] = None,
    target_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a strict diff; missing inputs never fall back to sample specs."""

    if source_spec is None or target_spec is None:
        return {
            "status": "NOT_RUN",
            "reason": "SOURCE_AND_TARGET_SPECS_REQUIRED",
            "is_backward_compatible": False,
            "breaking_changes_count": 0,
            "warnings_count": 0,
            "non_breaking_count": 0,
            "total_changes": 0,
            "duration_ms": 0.0,
            "changes": [],
        }
    try:
        report = _contract_differ.compare_specs(source_spec, target_spec)
    except ContractSpecError as exc:
        return {
            "status": "INVALID_SPEC",
            "reason": str(exc),
            "is_backward_compatible": False,
            "breaking_changes_count": 0,
            "warnings_count": 0,
            "non_breaking_count": 0,
            "total_changes": 0,
            "duration_ms": 0.0,
            "changes": [],
        }
    return {
        "status": (
            "COMPATIBLE"
            if report.is_backward_compatible
            else "BREAKING_CHANGES_DETECTED"
        ),
        "reason": None,
        "is_backward_compatible": report.is_backward_compatible,
        "breaking_changes_count": report.breaking_changes_count,
        "warnings_count": report.warnings_count,
        "non_breaking_count": report.non_breaking_count,
        "total_changes": report.total_changes,
        "duration_ms": report.duration_ms,
        "changes": [asdict(change) for change in report.changes],
    }
