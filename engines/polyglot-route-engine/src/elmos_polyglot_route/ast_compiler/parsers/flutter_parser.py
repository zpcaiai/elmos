"""Flutter / Dart Widget AST Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, RawSnippetStmt, LiteralExpr,
    UIComponentDecl, UIStateVar, UIViewNode, UIEventBinding
)
from .base import BaseAstParser


class FlutterAstParser(BaseAstParser):
    """Parses Flutter StatelessWidget and StatefulWidget into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__("flutter")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="flutter_module", source_language="flutter")

        # 1. Imports
        for match in re.finditer(r'import\s+["\']([^"\']+)["\']\s*;', source_code):
            module.imports.append(match.group(1))

        # 2. StatelessWidget / StatefulWidget
        widget_regex = re.compile(
            r'class\s+([A-Za-z_][A-Za-z0-9_]*)\s+extends\s+(StatelessWidget|StatefulWidget)\s*\{([^}]+)\}',
            re.DOTALL
        )
        for match in widget_regex.finditer(source_code):
            w_name = match.group(1)
            w_kind = match.group(2)
            w_body = match.group(3)

            ui_comp = UIComponentDecl(name=w_name, is_stateful=(w_kind == 'StatefulWidget'))
            u_class = UniversalClass(name=w_name, super_class=w_kind)

            # Extract final fields (props)
            field_regex = re.compile(r'final\s+([A-Za-z0-9_?<>]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;')
            for f_match in field_regex.finditer(w_body):
                f_type_str = f_match.group(1)
                f_name = f_match.group(2)
                t_info = self._parse_dart_type(f_type_str)
                ui_comp.props.append(UniversalParam(name=f_name, type_info=t_info))
                u_class.fields.append(UniversalField(name=f_name, type_info=t_info, is_readonly=True))

            module.ui_components.append(ui_comp)
            module.classes.append(u_class)

        # 3. State class: class _MyWidgetState extends State<MyWidget> { ... }
        state_regex = re.compile(
            r'class\s+([A-Za-z_][A-Za-z0-9_]*)\s+extends\s+State<([A-Za-z0-9_]+)>\s*\{([^}]+Widget\s+build\([^)]+\)\s*\{[^}]+\}[^}]*)\}',
            re.DOTALL
        )
        for match in state_regex.finditer(source_code):
            state_cls_name = match.group(1)
            parent_widget = match.group(2)
            state_body = match.group(3)

            # Find corresponding UIComponentDecl
            target_comp = next((c for c in module.ui_components if c.name == parent_widget), None)
            if not target_comp:
                target_comp = UIComponentDecl(name=parent_widget, is_stateful=True)
                module.ui_components.append(target_comp)

            # Extract state variables: int _counter = 0;
            state_var_regex = re.compile(r'(int|double|String|bool)\s+(_?[A-Za-z0-9_]+)\s*(?:=\s*([^;]+))?;')
            for sv_match in state_var_regex.finditer(state_body):
                t_name = sv_match.group(1)
                v_name = sv_match.group(2)
                v_init = sv_match.group(3)
                target_comp.state_vars.append(UIStateVar(
                    name=v_name,
                    type_info=self._parse_dart_type(t_name),
                    initial_value=LiteralExpr(v_init.strip()) if v_init else None
                ))

            # Extract build tree return Widget
            build_match = re.search(r'Widget\s+build\s*\([^)]*\)\s*\{.*?return\s+([A-Za-z0-9_]+)\s*\((.*?)\);', state_body, re.DOTALL)
            if build_match:
                widget_tag = build_match.group(1)
                widget_args = build_match.group(2)
                node = UIViewNode(tag=widget_tag)
                if 'onPressed:' in widget_args:
                    node.events.append(UIEventBinding(event_name="onPressed", handler_method_name="onPressed"))
                target_comp.root_view = node

        return module

    def _parse_dart_type(self, raw: str) -> UniversalType:
        s = raw.strip()
        is_opt = s.endswith('?')
        if is_opt:
            s = s[:-1].strip()
        if s in ('String',):
            res = UniversalType.string_type()
        elif s in ('int',):
            res = UniversalType.int64()
        elif s in ('double',):
            res = UniversalType.float64()
        elif s in ('bool',):
            res = UniversalType.boolean()
        elif s in ('void',):
            res = UniversalType.void()
        else:
            res = UniversalType.custom(s)
        res.is_nullable = is_opt
        return res
