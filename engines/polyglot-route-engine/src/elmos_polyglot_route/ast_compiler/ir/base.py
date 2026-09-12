"""Universal AST & Semantic Intermediate Representation (Universal IR).

This module models arbitrary enterprise software constructs across the four critical hazard domains:
1. Object Graph Lifecycle: Classes, structs, interfaces, enums, fields, constructors, destructors/finalizers, inheritance.
2. Async & Concurrency: Async/await, Tasks, Promises, CompletableFutures, Coroutines, Goroutines, Channels, Locks.
3. Exception Unwinding: Try/catch/finally, throw/raise, Result<T,E>, (T, error) tuples, panic/recover.
4. Complex Framework & Web API: REST controllers, HTTP route annotations, DI/IoC bindings, DTO models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


class PrimitiveKind(str, Enum):
    I8 = 'i8'
    I16 = 'i16'
    I32 = 'i32'
    I64 = 'i64'
    U8 = 'u8'
    U16 = 'u16'
    U32 = 'u32'
    U64 = 'u64'
    F32 = 'f32'
    F64 = 'f64'
    BOOL = 'bool'
    CHAR = 'char'
    STRING = 'string'
    VOID = 'void'
    ANY = 'any'


@dataclass
class UniversalType:
    kind: str  # primitive, list, map, set, tuple, optional, result, custom, generic
    name: str = ''
    element_type: UniversalType | None = None
    key_type: UniversalType | None = None
    value_type: UniversalType | None = None
    type_args: list[UniversalType] = field(default_factory=list)
    is_nullable: bool = False
    is_reference: bool = True
    pointer_kind: str | None = None  # None, 'raw', 'unique', 'shared', 'weak', 'strong'

    @classmethod
    def primitive(cls, kind: PrimitiveKind | str) -> UniversalType:
        val = kind.value if hasattr(kind, "value") else str(kind)
        return cls(kind="primitive", name=val, is_reference=False)

    @classmethod
    def string_type(cls) -> UniversalType:
        return cls(kind='primitive', name='string', is_reference=True)

    @classmethod
    def int64(cls) -> UniversalType:
        return cls(kind='primitive', name='i64', is_reference=False)

    @classmethod
    def float64(cls) -> UniversalType:
        return cls(kind='primitive', name='f64', is_reference=False)

    @classmethod
    def boolean(cls) -> UniversalType:
        return cls(kind='primitive', name='bool', is_reference=False)

    @classmethod
    def void(cls) -> UniversalType:
        return cls(kind='primitive', name='void', is_reference=False)

    @classmethod
    def list_of(cls, elem: UniversalType) -> UniversalType:
        return cls(kind='list', name='List', element_type=elem)

    @classmethod
    def map_of(cls, key: UniversalType, val: UniversalType) -> UniversalType:
        return cls(kind='map', name='Map', key_type=key, value_type=val)

    @classmethod
    def set_of(cls, elem: UniversalType) -> UniversalType:
        return cls(kind='set', name='Set', element_type=elem)

    @classmethod
    def optional_of(cls, inner: UniversalType) -> UniversalType:
        return cls(kind='optional', name='Optional', element_type=inner, is_nullable=True)

    @classmethod
    def result_of(cls, ok_type: UniversalType, err_type: UniversalType) -> UniversalType:
        return cls(kind='result', name='Result', element_type=ok_type, value_type=err_type)

    @classmethod
    def unique_ptr_of(cls, elem: UniversalType) -> UniversalType:
        return cls(kind='pointer', name='unique_ptr', element_type=elem, pointer_kind='unique')

    @classmethod
    def shared_ptr_of(cls, elem: UniversalType) -> UniversalType:
        return cls(kind='pointer', name='shared_ptr', element_type=elem, pointer_kind='shared')

    @classmethod
    def arc_strong(cls, elem: UniversalType) -> UniversalType:
        return cls(kind='pointer', name='arc_strong', element_type=elem, pointer_kind='strong')

    @classmethod
    def custom(cls, name: str) -> UniversalType:
        return cls(kind='custom', name=name)


class BinaryOperator(str, Enum):
    ADD = '+'
    SUB = '-'
    MUL = '*'
    DIV = '/'
    MOD = '%'
    EQ = '=='
    NE = '!='
    LT = '<'
    LE = '<='
    GT = '>'
    GE = '>='
    AND = '&&'
    OR = '||'
    BIT_AND = '&'
    BIT_OR = '|'
    BIT_XOR = '^'


class UnaryOperator(str, Enum):
    NEG = '-'
    NOT = '!'
    BIT_NOT = '~'


# AST Expressions
class UniversalExpr:
    pass


@dataclass
class LiteralExpr(UniversalExpr):
    value: Any
    type_kind: str = 'string'  # int, float, bool, string, null


@dataclass
class IdentifierExpr(UniversalExpr):
    name: str


@dataclass
class FieldAccessExpr(UniversalExpr):
    target: UniversalExpr
    field_name: str


@dataclass
class MethodCallExpr(UniversalExpr):
    target: UniversalExpr | None  # None if top-level function or this
    method_name: str
    args: list[UniversalExpr] = field(default_factory=list)


@dataclass
class BinaryExpr(UniversalExpr):
    left: UniversalExpr
    op: BinaryOperator
    right: UniversalExpr


@dataclass
class UnaryExpr(UniversalExpr):
    op: UnaryOperator
    operand: UniversalExpr


@dataclass
class ConstructExpr(UniversalExpr):
    class_name: str
    args: list[UniversalExpr] = field(default_factory=list)
    keyword_args: dict[str, UniversalExpr] = field(default_factory=dict)


@dataclass
class AwaitExpr(UniversalExpr):
    inner: UniversalExpr


@dataclass
class CastExpr(UniversalExpr):
    target_type: UniversalType
    inner: UniversalExpr


@dataclass
class RawSnippetExpr(UniversalExpr):
    code: str


# AST Statements
class UniversalStmt:
    pass


@dataclass
class VarDeclStmt(UniversalStmt):
    name: str
    type_info: UniversalType
    initial_value: UniversalExpr | None = None
    is_constant: bool = False


@dataclass
class AssignStmt(UniversalStmt):
    target: UniversalExpr
    value: UniversalExpr


@dataclass
class ReturnStmt(UniversalStmt):
    value: UniversalExpr | None = None


@dataclass
class ThrowStmt(UniversalStmt):
    exception_class: str
    message: str
    cause_expr: UniversalExpr | None = None


@dataclass
class CatchClause:
    exception_type: str
    variable_name: str
    body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class TryCatchFinallyStmt(UniversalStmt):
    try_body: list[UniversalStmt] = field(default_factory=list)
    catch_clauses: list[CatchClause] = field(default_factory=list)
    finally_body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class IfElseStmt(UniversalStmt):
    condition: UniversalExpr
    then_body: list[UniversalStmt] = field(default_factory=list)
    else_body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class WhileStmt(UniversalStmt):
    condition: UniversalExpr
    body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class ForLoopStmt(UniversalStmt):
    init_stmt: UniversalStmt | None
    condition: UniversalExpr | None
    update_stmt: UniversalStmt | None
    body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class ForEachStmt(UniversalStmt):
    item_name: str
    item_type: UniversalType
    iterable: UniversalExpr
    body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class ExprStmt(UniversalStmt):
    expr: UniversalExpr


@dataclass
class BreakStmt(UniversalStmt):
    pass


@dataclass
class ContinueStmt(UniversalStmt):
    pass


@dataclass
class AwaitStmt(UniversalStmt):
    expr: UniversalExpr


@dataclass
class LockStmt(UniversalStmt):
    lock_expr: UniversalExpr
    body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class SpawnStmt(UniversalStmt):
    """Launch a concurrent unit (goroutine / thread / task / executor job)."""

    body: list[UniversalStmt] = field(default_factory=list)
    join_handle: str | None = None


@dataclass
class ChannelMakeStmt(UniversalStmt):
    name: str
    element_type: UniversalType = field(default_factory=UniversalType.int64)
    capacity: int = 1


@dataclass
class ChannelSendStmt(UniversalStmt):
    channel: str
    value: UniversalExpr


@dataclass
class ChannelRecvStmt(UniversalStmt):
    channel: str
    target: str


@dataclass
class SelectArm:
    kind: str  # recv | send | default
    channel: str | None = None
    value: UniversalExpr | None = None
    target: str | None = None
    body: list[UniversalStmt] = field(default_factory=list)


@dataclass
class SelectStmt(UniversalStmt):
    arms: list[SelectArm] = field(default_factory=list)


@dataclass
class IoReadStmt(UniversalStmt):
    path: UniversalExpr
    target: str
    binary: bool = False


@dataclass
class IoWriteStmt(UniversalStmt):
    path: UniversalExpr
    value: UniversalExpr
    binary: bool = False


@dataclass
class MoveStmt(UniversalStmt):
    source: str
    target: str


@dataclass
class DropStmt(UniversalStmt):
    name: str
    kind: str = "owned"


@dataclass
class JoinStmt(UniversalStmt):
    handle: str


@dataclass
class RawSnippetStmt(UniversalStmt):
    code: str


# AST Annotations / Attributes
@dataclass
class UniversalAnnotation:
    name: str  # Controller, Route, Get, Post, Put, Delete, Body, Param, Inject
    args: list[str] = field(default_factory=list)
    kwargs: dict[str, str] = field(default_factory=dict)


# AST Declarations
@dataclass
class UniversalParam:
    name: str
    type_info: UniversalType
    default_value: UniversalExpr | None = None
    annotations: list[UniversalAnnotation] = field(default_factory=list)
    is_variadic: bool = False


@dataclass
class UniversalField:
    name: str
    type_info: UniversalType
    visibility: str = 'public'  # public, private, protected
    is_static: bool = False
    is_readonly: bool = False
    default_value: UniversalExpr | None = None
    annotations: list[UniversalAnnotation] = field(default_factory=list)


@dataclass
class UniversalMethod:
    name: str
    params: list[UniversalParam] = field(default_factory=list)
    return_type: UniversalType = field(default_factory=UniversalType.void)
    visibility: str = 'public'
    is_static: bool = False
    is_async: bool = False
    is_abstract: bool = False
    throws_exceptions: list[str] = field(default_factory=list)
    body: list[UniversalStmt] = field(default_factory=list)
    annotations: list[UniversalAnnotation] = field(default_factory=list)
    has_exception_handling: bool = False
    # Web API Metadata
    http_method: str | None = None  # GET, POST, PUT, DELETE, PATCH
    http_path: str | None = None


@dataclass
class UniversalConstructor:
    params: list[UniversalParam] = field(default_factory=list)
    body: list[UniversalStmt] = field(default_factory=list)
    visibility: str = 'public'


@dataclass
class UniversalClass:
    name: str
    super_class: str | None = None
    interfaces: list[str] = field(default_factory=list)
    fields: list[UniversalField] = field(default_factory=list)
    constructors: list[UniversalConstructor] = field(default_factory=list)
    methods: list[UniversalMethod] = field(default_factory=list)
    annotations: list[UniversalAnnotation] = field(default_factory=list)
    is_controller: bool = False
    base_route: str | None = None
    is_struct: bool = False
    is_interface: bool = False


# UI Declarations for React, Flutter, VB6 Form, etc.
@dataclass
class UIEventBinding:
    event_name: str  # onClick, onPressed, onChange, Form_Load, Command1_Click
    handler_method_name: str
    inline_statements: list[UniversalStmt] = field(default_factory=list)


@dataclass
class UIViewNode:
    tag: str  # Button, Text, Container, Column, Row, TextField, Form
    props: dict[str, UniversalExpr] = field(default_factory=dict)
    events: list[UIEventBinding] = field(default_factory=list)
    children: list[UIViewNode] = field(default_factory=list)
    text_content: str | None = None


@dataclass
class UIStateVar:
    name: str
    type_info: UniversalType
    initial_value: UniversalExpr | None = None


@dataclass
class UIComponentDecl:
    name: str
    props: list[UniversalParam] = field(default_factory=list)
    state_vars: list[UIStateVar] = field(default_factory=list)
    methods: list[UniversalMethod] = field(default_factory=list)
    root_view: UIViewNode | None = None
    lifecycle_hooks: dict[str, list[UniversalStmt]] = field(default_factory=dict)  # on_mount, on_update, on_destroy
    is_stateful: bool = True


@dataclass
class UniversalModule:
    name: str
    package_name: str = ''
    source_language: str = ''
    imports: list[str] = field(default_factory=list)
    classes: list[UniversalClass] = field(default_factory=list)
    free_functions: list[UniversalMethod] = field(default_factory=list)
    ui_components: list[UIComponentDecl] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

