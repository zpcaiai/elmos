"""Composition root for exact local and host-owned Foundry adapters."""

from __future__ import annotations

from .adapters import (
    AdapterRegistry,
    ExternalExecutionBroker,
    PermitVerifier,
)
from .external_bindings import register_external_bindings
from .local_semantics import CatalogView, LOCAL_SEMANTIC_SKILLS, LocalSemanticRuntime
from .store import FoundryStore


def build_default_adapter_registry(
    catalog: CatalogView,
    *,
    store: FoundryStore | None = None,
    permit_verifier: PermitVerifier | None = None,
    external_broker: ExternalExecutionBroker | None = None,
) -> AdapterRegistry:
    """Bind all exact identities while leaving external execution fail closed."""

    registry = AdapterRegistry(
        permit_verifier=permit_verifier,
        external_broker=external_broker,
    )
    LocalSemanticRuntime(catalog, store=store).register(registry)
    register_external_bindings(
        registry,
        catalog,
        local_skills=LOCAL_SEMANTIC_SKILLS,
    )
    if len(registry.describe()) != len(catalog.atomic_skills):
        raise RuntimeError("default adapter registry does not cover every exact Skill")
    return registry




def build_automated_adapter_registry(
    catalog: CatalogView,
    *,
    store: FoundryStore | None = None,
    permit_verifier: PermitVerifier | None = None,
    external_broker: ExternalExecutionBroker | None = None,
) -> AdapterRegistry:
    """Bind all exact identities with active automated broker and permit verifier."""
    from .automated_handlers.automated_broker import (
        create_automated_execution_broker,
        create_automated_permit_verifier,
    )

    broker = external_broker or create_automated_execution_broker()
    verifier = permit_verifier or create_automated_permit_verifier()
    return build_default_adapter_registry(
        catalog,
        store=store,
        permit_verifier=verifier,
        external_broker=broker,
    )

__all__ = ["build_default_adapter_registry", "build_automated_adapter_registry"]
