from __future__ import annotations

import ast
import platform
from pathlib import Path
from typing import Any

from . import types
from .models import Expression, Function, Parameter, RecordDefinition, RouteError, SemanticIR, Statement


def _type(annotation: ast.expr | None, record_names: set[str] | None = None) -> str:
    if isinstance(annotation, ast.Name):
        canonical = {"int": "integer", "float": "number", "bool": "boolean", "str": "string"}.get(annotation.id)
        if canonical:
            return canonical
        if record_names and annotation.id in record_names:
            return annotation.id
        return ""
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        canonical = {"int": "integer", "float": "number", "bool": "boolean", "str": "string"}.get(annotation.value)
        if canonical:
            return canonical
        if record_names and annotation.value in record_names:
            return annotation.value
        return ""
    return ""


_EMITTED_BINARY_HELPERS = {
    "_elmos_checked_add": "+",
    "_elmos_checked_sub": "-",
    "_elmos_checked_mul": "*",
    "_elmos_truncating_div": "/",
    "_elmos_truncating_mod": "%",
}


def _binary(operator: str, left: ast.expr, right: ast.expr, *, emitted_target: bool) -> dict[str, Any]:
    return {
        "kind": "binary",
        "operator": operator,
        "left": _expression(left, emitted_target=emitted_target),
        "right": _expression(right, emitted_target=emitted_target),
    }


def _emitted_call(node: ast.Call) -> dict[str, Any] | None:
    if node.keywords:
        raise RouteError("PYTHON_EMITTED_HELPER_KEYWORDS_UNSUPPORTED")
    if isinstance(node.func, ast.Name) and node.func.id in _EMITTED_BINARY_HELPERS:
        if len(node.args) != 2:
            raise RouteError(f"PYTHON_EMITTED_HELPER_ARITY:{node.func.id}")
        return _binary(
            _EMITTED_BINARY_HELPERS[node.func.id],
            node.args[0],
            node.args[1],
            emitted_target=True,
        )
    if (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "math"
        and node.func.attr == "fmod"
    ):
        if len(node.args) != 2:
            raise RouteError("PYTHON_EMITTED_HELPER_ARITY:math.fmod")
        return _binary("%", node.args[0], node.args[1], emitted_target=True)
    return None


def _signed_literal(node: ast.expr) -> ast.Constant | None:
    """`-1` is not a literal in Python's grammar -- it is unary minus applied
    to `1`. Fold the sign back in.

    This is the ONLY unary form lifted here, and it is pure syntax: the result
    is the literal the source obviously means. `bool` is excluded because it is
    an `int` subclass in Python and `-True` is not a boolean.
    """

    if not isinstance(node, ast.UnaryOp) or not isinstance(node.op, ast.USub | ast.UAdd):
        return None
    operand = node.operand
    if not isinstance(operand, ast.Constant):
        return None
    value = operand.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return ast.Constant(value=-value if isinstance(node.op, ast.USub) else +value)


def _expression(
    node: ast.expr,
    *,
    record_names: set[str] | None = None,
    record_defs: dict[str, RecordDefinition] | None = None,
    function_names: set[str] | None = None,
    emitted_target: bool = False,
) -> dict[str, Any]:
    folded = _signed_literal(node)
    if folded is not None:
        node = folded
    if isinstance(node, ast.Name):
        return {"kind": "name", "value": node.id}
    if isinstance(node, ast.Constant) and isinstance(node.value, str | int | float | bool):
        return {"kind": "literal", "value": node.value}
    if isinstance(node, ast.BinOp):
        operator = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
            ast.Mod: "%",
        }.get(type(node.op))
        if operator:
            return {
                "kind": "binary",
                "operator": operator,
                "left": _expression(
                    node.left,
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                ),
                "right": _expression(
                    node.right,
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                ),
            }
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        operator = {
            ast.Lt: "<",
            ast.LtE: "<=",
            ast.Gt: ">",
            ast.GtE: ">=",
            ast.Eq: "==",
            ast.NotEq: "!=",
        }.get(type(node.ops[0]))
        if operator:
            return {
                "kind": "binary",
                "operator": operator,
                "left": _expression(
                    node.left,
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                ),
                "right": _expression(
                    node.comparators[0],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                ),
            }
    if isinstance(node, ast.BoolOp) and len(node.values) >= 2:
        # Python's parser FLATTENS `a and b and c` into one three-value node,
        # so accepting only `len(values) == 2` refused a spelling while
        # accepting `(a and b) and c`, which is the same program. Left-folding
        # reproduces Python's own left-to-right grouping, and produces IR
        # byte-identical to the parenthesized form (see the test).
        #
        # Short-circuiting survives the fold: canonical `&&`/`||` short-circuit
        # (canonical.py `_expression`), so `(a && b) && c` stops exactly where
        # `a and b and c` stops.
        operator = "&&" if isinstance(node.op, ast.And) else "||"
        # NOT named `folded`: that name already holds the signed-literal fold
        # at the top of this function, and reusing it makes mypy read the two
        # as one variable of two incompatible types.
        chain = _expression(
            node.values[0],
            record_names=record_names,
            record_defs=record_defs,
            function_names=function_names,
            emitted_target=emitted_target,
        )
        for value in node.values[1:]:
            chain = {
                "kind": "binary",
                "operator": operator,
                "left": chain,
                "right": _expression(
                    value,
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                ),
            }
        return chain
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        # `not x` on a canonical boolean IS `x == False`. Nothing new enters
        # the IR, the type checker, canonical.py or the z3 denotation.
        #
        # A non-boolean operand is Python truthiness -- `not ""`, `not 0`,
        # `not []` -- which has no canonical meaning and no agreed spelling
        # across the targets. It still fails closed, as
        # `OPERAND_TYPE_MISMATCH:==:<type>:boolean` from `types.infer`.
        return {
            "kind": "binary",
            "operator": "==",
            "left": _expression(
                node.operand,
                record_names=record_names,
                record_defs=record_defs,
                function_names=function_names,
                emitted_target=emitted_target,
            ),
            "right": {"kind": "literal", "value": False},
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        # A signed LITERAL was folded at the top of this function; reaching
        # here means the operand is an expression.
        #
        # Refused with a reason rather than the generic code: lowering `-x` to
        # `0 - x` is exact for `integer` but NOT for `number`, because
        # IEEE-754 makes `-(0.0)` negative zero while `0.0 - 0.0` is positive
        # zero, and the sign of a returned zero is observable. Supporting it
        # honestly needs a unary node in the IR, in canonical.py, in the z3
        # denotation and in all 13 emitters.
        raise RouteError("PYTHON_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET")
    if isinstance(node, ast.Attribute):
        return {
            "kind": "member_access",
            "target": _expression(
                node.value,
                record_names=record_names,
                record_defs=record_defs,
                function_names=function_names,
                emitted_target=emitted_target,
            ),
            "member": node.attr,
        }
    if isinstance(node, ast.Call):
        if emitted_target:
            lifted = _emitted_call(node)
            if lifted is not None:
                return lifted
        if isinstance(node.func, ast.Name) and record_defs and node.func.id in record_defs:
            rec = record_defs[node.func.id]
            args_dict: dict[str, ast.expr] = {}
            if len(node.args) > len(rec.fields):
                raise RouteError(f"PYTHON_RECORD_TOO_MANY_ARGS:{rec.name}")
            for i, arg_expr in enumerate(node.args):
                args_dict[rec.fields[i].name] = arg_expr
            for kw in node.keywords:
                if kw.arg is None:
                    raise RouteError("PYTHON_RECORD_STAR_ARGS_UNSUPPORTED")
                if kw.arg in args_dict:
                    raise RouteError(f"PYTHON_RECORD_DUPLICATE_ARG:{rec.name}.{kw.arg}")
                field_names = {f.name for f in rec.fields}
                if kw.arg not in field_names:
                    raise RouteError(f"PYTHON_RECORD_UNKNOWN_FIELD:{rec.name}.{kw.arg}")
                args_dict[kw.arg] = kw.value
            for f in rec.fields:
                if f.name not in args_dict:
                    raise RouteError(f"PYTHON_RECORD_MISSING_ARG:{rec.name}.{f.name}")
            args_dict_evaluated = {
                f.name: _expression(
                    args_dict[f.name],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
                for f in rec.fields
            }
            return {
                "kind": "record_construct",
                "record_name": rec.name,
                "arguments": args_dict_evaluated,
            }
        if isinstance(node.func, ast.Name) and function_names and node.func.id in function_names:
            if node.keywords:
                raise RouteError("PYTHON_CALL_KEYWORDS_UNSUPPORTED")
            return {
                "kind": "call",
                "function_name": node.func.id,
                "arguments": [
                    _expression(
                        arg,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    )
                    for arg in node.args
                ],
            }
    raise RouteError(f"PYTHON_UNSUPPORTED_EXPRESSION:{type(node).__name__}")


def _statements(
    nodes: list[ast.stmt],
    *,
    record_names: set[str] | None = None,
    record_defs: dict[str, RecordDefinition] | None = None,
    function_names: set[str] | None = None,
    emitted_target: bool = False,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        if isinstance(node, ast.Return) and node.value is not None:
            result.append(
                {
                    "kind": "return",
                    "expression": _expression(
                        node.value,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                }
            )
        elif isinstance(node, ast.If):
            result.append(
                {
                    "kind": "if",
                    "condition": _expression(
                        node.test,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                    "then": _statements(
                        node.body,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                    "else": _statements(
                        node.orelse,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                }
            )
        elif isinstance(node, ast.AnnAssign):
            # `x: int = expr` -- the IR's `let`.
            #
            # ONLY the annotated form. A bare `x = 1` carries no declared type,
            # and inferring one here would mean the IR's type came from this
            # analyzer's guess rather than from the source language's own type
            # system -- which is exactly the thing `let` was designed not to do.
            # Python's own checkers treat the two forms differently too, so
            # refusing the unannotated one costs the author one annotation and
            # buys the whole pipeline a type it can hold the source to.
            if node.value is None:
                # `x: int` alone declares without binding. `let` is a binding.
                raise RouteError("PYTHON_ANNOTATED_DECLARATION_WITHOUT_VALUE")
            if node.simple != 1 or not isinstance(node.target, ast.Name):
                # `(x): int = 1`, `obj.x: int = 1`, `a[0]: int = 1` -- none of
                # these bind a plain local name.
                raise RouteError("PYTHON_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET")
            declared = _type(node.annotation, record_names)
            if not declared:
                raise RouteError(f"PYTHON_UNSUPPORTED_LOCAL_TYPE:{ast.unparse(node.annotation)}")
            result.append(
                {
                    "kind": "let",
                    "name": node.target.id,
                    "type": declared,
                    "expression": _expression(
                        node.value,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                }
            )
        elif isinstance(node, ast.While):
            if node.orelse:
                raise RouteError("PYTHON_WHILE_ORELSE_OUTSIDE_CERTIFIED_SUBSET")
            result.append(
                {
                    "kind": "while",
                    "condition": _expression(
                        node.test,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                    "body": _statements(
                        node.body,
                        record_names=record_names,
                        record_defs=record_defs,
                        function_names=function_names,
                        emitted_target=emitted_target,
                    ),
                }
            )
        elif isinstance(node, ast.For):
            if node.orelse:
                raise RouteError("PYTHON_FOR_ORELSE_OUTSIDE_CERTIFIED_SUBSET")
            if not isinstance(node.target, ast.Name):
                raise RouteError("PYTHON_FOR_TARGET_OUTSIDE_CERTIFIED_SUBSET")
            if not (
                isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "range"
            ):
                raise RouteError("PYTHON_NON_RANGE_FOR_OUTSIDE_CERTIFIED_SUBSET")
            if node.iter.keywords:
                raise RouteError("PYTHON_RANGE_KEYWORDS_UNSUPPORTED")
            args = node.iter.args
            if len(args) == 1:
                start: dict[str, Any] = {"kind": "literal", "value": 0}
                end = _expression(
                    args[0],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
                step = None
            elif len(args) == 2:
                start = _expression(
                    args[0],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
                end = _expression(
                    args[1],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
                step = None
            elif len(args) == 3:
                start = _expression(
                    args[0],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
                end = _expression(
                    args[1],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
                step = _expression(
                    args[2],
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                )
            else:
                raise RouteError(f"PYTHON_RANGE_ARITY_INVALID:{len(args)}")
            for_dict: dict[str, Any] = {
                "kind": "for",
                "name": node.target.id,
                "type": "integer",
                "start": start,
                "end": end,
                "body": _statements(
                    node.body,
                    record_names=record_names,
                    record_defs=record_defs,
                    function_names=function_names,
                    emitted_target=emitted_target,
                ),
            }
            if step is not None:
                for_dict["step"] = step
            result.append(for_dict)
        elif isinstance(node, ast.Break):
            result.append({"kind": "break"})
        elif isinstance(node, ast.Continue):
            result.append({"kind": "continue"})
        elif isinstance(node, ast.Assign):
            # Named apart from the generic rejection so the message says what
            # to do: annotate it. `PYTHON_UNSUPPORTED_STATEMENT:Assign` would
            # have read as "assignment is not supported at all", which stopped
            # being true here.
            raise RouteError("PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET")
        else:
            raise RouteError(f"PYTHON_UNSUPPORTED_STATEMENT:{type(node).__name__}")
    return result


def _reject_python_only_arithmetic(
    expression: Expression,
    environment: dict[str, str],
    records_env: dict[str, RecordDefinition] | None = None,
    functions_env: dict[str, Function] | None = None,
) -> None:
    """Refuse the two Python operators whose meaning does not survive lifting.

    The canonical IR defines `/` and `%` on two integers as the *truncating*
    pair Java, C# and TypeScript implement. Python's spellings differ:

      * `/` on two ints is true division -- `7 / 2` is 3.5, not 3, and the
        result is a float, so lifting it as canonical `/` would emit
        `7 / 2 == 3` in every other target.
      * `%` follows the sign of the divisor -- `-7 % 2` is 1 where Java,
        C# and TypeScript all answer -1. This applies to floats too, so the
        rejection is not restricted to integer operands.

    Both fail closed here rather than being lifted into an operator that
    means something else. Python's `//` is already outside the subset (it is
    not in the lifted operator table) for the same reason: it floors.
    """
    if expression.kind == "call":
        for arg in expression.call_arguments:
            _reject_python_only_arithmetic(arg, environment, records_env, functions_env)
        return
    if expression.kind == "member_access" and expression.target is not None:
        _reject_python_only_arithmetic(expression.target, environment, records_env, functions_env)
        return
    if expression.kind == "record_construct":
        for _, arg in expression.arguments:
            _reject_python_only_arithmetic(arg, environment, records_env, functions_env)
        return
    if expression.kind != "binary" or expression.left is None or expression.right is None:
        return
    if expression.operator == "%":
        raise RouteError("PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET")
    if expression.operator == "/":
        left = types.infer(expression.left, environment, records_env, functions_env)
        right = types.infer(expression.right, environment, records_env, functions_env)
        if left == "integer" and right == "integer":
            raise RouteError("PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET")
    _reject_python_only_arithmetic(expression.left, environment, records_env, functions_env)
    _reject_python_only_arithmetic(expression.right, environment, records_env, functions_env)


def _check_statements(
    statements: tuple[Statement, ...],
    environment: dict[str, str],
    records_env: dict[str, RecordDefinition] | None = None,
    functions_env: dict[str, Function] | None = None,
) -> None:
    """Walk for the Python-only arithmetic rejection, carrying the same scope
    rule `types._check_statements` uses.

    `_reject_python_only_arithmetic` calls `types.infer` to decide whether a
    `/` has two integer operands, and `infer` fails closed on a name it has
    never seen. So this walk has to bind `let` names as it meets them, and hand
    branches a copy -- otherwise a perfectly legal `x: int = 1` followed by
    `x / y` would be rejected as an undeclared name instead of being judged on
    its operand types.
    """
    for statement in statements:
        if statement.expression is not None:
            _reject_python_only_arithmetic(statement.expression, environment, records_env, functions_env)
        if statement.condition is not None:
            _reject_python_only_arithmetic(statement.condition, environment, records_env, functions_env)
        if statement.kind == "let" and statement.name is not None and statement.declared_type is not None:
            # After its own initializer, never before.
            environment[statement.name] = statement.declared_type
            continue
        if statement.kind == "while":
            _check_statements(statement.body, dict(environment), records_env, functions_env)
            continue
        if statement.kind == "for":
            if statement.start is not None:
                _reject_python_only_arithmetic(statement.start, environment, records_env, functions_env)
            if statement.end is not None:
                _reject_python_only_arithmetic(statement.end, environment, records_env, functions_env)
            if statement.step is not None:
                _reject_python_only_arithmetic(statement.step, environment, records_env, functions_env)
            loop_env = dict(environment)
            if statement.name is not None:
                loop_env[statement.name] = "integer"
            _check_statements(statement.body, loop_env, records_env, functions_env)
            continue
        _check_statements(statement.then_body, dict(environment), records_env, functions_env)
        _check_statements(statement.else_body, dict(environment), records_env, functions_env)


def _check_function(
    function: Function,
    records_env: dict[str, RecordDefinition] | None = None,
    functions_env: dict[str, Function] | None = None,
) -> None:
    # The canonical checker mutates and returns its environment, so its result
    # contains every top-level `let`.  The Python-only arithmetic walk must
    # instead start with parameters and bind locals in source order; otherwise
    # a later declaration is incorrectly visible to an earlier statement.
    types.check_function(function, records_env, functions_env)
    _check_statements(function.body, types.environment_of(function, records_env), records_env, functions_env)


def _emitted_body(nodes: list[ast.stmt], parameters: list[dict[str, str]]) -> list[ast.stmt]:
    """Validate and remove emitter-owned canonical-domain guards.

    The guards are not user statements: they are the executable realization of
    the canonical ``integer`` parameter domain in Python's unbounded ``int``.
    They are accepted only as the exact deterministic prefix emitted by
    :mod:`emitter`; a missing, reordered, duplicated, or lookalike guard fails
    closed instead of being ignored.
    """

    expected = [item["name"] for item in parameters if item["type"] == "integer"]
    if len(nodes) < len(expected):
        raise RouteError("PYTHON_EMITTED_INTEGER_GUARD_MISSING")
    for index, name in enumerate(expected):
        node = nodes[index]
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            raise RouteError(f"PYTHON_EMITTED_INTEGER_GUARD_MISSING:{name}")
        call = node.value
        if (
            not isinstance(call.func, ast.Name)
            or call.func.id != "_elmos_in_range"
            or call.keywords
            or len(call.args) != 1
            or not isinstance(call.args[0], ast.Name)
            or call.args[0].id != name
        ):
            raise RouteError(f"PYTHON_EMITTED_INTEGER_GUARD_INVALID:{name}")
    body = nodes[len(expected) :]
    if any(
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_elmos_in_range"
        for node in body
    ):
        raise RouteError("PYTHON_EMITTED_INTEGER_GUARD_UNEXPECTED")
    return body


def _split_leading_docstring(nodes: list[ast.stmt]) -> tuple[list[ast.stmt], str | None]:
    """Separate a leading docstring from the statements that follow it.

    A docstring is a bare string expression, so before this it hit the generic
    `PYTHON_UNSUPPORTED_STATEMENT:Expr` rejection and took the whole function
    with it. Measured on 20 real PyPI projects, 94 of the 109 functions whose
    signature was already fully inside the profile died on exactly this -- the
    single largest avoidable rejection in the frontend.

    Only the FIRST statement qualifies. A bare string anywhere else is a no-op
    expression, not documentation, and keeping it rejected is correct.

    The text is not discarded: `analyze_python` carries it into the IR as
    `Function.documentation` (provenance, not semantics), so the conversion
    never silently loses something the source declared.
    """

    if not nodes:
        return nodes, None
    first = nodes[0]
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return nodes, None
    remaining = nodes[1:]
    if not remaining:
        # A function whose entire body is its docstring has no behaviour to
        # convert. Fail closed with its own code rather than falling through to
        # a confusing empty-body error.
        raise RouteError("PYTHON_FUNCTION_BODY_IS_ONLY_DOCUMENTATION")
    return remaining, first.value.value


def _is_dataclass(node: ast.ClassDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return True
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "dataclass":
            return True
    return False


def _parse_record(node: ast.ClassDef, known_record_names: set[str]) -> RecordDefinition:
    if node.bases:
        raise RouteError(f"PYTHON_RECORD_INHERITANCE_UNSUPPORTED:{node.name}")
    fields: list[Parameter] = []
    field_names: set[str] = set()
    for item in node.body:
        if isinstance(item, ast.AnnAssign):
            if not isinstance(item.target, ast.Name):
                raise RouteError(f"PYTHON_RECORD_FIELD_TARGET_INVALID:{node.name}")
            f_name = item.target.id
            if f_name in field_names:
                raise RouteError(f"PYTHON_RECORD_DUPLICATE_FIELD:{node.name}.{f_name}")
            field_names.add(f_name)
            f_type = _type(item.annotation, known_record_names)
            if not f_type:
                raise RouteError(f"PYTHON_RECORD_FIELD_TYPE_INVALID:{node.name}.{f_name}")
            fields.append(Parameter(name=f_name, type=f_type))
        elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            continue
        elif isinstance(item, ast.Pass):
            continue
        else:
            raise RouteError(f"PYTHON_RECORD_UNSUPPORTED_MEMBER:{node.name}.{type(item).__name__}")
    if not fields:
        raise RouteError(f"PYTHON_RECORD_EMPTY:{node.name}")
    return RecordDefinition(name=node.name, fields=tuple(fields))


def _parse_function(
    candidate: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    record_names: set[str],
    record_defs: dict[str, RecordDefinition],
    function_names: set[str],
    emitted_target: bool,
) -> tuple[dict[str, Any], Function]:
    if isinstance(candidate, ast.AsyncFunctionDef):
        raise RouteError("ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
    parameters = []
    for argument in candidate.args.args:
        parameter_type = _type(argument.annotation, record_names)
        if not parameter_type:
            raise RouteError(f"PYTHON_PARAMETER_TYPE_REQUIRED:{argument.arg}")
        parameters.append({"name": argument.arg, "type": parameter_type})
    return_type = _type(candidate.returns, record_names)
    if not return_type:
        raise RouteError("PYTHON_RETURN_TYPE_REQUIRED")
    documentation: str | None = None
    if emitted_target:
        # Deliberately NOT applied to the emitted-target re-analysis. This
        # engine's emitters never produce a docstring, so one appearing there
        # means the target did not come from them -- and the re-analysis gate
        # exists to catch exactly that. Accepting it would weaken the gate.
        body = _emitted_body(candidate.body, parameters)
    else:
        body, documentation = _split_leading_docstring(candidate.body)
    function_mapping: dict[str, Any] = {
        "name": candidate.name,
        "parameters": parameters,
        "return_type": return_type,
        "body": _statements(
            body,
            record_names=record_names,
            record_defs=record_defs,
            function_names=function_names,
            emitted_target=emitted_target,
        ),
    }
    if documentation is not None:
        function_mapping["documentation"] = documentation
    return function_mapping, Function.from_mapping(function_mapping)


def analyze_python(path: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path.name, feature_version=(3, 12))
    records_list: list[RecordDefinition] = []
    record_defs: dict[str, RecordDefinition] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_dataclass(node):
            if node.name in record_defs:
                raise RouteError(f"PYTHON_DUPLICATE_RECORD_NAME:{node.name}")
            rec = _parse_record(node, set(record_defs.keys()))
            record_defs[rec.name] = rec
            records_list.append(rec)
    record_names = set(record_defs.keys())

    module_function_nodes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in module_function_nodes:
                raise RouteError(f"PYTHON_DUPLICATE_FUNCTION_NAME:{node.name}")
            module_function_nodes[node.name] = node

    if function_name not in module_function_nodes:
        raise RouteError(f"FUNCTION_NOT_FOUND:{function_name}")

    all_function_names = set(module_function_nodes.keys())
    parsed_functions: dict[str, Function] = {}
    function_mappings: dict[str, dict[str, Any]] = {}
    queue = [function_name]
    visited = {function_name}

    while queue:
        curr_name = queue.pop(0)
        mapping, fn = _parse_function(
            module_function_nodes[curr_name],
            record_names=record_names,
            record_defs=record_defs,
            function_names=all_function_names,
            emitted_target=emitted_target,
        )
        parsed_functions[curr_name] = fn
        function_mappings[curr_name] = mapping
        callees = types.extract_function_callees(fn)
        for callee in callees:
            if callee in module_function_nodes:
                if callee not in visited:
                    visited.add(callee)
                    queue.append(callee)
            else:
                raise RouteError(f"UNKNOWN_FUNCTION:{callee}")

    sorted_functions = types.topological_sort_functions(tuple(parsed_functions.values()))

    raw_semantic: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_language": "python",
        "source_file": path.name,
        "analyzer": "CPython ast",
        "analyzer_version": platform.python_version(),
        "functions": [function_mappings[f.name] for f in sorted_functions],
        "diagnostics": [],
    }
    if records_list:
        raw_semantic["records"] = [rec.to_mapping() for rec in records_list]
    semantic = SemanticIR.from_mapping(raw_semantic)
    types.check(semantic)
    if not emitted_target:
        functions_env = {f.name: f for f in semantic.functions}
        records_env = {r.name: r for r in semantic.records} if semantic.records else None
        for function in semantic.functions:
            _check_statements(function.body, types.environment_of(function, records_env), records_env, functions_env)
    return semantic
