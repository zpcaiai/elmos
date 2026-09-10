"""AST parser for Java enterprise code."""

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


class JavaAstParser(BaseAstParser):
    """Parses Java classes, Spring controllers, and methods into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('java')

    def parse(self, source_code: str) -> UniversalModule:
        class_blocks = self._extract_class_blocks(source_code)

        # 1. Attempt genuine native javac Tree API compiler if single clean class
        if len(class_blocks) <= 1:
            native_mod = NativeBridge.parse_java_with_javac(source_code)
            if native_mod and len(native_mod.classes) >= max(1, len(class_blocks)):
                return native_mod

        module = UniversalModule(name='JavaModule', source_language='java')

        # Package
        pkg_match = re.search(r' package\s+([a-zA-Z0-9_.]+)\s*;', source_code)
        if pkg_match:
            module.package_name = pkg_match.group(1)

        # Imports
        for imp in re.finditer(r'import\s+([a-zA-Z0-9_.*]+)\s*;', source_code):
            module.imports.append(imp.group(1))

        # Split into classes
        class_blocks = self._extract_class_blocks(source_code)
        for cls_name, annotations, base_route, is_controller, body in class_blocks:
            cls = self._parse_class_body(cls_name, annotations, base_route, is_controller, body)
            module.classes.append(cls)

        if not module.classes:
            # Fallback if no explicit class
            module.classes.append(UniversalClass(name='JavaDefaultClass'))

        return module

    def _extract_class_blocks(self, source: str) -> list[tuple[str, list[UniversalAnnotation], str | None, bool, str]]:
        results = []
        # Find class declarations: annotations? class Name ... { ... }
        class_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:public\s+|private\s+|protected\s+|static\s+)*'
            r'class\s+([a-zA-Z0-9_]+)'
            r'(?:<[^>]+>)?'
            r'(?:\s+extends\s+[a-zA-Z0-9_]+(?:<[^>]+>)?)?'
            r'(?:\s+implements\s+[a-zA-Z0-9_,\s]+(?:<[^>]+>)?)?'
            r'\s*\{',
            re.MULTILINE
        )

        pos = 0
        while pos < len(source):
            m = class_regex.search(source, pos)
            if not m:
                break
            annos_str = m.group(1).strip()
            cls_name = m.group(2)
            open_brace_idx = m.end() - 1

            # Match closing brace
            close_brace_idx = self._find_matching_brace(source, open_brace_idx)
            body = source[open_brace_idx + 1:close_brace_idx] if close_brace_idx != -1 else source[open_brace_idx + 1:]

            # Process annotations
            annotations = self._parse_annotations(annos_str)
            is_controller = any(a.name in ('RestController', 'Controller') for a in annotations)
            base_route = None
            for a in annotations:
                if a.name in ('RequestMapping', 'Route') and a.args:
                    base_route = a.args[0].strip('"\'')
            if is_controller and not base_route:
                base_route = '/api/v1/' + cls_name.lower().replace('controller', '')

            results.append((cls_name, annotations, base_route, is_controller, body))
            pos = close_brace_idx + 1 if close_brace_idx != -1 else len(source)

        return results

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

    def _parse_annotations(self, raw: str) -> list[UniversalAnnotation]:
        annos = []
        for m in re.finditer(r'@([a-zA-Z0-9_]+)(?:\(([^)]*)\))?', raw):
            name = m.group(1)
            arg_str = m.group(2) or ''
            args = [a.strip().strip('"\'') for a in arg_str.split(',') if a.strip()]
            annos.append(UniversalAnnotation(name=name, args=args))
        return annos

    def _parse_class_body(self, cls_name: str, annotations: list[UniversalAnnotation], base_route: str | None, is_controller: bool, body: str) -> UniversalClass:
        fields: list[UniversalField] = []
        constructors: list[UniversalConstructor] = []
        methods: list[UniversalMethod] = []

        # Find member definitions
        # Method or constructor regex
        member_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:(public|private|protected)\s+)?'
            r'(?:(static|final|abstract)\s+)*'
            r'([a-zA-Z0-9_<>,\[\]]+)\s+'
            r'([a-zA-Z0-9_]+)\s*'
            r'\(([^)]*)\)'
            r'(?:\s*throws\s+([a-zA-Z0-9_,\s]+))?'
            r'\s*(\{|;)',
            re.MULTILINE
        )

        field_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:(public|private|protected)\s+)?'
            r'(?:(static|final)\s+)*'
            r'([a-zA-Z0-9_<>,\[\]]+)\s+'
            r'([a-zA-Z0-9_]+)'
            r'(?:\s*=\s*([^;]+))?\s*;',
            re.MULTILINE
        )

        # Extract fields
        JAVA_KEYWORDS = {'return', 'throw', 'package', 'import', 'new', 'assert', 'break', 'continue', 'goto', 'if', 'else', 'while', 'for', 'switch', 'case', 'default'}
        for fm in field_regex.finditer(body):
            f_annos = self._parse_annotations(fm.group(1))
            f_vis = fm.group(2) or 'private'
            f_type_str = fm.group(4)
            f_name = fm.group(5)
            # Skip if this matched a keyword, method signature, or duplicate field
            if f_type_str in JAVA_KEYWORDS or f_name in JAVA_KEYWORDS:
                continue
            if f_name in ('get', 'set', 'is') or '(' in f_type_str or f_name == cls_name:
                continue
            if any(f.name == f_name for f in fields):
                continue
            f_type = self.parse_type(f_type_str)
            fields.append(UniversalField(name=f_name, type_info=f_type, visibility=f_vis, annotations=f_annos))

        # Extract methods and constructors
        pos = 0
        while pos < len(body):
            m = member_regex.search(body, pos)
            if not m:
                break
            annos_str = m.group(1)
            visibility = m.group(2) or 'public'
            type_or_name = m.group(4)
            name_or_paren = m.group(5)
            params_str = m.group(6)
            is_block = m.group(8) == '{'

            m_annos = self._parse_annotations(annos_str)
            params = self._parse_params(params_str)

            if is_block:
                brace_start = m.end() - 1
                brace_end = self._find_matching_brace(body, brace_start)
                m_body_str = body[brace_start + 1:brace_end] if brace_end != -1 else ''
                pos = brace_end + 1 if brace_end != -1 else len(body)
            else:
                m_body_str = ''
                pos = m.end()

            # Constructor check
            if type_or_name == cls_name or name_or_paren == cls_name:
                constructors.append(UniversalConstructor(
                    params=params,
                    visibility=visibility,
                    body=self._parse_statements_simple(m_body_str)
                ))
            else:
                m_type = self.parse_type(type_or_name)
                is_async = 'CompletableFuture' in type_or_name or 'Task' in type_or_name
                http_m = None
                http_p = None
                for a in m_annos:
                    if a.name == 'GetMapping':
                        http_m = 'GET'
                        http_p = a.args[0] if a.args else ''
                    elif a.name == 'PostMapping':
                        http_m = 'POST'
                        http_p = a.args[0] if a.args else ''
                    elif a.name == 'PutMapping':
                        http_m = 'PUT'
                        http_p = a.args[0] if a.args else ''
                    elif a.name == 'DeleteMapping':
                        http_m = 'DELETE'
                        http_p = a.args[0] if a.args else ''

                methods.append(UniversalMethod(
                    name=name_or_paren,
                    params=params,
                    return_type=m_type,
                    visibility=visibility,
                    is_async=is_async,
                    annotations=m_annos,
                    http_method=http_m,
                    http_path=http_p,
                    body=self._parse_statements_simple(m_body_str)
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
            parts = p.split()
            # Check for annotations like @PathVariable String serial or @RequestBody Asset asset
            annos = []
            while parts and parts[0].startswith('@'):
                annos.append(UniversalAnnotation(name=parts[0][1:]))
                parts = parts[1:]
            if len(parts) >= 2:
                ptype = self.parse_type(parts[-2])
                pname = parts[-1]
                params.append(UniversalParam(name=pname, type_info=ptype, annotations=annos))
            elif len(parts) == 1:
                params.append(UniversalParam(name=parts[0], type_info=UniversalType.string_type()))
        return params

    def _parse_statements_simple(self, body_str: str) -> list[UniversalStmt]:
        stmts: list[UniversalStmt] = []
        # Check for try-catch
        try_match = re.search(r'try\s*\{', body_str)
        if try_match:
            start = try_match.end() - 1
            end = self._find_matching_brace(body_str, start)
            try_content = body_str[start+1:end] if end != -1 else ''
            # catches
            catches = []
            catch_regex = re.compile(r'catch\s*\(([^)]+)\)\s*\{')
            for cm in catch_regex.finditer(body_str):
                c_start = cm.end() - 1
                c_end = self._find_matching_brace(body_str, c_start)
                c_content = body_str[c_start+1:c_end] if c_end != -1 else ''
                c_decl = cm.group(1).strip().split()
                exc_type = c_decl[0] if c_decl else 'Exception'
                exc_var = c_decl[1] if len(c_decl) > 1 else 'ex'
                catches.append(CatchClause(exception_type=exc_type, variable_name=exc_var, body=[RawSnippetStmt(c_content.strip())]))
            stmts.append(TryCatchFinallyStmt(try_body=[RawSnippetStmt(try_content.strip())], catch_clauses=catches))
            return stmts

        # Check return
        ret_match = re.search(r'return\s+([^;]+);', body_str)
        if ret_match:
            stmts.append(ReturnStmt(value=RawSnippetExpr(ret_match.group(1).strip())))
        elif body_str.strip():
            stmts.append(RawSnippetStmt(body_str.strip()))
        return stmts
