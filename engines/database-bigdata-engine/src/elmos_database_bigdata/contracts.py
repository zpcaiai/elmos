"""Strict request and result contracts for bounded planning only."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .canonical import canonical_digest, canonical_value

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
REQUEST_SCHEMA = "elmos.database-bigdata.request.v1"
RESULT_SCHEMA = "elmos.database-bigdata.result.v1"
EXTERNAL_CAPABILITIES = (
    "database",
    "provider",
    "network",
    "filesystem_write",
    "subprocess",
    "deployment",
    "benchmark",
    "chaos",
    "repair",
    "cutover",
    "certification",
)
PATH_FIELD_SUFFIXES = ("_path", "_paths", "_directory", "_directories")
PATH_FIELD_NAMES = frozenset({"path", "paths", "directory", "directories"})


class ContractError(ValueError):
    """Raised before any handler runs when the request is not exact and safe."""


def require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise ContractError(f"{field} must match {IDENTIFIER.pattern}")
    if len(value.encode("utf-8")) > 128:
        raise ContractError(f"{field} exceeds 128 UTF-8 bytes")
    return value


def require_relative_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ContractError(f"{field} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ContractError(
            f"{field} must be a normalized confined relative POSIX path"
        )
    return value


def _validate_paths(value: Any, trail: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            next_trail = (*trail, key)
            if key in PATH_FIELD_NAMES or key.endswith(PATH_FIELD_SUFFIXES):
                if isinstance(child, str):
                    require_relative_path(child, ".".join(next_trail))
                elif isinstance(child, list):
                    for index, item in enumerate(child):
                        require_relative_path(item, f"{'.'.join(next_trail)}[{index}]")
                else:
                    raise ContractError(
                        f"{'.'.join(next_trail)} must be a path or path list"
                    )
            _validate_paths(child, next_trail)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_paths(child, (*trail, str(index)))


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    schema_version: str
    skill: str
    operation: str
    request_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    idempotency_key: str
    inputs: Mapping[str, Any]
    external_capabilities: Mapping[str, bool]

    @classmethod
    def parse(cls, document: Mapping[str, Any]) -> RuntimeRequest:
        if not isinstance(document, Mapping):
            raise ContractError("request must be an object")
        allowed = {
            "schema_version",
            "skill",
            "operation",
            "request_id",
            "tenant_id",
            "project_id",
            "actor_id",
            "idempotency_key",
            "inputs",
            "external_capabilities",
        }
        actual_keys = list(document)
        if not all(isinstance(key, str) for key in actual_keys):
            raise ContractError("request field names must be strings")
        actual = set(actual_keys)
        extra = sorted(actual - allowed)
        missing = sorted(allowed - actual)
        if missing or extra:
            raise ContractError(
                f"request fields are not exact: missing={missing} extra={extra}"
            )
        if document.get("schema_version") != REQUEST_SCHEMA:
            raise ContractError(f"schema_version must be {REQUEST_SCHEMA}")
        if document.get("operation") != "plan":
            raise ContractError(
                "operation must be plan; runtime side effects are disabled"
            )
        inputs = document.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ContractError("inputs must be an object")
        copied_inputs = canonical_value(dict(inputs), label="inputs")
        _validate_paths(copied_inputs)
        requested = document.get("external_capabilities")
        if not isinstance(requested, Mapping) or set(requested) != set(
            EXTERNAL_CAPABILITIES
        ):
            raise ContractError(
                "external_capabilities must contain the exact deny-list keys"
            )
        if any(not isinstance(requested[name], bool) for name in EXTERNAL_CAPABILITIES):
            raise ContractError("external capability values must be booleans")
        enabled = sorted(name for name in EXTERNAL_CAPABILITIES if requested[name])
        if enabled:
            raise ContractError(f"external capabilities are disabled: {enabled}")
        return cls(
            schema_version=REQUEST_SCHEMA,
            skill=require_identifier(document.get("skill"), "skill"),
            operation="plan",
            request_id=require_identifier(document.get("request_id"), "request_id"),
            tenant_id=require_identifier(document.get("tenant_id"), "tenant_id"),
            project_id=require_identifier(document.get("project_id"), "project_id"),
            actor_id=require_identifier(document.get("actor_id"), "actor_id"),
            idempotency_key=require_identifier(
                document.get("idempotency_key"), "idempotency_key"
            ),
            inputs=copied_inputs,
            external_capabilities={name: False for name in EXTERNAL_CAPABILITIES},
        )

    def binding_digest(self) -> str:
        return canonical_digest(
            {
                "skill": self.skill,
                "operation": self.operation,
                "request_id": self.request_id,
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "actor_id": self.actor_id,
                "idempotency_key": self.idempotency_key,
                "inputs": self.inputs,
            }
        )


def denied_external_capabilities() -> dict[str, bool]:
    return {name: False for name in EXTERNAL_CAPABILITIES}


__all__ = [
    "EXTERNAL_CAPABILITIES",
    "REQUEST_SCHEMA",
    "RESULT_SCHEMA",
    "ContractError",
    "RuntimeRequest",
    "denied_external_capabilities",
]
