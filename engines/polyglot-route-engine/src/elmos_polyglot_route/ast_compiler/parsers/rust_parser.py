"""AST parser for Rust enterprise code."""

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


class RustAstParser(BaseAstParser):
    """Parses Rust code into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('rust')

    def parse(self, source_code: str) -> UniversalModule:
        # 1. Attempt genuine native syn AST compiler first
        native_mod = NativeBridge.parse_rust_with_syn(source_code)
        if native_mod and (native_mod.classes or native_mod.free_functions):
            return native_mod

        module = UniversalModule(name='RustModule', source_language='rust')

        # Uses
        for u in re.finditer(r'use\s+([a-zA-Z0-9_:]+);', source_code):
            module.imports.append(u.group(1))

        # Structs
        struct_regex = re.compile(
            r'((?:#\[[^\]]+\]\s*)*)'
            r'(?:pub\s+)?struct\s+([a-zA-Z0-9_]+)\s*\{([^}]*)\}',
            re.MULTILINE
        )
        for sm in struct_regex.finditer(source_code):
            attrs_str = sm.group(1)
            s_name = sm.group(2)
            s_body = sm.group(3)
            fields = []
            for line in s_body.strip().splitlines():
                line = line.strip().rstrip(',')
                if not line or line.startswith('//'):
                    continue
                if ':' in line:
                    fname, ftype_str = line.split(':', 1)
                    fname = fname.replace('pub', '').strip()
                    ftype = self.parse_type(ftype_str.strip())
                    fields.append(UniversalField(name=fname, type_info=ftype))
            module.classes.append(UniversalClass(name=s_name, fields=fields, is_struct=True))

        # Impl blocks
        impl_regex = re.compile(r'impl(?:<[^>]+>)?\s+([a-zA-Z0-9_]+)\s*\{', re.MULTILINE)
        pos = 0
        while pos < len(source_code):
            m = impl_regex.search(source_code, pos)
            if not m:
                break
            struct_name = m.group(1)
            open_brace = m.end() - 1
            close_brace = self._find_matching_brace(source_code, open_brace)
            impl_body = source_code[open_brace + 1:close_brace] if close_brace != -1 else ''
            pos = close_brace + 1 if close_brace != -1 else len(source_code)

            # Find methods inside impl
            methods = self._parse_impl_methods(impl_body)
            target_cls = None
            for c in module.classes:
                if c.name == struct_name:
                    target_cls = c
                    break
            if not target_cls:
                target_cls = UniversalClass(name=struct_name)
                module.classes.append(target_cls)

            for fn in methods:
                if fn.name in ('new', 'default'):
                    target_cls.constructors.append(UniversalConstructor(params=fn.params, body=fn.body))
                else:
                    target_cls.methods.append(fn)

        if not module.classes:
            module.classes.append(UniversalClass(name='RustService'))

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

    def _parse_impl_methods(self, impl_body: str) -> list[UniversalMethod]:
        methods = []
        fn_regex = re.compile(
            r'((?:#\[[^\]]+\]\s*)*)'
            r'(?:pub\s+)?'
            r'(async\s+)?fn\s+([a-zA-Z0-9_]+)\s*'
            r'\(([^)]*)\)'
            r'(?:\s*->\s*([^{]+))?\s*\{',
            re.MULTILINE
        )
        pos = 0
        while pos < len(impl_body):
            m = fn_regex.search(impl_body, pos)
            if not m:
                break
            attrs_str = m.group(1)
            is_async = bool(m.group(2))
            fn_name = m.group(3)
            params_str = m.group(4)
            ret_type_str = (m.group(5) or '()').strip()

            brace_start = m.end() - 1
            brace_end = self._find_matching_brace(impl_body, brace_start)
            body = impl_body[brace_start + 1:brace_end] if brace_end != -1 else ''
            pos = brace_end + 1 if brace_end != -1 else len(impl_body)

            params = []
            for p in params_str.split(','):
                p = p.strip()
                if not p or p in ('&self', '&mut self', 'self'):
                    continue
                if ':' in p:
                    pname, ptype = p.split(':', 1)
                    params.append(UniversalParam(name=pname.strip(), type_info=self.parse_type(ptype.strip())))

            # Unpack Result<T, E>
            inner_ret = ret_type_str
            if ret_type_str.startswith('Result<'):
                inner_ret = ret_type_str[7:].split(',', 1)[0].strip()
            ret_type = self.parse_type(inner_ret)

            http_m = 'GET' if 'get' in fn_name else ('POST' if 'create' in fn_name else None)

            methods.append(UniversalMethod(
                name=fn_name,
                params=params,
                return_type=ret_type,
                is_async=is_async,
                http_method=http_m,
                http_path='/{' + params[0].name + '}' if (http_m == 'GET' and params) else ('/' if http_m else None),
                body=[RawSnippetStmt(body.strip())]
            ))
        return methods
