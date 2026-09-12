from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto

MAX_METHODS = 100

class TargetLanguageStrategy(Enum):
    ABC_MIXIN = auto()
    ABSTRACT_CLASS_MIXIN = auto()
    DEFAULT_INTERFACE_METHODS = auto()
    EMBEDDED_STRUCT = auto()

@dataclass(frozen=True)
class InterfaceResolution:
    strategy: TargetLanguageStrategy
    target_language: str

class DefaultMethodResolver:
    def resolve(self, interface_name: str, default_methods: list[str], target_language: str) -> InterfaceResolution:
        if len(default_methods) > MAX_METHODS:
            raise ValueError(f"Too many default methods. Max allowed is {MAX_METHODS}")
            
        target_lang_lower = target_language.lower().strip()
        
        if target_lang_lower == "python":
            return InterfaceResolution(strategy=TargetLanguageStrategy.ABC_MIXIN, target_language="python")
        elif target_lang_lower == "typescript":
            return InterfaceResolution(strategy=TargetLanguageStrategy.ABSTRACT_CLASS_MIXIN, target_language="typescript")
        elif target_lang_lower == "c#":
            return InterfaceResolution(strategy=TargetLanguageStrategy.DEFAULT_INTERFACE_METHODS, target_language="c#")
        elif target_lang_lower == "go":
            return InterfaceResolution(strategy=TargetLanguageStrategy.EMBEDDED_STRUCT, target_language="go")
        else:
            raise ValueError(f"Unsupported target language: {target_language}")
