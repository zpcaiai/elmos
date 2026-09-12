"""AST parser for TypeScript enterprise code."""

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


class TypeScriptAstParser(BaseAstParser):
    """Parses TypeScript code into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('typescript')

    def parse(self, source_code: str) -> UniversalModule:
        # 1. Attempt genuine native TypeScript Compiler API first
        native_mod = NativeBridge.parse_typescript_with_node(source_code)
        if native_mod and (any(c.methods for c in native_mod.classes) or native_mod.free_functions):
            return native_mod

        module = UniversalModule(name='TypeScriptModule', source_language='typescript')

        # Imports
        for imp in re.finditer(r'import\s+(?:\{[^}]+\}|\*\s+as\s+[a-zA-Z0-9_]+|[a-zA-Z0-9_]+)\s+from\s+["\']([^"\']+)["\'];', source_code):
            module.imports.append(imp.group(1))

        # Classes
        class_blocks = self._extract_class_blocks(source_code)
        for cls_name, annotations, base_route, is_controller, body in class_blocks:
            cls = self._parse_class_body(cls_name, annotations, base_route, is_controller, body)
            module.classes.append(cls)

        if not module.classes:
            module.classes.append(UniversalClass(name='TypeScriptDefaultClass'))

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

    def _find_matching_paren(self, s: str, start_idx: int) -> int:
        depth = 0
        in_str = False
        quote_char = ''
        for i in range(start_idx, len(s)):
            c = s[i]
            if not in_str:
                if c in ('"', "'", '`'):
                    in_str = True
                    quote_char = c
                elif c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        return i
            else:
                if c == quote_char and (i == 0 or s[i - 1] != '\\'):
                    in_str = False
        return -1

    def _parse_decorators(self, raw: str) -> list[UniversalAnnotation]:
        annos = []
        for m in re.finditer(r'@([a-zA-Z0-9_]+)(?:\(([^)]*)\))?', raw):
            name = m.group(1)
            arg_str = m.group(2) or ''
            args = [a.strip().strip('"\'') for a in arg_str.split(',') if a.strip()]
            annos.append(UniversalAnnotation(name=name, args=args))
        return annos

    def _extract_class_blocks(self, source: str) -> list[tuple[str, list[UniversalAnnotation], str | None, bool, str]]:
        results = []
        class_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:export\s+)?(?:default\s+)?'
            r'class\s+([a-zA-Z0-9_]+)'
            r'(?:<[^>]+>)?'
            r'(?:\s+extends\s+[a-zA-Z0-9_]+)?'
            r'(?:\s+implements\s+[a-zA-Z0-9_,\s]+)?'
            r'\s*\{',
            re.MULTILINE
        )

        pos = 0
        while pos < len(source):
            m = class_regex.search(source, pos)
            if not m:
                break
            dec_str = m.group(1).strip()
            cls_name = m.group(2)
            open_brace = m.end() - 1
            close_brace = self._find_matching_brace(source, open_brace)
            body = source[open_brace + 1:close_brace] if close_brace != -1 else source[open_brace + 1:]

            annotations = self._parse_decorators(dec_str)
            is_controller = any(a.name in ('Controller', 'RestController') for a in annotations)
            base_route = None
            for a in annotations:
                if a.name == 'Controller' and a.args:
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

        # Parse constructor
        ctor_match = re.search(r'constructor\s*\(([^)]*)\)\s*\{', body)
        if ctor_match:
            params_str = ctor_match.group(1)
            params = self._parse_ts_params(params_str)
            brace_start = ctor_match.end() - 1
            brace_end = self._find_matching_brace(body, brace_start)
            ctor_body = body[brace_start + 1:brace_end] if brace_end != -1 else ''
            constructors.append(UniversalConstructor(params=params, body=[RawSnippetStmt(ctor_body.strip())]))
            # Also if constructor has public/private modifiers, they are fields
            for p in params:
                if not any(f.name == p.name for f in fields):
                    fields.append(UniversalField(name=p.name, type_info=p.type_info))

        # Explicit fields: serial: string; or private status: string;
        field_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:(public|private|protected|readonly)\s+)*'
            r'([a-zA-Z0-9_]+)\s*\??\s*:\s*([a-zA-Z0-9_<>,\[\]]+)'
            r'(?:\s*=\s*([^;]+))?\s*;',
            re.MULTILINE
        )
        for fm in field_regex.finditer(body):
            f_annos = self._parse_decorators(fm.group(1))
            f_name = fm.group(3)
            f_type = self.parse_type(fm.group(4))
            if not any(f.name == f_name for f in fields):
                fields.append(UniversalField(name=f_name, type_info=f_type, annotations=f_annos))

        # Methods: @Get(':serial') async getAssetBySerial(@Param('serial') serial: string): Promise<Asset> { ... }
        method_start_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:(public|private|protected)\s+)?'
            r'(?:(static|async)\s+)*'
            r'([a-zA-Z0-9_]+)\s*\(',
            re.MULTILINE
        )

        pos = 0
        while pos < len(body):
            m = method_start_regex.search(body, pos)
            if not m:
                break
            dec_str = m.group(1)
            name_str = m.group(4)
            if name_str in ('constructor', 'if', 'for', 'while', 'switch', 'catch'):
                pos = m.end()
                continue
            open_paren = m.end() - 1
            close_paren = self._find_matching_paren(body, open_paren)
            if close_paren == -1:
                pos = m.end()
                continue
            params_str = body[open_paren + 1:close_paren]
            after_paren = body[close_paren + 1:]
            ret_match = re.match(r'(?:\s*:\s*([a-zA-Z0-9_<>,\[\]\s]+?))?\s*\{', after_paren)
            if not ret_match:
                pos = close_paren + 1
                continue
            ret_type_str = (ret_match.group(1) or '').strip() or 'void'
            open_brace = close_paren + 1 + ret_match.end() - 1
            brace_end = self._find_matching_brace(body, open_brace)
            m_body = body[open_brace + 1:brace_end] if brace_end != -1 else ''
            pos = brace_end + 1 if brace_end != -1 else len(body)

            m_annos = self._parse_decorators(dec_str)
            params = self._parse_ts_params(params_str)

            is_async = 'async' in m.group(0) or 'Promise<' in ret_type_str
            inner_ret = ret_type_str
            if 'Promise<' in ret_type_str:
                inner_ret = ret_type_str.split('Promise<', 1)[1].rstrip('>')
            ret_type = self.parse_type(inner_ret)

            http_m = None
            http_p = None
            for a in m_annos:
                if a.name == 'Get':
                    http_m = 'GET'
                    http_p = a.args[0] if a.args else ''
                elif a.name == 'Post':
                    http_m = 'POST'
                    http_p = a.args[0] if a.args else ''
                elif a.name == 'Put':
                    http_m = 'PUT'
                    http_p = a.args[0] if a.args else ''
                elif a.name == 'Delete':
                    http_m = 'DELETE'
                    http_p = a.args[0] if a.args else ''

            methods.append(UniversalMethod(
                name=name_str,
                params=params,
                return_type=ret_type,
                is_async=is_async,
                annotations=m_annos,
                http_method=http_m,
                http_path=http_p,
                body=self._parse_statements_simple(m_body.strip())
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

    def _parse_ts_params(self, params_str: str) -> list[UniversalParam]:
        params = []
        if not params_str.strip():
            return params
        for p in params_str.split(','):
            p = p.strip()
            if not p:
                continue
            # Extract @Param('serial') serial: string or public serial: string
            annos = []
            while p.startswith('@'):
                end_idx = p.find(')')
                if end_idx != -1:
                    dec_txt = p[:end_idx+1]
                    annos.extend(self._parse_decorators(dec_txt))
                    p = p[end_idx+1:].strip()
                else:
                    break
            # Strip visibility
            p = re.sub(r'^(?:public|private|protected|readonly)\s+', '', p).strip()
            if ':' in p:
                name_part, type_part = p.split(':', 1)
                pname = name_part.strip().rstrip('?')
                ptype = self.parse_type(type_part.strip())
                params.append(UniversalParam(name=pname, type_info=ptype, annotations=annos))
            else:
                params.append(UniversalParam(name=p.strip(), type_info=UniversalType.string_type()))
        return params

    def _parse_statements_simple(self, body_str: str) -> list[UniversalStmt]:
        stmts: list[UniversalStmt] = []
        try_match = re.search(r'\btry\s*\{', body_str)
        if try_match:
            start = try_match.end() - 1
            end = self._find_matching_brace(body_str, start)
            try_content = body_str[start+1:end] if end != -1 else ''
            catches = []
            catch_regex = re.compile(r'\bcatch\s*(?:\(([^)]+)\))?\s*\{')
            for cm in catch_regex.finditer(body_str):
                c_start = cm.end() - 1
                c_end = self._find_matching_brace(body_str, c_start)
                c_content = body_str[c_start+1:c_end] if c_end != -1 else ''
                c_decl = (cm.group(1) or '').strip().split(':')
                exc_var = c_decl[0].strip() if c_decl else 'error'
                exc_type = c_decl[1].strip() if len(c_decl) > 1 else 'any'
                catches.append(CatchClause(exception_type=exc_type, variable_name=exc_var, body=[RawSnippetStmt(c_content.strip())]))
            stmts.append(TryCatchFinallyStmt(try_body=[RawSnippetStmt(try_content.strip())], catch_clauses=catches))
            return stmts
        if body_str.strip():
            stmts.append(RawSnippetStmt(body_str.strip()))
        return stmts

