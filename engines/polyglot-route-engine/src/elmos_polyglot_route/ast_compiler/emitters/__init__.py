"""Emitter registry and factory for all 15 supported enterprise and system languages (210 routes)."""

from __future__ import annotations

from collections.abc import Callable

from .base import BaseEmitter
from .cpp_emitter import CppEmitter
from .csharp_emitter import CSharpEmitter
from .flutter_emitter import FlutterEmitter
from .go_emitter import GoEmitter
from .java_emitter import JavaEmitter
from .kotlin_emitter import KotlinEmitter
from .objc_emitter import ObjCEmitter
from .php_emitter import PhpEmitter
from .python_emitter import PythonEmitter
from .react_emitter import ReactEmitter
from .rust_emitter import RustEmitter
from .swift_emitter import SwiftEmitter
from .typescript_emitter import TypeScriptEmitter
from .vb6_emitter import Vb6Emitter
from .vcpp6_emitter import Vcpp6Emitter

EMITTER_REGISTRY: dict[str, Callable[[], BaseEmitter]] = {
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
    "cpp": CppEmitter,
    "c++": CppEmitter,
    "cc": CppEmitter,
    "swift": SwiftEmitter,
    "objc": ObjCEmitter,
    "objective-c": ObjCEmitter,
    "objectivec": ObjCEmitter,
    "react": ReactEmitter,
    "flutter": FlutterEmitter,
    "dart": FlutterEmitter,
    "vb6": Vb6Emitter,
    "vcpp6": Vcpp6Emitter,
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
    "CppEmitter",
    "SwiftEmitter",
    "ObjCEmitter",
    "ReactEmitter",
    "FlutterEmitter",
    "Vb6Emitter",
    "Vcpp6Emitter",
    "get_emitter",
    "EMITTER_REGISTRY",
]
