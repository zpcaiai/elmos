"""Java front end: tree-sitter CST -> Unified Semantic IR.

The governing rule is **fail closed**.  Any construct this front end does not
model raises :class:`UnsupportedConstruct` with a source location.  It never
drops a node, never substitutes a placeholder, and never emits an approximation.
A front end that silently skips what it does not understand produces a
translation that looks complete and is not, which is the exact failure mode this
whole engine exists to prevent.

Type inference is deliberate rather than incidental: the emitter cannot pick the
right wrapping helper (32-bit vs 64-bit), cannot tell ``a + b`` on ints from
string concatenation, and cannot honour the implicit narrowing cast in ``i += d``
without a static type for every expression.  Where a type genuinely cannot be
determined, the IR records :class:`~j2p.uir.UnknownType` so it is countable and
gateable instead of invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import uir
from ..uir import (
    ArrayAccess,
    ArrayLength,
    ArrayType,
    Assign,
    Binary,
    Block,
    BoolLiteral,
    Break,
    Call,
    Cast,
    CatchClause,
    CharLiteral,
    ClassType,
    Continue,
    DoWhile,
    Expr,
    ExprStmt,
    Field,
    FieldAccess,
    FloatLiteral,
    For,
    ForEach,
    If,
    IncDec,
    InstanceOf,
    IntLiteral,
    Lambda,
    LocalVar,
    MethodRef,
    Method,
    Module,
    Name,
    New,
    NewArray,
    NullLiteral,
    Origin,
    Param,
    PrimitiveType,
    Return,
    StaticCall,
    StaticFieldAccess,
    Stmt,
    StringConcat,
    StringLiteral,
    Switch,
    SwitchCase,
    Ternary,
    This,
    Throw,
    Try,
    TypeDecl,
    Unary,
    UnknownType,
    While,
)

try:  # pragma: no cover - import guard
    import tree_sitter_java
    from tree_sitter import Language, Node, Parser
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "the Java front end requires tree_sitter and tree_sitter_java; install "
        "them with `pip install -r requirements.txt`.  It deliberately does not "
        "fall back to a regex parser."
    ) from exc


class UnsupportedConstruct(Exception):
    """A Java construct this front end refuses to translate."""

    def __init__(self, message: str, origin: Origin) -> None:
        super().__init__(f"{origin.file}:{origin.line}:{origin.column}: {message}")
        self.origin = origin
        self.reason = message


class ParseError(Exception):
    """The source did not parse as Java."""


_TYPE_DECL_NODES = (
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
)

#: Types whose values map onto Python built-ins without a wrapper class.
KNOWN_CLASS_TYPES = frozenset(
    {
        "String",
        "Object",
        "Integer",
        "Long",
        "Double",
        "Boolean",
        "Character",
        "StringBuilder",
        "Math",
        "System",
        "List",
        "ArrayList",
        "Map",
        "HashMap",
        "Set",
        "HashSet",
        "Objects",
    }
    | set(uir.FUNCTIONAL_INTERFACES)
)

_MODIFIER_TOKENS = frozenset(
    {
        "public",
        "protected",
        "private",
        "static",
        "final",
        "abstract",
        "synchronized",
        "native",
        "transient",
        "volatile",
        "strictfp",
        "default",
    }
)

_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    "s": " ",
    "0": "\0",
    "'": "'",
    '"': '"',
    "\\": "\\",
}


@dataclass
class _Scope:
    """A lexical scope.

    ``is_field_scope`` marks the outermost scope, which holds the enclosing
    class's fields rather than locals.  The distinction is not cosmetic: a
    parameter named ``value`` shadows a field named ``value``, and a front end
    that cannot tell them apart emits ``self.value = self.value``.
    """

    names: dict[str, uir.Type]
    parent: "_Scope | None" = None
    is_field_scope: bool = False

    def lookup(self, name: str) -> uir.Type | None:
        found = self.resolve(name)
        return None if found is None else found[0]

    def resolve(self, name: str) -> tuple[uir.Type, bool] | None:
        """Return ``(type, is_field)`` for ``name``, innermost scope first."""

        scope: _Scope | None = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name], scope.is_field_scope
            scope = scope.parent
        return None

    def child(self) -> "_Scope":
        return _Scope(names={}, parent=self)


class JavaFrontend:
    """Lower one Java compilation unit to UIR."""

    def __init__(self, source: bytes, filename: str) -> None:
        self.source = source
        self.filename = filename
        self._language = Language(tree_sitter_java.language())
        self._parser = Parser(self._language)
        #: Return types of methods declared in this compilation unit, so calls
        #: to them are typed instead of degrading to UnknownType.
        self._method_types: dict[str, uir.Type] = {}
        #: Declared parameter types per method, so that a lambda passed as an
        #: argument learns its target functional interface.  Without this,
        #: `fold((p, q) -> p - q, ...)` has untyped parameters and is refused.
        self._method_param_types: dict[str, tuple[uir.Type, ...]] = {}
        self._field_types: dict[str, uir.Type] = {}
        self._static_field_names: set[str] = set()
        self._static_method_names: set[str] = set()
        #: Interfaces declared here that have exactly one abstract method, and
        #: that method's name, result type and parameter types.  Without this a
        #: lambda targeting a project's own callback interface has no types at
        #: all, and every use of it is refused.
        self._interface_sams: dict[str, tuple[str, uir.Type, tuple[uir.Type, ...]]] = {}
        self._class_names: set[str] = set()
        self._current_class: str | None = None

    # -- entry point ------------------------------------------------------

    @classmethod
    def from_path(cls, path) -> "JavaFrontend":
        import pathlib

        p = pathlib.Path(path)
        return cls(p.read_bytes(), p.name)

    def parse(self) -> Module:
        tree = self._parser.parse(self.source)
        root = tree.root_node
        if root.has_error:
            bad = self._first_error(root)
            raise ParseError(
                f"{self.filename}: source does not parse as Java "
                f"(first problem near line {bad.start_point[0] + 1})"
            )
        return self._module(root)

    def _first_error(self, node: "Node") -> "Node":
        if node.type == "ERROR" or node.is_missing:
            return node
        for child in node.children:
            if child.has_error:
                return self._first_error(child)
        return node

    # -- helpers ----------------------------------------------------------

    def _origin(self, node: "Node") -> Origin:
        row, col = node.start_point
        return Origin(file=self.filename, line=row + 1, column=col + 1)

    def _text(self, node: "Node") -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8")

    def _reject(self, node: "Node", what: str) -> "Any":
        raise UnsupportedConstruct(
            f"unsupported Java construct: {node.type} (as {what})", self._origin(node)
        )

    @staticmethod
    def _named(node: "Node") -> list["Node"]:
        return [c for c in node.children if c.is_named]

    # -- module -----------------------------------------------------------

    def _module(self, root: "Node") -> Module:
        package: str | None = None
        imports: list[str] = []
        decls: list["Node"] = []

        for child in self._named(root):
            if child.type == "package_declaration":
                package = self._text(child.named_children[0])
            elif child.type == "import_declaration":
                imports.append(self._text(child.named_children[0]))
            elif child.type in _TYPE_DECL_NODES:
                decls.append(child)
            elif child.type in ("line_comment", "block_comment"):
                continue
            else:
                self._reject(child, "top-level declaration")

        # Pre-pass: collect signatures so forward references type correctly.
        for decl in decls:
            self._collect_signatures(decl)

        types: list[TypeDecl] = []
        for d in decls:
            types.extend(self._type_decl(d))
        return Module(
            origin=self._origin(root),
            package=package,
            imports=tuple(imports),
            types=tuple(types),
        )

    def _collect_signatures(self, decl: "Node") -> None:
        decl_name = self._text(decl.child_by_field_name("name"))
        self._class_names.add(decl_name)
        if decl.type == "interface_declaration":
            body = decl.child_by_field_name("body")
            abstract = [
                m
                for m in (self._named(body) if body is not None else [])
                if m.type == "method_declaration"
                and m.child_by_field_name("body") is None
            ]
            if len(abstract) == 1:
                m = abstract[0]
                self._interface_sams[decl_name] = (
                    self._text(m.child_by_field_name("name")),
                    self._type(m.child_by_field_name("type")),
                    tuple(
                        self._type(p.child_by_field_name("type"))
                        for p in self._named(m.child_by_field_name("parameters"))
                        if p.type == "formal_parameter"
                    ),
                )
        if decl.type == "record_declaration":
            params = decl.child_by_field_name("parameters")
            if params is not None:
                for component in self._named(params):
                    if component.type != "formal_parameter":
                        continue
                    name = self._text(component.child_by_field_name("name"))
                    # A record component is reachable both as a field and as an
                    # accessor method of the same name.
                    self._method_types[name] = self._type(
                        component.child_by_field_name("type")
                    )
        body = decl.child_by_field_name("body")
        if body is None:
            return
        for member in self._named(body):
            if member.type in _TYPE_DECL_NODES:
                self._collect_signatures(member)
            elif member.type == "method_declaration":
                name = self._text(member.child_by_field_name("name"))
                self._method_types[name] = self._type(member.child_by_field_name("type"))
                self._method_param_types[name] = tuple(
                    self._type(p.child_by_field_name("type"))
                    for p in self._named(member.child_by_field_name("parameters"))
                    if p.type == "formal_parameter"
                )
                if any(
                    tok.type == "static"
                    for mod in member.children
                    if mod.type == "modifiers"
                    for tok in mod.children
                ):
                    self._static_method_names.add(name)
            elif member.type == "field_declaration":
                declared = self._type(member.child_by_field_name("type"))
                is_static = any(
                    tok.type == "static"
                    for mod in member.children
                    if mod.type == "modifiers"
                    for tok in mod.children
                )
                for d in member.children_by_field_name("declarator"):
                    field_name = self._text(d.child_by_field_name("name"))
                    self._field_types[field_name] = declared
                    if is_static:
                        self._static_field_names.add(field_name)

    def _type_decl(self, node: "Node", enclosing: str | None = None) -> list[TypeDecl]:
        """Lower one type declaration, flattening any nested declarations.

        Java nests types lexically; Python does not need to, and a nested class
        emitted as a nested Python class would be harder to reference.  Non-static
        inner classes are rejected outright rather than flattened, because they
        capture the enclosing instance and flattening would silently drop that.
        """

        origin = self._origin(node)
        name = self._text(node.child_by_field_name("name"))
        previous_class = self._current_class
        previous_static = set(self._static_field_names)
        self._current_class = name
        kind = {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "record",
        }[node.type]
        modifiers = self._modifiers(node)
        if (
            enclosing is not None
            and kind == "class"
            and "static" not in modifiers
        ):
            self._reject(
                node,
                "non-static inner class (it captures the enclosing instance)",
            )
        nested: list[TypeDecl] = []

        if node.child_by_field_name("type_parameters") is not None:
            self._reject(node, "generic type declaration")

        superclass: uir.Type | None = None
        superclass_node = node.child_by_field_name("superclass")
        if superclass_node is not None:
            named = self._named(superclass_node)
            superclass = self._type(named[0]) if named else None

        interfaces: list[uir.Type] = []
        interfaces_node = node.child_by_field_name("interfaces")
        if interfaces_node is not None:
            for item in self._named(interfaces_node):
                for entry in self._named(item) or [item]:
                    interfaces.append(self._type(entry))

        record_components: list[Param] = []
        if kind == "record":
            params_node = node.child_by_field_name("parameters")
            if params_node is not None:
                record_components = list(self._params(params_node))
            for component in record_components:
                self._field_types[component.name] = component.type

        fields: list[Field] = []
        methods: list[Method] = []
        enum_constants: list[str] = []

        body = node.child_by_field_name("body")
        if body is not None:
            for member in self._named(body):
                if member.type == "field_declaration":
                    fields.extend(self._field(member))
                elif member.type == "method_declaration":
                    methods.append(self._method(member, name))
                elif member.type == "constructor_declaration":
                    methods.append(self._constructor(member, name))
                elif member.type == "enum_body_declarations":
                    for sub in self._named(member):
                        if sub.type == "field_declaration":
                            fields.extend(self._field(sub))
                        elif sub.type == "method_declaration":
                            methods.append(self._method(sub, name))
                        elif sub.type == "constructor_declaration":
                            methods.append(self._constructor(sub, name))
                        elif sub.type in ("line_comment", "block_comment", ";"):
                            continue
                        else:
                            self._reject(sub, "enum body member")
                elif member.type in _TYPE_DECL_NODES:
                    nested.extend(self._type_decl(member, enclosing=name))
                    self._current_class = name
                elif member.type == "compact_constructor_declaration":
                    self._reject(member, "compact record constructor")
                elif member.type == "static_initializer":
                    self._reject(member, "static initializer block")
                elif member.type == "enum_constant":
                    if member.child_by_field_name("arguments") is not None:
                        self._reject(member, "enum constant with arguments")
                    if member.child_by_field_name("body") is not None:
                        self._reject(member, "enum constant with body")
                    enum_constants.append(self._text(member.child_by_field_name("name")))
                elif member.type in ("line_comment", "block_comment", ";"):
                    continue
                else:
                    self._reject(member, "class member")

        self._current_class = previous_class
        self._static_field_names = previous_static
        decl = TypeDecl(
            origin=origin,
            name=name,
            kind=kind,
            modifiers=modifiers,
            superclass=superclass,
            interfaces=tuple(interfaces),
            fields=tuple(fields),
            methods=tuple(methods),
            enum_constants=tuple(enum_constants),
            record_components=tuple(record_components),
            enclosing=enclosing,
        )
        return [decl, *nested]

    def _modifiers(self, node: "Node") -> tuple[str, ...]:
        for child in node.children:
            if child.type == "modifiers":
                out: list[str] = []
                for token in child.children:
                    if token.type in _MODIFIER_TOKENS:
                        out.append(token.type)
                    elif token.type in ("marker_annotation", "annotation"):
                        continue
                    else:
                        self._reject(token, "modifier")
                return tuple(out)
        return ()

    def _field(self, node: "Node") -> list[Field]:
        origin = self._origin(node)
        modifiers = self._modifiers(node)
        declared = self._type(node.child_by_field_name("type"))
        scope = _Scope(names=dict(self._field_types), is_field_scope=True)
        out: list[Field] = []
        for declarator in node.children_by_field_name("declarator"):
            name = self._text(declarator.child_by_field_name("name"))
            value_node = declarator.child_by_field_name("value")
            init = self._expr(value_node, scope) if value_node is not None else None
            if init is not None:
                init = self._coerce(init, declared)
            out.append(
                Field(
                    origin=origin,
                    name=name,
                    type=declared,
                    modifiers=modifiers,
                    init=init,
                )
            )
        return out

    def _method(self, node: "Node", owner: str) -> Method:
        if node.child_by_field_name("type_parameters") is not None:
            self._reject(node, "generic method")
        origin = self._origin(node)
        name = self._text(node.child_by_field_name("name"))
        return_type = self._type(node.child_by_field_name("type"))
        modifiers = self._modifiers(node)
        params = self._params(node.child_by_field_name("parameters"))

        scope = _Scope(names=dict(self._field_types), is_field_scope=True)
        scope = scope.child()
        for p in params:
            scope.names[p.name] = p.type
        scope.names["__return__"] = return_type

        body_node = node.child_by_field_name("body")
        body = self._block(body_node, scope) if body_node is not None else None
        return Method(
            origin=origin,
            name=name,
            params=params,
            return_type=return_type,
            modifiers=modifiers,
            body=body,
            is_constructor=False,
        )

    def _constructor(self, node: "Node", owner: str) -> Method:
        origin = self._origin(node)
        params = self._params(node.child_by_field_name("parameters"))
        scope = _Scope(names=dict(self._field_types), is_field_scope=True).child()
        for p in params:
            scope.names[p.name] = p.type
        scope.names["__return__"] = uir.T_VOID
        body_node = node.child_by_field_name("body")
        body = self._block(body_node, scope) if body_node is not None else None
        return Method(
            origin=origin,
            name="<init>",
            params=params,
            return_type=uir.T_VOID,
            modifiers=self._modifiers(node),
            body=body,
            is_constructor=True,
        )

    def _params(self, node: "Node") -> tuple[Param, ...]:
        out: list[Param] = []
        for child in self._named(node):
            if child.type == "spread_parameter":
                self._reject(child, "varargs parameter")
            if child.type != "formal_parameter":
                self._reject(child, "parameter")
            out.append(
                Param(
                    origin=self._origin(child),
                    name=self._text(child.child_by_field_name("name")),
                    type=self._type(child.child_by_field_name("type")),
                )
            )
        return tuple(out)

    # -- types ------------------------------------------------------------

    def _type(self, node: "Node | None") -> uir.Type:
        if node is None:
            return UnknownType("missing-type-node")
        t = node.type
        if t in ("integral_type", "floating_point_type"):
            return PrimitiveType(self._text(node))
        if t == "boolean_type":
            return uir.T_BOOLEAN
        if t == "void_type":
            return uir.T_VOID
        if t == "array_type":
            return ArrayType(element=self._type(node.child_by_field_name("element")))
        if t == "type_identifier":
            name = self._text(node)
            return ClassType(name)
        if t == "generic_type":
            named = self._named(node)
            base = named[0]
            args: list[uir.Type] = []
            for child in named[1:]:
                if child.type != "type_arguments":
                    continue
                for a in self._named(child):
                    if a.type == "wildcard":
                        # `List<? extends X>` erases to something this front end
                        # cannot reason about, so it is recorded as unknown
                        # rather than silently treated as X.
                        args.append(UnknownType("wildcard-type-argument"))
                    else:
                        args.append(self._type(a))
            base_type = self._type(base)
            base_name = (
                base_type.name if isinstance(base_type, ClassType) else self._text(base)
            )
            return ClassType(base_name, tuple(args))
        if t == "scoped_type_identifier":
            return ClassType(self._text(node).split(".")[-1])
        return self._reject(node, "type")

    # -- statements -------------------------------------------------------

    def _block(self, node: "Node", scope: _Scope) -> Block:
        inner = scope.child()
        body: list[Stmt] = []
        for child in self._named(node):
            if child.type in ("line_comment", "block_comment"):
                continue
            body.append(self._stmt(child, inner))
        return Block(origin=self._origin(node), body=tuple(body))

    def _stmt(self, node: "Node", scope: _Scope) -> Stmt:
        origin = self._origin(node)
        t = node.type

        if t == "block":
            return self._block(node, scope)

        if t == "local_variable_declaration":
            declared = self._type(node.child_by_field_name("type"))
            stmts: list[Stmt] = []
            for declarator in node.children_by_field_name("declarator"):
                name = self._text(declarator.child_by_field_name("name"))
                extra_dims = len(
                    [c for c in declarator.children if c.type == "dimensions"]
                )
                var_type: uir.Type = declared
                for _ in range(extra_dims):
                    var_type = ArrayType(var_type)
                value_node = declarator.child_by_field_name("value")
                init = None
                if value_node is not None:
                    init = self._expr(value_node, scope, expected=var_type)
                    init = self._coerce(init, var_type)
                scope.names[name] = var_type
                stmts.append(
                    LocalVar(origin=origin, name=name, type=var_type, init=init)
                )
            if len(stmts) == 1:
                return stmts[0]
            return Block(origin=origin, body=tuple(stmts))

        if t == "expression_statement":
            return ExprStmt(origin=origin, expr=self._expr(node.named_children[0], scope))

        if t == "if_statement":
            cond = self._expr(node.child_by_field_name("condition"), scope)
            then = self._stmt(node.child_by_field_name("consequence"), scope)
            other_node = node.child_by_field_name("alternative")
            other = self._stmt(other_node, scope) if other_node is not None else None
            return If(origin=origin, cond=cond, then=then, other=other)

        if t == "while_statement":
            return While(
                origin=origin,
                cond=self._expr(node.child_by_field_name("condition"), scope),
                body=self._stmt(node.child_by_field_name("body"), scope),
            )

        if t == "do_statement":
            return DoWhile(
                origin=origin,
                body=self._stmt(node.child_by_field_name("body"), scope),
                cond=self._expr(node.child_by_field_name("condition"), scope),
            )

        if t == "for_statement":
            inner = scope.child()
            init: list[Stmt] = []
            for child in node.children_by_field_name("init"):
                init.append(self._stmt_or_expr(child, inner))
            cond_node = node.child_by_field_name("condition")
            cond = self._expr(cond_node, inner) if cond_node is not None else None
            update = tuple(
                self._expr(u, inner) for u in node.children_by_field_name("update")
            )
            body = self._stmt(node.child_by_field_name("body"), inner)
            return For(
                origin=origin,
                init=tuple(init),
                cond=cond,
                update=update,
                body=body,
            )

        if t == "enhanced_for_statement":
            var_type = self._type(node.child_by_field_name("type"))
            var_name = self._text(node.child_by_field_name("name"))
            iterable = self._expr(node.child_by_field_name("value"), scope)
            inner = scope.child()
            inner.names[var_name] = var_type
            return ForEach(
                origin=origin,
                var_name=var_name,
                var_type=var_type,
                iterable=iterable,
                body=self._stmt(node.child_by_field_name("body"), inner),
            )

        if t == "return_statement":
            named = self._named(node)
            if not named:
                return Return(origin=origin, value=None)
            value = self._expr(named[0], scope)
            declared = scope.lookup("__return__")
            if declared is not None:
                value = self._coerce(value, declared)
            return Return(origin=origin, value=value)

        if t == "break_statement":
            if self._named(node):
                self._reject(node, "labelled break")
            return Break(origin=origin)

        if t == "continue_statement":
            if self._named(node):
                self._reject(node, "labelled continue")
            return Continue(origin=origin)

        if t == "throw_statement":
            return Throw(origin=origin, value=self._expr(node.named_children[0], scope))

        if t == "try_statement":
            if node.child_by_field_name("resources") is not None:
                self._reject(node, "try-with-resources")
            body = self._block(node.child_by_field_name("body"), scope)
            catches: list[CatchClause] = []
            finally_: Stmt | None = None
            for child in self._named(node):
                if child.type == "catch_clause":
                    catches.append(self._catch(child, scope))
                elif child.type == "finally_clause":
                    finally_ = self._block(self._named(child)[0], scope)
            return Try(
                origin=origin, body=body, catches=tuple(catches), finally_=finally_
            )

        if t == "switch_expression":
            return self._switch(node, scope)

        if t in ("line_comment", "block_comment", ";"):
            return Block(origin=origin, body=())

        return self._reject(node, "statement")

    def _stmt_or_expr(self, node: "Node", scope: _Scope) -> Stmt:
        if node.type in ("local_variable_declaration", "expression_statement"):
            return self._stmt(node, scope)
        return ExprStmt(origin=self._origin(node), expr=self._expr(node, scope))

    def _catch(self, node: "Node", scope: _Scope) -> CatchClause:
        param = node.child_by_field_name("parameter")
        if param is None:
            param = [c for c in self._named(node) if c.type == "catch_formal_parameter"][0]
        name = self._text(param.child_by_field_name("name"))
        type_node = [c for c in self._named(param) if c.type == "catch_type"]
        types: list[uir.Type] = []
        if type_node:
            for entry in self._named(type_node[0]):
                types.append(self._type(entry))
        inner = scope.child()
        for ty in types:
            inner.names[name] = ty
        body = self._block(node.child_by_field_name("body"), inner)
        return CatchClause(
            origin=self._origin(node), types=tuple(types), name=name, body=body
        )

    def _switch(self, node: "Node", scope: _Scope) -> Switch:
        subject = self._expr(node.child_by_field_name("condition"), scope)
        body = node.child_by_field_name("body")
        cases: list[SwitchCase] = []
        for group in self._named(body):
            if group.type == "switch_rule":
                self._reject(group, "arrow switch rule")
            if group.type != "switch_block_statement_group":
                continue
            labels: list[Expr] = []
            stmts: list[Stmt] = []
            inner = scope.child()
            for child in self._named(group):
                if child.type == "switch_label":
                    named = self._named(child)
                    if named:  # `case X:`  (empty means `default:`)
                        labels.append(self._expr(named[0], inner))
                else:
                    stmts.append(self._stmt(child, inner))
            cases.append(
                SwitchCase(
                    origin=self._origin(group),
                    labels=tuple(labels),
                    body=tuple(stmts),
                )
            )
        return Switch(origin=self._origin(node), subject=subject, cases=tuple(cases))

    # -- expressions ------------------------------------------------------

    def _expr(
        self, node: "Node", scope: _Scope, expected: uir.Type | None = None
    ) -> Expr:
        origin = self._origin(node)
        t = node.type

        if t == "parenthesized_expression":
            return self._expr(self._named(node)[0], scope, expected)

        if t == "decimal_integer_literal":
            text = self._text(node).replace("_", "")
            if text.lower().endswith("l"):
                return IntLiteral(origin=origin, type=uir.T_LONG, value=int(text[:-1], 10))
            return IntLiteral(origin=origin, type=uir.T_INT, value=int(text, 10))

        if t in ("hex_integer_literal", "octal_integer_literal", "binary_integer_literal"):
            text = self._text(node).replace("_", "")
            is_long = text.lower().endswith("l")
            if is_long:
                text = text[:-1]
            value = int(text, 0)
            kind = uir.T_LONG if is_long else uir.T_INT
            width = 64 if is_long else 32
            if value >= 2 ** (width - 1):
                value -= 2 ** width
            return IntLiteral(origin=origin, type=kind, value=value)

        if t == "decimal_floating_point_literal":
            text = self._text(node).replace("_", "")
            if text.lower().endswith("f"):
                self._reject(node, "float literal (only double is supported)")
            if text.lower().endswith("d"):
                text = text[:-1]
            return FloatLiteral(origin=origin, type=uir.T_DOUBLE, text=text)

        if t in ("true", "false"):
            return BoolLiteral(origin=origin, type=uir.T_BOOLEAN, value=t == "true")

        if t == "character_literal":
            return CharLiteral(
                origin=origin, type=uir.T_CHAR, value=self._char_value(node)
            )

        if t == "string_literal":
            return StringLiteral(
                origin=origin, type=uir.T_STRING, value=self._string_value(node)
            )

        if t == "null_literal":
            return NullLiteral(origin=origin, type=ClassType("Object"))

        if t == "this":
            return This(origin=origin, type=UnknownType("this-type"))

        if t == "identifier":
            name = self._text(node)
            resolved = scope.resolve(name)
            if resolved is not None:
                declared, is_field = resolved
                if not is_field:
                    return Name(origin=origin, type=declared, ident=name)
                # An unqualified reference to a field of the enclosing class is
                # resolved here, not left for the emitter to guess at.
                if name in self._static_field_names:
                    return StaticFieldAccess(
                        origin=origin,
                        type=declared,
                        owner=self._current_class or "",
                        name=name,
                    )
                return FieldAccess(
                    origin=origin,
                    type=declared,
                    target=This(origin=origin, type=UnknownType("this-type")),
                    name=name,
                )
            if name in KNOWN_CLASS_TYPES | self._class_names:
                # A bare class name used as a call/field target.
                return Name(origin=origin, type=ClassType(name), ident=name)
            return Name(origin=origin, type=UnknownType(f"name:{name}"), ident=name)

        if t == "field_access":
            obj = node.child_by_field_name("object")
            field_name = self._text(node.child_by_field_name("field"))
            if field_name == "length":
                target = self._expr(obj, scope)
                if isinstance(target.type, ArrayType):
                    return ArrayLength(origin=origin, type=uir.T_INT, array=target)
            if obj.type == "identifier":
                owner = self._text(obj)
                if owner in KNOWN_CLASS_TYPES and scope.lookup(owner) is None:
                    return StaticFieldAccess(
                        origin=origin,
                        type=self._static_field_type(owner, field_name),
                        owner=owner,
                        name=field_name,
                    )
            target = self._expr(obj, scope)
            declared = self._field_types.get(field_name) if isinstance(target, This) else None
            return FieldAccess(
                origin=origin,
                type=declared if declared is not None else UnknownType(f"field:{field_name}"),
                target=target,
                name=field_name,
            )

        if t == "array_access":
            array = self._expr(node.child_by_field_name("array"), scope)
            index = self._expr(node.child_by_field_name("index"), scope)
            element = (
                array.type.element
                if isinstance(array.type, ArrayType)
                else UnknownType("array-element")
            )
            return ArrayAccess(origin=origin, type=element, array=array, index=index)

        if t == "binary_expression":
            return self._binary(node, scope)

        if t == "unary_expression":
            op = self._text(node.child_by_field_name("operator"))
            operand = self._expr(node.child_by_field_name("operand"), scope)
            if op == "!":
                return Unary(origin=origin, type=uir.T_BOOLEAN, op="!", operand=operand)
            result = self._unary_promote(operand.type)
            return Unary(origin=origin, type=result, op=op, operand=operand)

        if t == "update_expression":
            return self._update(node, scope)

        if t == "assignment_expression":
            left = self._expr(node.child_by_field_name("left"), scope)
            op = self._text(node.child_by_field_name("operator"))
            right = self._expr(node.child_by_field_name("right"), scope, expected=left.type)
            if op == "=":
                right = self._coerce(right, left.type)
            return Assign(origin=origin, type=left.type, op=op, target=left, value=right)

        if t == "ternary_expression":
            cond = self._expr(node.child_by_field_name("condition"), scope)
            then = self._expr(node.child_by_field_name("consequence"), scope, expected)
            other = self._expr(node.child_by_field_name("alternative"), scope, expected)
            result = self._binary_promote(then.type, other.type)
            if isinstance(result, UnknownType):
                result = then.type
            return Ternary(
                origin=origin, type=result, cond=cond, then=then, other=other
            )

        if t == "cast_expression":
            target = self._type(node.child_by_field_name("type"))
            operand = self._expr(node.child_by_field_name("value"), scope)
            return Cast(origin=origin, type=target, target=target, operand=operand)

        if t == "instanceof_expression":
            operand = self._expr(node.child_by_field_name("left"), scope)
            target = self._type(node.child_by_field_name("right"))
            return InstanceOf(
                origin=origin, type=uir.T_BOOLEAN, operand=operand, target=target
            )

        if t == "lambda_expression":
            return self._lambda(node, scope, expected)

        if t == "method_reference":
            return self._method_ref(node, scope)

        if t == "method_invocation":
            return self._call(node, scope)

        if t == "object_creation_expression":
            created = self._type(node.child_by_field_name("type"))
            args = self._args(node.child_by_field_name("arguments"), scope)
            return New(origin=origin, type=created, args=args)

        if t == "array_creation_expression":
            element = self._type(node.child_by_field_name("type"))
            dims = tuple(
                self._expr(self._named(d)[0], scope)
                for d in node.children
                if d.type == "dimensions_expr"
            )
            value_node = node.child_by_field_name("value")
            init = None
            if value_node is not None:
                init = tuple(
                    self._coerce(self._expr(v, scope), element)
                    for v in self._named(value_node)
                )
            array_type = ArrayType(element)
            return NewArray(
                origin=origin, type=array_type, element=element, dims=dims, init=init
            )

        if t == "array_initializer":
            element = (
                expected.element
                if isinstance(expected, ArrayType)
                else UnknownType("array-initializer-element")
            )
            init = tuple(
                self._coerce(self._expr(v, scope, expected=element), element)
                for v in self._named(node)
            )
            return NewArray(
                origin=origin,
                type=ArrayType(element),
                element=element,
                dims=(),
                init=init,
            )

        return self._reject(node, "expression")

    # -- lambdas and method references ------------------------------------

    def _lambda(
        self, node: "Node", scope: _Scope, expected: uir.Type | None
    ) -> Expr:
        """Lower a lambda.

        The declared type comes from context.  When context does not supply a
        functional interface the type is recorded as UnknownType rather than
        guessed: the emitter can still emit the lambda, but a *call* through an
        unknown type is refused rather than assumed to be the SAM.
        """

        origin = self._origin(node)
        params = self._lambda_params(node.child_by_field_name("parameters"))
        params = self._infer_lambda_param_types(params, expected)

        inner = scope.child()
        for p in params:
            inner.names[p.name] = p.type
        # A `return` inside a lambda returns from the *lambda*, not from the
        # enclosing method.  Leaving the method's __return__ in scope would
        # coerce the lambda's result to the wrong type - and to `void` whenever
        # the lambda appears inside a void method.
        sam = self._sam_name(expected) if expected is not None else None
        inner.names["__return__"] = (
            self._instance_call_type(expected, sam)
            if sam is not None
            else UnknownType("lambda-result-type")
        )

        body_node = node.child_by_field_name("body")
        if body_node is None:
            self._reject(node, "lambda without a body")

        declared: uir.Type = (
            expected
            if expected is not None and self._sam_name(expected) is not None
            else UnknownType("lambda-target-type")
        )

        if body_node.type == "block":
            return Lambda(
                origin=origin,
                type=declared,
                params=params,
                body_expr=None,
                body_block=self._block(body_node, inner),
            )
        # An expression-bodied lambda returns its expression, so it takes the
        # same conversion a `return` would.  Applying it only to block bodies
        # would make `x -> x / 2` and `x -> { return x / 2; }` behave
        # differently on the same interface.
        body_expr = self._expr(body_node, inner)
        result_type = inner.names["__return__"]
        return Lambda(
            origin=origin,
            type=declared,
            params=params,
            body_expr=self._coerce(body_expr, result_type),
            body_block=None,
        )

    def _sam_name(self, t: uir.Type) -> str | None:
        """The SAM of ``t``, whether it is a JDK interface or one declared here."""

        builtin = uir.sam_of(t)
        if builtin is not None:
            return builtin
        if isinstance(t, ClassType) and t.name in self._interface_sams:
            return self._interface_sams[t.name][0]
        return None

    def _infer_lambda_param_types(
        self, params: tuple[Param, ...], expected: uir.Type | None
    ) -> tuple[Param, ...]:
        """Give inferred lambda parameters the types the target interface implies.

        Without this, ``x -> x + 1`` on a ``Function<Integer,Integer>`` has an
        untyped ``x``, and the emitter cannot tell a 32-bit int addition from a
        64-bit one or from string concatenation, so it refuses.
        """

        if expected is None or not isinstance(expected, ClassType):
            return params

        if expected.name in self._interface_sams:
            return self._apply_param_types(
                params, list(self._interface_sams[expected.name][2])
            )

        if uir.sam_of(expected) is None or not expected.args:
            return params

        name = expected.name
        if name in ("Function", "BiFunction"):
            argument_types = list(expected.args[:-1])
        elif name in ("Predicate", "Consumer", "Supplier", "UnaryOperator",
                      "BinaryOperator", "ToIntFunction", "IntFunction"):
            argument_types = list(expected.args)
        elif name in ("BiPredicate", "BiConsumer", "Comparator"):
            argument_types = list(expected.args) * 2 if len(expected.args) == 1 else list(expected.args)
        else:
            return params

        return self._apply_param_types(params, argument_types)

    @staticmethod
    def _apply_param_types(
        params: tuple[Param, ...], argument_types: list[uir.Type]
    ) -> tuple[Param, ...]:
        out = []
        for index, p in enumerate(params):
            if isinstance(p.type, UnknownType) and index < len(argument_types):
                out.append(Param(origin=p.origin, name=p.name, type=argument_types[index]))
            else:
                out.append(p)
        return tuple(out)

    def _lambda_params(self, node: "Node | None") -> tuple[Param, ...]:
        """Java spells lambda parameters three different ways."""

        if node is None:
            return ()
        if node.type == "identifier":
            # `x -> ...`
            return (
                Param(
                    origin=self._origin(node),
                    name=self._text(node),
                    type=UnknownType("inferred-lambda-parameter"),
                ),
            )
        if node.type == "inferred_parameters":
            # `(x, y) -> ...`
            return tuple(
                Param(
                    origin=self._origin(child),
                    name=self._text(child),
                    type=UnknownType("inferred-lambda-parameter"),
                )
                for child in self._named(node)
                if child.type == "identifier"
            )
        if node.type == "formal_parameters":
            # `(int x, int y) -> ...`
            return self._params(node)
        return self._reject(node, "lambda parameter list")

    def _method_ref(self, node: "Node", scope: _Scope) -> Expr:
        """Lower ``Target::name``.

        A *bound* reference (``expr::m``) evaluates its receiver once, at the
        point the reference is created.  Lowering it to the same node as an
        unbound reference would lose that, and the receiver would be
        re-evaluated on every call.
        """

        origin = self._origin(node)
        children = self._named(node)
        if not children:
            self._reject(node, "method reference without a target")

        target_node = children[0]
        name_node = children[-1]
        name = self._text(name_node)

        if name_node.type == "new" or name == "new":
            if target_node.type not in ("type_identifier", "identifier"):
                self._reject(node, "constructor reference on a computed type")
            owner = self._text(target_node)
            if owner not in self._class_names:
                self._reject(
                    node,
                    f"constructor reference to {owner}, which is not declared here",
                )
            return MethodRef(
                origin=origin,
                type=UnknownType("method-ref"),
                ref_kind="constructor",
                name="<init>",
                owner=owner,
            )

        if target_node.type == "this":
            return MethodRef(
                origin=origin,
                type=UnknownType("method-ref"),
                ref_kind="bound",
                name=name,
                target=This(origin=self._origin(target_node), type=UnknownType("this-type")),
            )

        text = self._text(target_node)
        if target_node.type in ("type_identifier", "identifier") and scope.resolve(text) is None:
            if text not in self._class_names:
                self._reject(
                    node,
                    f"method reference {text}::{name} on a type with no "
                    f"declaration in this compilation unit",
                )
            return MethodRef(
                origin=origin,
                type=UnknownType("method-ref"),
                ref_kind="static" if name in self._static_method_names else "unbound",
                name=name,
                owner=text,
            )

        return MethodRef(
            origin=origin,
            type=UnknownType("method-ref"),
            ref_kind="bound",
            name=name,
            target=self._expr(target_node, scope),
        )

    # -- expression helpers ----------------------------------------------

    def _args(
        self,
        node: "Node | None",
        scope: _Scope,
        expected: tuple[uir.Type, ...] | None = None,
    ) -> tuple[Expr, ...]:
        if node is None:
            return ()
        nodes = self._named(node)
        out: list[Expr] = []
        for index, a in enumerate(nodes):
            want = (
                expected[index]
                if expected is not None and index < len(expected)
                else None
            )
            out.append(self._expr(a, scope, expected=want))
        return tuple(out)

    def _binary(self, node: "Node", scope: _Scope) -> Expr:
        origin = self._origin(node)
        op = self._text(node.child_by_field_name("operator"))
        left = self._expr(node.child_by_field_name("left"), scope)
        right = self._expr(node.child_by_field_name("right"), scope)

        if op == "+" and (self._is_string(left.type) or self._is_string(right.type)):
            parts: list[Expr] = []
            for side in (left, right):
                if isinstance(side, StringConcat):
                    parts.extend(side.parts)
                else:
                    parts.append(side)
            return StringConcat(origin=origin, type=uir.T_STRING, parts=tuple(parts))

        if op in ("&&", "||"):
            return Binary(
                origin=origin, type=uir.T_BOOLEAN, op=op, left=left, right=right
            )
        if op in ("<", "<=", ">", ">=", "==", "!="):
            return Binary(
                origin=origin, type=uir.T_BOOLEAN, op=op, left=left, right=right
            )
        if op in ("<<", ">>", ">>>"):
            # Shifts use *unary* promotion on the left operand only: the right
            # operand's type does not widen the result.
            return Binary(
                origin=origin,
                type=self._unary_promote(left.type),
                op=op,
                left=left,
                right=right,
            )
        if op in ("&", "|", "^") and self._is_boolean(left.type) and self._is_boolean(right.type):
            return Binary(
                origin=origin, type=uir.T_BOOLEAN, op=op, left=left, right=right
            )

        return Binary(
            origin=origin,
            type=self._binary_promote(left.type, right.type),
            op=op,
            left=left,
            right=right,
        )

    def _update(self, node: "Node", scope: _Scope) -> Expr:
        origin = self._origin(node)
        children = [c for c in node.children]
        text = self._text(node)
        op = "++" if "++" in text else "--"
        operand_node = self._named(node)[0]
        target = self._expr(operand_node, scope)
        prefix = children[0].type in ("++", "--")
        return IncDec(
            origin=origin, type=target.type, op=op, prefix=prefix, target=target
        )

    def _call(self, node: "Node", scope: _Scope) -> Expr:
        origin = self._origin(node)
        name = self._text(node.child_by_field_name("name"))
        args = self._args(
            node.child_by_field_name("arguments"),
            scope,
            self._method_param_types.get(name),
        )
        obj = node.child_by_field_name("object")

        if obj is None:
            declared = self._method_types.get(name, UnknownType(f"call:{name}"))
            return Call(origin=origin, type=declared, target=None, name=name, args=args)

        # System.out.println(...) arrives as a field_access target.
        obj_text = self._text(obj)
        if obj_text in ("System.out", "System.err"):
            return StaticCall(
                origin=origin, type=uir.T_VOID, owner=obj_text, name=name, args=args
            )

        if obj.type == "identifier" and scope.lookup(obj_text) is None:
            if obj_text in KNOWN_CLASS_TYPES or obj_text in self._class_names:
                return StaticCall(
                    origin=origin,
                    type=self._static_call_type(obj_text, name, args),
                    owner=obj_text,
                    name=name,
                    args=args,
                )

        target = self._expr(obj, scope)
        return Call(
            origin=origin,
            type=self._instance_call_type(target.type, name),
            target=target,
            name=name,
            args=args,
        )

    # -- type rules -------------------------------------------------------

    @staticmethod
    def _is_string(t: uir.Type) -> bool:
        return isinstance(t, ClassType) and t.name == "String"

    @staticmethod
    def _is_boolean(t: uir.Type) -> bool:
        return isinstance(t, PrimitiveType) and t.name == "boolean"

    @staticmethod
    def _unary_promote(t: uir.Type) -> uir.Type:
        return uir.unary_promote(t)

    @staticmethod
    def _binary_promote(a: uir.Type, b: uir.Type) -> uir.Type:
        return uir.binary_promote(a, b)

    def _coerce(self, expr: Expr, target: uir.Type) -> Expr:
        """Insert the implicit widening/narrowing Java performs at assignment.

        ``long x = 1;`` stores a long, and ``double d = 1;`` stores 1.0.  Losing
        this makes ``d / 2`` produce 0 instead of 0.5.
        """

        if not isinstance(target, PrimitiveType) or not isinstance(
            expr.type, PrimitiveType
        ):
            return expr
        if target.name == expr.type.name:
            return expr
        if target.name == "boolean" or expr.type.name == "boolean":
            return expr
        return Cast(origin=expr.origin, type=target, target=target, operand=expr)

    def _static_field_type(self, owner: str, name: str) -> uir.Type:
        table = {
            ("Integer", "MAX_VALUE"): uir.T_INT,
            ("Integer", "MIN_VALUE"): uir.T_INT,
            ("Long", "MAX_VALUE"): uir.T_LONG,
            ("Long", "MIN_VALUE"): uir.T_LONG,
            ("Math", "PI"): uir.T_DOUBLE,
            ("Math", "E"): uir.T_DOUBLE,
        }
        return table.get((owner, name), UnknownType(f"static-field:{owner}.{name}"))

    def _static_call_type(self, owner: str, name: str, args: tuple[Expr, ...]) -> uir.Type:
        if owner == "Math":
            if name in ("abs", "max", "min"):
                if args:
                    return self._binary_promote(
                        args[0].type, args[-1].type if len(args) > 1 else args[0].type
                    )
                return UnknownType("math-no-args")
            if name in ("floor", "ceil", "sqrt", "pow"):
                return uir.T_DOUBLE
        if owner == "Integer":
            if name in ("parseInt", "compare"):
                return uir.T_INT
            if name == "toString":
                return uir.T_STRING
            if name == "valueOf":
                return uir.T_INT
        if owner == "Long":
            if name == "parseLong":
                return uir.T_LONG
            if name == "toString":
                return uir.T_STRING
        if owner == "Double":
            if name == "parseDouble":
                return uir.T_DOUBLE
            if name == "toString":
                return uir.T_STRING
        if owner == "String" and name == "valueOf":
            return uir.T_STRING
        if owner in self._class_names:
            return self._method_types.get(name, UnknownType(f"call:{owner}.{name}"))
        return UnknownType(f"static-call:{owner}.{name}")

    def _instance_call_type(self, target: uir.Type, name: str) -> uir.Type:
        if isinstance(target, ClassType) and target.name in self._interface_sams:
            sam_name, result, _params = self._interface_sams[target.name]
            if sam_name == name:
                return result
        sam = uir.sam_of(target)
        if sam == name and isinstance(target, ClassType):
            # `Function<A,B>.apply` yields B; without the type argument the
            # result is honestly unknown rather than assumed.
            if target.name in ("Function", "BiFunction") and target.args:
                return target.args[-1]
            if target.name in ("Predicate", "BiPredicate"):
                return uir.T_BOOLEAN
            if target.name in ("Comparator", "ToIntFunction", "IntUnaryOperator",
                               "IntBinaryOperator", "IntSupplier"):
                return uir.T_INT
            if target.name in ("Runnable", "Consumer", "BiConsumer"):
                return uir.T_VOID
            if target.name in ("UnaryOperator", "BinaryOperator") and target.args:
                return target.args[0]
            if target.name == "Supplier" and target.args:
                return target.args[0]
            return UnknownType(f"sam-result:{target.name}")
        return self._instance_call_type_declared(target, name)

    def _instance_call_type_declared(self, target: uir.Type, name: str) -> uir.Type:
        if self._is_string(target):
            table = {
                "length": uir.T_INT,
                "charAt": uir.T_CHAR,
                "indexOf": uir.T_INT,
                "substring": uir.T_STRING,
                "toUpperCase": uir.T_STRING,
                "toLowerCase": uir.T_STRING,
                "trim": uir.T_STRING,
                "isEmpty": uir.T_BOOLEAN,
                "equals": uir.T_BOOLEAN,
            }
            if name in table:
                return table[name]
        if isinstance(target, ClassType) and target.name == "StringBuilder":
            if name == "toString":
                return uir.T_STRING
            if name == "length":
                return uir.T_INT
            if name in ("append", "reverse"):
                return ClassType("StringBuilder")
        return self._method_types.get(name, UnknownType(f"method:{name}"))

    # -- literal decoding -------------------------------------------------

    def _char_value(self, node: "Node") -> int:
        raw = self._text(node)[1:-1]
        decoded = self._decode_escapes(raw, node)
        if len(decoded) != 1:
            self._reject(node, "character literal with more than one code unit")
        return ord(decoded)

    def _string_value(self, node: "Node") -> str:
        raw = self._text(node)
        if raw.startswith('"""'):
            return self._text_block(raw, node)
        return self._decode_escapes(raw[1:-1], node)

    def _text_block(self, raw: str, node: "Node") -> str:
        """Strip incidental whitespace from a text block, per JLS 3.10.6.

        The common indent is computed over non-blank lines *and* the closing
        delimiter line, then removed; trailing spaces on each line go too.  Doing
        this by simple dedent gets the closing-delimiter rule wrong and silently
        shifts every line of the string.
        """

        inner = raw[3:-3]
        newline = inner.find("\n")
        if newline < 0:
            self._reject(node, "text block without a line terminator after the opener")
        lines = inner[newline + 1 :].split("\n")

        significant = [ln for ln in lines[:-1] if ln.strip()]
        candidates = significant + [lines[-1]]
        indent = min(
            (len(ln) - len(ln.lstrip(" \t")) for ln in candidates if ln.strip() or ln is lines[-1]),
            default=0,
        )
        stripped = [ln[indent:].rstrip(" \t") if ln.strip() else "" for ln in lines[:-1]]
        text = "\n".join(stripped)
        if lines[-1].strip():
            # Content on the closing line means the block does not end in a newline.
            text = text + ("\n" if stripped else "") + lines[-1][indent:]
        elif stripped:
            text += "\n"
        return self._decode_escapes(text, node)

    def _decode_escapes(self, raw: str, node: "Node") -> str:
        out: list[str] = []
        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch != "\\":
                out.append(ch)
                i += 1
                continue
            i += 1
            if i >= len(raw):
                self._reject(node, "dangling escape in literal")
            esc = raw[i]
            if esc in _ESCAPES:
                out.append(_ESCAPES[esc])
                i += 1
            elif esc == "u":
                while i < len(raw) and raw[i] == "u":
                    i += 1
                hex_digits = raw[i : i + 4]
                if len(hex_digits) != 4:
                    self._reject(node, "malformed unicode escape")
                out.append(chr(int(hex_digits, 16)))
                i += 4
            elif esc.isdigit():
                digits = ""
                while i < len(raw) and raw[i].isdigit() and len(digits) < 3:
                    digits += raw[i]
                    i += 1
                out.append(chr(int(digits, 8)))
            else:
                self._reject(node, f"unknown escape sequence \\{esc}")
        return "".join(out)


def parse_java(source: bytes, filename: str = "<memory>") -> Module:
    return JavaFrontend(source, filename).parse()


def parse_java_file(path) -> Module:
    return JavaFrontend.from_path(path).parse()
