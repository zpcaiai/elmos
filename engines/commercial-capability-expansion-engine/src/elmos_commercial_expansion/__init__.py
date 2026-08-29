"""Elmos Commercial Capability Expansion Engine v2.0.0.

Provides top-tier commercial production-grade capabilities across 8 kernels:
- K1: Skill Runtime
- K2: Repository Intelligence
- K3: Transformation
- K4: Build & Execution
- K5: Verification
- K6: Security & Governance
- K7: Database & Data
- K8: Observability & Evolution
"""

from .models import (
    KernelType,
    Priority,
    GateLevel,
    DecisionStatus,
    RiskLevel,
    TaskContext,
    SkillDefinition,
    PolicyDecision,
    RiskAssessment,
    EvidenceRecord,
    ProvenanceAttestation,
    E0E5GateDecision,
    Checkpoint,
    TrajectoryRecord,
)
from .service import CommercialCapabilityExpansionService

__version__ = "2.0.0"

__all__ = [
    "KernelType",
    "Priority",
    "GateLevel",
    "DecisionStatus",
    "RiskLevel",
    "TaskContext",
    "SkillDefinition",
    "PolicyDecision",
    "RiskAssessment",
    "EvidenceRecord",
    "ProvenanceAttestation",
    "E0E5GateDecision",
    "Checkpoint",
    "TrajectoryRecord",
    "CommercialCapabilityExpansionService",
]
