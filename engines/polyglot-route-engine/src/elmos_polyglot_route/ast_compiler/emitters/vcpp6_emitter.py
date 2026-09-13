"""Visual C++ 6.0 (MFC) Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class Vcpp6Emitter(BaseEmitter):
    """Emits Visual C++ 6.0 MFC compatible C++98 header/source code."""

    def __init__(self) -> None:
        super().__init__("vcpp6")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "char", "i16": "short", "i32": "int", "i64": "DWORD",
                "u8": "BYTE", "u16": "WORD", "u32": "DWORD", "u64": "DWORD",
                "f32": "float", "f64": "double", "bool": "BOOL",
                "char": "TCHAR", "string": "CString", "void": "void", "any": "void*"
            }
            return m.get(t.name, "void*")
        return t.name or "void*"

