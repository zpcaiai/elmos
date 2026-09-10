"""Swift 5.10 / 6.0 AST Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, ThrowStmt, RawSnippetStmt, LiteralExpr
)
from .base import BaseAstParser


class SwiftAstParser(BaseAstParser):
    """Parses modern Swift structs, classes, actors, and async/await methods into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__("swift")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="swift_module", source_language="swift")

        # 1. Imports
        for match in re.finditer(r'import\s+([A-Za-z0-9_]+)', source_code):
            module.imports.append(match.group(1))

        # 2. Struct, Class, Actor definitions with balanced braces
        entity_head_regex = re.compile(
            r'(?:public\s+|open\s+|final\s+)?(?:(struct|class|actor))\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_,\s]+))?\s*\{'
        )

        for match in entity_head_regex.finditer(source_code):
            entity_kind = match.group(1)
            entity_name = match.group(2)
            conformances = match.group(3)
            end_brace = self.find_matching_brace(source_code, match.start())
            if end_brace == -1:
                continue
            body = source_code[match.end():end_brace]

            u_class = UniversalClass(
                name=entity_name,
                is_struct=(entity_kind == 'struct')
            )
            if conformances:
                items = [c.strip() for c in conformances.split(',')]
                if items:
                    u_class.super_class = items[0]
                    u_class.interfaces = items[1:]

            # Parse fields: var name: Type, let name: Type
            field_regex = re.compile(
                r'(?:@Published\s+)?(?:public\s+|private\s+)?(var|let)\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_?:<>\s]+?)(?:\s*=\s*([^\n;]+))?(?:\n|;|$)'
            )
            for f_match in field_regex.finditer(body):
                f_name = f_match.group(2)
                t_str = f_match.group(3).strip()
                def_val = f_match.group(4)
                u_class.fields.append(UniversalField(
                    name=f_name,
                    type_info=self._parse_swift_type(t_str),
                    is_readonly=(f_match.group(1) == 'let'),
                    default_value=LiteralExpr(def_val.strip()) if def_val else None
                ))

            # Parse methods with balanced braces
            method_head_regex = re.compile(
                r'(?:@MainActor\s+)?(?:public\s+|private\s+)?(?:(static)\s+)?func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)(?:\s+(async))?(?:\s+(throws))?(?:\s*->\s*([^{]+))?\s*\{'
            )
            for m_match in method_head_regex.finditer(body):
                is_static = bool(m_match.group(1))
                m_name = m_match.group(2)
                params_str = m_match.group(3)
                is_async = bool(m_match.group(4))
                throws = bool(m_match.group(5))
                ret_str = m_match.group(6)
                
                m_end_brace = self.find_matching_brace(body, m_match.start())
                if m_end_brace == -1:
                    continue
                m_body_str = body[m_match.end():m_end_brace]

                u_method = UniversalMethod(
                    name=m_name,
                    is_static=is_static,
                    is_async=is_async,
                    has_exception_handling=throws,
                    return_type=self._parse_swift_type(ret_str.strip()) if ret_str else UniversalType.void()
                )

                if params_str.strip():
                    for p_item in params_str.split(','):
                        p_parts = p_item.strip().split(':')
                        if len(p_parts) == 2:
                            p_name = p_parts[0].strip().split()[-1]
                            p_type = self._parse_swift_type(p_parts[1].strip())
                            u_method.params.append(UniversalParam(name=p_name, type_info=p_type))

                u_method.body = self._parse_body_stmts(m_body_str)
                u_class.methods.append(u_method)

            module.classes.append(u_class)

        return module

    def _parse_swift_type(self, raw: str) -> UniversalType:
        s = raw.strip()
        is_opt = s.endswith('?')
        if is_opt:
            s = s[:-1].strip()
        if s.startswith('[') and s.endswith(']'):
            inner = s[1:-1].strip()
            if ':' in inner:
                k, v = inner.split(':', 1)
                return UniversalType.map_of(self._parse_swift_type(k), self._parse_swift_type(v))
            return UniversalType.list_of(self._parse_swift_type(inner))
        if s in ('String',):
            res = UniversalType.string_type()
        elif s in ('Int', 'Int64'):
            res = UniversalType.int64()
        elif s in ('Int32',):
            res = UniversalType.primitive('i32')
        elif s in ('Double', 'Float'):
            res = UniversalType.float64()
        elif s in ('Bool',):
            res = UniversalType.boolean()
        elif s in ('Void', '()'):
            res = UniversalType.void()
        else:
            res = UniversalType.custom(s)
        res.is_nullable = is_opt
        return res

    def _parse_body_stmts(self, body_text: str) -> list[UniversalStmt]:
        stmts: list[UniversalStmt] = []
        for line in body_text.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith('//'):
                continue
            if line_str.startswith('return '):
                val = line_str[7:].strip()
                stmts.append(ReturnStmt(value=LiteralExpr(val)))
            elif line_str.startswith('throw '):
                val = line_str[6:].strip()
                stmts.append(ThrowStmt(exception_expr=LiteralExpr(val)))
            else:
                stmts.append(RawSnippetStmt(code=line_str))
        return stmts
