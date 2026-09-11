"""Idiomatic Rust (Tokio / Serde) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class RustEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("rust")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "i8", "i16": "i16", "i32": "i32", "i64": "i64",
                "u8": "u8", "u16": "u16", "u32": "u32", "u64": "u64",
                "f32": "f32", "f64": "f64", "bool": "bool",
                "char": "char", "string": "String", "void": "()", "any": "serde_json::Value"
            }
            return m.get(t.name, "String")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"Vec<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"std::collections::HashMap<{k}, {v}>"
        return t.name or "String"

