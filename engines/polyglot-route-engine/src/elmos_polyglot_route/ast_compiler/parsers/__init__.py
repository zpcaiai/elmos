"""Parser registry for all 15 enterprise and system languages (210 routes)."""

from __future__ import annotations

from collections.abc import Callable

from .base import BaseAstParser
from .cpp_parser import CppAstParser
from .csharp_parser import CSharpAstParser
from .flutter_parser import FlutterAstParser
from .go_parser import GoAstParser
from .java_parser import JavaAstParser
from .kotlin_parser import KotlinAstParser
from .objc_parser import ObjCAstParser
from .php_parser import PhpAstParser
from .python_parser import PythonAstParser
from .react_parser import ReactAstParser
from .rust_parser import RustAstParser
from .swift_parser import SwiftAstParser
from .typescript_parser import TypeScriptAstParser
from .vb6_parser import Vb6AstParser
from .vcpp6_parser import Vcpp6AstParser

_PARSER_REGISTRY: dict[str, Callable[[], BaseAstParser]] = {
    "python": PythonAstParser,
    "py": PythonAstParser,
    "java": JavaAstParser,
    "csharp": CSharpAstParser,
    "cs": CSharpAstParser,
    "typescript": TypeScriptAstParser,
    "ts": TypeScriptAstParser,
    "go": GoAstParser,
    "golang": GoAstParser,
    "rust": RustAstParser,
    "rs": RustAstParser,
    "kotlin": KotlinAstParser,
    "kt": KotlinAstParser,
    "php": PhpAstParser,
    "cpp": CppAstParser,
    "c++": CppAstParser,
    "cc": CppAstParser,
    "swift": SwiftAstParser,
    "objc": ObjCAstParser,
    "objective-c": ObjCAstParser,
    "objectivec": ObjCAstParser,
    "react": ReactAstParser,
    "flutter": FlutterAstParser,
    "dart": FlutterAstParser,
    "vb6": Vb6AstParser,
    "vcpp6": Vcpp6AstParser,
}


def get_parser(language: str) -> BaseAstParser:
    lang = language.lower().strip()
    parser_cls = _PARSER_REGISTRY.get(lang)
    if not parser_cls:
        # Fallback to python parser for generic parsing
        return PythonAstParser()
    return parser_cls()


BaseParser = BaseAstParser
__all__ = [
    "BaseAstParser",
    "BaseParser",
    "get_parser",
    "PythonAstParser",
    "JavaAstParser",
    "CSharpAstParser",
    "TypeScriptAstParser",
    "GoAstParser",
    "RustAstParser",
    "KotlinAstParser",
    "PhpAstParser",
    "CppAstParser",
    "SwiftAstParser",
    "ObjCAstParser",
    "ReactAstParser",
    "FlutterAstParser",
    "Vb6AstParser",
    "Vcpp6AstParser",
]
