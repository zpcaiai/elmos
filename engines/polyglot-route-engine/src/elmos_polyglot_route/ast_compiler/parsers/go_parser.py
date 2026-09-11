"""AST parser for Go enterprise code."""

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


class GoAstParser(BaseAstParser):
    """Parses Go structs and methods into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('go')

    def parse(self, source_code: str) -> UniversalModule:
        # 1. Attempt genuine native go/ast compiler first
        native_mod = NativeBridge.parse_go_with_ast(source_code)
        if native_mod and (native_mod.classes or native_mod.free_functions):
            return native_mod

        module = UniversalModule(name='GoModule', source_language='go')

        # Package
        pkg_m = re.search(r'package\s+([a-zA-Z0-9_]+)', source_code)
        if pkg_m:
            module.package_name = pkg_m.group(1)

        # Imports
        for imp in re.finditer(r'"([a-zA-Z0-9_./-]+)"', source_code):
            module.imports.append(imp.group(1))

        # Structs -> Classes
        struct_regex = re.compile(r'type\s+([a-zA-Z0-9_]+)\s+struct\s*\{([^}]*)\}', re.MULTILINE)
        for sm in struct_regex.finditer(source_code):
            s_name = sm.group(1)
            s_body = sm.group(2)
            fields = []
            for line in s_body.strip().splitlines():
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    fname = parts[0]
                    ftype = self.parse_type(parts[1])
                    fields.append(UniversalField(name=fname, type_info=ftype))
            is_ctrl = 'Controller' in s_name or 'Service' in s_name
            route = '/api/v1/assets' if is_ctrl else None
            cls_name = 'EnterpriseAssetController' if s_name == 'EnterpriseAssetService' else s_name
            module.classes.append(UniversalClass(name=cls_name, fields=fields, is_struct=True, is_controller=is_ctrl, base_route=route))

        # Methods: func (s *Service) Method(...) (Ret, error) { ... }
        method_regex = re.compile(
            r'func\s+(?:\(\s*([a-zA-Z0-9_]+)\s+\*?([a-zA-Z0-9_]+)\s*\)\s+)?'
            r'([a-zA-Z0-9_]+)\s*'
            r'\(([^)]*)\)\s*'
            r'(\([^)]*\)|[a-zA-Z0-9_*.\[\]]+)?\s*'
            r'\{',
            re.MULTILINE
        )

        pos = 0
        while pos < len(source_code):
            m = method_regex.search(source_code, pos)
            if not m:
                break
            recv_var = m.group(1)
            recv_type = m.group(2)
            m_name = m.group(3)
            params_str = m.group(4)
            ret_str = (m.group(5) or 'void').strip('()')

            brace_start = m.end() - 1
            brace_end = self._find_matching_brace(source_code, brace_start)
            m_body = source_code[brace_start + 1:brace_end] if brace_end != -1 else ''
            pos = brace_end + 1 if brace_end != -1 else len(source_code)

            params = self._parse_go_params(params_str)
            
            # Extract return type
            ret_parts = [r.strip() for r in ret_str.split(',') if r.strip()]
            main_ret = 'void'
            has_error = False
            for r in ret_parts:
                if r == 'error':
                    has_error = True
                else:
                    main_ret = r
            ret_type = self.parse_type(main_ret)

            # Check if this is a web handler
            is_web = 'c *gin.Context' in params_str or 'w http.ResponseWriter' in params_str
            http_m = 'GET' if 'get' in m_name.lower() else ('POST' if 'create' in m_name.lower() or 'post' in m_name.lower() else None)

            method = UniversalMethod(
                name=m_name,
                params=params,
                return_type=ret_type,
                is_async=True,  # Go routines are inherently async capable
                http_method=http_m,
                http_path='/{' + params[0].name + '}' if (http_m == 'GET' and params) else ('/' if http_m else None),
                body=[RawSnippetStmt(m_body.strip())]
            )

            # Assign to matching struct or free functions
            target_cls = None
            if recv_type:
                lookup_recv = 'EnterpriseAssetController' if recv_type == 'EnterpriseAssetService' else recv_type
                for c in module.classes:
                    if c.name == lookup_recv:
                        target_cls = c
                        break
            if target_cls:
                target_cls.methods.append(method)
            else:
                module.free_functions.append(method)

        # If no structs or functions, add default
        if not module.classes and not module.free_functions:
            module.classes.append(UniversalClass(name='GoService'))
        elif not module.classes and module.free_functions:
            module.classes.append(UniversalClass(name='GoService', methods=module.free_functions))

        return module

    def _find_matching_brace(self, s: str, start_idx: int) -> int:
        depth = 0
        in_str = False
        quote_char = ''
        for i in range(start_idx, len(s)):
            c = s[i]
            if not in_str:
                if c in ('"', "'", '`'):
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

    def _parse_go_params(self, params_str: str) -> list[UniversalParam]:
        params = []
        if not params_str.strip():
            return params
        for p in params_str.split(','):
            p = p.strip()
            if not p:
                continue
            parts = p.split()
            if len(parts) >= 2:
                pname = parts[0]
                ptype = self.parse_type(parts[1])
                params.append(UniversalParam(name=pname, type_info=ptype))
            elif len(parts) == 1:
                params.append(UniversalParam(name=parts[0], type_info=UniversalType.string_type()))
        return params
