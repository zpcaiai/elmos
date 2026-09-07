"""ELMOS Repository Autonomy Kernel — executable implementation of the 31 capabilities.

The package is layered deliberately:

``errors`` / ``contracts`` / ``ports`` / ``registry``
    The foundation.  Pure, dependency-free, and imported by everything else.
``<capability>`` modules
    One module per declared capability.  Each owns its own failure codes,
    dataclasses and invariants, and binds a handler into the registry.
``adapters``
    The only code allowed to touch time, disk, a database or a subprocess.

Importing this package binds every capability handler, so
``registry.unbound_skills()`` is empty in a complete build.  A partial build is
detectable rather than silently degraded.
"""

from __future__ import annotations

from .contracts import Observability, SkillResult, Status, canonical_json, digest
from .errors import Category, KernelError
from .registry import DESCRIPTORS, bound_skills, dispatch, unbound_skills

__version__ = "2.0.0"

__all__ = [
    "Category",
    "_bind_all_capabilities",
    "DESCRIPTORS",
    "KernelError",
    "Observability",
    "SkillResult",
    "Status",
    "__version__",
    "bound_skills",
    "canonical_json",
    "digest",
    "dispatch",
    "unbound_skills",
]


def _bind_all_capabilities() -> tuple[str, ...]:
    """Import every capability module so the registry is complete.

    The capability modules are imported lazily rather than at package import so
    that a tool needing only ``contracts`` does not pay for the whole kernel.
    The trade-off is that ``registry.bound_skills()`` is empty until this runs,
    so anything that reports on completeness — the CLI, the conformance test —
    calls it first, and it returns what is still unbound rather than assuming
    success.
    """

    import importlib

    for module in _CAPABILITY_MODULES:
        importlib.import_module(f"{__name__}.{module}")
    return unbound_skills()


_CAPABILITY_MODULES: tuple[str, ...] = (
    "taskspec", "orchestrator", "authority", "tools", "policy", "sandbox", "leasing",
    "evidence", "census", "semindex", "semir", "changegraph", "validation", "vmesh",
    "releasegate", "compat", "contextplan", "toolloader", "continuity", "worktree",
    "router", "cache", "costeta", "security", "timetravel", "packreg", "demo2skill",
    "curator", "arena", "elo", "gym",
)
