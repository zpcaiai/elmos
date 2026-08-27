"""Stable adapter boundary for upstream API/version differences."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import InstructionEnvelope, ToolResult


@dataclass(frozen=True)
class AdapterAPIVersion:
    adapter_id: str
    api_version: str
    upstream_version: str


class AdapterBoundary:
    def __init__(self, version: AdapterAPIVersion, *, supported_capabilities: set[str], approval_modes: set[str]) -> None:
        self.version = version
        self._supported_capabilities = frozenset(supported_capabilities)
        self._approval_modes = frozenset(approval_modes)

    def validate_policy_mapping(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        requested = set(policy.get("allowed", ()))
        missing = sorted(requested - self._supported_capabilities)
        mode = policy.get("approval_mode", "default")
        if mode not in self._approval_modes:
            missing.append("approval_mode:" + str(mode))
        return {"valid": not missing, "missing": missing, "fail_closed": bool(missing)}

    def instruction(self, text: str, *, source: str, scope: str, provenance: Mapping[str, Any]) -> InstructionEnvelope:
        return InstructionEnvelope(text, source, scope, dict(provenance))

    def result(self, result: ToolResult) -> ToolResult:
        # TypedContent crosses the boundary unchanged.  Adapters may not turn it into a JSON string.
        return result
