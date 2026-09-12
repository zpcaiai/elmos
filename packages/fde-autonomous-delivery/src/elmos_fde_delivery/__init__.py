"""FDE Autonomous Delivery and Repository Refactoring Engine.

Provides allowlisted skill dispatch, topological orchestration, and strict
fail-closed execution boundaries for all 45 atomic skills and 6 packs.
"""

from __future__ import annotations

from .dispatcher import FdeSkillDispatcher, dispatch_fde_skill
from .orchestrator import FdeDeliveryOrchestrator
from .registry import (
    ARCHIVE_SHA256,
    PACKAGE_NAME,
    PACKAGE_VERSION,
    SKILL_BINDINGS,
    TOPOLOGICAL_ORDER,
    WORKFLOW_SKILLS,
    EffectClass,
    SkillBinding,
    describe_registry,
    topological_order,
)

__all__ = [
    "ARCHIVE_SHA256",
    "EffectClass",
    "FdeDeliveryOrchestrator",
    "FdeSkillDispatcher",
    "PACKAGE_NAME",
    "PACKAGE_VERSION",
    "SKILL_BINDINGS",
    "SkillBinding",
    "TOPOLOGICAL_ORDER",
    "WORKFLOW_SKILLS",
    "describe_registry",
    "dispatch_fde_skill",
    "topological_order",
]
