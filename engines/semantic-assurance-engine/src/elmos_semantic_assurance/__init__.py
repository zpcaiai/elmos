"""Elmos Semantic Assurance Engine v1.0.0.

Provides top-tier commercial production-grade capabilities across 9 capability batches:
- Batch J: Frontend & Syntax Semantics (Skills 169-184)
- Batch K: Type & Contract Semantics (Skills 185-198)
- Batch L: Control Flow & Data Flow Semantics (Skills 199-214)
- Batch M: Runtime, Memory & Concurrency Semantics (Skills 215-232)
- Batch N: Observable Behavior & Oracle Semantics (Skills 233-248)
- Batch O: Certification Corpora & Test Assets (Skills 249-262)
- Batch P: Native Runtime Labs & Toolchains (Skills 263-274)
- Batch Q: Formal Assurance & Translation Validation (Skills 275-288)
- Batch R: Semantic Stress & Differential Fuzzing (Skills 289-300)
"""

from .models import (
    BatchType,
    SemanticRisk,
    ObligationStatus,
    VerdictStatus,
    SemanticObligation,
    ProofObligation,
    BehaviorOracle,
    Counterexample,
    DifferentialResult,
    CertificationRun,
)
from .service import SemanticAssuranceService

__version__ = "1.0.0"

__all__ = [
    "BatchType",
    "SemanticRisk",
    "ObligationStatus",
    "VerdictStatus",
    "SemanticObligation",
    "ProofObligation",
    "BehaviorOracle",
    "Counterexample",
    "DifferentialResult",
    "CertificationRun",
    "SemanticAssuranceService",
]
