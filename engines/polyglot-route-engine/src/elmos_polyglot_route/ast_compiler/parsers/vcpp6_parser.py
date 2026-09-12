"""Visual C++ 6.0 MFC/ATL AST Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, RawSnippetStmt, LiteralExpr
)
from .base import BaseAstParser


class Vcpp6AstParser(BaseAstParser):
    """Parses VC++6 MFC dialog classes, message maps, and CString fields into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__("vcpp6")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="vcpp6_module", source_language="vcpp6")

        # 1. Includes
        for match in re.finditer(r'#include\s+[<"]([^>"]+)[>"]', source_code):
            module.imports.append(match.group(1))

        # 2. MFC Class definition: class CMainDlg : public CDialog { ... };
        class_head_regex = re.compile(
            r'class\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*(?:public|private|protected)?\s*([A-Za-z_][A-Za-z0-9_]*))?\s*\{'
        )
        for match in class_head_regex.finditer(source_code):
            c_name = match.group(1)
            s_name = match.group(2)
            end_brace = self.find_matching_brace(source_code, match.start())
            if end_brace == -1:
                continue
            body = source_code[match.end():end_brace]

            u_class = UniversalClass(name=c_name, super_class=s_name if s_name else "CDialog")

            # Parse fields: CString m_strName; int m_nAge;
            field_regex = re.compile(r'(CString|DWORD|BOOL|int|long|double)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;')
            for f_match in field_regex.finditer(body):
                f_type = self._parse_vcpp6_type(f_match.group(1))
                f_name = f_match.group(2)
                u_class.fields.append(UniversalField(name=f_name, type_info=f_type))

            # Parse methods: afx_msg void OnOK(); or void Calculate();
            method_regex = re.compile(
                r'(?:afx_msg\s+)?(void|BOOL|int|CString|double)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?:\{([^}]+)\}|;)',
                re.DOTALL
            )
            for m_match in method_regex.finditer(body):
                ret_type = self._parse_vcpp6_type(m_match.group(1))
                m_name = m_match.group(2)
                m_body = m_match.group(4)

                u_method = UniversalMethod(name=m_name, return_type=ret_type)
                if m_body:
                    for line in m_body.splitlines():
                        line = line.strip()
                        if line.startswith('return ') and line.endswith(';'):
                            u_method.body.append(ReturnStmt(value=LiteralExpr(line[7:-1].strip())))
                        elif line and not line.startswith('//'):
                            u_method.body.append(RawSnippetStmt(code=line))
                u_class.methods.append(u_method)

            module.classes.append(u_class)

        return module

    def _parse_vcpp6_type(self, raw: str) -> UniversalType:
        s = raw.strip()
        if s in ('CString',):
            return UniversalType.string_type()
        if s in ('BOOL', 'bool'):
            return UniversalType.boolean()
        if s in ('DWORD', 'long', '__int64'):
            return UniversalType.int64()
        if s in ('int',):
            return UniversalType.primitive('i32')
        if s in ('double',):
            return UniversalType.float64()
        if s in ('void',):
            return UniversalType.void()
        return UniversalType.custom(s)
