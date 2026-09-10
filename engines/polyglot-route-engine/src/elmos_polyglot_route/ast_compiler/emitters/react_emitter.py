"""Idiomatic React 18/19 TSX Functional Component Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType, UIComponentDecl
from .base import BaseEmitter


class ReactEmitter(BaseEmitter):
    """Emits clean, production-grade TypeScript React (TSX) functional components."""

    def __init__(self) -> None:
        super().__init__("react")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "number", "i16": "number", "i32": "number", "i64": "number",
                "u8": "number", "u16": "number", "u32": "number", "u64": "number",
                "f32": "number", "f64": "number", "bool": "boolean",
                "char": "string", "string": "string", "void": "void", "any": "any"
            }
            return m.get(t.name, "any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"{elem}[]"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"Record<{k}, {v}>"
        return t.name or "any"

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("import React, { useState, useEffect, useCallback } from 'react';")
        lines.append("")

        # 1. Emit UI Components
        if module.ui_components:
            for ui_comp in module.ui_components:
                lines.append(self._emit_ui_component(ui_comp))
                lines.append("")

        # 2. Emit Standard Classes / DTOs
        for c in module.classes:
            lines.append(self._emit_class(c))
            lines.append("")

        return "\n".join(lines)

    def _emit_ui_component(self, comp: UIComponentDecl) -> str:
        lines = []
        # Props interface
        lines.append(f"export interface {comp.name}Props {{")
        for p in comp.props:
            opt = "?" if p.type_info.is_nullable else ""
            lines.append(f"    {p.name}{opt}: {self.format_type(p.type_info)};")
        lines.append("}")
        lines.append("")

        # Component definition
        lines.append(f"export const {comp.name}: React.FC<{comp.name}Props> = (props) => {{")

        # State hooks
        for s in comp.state_vars:
            t_str = self.format_type(s.type_info)
            def_val = s.initial_value.value if s.initial_value and hasattr(s.initial_value, 'value') else "null"
            setter = f"set{s.name[0].upper()}{s.name[1:]}"
            lines.append(f"    const [{s.name}, {setter}] = useState<{t_str}>({def_val});")

        lines.append("")
        lines.append("    return (")
        lines.append(f"        <div className='{comp.name.lower()}-container'>")
        lines.append(f"            <h3>{comp.name}</h3>")
        lines.append("        </div>")
        lines.append("    );")
        lines.append("};")
        lines.append(f"export default {comp.name};")
        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        lines.append(f"export interface {c.name} {{")
        for f in c.fields:
            lines.append(f"    {f.name}: {self.format_type(f.type_info)};")
        lines.append("}")
        return "\n".join(lines)
