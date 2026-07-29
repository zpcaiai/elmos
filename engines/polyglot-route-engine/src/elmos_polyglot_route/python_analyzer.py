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


def _expression(node: ast.expr) -> dict[str, Any]:
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
                "left": _expression(node.left),
                "right": _expression(node.right),
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
                "left": _expression(node.left),
                "right": _expression(node.comparators[0]),
            }
    if isinstance(node, ast.BoolOp) and len(node.values) == 2:
        return {
            "kind": "binary",
            "operator": "&&" if isinstance(node.op, ast.And) else "||",
            "left": _expression(node.values[0]),
            "right": _expression(node.values[1]),
        }
    raise RouteError(f"PYTHON_UNSUPPORTED_EXPRESSION:{type(node).__name__}")


def _statements(nodes: list[ast.stmt]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        if isinstance(node, ast.Return) and node.value is not None:
            result.append({"kind": "return", "expression": _expression(node.value)})
        elif isinstance(node, ast.If):
            result.append(
                {
                    "kind": "if",
                    "condition": _expression(node.test),
                    "then": _statements(node.body),
                    "else": _statements(node.orelse),
                }
            )
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
    for statement in statements:
        if statement.expression is not None:
            _reject_python_only_arithmetic(statement.expression, environment)
        if statement.condition is not None:
            _reject_python_only_arithmetic(statement.condition, environment)
        _check_statements(statement.then_body, environment)
        _check_statements(statement.else_body, environment)


def _check_function(function: Function) -> None:
    environment = types.check_function(function)
    _check_statements(function.body, environment)


def analyze_python(path: Path, function_name: str) -> SemanticIR:
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
                    "body": _statements(candidate.body),
                }
            ],
            "diagnostics": [],
        }
    )
    for function in semantic.functions:
        _check_function(function)
    return semantic
