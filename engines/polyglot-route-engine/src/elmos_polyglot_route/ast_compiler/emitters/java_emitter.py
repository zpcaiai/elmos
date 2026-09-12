"""Idiomatic Java (Spring Boot 3 / CompletableFuture) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class JavaEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("java")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "byte", "i16": "short", "i32": "int", "i64": "long",
                "u8": "int", "u16": "int", "u32": "long", "u64": "long",
                "f32": "float", "f64": "double", "bool": "boolean",
                "char": "char", "string": "String", "void": "void", "any": "Object"
            }
            return m.get(t.name, "Object")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"java.util.List<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"java.util.Map<{k}, {v}>"
        return t.name or "Object"

