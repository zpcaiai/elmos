"""Allowlisted dispatch for all 1,244 exact native-program handlers."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from ..domain import TenantScope
from ..native_semantics import load_native_programs
from .compiler import ExactSkillError, HandlerFunc, compile_exact_handler
from .tool_runtime import EXPECTED_TOOL_IDS, load_tool_runtime

EXPECTED_EXACT_SKILLS = 1244


@lru_cache(maxsize=1)
def load_exact_handlers() -> Mapping[str, HandlerFunc]:
    """Compile every native program into a unique allowlisted callable."""

    programs = load_native_programs()
    if len(programs) != EXPECTED_EXACT_SKILLS:
        raise ExactSkillError(
            f"native program inventory is {len(programs)}, expected {EXPECTED_EXACT_SKILLS}"
        )
    catalog_tools = {
        str(tool)
        for program in programs.values()
        for stage in program.stages
        for tool in stage.get("tools", ())
    }
    if catalog_tools != set(EXPECTED_TOOL_IDS):
        missing = sorted(catalog_tools - set(EXPECTED_TOOL_IDS))
        extra = sorted(set(EXPECTED_TOOL_IDS) - catalog_tools)
        raise ExactSkillError(
            f"tool allowlist drifted from native programs; missing={missing[:12]} extra={extra[:12]}"
        )
    runtime = load_tool_runtime()
    if set(runtime) != catalog_tools:
        raise ExactSkillError("compiled tool runtime does not cover the catalog")

    handlers: dict[str, HandlerFunc] = {}
    identities: set[tuple[str, str, str, str]] = set()
    for name, program in programs.items():
        handler = compile_exact_handler(program)
        identity = (
            handler.__module__,
            handler.__qualname__,
            str(getattr(handler, "handler_id")),
            str(getattr(handler, "program_digest")),
        )
        if identity in identities:
            raise ExactSkillError(f"duplicate exact handler identity for {name}")
        identities.add(identity)
        handlers[name] = handler
    if len(handlers) != EXPECTED_EXACT_SKILLS or len(identities) != EXPECTED_EXACT_SKILLS:
        raise ExactSkillError("exact handler identities are not unique or incomplete")
    return MappingProxyType(handlers)


def get_exact_handler(skill_name: str) -> HandlerFunc:
    handler = load_exact_handlers().get(skill_name)
    if handler is None:
        raise ExactSkillError(f"no exact allowlisted handler for {skill_name}")
    return handler


def get_exact_handler_or_none(skill_name: str) -> HandlerFunc | None:
    return load_exact_handlers().get(skill_name)


def run_exact_skill(
    skill_name: str,
    payload: Mapping[str, Any] | None,
    tenant_scope: TenantScope | None = None,
    invocation_id: str = "",
    *,
    request_binding_digest: str | None = None,
) -> dict[str, Any]:
    programs = load_native_programs()
    program = programs.get(skill_name)
    if program is None:
        raise ExactSkillError(f"no exact native program for {skill_name}")
    handler = get_exact_handler(skill_name)
    return handler(
        skill_name,
        payload or {},
        tenant_scope,
        invocation_id,
        request_binding_digest=request_binding_digest,
    )


__all__ = [
    "EXPECTED_EXACT_SKILLS",
    "get_exact_handler",
    "get_exact_handler_or_none",
    "load_exact_handlers",
    "run_exact_skill",
]
