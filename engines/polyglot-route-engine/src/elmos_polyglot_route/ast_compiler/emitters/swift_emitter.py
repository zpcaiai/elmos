"""Idiomatic Swift 5.10 / 6.0 Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class SwiftEmitter(BaseEmitter):
    """Emits modern idiomatic Swift structs, classes, and async/await methods."""

    def __init__(self) -> None:
        super().__init__("swift")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "Int8", "i16": "Int16", "i32": "Int32", "i64": "Int64",
                "u8": "UInt8", "u16": "UInt16", "u32": "UInt32", "u64": "UInt64",
                "f32": "Float", "f64": "Double", "bool": "Bool",
                "char": "Character", "string": "String", "void": "Void", "any": "Any"
            }
            res = m.get(t.name, "Any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            res = f"[{elem}]"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            res = f"[{k}: {v}]"
        elif t.kind == "optional":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            res = f"{elem}?"
        else:
            res = t.name or "Any"
        if t.is_nullable and not res.endswith("?"):
            res = f"{res}?"
        return res

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("import Foundation")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_class(c))
            lines.append("")

        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        decl_kind = "struct" if c.is_struct else "class"
        conforms = [c.super_class] if c.super_class else []
        conforms.extend(c.interfaces)
        conf_str = f": {', '.join(conforms)}" if conforms else ""

        lines.append(f"public {decl_kind} {c.name}{conf_str} {{")

        for f in c.fields:
            mut = "let" if f.is_readonly else "var"
            t_str = self.format_type(f.type_info)
            def_str = f" = {f.default_value.value}" if f.default_value and hasattr(f.default_value, 'value') else ""
            lines.append(f"    public {mut} {f.name}: {t_str}{def_str}")

        if c.fields and c.methods:
            lines.append("")

        for m in c.methods:
            async_spec = " async" if m.is_async else ""
            throws_spec = " throws" if m.has_exception_handling or m.throws_exceptions else ""
            ret_type = self.format_type(m.return_type)
            ret_spec = f" -> {ret_type}" if ret_type != "Void" else ""
            static_spec = "static " if m.is_static else ""
            params_str = ", ".join(f"{p.name}: {self.format_type(p.type_info)}" for p in m.params)

            lines.append(f"    public {static_spec}func {m.name}({params_str}){async_spec}{throws_spec}{ret_spec} {{")
            if m.body:
                for s in m.body:
                    if hasattr(s, 'value') and s.value:
                        v = getattr(s.value, 'name', getattr(s.value, 'value', 'nil'))
                        lines.append(f"        return {v}")
                    elif hasattr(s, 'code'):
                        lines.append(f"        {s.code}")
            else:
                if ret_type != "Void":
                    lines.append(f"        // Default returned instance\n        fatalError('Not implemented')")
            lines.append("    }")

        lines.append("}")
        return "\n".join(lines)
