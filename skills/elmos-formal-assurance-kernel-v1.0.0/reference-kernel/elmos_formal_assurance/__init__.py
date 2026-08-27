"""Executable reference kernel for elmos-formal-assurance-kernel-v1.0.0."""
from .models import ProofStatus, AssuranceLevel, Criticality, ProofRunState
from .gate import evaluate_release_gate, validate_result
from .cache import proof_cache_key

__version__ = "1.0.0"
__all__ = [
    "ProofStatus", "AssuranceLevel", "Criticality", "ProofRunState",
    "evaluate_release_gate", "validate_result", "proof_cache_key"
]
