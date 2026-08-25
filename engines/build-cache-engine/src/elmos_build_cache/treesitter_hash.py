"""Exact public-interface extraction with real grammars.

``interface_hash`` ships a line-oriented scanner that works everywhere and is
honest about being a heuristic: it marks every non-Python unit
``HEURISTIC``, which makes ``compare_interfaces`` invalidate dependents
conservatively on any interface change. Correct, but it gives up most of the
benefit of separating API from body.

This module replaces the scanner with a real parse tree per language, using
``tree-sitter``. When a grammar is available and the file parses without error
nodes, extraction is ``EXACT``: multi-line signatures, generics containing
braces, one-line bodies, nested types and attribute lists are all resolved
structurally rather than guessed at from a line's shape.

The escalation ladder is deliberate and always downward:

``EXACT``
    a grammar parsed the unit with no ``ERROR``/``MISSING`` node;
``HEURISTIC``
    the grammar parsed it but the tree contains error nodes (a dialect or a
    language version the grammar predates), or the language's visibility is
    not statically decidable from one file (Python, JavaScript, PHP);
``UNSUPPORTED``
    no grammar, no recognised declaration, or ``tree_sitter`` is not
    installed -- the caller must invalidate conservatively.

Nothing here silently upgrades confidence: a language with no profile below
falls back to the scanner, and the scanner's verdict stands.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache, lru_cache
from typing import Any

from .canonical import digest_of
from .interface_hash import (
    _CAPABILITY_PATTERNS,
    _EVENT_PATTERNS,
    _ROUTE_PATTERNS,
    _SCHEMA_PATTERNS,
    _UI_PATTERNS,
    DYNAMIC_LANGUAGES,
    ExtractionConfidence,
    ModuleInterface,
    Symbol,
    SymbolKind,
    _collect,
    _collect_imports,
    _strip_comments_and_strings,
    _visibility_for,
)

#: Node types that carry a declaration's modifiers.
MODIFIER_TYPES: frozenset[str] = frozenset(
    {
        "modifiers",
        "modifier",
        "accessibility_modifier",
        "override_modifier",
        "visibility_modifier",
        "class_modifier",
        "member_modifier",
        "function_modifier",
        "property_modifier",
        "inheritance_modifier",
        "mutation_modifier",
        "parameter_modifier",
        "abstract",
        "final",
        "static",
    }
)

#: Node types that carry annotations/attributes/decorators.
ANNOTATION_TYPES: frozenset[str] = frozenset(
    {
        "annotation",
        "marker_annotation",
        "attribute",
        "attribute_list",
        "attribute_item",
        "decorator",
        "attribute_declaration",
    }
)

#: Node types whose text is a declaration's name, when there is no ``name`` field.
NAME_TYPES: tuple[str, ...] = (
    "identifier",
    "type_identifier",
    "simple_identifier",
    "field_identifier",
    "property_identifier",
    "name",
    "package_identifier",
    "namespace_identifier",
)

BODY_TYPES: frozenset[str] = frozenset(
    {
        "class_body",
        "declaration_list",
        "field_declaration_list",
        "enum_body",
        "enum_class_body",
        "enumerator_list",
        "interface_body",
        "protocol_body",
        "statement_block",
        "compound_statement",
        "function_body",
        "block",
        "statements",
        "constructor_body",
        "enum_variant_list",
        "struct_type",
        "interface_type",
        "class_body_declaration",
    }
)

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _masked(text: str, language: str) -> str:
    """Signature text with comments and string *contents* removed.

    A literal inside an annotation -- a route path, a column name, a topic --
    is surface, and ``surface_digest`` already tracks it. Leaving it in the
    signature too would report every route rename as a public-API break and
    invalidate dependents that only ever called the method.
    """
    return _normalize(_strip_comments_and_strings(text, language))


def _body_text(text: str, language: str) -> str:
    """Body text with comments removed but literals kept.

    Comments are not behaviour, so a comment-only edit must not look like a
    body change. String literals *are* behaviour and stay.
    """
    hash_comment = language in ("python", "php")
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        two = text[index : index + 2]
        char = text[index]
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
            out.append(char)
            index += 1
            while index < length and text[index] != quote:
                if text[index] == "\\":
                    out.append(text[index])
                    index += 1
                if index < length:
                    out.append(text[index])
                    index += 1
            out.append(quote)
            index += 1
            continue
        out.append(char)
        index += 1
    return _normalize("".join(out))


@dataclass(frozen=True)
class GrammarProfile:
    """How one language's parse tree maps onto ELMOS symbols."""

    language: str
    grammar: str
    declarations: Mapping[str, SymbolKind]
    #: Non-declaration nodes that still open a named scope (``impl``, namespaces).
    extra_scopes: Mapping[str, str] = field(default_factory=dict)
    #: The body is the next named sibling rather than a child (Dart).
    sibling_body: bool = False
    #: C-family access labels (``public:``) set the default visibility.
    access_labels: bool = False
    #: Default visibility when nothing else says otherwise.
    default_visibility: str = ""
    #: ``export`` wrappers make the wrapped declaration public.
    export_wrappers: frozenset[str] = frozenset()
    #: Child node types that must not be mistaken for a declaration's name.
    name_skip: frozenset[str] = frozenset()
    #: Go-style methods carry their owning type in a receiver parameter.
    receiver_scope: bool = False


_TYPE = SymbolKind.TYPE
_FUNCTION = SymbolKind.FUNCTION
_FIELD = SymbolKind.FIELD
_CONSTANT = SymbolKind.CONSTANT
_ENUM_MEMBER = SymbolKind.ENUM_MEMBER

PROFILES: dict[str, GrammarProfile] = {
    "java": GrammarProfile(
        language="java",
        grammar="java",
        declarations={
            "class_declaration": _TYPE,
            "interface_declaration": _TYPE,
            "enum_declaration": _TYPE,
            "record_declaration": _TYPE,
            "annotation_type_declaration": _TYPE,
            "method_declaration": _FUNCTION,
            "constructor_declaration": _FUNCTION,
            "compact_constructor_declaration": _FUNCTION,
            "field_declaration": _FIELD,
            "enum_constant": _ENUM_MEMBER,
        },
    ),
    "kotlin": GrammarProfile(
        language="kotlin",
        grammar="kotlin",
        declarations={
            "class_declaration": _TYPE,
            "object_declaration": _TYPE,
            "type_alias": _TYPE,
            "function_declaration": _FUNCTION,
            "secondary_constructor": _FUNCTION,
            "property_declaration": _FIELD,
            "class_parameter": _FIELD,
            "enum_entry": _ENUM_MEMBER,
        },
        extra_scopes={"companion_object": "Companion"},
    ),
    "csharp": GrammarProfile(
        language="csharp",
        grammar="csharp",
        declarations={
            "class_declaration": _TYPE,
            "interface_declaration": _TYPE,
            "struct_declaration": _TYPE,
            "record_declaration": _TYPE,
            "record_struct_declaration": _TYPE,
            "enum_declaration": _TYPE,
            "delegate_declaration": _TYPE,
            "method_declaration": _FUNCTION,
            "constructor_declaration": _FUNCTION,
            "operator_declaration": _FUNCTION,
            "property_declaration": _FIELD,
            "field_declaration": _FIELD,
            "event_field_declaration": _FIELD,
            "enum_member_declaration": _ENUM_MEMBER,
        },
        extra_scopes={"namespace_declaration": "", "file_scoped_namespace_declaration": ""},
        default_visibility="private",
    ),
    "go": GrammarProfile(
        language="go",
        grammar="go",
        declarations={
            "type_spec": _TYPE,
            "type_alias": _TYPE,
            "function_declaration": _FUNCTION,
            "method_declaration": _FUNCTION,
            "const_spec": _CONSTANT,
            "var_spec": _FIELD,
            "field_declaration": _FIELD,
            "method_elem": _FUNCTION,
        },
        receiver_scope=True,
    ),
    "rust": GrammarProfile(
        language="rust",
        grammar="rust",
        declarations={
            "struct_item": _TYPE,
            "enum_item": _TYPE,
            "trait_item": _TYPE,
            "union_item": _TYPE,
            "type_item": _TYPE,
            "mod_item": _TYPE,
            "function_item": _FUNCTION,
            "function_signature_item": _FUNCTION,
            "const_item": _CONSTANT,
            "static_item": _CONSTANT,
            "field_declaration": _FIELD,
            "enum_variant": _ENUM_MEMBER,
        },
        extra_scopes={"impl_item": ""},
    ),
    "cpp": GrammarProfile(
        language="cpp",
        grammar="cpp",
        declarations={
            "class_specifier": _TYPE,
            "struct_specifier": _TYPE,
            "union_specifier": _TYPE,
            "enum_specifier": _TYPE,
            "alias_declaration": _TYPE,
            "function_definition": _FUNCTION,
            "declaration": _FUNCTION,
            "field_declaration": _FIELD,
            "enumerator": _ENUM_MEMBER,
        },
        extra_scopes={"namespace_definition": ""},
        access_labels=True,
    ),
    "php": GrammarProfile(
        language="php",
        grammar="php",
        declarations={
            "class_declaration": _TYPE,
            "interface_declaration": _TYPE,
            "trait_declaration": _TYPE,
            "enum_declaration": _TYPE,
            "method_declaration": _FUNCTION,
            "function_definition": _FUNCTION,
            "property_declaration": _FIELD,
            "const_declaration": _CONSTANT,
            "enum_case": _ENUM_MEMBER,
        },
        extra_scopes={"namespace_definition": ""},
    ),
    "typescript": GrammarProfile(
        language="typescript",
        grammar="typescript",
        declarations={
            "class_declaration": _TYPE,
            "abstract_class_declaration": _TYPE,
            "interface_declaration": _TYPE,
            "type_alias_declaration": _TYPE,
            "enum_declaration": _TYPE,
            "function_declaration": _FUNCTION,
            "method_definition": _FUNCTION,
            "method_signature": _FUNCTION,
            "abstract_method_signature": _FUNCTION,
            "public_field_definition": _FIELD,
            "property_signature": _FIELD,
            "variable_declarator": _CONSTANT,
            "enum_assignment": _ENUM_MEMBER,
        },
        export_wrappers=frozenset({"export_statement"}),
    ),
    "javascript": GrammarProfile(
        language="javascript",
        grammar="javascript",
        declarations={
            "class_declaration": _TYPE,
            "function_declaration": _FUNCTION,
            "generator_function_declaration": _FUNCTION,
            "method_definition": _FUNCTION,
            "field_definition": _FIELD,
            "variable_declarator": _CONSTANT,
        },
        export_wrappers=frozenset({"export_statement"}),
    ),
    "swift": GrammarProfile(
        language="swift",
        grammar="swift",
        declarations={
            "class_declaration": _TYPE,
            "protocol_declaration": _TYPE,
            "typealias_declaration": _TYPE,
            "function_declaration": _FUNCTION,
            "protocol_function_declaration": _FUNCTION,
            "init_declaration": _FUNCTION,
            "deinit_declaration": _FUNCTION,
            "subscript_declaration": _FUNCTION,
            "property_declaration": _FIELD,
            "enum_entry": _ENUM_MEMBER,
        },
    ),
    "dart": GrammarProfile(
        language="dart",
        grammar="dart",
        declarations={
            "class_definition": _TYPE,
            "mixin_declaration": _TYPE,
            "extension_declaration": _TYPE,
            "enum_declaration": _TYPE,
            "type_alias": _TYPE,
            "function_signature": _FUNCTION,
            "method_signature": _FUNCTION,
            "getter_signature": _FUNCTION,
            "setter_signature": _FUNCTION,
            "declaration": _FIELD,
            "initialized_variable_definition": _FIELD,
            "static_final_declaration": _CONSTANT,
            "enum_constant": _ENUM_MEMBER,
        },
        sibling_body=True,
        name_skip=frozenset({"type_identifier", "void_type", "function_type"}),
    ),
    "objectivec": GrammarProfile(
        language="objectivec",
        grammar="objc",
        declarations={
            "class_interface": _TYPE,
            "category_interface": _TYPE,
            "protocol_declaration": _TYPE,
            "method_declaration": _FUNCTION,
            "method_definition": _FUNCTION,
            "property_declaration": _FIELD,
            "function_definition": _FUNCTION,
            "enum_specifier": _TYPE,
            "enumerator": _ENUM_MEMBER,
        },
        # ``@implementation`` restates what ``@interface`` already declared; it
        # contributes bodies to those symbols, not new ones.
        extra_scopes={"class_implementation": "", "category_implementation": ""},
        name_skip=frozenset({"type_identifier"}),
        access_labels=True,
    ),
}


# Python is deliberately absent: ``interface_hash._extract_python`` uses the
# standard library's own ``ast``, which is the language's real parser and knows
# ``__all__``, decorators and dunder conventions that a generic tree walk does
# not.


class GrammarUnavailable(RuntimeError):
    """No parser for this language in this environment."""


@cache
def grammar_version() -> str:
    """The grammar bundle's version, which is part of every digest it produces."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("tree-sitter-language-pack")
    except PackageNotFoundError:  # pragma: no cover - depends on the environment
        return "unknown"


@lru_cache(maxsize=32)
def _parser(grammar: str) -> Any:
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise GrammarUnavailable("tree_sitter_language_pack is not installed") from error
    try:
        return get_parser(grammar)
    except Exception as error:  # noqa: BLE001 - the pack raises several types
        raise GrammarUnavailable(f"no grammar for {grammar!r}: {error}") from error


def available(language: str) -> bool:
    """True when this environment can parse ``language`` exactly."""
    profile = PROFILES.get(language)
    if profile is None:
        return False
    try:
        _parser(profile.grammar)
    except GrammarUnavailable:
        return False
    return True


# --------------------------------------------------------------------------
# tree walking
# --------------------------------------------------------------------------
def _text(node: Any) -> str:
    data: bytes = node.text or b""
    return data.decode("utf-8", "replace")


def _named_children(node: Any) -> list[Any]:
    return list(node.named_children)


def _name_of(node: Any, skip: frozenset[str] = frozenset()) -> str | None:
    named = node.child_by_field_name("name")
    if named is not None:
        return _leaf_name(named)
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        found = _declarator_name(declarator)
        if found is not None:
            return found
    for child in _named_children(node):
        if child.type in NAME_TYPES and child.type not in skip:
            return _leaf_name(child)
    for child in _named_children(node):
        found = _nested_name(child, skip)
        if found is not None:
            return found
    return None


def _leaf_name(node: Any) -> str:
    for child in _named_children(node):
        if child.type in NAME_TYPES:
            return _leaf_name(child)
    return _normalize(_text(node))


def _declarator_name(node: Any) -> str | None:
    """C/C++ wrap the name in nested declarators: ``*f(int)`` -> ``f``."""
    if node.type in NAME_TYPES or node.type in ("qualified_identifier", "operator_name"):
        return _normalize(_text(node))
    inner = node.child_by_field_name("declarator")
    if inner is not None:
        return _declarator_name(inner)
    for child in _named_children(node):
        found = _declarator_name(child)
        if found is not None:
            return found
    return None


def _nested_name(node: Any, skip: frozenset[str] = frozenset()) -> str | None:
    """Names that live one level down (Dart's ``initialized_identifier_list``)."""
    if node.type in (
        "initialized_identifier_list",
        "initialized_identifier",
        "variable_declaration",
        "constructor_signature",
        "function_signature",
        "user_type",
        "type_spec",
        "variable_declarator",
        "static_final_declaration",
        "init_declarator",
        "struct_declaration",
        "struct_declarator",
        "pointer_declarator",
    ):
        return _name_of(node, skip) or _leaf_name(node)
    return None


def _modifier_text(node: Any) -> str:
    parts: list[str] = []
    for child in _named_children(node):
        if child.type in MODIFIER_TYPES:
            parts.append(_normalize(_text(child)))
        elif child.type in ("storage_class_specifier", "type_qualifier"):
            parts.append(_normalize(_text(child)))
    return " ".join(parts)


def _annotations(node: Any, language: str) -> tuple[str, ...]:
    found: list[str] = []
    for child in _named_children(node):
        if child.type in ANNOTATION_TYPES:
            found.append(_masked(_text(child), language))
        elif child.type in MODIFIER_TYPES:
            for grandchild in _named_children(child):
                if grandchild.type in ANNOTATION_TYPES:
                    found.append(_masked(_text(grandchild), language))
    return tuple(sorted(set(found)))


def _body_of(node: Any, profile: GrammarProfile) -> Any | None:
    body = node.child_by_field_name("body")
    if body is not None:
        return body
    for child in _named_children(node):
        if child.type in BODY_TYPES:
            return child
    if profile.sibling_body:
        sibling = node.next_named_sibling
        if sibling is not None and sibling.type in BODY_TYPES:
            return sibling
    return None


def _signature(node: Any, body: Any | None, kind: SymbolKind, language: str) -> str:
    text = _text(node)
    if body is None:
        if kind is SymbolKind.TYPE:
            # A type whose members are siblings rather than a body node (an
            # Objective-C ``@interface``) is identified by its header alone.
            return _masked(text.split("\n", 1)[0], language)
        return _masked(text, language)
    body_text = _text(body)
    if body_text and body_text in text:
        text = text.replace(body_text, "")
    return _masked(text, language)


@dataclass
class _Walker:
    profile: GrammarProfile
    symbols: list[Symbol] = field(default_factory=list)
    layout: int = 0

    def visit(
        self, node: Any, scope: Sequence[str], exported: bool, access: str, inherited: str
    ) -> None:
        access_here = access
        for child in _named_children(node):
            if self.profile.access_labels and child.type == "access_specifier":
                access_here = _normalize(_text(child)).rstrip(":")
                continue
            self.visit_node(child, scope, exported, access_here, inherited)

    def visit_node(
        self, node: Any, scope: Sequence[str], exported: bool, access: str, inherited: str
    ) -> None:
        node_type = node.type
        if node_type in self.profile.export_wrappers:
            self.visit(node, scope, True, access, inherited)
            return
        if node_type in self.profile.extra_scopes:
            name = _name_of(node, self.profile.name_skip) or self.profile.extra_scopes[node_type]
            inner = [*scope, name] if name else list(scope)
            self.visit(node, inner, exported, self._default_access(node, access), inherited)
            return

        kind = self.profile.declarations.get(node_type)
        if kind is None:
            self.visit(node, scope, exported, access, inherited)
            return
        kind = self._refine_kind(node, kind)

        declared = _name_of(node, self.profile.name_skip)
        if not declared:
            self.visit(node, scope, exported, access, inherited)
            return
        name = declared

        # A Swift ``extension Foo`` reuses ``class_declaration``; it extends an
        # existing type rather than declaring a new one.
        if self.profile.language == "swift" and _text(node).lstrip().startswith("extension"):
            self.visit(node, [*scope, name], exported, access, inherited)
            return

        owner = list(scope)
        if self.profile.receiver_scope:
            receiver = _receiver_type(node)
            if receiver:
                owner = [*scope, receiver]

        body = _body_of(node, self.profile)
        modifiers = _modifier_text(node)
        visibility = self._visibility(node, name, modifiers, exported, access, bool(owner), kind, inherited)
        layout_index: int | None = None
        if kind in (_FIELD, _ENUM_MEMBER, _TYPE, _CONSTANT):
            layout_index = self.layout
            self.layout += 1
        self.symbols.append(
            Symbol(
                symbol_id="::".join([*owner, name]),
                kind=kind,
                name=name,
                visibility=visibility,
                signature=_signature(node, body, kind, self.profile.language),
                annotations=_annotations(node, self.profile.language),
                layout_index=layout_index,
                body_digest=digest_of(_body_text(_text(body), self.profile.language)) if body is not None else None,
            )
        )
        # Only type-like declarations are containers. Walking into a function
        # body would turn its locals into public API, which is exactly the
        # class of mistake this module exists to remove.
        if kind is _TYPE:
            self.visit(node, [*owner, name], False, self._default_access(node, access), visibility)

    def _refine_kind(self, node: Any, kind: SymbolKind) -> SymbolKind:
        """C++ spells prototypes and variables with the same ``declaration`` node."""
        if self.profile.language == "cpp" and node.type == "declaration":
            declarator = node.child_by_field_name("declarator")
            if declarator is None or not _contains_type(declarator, "function_declarator"):
                return _FIELD
        return kind

    def _default_access(self, node: Any, access: str) -> str:
        if not self.profile.access_labels:
            return access
        text = _text(node).lstrip()
        if text.startswith(("struct", "@interface", "@protocol", "@implementation")):
            return "public"
        if text.startswith("class"):
            return "private"
        return access

    def _visibility(
        self,
        node: Any,
        name: str,
        modifiers: str,
        exported: bool,
        access: str,
        nested: bool,
        kind: SymbolKind,
        inherited: str,
    ) -> str:
        if exported:
            return "public"
        if modifiers:
            resolved = _visibility_for(self.profile.language, modifiers, name, nested=nested)
            if resolved != _fallback_visibility(self.profile.language, name, nested):
                return resolved
        if kind is _ENUM_MEMBER and inherited:
            # An enum's constants are exactly as visible as the enum itself.
            return inherited
        if self.profile.access_labels and access:
            return access
        if self.profile.default_visibility and not modifiers:
            return self.profile.default_visibility
        return _visibility_for(self.profile.language, modifiers, name, nested=nested)


def _contains_type(node: Any, wanted: str) -> bool:
    if node.type == wanted:
        return True
    return any(_contains_type(child, wanted) for child in _named_children(node))


def _receiver_type(node: Any) -> str:
    """``func (g *Greeter) Greet()`` belongs to ``Greeter``."""
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return ""
    for candidate in _named_children(receiver):
        found = _find_type_identifier(candidate)
        if found:
            return found
    return ""


def _find_type_identifier(node: Any) -> str:
    if node.type == "type_identifier":
        return _normalize(_text(node))
    for child in _named_children(node):
        found = _find_type_identifier(child)
        if found:
            return found
    return ""


def _merge_duplicates(symbols: Sequence[Symbol]) -> tuple[Symbol, ...]:
    """A declaration and its definition are one symbol; overloads are not.

    Objective-C states a method in ``@interface`` and again in
    ``@implementation``; C++ does the same across a header boundary. Merging on
    *identical* signatures folds those into a single symbol while leaving
    genuine overloads -- same name, different signature -- as the distinct API
    entries they are.
    """
    merged: dict[tuple[str, str, str], Symbol] = {}
    for symbol in symbols:
        key = (symbol.symbol_id, symbol.kind.value, _signature_key(symbol.signature))
        existing = merged.get(key)
        if existing is None:
            merged[key] = symbol
            continue
        merged[key] = Symbol(
            symbol_id=existing.symbol_id,
            kind=existing.kind,
            name=existing.name,
            visibility=existing.visibility,
            signature=existing.signature,
            annotations=tuple(sorted(set(existing.annotations) | set(symbol.annotations))),
            layout_index=existing.layout_index if existing.layout_index is not None else symbol.layout_index,
            body_digest=existing.body_digest or symbol.body_digest,
        )
    return tuple(merged.values())


def _signature_key(signature: str) -> str:
    return signature.rstrip("; ").strip()


def _fallback_visibility(language: str, name: str, nested: bool) -> str:
    return _visibility_for(language, "", name, nested=nested)


def _has_error(node: Any) -> bool:
    return bool(node.has_error)


def _iter_nodes(node: Any) -> Iterator[Any]:
    yield node
    for child in node.children:
        yield from _iter_nodes(child)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def extract(language: str, logical_path: str, source: str) -> ModuleInterface:
    """Exact extraction, or raise ``GrammarUnavailable`` for the caller to fall back."""
    profile = PROFILES.get(language)
    if profile is None:
        raise GrammarUnavailable(f"no grammar profile for {language!r}")
    parser = _parser(profile.grammar)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    walker = _Walker(profile)
    walker.visit(root, [], False, "", "")
    symbols = _merge_duplicates(walker.symbols)

    notes: list[str] = []
    confidence = ExtractionConfidence.EXACT
    if _has_error(root):
        confidence = ExtractionConfidence.HEURISTIC
        notes.append("the grammar reported error nodes; reuse stays conservative")
    if language in DYNAMIC_LANGUAGES:
        confidence = min(confidence, ExtractionConfidence.HEURISTIC, key=_rank)
        notes.append("dynamic language: visibility is heuristic, reuse stays conservative")
    if not symbols:
        confidence = ExtractionConfidence.UNSUPPORTED
        notes.append("no declarations recognised; treating the unit as opaque")
    notes.append(f"parsed by tree-sitter grammar {profile.grammar!r}")

    return ModuleInterface(
        language=language,
        logical_path=logical_path,
        confidence=confidence,
        symbols=symbols,
        routes=_collect(_ROUTE_PATTERNS, source),
        events=_collect(_EVENT_PATTERNS, source),
        schema_elements=_collect(_SCHEMA_PATTERNS, source),
        ui_components=_collect(_UI_PATTERNS, source),
        capabilities=_collect(_CAPABILITY_PATTERNS, source),
        imports=_collect_imports(source),
        notes=tuple(notes),
        raw_digest=digest_of(source),
        extractor=f"tree-sitter/{profile.grammar}@{grammar_version()}",
    )


_RANK = {
    ExtractionConfidence.EXACT: 2,
    ExtractionConfidence.HEURISTIC: 1,
    ExtractionConfidence.UNSUPPORTED: 0,
}


def _rank(confidence: ExtractionConfidence) -> int:
    return _RANK[confidence]
