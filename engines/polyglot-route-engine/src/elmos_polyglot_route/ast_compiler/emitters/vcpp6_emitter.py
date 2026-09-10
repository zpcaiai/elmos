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

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("#if !defined(AFX_ENTERPRISE_MODULE_H__INCLUDED_)")
        lines.append("#define AFX_ENTERPRISE_MODULE_H__INCLUDED_")
        lines.append("")
        lines.append("#if _MSC_VER > 1000")
        lines.append("#pragma once")
        lines.append("#endif // _MSC_VER > 1000")
        lines.append("")
        lines.append("#include <afxwin.h>")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_class(c))
            lines.append("")

        lines.append("#endif // !defined(AFX_ENTERPRISE_MODULE_H__INCLUDED_)")
        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        super_cls = c.super_class or "CObject"
        lines.append(f"class {c.name} : public {super_cls}")
        lines.append("{")
        lines.append("public:")

        for f in c.fields:
            lines.append(f"    {self.format_type(f.type_info)} {f.name};")

        if c.fields and c.methods:
            lines.append("")

        for m in c.methods:
            ret_type = self.format_type(m.return_type)
            params_str = ", ".join(f"{self.format_type(p.type_info)} {p.name}" for p in m.params)
            lines.append(f"    {ret_type} {m.name}({params_str})")
            lines.append("    {")
            lines.append("    }")

        lines.append("};")
        return "\n".join(lines)
