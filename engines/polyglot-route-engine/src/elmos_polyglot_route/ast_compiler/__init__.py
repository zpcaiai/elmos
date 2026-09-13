"""Universal AST Compiler package for Polyglot Routes (M29)."""

from .compiler import UniversalAstCompiler, compile_polyglot_ast, default_compiler
from .emitters import BaseEmitter, get_emitter
from .ir import (
    UniversalAnnotation,
    UniversalClass,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalType,
)
from .lowering import SemanticLoweringEngine
from .parsers import BaseAstParser, BaseParser, get_parser
from .shims import ShimRegistry

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
    "BaseAstParser",
    "BaseParser",
    "SemanticLoweringEngine",
    "ShimRegistry",
    "get_emitter",
    "BaseEmitter",
]
