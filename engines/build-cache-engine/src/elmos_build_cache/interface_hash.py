"""Semantic and public-interface hashing for the thirteen ELMOS languages.

The point of this module is to make a private change *not* invalidate the
world. It separates, per source unit:

``api_digest``
    public/exported signatures -- names, visibility, parameter and return
    types, generics, thrown types, attributes and annotations;
``abi_digest``
    the subset that changes binary or wire layout -- field order, base types,
    serialised members, enum values, packing attributes;
``body_digest``
    implementation bodies only;
``surface_digest``
    HTTP routes, events, message topics, database schema and UI/platform
    capabilities -- the things a dependent can observe without linking;
``semantic_digest``
    everything above, combined.

**Confidence is part of the contract.** A construct the extractor does not
understand yields ``ExtractionConfidence.UNSUPPORTED``, and callers must fall
back to conservative invalidation rather than assuming the private/public split
was computed correctly. Getting this wrong is a correctness bug, not a
performance one, so the default on doubt is always "invalidate more".
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .canonical import digest_of

SCHEMA_VERSION = "1.0.0"

#: Set by ``use_scanner_only`` to bypass tree-sitter (differential tests).
_SCANNER_ONLY = False

LANGUAGES: tuple[str, ...] = (
    "java",
    "kotlin",
    "python",
    "csharp",
    "go",
    "rust",
    "cpp",
    "php",
    "typescript",
    "javascript",
    "objectivec",
    "swift",
    "dart",
)

EXTENSION_LANGUAGE: dict[str, str] = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".py": "python",
    ".pyi": "python",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".h": "cpp",
    ".php": "php",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".m": "objectivec",
    ".mm": "objectivec",
    ".swift": "swift",
    ".dart": "dart",
}

#: Languages whose visibility is not statically decidable from a single file.
DYNAMIC_LANGUAGES: frozenset[str] = frozenset({"python", "javascript", "php"})


class ExtractionConfidence(str, Enum):
    EXACT = "EXACT"
    HEURISTIC = "HEURISTIC"
    UNSUPPORTED = "UNSUPPORTED"


class SymbolKind(str, Enum):
    TYPE = "TYPE"
    FUNCTION = "FUNCTION"
    FIELD = "FIELD"
    CONSTANT = "CONSTANT"
    ENUM_MEMBER = "ENUM_MEMBER"
    ROUTE = "ROUTE"
    EVENT = "EVENT"
    SCHEMA = "SCHEMA"
    UI_COMPONENT = "UI_COMPONENT"
    CAPABILITY = "CAPABILITY"


@dataclass(frozen=True)
class Symbol:
    """A stable identity plus the parts that matter for reuse decisions."""

    symbol_id: str
    kind: SymbolKind
    name: str
    visibility: str = "public"
    signature: str = ""
    annotations: tuple[str, ...] = ()
    layout_index: int | None = None
    body_digest: str | None = None

    @property
    def public(self) -> bool:
        return self.visibility in ("public", "exported", "open", "internal-api")

    def api_payload(self) -> dict[str, Any]:
        return {
            "id": self.symbol_id,
            "kind": str(self.kind.value),
            "name": self.name,
            "visibility": self.visibility,
            "signature": self.signature,
            "annotations": sorted(self.annotations),
        }

    def abi_payload(self) -> dict[str, Any]:
        return {**self.api_payload(), "layout_index": self.layout_index}


@dataclass(frozen=True)
class ModuleInterface:
    language: str
    logical_path: str
    confidence: ExtractionConfidence
    symbols: tuple[Symbol, ...] = ()
    routes: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    schema_elements: tuple[str, ...] = ()
    ui_components: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    raw_digest: str = ""
    #: Which extractor produced this, and at what version.
    #:
    #: It is part of ``semantic_digest`` on purpose. Two workers with different
    #: extractors installed will disagree about the private/public split, and a
    #: grammar upgrade can legitimately change a signature's spelling. Binding
    #: the identity into the digest turns that into an explicit cache miss
    #: instead of two machines quietly trusting each other's answer.
    extractor: str = "line-scanner/1"

    # -- digests ----------------------------------------------------------
    def opaque_types(self) -> frozenset[str]:
        """Types whose members the extractor did not resolve.

        A single-line class body, or any construct the line scanner cannot
        decompose, leaves a type with a body but no recorded members. Treating
        such a type as "unchanged public API" would be unsafe, so its body
        digest is folded into the API digest instead: any edit inside it
        invalidates dependents. Over-invalidation is the acceptable failure.
        """
        parents = {
            symbol.symbol_id.rsplit("::", 1)[0]
            for symbol in self.symbols
            if "::" in symbol.symbol_id
        }
        return frozenset(
            symbol.symbol_id
            for symbol in self.symbols
            if symbol.kind is SymbolKind.TYPE
            and symbol.body_digest is not None
            and symbol.symbol_id not in parents
        )

    @property
    def api_digest(self) -> str:
        opaque = self.opaque_types()
        payload: list[dict[str, Any]] = []
        for symbol in sorted(self.symbols, key=_key):
            if not symbol.public:
                continue
            entry = symbol.api_payload()
            if symbol.symbol_id in opaque:
                entry["opaque_body"] = symbol.body_digest
            payload.append(entry)
        return digest_of({"language": self.language, "symbols": payload})

    @property
    def abi_digest(self) -> str:
        """Layout identity.

        Fields and enum members count regardless of visibility: a private field
        reorder still changes the binary layout that a compiled dependent was
        built against.
        """
        layout = [
            s.abi_payload()
            for s in sorted(self.symbols, key=_key)
            if s.kind in (SymbolKind.FIELD, SymbolKind.ENUM_MEMBER) or (s.public and s.kind is SymbolKind.TYPE)
        ]
        return digest_of({"language": self.language, "layout": layout})

    @property
    def body_digest(self) -> str:
        return digest_of(
            {
                "language": self.language,
                "bodies": {s.symbol_id: s.body_digest for s in sorted(self.symbols, key=_key)},
            }
        )

    @property
    def surface_digest(self) -> str:
        return digest_of(
            {
                "routes": sorted(self.routes),
                "events": sorted(self.events),
                "schema": sorted(self.schema_elements),
                "ui": sorted(self.ui_components),
                "capabilities": sorted(self.capabilities),
            }
        )

    @property
    def semantic_digest(self) -> str:
        return digest_of(
            {
                "schema_version": SCHEMA_VERSION,
                "api": self.api_digest,
                "abi": self.abi_digest,
                "body": self.body_digest,
                "surface": self.surface_digest,
                "confidence": self.confidence.value,
                "extractor": self.extractor,
            }
        )

    def digests(self) -> dict[str, str]:
        return {
            "api": self.api_digest,
            "abi": self.abi_digest,
            "body": self.body_digest,
            "surface": self.surface_digest,
            "semantic": self.semantic_digest,
            "raw": self.raw_digest,
        }

    def public_symbols(self) -> tuple[Symbol, ...]:
        return tuple(s for s in self.symbols if s.public)


def _key(symbol: Symbol) -> tuple[str, str]:
    return (symbol.symbol_id, symbol.name)


@dataclass(frozen=True)
class InterfaceDelta:
    """What changed, and therefore which dependency edges must be walked."""

    logical_path: str
    api_changed: bool
    abi_changed: bool
    surface_changed: bool
    body_changed: bool
    conservative: bool
    reasons: tuple[str, ...] = ()
    added_symbols: tuple[str, ...] = ()
    removed_symbols: tuple[str, ...] = ()
    changed_symbols: tuple[str, ...] = ()

    @property
    def propagates_to_dependents(self) -> bool:
        """Interface changes cross module boundaries; private bodies do not."""
        return self.api_changed or self.abi_changed or self.surface_changed or self.conservative

    @property
    def unchanged(self) -> bool:
        return not (
            self.api_changed
            or self.abi_changed
            or self.surface_changed
            or self.body_changed
            or self.conservative
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_path": self.logical_path,
            "api_changed": self.api_changed,
            "abi_changed": self.abi_changed,
            "surface_changed": self.surface_changed,
            "body_changed": self.body_changed,
            "conservative": self.conservative,
            "reasons": list(self.reasons),
            "added_symbols": list(self.added_symbols),
            "removed_symbols": list(self.removed_symbols),
            "changed_symbols": list(self.changed_symbols),
        }


def language_for(logical_path: str) -> str | None:
    lowered = logical_path.lower()
    for suffix, language in EXTENSION_LANGUAGE.items():
        if lowered.endswith(suffix):
            return language
    return None


# --------------------------------------------------------------------------
# framework surface patterns
# --------------------------------------------------------------------------
_ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Spring / JAX-RS / Micronaut
    re.compile(r'@(?:Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'),
    re.compile(r'@(?:GET|POST|PUT|PATCH|DELETE)\b[\s\S]{0,80}?@Path\s*\(\s*"([^"]+)"'),
    # ASP.NET
    re.compile(r'\[\s*Http(?:Get|Post|Put|Patch|Delete)\s*\(\s*"([^"]+)"\s*\)\s*\]'),
    re.compile(r'\[\s*Route\s*\(\s*"([^"]+)"\s*\)\s*\]'),
    # Express / Koa / Fastify / NestJS decorators
    re.compile(r'\b(?:app|router|server)\.(?:get|post|put|patch|delete|all)\s*\(\s*[\'"]([^\'"]+)'),
    re.compile(r'@(?:Get|Post|Put|Patch|Delete)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'),
    # Flask / FastAPI / Django
    re.compile(r'@(?:app|router|bp|blueprint)\.(?:route|get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)'),
    re.compile(r'\bpath\s*\(\s*[\'"]([^\'"]*)[\'"]'),
    # Go net/http and chi/gin
    re.compile(r'\b(?:HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE)\s*\(\s*"([^"]+)"'),
    # Rust actix/rocket/axum
    re.compile(r'#\[\s*(?:get|post|put|patch|delete)\s*\(\s*"([^"]+)"'),
    re.compile(r'\.route\s*\(\s*"([^"]+)"'),
    # PHP Laravel / Symfony
    re.compile(r'Route::(?:get|post|put|patch|delete|any)\s*\(\s*[\'"]([^\'"]+)'),
    re.compile(r'#\[\s*Route\s*\(\s*[\'"]([^\'"]+)'),
    # Swift Vapor / Dart shelf
    re.compile(r'\b(?:app|routes?)\.(?:get|post|put|patch|delete)\s*\(\s*"([^"]+)"'),
)

_EVENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'@(?:KafkaListener|RabbitListener|JmsListener|EventListener)\s*\([^)]*?"([^"]+)"'),
    re.compile(r'\b(?:subscribe|on|addEventListener|consume|listen)\s*\(\s*[\'"]([^\'"]+)'),
    re.compile(r'\b(?:publish|emit|send|dispatch)\s*\(\s*[\'"]([^\'"]+)'),
    re.compile(r'#\[\s*(?:event|subscribe)\s*\(\s*"([^"]+)"'),
)

_SCHEMA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'@(?:Table|Entity)\s*\(\s*(?:name\s*=\s*)?"([^"]+)"'),
    re.compile(r'@Column\s*\(\s*(?:name\s*=\s*)?"([^"]+)"'),
    re.compile(r'\[\s*Table\s*\(\s*"([^"]+)"\s*\)\s*\]'),
    re.compile(r'\b__tablename__\s*=\s*[\'"]([^\'"]+)'),
    re.compile(r'\bdb:"([^"]+)"'),
    re.compile(r'#\[\s*(?:table_name|sql_name)\s*=\s*"([^"]+)"'),
    re.compile(r'\bprotected\s+\$table\s*=\s*[\'"]([^\'"]+)'),
    re.compile(r'\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)'),
    re.compile(r'@SerializedName\s*\(\s*"([^"]+)"'),
    re.compile(r'\bjson:"([^",]+)'),
)

_UI_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\bclass\s+(\w+)\s+extends\s+(?:StatelessWidget|StatefulWidget|React\.Component)'),
    re.compile(r'\b(?:function|const)\s+([A-Z]\w*)\s*(?:=\s*)?\([^)]*\)\s*(?::\s*JSX\.Element\s*)?(?:=>)?\s*\{'),
    re.compile(r'\bstruct\s+(\w+)\s*:\s*View\b'),
    re.compile(r'@Composable[\s\S]{0,40}?fun\s+(\w+)'),
    re.compile(r'@interface\s+(\w+)\s*:\s*UIView'),
)

_CAPABILITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\b(?:NSCamera|NSLocation|NSMicrophone|NSPhotoLibrary)\w*UsageDescription\b'),
    re.compile(r'android\.permission\.(\w+)'),
    re.compile(r'\bPermission\.(\w+)'),
    re.compile(r'\brequestPermissions?\s*\(\s*[\'"]([^\'"]+)'),
)


def _collect(patterns: Sequence[re.Pattern[str]], text: str) -> tuple[str, ...]:
    found: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            groups = [group for group in match.groups() if group]
            found.add(groups[0] if groups else match.group(0))
    return tuple(sorted(found))


# --------------------------------------------------------------------------
# brace-language extraction
# --------------------------------------------------------------------------
_VISIBILITY_TOKENS = ("public", "private", "protected", "internal", "fileprivate", "open", "package")

_MODIFIER_WORDS = frozenset(
    {
        "public", "private", "protected", "internal", "fileprivate", "open", "package", "pub",
        "static", "final", "abstract", "sealed", "override", "virtual", "async", "await", "export",
        "default", "inline", "const", "constexpr", "readonly", "suspend", "data", "partial", "extern",
        "unsafe", "mutating", "nonisolated", "operator", "explicit", "friend", "noexcept",
        "synchronized", "transient", "volatile", "native", "strictfp", "lateinit", "companion",
        "required", "convenience", "class", "new", "unowned", "weak", "yield", "declare",
        "func", "fun", "fn", "def", "sub", "function", "let", "var", "val",
    }
)

_CONTROL_KEYWORDS = frozenset(
    {"if", "for", "while", "switch", "catch", "return", "else", "match", "do", "try", "with",
     "using", "when", "guard", "defer", "throw", "case", "foreach", "lock", "select", "go", "assert"}
)

_TYPE_DECLARATION = re.compile(
    r"""^[ \t]*
        (?P<mods>(?:[A-Za-z_@#\[\]][\w$]*(?:\([^)]*\))?[ \t]+)*?)
        (?P<kw>class|interface|struct|enum|record|trait|protocol|object|actor|extension|impl|
            namespace|typealias|type|union)
        [ \t]+(?P<name>[A-Za-z_$][\w$]*)
        (?P<tail>[^;{\n]*)""",
    re.VERBOSE,
)

_FUNCTION_DECLARATION = re.compile(
    r"""^[ \t]*
        (?P<mods>(?:[A-Za-z_@#\[\]<>][\w$<>,.:\[\]*&?]*[ \t]+)*?)
        (?P<name>[A-Za-z_$][\w$]*)
        [ \t]*(?P<generics><[^;{}()\n]{0,120}>)?
        [ \t]*\((?P<params>[^;{}\n]{0,600})\)
        (?P<tail>[^;{\n]{0,200})?""",
    re.VERBOSE,
)

_FIELD_DECLARATION = re.compile(
    r"""^[ \t]*
        (?P<mods>(?:[A-Za-z_@#\[\]][\w$]*[ \t]+)*?)
        (?P<kw>var|let|val|const|readonly)
        [ \t]+(?P<name>[A-Za-z_$][\w$]*)
        (?P<tail>[^;{\n]*)""",
    re.VERBOSE,
)

# Objective-C instance/class methods: ``- (void)doThing:(int)value;``
_OBJC_METHOD = re.compile(r"^[ \t]*(?P<sign>[-+])[ \t]*\((?P<ret>[^)]*)\)[ \t]*(?P<selector>[^;{\n]+)")

# Typed member fields in curly-brace languages: ``private int count;``
_TYPED_FIELD = re.compile(
    r"""^[ \t]*
        (?P<mods>(?:[A-Za-z_@#\[\]][\w$]*[ \t]+)+)
        (?P<name>[A-Za-z_$][\w$]*)
        [ \t]*(?:=[^;\n]*)?;""",
    re.VERBOSE,
)


def _strip_comments_and_strings(text: str, language: str) -> str:
    """Remove content that must not affect signatures, keeping line structure."""
    out: list[str] = []
    index = 0
    length = len(text)
    hash_comment = language in ("python", "php", "ruby")
    while index < length:
        char = text[index]
        two = text[index : index + 2]
        if two == "/*":
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue
        if two == "//" or (char == "#" and hash_comment and two != "#["):
            end = text.find("\n", index)
            index = length if end < 0 else end
            continue
        if char in "\"'":
            quote = char
            index += 1
            out.append(quote)
            while index < length and text[index] != quote:
                if text[index] == "\\":
                    index += 1
                index += 1
            out.append(quote)
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _matching_block(text: str, open_index: int) -> tuple[int, str]:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index, text[open_index + 1 : index]
    return len(text), text[open_index + 1 :]


def _visibility_for(language: str, modifiers: str, name: str, nested: bool = False) -> str:
    for token in modifiers.split():
        base = token.split("(")[0]
        if base in _VISIBILITY_TOKENS:
            return "public" if base == "open" else base
        if base == "pub":
            return "public"
        if base == "export":
            return "public"
    if language == "go":
        return "exported" if name[:1].isupper() else "private"
    if language == "rust":
        return "private"
    if language in ("typescript", "javascript"):
        # Module scope is private unless explicitly exported; members of an
        # exported type are public unless underscore-prefixed by convention.
        if not nested:
            return "private"
        return "private" if name.startswith("_") else "public"
    if language == "dart":
        return "private" if name.startswith("_") else "public"
    if language == "java":
        return "package"
    return "public"


def _is_annotation_line(stripped: str) -> bool:
    return stripped.startswith("@") or stripped.startswith("#[") or (
        stripped.startswith("[") and stripped.endswith("]")
    )


def _extract_brace_language(language: str, logical_path: str, source: str) -> ModuleInterface:
    text = _strip_comments_and_strings(source, language)
    symbols: list[Symbol] = []
    notes: list[str] = []
    pending: list[str] = []
    scope: list[tuple[str, int]] = []  # (name, closing brace offset)
    layout_counter = 0

    lines = text.splitlines()
    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1

    def current_scope(offset: int) -> list[str]:
        while scope and offset > scope[-1][1]:
            scope.pop()
        return [name for name, _ in scope]

    for number, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_annotation_line(stripped):
            pending.append(stripped.strip("[]"))
            continue

        offset = offsets[number]
        prefix = current_scope(offset)
        record = _match_declaration(language, line)
        if record is None:
            pending.clear()
            continue
        kind, name, modifiers, signature = record
        if name in _CONTROL_KEYWORDS:
            pending.clear()
            continue

        body_digest: str | None = None
        close_offset = offset + len(line)
        open_column = line.find("{")
        if open_column >= 0:
            close_offset, body = _matching_block(text, offset + open_column)
            body_digest = digest_of(_normalize_body(body))

        layout_index: int | None = None
        if kind in (SymbolKind.FIELD, SymbolKind.ENUM_MEMBER, SymbolKind.TYPE):
            layout_index = layout_counter
            layout_counter += 1

        symbols.append(
            Symbol(
                symbol_id="::".join([*prefix, name]),
                kind=kind,
                name=name,
                visibility=_visibility_for(language, modifiers, name, nested=bool(prefix)),
                signature=signature,
                annotations=tuple(sorted(pending)),
                layout_index=layout_index,
                body_digest=body_digest,
            )
        )
        if kind is SymbolKind.TYPE and open_column >= 0:
            scope.append((name, close_offset))
        pending.clear()

    confidence = ExtractionConfidence.HEURISTIC
    if language in DYNAMIC_LANGUAGES:
        notes.append("dynamic language: visibility is heuristic, reuse stays conservative")
    if not symbols:
        confidence = ExtractionConfidence.UNSUPPORTED
        notes.append("no declarations recognised; treating the unit as opaque")

    return ModuleInterface(
        language=language,
        logical_path=logical_path,
        confidence=confidence,
        symbols=tuple(symbols),
        routes=_collect(_ROUTE_PATTERNS, source),
        events=_collect(_EVENT_PATTERNS, source),
        schema_elements=_collect(_SCHEMA_PATTERNS, source),
        ui_components=_collect(_UI_PATTERNS, source),
        capabilities=_collect(_CAPABILITY_PATTERNS, source),
        imports=_collect_imports(source),
        notes=tuple(notes),
        raw_digest=digest_of(source),
    )


def _match_declaration(language: str, line: str) -> tuple[SymbolKind, str, str, str] | None:
    """Return ``(kind, name, modifiers, signature)`` for a declaration line."""
    if language == "objectivec":
        objc = _OBJC_METHOD.match(line)
        if objc is not None:
            selector = re.sub(r"\s+", " ", objc.group("selector")).strip()
            name = selector.split(":")[0].split(" ")[0]
            visibility = "public" if objc.group("sign") == "+" else "public"
            return (
                SymbolKind.FUNCTION,
                name,
                visibility,
                f"{objc.group('sign')}({objc.group('ret').strip()}){selector}",
            )

    type_match = _TYPE_DECLARATION.match(line)
    if type_match is not None:
        tail = re.sub(r"\s+", " ", (type_match.group("tail") or "")).strip().rstrip("{").strip()
        return (
            SymbolKind.TYPE,
            type_match.group("name"),
            type_match.group("mods") or "",
            f"{type_match.group('kw')} {type_match.group('name')} {tail}".strip(),
        )

    function_match = _FUNCTION_DECLARATION.match(line)
    if function_match is not None:
        tail = (function_match.group("tail") or "").strip().rstrip("{").strip()
        looks_like_call = not tail and "{" not in line and not line.rstrip().endswith((";", "=>"))
        if not looks_like_call:
            modifiers = function_match.group("mods") or ""
            first = modifiers.split()[0] if modifiers.split() else ""
            if first in ("return", "if", "while", "for", "switch", "throw", "new", "await"):
                return None
            return (
                SymbolKind.FUNCTION,
                function_match.group("name"),
                modifiers,
                "{}{} ({}) {}".format(
                    function_match.group("name"),
                    function_match.group("generics") or "",
                    _normalize_params("(" + (function_match.group("params") or "") + ")"),
                    tail,
                ).strip(),
            )

    field_match = _FIELD_DECLARATION.match(line)
    if field_match is not None:
        tail = re.sub(r"\s+", " ", (field_match.group("tail") or "")).strip()
        return (
            SymbolKind.FIELD,
            field_match.group("name"),
            field_match.group("mods") or "",
            f"{field_match.group('kw')} {field_match.group('name')} {tail}".strip(),
        )

    typed = _TYPED_FIELD.match(line)
    if typed is not None:
        modifiers = typed.group("mods") or ""
        words = modifiers.split()
        if words and words[-1] not in _MODIFIER_WORDS:
            return (SymbolKind.FIELD, typed.group("name"), modifiers, f"{words[-1]} {typed.group('name')}")

    return None


def _normalize_params(params: str) -> str:
    inner = params.strip()
    if inner.startswith("("):
        inner = inner[1:]
    if inner.endswith(")"):
        inner = inner[:-1]
    parts = [re.sub(r"\s+", " ", part.strip()) for part in inner.split(",") if part.strip()]
    return "(" + ", ".join(parts) + ")"


def _normalize_body(body: str | None) -> str:
    if body is None:
        return ""
    return re.sub(r"\s+", " ", body).strip()


_IMPORT_PATTERNS = (
    re.compile(r"^\s*import\s+([\w.:/{}\-*\s,\"']+)", re.MULTILINE),
    re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE),
    re.compile(r"^\s*use\s+([\w:{}, ]+);", re.MULTILINE),
    re.compile(r"^\s*using\s+([\w.]+);", re.MULTILINE),
    re.compile(r"^\s*#include\s+[<\"]([^>\"]+)", re.MULTILINE),
    re.compile(r"^\s*(?:require|require_once|include)\s*\(?\s*['\"]([^'\"]+)", re.MULTILINE),
    re.compile(r"""(?:^|\s)(?:import|export)\s+.*?from\s+['\"]([^'\"]+)""", re.MULTILINE),
)


def _collect_imports(source: str) -> tuple[str, ...]:
    found: set[str] = set()
    for pattern in _IMPORT_PATTERNS:
        for match in pattern.finditer(source):
            value = match.group(1).strip().strip(";").strip()
            if value:
                found.add(re.sub(r"\s+", " ", value))
    return tuple(sorted(found))


# --------------------------------------------------------------------------
# python (exact, via the stdlib parser)
# --------------------------------------------------------------------------
def _extract_python(logical_path: str, source: str) -> ModuleInterface:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ModuleInterface(
            language="python",
            logical_path=logical_path,
            confidence=ExtractionConfidence.UNSUPPORTED,
            notes=(f"parse error at line {exc.lineno}: reuse must stay conservative",),
            raw_digest=digest_of(source),
        )

    exported: set[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(value, list | tuple):
                        exported = {str(item) for item in value}

    symbols: list[Symbol] = []
    dynamic_notes: list[str] = []
    layout_counter = 0

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def _visibility(self, name: str) -> str:
            if exported is not None:
                return "public" if name in exported else "private"
            return "private" if name.startswith("_") else "public"

        def _signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
            args = node.args
            parts: list[str] = []
            for group, prefix in ((args.posonlyargs, ""), (args.args, ""), (args.kwonlyargs, "*")):
                for argument in group:
                    annotation = ast.unparse(argument.annotation) if argument.annotation else ""
                    parts.append(f"{prefix}{argument.arg}:{annotation}")
            if args.vararg:
                parts.append("*" + args.vararg.arg)
            if args.kwarg:
                parts.append("**" + args.kwarg.arg)
            returns = ast.unparse(node.returns) if node.returns else ""
            return f"({', '.join(parts)}) -> {returns}"

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._function(node)

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            name = node.name
            symbol_id = "::".join([*self.scope, name])
            body_source = "\n".join(ast.unparse(statement) for statement in node.body)
            symbols.append(
                Symbol(
                    symbol_id=symbol_id,
                    kind=SymbolKind.FUNCTION,
                    name=name,
                    visibility=(
                        self._visibility(name)
                        if not self.scope
                        else ("private" if name.startswith("_") else "public")
                    ),
                    signature=self._signature(node),
                    annotations=tuple(sorted(ast.unparse(d) for d in node.decorator_list)),
                    body_digest=digest_of(body_source),
                )
            )
            self.scope.append(name)
            for child in node.body:
                self.visit(child)
            self.scope.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            nonlocal layout_counter
            name = node.name
            symbol_id = "::".join([*self.scope, name])
            bases = [ast.unparse(base) for base in node.bases]
            symbols.append(
                Symbol(
                    symbol_id=symbol_id,
                    kind=SymbolKind.TYPE,
                    name=name,
                    visibility=self._visibility(name),
                    signature=f"class({', '.join(bases)})",
                    annotations=tuple(sorted(ast.unparse(d) for d in node.decorator_list)),
                    layout_index=layout_counter,
                    body_digest=digest_of(
                        "\n".join(ast.unparse(statement) for statement in node.body)
                    ),
                )
            )
            layout_counter += 1
            self.scope.append(name)
            for child in node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    symbols.append(
                        Symbol(
                            symbol_id="::".join([*self.scope, child.target.id]),
                            kind=SymbolKind.FIELD,
                            name=child.target.id,
                            visibility="private" if child.target.id.startswith("_") else "public",
                            signature=ast.unparse(child.annotation),
                            layout_index=layout_counter,
                        )
                    )
                    layout_counter += 1
                self.visit(child)
            self.scope.pop()

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            function = ast.unparse(node.func)
            if function in ("getattr", "setattr", "eval", "exec", "__import__", "globals", "locals"):
                dynamic_notes.append(f"dynamic construct {function!r} defeats static visibility")
            self.generic_visit(node)

    Visitor().visit(tree)

    confidence = ExtractionConfidence.EXACT
    notes: list[str] = []
    if dynamic_notes:
        confidence = ExtractionConfidence.HEURISTIC
        notes.extend(sorted(set(dynamic_notes)))

    return ModuleInterface(
        language="python",
        logical_path=logical_path,
        confidence=confidence,
        symbols=tuple(symbols),
        routes=_collect(_ROUTE_PATTERNS, source),
        events=_collect(_EVENT_PATTERNS, source),
        schema_elements=_collect(_SCHEMA_PATTERNS, source),
        ui_components=(),
        capabilities=_collect(_CAPABILITY_PATTERNS, source),
        imports=_collect_imports(source),
        notes=tuple(notes),
        raw_digest=digest_of(source),
        extractor=f"python-ast/{sys.version_info.major}.{sys.version_info.minor}",
    )


# --------------------------------------------------------------------------
# public entry points
# --------------------------------------------------------------------------
def extract_interface(language: str, logical_path: str, source: str | bytes) -> ModuleInterface:
    """Extract the interface of one source unit."""
    if isinstance(source, bytes):
        try:
            source = source.decode("utf-8")
        except UnicodeDecodeError:
            return ModuleInterface(
                language=language,
                logical_path=logical_path,
                confidence=ExtractionConfidence.UNSUPPORTED,
                notes=("binary or non-UTF-8 content",),
                raw_digest=digest_of(repr(source)),
            )
    if language not in LANGUAGES:
        return ModuleInterface(
            language=language,
            logical_path=logical_path,
            confidence=ExtractionConfidence.UNSUPPORTED,
            notes=(f"language {language!r} has no extractor; invalidate conservatively",),
            raw_digest=digest_of(source),
        )
    if language == "python":
        return _extract_python(logical_path, source)
    if not _SCANNER_ONLY:
        from .treesitter_hash import GrammarUnavailable
        from .treesitter_hash import extract as treesitter_extract

        try:
            return treesitter_extract(language, logical_path, source)
        except GrammarUnavailable:
            pass  # no grammar here: the scanner below still answers, heuristically
    return _extract_brace_language(language, logical_path, source)


def use_scanner_only(enabled: bool) -> None:
    """Force the line scanner, for differential testing of the two extractors."""
    global _SCANNER_ONLY
    _SCANNER_ONLY = enabled


def extract_for_path(logical_path: str, source: str | bytes) -> ModuleInterface:
    language = language_for(logical_path)
    if language is None:
        return ModuleInterface(
            language="unknown",
            logical_path=logical_path,
            confidence=ExtractionConfidence.UNSUPPORTED,
            notes=("unrecognised file extension",),
            raw_digest=digest_of(source if isinstance(source, str) else repr(source)),
        )
    return extract_interface(language, logical_path, source)


def compare_interfaces(before: ModuleInterface, after: ModuleInterface) -> InterfaceDelta:
    """Classify a change. Unsupported extraction always invalidates conservatively."""
    reasons: list[str] = []
    conservative = (
        before.confidence is ExtractionConfidence.UNSUPPORTED
        or after.confidence is ExtractionConfidence.UNSUPPORTED
        or before.language != after.language
    )
    if conservative:
        reasons.append("extraction confidence is insufficient for a private/public split")

    old_public = {symbol.symbol_id: symbol for symbol in before.public_symbols()}
    new_public = {symbol.symbol_id: symbol for symbol in after.public_symbols()}
    added = sorted(set(new_public) - set(old_public))
    removed = sorted(set(old_public) - set(new_public))
    changed = sorted(
        symbol_id
        for symbol_id in set(old_public) & set(new_public)
        if old_public[symbol_id].api_payload() != new_public[symbol_id].api_payload()
    )

    api_changed = before.api_digest != after.api_digest
    abi_changed = before.abi_digest != after.abi_digest
    surface_changed = before.surface_digest != after.surface_digest
    body_changed = before.body_digest != after.body_digest

    if api_changed:
        reasons.append("public signatures changed")
    if abi_changed:
        reasons.append("layout or serialised members changed")
    if surface_changed:
        reasons.append("routes, events, schema or capabilities changed")
    if body_changed and not api_changed:
        reasons.append("implementation bodies changed")
    if before.confidence is ExtractionConfidence.HEURISTIC and (
        api_changed or abi_changed or surface_changed
    ):
        reasons.append("heuristic extraction: dependents invalidated conservatively")
        conservative = True

    return InterfaceDelta(
        logical_path=after.logical_path,
        api_changed=api_changed,
        abi_changed=abi_changed,
        surface_changed=surface_changed,
        body_changed=body_changed,
        conservative=conservative,
        reasons=tuple(dict.fromkeys(reasons)),
        added_symbols=tuple(added),
        removed_symbols=tuple(removed),
        changed_symbols=tuple(changed),
    )


@dataclass
class InterfaceIndex:
    """Per-path interfaces plus the import edges between them."""

    interfaces: dict[str, ModuleInterface] = field(default_factory=dict)

    def add(self, interface: ModuleInterface) -> None:
        self.interfaces[interface.logical_path] = interface

    def add_source(self, logical_path: str, source: str | bytes) -> ModuleInterface:
        interface = extract_for_path(logical_path, source)
        self.add(interface)
        return interface

    def digests(self) -> dict[str, str]:
        return {path: iface.semantic_digest for path, iface in sorted(self.interfaces.items())}

    def public_interface_digests(self) -> dict[str, str]:
        return {path: iface.api_digest for path, iface in sorted(self.interfaces.items())}

    def diff(self, other: InterfaceIndex) -> dict[str, InterfaceDelta]:
        deltas: dict[str, InterfaceDelta] = {}
        for path in sorted(set(self.interfaces) | set(other.interfaces)):
            before = self.interfaces.get(path)
            after = other.interfaces.get(path)
            if before is None and after is not None:
                deltas[path] = InterfaceDelta(path, True, True, True, True, False, ("added",))
            elif after is None and before is not None:
                deltas[path] = InterfaceDelta(path, True, True, True, True, False, ("removed",))
            elif before is not None and after is not None:
                delta = compare_interfaces(before, after)
                if not delta.unchanged:
                    deltas[path] = delta
        return deltas


def propagating_paths(deltas: Iterable[InterfaceDelta]) -> tuple[str, ...]:
    """Paths whose change must be walked across dependency edges."""
    return tuple(sorted(delta.logical_path for delta in deltas if delta.propagates_to_dependents))


def body_only_paths(deltas: Iterable[InterfaceDelta]) -> tuple[str, ...]:
    """Paths whose change stops at behaviour-sensitive edges."""
    return tuple(
        sorted(
            delta.logical_path
            for delta in deltas
            if delta.body_changed and not delta.propagates_to_dependents
        )
    )
