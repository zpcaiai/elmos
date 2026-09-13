"""Visual Basic 6.0 AST Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, RawSnippetStmt, LiteralExpr,
    UIComponentDecl, UIStateVar, UIViewNode, UIEventBinding
)
from .base import BaseAstParser


class Vb6AstParser(BaseAstParser):
    """Parses VB6 forms (.frm) and modules (.bas, .cls) into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__("vb6")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="vb6_module", source_language="vb6")

        # 1. Attribute VB_Name = "Form1"
        mod_name = "Form1"
        name_match = re.search(r'Attribute\s+VB_Name\s*=\s*"([^"]+)"', source_code, re.IGNORECASE)
        if name_match:
            mod_name = name_match.group(1)

        u_class = UniversalClass(name=mod_name)
        ui_comp = UIComponentDecl(name=mod_name)

        # 2. Dim variable As Type
        dim_regex = re.compile(r'^\s*(?:Dim|Private|Public)\s+([A-Za-z0-9_]+)\s+As\s+([A-Za-z0-9_]+)', re.MULTILINE | re.IGNORECASE)
        for d_match in dim_regex.finditer(source_code):
            var_name = d_match.group(1)
            type_str = d_match.group(2)
            u_type = self._parse_vb6_type(type_str)
            u_class.fields.append(UniversalField(name=var_name, type_info=u_type))
            ui_comp.state_vars.append(UIStateVar(name=var_name, type_info=u_type))

        # 3. Functions: Public Function Name(param As Type) As ReturnType ... End Function
        fn_regex = re.compile(
            r'^\s*(?:Public|Private)?\s*Function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s+As\s+([A-Za-z0-9_]+)(.*?)\s*End\s+Function',
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        for f_match in fn_regex.finditer(source_code):
            fn_name = f_match.group(1)
            params_str = f_match.group(2)
            ret_type = self._parse_vb6_type(f_match.group(3))
            body_str = f_match.group(4)

            u_method = UniversalMethod(name=fn_name, return_type=ret_type)
            if params_str.strip():
                for p_item in params_str.split(','):
                    # ByVal name As Type
                    p_match = re.search(r'(?:ByVal|ByRef)?\s*([A-Za-z0-9_]+)\s+As\s+([A-Za-z0-9_]+)', p_item, re.IGNORECASE)
                    if p_match:
                        u_method.params.append(UniversalParam(
                            name=p_match.group(1),
                            type_info=self._parse_vb6_type(p_match.group(2))
                        ))

            for line in body_str.splitlines():
                line = line.strip()
                if line.lower().startswith(f"{fn_name.lower()} ="):
                    val = line.split('=', 1)[1].strip()
                    u_method.body.append(ReturnStmt(value=LiteralExpr(val)))
                elif line and not line.startswith("'"):
                    u_method.body.append(RawSnippetStmt(code=line))

            u_class.methods.append(u_method)

        # 4. Subs and Event handlers: Private Sub Command1_Click() ... End Sub
        sub_regex = re.compile(
            r'^\s*(?:Public|Private)?\s*Sub\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)(.*?)\s*End\s+Sub',
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        for s_match in sub_regex.finditer(source_code):
            sub_name = s_match.group(1)
            body_str = s_match.group(3)
            u_method = UniversalMethod(name=sub_name, return_type=UniversalType.void())
            u_class.methods.append(u_method)

            # Map event handlers to UIComponentDecl
            if '_Click' in sub_name or '_Load' in sub_name:
                ctrl_name = sub_name.split('_')[0]
                evt_name = sub_name.split('_')[1]
                ui_comp.root_view = ui_comp.root_view or UIViewNode(tag="Form")
                ui_comp.root_view.events.append(UIEventBinding(
                    event_name=evt_name,
                    handler_method_name=sub_name
                ))

        module.classes.append(u_class)
        module.ui_components.append(ui_comp)
        return module

    def _parse_vb6_type(self, raw: str) -> UniversalType:
        s = raw.strip().lower()
        if s in ('string',):
            return UniversalType.string_type()
        if s in ('long', 'integer'):
            return UniversalType.int64()
        if s in ('double', 'single'):
            return UniversalType.float64()
        if s in ('boolean',):
            return UniversalType.boolean()
        return UniversalType.custom(raw.strip())
