"""Legacy read-only catalog models.

Execution, authority, evidence and handler-request contracts are deliberately
not re-exported from this compatibility module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KernelType(str, Enum):
    K1_SKILL_RUNTIME = "K1-skill-runtime"
    K2_REPOSITORY_INTELLIGENCE = "K2-repository-intelligence"
    K3_TRANSFORMATION = "K3-transformation"
    K4_BUILD_EXECUTION = "K4-build-execution"
    K5_VERIFICATION = "K5-verification"
    K6_SECURITY_GOVERNANCE = "K6-security-governance"
    K7_DATABASE_DATA = "K7-database-data"
    K8_OBSERVABILITY_EVOLUTION = "K8-observability-evolution"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Untrusted planning context; never converted into a trusted Scope."""

    tenant_id: str
    repository_id: str
    objective: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    id: str
    name: str
    kernel: KernelType
    priority: Priority
    objective: str
    path: str


__all__ = [
    "KernelType",
    "Priority",
    "SkillDefinition",
    "TaskContext",
]
