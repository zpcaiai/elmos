"""Idiomatic Flutter / Dart Widget Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType, UIComponentDecl
from .base import BaseEmitter


class FlutterEmitter(BaseEmitter):
    """Emits Flutter StatelessWidget and StatefulWidget Dart source files."""

    def __init__(self) -> None:
        super().__init__("flutter")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int", "i16": "int", "i32": "int", "i64": "int",
                "u8": "int", "u16": "int", "u32": "int", "u64": "int",
                "f32": "double", "f64": "double", "bool": "bool",
                "char": "String", "string": "String", "void": "void", "any": "dynamic"
            }
            res = m.get(t.name, "dynamic")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            res = f"List<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            res = f"Map<{k}, {v}>"
        else:
            res = t.name or "dynamic"
        if t.is_nullable and not res.endswith("?"):
            res = f"{res}?"
        return res

