"""ELMOS Java legacy-web modernization runtime."""

from .contracts import ArtifactEnvelope, CapabilityResult, RuntimeRequest
from .runtime import CATALOG, SKILL_REGISTRY, capability_manifest, dispatch, validate_skill_registry
from .service import ModernizationService

__all__ = [
    "ArtifactEnvelope",
    "CapabilityResult",
    "RuntimeRequest",
    "ModernizationService",
    "CATALOG",
    "SKILL_REGISTRY",
    "capability_manifest",
    "dispatch",
    "validate_skill_registry",
]
