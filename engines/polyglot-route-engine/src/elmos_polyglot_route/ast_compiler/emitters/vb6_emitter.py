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

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        mod_name = module.name or "Module1"
        lines.append(f'Attribute VB_Name = "{mod_name}"')
        lines.append("Option Explicit")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_class(c))

        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        for f in c.fields:
            lines.append(f"Public {f.name} As {self.format_type(f.type_info)}")

        if c.fields and c.methods:
            lines.append("")

        for m in c.methods:
            ret_type = self.format_type(m.return_type)
            params_str = ", ".join(f"ByVal {p.name} As {self.format_type(p.type_info)}" for p in m.params)
            
            if ret_type == "Void":
                lines.append(f"Public Sub {m.name}({params_str})")
                lines.append("    ' Generated VB6 Sub implementation")
                lines.append("End Sub")
            else:
                lines.append(f"Public Function {m.name}({params_str}) As {ret_type}")
                lines.append(f"    ' Generated VB6 Function implementation")
                lines.append("End Function")
            lines.append("")

        return "\n".join(lines)
