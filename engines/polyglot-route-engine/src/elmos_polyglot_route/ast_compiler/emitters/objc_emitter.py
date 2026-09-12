"""Idiomatic Objective-C ARC Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class ObjCEmitter(BaseEmitter):
    """Emits modern Objective-C header and implementation with ARC semantics."""

    def __init__(self) -> None:
        super().__init__("objc")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int8_t", "i16": "int16_t", "i32": "int32_t", "i64": "NSInteger",
                "u8": "uint8_t", "u16": "uint16_t", "u32": "uint32_t", "u64": "NSUInteger",
                "f32": "float", "f64": "double", "bool": "BOOL",
                "char": "char", "string": "NSString *", "void": "void", "any": "id"
            }
            return m.get(t.name, "id")
        elif t.kind == "list":
            return "NSArray *"
        elif t.kind == "map":
            return "NSDictionary *"
        elif t.kind == "pointer":
            return f"{t.element_type.name if t.element_type else 'NSObject'} *"
        return f"{t.name} *" if t.name not in ("NSInteger", "NSUInteger", "BOOL", "double", "float", "void") else t.name

