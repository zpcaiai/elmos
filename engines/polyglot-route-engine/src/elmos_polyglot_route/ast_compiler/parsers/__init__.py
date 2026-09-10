"""Parser registry for 8 mainstream enterprise languages."""

from __future__ import annotations

from .base import BaseAstParser
from .python_parser import PythonAstParser
from .java_parser import JavaAstParser
from .csharp_parser import CSharpAstParser
from .typescript_parser import TypeScriptAstParser
from .go_parser import GoAstParser
from .rust_parser import RustAstParser
from .kotlin_parser import KotlinAstParser
from .php_parser import PhpAstParser

_PARSER_REGISTRY: dict[str, type[BaseAstParser]] = {
    'python': PythonAstParser,
    'java': JavaAstParser,
    'csharp': CSharpAstParser,
    'typescript': TypeScriptAstParser,
    'go': GoAstParser,
    'rust': RustAstParser,
    'kotlin': KotlinAstParser,
    'php': PhpAstParser,
}

def get_parser(language: str) -> BaseAstParser:
    lang = language.lower().strip()
    parser_cls = _PARSER_REGISTRY.get(lang)
    if not parser_cls:
        # Fallback to python parser for generic parsing
        return PythonAstParser()
    return parser_cls()

BaseParser = BaseAstParser
__all__ = ["BaseAstParser", "BaseParser", "get_parser"]
