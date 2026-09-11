"""Idiomatic TypeScript (NestJS / Promise) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class TypeScriptEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("typescript")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "number", "i16": "number", "i32": "number", "i64": "number",
                "u8": "number", "u16": "number", "u32": "number", "u64": "number",
                "f32": "number", "f64": "number", "bool": "boolean",
                "char": "string", "string": "string", "void": "void", "any": "any"
            }
            return m.get(t.name, "any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"{elem}[]"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"Record<{k}, {v}>"
        return t.name or "any"

