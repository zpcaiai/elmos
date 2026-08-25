from __future__ import annotations

import ast
import platform
from pathlib import Path
from typing import Any

from . import types
from .models import Expression, Function, RouteError, SemanticIR, Statement


def _type(annotation: ast.expr | None) -> str:
    if isinstance(annotation, ast.Name):
        return {"int": "integer", "float": "number", "bool": "boolean", "str": "string"}.get(annotation.id, "")
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


def _expression(node: ast.expr, *, emitted_target: bool = False) -> dict[str, Any]:
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
                "left": _expression(node.left, emitted_target=emitted_target),
                "right": _expression(node.right, emitted_target=emitted_target),
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
                "left": _expression(node.left, emitted_target=emitted_target),
                "right": _expression(node.comparators[0], emitted_target=emitted_target),
            }
    if isinstance(node, ast.BoolOp) and len(node.values) == 2:
        return {
            "kind": "binary",
            "operator": "&&" if isinstance(node.op, ast.And) else "||",
            "left": _expression(node.values[0], emitted_target=emitted_target),
            "right": _expression(node.values[1], emitted_target=emitted_target),
        }
    if emitted_target and isinstance(node, ast.Call):
        lifted = _emitted_call(node)
        if lifted is not None:
            return lifted
    raise RouteError(f"PYTHON_UNSUPPORTED_EXPRESSION:{type(node).__name__}")


def _statements(nodes: list[ast.stmt], *, emitted_target: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        if isinstance(node, ast.Return) and node.value is not None:
            result.append(
                {
                    "kind": "return",
                    "expression": _expression(node.value, emitted_target=emitted_target),
                }
            )
        elif isinstance(node, ast.If):
            result.append(
                {
                    "kind": "if",
                    "condition": _expression(node.test, emitted_target=emitted_target),
                    "then": _statements(node.body, emitted_target=emitted_target),
                    "else": _statements(node.orelse, emitted_target=emitted_target),
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
            declared = _type(node.annotation)
            if not declared:
                raise RouteError(f"PYTHON_UNSUPPORTED_LOCAL_TYPE:{ast.unparse(node.annotation)}")
            result.append(
                {
                    "kind": "let",
                    "name": node.target.id,
                    "type": declared,
                    "expression": _expression(node.value, emitted_target=emitted_target),
                }
            )
        elif isinstance(node, ast.Assign):
            # Named apart from the generic rejection so the message says what
            # to do: annotate it. `PYTHON_UNSUPPORTED_STATEMENT:Assign` would
            # have read as "assignment is not supported at all", which stopped
            # being true here.
            raise RouteError("PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET")
        else:
            raise RouteError(f"PYTHON_UNSUPPORTED_STATEMENT:{type(node).__name__}")
    return result


def _reject_python_only_arithmetic(expression: Expression, environment: dict[str, str]) -> None:
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
    if expression.kind != "binary" or expression.left is None or expression.right is None:
        return
    if expression.operator == "%":
        raise RouteError("PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET")
    if expression.operator == "/":
        left = types.infer(expression.left, environment)
        right = types.infer(expression.right, environment)
        if left == "integer" and right == "integer":
            raise RouteError("PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET")
    _reject_python_only_arithmetic(expression.left, environment)
    _reject_python_only_arithmetic(expression.right, environment)


def _check_statements(statements: tuple[Statement, ...], environment: dict[str, str]) -> None:
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
            _reject_python_only_arithmetic(statement.expression, environment)
        if statement.condition is not None:
            _reject_python_only_arithmetic(statement.condition, environment)
        if statement.kind == "let" and statement.name is not None and statement.declared_type is not None:
            # After its own initializer, never before.
            environment[statement.name] = statement.declared_type
            continue
        _check_statements(statement.then_body, dict(environment))
        _check_statements(statement.else_body, dict(environment))


def _check_function(function: Function) -> None:
    # The canonical checker mutates and returns its environment, so its result
    # contains every top-level `let`.  The Python-only arithmetic walk must
    # instead start with parameters and bind locals in source order; otherwise
    # a later declaration is incorrectly visible to an earlier statement.
    types.check_function(function)
    _check_statements(function.body, types.environment_of(function))


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


def analyze_python(path: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path.name, feature_version=(3, 12))
    candidate = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name
        ),
        None,
    )
    if candidate is None:
        raise RouteError(f"FUNCTION_NOT_FOUND:{function_name}")
    if isinstance(candidate, ast.AsyncFunctionDef):
        raise RouteError("ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET")
    parameters = []
    for argument in candidate.args.args:
        parameter_type = _type(argument.annotation)
        if not parameter_type:
            raise RouteError(f"PYTHON_PARAMETER_TYPE_REQUIRED:{argument.arg}")
        parameters.append({"name": argument.arg, "type": parameter_type})
    return_type = _type(candidate.returns)
    if not return_type:
        raise RouteError("PYTHON_RETURN_TYPE_REQUIRED")
    body = _emitted_body(candidate.body, parameters) if emitted_target else candidate.body
    semantic = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": path.name,
            "analyzer": "CPython ast",
            "analyzer_version": platform.python_version(),
            "functions": [
                {
                    "name": candidate.name,
                    "parameters": parameters,
                    "return_type": return_type,
                    "body": _statements(body, emitted_target=emitted_target),
                }
            ],
            "diagnostics": [],
        }
    )
    for function in semantic.functions:
        if emitted_target:
            types.check_function(function)
        else:
            _check_function(function)
    return semantic
