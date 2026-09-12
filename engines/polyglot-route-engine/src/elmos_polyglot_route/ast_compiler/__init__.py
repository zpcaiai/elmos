"""Universal AST Compiler package for Polyglot Routes (M29)."""

from .ir import (
    UniversalType,
    UniversalAnnotation,
    UniversalParam,
    UniversalField,
    UniversalMethod,
    UniversalClass,
    UniversalModule,
)
from .compiler import UniversalAstCompiler, compile_polyglot_ast, default_compiler
from .parsers import get_parser, BaseAstParser, BaseParser
from .lowering import SemanticLoweringEngine
from .shims import ShimRegistry
from .emitters import get_emitter, BaseEmitter

__all__ = [
    "UniversalType",
    "UniversalAnnotation",
    "UniversalParam",
    "UniversalField",
    "UniversalMethod",
    "UniversalClass",
    "UniversalModule",
    "UniversalAstCompiler",
    "compile_polyglot_ast",
    "default_compiler",
    "get_parser",
    "BaseAstParser, BaseParser",
    "SemanticLoweringEngine",
    "ShimRegistry",
    "get_emitter",
    "BaseEmitter",
]
