"""Exact fail-closed native semantic routes for brokered Foundry Skills.

The source package does not provide executable adapters. This module binds each
repository-owned native semantic program to one digest-bound host route. The
repository controls workflow, inputs, outputs, tools, gates and result
validation; provider effects still require an injected broker, durable store,
exact permit and trusted permit/result verifiers.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .adapters import (
    AdapterBinding,
    AdapterRegistry,
    EffectClass,
    ExternalAdapterRoute,
)
from .canonical import canonical_digest
from .native_semantics import native_program_for


EXTERNAL_BINDING_VERSION = "1.0.0"
EXTERNAL_INTEGRATION_STATUS = "NATIVE_IMPLEMENTED_HOST_RUNTIME_REQUIRED"


class ExternalBindingCatalog(Protocol):
    atomic_skills: Mapping[str, Mapping[str, Any]]


def _plain_digest(value: Mapping[str, Any]) -> str:
    return canonical_digest(value).removeprefix("sha256:")


def _binding_document(name: str, record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the complete immutable contract that identifies one route."""

    return {
        "schema_version": "elmos.foundry.external-skill-binding.v1",
        "skill_name": name,
        "skill_version": record["version"],
        "skill_source_sha256": record["source_sha256"],
        "pack": record["pack"],
        "risk_class": record["risk_class"],
        "inputs": list(record["inputs"]),
        "outputs": list(record["outputs"]),
        "allowed_tools": list(record["allowed_tools"]),
        "required_gates": list(record["required_gates"]),
        "workflow": list(record["workflow"]),
        "dependencies": list(record["dependencies"]),
        "invariants": list(record["invariants"]),
        "effect_class": EffectClass.PRIVILEGED_EXTERNAL.value,
        "operation": f"foundry.skill.{name}.execute",
        "semantic_handler_binding": f"native.{name}",
        "integration_status": EXTERNAL_INTEGRATION_STATUS,
    }


def exact_external_binding(
    name: str,
    record: Mapping[str, Any],
) -> tuple[AdapterBinding, ExternalAdapterRoute]:
    """Compile one catalog row into a unique adapter and broker route."""

    program = native_program_for(name, record)
    document = dict(_binding_document(name, record))
    document["semantic_program_digest"] = "sha256:" + program.digest
    binding_digest = _plain_digest(document)
    route_document = {
        "schema_version": "elmos.foundry.external-skill-route.v1",
        "binding_digest": binding_digest,
        "skill_name": name,
        "operation": document["operation"],
        "semantic_handler_binding": program.handler_id,
        "semantic_program_digest": "sha256:" + program.digest,
    }
    binding = AdapterBinding(
        adapter_id=f"external.{name}",
        version=EXTERNAL_BINDING_VERSION,
        digest=binding_digest,
        exact_skills=(name,),
        # Conservative by construction. The host may deny or isolate the
        # route, but repository content cannot downgrade its authority class.
        effect_class=EffectClass.PRIVILEGED_EXTERNAL,
        metadata=MappingProxyType(
            {
                "integration_status": EXTERNAL_INTEGRATION_STATUS,
                "pack": str(record["pack"]),
                "risk_class": str(record["risk_class"]),
                "skill_source_sha256": str(record["source_sha256"]),
                "semantic_handler_binding": program.handler_id,
                "semantic_program_digest": "sha256:" + program.digest,
            }
        ),
    )
    route = ExternalAdapterRoute(
        route_id=f"route.{name}",
        version=EXTERNAL_BINDING_VERSION,
        digest=_plain_digest(route_document),
        operation=str(document["operation"]),
        semantic_program=program,
    )
    return binding, route


def register_external_bindings(
    registry: AdapterRegistry,
    catalog: ExternalBindingCatalog,
    *,
    local_skills: frozenset[str],
) -> AdapterRegistry:
    """Register every non-local Skill exactly once, with no fallback route."""

    names = set(catalog.atomic_skills)
    unknown_local = sorted(local_skills - names)
    if unknown_local:
        raise ValueError(f"local Skill registry is outside the catalog: {unknown_local}")
    for name in sorted(names - local_skills):
        binding, route = exact_external_binding(name, catalog.atomic_skills[name])
        registry.register(binding, route)
    return registry


__all__ = [
    "EXTERNAL_BINDING_VERSION",
    "EXTERNAL_INTEGRATION_STATUS",
    "ExternalBindingCatalog",
    "exact_external_binding",
    "register_external_bindings",
]
