"""Dynamic dispatcher for FDE autonomous delivery capability package.

Binds the 45 allowlisted atomic skills to their corresponding Python handlers,
enforcing effect class validation, non-self-certification boundaries (max E3),
and fail-closed behavior on unknown skills or prohibited production operations.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any, Final

from .registry import (
    ALIAS_PREFIX,
    SKILL_BINDINGS,
    SkillBinding,
)

PROHIBITED_PAYLOAD_FLAGS: Final = frozenset(
    {
        "production_write",
        "production_mutation",
        "apply_production_mutation",
    }
)


class FdeSkillDispatcher:
    """Allowlisted, fail-closed dispatcher for all 45 FDE delivery skills."""

    _HANDLER_CACHE: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {}

    @classmethod
    def resolve_binding(cls, skill_name: str) -> SkillBinding:
        """Resolve a skill name or alias to its SkillBinding, or fail closed."""
        if skill_name in SKILL_BINDINGS:
            return SKILL_BINDINGS[skill_name]
        if skill_name.startswith(ALIAS_PREFIX):
            unprefixed = skill_name[len(ALIAS_PREFIX) :]
            if unprefixed in SKILL_BINDINGS:
                return SKILL_BINDINGS[unprefixed]
        raise KeyError(f"UNKNOWN_OR_UNAUTHORIZED_FDE_SKILL: {skill_name}")

    @classmethod
    def get_handler(cls, binding: SkillBinding) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
        """Resolve and cache the handler callable for a binding."""
        key = f"{binding.module}:{binding.handler}"
        if key not in cls._HANDLER_CACHE:
            mod = importlib.import_module(binding.module)
            fn = getattr(mod, binding.handler)
            cls._HANDLER_CACHE[key] = fn
        return cls._HANDLER_CACHE[key]

    @classmethod
    def dispatch(
        cls, skill_name: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Dispatch a skill execution with strict boundary and policy checks."""
        binding = cls.resolve_binding(skill_name)
        active_payload = dict(payload) if payload is not None else {}

        # Fail-closed checks for prohibited production actions
        for flag in PROHIBITED_PAYLOAD_FLAGS:
            if active_payload.get(flag):
                raise PermissionError(
                    f"Production mutation prohibited in capability package handlers: {flag}=True"
                )

        if active_payload.get("target_environment") == "production":
            raise PermissionError(
                "Direct production target environment is prohibited in local handlers"
            )

        # Enforce non-self-certification boundaries
        if active_payload.get("claim_certification_level") in ("E4", "E5"):
            raise PermissionError(
                "Capability package handlers cannot certify E4/E5; external certification required"
            )

        handler = cls.get_handler(binding)
        result = handler(active_payload)

        # Ensure result adheres to standalone boundaries
        result_dict = dict(result)
        result_dict.setdefault("effect_class", binding.effect_class.value)
        result_dict.setdefault("standalone_boundary", "E3")
        result_dict.setdefault("source_id", binding.source_id)
        result_dict.setdefault("alias", binding.alias)

        return result_dict


def dispatch_fde_skill(
    skill_name: str, payload: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Convenience functional interface for FdeSkillDispatcher.dispatch."""
    return FdeSkillDispatcher.dispatch(skill_name, payload)
