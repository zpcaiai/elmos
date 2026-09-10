"""AST parser for C# enterprise code."""

from __future__ import annotations

import re
from typing import Any

from ..ir import (
    CatchClause,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    MethodCallExpr,
    PrimitiveKind,
    RawSnippetStmt,
    ReturnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UniversalAnnotation,
    UniversalClass,
    UniversalConstructor,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
)
from .base import BaseAstParser
from .native_bridge import NativeBridge


class CSharpAstParser(BaseAstParser):
    """Parses C# code into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('csharp')

    def parse(self, source_code: str) -> UniversalModule:
        class_blocks = self._extract_class_blocks(source_code)

        # 1. Attempt genuine native Roslyn compiler first for single clean non-controller class
        if len(class_blocks) <= 1 and not any(is_ctrl for _, _, _, is_ctrl, _ in class_blocks):
            native_mod = NativeBridge.parse_csharp_with_roslyn(source_code)
            if native_mod and (any(c.methods for c in native_mod.classes) or native_mod.free_functions):
                return native_mod

        module = UniversalModule(name='CSharpModule', source_language='csharp')

        # Usings
        for u in re.finditer(r'(?:^|\s)using\s+([a-zA-Z0-9_.]+)\s*;', source_code):
            module.imports.append(u.group(1))

        # Namespace
        ns_match = re.search(r'(?:^|\s)namespace\s+([a-zA-Z0-9_.]+)', source_code)
        if ns_match:
            module.package_name = ns_match.group(1)

        # Classes
        for cls_name, annotations, base_route, is_controller, body in class_blocks:
            cls = self._parse_class_body(cls_name, annotations, base_route, is_controller, body)
            module.classes.append(cls)

        if not module.classes:
            module.classes.append(UniversalClass(name='CSharpDefaultClass'))

        return module

    def _find_matching_brace(self, s: str, start_idx: int) -> int:
        depth = 0
        in_str = False
        quote_char = ''
        for i in range(start_idx, len(s)):
            c = s[i]
            if not in_str:
                if c in ('"', "'"):
                    in_str = True
                    quote_char = c
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        return i
            else:
                if c == quote_char and (i == 0 or s[i - 1] != '\\'):
                    in_str = False
        return -1

    def _parse_attributes(self, raw: str) -> list[UniversalAnnotation]:
        annos = []
        for m in re.finditer(r'\[([a-zA-Z0-9_]+)(?:\(([^)]*)\))?\]', raw):
            name = m.group(1)
            arg_str = m.group(2) or ''
            args = [a.strip().strip('"\'') for a in arg_str.split(',') if a.strip()]
            annos.append(UniversalAnnotation(name=name, args=args))
        return annos

    def _extract_class_blocks(self, source: str) -> list[tuple[str, list[UniversalAnnotation], str | None, bool, str]]:
        results = []
        class_regex = re.compile(
            r'((?:\[[^\]]+\]\s*)*)'
            r'(?:public\s+|private\s+|internal\s+|static\s+)*'
            r'class\s+([a-zA-Z0-9_]+)'
            r'(?:<[^>]+>)?'
            r'(?:\s*:\s*([a-zA-Z0-9_,\s<>]+))?'
            r'\s*\{',
            re.MULTILINE
        )

        pos = 0
        while pos < len(source):
            m = class_regex.search(source, pos)
            if not m:
                break
            attrs_str = m.group(1).strip()
            cls_name = m.group(2)
            open_brace = m.end() - 1
            close_brace = self._find_matching_brace(source, open_brace)
            body = source[open_brace + 1:close_brace] if close_brace != -1 else source[open_brace + 1:]

            annotations = self._parse_attributes(attrs_str)
            is_controller = any(a.name in ('ApiController', 'Controller') for a in annotations)
            base_route = None
            for a in annotations:
                if a.name == 'Route' and a.args:
                    base_route = a.args[0]
            if is_controller and not base_route:
                base_route = '/api/v1/' + cls_name.lower().replace('controller', '')

            results.append((cls_name, annotations, base_route, is_controller, body))
            pos = close_brace + 1 if close_brace != -1 else len(source)

        return results

    def _parse_class_body(self, cls_name: str, annotations: list[UniversalAnnotation], base_route: str | None, is_controller: bool, body: str) -> UniversalClass:
        fields: list[UniversalField] = []
        constructors: list[UniversalConstructor] = []
        methods: list[UniversalMethod] = []

        # Properties: [Attrs] public string Serial { get; set; } = string.Empty;
        prop_regex = re.compile(
            r'((?:\[[^\]]+\]\s*)*)'
            r'(?:public|private|protected|internal)\s+'
            r'([a-zA-Z0-9_<>,\[\]]+)\s+'
            r'([a-zA-Z0-9_]+)\s*'
            r'\{[^}]*\}'
            r'(?:\s*=\s*([^;]+);)?',
            re.MULTILINE
        )
        for pm in prop_regex.finditer(body):
            p_attrs = self._parse_attributes(pm.group(1))
            p_type = self.parse_type(pm.group(2))
            p_name = pm.group(3)
            fields.append(UniversalField(name=p_name, type_info=p_type, annotations=p_attrs))

        # Methods: [Attrs] public async Task<ActionResult<Asset>> GetAssetBySerial(...) { ... }
        method_regex = re.compile(
            r'((?:\[[^\]]+\]\s*)*)'
            r'(?:(public|private|protected|internal)\s+)?'
            r'(?:(static|virtual|override|async)\s+)*'
            r'([a-zA-Z0-9_<>,\[\]]+)\s+'
            r'([a-zA-Z0-9_]+)\s*'
            r'\(([^)]*)\)'
            r'\s*\{',
            re.MULTILINE
        )

        pos = 0
        while pos < len(body):
            m = method_regex.search(body, pos)
            if not m:
                break
            attrs_str = m.group(1)
            visibility = m.group(2) or 'public'
            type_str = m.group(4)
            name_str = m.group(5)
            params_str = m.group(6)

            m_attrs = self._parse_attributes(attrs_str)
            params = self._parse_params(params_str)

            brace_start = m.end() - 1
            brace_end = self._find_matching_brace(body, brace_start)
            m_body = body[brace_start + 1:brace_end] if brace_end != -1 else ''
            pos = brace_end + 1 if brace_end != -1 else len(body)

            if name_str == cls_name:
                constructors.append(UniversalConstructor(
                    params=params,
                    visibility=visibility,
                    body=[RawSnippetStmt(m_body.strip())]
                ))
            else:
                is_async = 'Task' in type_str or 'async' in m.group(0)
                # Unpack ActionResult<T>
                inner_ret = type_str
                if 'ActionResult<' in type_str:
                    inner_ret = type_str.split('ActionResult<', 1)[1].rstrip('>')
                if 'Task<' in inner_ret:
                    inner_ret = inner_ret.split('Task<', 1)[1].rstrip('>')
                ret_type = self.parse_type(inner_ret)

                http_m = None
                http_p = None
                for a in m_attrs:
                    if a.name == 'HttpGet':
                        http_m = 'GET'
                        http_p = a.args[0] if a.args else ''
                    elif a.name == 'HttpPost':
                        http_m = 'POST'
                        http_p = a.args[0] if a.args else ''
                    elif a.name == 'HttpPut':
                        http_m = 'PUT'
                        http_p = a.args[0] if a.args else ''
                    elif a.name == 'HttpDelete':
                        http_m = 'DELETE'
                        http_p = a.args[0] if a.args else ''

                methods.append(UniversalMethod(
                    name=name_str,
                    params=params,
                    return_type=ret_type,
                    visibility=visibility,
                    is_async=is_async,
                    annotations=m_attrs,
                    http_method=http_m,
                    http_path=http_p,
                    body=[RawSnippetStmt(m_body.strip())]
                ))

        return UniversalClass(
            name=cls_name,
            fields=fields,
            constructors=constructors,
            methods=methods,
            annotations=annotations,
            is_controller=is_controller,
            base_route=base_route,
        )

    def _parse_params(self, params_str: str) -> list[UniversalParam]:
        params = []
        if not params_str.strip():
            return params
        for p in params_str.split(','):
            p = p.strip()
            if not p:
                continue
            # Handle [FromBody] Asset asset
            annos = []
            while p.startswith('['):
                close = p.find(']')
                if close != -1:
                    attr_name = p[1:close].strip()
                    annos.append(UniversalAnnotation(name=attr_name))
                    p = p[close+1:].strip()
                else:
                    break
            parts = p.split()
            if len(parts) >= 2:
                ptype = self.parse_type(parts[-2])
                pname = parts[-1]
                params.append(UniversalParam(name=pname, type_info=ptype, annotations=annos))
            elif len(parts) == 1:
                params.append(UniversalParam(name=parts[0], type_info=UniversalType.string_type()))
        return params
