"""Idiomatic Go (standard library / concurrency) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class GoEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("go")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int8", "i16": "int16", "i32": "int32", "i64": "int64",
                "u8": "uint8", "u16": "uint16", "u32": "uint32", "u64": "uint64",
                "f32": "float32", "f64": "float64", "bool": "bool",
                "char": "rune", "string": "string", "void": "", "any": "any"
            }
            return m.get(t.name, "any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"[]{elem}"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"map[{k}]{v}"
        return t.name or "any"

