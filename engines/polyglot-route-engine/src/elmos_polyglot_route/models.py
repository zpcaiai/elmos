from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Language = Literal["java", "python", "csharp", "typescript", "cpp", "objc", "swift"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = (
    "java",
    "python",
    "csharp",
    "typescript",
    "cpp",
    "objc",
    "swift",
)

#: Languages this engine can lift *from*. Swift is currently a target only:
#: its analyzer needs a SwiftSyntax-backed helper built against a pinned Swift
#: toolchain, the same shape as the Roslyn and TypeScript Compiler API helpers
#: this engine already shells out to. Until that exists, a Swift source fails
#: closed (`SWIFT_SOURCE_ANALYZER_NOT_AVAILABLE`) rather than being parsed at
#: the text level.
ANALYZABLE_LANGUAGES: tuple[Language, ...] = (
    "java",
    "python",
    "csharp",
    "typescript",
    "cpp",
    "objc",
)


class RouteError(ValueError):
    """Raised when a route cannot preserve the declared semantic subset."""


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Parameter:
        name = str(value.get("name", "")).strip()
        parameter_type = str(value.get("type", "")).strip()
        if not name or parameter_type not in {"integer", "number", "boolean", "string"}:
            raise RouteError("INVALID_PARAMETER")
        return cls(name=name, type=parameter_type)

    def to_mapping(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type}


@dataclass(frozen=True)
class Expression:
    kind: str
    value: str | int | float | bool | None = None
    operator: str | None = None
    left: Expression | None = None
    right: Expression | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Expression:
        kind = str(value.get("kind", ""))
        if kind in {"name", "literal"}:
            return cls(kind=kind, value=value.get("value"))
        if kind == "binary":
            operator = str(value.get("operator", ""))
            if operator not in {"+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||"}:
                raise RouteError(f"UNSUPPORTED_OPERATOR:{operator}")
            left = value.get("left")
            right = value.get("right")
            if not isinstance(left, dict) or not isinstance(right, dict):
                raise RouteError("BINARY_OPERANDS_REQUIRED")
            return cls(
                kind=kind,
                operator=operator,
                left=cls.from_mapping(left),
                right=cls.from_mapping(right),
            )
        raise RouteError(f"UNSUPPORTED_EXPRESSION:{kind}")

    def to_mapping(self) -> dict[str, Any]:
        if self.kind in {"name", "literal"}:
            return {"kind": self.kind, "value": self.value}
        if self.left is None or self.right is None or self.operator is None:
            raise RouteError("INVALID_BINARY_EXPRESSION")
        return {
            "kind": "binary",
            "operator": self.operator,
            "left": self.left.to_mapping(),
            "right": self.right.to_mapping(),
        }


@dataclass(frozen=True)
class Statement:
    kind: str
    expression: Expression | None = None
    condition: Expression | None = None
    then_body: tuple[Statement, ...] = ()
    else_body: tuple[Statement, ...] = ()

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Statement:
        kind = str(value.get("kind", ""))
        if kind == "return":
            expression = value.get("expression")
            if not isinstance(expression, dict):
                raise RouteError("RETURN_EXPRESSION_REQUIRED")
            return cls(kind=kind, expression=Expression.from_mapping(expression))
        if kind == "if":
            condition = value.get("condition")
            then_body = value.get("then", [])
            else_body = value.get("else", [])
            if not isinstance(condition, dict) or not isinstance(then_body, list) or not isinstance(else_body, list):
                raise RouteError("INVALID_IF_STATEMENT")
            return cls(
                kind=kind,
                condition=Expression.from_mapping(condition),
                then_body=tuple(cls.from_mapping(item) for item in then_body if isinstance(item, dict)),
                else_body=tuple(cls.from_mapping(item) for item in else_body if isinstance(item, dict)),
            )
        raise RouteError(f"UNSUPPORTED_STATEMENT:{kind}")

    def to_mapping(self) -> dict[str, Any]:
        if self.kind == "return" and self.expression is not None:
            return {"kind": "return", "expression": self.expression.to_mapping()}
        if self.kind == "if" and self.condition is not None:
            return {
                "kind": "if",
                "condition": self.condition.to_mapping(),
                "then": [item.to_mapping() for item in self.then_body],
                "else": [item.to_mapping() for item in self.else_body],
            }
        raise RouteError("INVALID_STATEMENT")


@dataclass(frozen=True)
class Function:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: str
    body: tuple[Statement, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Function:
        name = str(value.get("name", "")).strip()
        return_type = str(value.get("return_type", "")).strip()
        parameters = value.get("parameters")
        body = value.get("body")
        if not name or return_type not in {"integer", "number", "boolean", "string"}:
            raise RouteError("INVALID_FUNCTION_SIGNATURE")
        if not isinstance(parameters, list) or not isinstance(body, list) or not body:
            raise RouteError("FUNCTION_BODY_REQUIRED")
        return cls(
            name=name,
            parameters=tuple(Parameter.from_mapping(item) for item in parameters if isinstance(item, dict)),
            return_type=return_type,
            body=tuple(Statement.from_mapping(item) for item in body if isinstance(item, dict)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameters": [parameter.to_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.to_mapping() for statement in self.body],
        }


@dataclass(frozen=True)
class SemanticIR:
    source_language: Language
    source_file: str
    analyzer: str
    analyzer_version: str
    functions: tuple[Function, ...]
    diagnostics: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> SemanticIR:
        if value.get("schema_version") != "1.0.0":
            raise RouteError("UNSUPPORTED_SEMANTIC_IR")
        source_language = str(value.get("source_language", ""))
        if source_language not in SUPPORTED_LANGUAGES:
            raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{source_language}")
        functions = value.get("functions")
        diagnostics = value.get("diagnostics", [])
        if not isinstance(functions, list) or not functions:
            raise RouteError("NO_SUPPORTED_FUNCTIONS")
        if not isinstance(diagnostics, list):
            raise RouteError("INVALID_DIAGNOSTICS")
        return cls(
            source_language=source_language,  # type: ignore[arg-type]
            source_file=str(value.get("source_file", "")),
            analyzer=str(value.get("analyzer", "")),
            analyzer_version=str(value.get("analyzer_version", "")),
            functions=tuple(Function.from_mapping(item) for item in functions if isinstance(item, dict)),
            diagnostics=tuple(str(item) for item in diagnostics),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "source_language": self.source_language,
            "source_file": self.source_file,
            "analyzer": self.analyzer,
            "analyzer_version": self.analyzer_version,
            "functions": [function.to_mapping() for function in self.functions],
            "diagnostics": list(self.diagnostics),
        }
