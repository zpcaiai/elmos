"""Objective-C ARC AST Parser producing Universal AST IR."""

from __future__ import annotations

import re
from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, RawSnippetStmt, LiteralExpr
)
from .base import BaseAstParser


class ObjCAstParser(BaseAstParser):
    """Parses Objective-C @interface and @implementation into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__("objc")

    def parse(self, source_code: str) -> UniversalModule:
        module = UniversalModule(name="objc_module", source_language="objc")

        # 1. Imports
        for match in re.finditer(r'#import\s+[<"]([^>"]+)[>"]', source_code):
            module.imports.append(match.group(1))

        # 2. @interface Name : SuperClass
        interface_regex = re.compile(
            r'@interface\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z_][A-Za-z0-9_]*))?(?:\s*<([^>]+)>)?\s*(.*?)\s*@end',
            re.DOTALL
        )

        classes_dict: dict[str, UniversalClass] = {}

        for match in interface_regex.finditer(source_code):
            c_name = match.group(1)
            s_name = match.group(2)
            protocols = match.group(3)
            body = match.group(4)

            u_class = UniversalClass(
                name=c_name,
                super_class=s_name.strip() if s_name else "NSObject"
            )
            if protocols:
                u_class.interfaces = [p.strip() for p in protocols.split(',')]

            # Extract @property (nonatomic, copy/strong/assign) Type *name;
            prop_regex = re.compile(
                r'@property\s*\([^)]*\)\s*([A-Za-z0-9_]+(?:\s*\*)?)\s*([A-Za-z_][A-Za-z0-9_]*);'
            )
            for p_match in prop_regex.finditer(body):
                p_type = self._parse_objc_type(p_match.group(1))
                p_name = p_match.group(2)
                u_class.fields.append(UniversalField(name=p_name, type_info=p_type))

            classes_dict[c_name] = u_class

        # 3. @implementation Name ... @end
        impl_regex = re.compile(
            r'@implementation\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*?)\s*@end',
            re.DOTALL
        )
        for match in impl_regex.finditer(source_code):
            c_name = match.group(1)
            body = match.group(2)
            u_class = classes_dict.get(c_name) or UniversalClass(name=c_name)

            # Method definitions: - (ReturnType)methodName:(ArgType)arg;
            method_regex = re.compile(
                r'([-+])\s*\(([^)]+)\)\s*([A-Za-z0-9_:]+)\s*\{([^}]+)\}',
                re.DOTALL
            )
            for m_match in method_regex.finditer(body):
                is_static = (m_match.group(1) == '+')
                ret_type = self._parse_objc_type(m_match.group(2))
                sig = m_match.group(3).strip()
                m_body = m_match.group(4)

                m_name = sig.split(':')[0] if ':' in sig else sig
                u_method = UniversalMethod(
                    name=m_name,
                    return_type=ret_type,
                    is_static=is_static
                )
                
                # Extract basic statements
                for line in m_body.splitlines():
                    line_str = line.strip()
                    if line_str.startswith('return ') and line_str.endswith(';'):
                        u_method.body.append(ReturnStmt(value=LiteralExpr(line_str[7:-1].strip())))
                    elif line_str and not line_str.startswith('//'):
                        u_method.body.append(RawSnippetStmt(code=line_str))

                u_class.methods.append(u_method)
            classes_dict[c_name] = u_class

        module.classes = list(classes_dict.values())
        return module

    def _parse_objc_type(self, raw: str) -> UniversalType:
        s = raw.replace('*', '').strip()
        if s in ('NSString',):
            return UniversalType.string_type()
        if s in ('NSInteger', 'long', 'int64_t'):
            return UniversalType.int64()
        if s in ('int', 'int32_t'):
            return UniversalType.primitive('i32')
        if s in ('double', 'CGFloat', 'float'):
            return UniversalType.float64()
        if s in ('BOOL', 'bool'):
            return UniversalType.boolean()
        if s in ('void',):
            return UniversalType.void()
        if s in ('NSArray',):
            return UniversalType.list_of(UniversalType.custom("id"))
        if s in ('NSDictionary',):
            return UniversalType.map_of(UniversalType.string_type(), UniversalType.custom("id"))
        return UniversalType.custom(s)
