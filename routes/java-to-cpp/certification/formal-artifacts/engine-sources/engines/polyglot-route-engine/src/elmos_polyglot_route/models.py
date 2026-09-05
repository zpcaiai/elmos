from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

Language = Literal[
    "java",
    "python",
    "csharp",
    "typescript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
    "php",
    "kotlin",
    "react",
    "flutter",
    # Deprecated.  Kept in the type so the Node.js analyzer, emitter, assembly
    # and evidence machinery that still ships in this engine remains typed.  It
    # is deliberately absent from ``SUPPORTED_LANGUAGES`` below: no javascript
    # direction is part of the active route matrix any more.
    "javascript",
]

#: Languages that are no longer part of the supported set but whose engine
#: machinery and filed evidence stay in place.  A deprecated language is not a
#: route source, not a route target, and not a member of any active route set;
#: its packs under ``routes/`` and its provenance partition names are retained
#: unchanged so archived evidence keeps its address.
DEPRECATED_LANGUAGES: tuple[Language, ...] = ("javascript",)

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
    "php",
    "kotlin",
    "react",
    "flutter",
)

#: Languages that are declared in the route matrix but have no native analyzer
#: yet.  They are real matrix members -- every direction naming them has a
#: route pack and a provenance owner -- but any attempt to *lift from* them
#: fails closed with ``SOURCE_ANALYZER_NOT_IMPLEMENTED`` rather than silently
#: producing an unbacked SemanticIR.  Moving a language out of this tuple is
#: the single edit that turns its analyzer on, and it must not happen before a
#: pinned toolchain and a real analyzer exist for it.
PENDING_ANALYZER_LANGUAGES: tuple[Language, ...] = ()

#: Languages this engine can lift *from*.  This was an alias for
#: ``SUPPORTED_LANGUAGES`` while every supported language had an analyzer.  It
#: remains an explicit tuple so future matrix declarations cannot silently
#: claim analyzer support; aliasing it to ``SUPPORTED_LANGUAGES`` would make
#: ``PENDING_ANALYZER_LANGUAGES`` decorative.  Swift is analyzed by the
#: SwiftSyntax helper under `native/swift`, which `native.analyze` builds on
#: demand the same way the TypeScript CLI is built.
ANALYZABLE_LANGUAGES: tuple[Language, ...] = tuple(
    language for language in SUPPORTED_LANGUAGES if language not in PENDING_ANALYZER_LANGUAGES
)

#: Languages whose exact single-unit source analyzer exists, but whose
#: repository-wide inventory, discovery, placement, build, and relift surface
#: is not complete.  This is intentionally independent of analyzer readiness:
#: promoting a parser must not silently promote whole-repository support.
PENDING_REPOSITORY_LANGUAGES: tuple[Language, ...] = ()

#: Languages the repository orchestration surface actually handles end to end:
#: source inventory extensions, discovery declaration patterns, target project
#: placement and target build files.  This is deliberately NOT
#: ``SUPPORTED_LANGUAGES``. A repository-pending language is a declared matrix
#: member with no complete repository surface yet, and a deprecated language keeps its
#: repository surface so filed evidence stays reproducible.  Adding a stub
#: extension or placer for a pending language just to make a set comparison
#: pass would claim support that does not exist.
REPOSITORY_SURFACE_LANGUAGES: tuple[Language, ...] = tuple(
    language
    for language in (*SUPPORTED_LANGUAGES, *DEPRECATED_LANGUAGES)
    if language not in PENDING_REPOSITORY_LANGUAGES
)

REPOSITORY_LANGUAGE_LIFECYCLE_ACTIVE = "ACTIVE"
REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY = "DEPRECATED_REPLAY"


def repository_language_lifecycle(
    source_language: object,
    target_language: object,
) -> str | None:
    """Classify a repository pair without reviving a deprecated direction."""

    if source_language in SUPPORTED_LANGUAGES and target_language in SUPPORTED_LANGUAGES:
        return REPOSITORY_LANGUAGE_LIFECYCLE_ACTIVE
    if (source_language, target_language) in DEPRECATED_DIRECTED_PAIRS:
        return REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY
    return None

#: The explicit complete route matrix.  Route-pack presence does not imply a
#: local pass, repository pass, independent verification, or certification;
#: those remain separate evidence-bound states for every direction.
COMPLETE_MATRIX_LANGUAGES: tuple[Language, ...] = SUPPORTED_LANGUAGES

#: Backwards-compatible name used by the Batch 29 inventory and relifters.
ROUTED_LANGUAGES: tuple[Language, ...] = COMPLETE_MATRIX_LANGUAGES

#: Exact routes that retain the stricter native module profile.  They are a
#: subset of the complete matrix, not the only routes for these languages.
#: Unchanged by the thirteen-language expansion: all eight survive because the
#: matrix stayed a full cartesian product.
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
#: from TypeScript: these 20 directions use Node.js ESM plus strict JSDoc
#: contracts and retain their own evidence/gate state.
#:
#: PINNED TO A LITERAL.  This used to be a comprehension over
#: ``COMPLETE_MATRIX_LANGUAGES`` filtered on ``"javascript" in {source, target}``.
#: Deprecating javascript would have silently evaluated that comprehension to
#: an empty tuple -- no error, no failing import -- and
#: ``requires_concrete_source_spans`` would have flipped these 20 directions
#: from the relaxed span contract to the strict one.  The value is frozen here
#: precisely so that removing the language cannot rewrite it.
NODEJS_DIRECTED_PAIRS: tuple[tuple[Language, Language], ...] = (
    ("java", "javascript"),
    ("python", "javascript"),
    ("csharp", "javascript"),
    ("typescript", "javascript"),
    ("javascript", "java"),
    ("javascript", "python"),
    ("javascript", "csharp"),
    ("javascript", "typescript"),
    ("javascript", "go"),
    ("javascript", "rust"),
    ("javascript", "cpp"),
    ("javascript", "objc"),
    ("javascript", "swift"),
    ("javascript", "php"),
    ("go", "javascript"),
    ("rust", "javascript"),
    ("cpp", "javascript"),
    ("objc", "javascript"),
    ("swift", "javascript"),
    ("php", "javascript"),
)

#: Directions that left the active matrix with javascript.  Identical in value
#: to ``NODEJS_DIRECTED_PAIRS``; named separately because one is a provenance
#: label for filed evidence and the other is a lifecycle state.
DEPRECATED_DIRECTED_PAIRS: tuple[tuple[Language, Language], ...] = NODEJS_DIRECTED_PAIRS

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
#: has an explicit route entry for every supported directed pair, so no
#: supported language is reachable only inside the engine.  This is a different
#: axis from ``PENDING_ANALYZER_LANGUAGES``: those languages *are* routed, they
#: simply cannot yet be lifted from.  Evidence strength is still route-specific:
#: the eight native/JVM pairs above use the specialised formal profile, while
#: every route keeps its own local, independent and certification states.  An
#: empty tuple must therefore not be read as a certification claim.
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


def _is_valid_type_name(t: str) -> bool:
    return t in {"integer", "number", "boolean", "string"} or (t.isidentifier() and not t.startswith("_"))


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
        if not name or not _is_valid_type_name(parameter_type):
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
class RecordDefinition:
    name: str
    fields: tuple[Parameter, ...]
    source_span: SourceSpan | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "record") -> RecordDefinition:
        _require_exact_keys(
            value,
            frozenset({"name", "fields"}),
            frozenset({"source_span"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        if not _is_valid_type_name(name) or name in {"integer", "number", "boolean", "string"}:
            raise RouteError("INVALID_RECORD_NAME")
        raw_fields = _require_mapping_list(value["fields"], f"{_path}.fields", nonempty=True)
        field_names = set()
        parsed_fields: list[Parameter] = []
        for index, item in enumerate(raw_fields):
            param = Parameter.from_mapping(item, _path=f"{_path}.fields[{index}]")
            if param.name in field_names:
                raise RouteError(f"DUPLICATE_RECORD_FIELD:{param.name}")
            field_names.add(param.name)
            parsed_fields.append(param)
        return cls(
            name=name,
            fields=tuple(parsed_fields),
            source_span=_optional_source_span(value, _path),
        )

    def semantic_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fields": [f.semantic_mapping() for f in self.fields],
        }

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "fields": [f.to_mapping() for f in self.fields],
        }
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
    record_name: str | None = None
    arguments: tuple[tuple[str, Expression], ...] = ()
    target: Expression | None = None
    member: str | None = None
    function_name: str | None = None
    call_arguments: tuple[Expression, ...] = ()
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
        if kind == "member_access":
            _require_exact_keys(
                value,
                frozenset({"kind", "target", "member"}),
                frozenset({"source_span"}),
                _path,
            )
            target_raw = value["target"]
            if type(target_raw) is not dict:
                raise RouteError(f"INVALID_MEMBER_ACCESS_TARGET:{_path}.target")
            target = cls.from_mapping(target_raw, _path=f"{_path}.target")
            member = _require_string(value["member"], f"{_path}.member", nonempty=True)
            return cls(
                kind=kind,
                target=target,
                member=member,
                source_span=_optional_source_span(value, _path),
            )
        if kind == "record_construct":
            _require_exact_keys(
                value,
                frozenset({"kind", "record_name", "arguments"}),
                frozenset({"source_span"}),
                _path,
            )
            record_name = _require_string(value["record_name"], f"{_path}.record_name", nonempty=True)
            args_raw = value["arguments"]
            if type(args_raw) is not dict:
                raise RouteError(f"INVALID_RECORD_CONSTRUCT_ARGUMENTS:{_path}.arguments")
            parsed_args: list[tuple[str, Expression]] = []
            for arg_k, arg_v in args_raw.items():
                if type(arg_k) is not str or not arg_k or type(arg_v) is not dict:
                    raise RouteError(f"INVALID_RECORD_ARGUMENT:{_path}.arguments.{arg_k}")
                parsed_args.append((arg_k, cls.from_mapping(arg_v, _path=f"{_path}.arguments.{arg_k}")))
            return cls(
                kind=kind,
                record_name=record_name,
                arguments=tuple(parsed_args),
                source_span=_optional_source_span(value, _path),
            )
        if kind == "call":
            _require_exact_keys(
                value,
                frozenset({"kind", "function_name", "arguments"}),
                frozenset({"source_span"}),
                _path,
            )
            fn_name = _require_string(value["function_name"], f"{_path}.function_name", nonempty=True)
            args_raw = value["arguments"]
            if type(args_raw) is not list:
                raise RouteError(f"INVALID_CALL_ARGUMENTS:{_path}.arguments")
            call_args = tuple(
                cls.from_mapping(arg_item, _path=f"{_path}.arguments[{i}]")
                for i, arg_item in enumerate(args_raw)
            )
            return cls(
                kind=kind,
                function_name=fn_name,
                call_arguments=call_args,
                source_span=_optional_source_span(value, _path),
            )
        raise RouteError(f"UNSUPPORTED_EXPRESSION:{kind}")

    def semantic_mapping(self) -> dict[str, Any]:
        if self.kind in {"name", "literal"}:
            return {"kind": self.kind, "value": self.value}
        if self.kind == "member_access":
            if self.target is None or self.member is None:
                raise RouteError("INVALID_MEMBER_ACCESS_EXPRESSION")
            return {
                "kind": "member_access",
                "target": self.target.semantic_mapping(),
                "member": self.member,
            }
        if self.kind == "record_construct":
            if self.record_name is None:
                raise RouteError("INVALID_RECORD_CONSTRUCT_EXPRESSION")
            return {
                "kind": "record_construct",
                "record_name": self.record_name,
                "arguments": {k: v.semantic_mapping() for k, v in self.arguments},
            }
        if self.kind == "call":
            if self.function_name is None:
                raise RouteError("INVALID_CALL_EXPRESSION")
            return {
                "kind": "call",
                "function_name": self.function_name,
                "arguments": [arg.semantic_mapping() for arg in self.call_arguments],
            }
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
        elif self.kind == "member_access":
            if self.target is None or self.member is None:
                raise RouteError("INVALID_MEMBER_ACCESS_EXPRESSION")
            result = {
                "kind": "member_access",
                "target": self.target.to_mapping(),
                "member": self.member,
            }
        elif self.kind == "record_construct":
            if self.record_name is None:
                raise RouteError("INVALID_RECORD_CONSTRUCT_EXPRESSION")
            result = {
                "kind": "record_construct",
                "record_name": self.record_name,
                "arguments": {k: v.to_mapping() for k, v in self.arguments},
            }
        elif self.kind == "call":
            if self.function_name is None:
                raise RouteError("INVALID_CALL_EXPRESSION")
            result = {
                "kind": "call",
                "function_name": self.function_name,
                "arguments": [arg.to_mapping() for arg in self.call_arguments],
            }
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
    #: `let` only: the bound name and its declared canonical type.
    name: str | None = None
    declared_type: str | None = None
    #: `for` only: monotonic iteration loop
    start: Expression | None = None
    end: Expression | None = None
    step: Expression | None = None
    #: `while` and `for` loop body
    body: tuple[Statement, ...] = ()
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
        if kind == "let":
            # A single-assignment local binding.
            _require_exact_keys(
                value,
                frozenset({"kind", "name", "type", "expression"}),
                frozenset({"source_span"}),
                _path,
            )
            name = _require_string(value["name"], f"{_path}.name")
            declared_type = _require_string(value["type"], f"{_path}.type")
            if not name:
                raise RouteError(f"LET_NAME_REQUIRED:{_path}")
            expression = value["expression"]
            if type(expression) is not dict:
                raise RouteError(f"LET_EXPRESSION_REQUIRED:{_path}")
            return cls(
                kind=kind,
                name=name,
                declared_type=declared_type,
                expression=Expression.from_mapping(expression, _path=f"{_path}.expression"),
                source_span=_optional_source_span(value, _path),
            )
        if kind == "while":
            _require_exact_keys(
                value,
                frozenset({"kind", "condition", "body"}),
                frozenset({"source_span"}),
                _path,
            )
            condition = value["condition"]
            if type(condition) is not dict:
                raise RouteError(f"INVALID_WHILE_STATEMENT:{_path}")
            parsed_body = _require_mapping_list(value["body"], f"{_path}.body")
            return cls(
                kind=kind,
                condition=Expression.from_mapping(condition, _path=f"{_path}.condition"),
                body=tuple(
                    cls.from_mapping(item, _path=f"{_path}.body[{index}]")
                    for index, item in enumerate(parsed_body)
                ),
                source_span=_optional_source_span(value, _path),
            )
        if kind == "for":
            _require_exact_keys(
                value,
                frozenset({"kind", "name", "type", "start", "end", "body"}),
                frozenset({"step", "source_span"}),
                _path,
            )
            name = _require_string(value["name"], f"{_path}.name")
            if not name:
                raise RouteError(f"FOR_NAME_REQUIRED:{_path}")
            declared_type = _require_string(value["type"], f"{_path}.type")
            start = value["start"]
            end = value["end"]
            if type(start) is not dict or type(end) is not dict:
                raise RouteError(f"INVALID_FOR_STATEMENT:{_path}")
            step = value.get("step")
            if step is not None and type(step) is not dict:
                raise RouteError(f"INVALID_FOR_STEP:{_path}")
            parsed_body = _require_mapping_list(value["body"], f"{_path}.body")
            return cls(
                kind=kind,
                name=name,
                declared_type=declared_type,
                start=Expression.from_mapping(start, _path=f"{_path}.start"),
                end=Expression.from_mapping(end, _path=f"{_path}.end"),
                step=Expression.from_mapping(step, _path=f"{_path}.step") if step is not None else None,
                body=tuple(
                    cls.from_mapping(item, _path=f"{_path}.body[{index}]")
                    for index, item in enumerate(parsed_body)
                ),
                source_span=_optional_source_span(value, _path),
            )
        if kind == "break":
            _require_exact_keys(
                value,
                frozenset({"kind"}),
                frozenset({"source_span"}),
                _path,
            )
            return cls(kind=kind, source_span=_optional_source_span(value, _path))
        if kind == "continue":
            _require_exact_keys(
                value,
                frozenset({"kind"}),
                frozenset({"source_span"}),
                _path,
            )
            return cls(kind=kind, source_span=_optional_source_span(value, _path))
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
        if self.kind == "let" and self.expression is not None:
            return {
                "kind": "let",
                "name": self.name,
                "type": self.declared_type,
                "expression": self.expression.semantic_mapping(),
            }
        if self.kind == "while" and self.condition is not None:
            return {
                "kind": "while",
                "condition": self.condition.semantic_mapping(),
                "body": [item.semantic_mapping() for item in self.body],
            }
        if self.kind == "for" and self.name is not None and self.start is not None and self.end is not None:
            res: dict[str, Any] = {
                "kind": "for",
                "name": self.name,
                "type": self.declared_type,
                "start": self.start.semantic_mapping(),
                "end": self.end.semantic_mapping(),
                "body": [item.semantic_mapping() for item in self.body],
            }
            if self.step is not None:
                res["step"] = self.step.semantic_mapping()
            return res
        if self.kind == "break":
            return {"kind": "break"}
        if self.kind == "continue":
            return {"kind": "continue"}
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
        elif self.kind == "let" and self.expression is not None:
            result = {
                "kind": "let",
                "name": self.name,
                "type": self.declared_type,
                "expression": self.expression.to_mapping(),
            }
        elif self.kind == "while" and self.condition is not None:
            result = {
                "kind": "while",
                "condition": self.condition.to_mapping(),
                "body": [item.to_mapping() for item in self.body],
            }
        elif self.kind == "for" and self.name is not None and self.start is not None and self.end is not None:
            result = {
                "kind": "for",
                "name": self.name,
                "type": self.declared_type,
                "start": self.start.to_mapping(),
                "end": self.end.to_mapping(),
                "body": [item.to_mapping() for item in self.body],
            }
            if self.step is not None:
                result["step"] = self.step.to_mapping()
        elif self.kind == "break":
            result = {"kind": "break"}
        elif self.kind == "continue":
            result = {"kind": "continue"}
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
    #: Source-language documentation attached to the declaration (a Python
    #: docstring; the equivalent in other frontends can follow).
    #:
    #: This is PROVENANCE, not semantics, and the distinction is load-bearing:
    #: it appears in `to_mapping` -- so nothing the source carried is silently
    #: dropped and the artifact digest reflects it -- and NOT in
    #: `semantic_mapping`, so source/target equivalence is never asked to
    #: compare a Python `__doc__` against a Java method that has no such
    #: concept. Functions without documentation serialize byte-identically to
    #: before this field existed, so previously recorded IR digests still hold.
    documentation: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, _path: str = "function") -> Function:
        _require_exact_keys(
            value,
            frozenset({"name", "parameters", "return_type", "body"}),
            frozenset({"source_span", "documentation"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        return_type = _require_string(value["return_type"], f"{_path}.return_type")
        documentation = (
            # An empty docstring is legal Python and stays distinguishable from
            # "no docstring at all", so `nonempty` is deliberately not required.
            _require_string(value["documentation"], f"{_path}.documentation")
            if "documentation" in value
            else None
        )
        parameters = _require_mapping_list(value["parameters"], f"{_path}.parameters")
        body = _require_mapping_list(value["body"], f"{_path}.body", nonempty=True)
        if not name or not _is_valid_type_name(return_type):
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
            documentation=documentation,
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
        if self.documentation is not None:
            result["documentation"] = self.documentation
        return result


@dataclass(frozen=True)
class SemanticIR:
    source_language: Language
    source_file: str
    analyzer: str
    analyzer_version: str
    functions: tuple[Function, ...]
    diagnostics: tuple[str, ...]
    records: tuple[RecordDefinition, ...] = ()

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
            frozenset({"records"}),
            "semantic_ir",
        )
        schema_version = _require_string(value["schema_version"], "semantic_ir.schema_version")
        if schema_version != "1.0.0":
            raise RouteError("UNSUPPORTED_SEMANTIC_IR")
        source_language = _require_string(value["source_language"], "semantic_ir.source_language")
        if source_language not in SUPPORTED_LANGUAGES and source_language not in DEPRECATED_LANGUAGES:
            raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{source_language}")
        if source_language in PENDING_ANALYZER_LANGUAGES:
            # A matrix member without an analyzer must not be able to produce a
            # SemanticIR at all: accepting one here would let a hand-written or
            # mislabelled IR masquerade as a real lift.
            raise RouteError(f"SOURCE_ANALYZER_NOT_IMPLEMENTED:{source_language}")
        source_file = _require_string(value["source_file"], "semantic_ir.source_file")
        analyzer = _require_string(value["analyzer"], "semantic_ir.analyzer")
        analyzer_version = _require_string(value["analyzer_version"], "semantic_ir.analyzer_version")
        functions = _require_mapping_list(value["functions"], "semantic_ir.functions", nonempty=True)
        diagnostics = value["diagnostics"]
        if type(diagnostics) is not list or any(type(item) is not str for item in diagnostics):
            raise RouteError("INVALID_DIAGNOSTICS")
        raw_records = value.get("records", [])
        if type(raw_records) is not list or any(type(item) is not dict for item in raw_records):
            raise RouteError("INVALID_SEMANTIC_IR_RECORDS")
        records = tuple(
            RecordDefinition.from_mapping(item, _path=f"semantic_ir.records[{index}]")
            for index, item in enumerate(raw_records)
        )
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
            records=records,
        )

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": "1.0.0",
            "source_language": self.source_language,
            "source_file": self.source_file,
            "analyzer": self.analyzer,
            "analyzer_version": self.analyzer_version,
            "functions": [function.to_mapping() for function in self.functions],
            "diagnostics": list(self.diagnostics),
        }
        if self.records:
            result["records"] = [record.to_mapping() for record in self.records]
        return result

    def semantic_mapping(self) -> dict[str, Any]:
        """Canonical semantics with all concrete source locations removed."""

        result: dict[str, Any] = {
            "schema_version": "1.0.0",
            "source_language": self.source_language,
            "functions": [function.semantic_mapping() for function in self.functions],
            "diagnostics": list(self.diagnostics),
        }
        if self.records:
            result["records"] = [record.semantic_mapping() for record in self.records]
        return result
