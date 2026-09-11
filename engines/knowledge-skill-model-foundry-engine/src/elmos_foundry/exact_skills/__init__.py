"""Exact allowlisted handlers for every HOST_ROUTE_BOUND Foundry skill.

Each of the 1,244 native semantic programs compiles to a unique callable.
Dispatch is allowlist-only: unknown skills, cross-skill invocation, and
undeclared tools fail closed.  Local traces are self-attested engineering
evidence only; external and independent evidence remain NOT_RUN.
"""

from .compiler import ExactSkillError, compile_exact_handler, execute_exact_program
from .registry import (
    EXPECTED_EXACT_SKILLS,
    get_exact_handler,
    get_exact_handler_or_none,
    load_exact_handlers,
    run_exact_skill,
)
from .tool_runtime import EXPECTED_TOOL_IDS, load_tool_runtime

__all__ = [
    "EXPECTED_EXACT_SKILLS",
    "EXPECTED_TOOL_IDS",
    "ExactSkillError",
    "compile_exact_handler",
    "execute_exact_program",
    "get_exact_handler",
    "get_exact_handler_or_none",
    "load_exact_handlers",
    "load_tool_runtime",
    "run_exact_skill",
]
