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

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("#import <Foundation/Foundation.h>")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_interface(c))
            lines.append("")
            lines.append(self._emit_implementation(c))
            lines.append("")

        return "\n".join(lines)

    def _emit_interface(self, c: UniversalClass) -> str:
        lines = []
        super_cls = c.super_class or "NSObject"
        lines.append(f"@interface {c.name} : {super_cls}")

        for f in c.fields:
            t_str = self.format_type(f.type_info)
            prop_attr = "assign" if t_str in ("NSInteger", "NSUInteger", "BOOL", "double", "float") else "strong"
            lines.append(f"@property (nonatomic, {prop_attr}) {t_str} {f.name};")

        for m in c.methods:
            ret_type = self.format_type(m.return_type)
            sign = "+" if m.is_static else "-"
            if not m.params:
                lines.append(f"{sign} ({ret_type}){m.name};")
            else:
                p_strs = [f"{p.name}:({self.format_type(p.type_info)}){p.name}" for p in m.params]
                lines.append(f"{sign} ({ret_type}){m.name}With{':'.join(p_strs)};")

        lines.append("@end")
        return "\n".join(lines)

    def _emit_implementation(self, c: UniversalClass) -> str:
        lines = []
        lines.append(f"@implementation {c.name}")

        for m in c.methods:
            ret_type = self.format_type(m.return_type)
            sign = "+" if m.is_static else "-"
            if not m.params:
                lines.append(f"{sign} ({ret_type}){m.name} {{")
            else:
                p_strs = [f"{p.name}:({self.format_type(p.type_info)}){p.name}" for p in m.params]
                lines.append(f"{sign} ({ret_type}){m.name}With{':'.join(p_strs)} {{")

            if m.body:
                for s in m.body:
                    if hasattr(s, 'value') and s.value:
                        lines.append(f"    return {getattr(s.value, 'value', 'nil')};")
                    elif hasattr(s, 'code'):
                        lines.append(f"    {s.code}")
            else:
                if ret_type != "void":
                    lines.append("    return nil;")
            lines.append("}")

        lines.append("@end")
        return "\n".join(lines)
