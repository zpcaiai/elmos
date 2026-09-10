"""Modern C++20 AST Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, VarDeclStmt, ThrowStmt, TryCatchFinallyStmt,
    ExprStmt, RawSnippetStmt, MethodCallExpr, IdentifierExpr, LiteralExpr
)
from .base import BaseAstParser


class CppAstParser(BaseAstParser):
    """Parses C++20 classes, structs, namespaces, and methods into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__("cpp")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="cpp_module", source_language="cpp")
        
        # 1. Imports / Includes
        for match in re.finditer(r'#include\s+[<"]([^>"]+)[>"]', source_code):
            module.imports.append(match.group(1))

        # 2. Namespace
        ns_match = re.search(r'namespace\s+([A-Za-z0-9_:]+)\s*\{', source_code)
        if ns_match:
            module.package_name = ns_match.group(1)

        # 3. Class / Struct definition with balanced braces
        class_head_regex = re.compile(
            r'(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*(?:public|private|protected)?\s*([A-Za-z_][A-Za-z0-9_]*))?\s*\{'
        )
        
        for match in class_head_regex.finditer(source_code):
            class_name = match.group(1)
            super_class = match.group(2)
            end_brace = self.find_matching_brace(source_code, match.start())
            if end_brace == -1:
                continue
            body = source_code[match.end():end_brace]
            
            u_class = UniversalClass(
                name=class_name,
                super_class=super_class.strip() if super_class else None
            )

            # Extract fields
            field_regex = re.compile(
                r'(?:(?:public|private|protected)\s*:\s*)?(?:(static|const)\s+)?([A-Za-z0-9_:<>]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*([^;]+))?;'
            )
            for f_match in field_regex.finditer(body):
                if '(' in f_match.group(0):  # Skip methods
                    continue
                type_str = f_match.group(2)
                f_name = f_match.group(3)
                default_val = f_match.group(4)
                keywords = {'return', 'throw', 'if', 'while', 'for', 'switch', 'else', 'case', 'break', 'continue'}
                if f_name in keywords or type_str in keywords:
                    continue
                u_type = self._parse_cpp_type(type_str)
                u_class.fields.append(UniversalField(
                    name=f_name,
                    type_info=u_type,
                    default_value=LiteralExpr(default_val.strip()) if default_val else None
                ))

            # Extract methods with balanced braces
            method_head_regex = re.compile(
                r'(?:(static|virtual|inline|explicit)\s+)?([A-Za-z0-9_:<>]+)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)(?:\s+const)?(?:\s+noexcept)?\s*\{'
            )
            for m_match in method_head_regex.finditer(body):
                ret_type_str = m_match.group(2)
                m_name = m_match.group(3)
                params_str = m_match.group(4)
                
                m_end_brace = self.find_matching_brace(body, m_match.start())
                if m_end_brace == -1:
                    continue
                m_body_str = body[m_match.end():m_end_brace]
                
                if m_name in ('if', 'while', 'switch', 'catch'):
                    continue

                u_method = UniversalMethod(
                    name=m_name,
                    return_type=self._parse_cpp_type(ret_type_str),
                    is_static=bool(m_match.group(1) == 'static')
                )
                
                # Parse parameters
                if params_str.strip():
                    for param_str in params_str.split(','):
                        param_parts = param_str.strip().split()
                        if len(param_parts) >= 2:
                            p_type_str = ' '.join(param_parts[:-1]).replace('const', '').replace('&', '').replace('*', '').strip()
                            p_name = param_parts[-1].lstrip('&').lstrip('*').strip()
                            u_method.params.append(UniversalParam(name=p_name, type_info=self._parse_cpp_type(p_type_str)))

                u_method.body = self._parse_body_stmts(m_body_str)
                u_class.methods.append(u_method)

            module.classes.append(u_class)

        return module

    def _parse_cpp_type(self, raw: str) -> UniversalType:
        s = raw.strip()
        if 'shared_ptr<' in s:
            inner = s[s.find('<')+1:s.rfind('>')].strip()
            return UniversalType.shared_ptr_of(self._parse_cpp_type(inner))
        if 'unique_ptr<' in s:
            inner = s[s.find('<')+1:s.rfind('>')].strip()
            return UniversalType.unique_ptr_of(self._parse_cpp_type(inner))
        if 'vector<' in s:
            inner = s[s.find('<')+1:s.rfind('>')].strip()
            return UniversalType.list_of(self._parse_cpp_type(inner))
        if 'map<' in s or 'unordered_map<' in s:
            parts = s[s.find('<')+1:s.rfind('>')].split(',')
            k = self._parse_cpp_type(parts[0].strip()) if len(parts) > 0 else UniversalType.string_type()
            v = self._parse_cpp_type(parts[1].strip()) if len(parts) > 1 else UniversalType.custom("Any")
            return UniversalType.map_of(k, v)
        if s in ('std::string', 'string'):
            return UniversalType.string_type()
        if s in ('int', 'int32_t', 'i32'):
            return UniversalType.primitive('i32')
        if s in ('int64_t', 'long', 'long long', 'i64'):
            return UniversalType.int64()
        if s in ('double', 'float', 'f64'):
            return UniversalType.float64()
        if s in ('bool', 'boolean'):
            return UniversalType.boolean()
        if s in ('void',):
            return UniversalType.void()
        return UniversalType.custom(s)

    def _parse_body_stmts(self, body_text: str) -> list[UniversalStmt]:
        stmts: list[UniversalStmt] = []
        for line in body_text.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith('//'):
                continue
            if line_str.startswith('return ') and line_str.endswith(';'):
                val = line_str[7:-1].strip()
                stmts.append(ReturnStmt(value=LiteralExpr(val)))
            elif line_str.startswith('throw ') and line_str.endswith(';'):
                val = line_str[6:-1].strip()
                stmts.append(ThrowStmt(exception_expr=LiteralExpr(val)))
            else:
                stmts.append(RawSnippetStmt(code=line_str))
        return stmts
