from __future__ import annotations

import json
from dataclasses import dataclass

from .models import Expression, Function, Language, RouteError, SemanticIR, Statement


@dataclass(frozen=True)
class EmittedFile:
    relative_path: str
    content: str


def _type(language: Language, value: str) -> str:
    mapping = {
        "java": {"integer": "long", "number": "double", "boolean": "boolean", "string": "String"},
        "python": {"integer": "int", "number": "float", "boolean": "bool", "string": "str"},
        "csharp": {"integer": "long", "number": "double", "boolean": "bool", "string": "string"},
        "typescript": {"integer": "number", "number": "number", "boolean": "boolean", "string": "string"},
    }
    try:
        return mapping[language][value]
    except KeyError as error:
        raise RouteError(f"UNSUPPORTED_TYPE_MAPPING:{language}:{value}") from error


def _literal(language: Language, value: str | int | float | bool | None) -> str:
    if isinstance(value, bool):
        if language == "python":
            return "True" if value else "False"
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int | float):
        return str(value)
    raise RouteError("NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET")


def _expression(language: Language, expression: Expression) -> str:
    if expression.kind == "name":
        return str(expression.value)
    if expression.kind == "literal":
        return _literal(language, expression.value)
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        operator = expression.operator
        if language == "python":
            operator = {"&&": "and", "||": "or"}.get(operator or "", operator)
        return f"({_expression(language, expression.left)} {operator} {_expression(language, expression.right)})"
    raise RouteError(f"UNSUPPORTED_EMISSION_EXPRESSION:{expression.kind}")


def _statements(language: Language, statements: tuple[Statement, ...], indent: int) -> list[str]:
    unit = "    "
    prefix = unit * indent
    lines: list[str] = []
    for statement in statements:
        if statement.kind == "return" and statement.expression is not None:
            suffix = "" if language == "python" else ";"
            lines.append(f"{prefix}return {_expression(language, statement.expression)}{suffix}")
            continue
        if statement.kind == "if" and statement.condition is not None:
            condition = _expression(language, statement.condition)
            if language == "python":
                lines.append(f"{prefix}if {condition}:")
                lines.extend(_statements(language, statement.then_body, indent + 1))
                if statement.else_body:
                    lines.append(f"{prefix}else:")
                    lines.extend(_statements(language, statement.else_body, indent + 1))
            else:
                lines.append(f"{prefix}if ({condition}) {{")
                lines.extend(_statements(language, statement.then_body, indent + 1))
                lines.append(f"{prefix}}}")
                if statement.else_body:
                    lines.append(f"{prefix}else {{")
                    lines.extend(_statements(language, statement.else_body, indent + 1))
                    lines.append(f"{prefix}}}")
            continue
        raise RouteError(f"UNSUPPORTED_EMISSION_STATEMENT:{statement.kind}")
    return lines


def _function(language: Language, function: Function) -> str:
    parameters = ", ".join(f"{_type(language, item.type)} {item.name}" for item in function.parameters)
    if language == "python":
        parameters = ", ".join(f"{item.name}: {_type(language, item.type)}" for item in function.parameters)
        lines = [f"def {function.name}({parameters}) -> {_type(language, function.return_type)}:"]
        lines.extend(_statements(language, function.body, 1))
        return "\n".join(lines)
    if language == "typescript":
        parameters = ", ".join(f"{item.name}: {_type(language, item.type)}" for item in function.parameters)
    if language == "java":
        lines = [f"    public static {_type(language, function.return_type)} {function.name}({parameters}) {{"]
    elif language == "csharp":
        lines = [f"    public static {_type(language, function.return_type)} {function.name}({parameters}) {{"]
    else:
        lines = [f"export function {function.name}({parameters}): {_type(language, function.return_type)} {{"]
    lines.extend(_statements(language, function.body, 2 if language in {"java", "csharp"} else 1))
    lines.append("    }" if language in {"java", "csharp"} else "}")
    return "\n".join(lines)


def emit(ir: SemanticIR, target: Language) -> EmittedFile:
    if ir.diagnostics:
        raise RouteError("SOURCE_DIAGNOSTICS_BLOCK_EMISSION:" + ",".join(ir.diagnostics))
    functions = "\n\n".join(_function(target, function) for function in ir.functions)
    if target == "java":
        return EmittedFile("Migrated.java", f"public final class Migrated {{\n{functions}\n}}\n")
    if target == "csharp":
        return EmittedFile("Migrated.cs", f"public static class Migrated\n{{\n{functions}\n}}\n")
    if target == "python":
        return EmittedFile("migrated.py", f"from __future__ import annotations\n\n{functions}\n")
    return EmittedFile("migrated.ts", f"{functions}\n")
