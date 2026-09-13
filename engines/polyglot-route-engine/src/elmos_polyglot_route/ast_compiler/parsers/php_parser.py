"""AST parser for PHP enterprise code."""

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


class PhpAstParser(BaseAstParser):
    """Parses PHP classes and methods into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('php')

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name='PhpModule', source_language='php')

        # Namespace
        ns_m = re.search(r'^\s*namespace\s+([a-zA-Z0-9_\\]+);', source_code, re.MULTILINE)
        if ns_m:
            module.package_name = ns_m.group(1)

        # Uses
        for u in re.finditer(r'^\s*use\s+([a-zA-Z0-9_\\]+);', source_code, re.MULTILINE):
            module.imports.append(u.group(1))

        # Classes: class Asset { ... }
        class_regex = re.compile(
            r'((?:#\[[^\]]+\]\s*)*)'
            r'class\s+([a-zA-Z0-9_]+)'
            r'(?:\s+extends\s+[a-zA-Z0-9_]+)?'
            r'\s*\{',
            re.MULTILINE
        )
        pos = 0
        while pos < len(source_code):
            m = class_regex.search(source_code, pos)
            if not m:
                break
            attrs_str = m.group(1)
            cls_name = m.group(2)
            open_brace = m.end() - 1
            close_brace = self._find_matching_brace(source_code, open_brace)
            body = source_code[open_brace + 1:close_brace] if close_brace != -1 else ''
            pos = close_brace + 1 if close_brace != -1 else len(source_code)

            fields: list[UniversalField] = []
            constructors: list[UniversalConstructor] = []
            methods: list[UniversalMethod] = []

            # Constructor promotion: public function __construct(public string , ...)
            ctor_match = re.search(r'function\s+__construct\s*\(([^)]*)\)\s*\{', body)
            if ctor_match:
                params_str = ctor_match.group(1)
                params = self._parse_php_params(params_str)
                for p in params:
                    fields.append(UniversalField(name=p.name, type_info=p.type_info))
                constructors.append(UniversalConstructor(params=params))

            # Regular fields: public string $serial;
            field_regex = re.compile(
                r'(public|private|protected)\s+([a-zA-Z0-9_\\]+)\s+\$([a-zA-Z0-9_]+)\s*;',
                re.MULTILINE
            )
            for fm in field_regex.finditer(body):
                f_type = self.parse_type(fm.group(2))
                f_name = fm.group(3)
                if not any(f.name == f_name for f in fields):
                    fields.append(UniversalField(name=f_name, type_info=f_type))

            # Methods: public function getAssetBySerial(string $serial): JsonResponse { ... }
            method_regex = re.compile(
                r'((?:#\[[^\]]+\]\s*)*)'
                r'(?:(public|private|protected)\s+)?'
                r'function\s+([a-zA-Z0-9_]+)\s*'
                r'\(([^)]*)\)'
                r'(?:\s*:\s*([a-zA-Z0-9_\\]+))?'
                r'\s*\{',
                re.MULTILINE
            )
            m_pos = 0
            while m_pos < len(body):
                mm = method_regex.search(body, m_pos)
                if not mm:
                    break
                m_name = mm.group(3)
                if m_name == '__construct':
                    m_pos = mm.end()
                    continue
                p_str = mm.group(4)
                r_str = mm.group(5) or 'void'
                b_start = mm.end() - 1
                b_end = self._find_matching_brace(body, b_start)
                m_body_str = body[b_start + 1:b_end] if b_end != -1 else ''
                m_pos = b_end + 1 if b_end != -1 else len(body)

                params = self._parse_php_params(p_str)
                ret_type = self.parse_type(r_str)
                http_m = 'GET' if 'get' in m_name else ('POST' if 'create' in m_name else None)

                methods.append(UniversalMethod(
                    name=m_name,
                    params=params,
                    return_type=ret_type,
                    http_method=http_m,
                    http_path='/{' + params[0].name + '}' if (http_m == 'GET' and params) else ('/' if http_m else None),
                    body=[RawSnippetStmt(m_body_str.strip())]
                ))

            is_controller = 'Controller' in cls_name
            module.classes.append(UniversalClass(
                name=cls_name,
                fields=fields,
                constructors=constructors,
                methods=methods,
                is_controller=is_controller,
                base_route='/api/v1/' + cls_name.lower().replace('controller', '') if is_controller else None,
            ))

        if not module.classes:
            module.classes.append(UniversalClass(name='PhpService'))

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

    def _parse_php_params(self, params_str: str) -> list[UniversalParam]:
        params = []
        if not params_str.strip():
            return params
        for p in params_str.split(','):
            p = p.strip()
            if not p:
                continue
            # e.g. public string  or string 
            p = re.sub(r'^(?:public|private|protected|readonly)\s+', '', p).strip()
            parts = p.split()
            if len(parts) >= 2:
                ptype = self.parse_type(parts[0])
                pname = parts[1].lstrip('$')
                params.append(UniversalParam(name=pname, type_info=ptype))
            elif len(parts) == 1:
                pname = parts[0].lstrip('$')
                params.append(UniversalParam(name=pname, type_info=UniversalType.string_type()))
        return params
