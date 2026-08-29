"""ELMOS Polyglot Repository Semantic Compiler Engine v3.0.0."""

from .models import (
    BatchType,
    TechnologySurface,
    RouteCell,
    RouteCertificationPlan,
    SemanticObligation,
    ProofObligation,
    BehaviorOracle,
    Counterexample,
    CertificationRun,
    VerdictStatus,
    ObligationStatus,
    SemanticRisk,
)
from .service import PolyglotSemanticCompilerService
from .tree_sitter_incremental import (
    AstSpan,
    IncrementalAstNode,
    IncrementalAstTree,
    TreeSitterIncrementalParser,
    parse_incremental_cst,
)

__version__ = "3.0.0"
__all__ = [
    "BatchType",
    "TechnologySurface",
    "RouteCell",
    "RouteCertificationPlan",
    "SemanticObligation",
    "ProofObligation",
    "BehaviorOracle",
    "Counterexample",
    "CertificationRun",
    "VerdictStatus",
    "ObligationStatus",
    "SemanticRisk",
    "PolyglotSemanticCompilerService",
    "AstSpan",
    "IncrementalAstNode",
    "IncrementalAstTree",
    "TreeSitterIncrementalParser",
    "parse_incremental_cst",
]

