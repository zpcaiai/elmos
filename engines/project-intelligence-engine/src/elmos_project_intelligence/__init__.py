"""Bounded local Project Intelligence runtime."""

from .architecture_drift_detector import (
    ArchitecturalLayer,
    ArchitectureDriftDetector,
    ArchitectureDriftReport,
    ArchitectureViolation,
)
from .artifacts import ArtifactStoreError, ContentAddressedArtifactStore
from .dataflow_taint_engine import (
    DataflowTaintEngine,
    TaintSink,
    TaintSource,
    TaintVulnerability,
)
from .deep_callgraph import (
    CallEdge,
    CallGraphSummary,
    DeepCallGraphBuilder,
    FunctionNode,
)
from .domain import CapabilityOutcome
from .runtime import (
    SKILL_REGISTRY,
    SkillRuntimeError,
    capability_manifest,
    dispatch_skill,
    validate_skill_registry,
)
from .service import ProjectIntelligenceService
from .threat_model_engine import (
    ThreatFinding,
    ThreatModelEngine,
    ThreatModelReport,
    TrustBoundary,
)

__all__ = [
    "ArchitecturalLayer",
    "ArchitectureDriftDetector",
    "ArchitectureDriftReport",
    "ArchitectureViolation",
    "ArtifactStoreError",
    "CallEdge",
    "CallGraphSummary",
    "CapabilityOutcome",
    "ContentAddressedArtifactStore",
    "DataflowTaintEngine",
    "DeepCallGraphBuilder",
    "FunctionNode",
    "ProjectIntelligenceService",
    "SKILL_REGISTRY",
    "SkillRuntimeError",
    "TaintSink",
    "TaintSource",
    "TaintVulnerability",
    "ThreatFinding",
    "ThreatModelEngine",
    "ThreatModelReport",
    "TrustBoundary",
    "capability_manifest",
    "dispatch_skill",
    "validate_skill_registry",
]
