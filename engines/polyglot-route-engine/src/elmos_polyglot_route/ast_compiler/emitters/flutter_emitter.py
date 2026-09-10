"""Idiomatic Flutter / Dart Widget Emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType, UIComponentDecl
from .base import BaseEmitter


class FlutterEmitter(BaseEmitter):
    """Emits Flutter StatelessWidget and StatefulWidget Dart source files."""

    def __init__(self) -> None:
        super().__init__("flutter")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int", "i16": "int", "i32": "int", "i64": "int",
                "u8": "int", "u16": "int", "u32": "int", "u64": "int",
                "f32": "double", "f64": "double", "bool": "bool",
                "char": "String", "string": "String", "void": "void", "any": "dynamic"
            }
            res = m.get(t.name, "dynamic")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            res = f"List<{elem}>"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            res = f"Map<{k}, {v}>"
        else:
            res = t.name or "dynamic"
        if t.is_nullable and not res.endswith("?"):
            res = f"{res}?"
        return res

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("import 'package:flutter/material.dart';")
        lines.append("")

        if module.ui_components:
            for ui_comp in module.ui_components:
                lines.append(self._emit_widget(ui_comp))
                lines.append("")

        for c in module.classes:
            lines.append(self._emit_data_class(c))
            lines.append("")

        return "\n".join(lines)

    def _emit_widget(self, comp: UIComponentDecl) -> str:
        lines = []
        lines.append(f"class {comp.name} extends StatefulWidget {{")
        lines.append(f"  const {comp.name}({{super.key}});")
        lines.append("")
        lines.append("  @override")
        lines.append(f"  State<{comp.name}> createState() => _{comp.name}State();")
        lines.append("}")
        lines.append("")
        lines.append(f"class _{comp.name}State extends State<{comp.name}> {{")

        for s in comp.state_vars:
            t_str = self.format_type(s.type_info)
            def_val = f" = {s.initial_value.value}" if s.initial_value and hasattr(s.initial_value, 'value') else ""
            lines.append(f"  {t_str} _{s.name}{def_val};")

        lines.append("")
        lines.append("  @override")
        lines.append("  Widget build(BuildContext context) {")
        lines.append("    return Container(")
        lines.append("      padding: const EdgeInsets.all(16.0),")
        lines.append(f"      child: Text('{comp.name} View'),")
        lines.append("    );")
        lines.append("  }")
        lines.append("}")
        return "\n".join(lines)

    def _emit_data_class(self, c: UniversalClass) -> str:
        lines = []
        lines.append(f"class {c.name} {{")
        for f in c.fields:
            lines.append(f"  final {self.format_type(f.type_info)} {f.name};")
        lines.append("")
        params_str = ", ".join(f"required this.{f.name}" for f in c.fields)
        lines.append(f"  {c.name}({{{params_str}}});")
        lines.append("}")
        return "\n".join(lines)
