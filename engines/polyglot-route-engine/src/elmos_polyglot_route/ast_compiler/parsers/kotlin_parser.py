"""AST parser for Kotlin enterprise code."""

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


class KotlinAstParser(BaseAstParser):
    """Parses Kotlin data classes and services into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('kotlin')

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name='KotlinModule', source_language='kotlin')

        # Package
        pkg_m = re.search(r'package\s+([a-zA-Z0-9_.]+)', source_code)
        if pkg_m:
            module.package_name = pkg_m.group(1)

        # Imports
        for imp in re.finditer(r'import\s+([a-zA-Z0-9_.*]+)', source_code):
            module.imports.append(imp.group(1))

        # Data classes: data class Asset(val serial: String, val status: String, val value: Double)
        data_cls_regex = re.compile(
            r'data\s+class\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)',
            re.MULTILINE
        )
        for dcm in data_cls_regex.finditer(source_code):
            c_name = dcm.group(1)
            params_str = dcm.group(2)
            fields = []
            for p in params_str.split(','):
                p = p.strip()
                if not p:
                    continue
                clean = re.sub(r'^(?:val|var)\s+', '', p).strip()
                if ':' in clean:
                    fname, ftype = clean.split(':', 1)
                    fields.append(UniversalField(name=fname.strip(), type_info=self.parse_type(ftype.strip())))
            module.classes.append(UniversalClass(name=c_name, fields=fields))

        # Standard classes: [Annotations] class EnterpriseAssetController { ... }
        class_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(?:open\s+)?class\s+([a-zA-Z0-9_]+)'
            r'(?:\s*\(([^)]*)\))?'
            r'\s*\{',
            re.MULTILINE
        )
        pos = 0
        while pos < len(source_code):
            m = class_regex.search(source_code, pos)
            if not m:
                break
            annos_str = m.group(1)
            cls_name = m.group(2)
            open_brace = m.end() - 1
            close_brace = self._find_matching_brace(source_code, open_brace)
            body = source_code[open_brace + 1:close_brace] if close_brace != -1 else ''
            pos = close_brace + 1 if close_brace != -1 else len(source_code)

            annos = self._parse_annotations(annos_str)
            is_controller = any(a.name in ('RestController', 'Controller') for a in annos)
            base_route = None
            for a in annos:
                if a.name in ('RequestMapping', 'Route') and a.args:
                    base_route = a.args[0]
            if is_controller and not base_route:
                base_route = '/api/v1/' + cls_name.lower().replace('controller', '')

            # Methods inside class: [Annotations] suspend fun getAssetBySerial(serial: String): Asset { ... }
            methods = self._parse_methods(body)

            module.classes.append(UniversalClass(
                name=cls_name,
                methods=methods,
                annotations=annos,
                is_controller=is_controller,
                base_route=base_route,
            ))

        if not module.classes:
            module.classes.append(UniversalClass(name='KotlinService'))

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

    def _parse_annotations(self, raw: str) -> list[UniversalAnnotation]:
        annos = []
        for m in re.finditer(r'@([a-zA-Z0-9_]+)(?:\(([^)]*)\))?', raw):
            name = m.group(1)
            arg_str = m.group(2) or ''
            args = [a.strip().strip('"\'') for a in arg_str.split(',') if a.strip()]
            annos.append(UniversalAnnotation(name=name, args=args))
        return annos

    def _parse_methods(self, body: str) -> list[UniversalMethod]:
        methods = []
        method_regex = re.compile(
            r'((?:@[a-zA-Z0-9_]+(?:\([^)]*\))?\s*)*)'
            r'(suspend\s+)?fun\s+([a-zA-Z0-9_]+)\s*'
            r'\(([^)]*)\)'
            r'(?:\s*:\s*([a-zA-Z0-9_<>,\[\]]+))?'
            r'\s*\{',
            re.MULTILINE
        )
        pos = 0
        while pos < len(body):
            m = method_regex.search(body, pos)
            if not m:
                break
            annos_str = m.group(1)
            is_async = bool(m.group(2))
            name = m.group(3)
            params_str = m.group(4)
            ret_type_str = m.group(5) or 'Unit'

            brace_start = m.end() - 1
            brace_end = self._find_matching_brace(body, brace_start)
            m_body = body[brace_start + 1:brace_end] if brace_end != -1 else ''
            pos = brace_end + 1 if brace_end != -1 else len(body)

            m_annos = self._parse_annotations(annos_str)
            params = []
            for p in params_str.split(','):
                p = p.strip()
                if not p:
                    continue
                if ':' in p:
                    pname, ptype = p.split(':', 1)
                    params.append(UniversalParam(name=pname.strip(), type_info=self.parse_type(ptype.strip())))

            ret_type = self.parse_type(ret_type_str)

            http_m = None
            http_p = None
            for a in m_annos:
                if a.name == 'GetMapping':
                    http_m = 'GET'
                    http_p = a.args[0] if a.args else ''
                elif a.name == 'PostMapping':
                    http_m = 'POST'
                    http_p = a.args[0] if a.args else ''

            methods.append(UniversalMethod(
                name=name,
                params=params,
                return_type=ret_type,
                is_async=is_async,
                annotations=m_annos,
                http_method=http_m,
                http_path=http_p,
                body=[RawSnippetStmt(m_body.strip())]
            ))
        return methods
