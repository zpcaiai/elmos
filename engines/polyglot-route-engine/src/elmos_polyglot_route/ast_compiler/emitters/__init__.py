"""Emitter registry and factory for all 8 supported languages."""

from __future__ import annotations

from typing import Dict, Type
from .base import BaseEmitter
from .java_emitter import JavaEmitter
from .csharp_emitter import CSharpEmitter
from .python_emitter import PythonEmitter
from .typescript_emitter import TypeScriptEmitter
from .go_emitter import GoEmitter
from .rust_emitter import RustEmitter
from .kotlin_emitter import KotlinEmitter
from .php_emitter import PhpEmitter

EMITTER_REGISTRY: Dict[str, Type[BaseEmitter]] = {
    "java": JavaEmitter,
    "csharp": CSharpEmitter,
    "cs": CSharpEmitter,
    "python": PythonEmitter,
    "py": PythonEmitter,
    "typescript": TypeScriptEmitter,
    "ts": TypeScriptEmitter,
    "go": GoEmitter,
    "golang": GoEmitter,
    "rust": RustEmitter,
    "rs": RustEmitter,
    "kotlin": KotlinEmitter,
    "kt": KotlinEmitter,
    "php": PhpEmitter,
}


def get_emitter(lang: str) -> BaseEmitter:
    normalized = lang.lower().strip()
    cls = EMITTER_REGISTRY.get(normalized)
    if not cls:
        raise ValueError(f"No emitter registered for language: {lang}")
    return cls()

__all__ = [
    "BaseEmitter",
    "JavaEmitter",
    "CSharpEmitter",
    "PythonEmitter",
    "TypeScriptEmitter",
    "GoEmitter",
    "RustEmitter",
    "KotlinEmitter",
    "PhpEmitter",
    "get_emitter",
    "EMITTER_REGISTRY",
]
