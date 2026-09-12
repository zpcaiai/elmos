"""Object graph lifecycle & memory management lowering across 8 languages."""

from __future__ import annotations

from typing import Any
from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalType


class LifecycleLowering:
    """Adjusts memory, ownership, and resource cleanup models for target language."""

    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = target_language.lower().strip()
        for c in module.classes:
            cls.lower_class(c, target)
        return module

    @classmethod
    def lower_class(cls, c: UniversalClass, target_language: str) -> None:
        if target_language == 'rust':
            # In Rust, structs need derive traits and memory layout
            c.is_struct = True
            for f in c.fields:
                # Value types are owned in Rust
                if f.type_info.name == 'string':
                    f.type_info.name = 'String'
        elif target_language in ('java', 'csharp', 'kotlin'):
            # In JVM/.NET, objects are reference types, value types are primitives
            for f in c.fields:
                if f.type_info.name == 'String':
                    f.type_info.name = 'String' if target_language != 'csharp' else 'string'
        elif target_language == 'go':
            c.is_struct = True
            for f in c.fields:
                # Go exported fields must be capitalized
                if f.name and f.name[0].islower():
                    f.name = f.name[0].upper() + f.name[1:]
