"""Python scope and binding resolution.

This is what separates a codemod from ``sed``.  Before any Python symbol is
renamed, moved or re-signatured, every ``Name`` occurrence in the file is bound
to the declaration it actually refers to, following real Python scoping:

* LEGB resolution, with the rule that **class bodies are not visible to nested
  functions** — the single most common source of wrong renames;
* comprehensions and generator expressions get their own scope (Python 3);
* ``global`` / ``nonlocal`` re-target a binding to an enclosing scope;
* parameters, walrus targets, ``for`` targets, ``with ... as``, ``except ... as``,
  ``match`` captures, imports, ``def``/``class`` and augmented assignment all
  create or rebind names;
* attribute accesses are recorded separately, because ``x.name`` is *not*
  resolvable without types and must never be renamed as if it were.

A rename that would capture or shadow an existing binding is reported as a
conflict rather than applied.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ScopeKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    LAMBDA = "lambda"
    COMPREHENSION = "comprehension"


class BindingKind(StrEnum):
    MODULE = "module"
    IMPORT = "import"
    FUNCTION = "function"
    CLASS = "class"
    PARAMETER = "parameter"
    ASSIGNMENT = "assignment"
    FOR_TARGET = "for-target"
    WITH_TARGET = "with-target"
    EXCEPT_TARGET = "except-target"
    COMPREHENSION_TARGET = "comprehension-target"
    MATCH_CAPTURE = "match-capture"
    GLOBAL_DECLARATION = "global-declaration"
    NONLOCAL_DECLARATION = "nonlocal-declaration"


@dataclass(frozen=True, slots=True)
class Binding:
    name: str
    kind: BindingKind
    scope_id: int
    line: int
    column: int
    end_line: int
    end_column: int
    qualified_name: str = ""

    @property
    def key(self) -> tuple[int, str]:
        return (self.scope_id, self.name)


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One textual appearance of a name, with what it resolved to."""

    name: str
    line: int
    column: int
    end_line: int
    end_column: int
    context: str
    binding: Binding | None
    node_type: str = "Name"

    @property
    def resolved(self) -> bool:
        return self.binding is not None


@dataclass(slots=True)
class Scope:
    scope_id: int
    kind: ScopeKind
    parent: int | None
    name: str = ""
    bindings: dict[str, Binding] = field(default_factory=dict)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)
    children: list[int] = field(default_factory=list)

    @property
    def transparent_to_nested_functions(self) -> bool:
        """Class bodies do not participate in the enclosing-scope chain."""

        return self.kind is not ScopeKind.CLASS


class ScopeTable:
    """The resolved scope tree for one module."""

    __slots__ = ("_scopes", "_occurrences", "_attributes", "_module")

    def __init__(self, module: str) -> None:
        self._scopes: dict[int, Scope] = {}
        self._occurrences: list[Occurrence] = []
        self._attributes: list[Occurrence] = []
        self._module = module

    # -- construction ----------------------------------------------------

    def add_scope(self, kind: ScopeKind, parent: int | None, name: str = "") -> Scope:
        scope = Scope(scope_id=len(self._scopes), kind=kind, parent=parent, name=name)
        self._scopes[scope.scope_id] = scope
        if parent is not None:
            self._scopes[parent].children.append(scope.scope_id)
        return scope

    def scope(self, scope_id: int) -> Scope:
        return self._scopes[scope_id]

    @property
    def module_scope(self) -> Scope:
        return self._scopes[0]

    @property
    def scopes(self) -> tuple[Scope, ...]:
        return tuple(self._scopes[key] for key in sorted(self._scopes))

    @property
    def occurrences(self) -> tuple[Occurrence, ...]:
        return tuple(self._occurrences)

    @property
    def attribute_occurrences(self) -> tuple[Occurrence, ...]:
        return tuple(self._attributes)

    def record(self, occurrence: Occurrence) -> None:
        self._occurrences.append(occurrence)

    def record_attribute(self, occurrence: Occurrence) -> None:
        self._attributes.append(occurrence)

    # -- resolution ------------------------------------------------------

    def resolve(self, name: str, scope_id: int) -> Binding | None:
        """LEGB lookup from ``scope_id``, honouring the class-scope rule."""

        current: int | None = scope_id
        first = True
        while current is not None:
            scope = self._scopes[current]
            skip_class = scope.kind is ScopeKind.CLASS and not first
            if not skip_class:
                if name in scope.global_names:
                    return self.module_scope.bindings.get(name)
                if name in scope.nonlocal_names:
                    return self._resolve_nonlocal(name, scope)
                binding = scope.bindings.get(name)
                if binding is not None:
                    return binding
            first = False
            current = scope.parent
        return None

    def _resolve_nonlocal(self, name: str, scope: Scope) -> Binding | None:
        current = scope.parent
        while current is not None:
            candidate = self._scopes[current]
            if candidate.kind in (ScopeKind.FUNCTION, ScopeKind.LAMBDA, ScopeKind.COMPREHENSION):
                binding = candidate.bindings.get(name)
                if binding is not None:
                    return binding
            current = candidate.parent
        return None

    def bindings_named(self, name: str) -> tuple[Binding, ...]:
        return tuple(
            scope.bindings[name] for scope in self.scopes if name in scope.bindings
        )

    def occurrences_of(self, binding: Binding) -> tuple[Occurrence, ...]:
        return tuple(item for item in self._occurrences if item.binding == binding)

    def visible_names(self, scope_id: int) -> set[str]:
        """Every name reachable from ``scope_id`` — used for capture checks."""

        found: set[str] = set()
        current: int | None = scope_id
        first = True
        while current is not None:
            scope = self._scopes[current]
            if not (scope.kind is ScopeKind.CLASS and not first):
                found |= set(scope.bindings)
            first = False
            current = scope.parent
        return found

    def descendant_scopes(self, scope_id: int) -> Iterator[Scope]:
        stack = [scope_id]
        while stack:
            current = stack.pop()
            scope = self._scopes[current]
            yield scope
            stack.extend(scope.children)

    def to_payload(self) -> dict[str, Any]:
        return {
            "module": self._module,
            "scopes": [
                {
                    "id": scope.scope_id,
                    "kind": scope.kind.value,
                    "name": scope.name,
                    "parent": scope.parent,
                    "bindings": sorted(scope.bindings),
                    "globals": sorted(scope.global_names),
                    "nonlocals": sorted(scope.nonlocal_names),
                }
                for scope in self.scopes
            ],
            "occurrences": len(self._occurrences),
            "unresolved": sum(1 for item in self._occurrences if not item.resolved),
            "attributeOccurrences": len(self._attributes),
        }


class _Builder(ast.NodeVisitor):
    """Two-pass scope construction: bind first, then resolve."""

    def __init__(self, table: ScopeTable, module: str) -> None:
        self.table = table
        self.module = module
        self.stack: list[int] = []
        self.qualifier: list[str] = [module]
        self._pass = 1
        self._enter_index = 0

    # -- helpers ---------------------------------------------------------

    @property
    def current(self) -> Scope:
        return self.table.scope(self.stack[-1])

    def _bind(self, name: str, kind: BindingKind, node: ast.AST) -> None:
        if self._pass != 1:
            return
        scope = self.current
        if name in scope.global_names:
            target = self.table.module_scope
        elif name in scope.nonlocal_names:
            return
        else:
            target = scope
        if name in target.bindings and kind not in (BindingKind.FUNCTION, BindingKind.CLASS):
            return  # first binding wins for position reporting
        line: int = getattr(node, "lineno", 1)
        column: int = getattr(node, "col_offset", 0)
        end_line_raw: int | None = getattr(node, "end_lineno", None)
        end_column_raw: int | None = getattr(node, "end_col_offset", None)
        target.bindings[name] = Binding(
            name=name,
            kind=kind,
            scope_id=target.scope_id,
            line=line,
            column=column,
            end_line=line if end_line_raw is None else end_line_raw,
            end_column=column if end_column_raw is None else end_column_raw,
            qualified_name=".".join([*self.qualifier, name]),
        )

    def _bind_target(self, node: ast.AST, kind: BindingKind) -> None:
        if isinstance(node, ast.Name):
            self._bind(node.id, kind, node)
        elif isinstance(node, ast.Tuple | ast.List):
            for element in node.elts:
                self._bind_target(element, kind)
        elif isinstance(node, ast.Starred):
            self._bind_target(node.value, kind)

    def _enter(self, kind: ScopeKind, name: str = "") -> Scope:
        """Enter a scope.

        Both passes traverse the tree in exactly the same order, so scope ids
        assigned in pass 1 can be replayed by position in pass 2.  Matching by
        (kind, name) instead would mis-associate two same-named siblings — for
        example two ``if``-guarded definitions of the same function.
        """

        if self._pass == 1:
            scope = self.table.add_scope(kind, self.stack[-1] if self.stack else None, name)
        else:
            self._enter_index += 1
            scope = self.table.scope(self._enter_index)
            if scope.kind is not kind:  # pragma: no cover - guards a traversal-order bug
                raise RuntimeError(
                    f"scope replay diverged: expected {kind.value}, found {scope.kind.value}"
                )
        self.stack.append(scope.scope_id)
        return scope

    def _leave(self) -> None:
        self.stack.pop()

    # -- module ----------------------------------------------------------

    def run(self, tree: ast.Module) -> None:
        self._pass = 1
        self.table.add_scope(ScopeKind.MODULE, None, self.module)
        self.stack = [0]
        self.generic_visit(tree)
        self.stack = [0]
        self._pass = 2
        self._enter_index = 0
        self.generic_visit(tree)
        self.stack = []

    # -- declarations ----------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast API
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast API
        self._function(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._bind(node.name, BindingKind.FUNCTION, node)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *(item for item in node.args.kw_defaults if item is not None)]:
            self.visit(default)
        for argument in _all_args(node.args):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        if node.returns is not None:
            self.visit(node.returns)
        self._enter(ScopeKind.FUNCTION, node.name)
        self.qualifier.append(node.name)
        for argument in _all_args(node.args):
            self._bind(argument.arg, BindingKind.PARAMETER, argument)
        for statement in node.body:
            self.visit(statement)
        self.qualifier.pop()
        self._leave()

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802 - ast API
        for default in [*node.args.defaults, *(item for item in node.args.kw_defaults if item is not None)]:
            self.visit(default)
        self._enter(ScopeKind.LAMBDA, "<lambda>")
        for argument in _all_args(node.args):
            self._bind(argument.arg, BindingKind.PARAMETER, argument)
        self.visit(node.body)
        self._leave()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast API
        self._bind(node.name, BindingKind.CLASS, node)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._enter(ScopeKind.CLASS, node.name)
        self.qualifier.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.qualifier.pop()
        self._leave()

    # -- bindings --------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast API
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._bind(bound, BindingKind.IMPORT, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast API
        for alias in node.names:
            if alias.name == "*":
                continue
            self._bind(alias.asname or alias.name, BindingKind.IMPORT, node)

    def visit_Global(self, node: ast.Global) -> None:  # noqa: N802 - ast API
        if self._pass == 1:
            self.current.global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:  # noqa: N802 - ast API
        if self._pass == 1:
            self.current.nonlocal_names.update(node.names)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast API
        self.visit(node.value)
        for target in node.targets:
            self._bind_target(target, BindingKind.ASSIGNMENT)
            self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 - ast API
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)
        self._bind_target(node.target, BindingKind.ASSIGNMENT)
        self.visit(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802 - ast API
        self.visit(node.value)
        self._bind_target(node.target, BindingKind.ASSIGNMENT)
        self.visit(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802 - ast API
        self.visit(node.value)
        self._bind_target(node.target, BindingKind.ASSIGNMENT)
        self.visit(node.target)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802 - ast API
        self.visit(node.iter)
        self._bind_target(node.target, BindingKind.FOR_TARGET)
        self.visit(node.target)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802 - ast API
        self.visit_For(node)  # type: ignore[arg-type]

    def visit_With(self, node: ast.With) -> None:  # noqa: N802 - ast API
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars, BindingKind.WITH_TARGET)
                self.visit(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802 - ast API
        self.visit_With(node)  # type: ignore[arg-type]

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802 - ast API
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self._bind(node.name, BindingKind.EXCEPT_TARGET, node)
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:  # noqa: N802 - ast API
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self._bind(node.name, BindingKind.MATCH_CAPTURE, node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:  # noqa: N802 - ast API
        if node.name:
            self._bind(node.name, BindingKind.MATCH_CAPTURE, node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:  # noqa: N802 - ast API
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self._bind(node.rest, BindingKind.MATCH_CAPTURE, node)

    # -- comprehensions --------------------------------------------------

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802 - ast API
        self._comprehension(node, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802 - ast API
        self._comprehension(node, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802 - ast API
        self._comprehension(node, [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802 - ast API
        self._comprehension(node, [node.key, node.value])

    def _comprehension(self, node: ast.AST, elements: list[ast.expr]) -> None:
        generators: list[ast.comprehension] = list(getattr(node, "generators", []))
        if generators:
            # The first iterable is evaluated in the *enclosing* scope.
            self.visit(generators[0].iter)
        self._enter(ScopeKind.COMPREHENSION, "<comprehension>")
        for index, generator in enumerate(generators):
            self._bind_target(generator.target, BindingKind.COMPREHENSION_TARGET)
            self.visit(generator.target)
            if index > 0:
                self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        for element in elements:
            self.visit(element)
        self._leave()

    # -- uses ------------------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802 - ast API
        if self._pass != 2:
            return
        context = type(node.ctx).__name__.lower()
        self.table.record(
            Occurrence(
                name=node.id,
                line=node.lineno,
                column=node.col_offset,
                end_line=node.end_lineno or node.lineno,
                end_column=node.end_col_offset or node.col_offset + len(node.id),
                context=context,
                binding=self.table.resolve(node.id, self.stack[-1]),
            )
        )

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast API
        self.visit(node.value)
        if self._pass != 2:
            return
        end_line = node.end_lineno or node.lineno
        end_column = node.end_col_offset or 0
        self.table.record_attribute(
            Occurrence(
                name=node.attr,
                line=end_line,
                column=max(0, end_column - len(node.attr)),
                end_line=end_line,
                end_column=end_column,
                context=type(node.ctx).__name__.lower(),
                binding=None,
                node_type="Attribute",
            )
        )


def _all_args(args: ast.arguments) -> list[ast.arg]:
    collected = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        collected.append(args.vararg)
    if args.kwarg is not None:
        collected.append(args.kwarg)
    return collected


def analyze(source: str, *, module: str = "<module>", filename: str = "<unknown>") -> ScopeTable:
    """Build the scope table for ``source``; raises ``SyntaxError`` on bad input."""

    tree = ast.parse(source, filename=filename)
    table = ScopeTable(module)
    _Builder(table, module).run(tree)
    return table


__all__ = [
    "Binding",
    "BindingKind",
    "Occurrence",
    "Scope",
    "ScopeKind",
    "ScopeTable",
    "analyze",
]
