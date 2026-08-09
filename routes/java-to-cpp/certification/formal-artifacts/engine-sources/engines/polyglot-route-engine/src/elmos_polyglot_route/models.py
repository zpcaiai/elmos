from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

Language = Literal["java", "python", "csharp", "typescript", "go", "rust", "cpp", "objc", "swift"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = (
    "java",
    "python",
    "csharp",
    "typescript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
)

#: Languages this engine can lift *from*. Every supported language is also a
#: source: Swift is analyzed by the SwiftSyntax helper under
#: `native/swift`, which `native.analyze` builds on demand the same way the
#: TypeScript CLI is built. The distinction is kept as its own name because a
#: newly added target is a smaller change than a newly added source, and
#: callers that enumerate sources should say so explicitly.
ANALYZABLE_LANGUAGES: tuple[Language, ...] = SUPPORTED_LANGUAGES

#: The original complete route matrix.  Keeping this set separate is
#: important: adding the three specialised languages to it would silently
#: manufacture a 9-language/72-route claim that neither the route inventory
#: nor the evidence supports.
COMPLETE_MATRIX_LANGUAGES: tuple[Language, ...] = (
    "java",
    "python",
    "csharp",
    "typescript",
    "go",
    "rust",
)

#: Backwards-compatible name used by the original Batch 29 inventory and
#: native relifters.  It denotes the complete six-language matrix, not every
#: language that participates in any route.
ROUTED_LANGUAGES: tuple[Language, ...] = COMPLETE_MATRIX_LANGUAGES

#: Exact additional directed routes.  This is intentionally an allow-list,
#: not a Cartesian product over Java/C++/Objective-C/Swift.
SPECIALIZED_DIRECTED_PAIRS: tuple[tuple[Language, Language], ...] = (
    ("cpp", "objc"),
    ("objc", "cpp"),
    ("cpp", "swift"),
    ("swift", "cpp"),
    ("objc", "swift"),
    ("swift", "objc"),
    ("cpp", "java"),
    ("java", "cpp"),
)

COMPLETE_MATRIX_DIRECTED_PAIRS: tuple[tuple[Language, Language], ...] = tuple(
    (source, target) for source in COMPLETE_MATRIX_LANGUAGES for target in COMPLETE_MATRIX_LANGUAGES if source != target
)

ROUTED_PAIRS: tuple[tuple[Language, Language], ...] = (
    *COMPLETE_MATRIX_DIRECTED_PAIRS,
    *SPECIALIZED_DIRECTED_PAIRS,
)

TYPED_PURE_FUNCTION_PROFILE = "typed-pure-function-v1"
TYPED_PURE_MODULE_PROFILE = "typed-pure-module-v1"


def is_routed_pair(source: str, target: str) -> bool:
    """Return whether one exact directed route is explicitly declared.

    The function deliberately accepts strings because it is also an input
    boundary for CLI/API values.  Unknown languages and same-language routes
    fail closed rather than being coerced into the matrix.
    """

    return (source, target) in ROUTED_PAIRS


def is_specialized_pair(source: str, target: str) -> bool:
    return (source, target) in SPECIALIZED_DIRECTED_PAIRS


def requires_concrete_source_spans(source: str, target: str, profile: str) -> bool:
    """Explicit compatibility boundary for concrete chunk evidence.

    The existing 30 routes predate concrete analyzer spans and retain their
    semantic-pointer contract. New specialised routes and every module proof
    require real, byte-validated spans; unknown profiles fail closed.
    """

    if profile == TYPED_PURE_MODULE_PROFILE:
        return True
    if profile == TYPED_PURE_FUNCTION_PROFILE:
        return is_specialized_pair(source, target)
    return True


#: Languages outside the original complete matrix.  The historical name is
#: retained for compatibility, but these languages now participate only in
#: the exact specialised pairs above; they still must not be treated as a
#: complete submatrix.
#:
#: The distinction was previously implicit: `SUPPORTED_LANGUAGES` listed nine,
#: `routes/` held thirty pairs over six, and nothing reconciled the two. Read
#: from the engine the platform appeared to support seventy-two directed pairs;
#: read from `routes/` it supported thirty. Naming the gap is not the same as
#: closing it -- these three remain engine-only until they carry the same
#: evidence the other six do -- but a boundary that is written down can be
#: checked, and `tests/test_language_set.py` checks it.
ENGINE_ONLY_LANGUAGES: tuple[Language, ...] = ("cpp", "objc", "swift")


class RouteError(ValueError):
    """Raised when a route cannot preserve the declared semantic subset."""


@dataclass(frozen=True)
class SourceSpan:
    """Concrete UTF-8 byte range for one syntax node.

    ``start_byte`` is inclusive and ``end_byte`` exclusive.  ``file`` is a
    logical, relative POSIX path so evidence cannot smuggle an absolute or
    parent-traversing filesystem reference into a chunk map.
    """

    file: str
    start_byte: int
    end_byte: int

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> SourceSpan:
        file = str(value.get("file", "")).strip()
        start_byte = value.get("start_byte")
        end_byte = value.get("end_byte")
        logical_path = PurePosixPath(file) if file else PurePosixPath(".")
        if (
            not file
            or "\x00" in file
            or "\\" in file
            or logical_path.is_absolute()
            or "." in logical_path.parts
            or ".." in logical_path.parts
        ):
            raise RouteError("INVALID_SOURCE_SPAN_FILE")
        if type(start_byte) is not int or type(end_byte) is not int or start_byte < 0 or end_byte <= start_byte:
            raise RouteError("INVALID_SOURCE_SPAN_RANGE")
        return cls(file=file, start_byte=start_byte, end_byte=end_byte)

    def to_mapping(self) -> dict[str, str | int]:
        return {
            "file": self.file,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
        }


def _optional_source_span(value: dict[str, Any]) -> SourceSpan | None:
    span = value.get("source_span")
    if span is None:
        return None
    if not isinstance(span, dict):
        raise RouteError("INVALID_SOURCE_SPAN")
    return SourceSpan.from_mapping(span)


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    source_span: SourceSpan | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Parameter:
        name = str(value.get("name", "")).strip()
        parameter_type = str(value.get("type", "")).strip()
        if not name or parameter_type not in {"integer", "number", "boolean", "string"}:
            raise RouteError("INVALID_PARAMETER")
        return cls(name=name, type=parameter_type, source_span=_optional_source_span(value))

    def semantic_mapping(self) -> dict[str, str]:
        return {"name": self.name, "type": self.type}

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = self.semantic_mapping()
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        return result


@dataclass(frozen=True)
class Expression:
    kind: str
    value: str | int | float | bool | None = None
    operator: str | None = None
    left: Expression | None = None
    right: Expression | None = None
    source_span: SourceSpan | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Expression:
        kind = str(value.get("kind", ""))
        if kind in {"name", "literal"}:
            return cls(
                kind=kind,
                value=value.get("value"),
                source_span=_optional_source_span(value),
            )
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
                source_span=_optional_source_span(value),
            )
        raise RouteError(f"UNSUPPORTED_EXPRESSION:{kind}")

    def semantic_mapping(self) -> dict[str, Any]:
        if self.kind in {"name", "literal"}:
            return {"kind": self.kind, "value": self.value}
        if self.left is None or self.right is None or self.operator is None:
            raise RouteError("INVALID_BINARY_EXPRESSION")
        return {
            "kind": "binary",
            "operator": self.operator,
            "left": self.left.semantic_mapping(),
            "right": self.right.semantic_mapping(),
        }

    def to_mapping(self) -> dict[str, Any]:
        if self.kind in {"name", "literal"}:
            result = self.semantic_mapping()
        else:
            if self.left is None or self.right is None or self.operator is None:
                raise RouteError("INVALID_BINARY_EXPRESSION")
            result = {
                "kind": "binary",
                "operator": self.operator,
                "left": self.left.to_mapping(),
                "right": self.right.to_mapping(),
            }
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        return result


@dataclass(frozen=True)
class Statement:
    kind: str
    expression: Expression | None = None
    condition: Expression | None = None
    then_body: tuple[Statement, ...] = ()
    else_body: tuple[Statement, ...] = ()
    source_span: SourceSpan | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Statement:
        kind = str(value.get("kind", ""))
        if kind == "return":
            expression = value.get("expression")
            if not isinstance(expression, dict):
                raise RouteError("RETURN_EXPRESSION_REQUIRED")
            return cls(
                kind=kind,
                expression=Expression.from_mapping(expression),
                source_span=_optional_source_span(value),
            )
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
                source_span=_optional_source_span(value),
            )
        raise RouteError(f"UNSUPPORTED_STATEMENT:{kind}")

    def semantic_mapping(self) -> dict[str, Any]:
        if self.kind == "return" and self.expression is not None:
            return {"kind": "return", "expression": self.expression.semantic_mapping()}
        if self.kind == "if" and self.condition is not None:
            return {
                "kind": "if",
                "condition": self.condition.semantic_mapping(),
                "then": [item.semantic_mapping() for item in self.then_body],
                "else": [item.semantic_mapping() for item in self.else_body],
            }
        raise RouteError("INVALID_STATEMENT")

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any]
        if self.kind == "return" and self.expression is not None:
            result = {"kind": "return", "expression": self.expression.to_mapping()}
        elif self.kind == "if" and self.condition is not None:
            result = {
                "kind": "if",
                "condition": self.condition.to_mapping(),
                "then": [item.to_mapping() for item in self.then_body],
                "else": [item.to_mapping() for item in self.else_body],
            }
        else:
            raise RouteError("INVALID_STATEMENT")
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        return result


@dataclass(frozen=True)
class Function:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: str
    body: tuple[Statement, ...]
    source_span: SourceSpan | None = None

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
            source_span=_optional_source_span(value),
        )

    def signature_mapping(self) -> dict[str, Any]:
        return {
            "parameters": [parameter.semantic_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
        }

    def semantic_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameters": [parameter.semantic_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.semantic_mapping() for statement in self.body],
        }

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "parameters": [parameter.to_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.to_mapping() for statement in self.body],
        }
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        return result


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

    def semantic_mapping(self) -> dict[str, Any]:
        """Canonical semantics with all concrete source locations removed."""

        return {
            "schema_version": "1.0.0",
            "source_language": self.source_language,
            "functions": [function.semantic_mapping() for function in self.functions],
            "diagnostics": list(self.diagnostics),
        }
