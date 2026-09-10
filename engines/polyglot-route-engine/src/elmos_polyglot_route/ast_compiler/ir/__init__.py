"""Universal AST & Semantic Intermediate Representation (Universal IR) Package.

Exports base Universal AST constructs along with formal Type Lattice,
Control Flow Graph (CFG), Data Flow Graph (DFG / SSA), and Ownership/Lifetime models.
"""

from __future__ import annotations

# Re-export base Universal AST models
from .base import (
    AssignStmt,
    AwaitExpr,
    AwaitStmt,
    BinaryExpr,
    BinaryOperator,
    BreakStmt,
    CastExpr,
    CatchClause,
    ConstructExpr,
    ContinueStmt,
    ExprStmt,
    FieldAccessExpr,
    ForEachStmt,
    ForLoopStmt,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    LockStmt,
    MethodCallExpr,
    PrimitiveKind,
    RawSnippetExpr,
    RawSnippetStmt,
    ReturnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UIComponentDecl,
    UIEventBinding,
    UIStateVar,
    UIViewNode,
    UnaryExpr,
    UnaryOperator,
    UniversalAnnotation,
    UniversalClass,
    UniversalConstructor,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
    WhileStmt,
)

# Export Type Lattice & Algebraic Type System
from .types import (
    ExtendedTypeKind,
    FunctionSignature,
    GenericParam,
    TypeLattice,
    Variance,
)

# Export Control Flow Graph & Dominator Analysis
from .cfg import (
    BasicBlock,
    CfgBuilder,
    CfgEdge,
    CfgEdgeKind,
    ControlFlowGraph,
)

# Export Data Flow Graph & Liveness Analysis
from .dfg import (
    DataFlowGraph,
    Definition,
    LivenessInfo,
    PhiNode,
    Use,
)

# Export Ownership & Lifetime Model
from .ownership import (
    BorrowState,
    LifetimeRegion,
    OwnershipAnalyzer,
    OwnershipKind,
    OwnershipViolation,
)

__all__ = [
    # Base AST
    "AssignStmt",
    "AwaitExpr",
    "AwaitStmt",
    "BinaryExpr",
    "BinaryOperator",
    "BreakStmt",
    "CastExpr",
    "CatchClause",
    "ConstructExpr",
    "ContinueStmt",
    "ExprStmt",
    "FieldAccessExpr",
    "ForEachStmt",
    "ForLoopStmt",
    "IdentifierExpr",
    "IfElseStmt",
    "LiteralExpr",
    "LockStmt",
    "MethodCallExpr",
    "PrimitiveKind",
    "RawSnippetExpr",
    "RawSnippetStmt",
    "ReturnStmt",
    "ThrowStmt",
    "TryCatchFinallyStmt",
    "UIComponentDecl",
    "UIEventBinding",
    "UIStateVar",
    "UIViewNode",
    "UnaryExpr",
    "UnaryOperator",
    "UniversalAnnotation",
    "UniversalClass",
    "UniversalConstructor",
    "UniversalExpr",
    "UniversalField",
    "UniversalMethod",
    "UniversalModule",
    "UniversalParam",
    "UniversalStmt",
    "UniversalType",
    "VarDeclStmt",
    "WhileStmt",
    # Types
    "ExtendedTypeKind",
    "FunctionSignature",
    "GenericParam",
    "TypeLattice",
    "Variance",
    # CFG
    "BasicBlock",
    "CfgBuilder",
    "CfgEdge",
    "CfgEdgeKind",
    "ControlFlowGraph",
    # DFG
    "DataFlowGraph",
    "Definition",
    "LivenessInfo",
    "PhiNode",
    "Use",
    # Ownership
    "BorrowState",
    "LifetimeRegion",
    "OwnershipAnalyzer",
    "OwnershipKind",
    "OwnershipViolation",
]
