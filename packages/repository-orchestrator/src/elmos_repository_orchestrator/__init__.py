"""Fail-closed local runtime for the repository-orchestrator Skill package.

The runtime performs deterministic local planning and validation only.  It does
not invoke models, shells, SCM, worktrees, networks, or external certification
services unless an explicitly trusted adapter is supplied by an authorized
caller.
"""

from .catalog import MODEL_ALIASES, SKILL_NAMES, SKILL_SPECS
from .contracts import HandlerResult, Status
from .dispatcher import RuntimeDispatcher
from .runtime import dispatch

__all__ = [
    "HandlerResult",
    "MODEL_ALIASES",
    "RuntimeDispatcher",
    "dispatch",
    "SKILL_NAMES",
    "SKILL_SPECS",
    "Status",
]

__version__ = "0.1.0"
