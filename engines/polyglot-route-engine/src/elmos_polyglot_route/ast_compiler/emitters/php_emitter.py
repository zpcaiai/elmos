"""Idiomatic PHP (Laravel Controller) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class PhpEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("php")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int", "i16": "int", "i32": "int", "i64": "int",
                "u8": "int", "u16": "int", "u32": "int", "u64": "int",
                "f32": "float", "f64": "float", "bool": "bool",
                "char": "string", "string": "string", "void": "void", "any": "mixed"
            }
            return m.get(t.name, "mixed")
        elif t.kind == "list" or t.kind == "map":
            return "array"
        return t.name or "mixed"

