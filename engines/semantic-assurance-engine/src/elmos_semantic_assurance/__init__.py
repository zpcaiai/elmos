"""Digest-bound semantic assurance for Batches J-R (ELMOS-POLY-169..300)."""

from .adapters import AdapterReceipt, AdapterSet, ExecutionAdapter
from .contracts import (
    AssuranceScope,
    CapabilityState,
    EvidenceStatus,
    ExecutionStatus,
    Operation,
    SkillRequest,
    TrustedIdentity,
)
from .registry import SkillBinding, SkillRegistry
from .runtime import AuthorizationError, SemanticAssuranceRuntime
from .service import SemanticAssuranceService, get_assurance_status
from .store import IdempotencyConflict, SemanticAssuranceStore, StoreError

__version__ = "1.0.0"

__all__ = [
    "AdapterReceipt",
    "AdapterSet",
    "AssuranceScope",
    "AuthorizationError",
    "CapabilityState",
    "EvidenceStatus",
    "ExecutionAdapter",
    "ExecutionStatus",
    "IdempotencyConflict",
    "Operation",
    "SemanticAssuranceRuntime",
    "SemanticAssuranceService",
    "SemanticAssuranceStore",
    "SkillBinding",
    "SkillRegistry",
    "SkillRequest",
    "StoreError",
    "TrustedIdentity",
    "get_assurance_status",
]
