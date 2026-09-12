"""Idiomatic Swift 5.10 / 6.0 Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class SwiftEmitter(BaseEmitter):
    """Emits modern idiomatic Swift structs, classes, and async/await methods."""

    def __init__(self) -> None:
        super().__init__("swift")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "Int8", "i16": "Int16", "i32": "Int32", "i64": "Int64",
                "u8": "UInt8", "u16": "UInt16", "u32": "UInt32", "u64": "UInt64",
                "f32": "Float", "f64": "Double", "bool": "Bool",
                "char": "Character", "string": "String", "void": "Void", "any": "Any"
            }
            res = m.get(t.name, "Any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            res = f"[{elem}]"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            res = f"[{k}: {v}]"
        elif t.kind == "optional":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            res = f"{elem}?"
        else:
            res = t.name or "Any"
        if t.is_nullable and not res.endswith("?"):
            res = f"{res}?"
        return res

