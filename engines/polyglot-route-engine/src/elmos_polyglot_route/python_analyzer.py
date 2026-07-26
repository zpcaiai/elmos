from __future__ import annotations

import ast
import platform
from pathlib import Path
from typing import Any

from .models import RouteError, SemanticIR


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
    return SemanticIR.from_mapping(
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
