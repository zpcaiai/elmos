"""Stable importer binding for hosts that load this package as a Skill runtime.

The host imports exactly two names — :func:`dispatch` and :func:`handler_names`
— and passes its own authority through ``trusted_context``.  Everything else in
the package is an implementation detail that may change between versions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .catalog import PACKAGE_NAME, PACKAGE_VERSION, SKILL_NAMES, SKILL_SPECS
from .dispatcher import (
    PENDING_SKILLS,
    build_trusted_context,
    dispatch,
    handler_names,
    implemented_skills,
)

RUNTIME_MODULE = "elmos_repository_refactoring.runtime"
RUNTIME_CALLABLE = "dispatch"


def describe() -> dict[str, Any]:
    """A machine-readable description of what this runtime can actually do."""

    return {
        "package": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "runtimeModule": RUNTIME_MODULE,
        "runtimeCallable": RUNTIME_CALLABLE,
        "skills": [
            {
                "name": name,
                "handler": SKILL_SPECS[name].handler,
                "riskClass": SKILL_SPECS[name].risk_class.value,
                "canonicalOwner": SKILL_SPECS[name].canonical_owner,
                "dependsOn": list(SKILL_SPECS[name].depends_on),
                "mutating": SKILL_SPECS[name].mutating,
                "minimumAdapterLevel": SKILL_SPECS[name].minimum_adapter_level.value,
                "outputs": list(SKILL_SPECS[name].outputs),
                "implemented": name not in PENDING_SKILLS,
            }
            for name in SKILL_NAMES
        ],
        "implementedCount": len(implemented_skills()),
        "totalCount": len(SKILL_NAMES),
    }


def skill_catalog_payload() -> dict[str, Any]:
    """The ``config/skill-catalog.json`` content, generated from the code.

    Generating it means the registry file can never drift from the catalog it
    claims to describe; the test-suite asserts the file matches this output.
    """

    return {
        "schema_version": "elmos.repository-refactoring.skill-catalog.v1",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "runtime_module": RUNTIME_MODULE,
        "runtime_callable": RUNTIME_CALLABLE,
        "skills": [
            {
                "name": name,
                "handler": SKILL_SPECS[name].handler,
                "canonical_owner": SKILL_SPECS[name].canonical_owner,
                "risk_class": SKILL_SPECS[name].risk_class.value,
                "mutating": SKILL_SPECS[name].mutating,
                "minimum_adapter_level": SKILL_SPECS[name].minimum_adapter_level.value,
                "depends_on": list(SKILL_SPECS[name].depends_on),
                "implemented": name not in PENDING_SKILLS,
            }
            for name in SKILL_NAMES
        ],
    }


def run(
    skill_name: str,
    payload: Mapping[str, Any] | None = None,
    *,
    trusted_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Alias for :func:`dispatch` with a name that reads better at call sites."""

    return dispatch(skill_name, payload, trusted_context=trusted_context)


__all__ = [
    "PENDING_SKILLS",
    "RUNTIME_CALLABLE",
    "RUNTIME_MODULE",
    "build_trusted_context",
    "describe",
    "dispatch",
    "handler_names",
    "implemented_skills",
    "run",
    "skill_catalog_payload",
]
