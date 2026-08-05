"""Whole-program symbol resolution.

The engine used to lower one file at a time.  That is a reasonable place to
start and a dead end: a call to a class declared in another file has no type, so
it is refused, and measurement showed that this single limitation blocked 94% of
the files that failed to translate.  No amount of standard-library work moves
that number.

So there are now two passes.  The first scans every file for *declarations only*
and builds an index; the second lowers and emits with that index in hand.

Two properties of the scan matter more than they look:

* **It cannot fail.**  A file whose method bodies use constructs the front end
  refuses must still contribute its signatures, because other files depend on
  them.  Bodies are never visited, and a type that will not lower is recorded as
  unknown rather than raising.
* **It resolves names per file.**  ``Foo`` means different things in different
  files depending on package and imports, so the index stores what was written
  and resolves it afterwards, once every declaration is known.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import uir
from .uir import ClassType, UnknownType


@dataclass(frozen=True)
class MethodInfo:
    name: str
    return_type: uir.Type
    param_types: tuple[uir.Type, ...]
    is_static: bool
    is_varargs: bool
    is_abstract: bool


@dataclass(frozen=True)
class FieldInfo:
    name: str
    type: uir.Type
    is_static: bool


@dataclass
class TypeInfo:
    """One declared type, with its members and where it came from."""

    simple_name: str
    qualified_name: str
    kind: str  # class | interface | enum | record
    package: str | None
    source_file: str
    #: The Python module the generated code for this type lives in.
    module: str
    modifiers: tuple[str, ...] = ()
    superclass_text: str | None = None
    interface_texts: tuple[str, ...] = ()
    fields: dict[str, FieldInfo] = field(default_factory=dict)
    methods: dict[str, list[MethodInfo]] = field(default_factory=dict)
    record_components: tuple[tuple[str, uir.Type], ...] = ()
    enum_constants: tuple[str, ...] = ()
    enclosing: str | None = None

    def method(self, name: str) -> MethodInfo | None:
        """The first overload of ``name``.

        Overload *selection* needs argument types the front end does not always
        have, so this returns the first declaration and the emitter refuses the
        call when the overloads disagree about what it would need to know.
        """

        found = self.methods.get(name)
        return found[0] if found else None

    def is_functional_interface(self) -> tuple[str, MethodInfo] | None:
        if self.kind != "interface":
            return None
        abstract = [m for ms in self.methods.values() for m in ms if m.is_abstract]
        if len(abstract) == 1:
            return abstract[0].name, abstract[0]
        return None


@dataclass
class FileDeclarations:
    path: str
    package: str | None
    imports: tuple[str, ...]
    types: list[TypeInfo]


class ProgramIndex:
    """Every type declared in the scanned tree, resolvable by simple name."""

    def __init__(self) -> None:
        self.types: dict[str, TypeInfo] = {}
        self._by_simple: dict[str, list[TypeInfo]] = {}
        #: Nested types keyed by the way they are usually written: `Outer.Inner`.
        self._by_tail: dict[str, list[TypeInfo]] = {}
        self.files: list[FileDeclarations] = []
        #: Files that could not be scanned at all, with why.  Reported rather
        #: than swallowed: a missing file silently narrows every lookup.
        self.unscanned: list[tuple[str, str]] = []
        #: Two declarations claiming one qualified name -- duplicated source
        #: roots, or a generated copy checked in beside its source.  The first
        #: wins and the clash is reported, because silently overwriting would
        #: make resolution depend on directory iteration order.
        self.collisions: list[tuple[str, str, str]] = []

    def add(self, declarations: FileDeclarations) -> None:
        self.files.append(declarations)
        for info in declarations.types:
            existing = self.types.get(info.qualified_name)
            if existing is not None:
                self.collisions.append(
                    (info.qualified_name, existing.source_file, info.source_file)
                )
                continue
            self.types[info.qualified_name] = info
            self._by_simple.setdefault(info.simple_name, []).append(info)
            if info.enclosing is not None:
                tail = f"{info.enclosing.rsplit('.', 1)[-1]}.{info.simple_name}"
                self._by_tail.setdefault(tail, []).append(info)

    def resolve(
        self, name: str, package: str | None, imports: tuple[str, ...]
    ) -> TypeInfo | None:
        """Resolve a written type name the way Java would, in this order.

        An explicit single-type import wins, then the same package, then a
        wildcard import, then -- only if the name is unambiguous across the
        whole program -- a global match.  The last step is a deliberate
        relaxation: it lets an unimported name resolve when there is exactly one
        candidate, and refuses to guess when there is more than one.
        """

        if "." in name:
            direct = self.types.get(name)
            if direct is not None:
                return direct
            nested = self._by_tail.get(name, [])
            if len(nested) == 1:
                return nested[0]
            name = name.rsplit(".", 1)[1]

        for imported in imports:
            if imported.rsplit(".", 1)[-1] == name:
                found = self.types.get(imported)
                if found is not None:
                    return found

        if package is not None:
            found = self.types.get(f"{package}.{name}")
            if found is not None:
                return found

        for imported in imports:
            if imported.endswith(".*"):
                found = self.types.get(f"{imported[:-2]}.{name}")
                if found is not None:
                    return found

        candidates = self._by_simple.get(name, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    def simple_names(self) -> set[str]:
        return set(self._by_simple)

    def summary(self) -> dict:
        return {
            "files_scanned": len(self.files),
            "types_indexed": len(self.types),
            "ambiguous_simple_names": sorted(
                name for name, v in self._by_simple.items() if len(v) > 1
            )[:40],
            "unscanned": self.unscanned[:20],
            "collisions": self.collisions[:20],
        }


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

_TYPE_NODES = (
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
)


def scan_file(path: Path) -> FileDeclarations:
    """Extract declarations from one file without lowering any body."""

    from .frontend.java import JavaFrontend, UnsupportedConstruct

    source = Path(path).read_bytes()
    frontend = JavaFrontend(source, Path(path).name)
    tree = frontend._parser.parse(source)
    root = tree.root_node

    package: str | None = None
    imports: list[str] = []
    for child in root.children:
        if not child.is_named:
            continue
        if child.type == "package_declaration":
            named = [c for c in child.children if c.is_named]
            if named:
                package = frontend._text(named[0])
        elif child.type == "import_declaration":
            text = frontend._text(child)
            text = text.removeprefix("import").strip().rstrip(";").strip()
            imports.append(text.removeprefix("static").strip())

    module = Path(path).stem
    types: list[TypeInfo] = []
    for child in root.children:
        if child.is_named and child.type in _TYPE_NODES:
            _scan_type(frontend, child, package, module, str(path), types, None)

    return FileDeclarations(
        path=str(path), package=package, imports=tuple(imports), types=types
    )


def _safe_type(frontend, node) -> uir.Type:
    """Lower a type node, degrading to unknown rather than raising.

    The index must survive files the front end cannot fully lower; refusing to
    record a signature because one parameter used an exotic type would make
    every *caller* of that method unresolvable too.
    """

    from .frontend.java import UnsupportedConstruct

    if node is None:
        return UnknownType("scan:missing-type")
    try:
        return frontend._type(node)
    except (UnsupportedConstruct, RecursionError):
        return UnknownType("scan:unsupported-type")


def _modifier_tokens(node) -> tuple[str, ...]:
    for child in node.children:
        if child.type == "modifiers":
            return tuple(t.type for t in child.children if t.type.isalpha())
    return ()


def _scan_type(
    frontend,
    node,
    package: str | None,
    module: str,
    source_file: str,
    out: list[TypeInfo],
    enclosing: str | None,
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    simple = frontend._text(name_node)
    if enclosing is not None:
        # A nested type is qualified through its enclosing type, not straight
        # off the package: `pkg.Outer.Inner`, never `pkg.Inner`.  Flattening it
        # would let a nested class silently displace a top-level one.
        qualified = f"{enclosing}.{simple}"
    else:
        qualified = f"{package}.{simple}" if package else simple
    kind = {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "record_declaration": "record",
    }[node.type]

    # Type parameters must be in scope while member types are lowered, or `T`
    # would resolve to a class named T that does not exist.
    introduced = set()
    params_node = node.child_by_field_name("type_parameters")
    if params_node is not None:
        for child in params_node.children:
            if child.type == "type_parameter":
                for grand in child.children:
                    if grand.type == "type_identifier":
                        introduced.add(frontend._text(grand))
                        break
    frontend._type_variables |= introduced

    info = TypeInfo(
        simple_name=simple,
        qualified_name=qualified,
        kind=kind,
        package=package,
        source_file=source_file,
        module=module,
        modifiers=_modifier_tokens(node),
        enclosing=enclosing,
    )

    superclass = node.child_by_field_name("superclass")
    if superclass is not None:
        named = [c for c in superclass.children if c.is_named]
        if named:
            info.superclass_text = frontend._text(named[0])

    interfaces_node = node.child_by_field_name("interfaces")
    if interfaces_node is not None:
        texts = []
        for item in interfaces_node.children:
            if not item.is_named:
                continue
            for entry in ([c for c in item.children if c.is_named] or [item]):
                texts.append(frontend._text(entry))
        info.interface_texts = tuple(texts)

    if kind == "record":
        parameters = node.child_by_field_name("parameters")
        components: list[tuple[str, uir.Type]] = []
        if parameters is not None:
            for child in parameters.children:
                if child.type != "formal_parameter":
                    continue
                component_name = child.child_by_field_name("name")
                if component_name is None:
                    continue
                component_type = _safe_type(frontend, child.child_by_field_name("type"))
                components.append((frontend._text(component_name), component_type))
        info.record_components = tuple(components)
        for component_name, component_type in components:
            # A record component is reachable as both a field and an accessor.
            info.fields[component_name] = FieldInfo(component_name, component_type, False)
            info.methods.setdefault(component_name, []).append(
                MethodInfo(component_name, component_type, (), False, False, False)
            )

    body = node.child_by_field_name("body")
    if body is not None:
        for member in body.children:
            if not member.is_named:
                continue
            if member.type in _TYPE_NODES:
                _scan_type(
                    frontend, member, package, module, source_file, out, qualified
                )
            elif member.type == "field_declaration":
                _scan_field(frontend, member, info)
            elif member.type in ("method_declaration", "constructor_declaration"):
                _scan_method(frontend, member, info)
            elif member.type == "enum_body_declarations":
                for sub in member.children:
                    if not sub.is_named:
                        continue
                    if sub.type == "field_declaration":
                        _scan_field(frontend, sub, info)
                    elif sub.type in ("method_declaration", "constructor_declaration"):
                        _scan_method(frontend, sub, info)
            elif member.type == "enum_constant":
                constant = member.child_by_field_name("name")
                if constant is not None:
                    info.enum_constants += (frontend._text(constant),)

    frontend._type_variables -= introduced
    out.append(info)


def _scan_field(frontend, node, info: TypeInfo) -> None:
    declared = _safe_type(frontend, node.child_by_field_name("type"))
    modifiers = _modifier_tokens(node)
    for child in node.children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name")
        if name_node is None:
            continue
        name = frontend._text(name_node)
        info.fields[name] = FieldInfo(name, declared, "static" in modifiers)


def _scan_method(frontend, node, info: TypeInfo) -> None:
    is_constructor = node.type == "constructor_declaration"
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = "<init>" if is_constructor else frontend._text(name_node)

    introduced = set()
    params_node = node.child_by_field_name("type_parameters")
    if params_node is not None:
        for child in params_node.children:
            if child.type == "type_parameter":
                for grand in child.children:
                    if grand.type == "type_identifier":
                        introduced.add(frontend._text(grand))
                        break
    frontend._type_variables |= introduced

    return_type = (
        UnknownType("constructor")
        if is_constructor
        else _safe_type(frontend, node.child_by_field_name("type"))
    )
    modifiers = _modifier_tokens(node)
    parameters = node.child_by_field_name("parameters")
    param_types: list[uir.Type] = []
    is_varargs = False
    if parameters is not None:
        for child in parameters.children:
            if child.type == "formal_parameter":
                param_types.append(_safe_type(frontend, child.child_by_field_name("type")))
            elif child.type == "spread_parameter":
                is_varargs = True
                named = [c for c in child.children if c.is_named]
                element = _safe_type(frontend, named[0]) if named else UnknownType("varargs")
                param_types.append(uir.ArrayType(element))

    info.methods.setdefault(name, []).append(
        MethodInfo(
            name=name,
            return_type=return_type,
            param_types=tuple(param_types),
            is_static="static" in modifiers,
            is_varargs=is_varargs,
            is_abstract=node.child_by_field_name("body") is None,
        )
    )
    frontend._type_variables -= introduced


def scan_tree(root: Path, limit: int = 0) -> ProgramIndex:
    """Index every ``.java`` file under ``root``."""

    index = ProgramIndex()
    files = sorted(Path(root).rglob("*.java"))
    if limit:
        files = files[:limit]
    for path in files:
        try:
            index.add(scan_file(path))
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            index.unscanned.append((str(path), repr(exc)[:160]))
    return index


def scan_files(paths) -> ProgramIndex:
    index = ProgramIndex()
    for path in paths:
        try:
            index.add(scan_file(Path(path)))
        except Exception as exc:  # noqa: BLE001
            index.unscanned.append((str(path), repr(exc)[:160]))
    return index
