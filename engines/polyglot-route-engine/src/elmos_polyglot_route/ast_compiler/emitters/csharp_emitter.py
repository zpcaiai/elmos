"""Idiomatic C# 12 / .NET 8 (ASP.NET Core / Task) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class CSharpEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("csharp")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "sbyte", "i16": "short", "i32": "int", "i64": "long",
                "u8": "byte", "u16": "ushort", "u32": "uint", "u64": "ulong",
                "f32": "float", "f64": "double", "bool": "bool",
                "char": "char", "string": "string", "void": "void", "any": "object"
            }
            return m.get(t.name, "object")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"System.Collections.Generic.List<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"System.Collections.Generic.Dictionary<{k}, {v}>"
        return t.name or "object"

