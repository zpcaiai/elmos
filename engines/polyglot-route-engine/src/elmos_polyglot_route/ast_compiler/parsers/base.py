"""Base class and common helpers for multi-language AST parsers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from ..ir import (
    BinaryExpr,
    BinaryOperator,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    LiteralExpr,
    MethodCallExpr,
    PrimitiveKind,
    RawSnippetExpr,
    RawSnippetStmt,
    ReturnStmt,
    ThrowStmt,
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


class BaseAstParser(ABC):
    """Abstract base class for source code parsers producing Universal AST IR."""

    def __init__(self, language: str) -> None:
        self.language = language

    @abstractmethod
    def parse(self, source_code: str) -> UniversalModule:
        """Parse raw source code into a UniversalModule."""
        pass

    def parse_type(self, raw_type: str) -> UniversalType:
        """Normalize language-specific type string into UniversalType."""
        t = raw_type.strip()
        if not t or t in ('void', 'None', 'unit', '()'):
            return UniversalType.void()
        
        # Strip nullable markers
        is_nullable = False
        if t.endswith('?') or t.startswith('Optional[') or t.startswith('Nullable<'):
            is_nullable = True
            if t.endswith('?'):
                t = t[:-1].strip()
            elif t.startswith('Optional['):
                t = t[9:-1].strip()
            elif t.startswith('Nullable<'):
                t = t[9:-1].strip()

        # Primitives
        lower = t.lower()
        if lower in ('string', 'str', 'nsstring *', 'nsstring', 'char*'):
            return UniversalType(kind='primitive', name='string', is_nullable=is_nullable, is_reference=True)
        if lower in ('int', 'integer', 'long', 'long long', 'i32', 'i64', 'int64', 'isize'):
            return UniversalType(kind='primitive', name='i64', is_nullable=is_nullable, is_reference=False)
        if lower in ('short', 'i16', 'int16'):
            return UniversalType(kind='primitive', name='i16', is_nullable=is_nullable, is_reference=False)
        if lower in ('byte', 'i8', 'int8', 'u8', 'uint8'):
            return UniversalType(kind='primitive', name='i8', is_nullable=is_nullable, is_reference=False)
        if lower in ('uint', 'u32', 'uint32', 'u64', 'uint64', 'usize'):
            return UniversalType(kind='primitive', name='u64', is_nullable=is_nullable, is_reference=False)
        if lower in ('float', 'double', 'f32', 'f64', 'float64', 'float32', 'number'):
            return UniversalType(kind='primitive', name='f64', is_nullable=is_nullable, is_reference=False)
        if lower in ('bool', 'boolean'):
            return UniversalType(kind='primitive', name='bool', is_nullable=is_nullable, is_reference=False)
        if lower in ('any', 'object', 'interface{}', 'anyobject', 'unknown'):
            return UniversalType(kind='primitive', name='any', is_nullable=True, is_reference=True)

        # Generic collections: List<T>, Vec<T>, []T
        if t.startswith('[]'):
            elem = self.parse_type(t[2:])
            return UniversalType.list_of(elem)
        if re.match(r'^(List|ArrayList|Vec|Array|Sequence|Iterable)<(.+)>$', t):
            match = re.match(r'^(List|ArrayList|Vec|Array|Sequence|Iterable)<(.+)>$', t)
            elem = self.parse_type(match.group(2))
            return UniversalType.list_of(elem)
        if re.match(r'^(Map|HashMap|Dictionary|dict)<(.+?),\s*(.+?)>$', t):
            match = re.match(r'^(Map|HashMap|Dictionary|dict)<(.+?),\s*(.+?)>$', t)
            k = self.parse_type(match.group(2))
            v = self.parse_type(match.group(3))
            return UniversalType.map_of(k, v)
        if t.startswith('map[') and ']' in t:
            close = t.index(']')
            k = self.parse_type(t[4:close])
            v = self.parse_type(t[close+1:])
            return UniversalType.map_of(k, v)
        if re.match(r'^(Set|HashSet)<(.+)>$', t):
            match = re.match(r'^(Set|HashSet)<(.+)>$', t)
            elem = self.parse_type(match.group(2))
            return UniversalType.set_of(elem)

        # Async wrappers: Task<T>, Promise<T>, CompletableFuture<T>, Deferred<T>
        if re.match(r'^(Task|Promise|CompletableFuture|Deferred|Future)<(.+)>$', t):
            match = re.match(r'^(Task|Promise|CompletableFuture|Deferred|Future)<(.+)>$', t)
            inner = self.parse_type(match.group(2))
            res = UniversalType.custom(t)
            res.element_type = inner
            return res

        # Result wrappers: Result<T, E>
        if re.match(r'^Result<(.+?),\s*(.+?)>$', t):
            match = re.match(r'^Result<(.+?),\s*(.+?)>$', t)
            ok_type = self.parse_type(match.group(1))
            err_type = self.parse_type(match.group(2))
            return UniversalType.result_of(ok_type, err_type)

        return UniversalType(kind='custom', name=t, is_nullable=is_nullable, is_reference=True)
