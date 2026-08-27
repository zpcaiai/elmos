"""Repository-owned runtime for the ELMOS Formal Assurance Kernel."""

from .canonical import canonical_json, digest_bytes, digest_value
from .artifact_store import ContentAddressedArtifactStore
from .contracts import (
    AssuranceLevel,
    Criticality,
    ProofResult,
    ProofStatus,
    ProofRunState,
    Scope,
    TrustedIdentity,
)
from .gate import evaluate_release_gate, validate_result
from .registry import SkillRegistry
from .runtime import FormalAssuranceRuntime

__version__ = "0.1.0"

__all__ = [
    "AssuranceLevel",
    "ContentAddressedArtifactStore",
    "Criticality",
    "FormalAssuranceRuntime",
    "ProofResult",
    "ProofRunState",
    "ProofStatus",
    "Scope",
    "SkillRegistry",
    "TrustedIdentity",
    "canonical_json",
    "digest_bytes",
    "digest_value",
    "evaluate_release_gate",
    "validate_result",
]
