"""Idiomatic Modern C++20 Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class CppEmitter(BaseEmitter):
    """Emits production-grade modern C++20 header/source code."""

    def __init__(self) -> None:
        super().__init__("cpp")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "int64_t",
                "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "uint64_t",
                "f32": "float", "f64": "double", "bool": "bool",
                "char": "char", "string": "std::string", "void": "void", "any": "std::any"
            }
            return m.get(t.name, "void")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"std::vector<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"std::unordered_map<{k}, {v}>"
        elif t.kind == "pointer":
            elem = self.format_type(t.element_type or UniversalType.custom("void"))
            if t.pointer_kind == "unique":
                return f"std::unique_ptr<{elem}>"
            return f"std::shared_ptr<{elem}>"
        elif t.kind == "optional":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"std::optional<{elem}>"
        return t.name or "void"

