"""Semantic IR compiler for a deliberately narrow, explicitly declared Python subset.

This is the component in a system like this that is most often over-claimed, so the
honesty mechanism *is* the feature: the subset is enumerated in :data:`SUBSET`, every
construct outside it is refused with a stable code (never approximated, never silently
dropped), and every compile returns an :class:`Admission` summary — how many top-level
units were admitted, how many refused, and the reason histogram — so a caller can
*measure* the subset instead of believing a paragraph of prose about it.

The subset is chosen so that an admitted function is **pure and total**: it reads only
its parameters and its own block-scoped ``let`` bindings, it has no side effects, and it
cannot raise.  That is why ``//`` and ``%`` are refused (``ZeroDivisionError`` makes them
partial) and why recursion is refused (a call may only target a function already admitted
earlier in the same unit, which makes the call graph acyclic by construction).  A subset
that could raise would make "the IR means the same thing as the source" untestable by the
round-trip grid that guards this module.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import (
    Status,
    digest,
    reject_unknown_fields,
    require_bool,
    require_mapping,
    require_str,
)
from .errors import Category, KernelError, register_codes
from .registry import register

__all__ = [
    "IR_VERSION",
    "SUBSET",
    "IrType",
    "Literal",
    "Name",
    "Unary",
    "Binary",
    "Compare",
    "BoolOp",
    "Call",
    "Let",
    "Return",
    "If",
    "IrParam",
    "IrFunction",
    "SemanticIr",
    "Rejection",
    "Admission",
    "compile_unit",
    "emit_python",
    "handle",
]

register_codes(
    Category.SEMANTIC,
    "IR_SOURCE_UNPARSEABLE",
    "IR_UNSUPPORTED_STATEMENT",
    "IR_UNSUPPORTED_EXPRESSION",
    "IR_UNSUPPORTED_TYPE",
    "IR_UNSUPPORTED_SIGNATURE",
    "IR_MISSING_ANNOTATION",
    "IR_MISSING_RETURN",
    "IR_UNRESOLVED_CALL",
    "IR_UNBOUND_NAME",
    "IR_TYPE_MISMATCH",
    "IR_REBINDING_FORBIDDEN",
    "IR_UNREACHABLE_STATEMENT",
    "IR_ARITY_MISMATCH",
    # Codes named by skills/semantic-ir-compiler/SKILL.md.
    "IR_UNREPRESENTABLE",
    "SEMANTIC_GAP",
    "SOURCE_MAP_INCOMPLETE",
    "TARGET_PROFILE_UNSUPPORTED",
)

#: Version of the IR shape *and* of the admitted subset.  Both move together: widening
#: the subset changes what an IR of a given version is allowed to contain, so a consumer
#: that pinned a version is not silently handed constructs it cannot lower.
IR_VERSION = "semir/1.0.0-python-pure-total"

#: The admitted subset, as data.  Tests assert against this, callers can render it, and a
#: construct absent from here is refused rather than approximated.
SUBSET: Mapping[str, Any] = {
    "language": "python",
    "irVersion": IR_VERSION,
    "unit": "a module whose every top-level statement is a plain function definition",
    "types": ("int", "bool", "str"),
    "signature": (
        "every parameter annotated, return annotated, no defaults, no *args/**kwargs, "
        "no positional-only or keyword-only parameters, no decorators, not async"
    ),
    "statements": ("let (annotated single assignment)", "if/elif/else", "return"),
    "expressions": (
        "int/bool/str literal",
        "parameter or let reference",
        "unary minus on int",
        "not on bool",
        "+ - * on int",
        "== != on two operands of one type",
        "< <= > >= on int",
        "and/or on bool",
        "call to a function admitted earlier in the same unit",
    ),
    "totality": (
        "admitted functions cannot raise: // and % are excluded (ZeroDivisionError), "
        "** is excluded (float results), recursion is excluded (no termination proof)"
    ),
    "purity": "no globals, no imports, no attributes, no mutation, no I/O",
    "excluded": (
        "for", "while", "with", "try", "assert", "raise", "del", "global", "nonlocal",
        "lambda", "comprehension", "f-string", "ternary if-expression", "docstring",
        "chained comparison", "is/in", "attribute access", "subscript", "None", "float",
        "class", "import", "module-level statement",
    ),
}


class IrType(StrEnum):
    """The three value types the IR can represent.

    ``bool`` is kept disjoint from ``int`` even though Python makes it a subclass: the IR
    performs no implicit widening, so ``not 1`` and ``-True`` are refused rather than
    quietly given a meaning the target language may not share.
    """

    INT = "int"
    BOOL = "bool"
    STR = "str"


_ANNOTATIONS: Mapping[str, IrType] = {"int": IrType.INT, "bool": IrType.BOOL, "str": IrType.STR}
_BINARY_OPS: Mapping[type[ast.operator], str] = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul"}
_BINARY_TOKENS: Mapping[str, str] = {"add": "+", "sub": "-", "mul": "*"}
_COMPARE_OPS: Mapping[type[ast.cmpop], str] = {
    ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le", ast.Gt: "gt", ast.GtE: "ge",
}
_COMPARE_TOKENS: Mapping[str, str] = {
    "eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">=",
}
_ORDERED_ONLY = frozenset({"lt", "le", "gt", "ge"})


# --- expressions -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Literal:
    """An ``int``, ``bool`` or ``str`` constant."""

    type: IrType
    value: int | bool | str

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "literal", "type": str(self.type), "value": self.value}


@dataclass(frozen=True, slots=True)
class Name:
    """A reference to a parameter or to a ``let`` binding visible in this block."""

    name: str
    type: IrType

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "name", "type": str(self.type), "name": self.name}


@dataclass(frozen=True, slots=True)
class Unary:
    """``-x`` on an int, or ``not x`` on a bool."""

    op: str
    operand: Expr
    type: IrType

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "unary", "type": str(self.type), "op": self.op,
                "operand": self.operand.to_payload()}


@dataclass(frozen=True, slots=True)
class Binary:
    """``+``, ``-`` or ``*`` on two ints.

    Division and modulo are absent on purpose; see :data:`SUBSET`.
    """

    op: str
    left: Expr
    right: Expr
    type: IrType

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "binary", "type": str(self.type), "op": self.op,
                "left": self.left.to_payload(), "right": self.right.to_payload()}


@dataclass(frozen=True, slots=True)
class Compare:
    """A single, unchained comparison yielding a bool."""

    op: str
    left: Expr
    right: Expr
    type: IrType = IrType.BOOL

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "compare", "type": str(self.type), "op": self.op,
                "left": self.left.to_payload(), "right": self.right.to_payload()}


@dataclass(frozen=True, slots=True)
class BoolOp:
    """``and`` / ``or`` over two or more bool operands."""

    op: str
    values: tuple[Expr, ...]
    type: IrType = IrType.BOOL

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "boolop", "type": str(self.type), "op": self.op,
                "values": [value.to_payload() for value in self.values]}


@dataclass(frozen=True, slots=True)
class Call:
    """A call to a function admitted earlier in the same unit."""

    func: str
    args: tuple[Expr, ...]
    type: IrType

    def to_payload(self) -> dict[str, Any]:
        return {"kind": "call", "type": str(self.type), "func": self.func,
                "args": [arg.to_payload() for arg in self.args]}


Expr = Literal | Name | Unary | Binary | Compare | BoolOp | Call


# --- statements --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Let:
    """A single, annotated, block-scoped binding.

    ``let`` exists because without it the subset is uselessly small: any function that
    names an intermediate value would have to be refused, or the compiler would have to
    inline the intermediate at every use site.  Inlining is safe *semantically* here (the
    subset is pure and total, so duplicating an expression cannot change the answer), but
    it costs the two things this module is built to protect — the emitted source stops
    corresponding 1:1 to the original, and the source map degrades from "this node came
    from that line" to "this node came from several lines at once".

    The price of keeping it: ``let`` is the only construct that makes statement order
    meaningful (everything else in the subset is order-free), so the IR needs an
    environment, block scoping and a rebinding rule.  Rebinding is refused outright —
    ``x`` names one value for the whole block, which keeps every expression node's type
    decidable from its position alone.
    """

    node_id: str
    name: str
    type: IrType
    value: Expr

    def to_node(self) -> dict[str, Any]:
        return {"id": self.node_id, "kind": "let", "name": self.name,
                "type": str(self.type), "value": self.value.to_payload()}


@dataclass(frozen=True, slots=True)
class Return:
    """A return whose expression type equals the declared return type."""

    node_id: str
    value: Expr

    def to_node(self) -> dict[str, Any]:
        return {"id": self.node_id, "kind": "return", "value": self.value.to_payload()}


@dataclass(frozen=True, slots=True)
class If:
    """A total two-way branch: both arms must terminate, so ``else`` is mandatory."""

    node_id: str
    test: Expr
    then: tuple[Stmt, ...]
    orelse: tuple[Stmt, ...]

    def to_node(self) -> dict[str, Any]:
        return {"id": self.node_id, "kind": "if", "test": self.test.to_payload(),
                "thenIds": [stmt.node_id for stmt in self.then],
                "elseIds": [stmt.node_id for stmt in self.orelse]}


Stmt = Let | Return | If


@dataclass(frozen=True, slots=True)
class IrParam:
    """One annotated parameter."""

    name: str
    type: IrType


@dataclass(frozen=True, slots=True)
class IrFunction:
    """An admitted function: pure, total, fully annotated, every path returning."""

    node_id: str
    name: str
    params: tuple[IrParam, ...]
    return_type: IrType
    body: tuple[Stmt, ...]

    def to_node(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": "function",
            "name": self.name,
            "params": [{"name": p.name, "type": str(p.type)} for p in self.params],
            "returnType": str(self.return_type),
            "bodyIds": [stmt.node_id for stmt in self.body],
        }


# --- rejections & admission --------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rejection:
    """One refused top-level unit, with the stable reason and where it was.

    A rejection is a first-class output, not a log line.  The defect this design exists to
    prevent is a statement the compiler did not understand being dropped from the IR while
    the enclosing function is still emitted as if it had been fully translated.
    """

    symbol: str
    code: str
    message: str
    line: int
    column: int

    def to_payload(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "code": self.code, "message": self.message,
                "line": self.line, "column": self.column}


@dataclass(frozen=True, slots=True)
class Admission:
    """How much of the unit the subset actually covered.

    ``admittedPerMille`` is ``None`` with ``measured: false`` for an empty unit.  Zero
    units admitted out of zero is not a coverage of 0 % — it is no measurement at all, and
    the two must not render identically.
    """

    total_units: int
    admitted_units: int
    rejected_units: int
    reason_histogram: tuple[tuple[str, int], ...]

    def to_payload(self) -> dict[str, Any]:
        measured = self.total_units > 0
        return {
            "totalUnits": self.total_units,
            "admittedUnits": self.admitted_units,
            "rejectedUnits": self.rejected_units,
            "reasonHistogram": [{"code": code, "count": count}
                                for code, count in self.reason_histogram],
            "admittedPerMille": (
                (self.admitted_units * 1000) // self.total_units if measured else None
            ),
            "measured": measured,
        }


# --- the IR ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SemanticIr:
    """A compiled unit.

    :meth:`structural_digest` deliberately excludes the source map and the source hash.
    Round-trip stability is a claim about *meaning*, not about byte offsets: re-compiling
    :func:`emit_python` output must reproduce the same nodes and edges even though it came
    from different text at different line numbers.
    """

    ir_version: str
    unit_id: str
    source_sha: str
    functions: tuple[IrFunction, ...]
    positions: tuple[tuple[str, tuple[int, int, int]], ...] = ()

    @property
    def ir_id(self) -> str:
        return f"{self.unit_id}:{self.structural_digest[7:19]}"

    def nodes(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for function in self.functions:
            out.append(function.to_node())
            for stmt in function.body:
                _collect_nodes(stmt, out)
        return out

    def edges(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for function in self.functions:
            for stmt in function.body:
                out.append({"from": function.node_id, "to": stmt.node_id, "kind": "contains"})
                _collect_edges(stmt, out)
            for callee in sorted(_calls_in_function(function)):
                out.append({"from": function.node_id, "to": f"fn:{callee}", "kind": "calls"})
        return out

    def source_map(self) -> dict[str, Any]:
        """Node id -> source position.

        Positions live here rather than inside the nodes so that two IRs with the same
        meaning compare equal regardless of the line numbers they came from.
        """

        return {
            "unitId": self.unit_id,
            "positions": {
                node_id: {"line": line, "column": column, "endLine": end_line}
                for node_id, (line, column, end_line) in self.positions
            },
        }

    def structural_payload(self) -> dict[str, Any]:
        return {"irVersion": self.ir_version, "nodes": self.nodes(), "edges": self.edges()}

    @property
    def structural_digest(self) -> str:
        return digest(self.structural_payload())

    def to_payload(self, *, semantic_gaps: Sequence[Rejection] = ()) -> dict[str, Any]:
        """Render the ``contracts/schemas/semantic-ir.schema.json`` shape."""

        return {
            "irId": self.ir_id,
            "version": self.ir_version,
            "sourceSnapshotSha": self.source_sha,
            "nodes": self.nodes(),
            "edges": self.edges(),
            "semanticGaps": [gap.to_payload() for gap in semantic_gaps],
            "sourceMap": self.source_map(),
            "structuralDigest": self.structural_digest,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def _collect_nodes(stmt: Stmt, out: list[dict[str, Any]]) -> None:
    out.append(stmt.to_node())
    if isinstance(stmt, If):
        for child in (*stmt.then, *stmt.orelse):
            _collect_nodes(child, out)


def _collect_edges(stmt: Stmt, out: list[dict[str, Any]]) -> None:
    if isinstance(stmt, If):
        for child in stmt.then:
            out.append({"from": stmt.node_id, "to": child.node_id, "kind": "then"})
            _collect_edges(child, out)
        for child in stmt.orelse:
            out.append({"from": stmt.node_id, "to": child.node_id, "kind": "else"})
            _collect_edges(child, out)


def _calls_in_expr(expr: Expr, into: set[str]) -> None:
    if isinstance(expr, Call):
        into.add(expr.func)
        for arg in expr.args:
            _calls_in_expr(arg, into)
    elif isinstance(expr, Unary):
        _calls_in_expr(expr.operand, into)
    elif isinstance(expr, (Binary, Compare)):
        _calls_in_expr(expr.left, into)
        _calls_in_expr(expr.right, into)
    elif isinstance(expr, BoolOp):
        for value in expr.values:
            _calls_in_expr(value, into)


def _calls_in_stmt(stmt: Stmt, into: set[str]) -> None:
    if isinstance(stmt, Let):
        _calls_in_expr(stmt.value, into)
    elif isinstance(stmt, Return):
        _calls_in_expr(stmt.value, into)
    else:
        _calls_in_expr(stmt.test, into)
        for child in (*stmt.then, *stmt.orelse):
            _calls_in_stmt(child, into)


def _calls_in_function(function: IrFunction) -> set[str]:
    into: set[str] = set()
    for stmt in function.body:
        _calls_in_stmt(stmt, into)
    return into


# --- compilation -------------------------------------------------------------


class _Refused(Exception):
    """Internal control flow: one unit is outside the subset."""

    def __init__(self, code: str, message: str, node: ast.AST) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = getattr(node, "lineno", 0)
        self.column = getattr(node, "col_offset", 0)


def _refuse(code: str, message: str, node: ast.AST) -> _Refused:
    return _Refused(code, message, node)


class _UnitCompiler:
    """Compiles one function against the functions already admitted before it."""

    def __init__(self, admitted: Mapping[str, IrFunction]) -> None:
        self._admitted = admitted
        self.positions: dict[str, tuple[int, int, int]] = {}

    def compile_function(self, node: ast.FunctionDef) -> IrFunction:
        self._check_signature(node)
        params: list[IrParam] = []
        scope: dict[str, IrType] = {}
        for arg in node.args.args:
            if arg.annotation is None:
                raise _refuse("IR_MISSING_ANNOTATION",
                              f"parameter {arg.arg!r} has no type annotation", arg)
            param_type = self._annotation(arg.annotation)
            if arg.arg in scope:
                raise _refuse("IR_REBINDING_FORBIDDEN",
                              f"duplicate parameter {arg.arg!r}", arg)
            scope[arg.arg] = param_type
            params.append(IrParam(name=arg.arg, type=param_type))
        if node.returns is None:
            raise _refuse("IR_MISSING_ANNOTATION",
                          f"function {node.name!r} has no return annotation", node)
        return_type = self._annotation(node.returns)

        function_id = f"fn:{node.name}"
        self._record(function_id, node)
        body, terminates = self._block(node.body, scope, return_type, f"{function_id}/body")
        if not terminates:
            raise _refuse("IR_MISSING_RETURN",
                          f"function {node.name!r} has a path that does not return", node)
        return IrFunction(node_id=function_id, name=node.name, params=tuple(params),
                          return_type=return_type, body=body)

    # -- helpers --

    def _record(self, node_id: str, node: ast.AST) -> None:
        self.positions[node_id] = (
            getattr(node, "lineno", 0),
            getattr(node, "col_offset", 0),
            getattr(node, "end_lineno", 0) or 0,
        )

    def _check_signature(self, node: ast.FunctionDef) -> None:
        args = node.args
        if node.decorator_list:
            raise _refuse("IR_UNSUPPORTED_SIGNATURE",
                          f"function {node.name!r} is decorated", node)
        if args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg:
            raise _refuse("IR_UNSUPPORTED_SIGNATURE",
                          f"function {node.name!r} uses a parameter kind outside the subset",
                          node)
        if args.defaults or any(default is not None for default in args.kw_defaults):
            raise _refuse("IR_UNSUPPORTED_SIGNATURE",
                          f"function {node.name!r} has default arguments", node)

    def _annotation(self, node: ast.expr) -> IrType:
        if isinstance(node, ast.Name) and node.id in _ANNOTATIONS:
            return _ANNOTATIONS[node.id]
        rendered = ast.dump(node) if not isinstance(node, ast.Name) else node.id
        raise _refuse("IR_UNSUPPORTED_TYPE",
                      f"type annotation {rendered} is outside the subset {('int', 'bool', 'str')}",
                      node)

    def _block(self, stmts: Sequence[ast.stmt], scope: Mapping[str, IrType],
               return_type: IrType, prefix: str) -> tuple[tuple[Stmt, ...], bool]:
        local: dict[str, IrType] = dict(scope)
        out: list[Stmt] = []
        terminates = False
        for index, stmt in enumerate(stmts):
            if terminates:
                raise _refuse("IR_UNREACHABLE_STATEMENT",
                              "statement follows a statement that always returns", stmt)
            node_id = f"{prefix}/{index}"
            self._record(node_id, stmt)
            if isinstance(stmt, ast.Return):
                if stmt.value is None:
                    raise _refuse("IR_UNSUPPORTED_TYPE",
                                  "bare return yields None, which the subset cannot type", stmt)
                value = self._expr(stmt.value, local)
                if value.type is not return_type:
                    raise _refuse("IR_TYPE_MISMATCH",
                                  f"returns {value.type} where {return_type} is declared", stmt)
                out.append(Return(node_id=node_id, value=value))
                terminates = True
            elif isinstance(stmt, ast.AnnAssign):
                out.append(self._let(stmt, local, node_id))
            elif isinstance(stmt, ast.If):
                branch, branch_terminates = self._if(stmt, local, return_type, node_id)
                out.append(branch)
                terminates = branch_terminates
            elif isinstance(stmt, ast.Assign):
                raise _refuse("IR_MISSING_ANNOTATION",
                              "assignment without a type annotation", stmt)
            else:
                raise _refuse("IR_UNSUPPORTED_STATEMENT",
                              f"{type(stmt).__name__} is outside the subset", stmt)
        return tuple(out), terminates

    def _let(self, stmt: ast.AnnAssign, local: dict[str, IrType], node_id: str) -> Let:
        if stmt.value is None:
            raise _refuse("IR_UNSUPPORTED_STATEMENT",
                          "annotation without a value binds nothing", stmt)
        if not isinstance(stmt.target, ast.Name):
            raise _refuse("IR_UNSUPPORTED_STATEMENT",
                          "only a plain name can be bound", stmt)
        name = stmt.target.id
        if name in local:
            raise _refuse("IR_REBINDING_FORBIDDEN",
                          f"{name!r} is already bound in this scope", stmt)
        declared = self._annotation(stmt.annotation)
        value = self._expr(stmt.value, local)
        if value.type is not declared:
            raise _refuse("IR_TYPE_MISMATCH",
                          f"{name!r} is annotated {declared} but bound to {value.type}", stmt)
        local[name] = declared
        return Let(node_id=node_id, name=name, type=declared, value=value)

    def _if(self, stmt: ast.If, local: Mapping[str, IrType], return_type: IrType,
            node_id: str) -> tuple[If, bool]:
        test = self._expr(stmt.test, local)
        if test.type is not IrType.BOOL:
            raise _refuse("IR_TYPE_MISMATCH",
                          f"if test is {test.type}; the subset requires bool "
                          "(no truthiness coercion)", stmt)
        if not stmt.orelse:
            raise _refuse("IR_MISSING_RETURN",
                          "if without else leaves a path that does not return", stmt)
        then, then_terminates = self._block(stmt.body, local, return_type, f"{node_id}/then")
        orelse, else_terminates = self._block(stmt.orelse, local, return_type, f"{node_id}/else")
        branch = If(node_id=node_id, test=test, then=then, orelse=orelse)
        return branch, then_terminates and else_terminates

    def _expr(self, node: ast.expr, scope: Mapping[str, IrType]) -> Expr:
        if isinstance(node, ast.Constant):
            return self._literal(node)
        if isinstance(node, ast.Name):
            declared = scope.get(node.id)
            if declared is None:
                raise _refuse("IR_UNBOUND_NAME",
                              f"{node.id!r} is not a parameter or a let binding in scope "
                              "(the subset has no globals)", node)
            return Name(name=node.id, type=declared)
        if isinstance(node, ast.UnaryOp):
            return self._unary(node, scope)
        if isinstance(node, ast.BinOp):
            return self._binary(node, scope)
        if isinstance(node, ast.Compare):
            return self._compare(node, scope)
        if isinstance(node, ast.BoolOp):
            return self._boolop(node, scope)
        if isinstance(node, ast.Call):
            return self._call(node, scope)
        raise _refuse("IR_UNSUPPORTED_EXPRESSION",
                      f"{type(node).__name__} is outside the subset", node)

    def _literal(self, node: ast.Constant) -> Literal:
        value = node.value
        if isinstance(value, bool):
            return Literal(type=IrType.BOOL, value=value)
        if isinstance(value, int):
            return Literal(type=IrType.INT, value=value)
        if isinstance(value, str):
            return Literal(type=IrType.STR, value=value)
        raise _refuse("IR_UNSUPPORTED_TYPE",
                      f"literal of type {type(value).__name__} is outside the subset", node)

    def _unary(self, node: ast.UnaryOp, scope: Mapping[str, IrType]) -> Unary:
        operand = self._expr(node.operand, scope)
        if isinstance(node.op, ast.USub):
            if operand.type is not IrType.INT:
                raise _refuse("IR_UNSUPPORTED_TYPE",
                              f"unary minus on {operand.type} is outside the subset", node)
            return Unary(op="neg", operand=operand, type=IrType.INT)
        if isinstance(node.op, ast.Not):
            if operand.type is not IrType.BOOL:
                raise _refuse("IR_UNSUPPORTED_TYPE",
                              f"not on {operand.type} would rely on truthiness", node)
            return Unary(op="not", operand=operand, type=IrType.BOOL)
        raise _refuse("IR_UNSUPPORTED_EXPRESSION",
                      f"unary {type(node.op).__name__} is outside the subset", node)

    def _binary(self, node: ast.BinOp, scope: Mapping[str, IrType]) -> Binary:
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise _refuse("IR_UNSUPPORTED_EXPRESSION",
                          f"binary {type(node.op).__name__} is outside the subset "
                          "(// and % are partial, ** is not int-closed)", node)
        left = self._expr(node.left, scope)
        right = self._expr(node.right, scope)
        if left.type is not IrType.INT or right.type is not IrType.INT:
            raise _refuse("IR_UNSUPPORTED_TYPE",
                          f"arithmetic on ({left.type}, {right.type}) is outside the subset; "
                          "only int arithmetic is admitted", node)
        return Binary(op=op, left=left, right=right, type=IrType.INT)

    def _compare(self, node: ast.Compare, scope: Mapping[str, IrType]) -> Compare:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise _refuse("IR_UNSUPPORTED_EXPRESSION",
                          "chained comparison is outside the subset", node)
        op = _COMPARE_OPS.get(type(node.ops[0]))
        if op is None:
            raise _refuse("IR_UNSUPPORTED_EXPRESSION",
                          f"comparison {type(node.ops[0]).__name__} is outside the subset", node)
        left = self._expr(node.left, scope)
        right = self._expr(node.comparators[0], scope)
        if left.type is not right.type:
            raise _refuse("IR_TYPE_MISMATCH",
                          f"comparison between {left.type} and {right.type}", node)
        if op in _ORDERED_ONLY and left.type is not IrType.INT:
            raise _refuse("IR_UNSUPPORTED_TYPE",
                          f"ordering comparison on {left.type} is outside the subset", node)
        return Compare(op=op, left=left, right=right)

    def _boolop(self, node: ast.BoolOp, scope: Mapping[str, IrType]) -> BoolOp:
        op = "and" if isinstance(node.op, ast.And) else "or"
        values = tuple(self._expr(value, scope) for value in node.values)
        for value in values:
            if value.type is not IrType.BOOL:
                raise _refuse("IR_UNSUPPORTED_TYPE",
                              f"boolean operator applied to {value.type}", node)
        return BoolOp(op=op, values=values)

    def _call(self, node: ast.Call, scope: Mapping[str, IrType]) -> Call:
        if node.keywords or not isinstance(node.func, ast.Name):
            raise _refuse("IR_UNSUPPORTED_EXPRESSION",
                          "only positional calls to a plain name are admitted", node)
        target = self._admitted.get(node.func.id)
        if target is None:
            raise _refuse("IR_UNRESOLVED_CALL",
                          f"{node.func.id!r} is not a function admitted earlier in this unit "
                          "(recursion and forward references are outside the subset)", node)
        args = tuple(self._expr(arg, scope) for arg in node.args)
        if len(args) != len(target.params):
            raise _refuse("IR_ARITY_MISMATCH",
                          f"{node.func.id!r} takes {len(target.params)} arguments, "
                          f"{len(args)} given", node)
        for arg, param in zip(args, target.params, strict=True):
            if arg.type is not param.type:
                raise _refuse("IR_TYPE_MISMATCH",
                              f"{node.func.id!r} parameter {param.name!r} is {param.type}, "
                              f"argument is {arg.type}", node)
        return Call(func=node.func.id, args=args, type=target.return_type)


def compile_unit(source: str, *, unit_id: str = "unit") -> tuple[SemanticIr, tuple[Rejection, ...]]:
    """Compile one Python module into IR plus the list of refusals.

    Returns ``(ir, rejections)``.  A unit with zero admitted functions is a legitimate,
    *measured* result — it is not an error, and it is not an empty success either: the
    rejections and the :class:`Admission` histogram say exactly what happened.  A source
    that will not parse is a different thing entirely and raises ``IR_SOURCE_UNPARSEABLE``,
    because "nothing was admitted" and "nothing was even looked at" must not look alike.
    """

    text = source if isinstance(source, str) else ""
    if not isinstance(source, str):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="source must be a string",
            recommended_action="pass the unit source text",
        )
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise KernelError(
            code="IR_SOURCE_UNPARSEABLE",
            message=f"{unit_id} is not parseable Python: {exc.msg} at line {exc.lineno}",
            recommended_action="fix the syntax error before requesting an IR",
            details={"unitId": unit_id, "line": exc.lineno or 0},
        ) from exc

    admitted: dict[str, IrFunction] = {}
    rejections: list[Rejection] = []
    positions: dict[str, tuple[int, int, int]] = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.FunctionDef):
            rejections.append(Rejection(
                symbol=f"<module>@{getattr(stmt, 'lineno', 0)}",
                code="IR_UNSUPPORTED_STATEMENT",
                message=f"top-level {type(stmt).__name__} is outside the subset; "
                        "a unit is a module of plain function definitions",
                line=getattr(stmt, "lineno", 0),
                column=getattr(stmt, "col_offset", 0),
            ))
            continue
        compiler = _UnitCompiler(admitted)
        try:
            function = compiler.compile_function(stmt)
        except _Refused as refused:
            rejections.append(Rejection(symbol=stmt.name, code=refused.code,
                                        message=refused.message, line=refused.line,
                                        column=refused.column))
            continue
        if stmt.name in admitted:
            rejections.append(Rejection(
                symbol=stmt.name, code="IR_REBINDING_FORBIDDEN",
                message=f"{stmt.name!r} is defined more than once in this unit",
                line=stmt.lineno, column=stmt.col_offset,
            ))
            continue
        admitted[stmt.name] = function
        positions.update(compiler.positions)

    ir = SemanticIr(
        ir_version=IR_VERSION,
        unit_id=unit_id,
        source_sha=digest({"unitId": unit_id, "source": text}),
        functions=tuple(admitted.values()),
        positions=tuple(sorted(positions.items())),
    )
    return ir, tuple(rejections)


def admission_of(ir: SemanticIr, rejections: Sequence[Rejection]) -> Admission:
    """Summarise how much of the unit the subset covered."""

    histogram: dict[str, int] = {}
    for rejection in rejections:
        histogram[rejection.code] = histogram.get(rejection.code, 0) + 1
    admitted = len(ir.functions)
    return Admission(
        total_units=admitted + len(rejections),
        admitted_units=admitted,
        rejected_units=len(rejections),
        reason_histogram=tuple(sorted(histogram.items())),
    )


def source_map_gaps(ir: SemanticIr) -> tuple[str, ...]:
    """Node ids with no source position.

    Expressions are located by their enclosing statement, not individually; that is a real
    limitation of this IR and is stated rather than papered over.
    """

    positions = ir.source_map().get("positions", {})
    return tuple(node["id"] for node in ir.nodes() if node["id"] not in positions)


# --- emission ----------------------------------------------------------------


def _emit_expr(expr: Expr) -> str:
    if isinstance(expr, Literal):
        if expr.type is IrType.BOOL:
            return "True" if expr.value else "False"
        if expr.type is IrType.INT:
            return str(expr.value)
        return repr(expr.value)
    if isinstance(expr, Name):
        return expr.name
    if isinstance(expr, Unary):
        inner = _emit_expr(expr.operand)
        return f"(-{inner})" if expr.op == "neg" else f"(not {inner})"
    if isinstance(expr, Binary):
        token = _BINARY_TOKENS[expr.op]
        return f"({_emit_expr(expr.left)} {token} {_emit_expr(expr.right)})"
    if isinstance(expr, Compare):
        token = _COMPARE_TOKENS[expr.op]
        return f"({_emit_expr(expr.left)} {token} {_emit_expr(expr.right)})"
    if isinstance(expr, BoolOp):
        joined = f" {expr.op} ".join(_emit_expr(value) for value in expr.values)
        return f"({joined})"
    return f"{expr.func}({', '.join(_emit_expr(arg) for arg in expr.args)})"


def _emit_block(stmts: Iterable[Stmt], indent: int) -> list[str]:
    pad = "    " * indent
    lines: list[str] = []
    for stmt in stmts:
        if isinstance(stmt, Let):
            lines.append(f"{pad}{stmt.name}: {stmt.type} = {_emit_expr(stmt.value)}")
        elif isinstance(stmt, Return):
            lines.append(f"{pad}return {_emit_expr(stmt.value)}")
        else:
            lines.append(f"{pad}if {_emit_expr(stmt.test)}:")
            lines.extend(_emit_block(stmt.then, indent + 1))
            lines.append(f"{pad}else:")
            lines.extend(_emit_block(stmt.orelse, indent + 1))
    return lines


def emit_python(ir: SemanticIr) -> str:
    """Render the IR back to Python.

    The output is fully parenthesised rather than minimally parenthesised: precedence
    reconstruction is the classic place where a pretty-printer silently changes meaning,
    and the round-trip test in ``tests/test_semir.py`` would only catch it for the shapes
    the fixtures happen to contain.  Parenthesising unconditionally removes the class of
    bug instead of testing for it.
    """

    lines: list[str] = []
    for index, function in enumerate(ir.functions):
        if index:
            lines.append("")
        params = ", ".join(f"{p.name}: {p.type}" for p in function.params)
        lines.append(f"def {function.name}({params}) -> {function.return_type}:")
        lines.extend(_emit_block(function.body, 1))
    return "\n".join(lines) + "\n"


# --- registry entry point ----------------------------------------------------

_KNOWN_FIELDS = ("sourceUnit", "languageProfile", "requireFullAdmission")
_KNOWN_UNIT_FIELDS = ("unitId", "source")
_KNOWN_PROFILE_FIELDS = ("language", "irVersion", "targetLanguage")


@register("semantic-ir-compiler")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point: decode strictly, compile, report the subset boundary."""

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _KNOWN_FIELDS, field_name="semantic-ir-compiler request")

    unit = require_mapping(payload.get("sourceUnit"), "sourceUnit")
    reject_unknown_fields(unit, _KNOWN_UNIT_FIELDS, field_name="sourceUnit")
    unit_id = require_str(unit.get("unitId"), "sourceUnit.unitId", max_length=128)
    source = unit.get("source")
    if not isinstance(source, str):
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="sourceUnit.source must be a string",
            recommended_action="supply the unit source text",
        )

    profile = require_mapping(payload.get("languageProfile"), "languageProfile")
    reject_unknown_fields(profile, _KNOWN_PROFILE_FIELDS, field_name="languageProfile")
    language = require_str(profile.get("language"), "languageProfile.language", max_length=64)
    if language != "python":
        raise KernelError(
            code="TARGET_PROFILE_UNSUPPORTED",
            message=f"language {language!r} has no admitted subset in this build",
            recommended_action="request the python profile or extend the compiler",
            details={"supported": ["python"]},
        )
    target = profile.get("targetLanguage", "python")
    if target != "python":
        raise KernelError(
            code="TARGET_PROFILE_UNSUPPORTED",
            message=f"target language {target!r} is not emitted by this build",
            recommended_action="request the python target",
            details={"supported": ["python"]},
        )
    declared_version = profile.get("irVersion", IR_VERSION)
    if declared_version != IR_VERSION:
        raise KernelError(
            code="TARGET_PROFILE_UNSUPPORTED",
            message=f"irVersion {declared_version!r} is not produced by this build",
            recommended_action=f"request {IR_VERSION}",
            details={"supported": [IR_VERSION]},
        )
    require_full = require_bool(payload.get("requireFullAdmission", False), "requireFullAdmission")

    ir, rejections = compile_unit(source, unit_id=unit_id)
    admission = admission_of(ir, rejections)
    gaps = source_map_gaps(ir)
    if gaps:
        raise KernelError(
            code="SOURCE_MAP_INCOMPLETE",
            message=f"{len(gaps)} IR nodes have no source position",
            recommended_action="treat as a compiler defect; do not consume this IR",
            details={"nodes": list(gaps[:16])},
        )

    if rejections and not ir.functions:
        raise KernelError(
            code="IR_UNREPRESENTABLE",
            message=f"{unit_id}: no top-level unit is inside the admitted subset",
            recommended_action="narrow the input to the subset reported in `subset`",
            details={"admission": admission.to_payload(),
                     "rejections": [r.to_payload() for r in rejections]},
        )
    if rejections and require_full:
        raise KernelError(
            code="IR_UNREPRESENTABLE",
            message=(f"{unit_id}: {admission.admitted_units} of {admission.total_units} units "
                     "admitted, full admission was required"),
            partial=True,
            recommended_action="lower the admitted subset yourself or drop requireFullAdmission",
            details={"admission": admission.to_payload(),
                     "rejections": [r.to_payload() for r in rejections]},
        )

    return {
        "status": Status.SUCCEEDED,
        "semanticIr": ir.to_payload(semantic_gaps=rejections),
        "semanticGaps": [rejection.to_payload() for rejection in rejections],
        "sourceMap": ir.source_map(),
        "admission": admission.to_payload(),
        "emittedSource": emit_python(ir),
        "subset": dict(SUBSET),
        "digest": ir.digest,
        "structuralDigest": ir.structural_digest,
    }
