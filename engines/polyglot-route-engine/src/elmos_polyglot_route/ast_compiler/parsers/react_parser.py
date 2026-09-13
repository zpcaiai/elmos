"""React 18/19 TSX Functional Component Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, RawSnippetStmt, LiteralExpr,
    UIComponentDecl, UIStateVar, UIViewNode, UIEventBinding
)
from .base import BaseAstParser


class ReactAstParser(BaseAstParser):
    """Parses React Functional Components, TSX Props, useState hooks, and JSX return trees."""

    def __init__(self) -> None:
        super().__init__("react")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="react_module", source_language="react")

        # 1. Imports
        for match in re.finditer(r'import\s+(?:\{[^}]+\}|\*\s+as\s+[A-Za-z0-9_]+|[A-Za-z0-9_]+)\s+from\s+["\']([^"\']+)["\']', source_code):
            module.imports.append(match.group(1))

        # 2. Parse Props interface if exists: interface UserCardProps { name: string; age?: number; }
        props_map: dict[str, list[UniversalParam]] = {}
        for match in re.finditer(r'interface\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{([^}]+)\}', source_code):
            if_name = match.group(1)
            props_list: list[UniversalParam] = []
            for line in match.group(2).splitlines():
                line = line.strip().rstrip(';')
                if ':' in line:
                    p_name, p_type_str = line.split(':', 1)
                    is_opt = p_name.strip().endswith('?')
                    clean_name = p_name.strip().rstrip('?')
                    u_type = self._parse_ts_type(p_type_str.strip())
                    u_type.is_nullable = is_opt
                    props_list.append(UniversalParam(name=clean_name, type_info=u_type))
            props_map[if_name] = props_list

        # 3. Parse Function Component: export function UserCard(props: UserCardProps) { ... }
        comp_regex = re.compile(
            r'(?:export\s+)?(?:default\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)(?:\s*:\s*[A-Za-z0-9_<>\s]+)?\s*\{([^}]+return\s*\([^;]+\);?[^}]*)\}',
            re.DOTALL
        )

        for match in comp_regex.finditer(source_code):
            comp_name = match.group(1)
            param_str = match.group(2).strip()
            body_str = match.group(3)

            ui_comp = UIComponentDecl(name=comp_name)
            u_class = UniversalClass(name=comp_name, super_class="React.Component")

            # Link props
            if param_str:
                props_type_match = re.search(r':\s*([A-Za-z0-9_]+)', param_str)
                if props_type_match and props_type_match.group(1) in props_map:
                    ui_comp.props = props_map[props_type_match.group(1)]
                else:
                    ui_comp.props = [UniversalParam(name="props", type_info=UniversalType.custom("Props"))]

            # Parse useState: const [count, setCount] = useState<number>(0);
            state_regex = re.compile(r'const\s*\[([A-Za-z0-9_]+),\s*set([A-Za-z0-9_]+)\]\s*=\s*useState(?:<([^>]+)>)?\(([^)]*)\);')
            for s_match in state_regex.finditer(body_str):
                s_name = s_match.group(1)
                s_type_raw = s_match.group(3)
                s_init_val = s_match.group(4)
                s_type = self._parse_ts_type(s_type_raw.strip()) if s_type_raw else UniversalType.int64()
                ui_comp.state_vars.append(UIStateVar(
                    name=s_name,
                    type_info=s_type,
                    initial_value=LiteralExpr(s_init_val.strip()) if s_init_val else None
                ))
                u_class.fields.append(UniversalField(name=s_name, type_info=s_type))

            # Parse JSX return node: return (<div className="...">...</div>);
            jsx_match = re.search(r'return\s*\(\s*(<[A-Za-z0-9_]+[^>]*>.*?</[A-Za-z0-9_]+>|<[A-Za-z0-9_]+[^/>]*/>)\s*\);', body_str, re.DOTALL)
            if jsx_match:
                ui_comp.root_view = self._parse_jsx_tree(jsx_match.group(1))

            module.ui_components.append(ui_comp)
            module.classes.append(u_class)

        return module

    def _parse_jsx_tree(self, jsx_text: str) -> UIViewNode:
        tag_match = re.match(r'<([A-Za-z0-9_]+)', jsx_text.strip())
        tag = tag_match.group(1) if tag_match else "div"
        node = UIViewNode(tag=tag)
        # Check onClick
        if 'onClick=' in jsx_text:
            node.events.append(UIEventBinding(event_name="onClick", handler_method_name="handleClick"))
        # Check text content inside
        text_match = re.search(r'>([^<]+)<', jsx_text)
        if text_match:
            node.text_content = text_match.group(1).strip()
        return node

    def _parse_ts_type(self, raw: str) -> UniversalType:
        s = raw.strip()
        if s == 'string':
            return UniversalType.string_type()
        if s == 'number':
            return UniversalType.float64()
        if s == 'boolean':
            return UniversalType.boolean()
        if s == 'void':
            return UniversalType.void()
        return UniversalType.custom(s)
