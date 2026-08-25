"""Strict loader for the machine-readable 50-method public interface registry."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from .canonical import canonical_digest


ExecutionMode = Literal["local", "requires_adapter"]
_METHOD = re.compile(r"^[A-Za-z][A-Za-z0-9.]{1,191}$")
_ACTION = re.compile(r"^[a-z][a-z0-9-]{0,127}$")
_ERROR = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_INPUT = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_PACKAGE_IDS = {f"P{number:02d}" for number in range(8)}
PLATFORM_ERRORS = (
    "REQUEST_INVALID",
    "METHOD_NOT_FOUND",
    "POLICY_DENIED",
    "APPROVAL_REQUIRED",
    "REQUIRED_INPUT_MISSING",
    "REQUIRED_INPUT_INVALID",
    "DEPENDENCY_BLOCKED",
    "DEPENDENCY_SCOPE_MISMATCH",
    "DEPENDENCY_IDENTITY_MISMATCH",
    "DEPENDENCY_NOT_EXECUTED",
    "EVIDENCE_SCOPE_MISMATCH",
    "IDEMPOTENCY_KEY_REQUIRED",
    "ADAPTER_REQUIRED",
    "PAYLOAD_INVALID",
    "CAPABILITY_UNSUPPORTED",
)


class PublicMethodRegistryError(ValueError):
    """Raised when the checked-in public-method registry is invalid."""


@dataclass(frozen=True)
class PublicMethodBinding:
    method: str
    package_id: str
    action: str
    execution_mode: ExecutionMode
    required_inputs: tuple[str, ...]
    domain_errors: tuple[str, ...]
    platform_errors: tuple[str, ...]


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicMethodRegistryError(f"public-method registry contains duplicate key {key!r}")
        result[key] = value
    return result


def _load(path: str | Path | None = None) -> tuple[Mapping[str, PublicMethodBinding], str]:
    source = Path(path) if path is not None else Path(__file__).with_name("public_method_registry.json")
    try:
        document = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicMethodRegistryError(f"cannot load public-method registry {source}: {exc}") from exc
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "methods"}:
        raise PublicMethodRegistryError("public-method registry root fields do not match schema 1.0")
    if document.get("schema_version") != "1.0":
        raise PublicMethodRegistryError("unsupported public-method registry schema version")
    values = document.get("methods")
    if not isinstance(values, list) or len(values) != 50:
        raise PublicMethodRegistryError("public-method registry must contain exactly 50 entries")
    bindings: dict[str, PublicMethodBinding] = {}
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {
            "method", "package_id", "action", "execution_mode", "required_inputs",
            "domain_errors", "platform_errors",
        }:
            raise PublicMethodRegistryError(f"methods[{index}] fields do not match schema 1.0")
        method = value.get("method")
        package_id = value.get("package_id")
        action = value.get("action")
        mode = value.get("execution_mode")
        required_inputs = value.get("required_inputs")
        domain_errors = value.get("domain_errors")
        platform_errors = value.get("platform_errors")
        if not isinstance(method, str) or not _METHOD.fullmatch(method):
            raise PublicMethodRegistryError(f"methods[{index}].method is invalid")
        if method in bindings:
            raise PublicMethodRegistryError(f"duplicate public method {method}")
        if package_id not in _PACKAGE_IDS:
            raise PublicMethodRegistryError(f"methods[{index}].package_id is invalid")
        if not isinstance(action, str) or not _ACTION.fullmatch(action):
            raise PublicMethodRegistryError(f"methods[{index}].action is invalid")
        if mode not in {"local", "requires_adapter"}:
            raise PublicMethodRegistryError(f"methods[{index}].execution_mode is invalid")
        if not isinstance(required_inputs, list) or not required_inputs:
            raise PublicMethodRegistryError(f"methods[{index}].required_inputs must be non-empty")
        parsed_inputs: list[str] = []
        for input_index, field in enumerate(required_inputs):
            if not isinstance(field, str) or not _INPUT.fullmatch(field):
                raise PublicMethodRegistryError(
                    f"methods[{index}].required_inputs[{input_index}] is invalid"
                )
            parsed_inputs.append(field)
        if len(parsed_inputs) != len(set(parsed_inputs)):
            raise PublicMethodRegistryError(f"methods[{index}].required_inputs contains duplicates")
        parsed_error_sets: dict[str, tuple[str, ...]] = {}
        for field, errors in (
            ("domain_errors", domain_errors),
            ("platform_errors", platform_errors),
        ):
            if not isinstance(errors, list) or not errors:
                raise PublicMethodRegistryError(f"methods[{index}].{field} must be non-empty")
            parsed: list[str] = []
            for error_index, error in enumerate(errors):
                if not isinstance(error, str) or not _ERROR.fullmatch(error):
                    raise PublicMethodRegistryError(
                        f"methods[{index}].{field}[{error_index}] is invalid"
                    )
                parsed.append(error)
            if len(parsed) != len(set(parsed)):
                raise PublicMethodRegistryError(f"methods[{index}].{field} contains duplicates")
            parsed_error_sets[field] = tuple(parsed)
        expected_platform_errors = tuple(
            error
            for error in PLATFORM_ERRORS
            if error not in set(parsed_error_sets["domain_errors"])
        )
        if parsed_error_sets["platform_errors"] != expected_platform_errors:
            raise PublicMethodRegistryError(
                f"methods[{index}].platform_errors does not match the runtime envelope"
            )
        bindings[method] = PublicMethodBinding(
            method=method,
            package_id=cast(str, package_id),
            action=action,
            execution_mode=cast(ExecutionMode, mode),
            required_inputs=tuple(parsed_inputs),
            domain_errors=parsed_error_sets["domain_errors"],
            platform_errors=parsed_error_sets["platform_errors"],
        )
    if {binding.package_id for binding in bindings.values()} != _PACKAGE_IDS:
        raise PublicMethodRegistryError("public-method registry must cover exactly P00 through P07")
    return MappingProxyType(bindings), canonical_digest(document)


PUBLIC_METHODS, PUBLIC_METHOD_REGISTRY_DIGEST = _load()


def public_method(name: str) -> PublicMethodBinding | None:
    return PUBLIC_METHODS.get(name)


def load_public_method_registry(
    path: str | Path | None = None,
) -> tuple[Mapping[str, PublicMethodBinding], str]:
    """Load and validate an alternate registry for drift and negative tests."""

    return _load(path)
