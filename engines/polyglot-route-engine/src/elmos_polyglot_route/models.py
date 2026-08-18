from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

Language = Literal[
    "java",
    "python",
    "csharp",
    "typescript",
    "javascript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
    "php",
]
SUPPORTED_LANGUAGES: tuple[Language, ...] = (
    "java",
    "python",
    "csharp",
    "typescript",
    "javascript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
    "php",
)

#: Languages this engine can lift *from*. Every supported language is also a
#: source: Swift is analyzed by the SwiftSyntax helper under
#: `native/swift`, which `native.analyze` builds on demand the same way the
#: TypeScript CLI is built. The distinction is kept as its own name because a
#: newly added target is a smaller change than a newly added source, and
#: callers that enumerate sources should say so explicitly.
ANALYZABLE_LANGUAGES: tuple[Language, ...] = SUPPORTED_LANGUAGES

#: The explicit complete route matrix.  Route-pack presence does not imply a
#: local pass, repository pass, independent verification, or certification;
#: those remain separate evidence-bound states for every direction.
COMPLETE_MATRIX_LANGUAGES: tuple[Language, ...] = (
    "java",
    "python",
    "csharp",
    "typescript",
    "javascript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
    "php",
)

#: Backwards-compatible name used by the Batch 29 inventory and relifters.
ROUTED_LANGUAGES: tuple[Language, ...] = COMPLETE_MATRIX_LANGUAGES

#: Exact routes that retain the stricter native module profile.  They are a
#: subset of the complete matrix, not the only routes for these languages.
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

#: Exact Node.js route expansion.  JavaScript is a separate language identity
#: from TypeScript: these 18 directions use Node.js ESM plus strict JSDoc
#: contracts and retain their own evidence/gate state.  They deliberately do
#: not extend ``SPECIALIZED_DIRECTED_PAIRS`` because that name and its eight
#: entries are an immutable Batch 29 proof scope.
NODEJS_DIRECTED_PAIRS: tuple[tuple[Language, Language], ...] = tuple(
    (source, target)
    for source in COMPLETE_MATRIX_LANGUAGES
    for target in COMPLETE_MATRIX_LANGUAGES
    if source != target and "javascript" in {source, target}
)

COMPLETE_MATRIX_DIRECTED_PAIRS: tuple[tuple[Language, Language], ...] = tuple(
    (source, target) for source in COMPLETE_MATRIX_LANGUAGES for target in COMPLETE_MATRIX_LANGUAGES if source != target
)

ROUTED_PAIRS: tuple[tuple[Language, Language], ...] = COMPLETE_MATRIX_DIRECTED_PAIRS

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
        return is_specialized_pair(source, target) or (source, target) in NODEJS_DIRECTED_PAIRS
    return True


#: Backwards-compatible inventory field.  The repository orchestration surface
#: now has an explicit route entry for every supported directed pair, so no
#: supported language remains engine-only.  Evidence strength is still
#: route-specific: the eight native/JVM pairs above use the specialised formal
#: profile, while every route keeps its own local, independent and certification
#: states.  An empty tuple must therefore not be read as a certification claim.
ENGINE_ONLY_LANGUAGES: tuple[Language, ...] = ()


class RouteError(ValueError):
    """Raised when a route cannot preserve the declared semantic subset."""


def _require_exact_keys(
    value: dict[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    path: str,
) -> None:
    """Require one closed SemanticIR object shape.

    SemanticIR is persisted as proof input, so silently dropping an unknown
    member is not forward compatibility: it lets the persisted bytes and
    digests claim a term different from the term the verifier reconstructs.
    Optional members are therefore explicit and every accepted mapping must
    survive ``from_mapping``/``to_mapping`` without losing a key.
    """

    observed = set(value)
    if not required.issubset(observed) or not observed.issubset(required | optional):
        raise RouteError(f"SEMANTIC_IR_KEYS_INVALID:{path}")


def _require_string(value: Any, path: str, *, nonempty: bool = False) -> str:
    if type(value) is not str or nonempty and (not value or value != value.strip()):
        raise RouteError(f"SEMANTIC_IR_STRING_INVALID:{path}")
    return value


def _require_mapping_list(value: Any, path: str, *, nonempty: bool = False) -> list[dict[str, Any]]:
    if type(value) is not list or nonempty and not value or any(type(item) is not dict for item in value):
        raise RouteError(f"SEMANTIC_IR_MAPPING_LIST_INVALID:{path}")
    return value


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
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "source_span") -> SourceSpan:
        _require_exact_keys(
            value,
            frozenset({"file", "start_byte", "end_byte"}),
            frozenset(),
            _path,
        )
        file = _require_string(value["file"], f"{_path}.file", nonempty=True)
        start_byte = value["start_byte"]
        end_byte = value["end_byte"]
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


def _optional_source_span(value: dict[str, Any], path: str) -> SourceSpan | None:
    if "source_span" not in value:
        return None
    span = value["source_span"]
    if type(span) is not dict:
        raise RouteError("INVALID_SOURCE_SPAN")
    return SourceSpan.from_mapping(span, _path=f"{path}.source_span")


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    source_span: SourceSpan | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "parameter") -> Parameter:
        _require_exact_keys(
            value,
            frozenset({"name", "type"}),
            frozenset({"source_span"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        parameter_type = _require_string(value["type"], f"{_path}.type")
        if not name or parameter_type not in {"integer", "number", "boolean", "string"}:
            raise RouteError("INVALID_PARAMETER")
        return cls(name=name, type=parameter_type, source_span=_optional_source_span(value, _path))

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
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "expression") -> Expression:
        if "kind" not in value:
            raise RouteError(f"SEMANTIC_IR_KEYS_INVALID:{_path}")
        kind = _require_string(value["kind"], f"{_path}.kind")
        if kind == "name":
            _require_exact_keys(
                value,
                frozenset({"kind", "value"}),
                frozenset({"source_span"}),
                _path,
            )
            name = _require_string(value["value"], f"{_path}.value", nonempty=True)
            return cls(
                kind=kind,
                value=name,
                source_span=_optional_source_span(value, _path),
            )
        if kind == "literal":
            _require_exact_keys(
                value,
                frozenset({"kind", "value"}),
                frozenset({"source_span"}),
                _path,
            )
            literal = value["value"]
            if type(literal) not in {str, int, float, bool, type(None)}:
                raise RouteError(f"SEMANTIC_IR_LITERAL_INVALID:{_path}.value")
            return cls(
                kind=kind,
                value=literal,
                source_span=_optional_source_span(value, _path),
            )
        if kind == "binary":
            _require_exact_keys(
                value,
                frozenset({"kind", "operator", "left", "right"}),
                frozenset({"source_span"}),
                _path,
            )
            operator = _require_string(value["operator"], f"{_path}.operator")
            if operator not in {"+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||"}:
                raise RouteError(f"UNSUPPORTED_OPERATOR:{operator}")
            left = value["left"]
            right = value["right"]
            if type(left) is not dict or type(right) is not dict:
                raise RouteError("BINARY_OPERANDS_REQUIRED")
            return cls(
                kind=kind,
                operator=operator,
                left=cls.from_mapping(left, _path=f"{_path}.left"),
                right=cls.from_mapping(right, _path=f"{_path}.right"),
                source_span=_optional_source_span(value, _path),
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
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "statement") -> Statement:
        if "kind" not in value:
            raise RouteError(f"SEMANTIC_IR_KEYS_INVALID:{_path}")
        kind = _require_string(value["kind"], f"{_path}.kind")
        if kind == "return":
            _require_exact_keys(
                value,
                frozenset({"kind", "expression"}),
                frozenset({"source_span"}),
                _path,
            )
            expression = value["expression"]
            if type(expression) is not dict:
                raise RouteError("RETURN_EXPRESSION_REQUIRED")
            return cls(
                kind=kind,
                expression=Expression.from_mapping(expression, _path=f"{_path}.expression"),
                source_span=_optional_source_span(value, _path),
            )
        if kind == "if":
            _require_exact_keys(
                value,
                frozenset({"kind", "condition", "then", "else"}),
                frozenset({"source_span"}),
                _path,
            )
            condition = value["condition"]
            then_body = value["then"]
            else_body = value["else"]
            if type(condition) is not dict:
                raise RouteError("INVALID_IF_STATEMENT")
            parsed_then = _require_mapping_list(then_body, f"{_path}.then")
            parsed_else = _require_mapping_list(else_body, f"{_path}.else")
            return cls(
                kind=kind,
                condition=Expression.from_mapping(condition, _path=f"{_path}.condition"),
                then_body=tuple(
                    cls.from_mapping(item, _path=f"{_path}.then[{index}]") for index, item in enumerate(parsed_then)
                ),
                else_body=tuple(
                    cls.from_mapping(item, _path=f"{_path}.else[{index}]") for index, item in enumerate(parsed_else)
                ),
                source_span=_optional_source_span(value, _path),
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
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "function") -> Function:
        _require_exact_keys(
            value,
            frozenset({"name", "parameters", "return_type", "body"}),
            frozenset({"source_span"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        return_type = _require_string(value["return_type"], f"{_path}.return_type")
        parameters = _require_mapping_list(value["parameters"], f"{_path}.parameters")
        body = _require_mapping_list(value["body"], f"{_path}.body", nonempty=True)
        if not name or return_type not in {"integer", "number", "boolean", "string"}:
            raise RouteError("INVALID_FUNCTION_SIGNATURE")
        return cls(
            name=name,
            parameters=tuple(
                Parameter.from_mapping(item, _path=f"{_path}.parameters[{index}]")
                for index, item in enumerate(parameters)
            ),
            return_type=return_type,
            body=tuple(Statement.from_mapping(item, _path=f"{_path}.body[{index}]") for index, item in enumerate(body)),
            source_span=_optional_source_span(value, _path),
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
        _require_exact_keys(
            value,
            frozenset(
                {
                    "schema_version",
                    "source_language",
                    "source_file",
                    "analyzer",
                    "analyzer_version",
                    "functions",
                    "diagnostics",
                }
            ),
            frozenset(),
            "semantic_ir",
        )
        schema_version = _require_string(value["schema_version"], "semantic_ir.schema_version")
        if schema_version != "1.0.0":
            raise RouteError("UNSUPPORTED_SEMANTIC_IR")
        source_language = _require_string(value["source_language"], "semantic_ir.source_language")
        if source_language not in SUPPORTED_LANGUAGES:
            raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{source_language}")
        source_file = _require_string(value["source_file"], "semantic_ir.source_file")
        analyzer = _require_string(value["analyzer"], "semantic_ir.analyzer")
        analyzer_version = _require_string(value["analyzer_version"], "semantic_ir.analyzer_version")
        functions = _require_mapping_list(value["functions"], "semantic_ir.functions", nonempty=True)
        diagnostics = value["diagnostics"]
        if type(diagnostics) is not list or any(type(item) is not str for item in diagnostics):
            raise RouteError("INVALID_DIAGNOSTICS")
        return cls(
            source_language=source_language,  # type: ignore[arg-type]
            source_file=source_file,
            analyzer=analyzer,
            analyzer_version=analyzer_version,
            functions=tuple(
                Function.from_mapping(item, _path=f"semantic_ir.functions[{index}]")
                for index, item in enumerate(functions)
            ),
            diagnostics=tuple(diagnostics),
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
