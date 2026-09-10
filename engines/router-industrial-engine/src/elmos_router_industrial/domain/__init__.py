"""Domain contracts and error taxonomy for Elmos Router Industrial."""

from __future__ import annotations

from .contracts import (
    BudgetEnvelope,
    CandidateEvaluation,
    CapabilityLease,
    DataClassification,
    ExecutionLane,
    InferenceMessage,
    InferenceRequest,
    InferenceResponse,
    InferenceStreamChunk,
    ModelDescriptor,
    ModelExecutionPlan,
    ProviderDeployment,
    ProviderDescriptor,
    ReconciledUsage,
    RouteDecision,
    RouteRequest,
    ScoreBreakdown,
    TaskClass,
    UsageReport,
    VerifiedSecurityContext,
)
from .errors import (
    ErrorTaxonomyClass,
    ProviderError,
    map_http_status_to_taxonomy,
)

__all__ = [
    "BudgetEnvelope",
    "CandidateEvaluation",
    "CapabilityLease",
    "DataClassification",
    "ErrorTaxonomyClass",
    "ExecutionLane",
    "InferenceMessage",
    "InferenceRequest",
    "InferenceResponse",
    "InferenceStreamChunk",
    "ModelDescriptor",
    "ModelExecutionPlan",
    "ProviderDeployment",
    "ProviderDescriptor",
    "ProviderError",
    "ReconciledUsage",
    "RouteDecision",
    "RouteRequest",
    "ScoreBreakdown",
    "TaskClass",
    "UsageReport",
    "VerifiedSecurityContext",
    "map_http_status_to_taxonomy",
]
