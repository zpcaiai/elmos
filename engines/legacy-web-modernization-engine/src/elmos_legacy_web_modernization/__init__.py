"""ELMOS Java legacy-web modernization runtime."""

from .contracts import ArtifactEnvelope, CapabilityResult, RuntimeRequest
from .external_evidence import ExternalEvidenceError, evaluate_external_intake, not_run_external_status
from .runtime import CATALOG, SKILL_REGISTRY, capability_manifest, dispatch, validate_skill_registry
from .service import ModernizationService

__all__ = [
    "ArtifactEnvelope",
    "CapabilityResult",
    "RuntimeRequest",
    "ExternalEvidenceError",
    "evaluate_external_intake",
    "not_run_external_status",
    "ModernizationService",
    "CATALOG",
    "SKILL_REGISTRY",
    "capability_manifest",
    "dispatch",
    "validate_skill_registry",
]
