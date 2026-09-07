"""Skill handler registry — maps every skill name to its domain-specific handler.

This module builds the complete mapping of all 296 AI Capability Enhancement
skills to their respective domain handler functions.  Each handler implements
the full lifecycle declared in the skill's implementation.yaml:
  REQUESTED → PROFILED → PLANNED → RUNNING → VERIFYING → EVIDENCE_SEALED → COMPLETED

Handlers are grouped into 15 functional domains, each implemented in a
dedicated sub-module under handlers/.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .runtime import SkillExecutionResult

SkillHandler = Callable[[Mapping[str, Any]], SkillExecutionResult]


def build_handler_registry() -> dict[str, SkillHandler]:
    """Build and return the complete handler registry for all 296 skills."""
    from .handlers import (
        agent_identity,
        agent_orchestration,
        ai_assurance,
        ai_compilation,
        ai_governance,
        ai_project_generation,
        data_platform,
        formal_verification,
        infra_deployment,
        mcp_protocol,
        model_serving,
        observability_ops,
        rag_retrieval,
        security_supply_chain,
        testing_quality,
    )

    registry: dict[str, SkillHandler] = {}

    # Register all domain modules
    for module in [
        agent_identity,
        agent_orchestration,
        ai_assurance,
        ai_compilation,
        ai_governance,
        ai_project_generation,
        data_platform,
        formal_verification,
        infra_deployment,
        mcp_protocol,
        model_serving,
        observability_ops,
        rag_retrieval,
        security_supply_chain,
        testing_quality,
    ]:
        handlers = module.get_handlers()
        for name, handler in handlers.items():
            if name in registry:
                raise ValueError(f"duplicate handler for skill {name}")
            registry[name] = handler

    return registry
