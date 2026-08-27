"""Per-language symbol and reference extraction.

Two tiers, and the tier is always recorded on the output so nothing downstream
can mistake one for the other:

``compiler`` (confidence 1.0)
    Python, through the standard-library :mod:`ast`.  Definitions, imports,
    calls, attribute reads/writes, inheritance and decorators are exact, with
    real source ranges.  Dynamic constructs (``getattr``, ``importlib``,
    ``globals()``, ``__getattr__``, string-keyed dispatch) are detected and
    emitted as *dynamic* references, so a rename that could break them raises
    unknown-risk instead of silently succeeding.

``syntactic`` (confidence < 1.0)
    Every other language, through a comment- and string-stripped declaration
    scanner with per-language grammar fragments.  These results are real —
    a Java class declaration is found where it is — but they are typed as
    unresolved, so an L2 operation (change-signature, type-aware rename) is
    refused for those languages rather than attempted on partial data.

Nothing here executes repository content.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .contracts import EntityKind, RelationshipType

#: Constructs that can reach a symbol without naming it statically.
DYNAMIC_PYTHON_CALLS = frozenset(
    {
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "eval",
        "exec",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
    }
)

DYNAMIC_PYTHON_ATTRS = frozenset(
    {
        "importlib.import_module",
        "importlib.util.find_spec",
        "pkgutil.iter_modules",
        "operator.attrgetter",
        "operator.methodcaller",
    }
)


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "startLine": self.start_line,
            "startColumn": self.start_column,
            "endLine": self.end_line,
            "endColumn": self.end_column,
        }


@dataclass(frozen=True, slots=True)
class ExtractedSymbol:
    kind: EntityKind
    name: str
    qualified_name: str
    span: SourceSpan
    signature: str = ""
    visibility: str = "unknown"
    parent: str = ""
    confidence: Decimal = Decimal("1")
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def exported(self) -> bool:
        return self.visibility in ("public", "exported")


@dataclass(frozen=True, slots=True)
class ExtractedReference:
    type: RelationshipType
    name: str
    span: SourceSpan
    qualified_hint: str = ""
    from_symbol: str = ""
    confidence: Decimal = Decimal("1")
    dynamic: bool = False
    detail: str = ""
    #: For dynamic references, what the computed name can reach:
    #: ``attribute`` (``getattr(obj, ...)`` — only members of that object) or
    #: ``module`` (``eval``, ``globals()``, ``importlib`` — anything at module
    #: scope).  The distinction is what keeps a ``getattr`` on ``self`` from
    #: blocking every unrelated module-level rename in the same file.
    dynamic_scope: str = ""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    path: str
    language: str
    engine: str
    parsed: bool
    symbols: tuple[ExtractedSymbol, ...] = ()
    references: tuple[ExtractedReference, ...] = ()
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    dynamic_markers: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    base_confidence: Decimal = Decimal("1")

    @property
    def resolved(self) -> bool:
        return self.parsed and self.engine == "compiler"


# ---------------------------------------------------------------------------
# Python — exact
# ---------------------------------------------------------------------------


def _dotted(node: ast.AST) -> str:
    """Render an attribute/name chain, or ``""`` when it is not static."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


def _span(node: ast.AST) -> SourceSpan:
    start_line = getattr(node, "lineno", 1)
    start_col = getattr(node, "col_offset", 0)
    end_line = getattr(node, "end_lineno", None) or start_line
    end_col = getattr(node, "end_col_offset", None)
    return SourceSpan(start_line, start_col, end_line, start_col if end_col is None else end_col)


def _python_visibility(name: str) -> str:
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    if name.startswith("_"):
        return "internal"
    return "public"


def _python_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parts: list[str] = []
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    defaults_offset = len(positional) - len(args.defaults)
    for index, argument in enumerate(positional):
        rendered = argument.arg
        if argument.annotation is not None:
            rendered += f": {ast.unparse(argument.annotation)}"
        if index >= defaults_offset:
            rendered += "=..."
        parts.append(rendered)
    if args.vararg is not None:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for argument, default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
        rendered = argument.arg
        if argument.annotation is not None:
            rendered += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            rendered += "=..."
        parts.append(rendered)
    if args.kwarg is not None:
        parts.append(f"**{args.kwarg.arg}")
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"({', '.join(parts)}){returns}"


class _PythonVisitor(ast.NodeVisitor):
    """Single pass producing symbols, references and dynamic markers."""

    def __init__(self, module: str) -> None:
        self.module = module
        self.symbols: list[ExtractedSymbol] = []
        self.references: list[ExtractedReference] = []
        self.imports: list[str] = []
        self.exports: list[str] = []
        self.dynamic: list[str] = []
        self._scope: list[str] = [module]
        self._class_depth = 0

    # -- helpers ---------------------------------------------------------

    @property
    def _current(self) -> str:
        return ".".join(self._scope)

    def _qualified(self, name: str) -> str:
        return f"{self._current}.{name}"

    # -- definitions -----------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast API
        qualified = self._qualified(node.name)
        self.symbols.append(
            ExtractedSymbol(
                kind=EntityKind.TYPE,
                name=node.name,
                qualified_name=qualified,
                span=_span(node),
                signature=f"class {node.name}",
                visibility=_python_visibility(node.name),
                parent=self._current,
                attributes={
                    "decorators": [ast.unparse(item) for item in node.decorator_list],
                    "bases": [ast.unparse(item) for item in node.bases],
                },
            )
        )
        for base in node.bases:
            rendered = _dotted(base) or ast.unparse(base)
            self.references.append(
                ExtractedReference(
                    type=RelationshipType.INHERITS,
                    name=rendered,
                    span=_span(base),
                    from_symbol=qualified,
                )
            )
        self._scope.append(node.name)
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1
        self._scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = self._qualified(node.name)
        self.symbols.append(
            ExtractedSymbol(
                kind=EntityKind.METHOD if self._class_depth else EntityKind.FUNCTION,
                name=node.name,
                qualified_name=qualified,
                span=_span(node),
                signature=_python_signature(node),
                visibility=_python_visibility(node.name),
                parent=self._current,
                attributes={
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [ast.unparse(item) for item in node.decorator_list],
                    "arity": len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs),
                    "annotated": all(
                        argument.annotation is not None
                        for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                    ),
                },
            )
        )
        for decorator in node.decorator_list:
            rendered = _dotted(decorator) or ast.unparse(decorator)
            if rendered in ("override", "typing.override", "abc.abstractmethod"):
                self.references.append(
                    ExtractedReference(
                        type=RelationshipType.OVERRIDES,
                        name=node.name,
                        span=_span(decorator),
                        from_symbol=qualified,
                    )
                )
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast API
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast API
        self._visit_function(node)

    # -- imports ---------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast API
        for alias in node.names:
            self.imports.append(alias.name)
            self.references.append(
                ExtractedReference(
                    type=RelationshipType.IMPORTS,
                    name=alias.name,
                    span=_span(node),
                    from_symbol=self.module,
                    detail=f"as {alias.asname}" if alias.asname else "",
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast API
        base = node.module or ""
        prefix = "." * node.level
        for alias in node.names:
            target = f"{prefix}{base}.{alias.name}" if base else f"{prefix}{alias.name}"
            self.imports.append(target)
            self.references.append(
                ExtractedReference(
                    type=RelationshipType.IMPORTS,
                    name=target,
                    span=_span(node),
                    from_symbol=self.module,
                    detail=f"relative-level={node.level}" if node.level else "",
                )
            )
        self.generic_visit(node)

    # -- uses ------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast API
        rendered = _dotted(node.func)
        if rendered:
            self.references.append(
                ExtractedReference(
                    type=RelationshipType.CALLS,
                    name=rendered,
                    span=_span(node),
                    from_symbol=self._current,
                )
            )
            root = rendered.split(".", 1)[0]
            if rendered in DYNAMIC_PYTHON_ATTRS or root in DYNAMIC_PYTHON_CALLS:
                literal = _first_string_argument(node)
                scope = _dynamic_scope(rendered, root)
                self.dynamic.append(f"{rendered}@{node.lineno}" + (f":{literal}" if literal else ""))
                self.references.append(
                    ExtractedReference(
                        type=RelationshipType.REFERENCES,
                        name=literal or rendered,
                        span=_span(node),
                        from_symbol=self._current,
                        confidence=Decimal("0.5") if literal else Decimal("0.2"),
                        dynamic=True,
                        detail=f"dynamic-via:{rendered}",
                        dynamic_scope=scope,
                    )
                )
        else:
            self.dynamic.append(f"computed-callee@{node.lineno}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast API
        rendered = _dotted(node)
        if rendered:
            is_write = isinstance(getattr(node, "ctx", None), ast.Store)
            self.references.append(
                ExtractedReference(
                    type=RelationshipType.WRITES if is_write else RelationshipType.READS,
                    name=rendered,
                    span=_span(node),
                    from_symbol=self._current,
                )
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802 - ast API
        if isinstance(node.ctx, ast.Load):
            self.references.append(
                ExtractedReference(
                    type=RelationshipType.REFERENCES,
                    name=node.id,
                    span=_span(node),
                    from_symbol=self._current,
                )
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast API
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                self.exports.extend(_string_sequence(node.value))
            if isinstance(target, ast.Name) and len(self._scope) == 1:
                self.symbols.append(
                    ExtractedSymbol(
                        kind=EntityKind.VARIABLE,
                        name=target.id,
                        qualified_name=self._qualified(target.id),
                        span=_span(target),
                        visibility=_python_visibility(target.id),
                        parent=self._current,
                    )
                )
        self.generic_visit(node)


#: ``getattr``-family calls reach only members of the object they are given;
#: ``eval``-family calls reach module scope.
_ATTRIBUTE_SCOPED = frozenset({"getattr", "setattr", "hasattr", "delattr"})


def _dynamic_scope(rendered: str, root: str) -> str:
    if root in _ATTRIBUTE_SCOPED or rendered.startswith("operator."):
        return "attribute"
    return "module"


def _first_string_argument(node: ast.Call) -> str:
    for argument in node.args:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return argument.value
    return ""


def _string_sequence(node: ast.AST | None) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple):
        return [
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
    return []


def _module_name(path: str) -> str:
    trimmed = path[:-3] if path.endswith(".py") else path
    if trimmed.endswith("/__init__"):
        trimmed = trimmed[: -len("/__init__")]
    for prefix in ("src/", "lib/"):
        if trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix) :]
            break
    return trimmed.replace("/", ".")


def extract_python(path: str, text: str) -> ExtractionResult:
    module = _module_name(path)
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        return ExtractionResult(
            path=path,
            language="python",
            engine="compiler",
            parsed=False,
            errors=(f"syntax-error:line {error.lineno}: {error.msg}",),
            base_confidence=Decimal("0"),
        )
    visitor = _PythonVisitor(module)
    visitor.visit(tree)
    exports = tuple(visitor.exports) or tuple(
        symbol.name for symbol in visitor.symbols if symbol.parent == module and symbol.visibility == "public"
    )
    return ExtractionResult(
        path=path,
        language="python",
        engine="compiler",
        parsed=True,
        symbols=tuple(visitor.symbols),
        references=tuple(visitor.references),
        imports=tuple(dict.fromkeys(visitor.imports)),
        exports=exports,
        dynamic_markers=tuple(dict.fromkeys(visitor.dynamic)),
    )


# ---------------------------------------------------------------------------
# Syntactic families
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Grammar:
    line_comments: tuple[str, ...]
    block_comments: tuple[tuple[str, str], ...]
    string_delims: tuple[str, ...]
    declarations: tuple[tuple[EntityKind, str], ...]
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    dynamic: tuple[str, ...] = ()
    confidence: Decimal = Decimal("0.75")


_C_LIKE_COMMENTS = ("//",)
_C_LIKE_BLOCKS = (("/*", "*/"),)

_GRAMMARS: Mapping[str, _Grammar] = {
    "java": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"', "'"),
        declarations=(
            (EntityKind.PACKAGE, r"^\s*package\s+([\w.]+)\s*;"),
            (EntityKind.TYPE, r"^\s*(?:public\s+|private\s+|protected\s+|final\s+|abstract\s+|static\s+|sealed\s+)*"
                              r"(?:class|interface|enum|record)\s+(\w+)"),
            (EntityKind.METHOD, r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|synchronized\s+|"
                                r"abstract\s+|native\s+|default\s+)+[\w<>\[\].,?\s]+\s+(\w+)\s*\("),
            (EntityKind.FIELD, r"^\s*(?:public|private|protected)\s+(?:static\s+|final\s+|volatile\s+|transient\s+)*"
                               r"[\w<>\[\].,?]+\s+(\w+)\s*[;=]"),
        ),
        imports=(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;",),
        dynamic=(r"Class\.forName\s*\(", r"\.getMethod\s*\(", r"\.getDeclaredField\s*\(", r"@Reflective"),
        confidence=Decimal("0.8"),
    ),
    "kotlin": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"',),
        declarations=(
            (EntityKind.PACKAGE, r"^\s*package\s+([\w.]+)"),
            (EntityKind.TYPE, r"^\s*(?:\w+\s+)*(?:class|interface|object|enum class|data class)\s+(\w+)"),
            (EntityKind.FUNCTION, r"^\s*(?:\w+\s+)*fun\s+(?:<[^>]+>\s+)?(?:[\w.]+\.)?(\w+)\s*\("),
            (EntityKind.PROPERTY, r"^\s*(?:\w+\s+)*(?:val|var)\s+(\w+)"),
        ),
        imports=(r"^\s*import\s+([\w.*]+)",),
        dynamic=(r"::class\.java", r"Class\.forName\s*\("),
    ),
    "csharp": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"',),
        declarations=(
            (EntityKind.NAMESPACE, r"^\s*namespace\s+([\w.]+)"),
            (EntityKind.TYPE, r"^\s*(?:\w+\s+)*(?:class|interface|struct|record|enum)\s+(\w+)"),
            (EntityKind.METHOD, r"^\s*(?:public|private|protected|internal)\s+(?:\w+\s+)*[\w<>\[\],?\s]+\s+(\w+)\s*\("),
            (EntityKind.PROPERTY, r"^\s*(?:public|private|protected|internal)\s+(?:\w+\s+)*[\w<>\[\],?]+\s+(\w+)\s*\{"),
        ),
        imports=(r"^\s*using\s+(?:static\s+)?([\w.=\s]+);",),
        dynamic=(r"typeof\s*\(", r"GetType\s*\(", r"Activator\.CreateInstance", r"nameof\s*\("),
        confidence=Decimal("0.8"),
    ),
    "typescript": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"', "'", "`"),
        declarations=(
            (EntityKind.TYPE, r"^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface|type|enum)\s+(\w+)"),
            (EntityKind.FUNCTION, r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)"),
            (EntityKind.FUNCTION, r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?\("),
            (EntityKind.VARIABLE, r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::|=)"),
            (EntityKind.METHOD, r"^\s{2,}(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+)*"
                                r"(\w+)\s*\([^)]*\)\s*[:{]"),
        ),
        imports=(r"""^\s*import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""",
                 r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
        exports=(r"^\s*export\s+(?:default\s+)?(?:class|interface|type|enum|function|const|let|var)\s+(\w+)",),
        dynamic=(r"\[[^\]\n]*\$\{", r"\beval\s*\(", r"\bnew Function\s*\(", r"\bimport\s*\(", r"Reflect\.\w+"),
        confidence=Decimal("0.8"),
    ),
    "go": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"', "`"),
        declarations=(
            (EntityKind.PACKAGE, r"^\s*package\s+(\w+)"),
            (EntityKind.FUNCTION, r"^\s*func\s+(\w+)\s*\("),
            (EntityKind.METHOD, r"^\s*func\s+\([^)]*\)\s*(\w+)\s*\("),
            (EntityKind.TYPE, r"^\s*type\s+(\w+)\s+"),
        ),
        imports=(r"""^\s*(?:import\s+)?(?:\w+\s+)?"([\w./-]+)"\s*$""",),
        dynamic=(r"reflect\.", r"interface\s*\{\s*\}"),
        confidence=Decimal("0.8"),
    ),
    "rust": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"',),
        declarations=(
            (EntityKind.FUNCTION, r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"),
            (EntityKind.TYPE, r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|type|union)\s+(\w+)"),
            (EntityKind.MACRO, r"^\s*macro_rules!\s*(\w+)"),
        ),
        imports=(r"^\s*use\s+([\w:{}*,\s]+);",),
        dynamic=(r"\bAny\b", r"downcast", r"macro_rules!"),
    ),
    "php": _Grammar(
        line_comments=("//", "#"),
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"', "'"),
        declarations=(
            (EntityKind.NAMESPACE, r"^\s*namespace\s+([\w\\]+)"),
            (EntityKind.TYPE, r"^\s*(?:final\s+|abstract\s+)*(?:class|interface|trait|enum)\s+(\w+)"),
            (EntityKind.METHOD, r"^\s*(?:public|private|protected)?\s*(?:static\s+)?function\s+(\w+)\s*\("),
        ),
        imports=(r"^\s*use\s+([\w\\]+)",),
        dynamic=(r"\$\$", r"call_user_func", r"->\{\s*\$", r"::\{\s*\$", r"variable_variables"),
    ),
    "ruby": _Grammar(
        line_comments=("#",),
        block_comments=(("=begin", "=end"),),
        string_delims=('"', "'"),
        declarations=(
            (EntityKind.TYPE, r"^\s*(?:class|module)\s+([\w:]+)"),
            (EntityKind.METHOD, r"^\s*def\s+(?:self\.)?([\w?!=]+)"),
        ),
        imports=(r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""",),
        dynamic=(r"\bsend\b", r"method_missing", r"define_method", r"const_get", r"instance_variable_get"),
        confidence=Decimal("0.6"),
    ),
    "swift": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"',),
        declarations=(
            (EntityKind.TYPE, r"^\s*(?:public\s+|internal\s+|private\s+|open\s+|final\s+)*"
                              r"(?:class|struct|enum|protocol|extension)\s+(\w+)"),
            (EntityKind.FUNCTION, r"^\s*(?:public\s+|private\s+|internal\s+|static\s+|override\s+)*func\s+(\w+)"),
            (EntityKind.PROPERTY, r"^\s*(?:public\s+|private\s+)*(?:var|let)\s+(\w+)"),
        ),
        imports=(r"^\s*import\s+(\w+)",),
        dynamic=(r"@objc", r"NSClassFromString", r"#selector"),
    ),
    "dart": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"', "'"),
        declarations=(
            (EntityKind.TYPE, r"^\s*(?:abstract\s+)?(?:class|mixin|enum|extension)\s+(\w+)"),
            (EntityKind.FUNCTION, r"^\s*(?:[\w<>,\s?]+\s+)?(\w+)\s*\([^)]*\)\s*(?:async\s*)?\{"),
        ),
        imports=(r"""^\s*import\s+['"]([^'"]+)['"]""",),
        dynamic=(r"noSuchMethod", r"dart:mirrors"),
    ),
    "cpp": _Grammar(
        line_comments=_C_LIKE_COMMENTS,
        block_comments=_C_LIKE_BLOCKS,
        string_delims=('"', "'"),
        declarations=(
            (EntityKind.TYPE, r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct|union|enum(?:\s+class)?)\s+(\w+)"),
            (EntityKind.NAMESPACE, r"^\s*namespace\s+(\w+)"),
            (EntityKind.FUNCTION, r"^\s*(?:[\w:<>,*&\s]+\s+)?([\w:~]+)\s*\([^;]*\)\s*(?:const\s*)?\{"),
            (EntityKind.MACRO, r"^\s*#define\s+(\w+)"),
        ),
        imports=(r"""^\s*#include\s+[<"]([^>"]+)[>"]""",),
        dynamic=(r"dynamic_cast", r"typeid", r"#define", r"template\s*<"),
        confidence=Decimal("0.6"),
    ),
    "sql": _Grammar(
        line_comments=("--",),
        block_comments=_C_LIKE_BLOCKS,
        string_delims=("'",),
        declarations=(
            (EntityKind.DATABASE_OBJECT,
             r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|INDEX|FUNCTION|PROCEDURE|TRIGGER|TYPE|SCHEMA)"
             r"\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)"),
            (EntityKind.DATABASE_OBJECT, r"(?i)^\s*ALTER\s+TABLE\s+([\w.\"]+)"),
        ),
        dynamic=(r"(?i)EXECUTE\s+IMMEDIATE", r"(?i)\bEXEC\s*\("),
        confidence=Decimal("0.85"),
    ),
}

#: Languages that share an existing grammar exactly.
_GRAMMAR_ALIASES: Mapping[str, str] = {
    "javascript": "typescript",
    "tsx": "typescript",
    "jsx": "typescript",
    "vue": "typescript",
    "node": "typescript",
    "c": "cpp",
    "objective-c": "cpp",
    "scala": "kotlin",
    "groovy": "java",
    "vbnet": "csharp",
    "fsharp": "csharp",
    "plsql": "sql",
    "tsql": "sql",
    "postgresql": "sql",
    "flutter": "dart",
}


def _strip_noise(text: str, grammar: _Grammar, *, keep_strings: bool = False) -> str:
    """Blank out comments (and optionally string bodies), preserving geometry.

    Replacing rather than deleting keeps every reported source span valid,
    which matters because those spans are what a patch is anchored to.

    ``keep_strings`` exists because import targets live *inside* strings in
    TypeScript, Go, Ruby, Dart and C++ — blanking them would make every import
    in those languages invisible.  Declaration scanning still runs against the
    fully-stripped text so that ``"class Fake {"`` in a literal cannot be
    mistaken for a declaration.
    """

    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        matched = False
        for opener, closer in grammar.block_comments:
            if text.startswith(opener, index):
                end = text.find(closer, index + len(opener))
                end = length if end == -1 else end + len(closer)
                out.append("".join("\n" if item == "\n" else " " for item in text[index:end]))
                index = end
                matched = True
                break
        if matched:
            continue
        for opener in grammar.line_comments:
            if text.startswith(opener, index):
                end = text.find("\n", index)
                end = length if end == -1 else end
                out.append(" " * (end - index))
                index = end
                matched = True
                break
        if matched:
            continue
        if char in grammar.string_delims:
            if keep_strings:
                out.append(char)
                index += 1
                while index < length:
                    if text[index] == "\\" and index + 1 < length:
                        out.append(text[index : index + 2])
                        index += 2
                        continue
                    out.append(text[index])
                    index += 1
                    if text[index - 1] == char:
                        break
                continue
            index += 1
            out.append(" ")
            while index < length:
                if text[index] == "\\" and index + 1 < length:
                    out.append("  ")
                    index += 2
                    continue
                if text[index] == char:
                    out.append(" ")
                    index += 1
                    break
                out.append("\n" if text[index] == "\n" else " ")
                index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def extract_syntactic(path: str, text: str, language: str) -> ExtractionResult:
    grammar_key = _GRAMMAR_ALIASES.get(language, language)
    grammar = _GRAMMARS.get(grammar_key)
    if grammar is None:
        return ExtractionResult(
            path=path,
            language=language,
            engine="none",
            parsed=False,
            errors=(f"no-extractor-for-language:{language}",),
            base_confidence=Decimal("0"),
        )
    stripped = _strip_noise(text, grammar)
    with_strings = _strip_noise(text, grammar, keep_strings=True)
    lines = stripped.splitlines()
    string_lines = with_strings.splitlines()
    raw_lines = text.splitlines()
    module = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    symbols: list[ExtractedSymbol] = []
    references: list[ExtractedReference] = []
    imports: list[str] = []
    exports: list[str] = []
    dynamic: list[str] = []

    compiled = [(kind, re.compile(pattern)) for kind, pattern in grammar.declarations]
    import_patterns = [re.compile(pattern) for pattern in grammar.imports]
    export_patterns = [re.compile(pattern) for pattern in grammar.exports]
    dynamic_patterns = [re.compile(pattern) for pattern in grammar.dynamic]

    container = module
    type_container = ""
    #: Member kinds hang off the most recently declared type, so a field keeps
    #: its owning class in its qualified name instead of floating up to the
    #: package.
    member_kinds = {EntityKind.METHOD, EntityKind.FIELD, EntityKind.PROPERTY}
    for number, line in enumerate(lines, start=1):
        string_line = string_lines[number - 1] if number <= len(string_lines) else line
        if not line.strip() and not string_line.strip():
            continue
        for kind, pattern in compiled:
            match = pattern.match(line)
            if not match:
                continue
            name = match.group(1)
            if kind in (EntityKind.PACKAGE, EntityKind.NAMESPACE):
                container = name
                type_container = ""
                qualified = name
            elif kind is EntityKind.TYPE:
                type_container = name
                qualified = f"{container}.{name}"
            elif kind in member_kinds and type_container:
                qualified = f"{container}.{type_container}.{name}"
            elif kind is EntityKind.DATABASE_OBJECT:
                # Database objects are already globally qualified by schema;
                # prefixing them with a filename would invent a namespace.
                qualified = name.strip('"')
            else:
                qualified = f"{container}.{name}"
            symbols.append(
                ExtractedSymbol(
                    kind=kind,
                    name=name,
                    qualified_name=qualified,
                    span=SourceSpan(number, match.start(1), number, match.end(1)),
                    signature=raw_lines[number - 1].strip()[:200] if number <= len(raw_lines) else "",
                    visibility=_syntactic_visibility(line, language, name, kind),
                    parent=type_container or container,
                    confidence=grammar.confidence,
                )
            )
            break
        for pattern in import_patterns:
            found = pattern.search(string_line)
            if found:
                target = found.group(1).strip().strip("\"'")
                if not target:
                    continue
                imports.append(target)
                references.append(
                    ExtractedReference(
                        type=RelationshipType.IMPORTS,
                        name=target,
                        span=SourceSpan(number, 0, number, len(string_line)),
                        from_symbol=container,
                        confidence=grammar.confidence,
                    )
                )
        for pattern in export_patterns:
            found = pattern.search(line)
            if found:
                exports.append(found.group(1))
        for pattern in dynamic_patterns:
            if pattern.search(string_line):
                dynamic.append(f"{pattern.pattern}@{number}")

    return ExtractionResult(
        path=path,
        language=language,
        engine="syntactic",
        parsed=True,
        symbols=tuple(symbols),
        references=tuple(references),
        imports=tuple(dict.fromkeys(imports)),
        exports=tuple(dict.fromkeys(exports)),
        dynamic_markers=tuple(dict.fromkeys(dynamic)),
        base_confidence=grammar.confidence,
    )


def _syntactic_visibility(line: str, language: str, name: str = "", kind: EntityKind | None = None) -> str:
    lowered = line.strip()
    if kind in (EntityKind.PACKAGE, EntityKind.NAMESPACE):
        return "public"
    if language == "go":
        # Go visibility is spelled by the identifier itself, not by a modifier.
        return "public" if name[:1].isupper() else "internal"
    if language in ("java", "kotlin", "csharp", "swift", "php", "cpp"):
        if lowered.startswith(("public ", "open ")) or " public " in lowered[:60]:
            return "public"
        if lowered.startswith("protected ") or " protected " in lowered[:60]:
            return "protected"
        if lowered.startswith("private ") or " private " in lowered[:60]:
            return "private"
        if lowered.startswith("internal ") or " internal " in lowered[:60]:
            return "internal"
        return "package-private" if language == "java" else "unknown"
    if language in ("typescript", "javascript", "tsx", "jsx", "vue", "node"):
        return "exported" if lowered.startswith("export") else "module"
    if language == "rust":
        return "public" if lowered.startswith("pub") else "internal"
    return "unknown"


LANGUAGES_WITH_EXTRACTORS: tuple[str, ...] = tuple(
    sorted({"python", *_GRAMMARS, *_GRAMMAR_ALIASES})
)


def extract(path: str, text: str, language: str) -> ExtractionResult:
    """Extract symbols and references for one file."""

    if language == "python":
        return extract_python(path, text)
    return extract_syntactic(path, text, language)


def supported(language: str) -> bool:
    return language == "python" or _GRAMMAR_ALIASES.get(language, language) in _GRAMMARS


def dynamic_risk(results: Sequence[ExtractionResult]) -> Decimal:
    """Share of parsed files carrying at least one dynamic-reference marker."""

    parsed = [result for result in results if result.parsed]
    if not parsed:
        return Decimal("1")
    risky = sum(1 for result in parsed if result.dynamic_markers)
    return (Decimal(risky) / Decimal(len(parsed))).quantize(Decimal("0.0001"))


__all__ = [
    "LANGUAGES_WITH_EXTRACTORS",
    "ExtractedReference",
    "ExtractedSymbol",
    "ExtractionResult",
    "SourceSpan",
    "dynamic_risk",
    "extract",
    "extract_python",
    "extract_syntactic",
    "supported",
]
