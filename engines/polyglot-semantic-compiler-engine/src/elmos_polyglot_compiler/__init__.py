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
from .regression_bisector import (
    BisectResult,
    BisectStep,
    SemanticRegressionBisector,
    run_semantic_bisect,
)
from .api_contract_diff import (
    ApiContractDiffer,
    ContractDiffItem,
    ContractDiffReport,
    run_api_contract_diff,
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
    "BisectResult",
    "BisectStep",
    "SemanticRegressionBisector",
    "run_semantic_bisect",
    "ApiContractDiffer",
    "ContractDiffItem",
    "ContractDiffReport",
    "run_api_contract_diff",
]



