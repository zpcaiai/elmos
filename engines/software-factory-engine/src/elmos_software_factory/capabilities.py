"""Strict loader for the machine-readable 102-Skill capability registry."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from .canonical import canonical_digest


CapabilityMode = Literal["local", "requires_adapter"]
_SKILL = re.compile(r"^elmos-[a-z0-9][a-z0-9-]{0,186}$")
_ACTION = re.compile(r"^[a-z][a-z0-9-]{0,127}$")
_INPUT = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


class CapabilityRegistryError(ValueError):
    """Raised when the checked-in capability registry drifts or is malformed."""


@dataclass(frozen=True)
class CapabilityContract:
    skill_name: str
    action: str
    mode: CapabilityMode
    required_inputs: tuple[str, ...]


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CapabilityRegistryError(f"capability registry contains duplicate key {key!r}")
        result[key] = value
    return result


def _load(path: str | Path | None = None) -> tuple[Mapping[str, CapabilityContract], str]:
    source = Path(path) if path is not None else Path(__file__).with_name("capability_registry.json")
    try:
        document = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapabilityRegistryError(f"cannot load capability registry {source}: {exc}") from exc
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "capabilities"}:
        raise CapabilityRegistryError("capability registry root fields do not match schema 1.0")
    if document.get("schema_version") != "1.0":
        raise CapabilityRegistryError("unsupported capability registry schema version")
    values = document.get("capabilities")
    if not isinstance(values, list) or len(values) != 102:
        raise CapabilityRegistryError("capability registry must contain exactly 102 entries")
    contracts: dict[str, CapabilityContract] = {}
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {
            "skill_name", "action", "mode", "required_inputs"
        }:
            raise CapabilityRegistryError(f"capabilities[{index}] fields do not match schema 1.0")
        skill_name = value.get("skill_name")
        action = value.get("action")
        mode = value.get("mode")
        required = value.get("required_inputs")
        if not isinstance(skill_name, str) or not _SKILL.fullmatch(skill_name):
            raise CapabilityRegistryError(f"capabilities[{index}].skill_name is invalid")
        if skill_name in contracts:
            raise CapabilityRegistryError(f"duplicate capability Skill {skill_name}")
        if not isinstance(action, str) or not _ACTION.fullmatch(action):
            raise CapabilityRegistryError(f"capabilities[{index}].action is invalid")
        if mode not in {"local", "requires_adapter"}:
            raise CapabilityRegistryError(f"capabilities[{index}].mode is invalid")
        if not isinstance(required, list):
            raise CapabilityRegistryError(f"capabilities[{index}].required_inputs must be an array")
        parsed_required: list[str] = []
        for field_index, field in enumerate(required):
            if not isinstance(field, str) or not _INPUT.fullmatch(field):
                raise CapabilityRegistryError(
                    f"capabilities[{index}].required_inputs[{field_index}] is invalid"
                )
            parsed_required.append(field)
        if len(parsed_required) != len(set(parsed_required)):
            raise CapabilityRegistryError(f"capabilities[{index}].required_inputs contains duplicates")
        contracts[skill_name] = CapabilityContract(
            skill_name=skill_name,
            action=action,
            mode=cast(CapabilityMode, mode),
            required_inputs=tuple(parsed_required),
        )
    return MappingProxyType(contracts), canonical_digest(document)


CAPABILITY_CONTRACTS, CAPABILITY_REGISTRY_DIGEST = _load()


def capability_contract(skill_name: str) -> CapabilityContract | None:
    return CAPABILITY_CONTRACTS.get(skill_name)


def load_capability_registry(
    path: str | Path | None = None,
) -> tuple[Mapping[str, CapabilityContract], str]:
    """Load and validate an alternate registry for drift and negative tests."""

    return _load(path)
