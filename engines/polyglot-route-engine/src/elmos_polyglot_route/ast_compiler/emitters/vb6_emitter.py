"""Visual Basic 6.0 Module and Form Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class Vb6Emitter(BaseEmitter):
    """Emits classic Visual Basic 6.0 .bas or .cls source files."""

    def __init__(self) -> None:
        super().__init__("vb6")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "Byte", "i16": "Integer", "i32": "Long", "i64": "Long",
                "u8": "Byte", "u16": "Integer", "u32": "Long", "u64": "Long",
                "f32": "Single", "f64": "Double", "bool": "Boolean",
                "char": "String", "string": "String", "void": "Void", "any": "Variant"
            }
            return m.get(t.name, "Variant")
        return t.name or "Variant"

