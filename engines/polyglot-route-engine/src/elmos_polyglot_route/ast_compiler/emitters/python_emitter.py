"""Idiomatic Python 3.12 (FastAPI / dataclass / asyncio) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class PythonEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("python")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int", "i16": "int", "i32": "int", "i64": "int",
                "u8": "int", "u16": "int", "u32": "int", "u64": "int",
                "f32": "float", "f64": "float", "bool": "bool",
                "char": "str", "string": "str", "void": "None", "any": "Any"
            }
            return m.get(t.name, "Any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"list[{elem}]"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"dict[{k}, {v}]"
        return t.name or "Any"

