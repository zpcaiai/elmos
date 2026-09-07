"""Fail-closed local runtime for the repository-orchestrator Skill package.

The runtime performs deterministic local planning and validation only.  It does
not invoke models, shells, SCM, worktrees, networks, or external certification
services unless an explicitly trusted adapter is supplied by an authorized
caller.
"""

from .catalog import MODEL_ALIASES, SKILL_NAMES, SKILL_SPECS
from .contracts import HandlerResult, Status
from .dispatcher import RuntimeDispatcher
from .agentic import LangGraphRepairWorkflow, RepairTools
from .incremental import BoundedBatchExecutor, IncrementalManifest, VerifiedArtifactCache
from .integrations import DifyWorkflowClient, ElasticsearchProjection, TraceRecorder
from .memory import ExperienceMemoryStore, ExperienceRecord, MemoryTier
from .multiagent import GovernedMultiAgentCoordinator
from .retrieval import HybridIndex, RetrievalQuery, SearchDocument, SourceAnchor
from .semantic import SemanticSkillRouter, SkillDescriptor
from .runtime import dispatch

__all__ = [
    "HandlerResult",
    "HybridIndex",
    "RetrievalQuery",
    "SearchDocument",
    "SourceAnchor",
    "SemanticSkillRouter",
    "SkillDescriptor",
    "LangGraphRepairWorkflow",
    "RepairTools",
    "GovernedMultiAgentCoordinator",
    "IncrementalManifest",
    "VerifiedArtifactCache",
    "BoundedBatchExecutor",
    "ElasticsearchProjection",
    "DifyWorkflowClient",
    "TraceRecorder",
    "ExperienceMemoryStore",
    "ExperienceRecord",
    "MemoryTier",
    "MODEL_ALIASES",
    "RuntimeDispatcher",
    "dispatch",
    "SKILL_NAMES",
    "SKILL_SPECS",
    "Status",
]

__version__ = "0.2.0"
