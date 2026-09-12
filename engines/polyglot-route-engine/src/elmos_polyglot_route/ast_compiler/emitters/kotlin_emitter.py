"""Idiomatic Kotlin (Spring Boot 3 / Coroutines) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class KotlinEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("kotlin")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "Byte", "i16": "Short", "i32": "Int", "i64": "Long",
                "u8": "UByte", "u16": "UShort", "u32": "UInt", "u64": "ULong",
                "f32": "Float", "f64": "Double", "bool": "Boolean",
                "char": "Char", "string": "String", "void": "Unit", "any": "Any"
            }
            return m.get(t.name, "Any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"List<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"Map<{k}, {v}>"
        return t.name or "Any"

