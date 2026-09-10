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

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("#pragma once")
        lines.append("")
        lines.append("#include <string>")
        lines.append("#include <vector>")
        lines.append("#include <unordered_map>")
        lines.append("#include <memory>")
        lines.append("#include <optional>")
        lines.append("#include <future>")
        lines.append("#include <iostream>")
        lines.append("#include <stdexcept>")
        lines.append("")
        lines.append("namespace enterprise {")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_class(c))
            lines.append("")

        lines.append("} // namespace enterprise")
        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        super_spec = f" : public {c.super_class}" if c.super_class else ""
        lines.append(f"class {c.name}{super_spec} {{")
        lines.append("public:")

        # Fields
        for f in c.fields:
            t_str = self.format_type(f.type_info)
            def_str = f" = {f.default_value.value}" if f.default_value and hasattr(f.default_value, 'value') else ""
            lines.append(f"    {t_str} {f.name}{def_str};")

        if c.fields and c.methods:
            lines.append("")

        # Methods
        for m in c.methods:
            ret_type = self.format_type(m.return_type)
            if m.is_async:
                ret_type = f"std::future<{ret_type}>"
            
            params_str = ", ".join(f"const {self.format_type(p.type_info)}& {p.name}" if p.type_info.is_reference else f"{self.format_type(p.type_info)} {p.name}" for p in m.params)
            static_spec = "static " if m.is_static else ""
            lines.append(f"    {static_spec}{ret_type} {m.name}({params_str}) {{")
            
            if m.body:
                for s in m.body:
                    if hasattr(s, 'value') and s.value:
                        v = getattr(s.value, 'name', getattr(s.value, 'value', '{}'))
                        if v == 'default':
                            v = '{}'
                        lines.append(f"        return {v};")
                    elif hasattr(s, 'code'):
                        lines.append(f"        {s.code}")
            else:
                if ret_type != "void":
                    lines.append(f"        return {{}};")
            lines.append("    }")

        lines.append("};")
        return "\n".join(lines)
