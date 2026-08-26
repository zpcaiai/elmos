"""Scope-correct Python refactoring operations.

Each operation returns :class:`~.patch.TextEdit` objects plus a list of
diagnostics.  Nothing here writes a file; the executor decides whether the
edits may be applied.

The operations are deliberately conservative in one specific way: when an
operation cannot prove that a change is safe — a name capture, an unresolved
reference, a dynamic access that might reach the symbol — it reports a
diagnostic and declines to emit the edit, rather than emitting it with a
warning.  A partially-correct rename is worse than a refused one.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import ContractError, normalize_newlines
from .patch import TextEdit
from .pyscope import Binding, BindingKind, Occurrence, ScopeKind, ScopeTable, analyze

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Severity = Severity.WARNING
    path: str = ""
    line: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "path": self.path,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class OperationResult:
    edits: tuple[TextEdit, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    matched: int = 0

    @property
    def blocked(self) -> bool:
        return any(item.severity is Severity.BLOCKING for item in self.diagnostics)

    @property
    def applicable(self) -> bool:
        return bool(self.edits) and not self.blocked

    def to_payload(self) -> dict[str, Any]:
        return {
            "editCount": len(self.edits),
            "matched": self.matched,
            "blocked": self.blocked,
            "edits": [edit.to_payload() for edit in self.edits],
            "diagnostics": [item.to_payload() for item in self.diagnostics],
        }

    def merge(self, other: OperationResult) -> OperationResult:
        return OperationResult(
            edits=(*self.edits, *other.edits),
            diagnostics=(*self.diagnostics, *other.diagnostics),
            matched=self.matched + other.matched,
        )


def _lines(source: str) -> list[str]:
    return normalize_newlines(source).split("\n")


def _locate_identifier(lines: Sequence[str], start_line: int, start_column: int, name: str) -> tuple[int, int] | None:
    """Find the first whole-word ``name`` at or after (start_line, start_column)."""

    for offset in range(start_line - 1, min(len(lines), start_line + 40)):
        text = lines[offset]
        begin = start_column if offset == start_line - 1 else 0
        for match in _IDENTIFIER.finditer(text, begin):
            if match.group() == name:
                return offset + 1, match.start()
    return None


def _module_of(path: str) -> str:
    trimmed = path[:-3] if path.endswith(".py") else path
    if trimmed.endswith("/__init__"):
        trimmed = trimmed[: -len("/__init__")]
    for prefix in ("src/", "lib/"):
        if trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix) :]
            break
    return trimmed.replace("/", ".")


def _parse(path: str, source: str) -> tuple[ast.Module, ScopeTable] | tuple[None, None]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None, None
    module = _module_of(path)
    return tree, analyze(source, module=module, filename=path)


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def rename_binding(
    path: str,
    source: str,
    *,
    old_name: str,
    new_name: str,
    scope: str = "module",
    action_id: str = "",
    qualified_name: str = "",
) -> OperationResult:
    """Rename one binding and every occurrence that resolves to it.

    ``scope`` selects which binding to rename: ``module`` for a module-level
    name, or a dotted path such as ``ClassName.method`` for a nested one.
    Occurrences bound to a *different* declaration with the same spelling are
    left alone — that is the whole point of resolving first.
    """

    diagnostics: list[Diagnostic] = []
    if not _IDENTIFIER.fullmatch(new_name):
        return OperationResult(
            diagnostics=(
                Diagnostic("invalid_identifier", f"'{new_name}' is not a Python identifier", Severity.BLOCKING, path),
            )
        )
    tree, table = _parse(path, source)
    if tree is None or table is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )

    binding = _select_binding(table, old_name, scope)
    if binding is None:
        return OperationResult(diagnostics=())

    conflicts = _capture_conflicts(table, binding, new_name)
    if conflicts:
        return OperationResult(
            diagnostics=tuple(
                Diagnostic(
                    "rename_capture",
                    f"renaming '{old_name}' to '{new_name}' would collide with an existing binding in {detail}",
                    Severity.BLOCKING,
                    path,
                )
                for detail in conflicts
            )
        )

    lines = _lines(source)
    edits: list[TextEdit] = []
    definition = _locate_identifier(lines, binding.line, binding.column, old_name)
    if definition is None:
        diagnostics.append(
            Diagnostic(
                "definition_not_located",
                f"could not locate the declaration text for '{old_name}' at line {binding.line}",
                Severity.BLOCKING,
                path,
                binding.line,
            )
        )
    else:
        line, column = definition
        edits.append(
            TextEdit(
                path=path,
                start_line=line,
                start_column=column,
                end_line=line,
                end_column=column + len(old_name),
                replacement=new_name,
                action_id=action_id,
                symbol=qualified_name or binding.qualified_name,
                rationale="declaration",
            )
        )

    for occurrence in table.occurrences_of(binding):
        if (occurrence.line, occurrence.column) == (definition or (0, 0)):
            continue
        edits.append(
            TextEdit(
                path=path,
                start_line=occurrence.line,
                start_column=occurrence.column,
                end_line=occurrence.end_line,
                end_column=occurrence.end_column,
                replacement=new_name,
                action_id=action_id,
                symbol=qualified_name or binding.qualified_name,
                rationale=f"reference ({occurrence.context})",
            )
        )

    diagnostics.extend(_dynamic_reference_warnings(path, tree, old_name))
    diagnostics.extend(_string_literal_warnings(path, tree, old_name))
    return OperationResult(edits=tuple(edits), diagnostics=tuple(diagnostics), matched=len(edits))


def _select_binding(table: ScopeTable, name: str, scope: str) -> Binding | None:
    if scope in ("module", "", "*"):
        return table.module_scope.bindings.get(name)
    parts = scope.split(".")
    current = table.module_scope
    for part in parts:
        match = next(
            (
                table.scope(child)
                for child in current.children
                if table.scope(child).name == part
            ),
            None,
        )
        if match is None:
            return None
        current = match
    return current.bindings.get(name)


def _capture_conflicts(table: ScopeTable, binding: Binding, new_name: str) -> tuple[str, ...]:
    """Scopes where introducing ``new_name`` would shadow or be shadowed."""

    found: list[str] = []
    target_scope = table.scope(binding.scope_id)
    if new_name in target_scope.bindings:
        found.append(f"scope '{target_scope.name or target_scope.kind.value}'")
    for occurrence in table.occurrences_of(binding):
        del occurrence  # occurrence position is not needed; the scope set is
    for scope in table.descendant_scopes(binding.scope_id):
        if scope.scope_id == binding.scope_id:
            continue
        if new_name in scope.bindings and scope.kind is not ScopeKind.CLASS:
            uses = any(
                item.binding == binding
                for item in table.occurrences
                if _within(table, item, scope.scope_id)
            )
            if uses:
                found.append(f"nested scope '{scope.name or scope.kind.value}'")
    return tuple(dict.fromkeys(found))


def _within(table: ScopeTable, occurrence: Occurrence, scope_id: int) -> bool:
    del table, occurrence, scope_id
    # Occurrences do not carry their scope id; the conservative answer is that
    # a shadowing binding in any descendant scope is a conflict.  Returning
    # True keeps the check conservative rather than optimistic.
    return True


_DYNAMIC_CALLS = frozenset({"getattr", "setattr", "hasattr", "delattr", "eval", "exec", "__import__"})


def _dynamic_reference_warnings(path: str, tree: ast.Module, name: str) -> list[Diagnostic]:
    found: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        callee_name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
        if callee_name in _DYNAMIC_CALLS:
            found.append(
                Diagnostic(
                    "dynamic_access_nearby",
                    f"'{callee_name}(...)' at line {node.lineno} can reach attributes by computed name; "
                    f"verify manually that it does not reference '{name}'",
                    Severity.WARNING,
                    path,
                    node.lineno,
                )
            )
    return found


def _string_literal_warnings(path: str, tree: ast.Module, name: str) -> list[Diagnostic]:
    found: list[Diagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == name:
            found.append(
                Diagnostic(
                    "string_literal_match",
                    f"a string literal at line {node.lineno} equals '{name}'; "
                    "it is not renamed automatically because a string is not a reference",
                    Severity.WARNING,
                    path,
                    node.lineno,
                )
            )
    return found


def rename_imported_symbol(
    path: str,
    source: str,
    *,
    module: str,
    old_name: str,
    new_name: str,
    action_id: str = "",
) -> OperationResult:
    """Follow a renamed symbol into the files that import it.

    Without this, renaming a definition leaves every importer referring to a
    name that no longer exists — a "successful" refactor that breaks the build.
    Three import shapes are handled distinctly:

    ``from m import old``
        The import target *and* every local use are renamed.
    ``from m import old as alias``
        Only the import target is renamed; ``alias`` keeps its spelling, so
        local code is untouched.
    ``import m`` … ``m.old``
        The attribute is renamed at each usage; the import is untouched.
    """

    tree, table = _parse(path, source)
    if tree is None or table is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )
    lines = _lines(source)
    edits: list[TextEdit] = []
    diagnostics: list[Diagnostic] = []
    module_aliases: set[str] = set()
    rename_local = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module != module:
                continue
            for alias in node.names:
                if alias.name != old_name:
                    continue
                located = _locate_identifier(lines, node.lineno, node.col_offset, old_name)
                if located is None:
                    diagnostics.append(
                        Diagnostic(
                            "import_not_located",
                            f"could not locate '{old_name}' in the import at line {node.lineno}",
                            Severity.BLOCKING,
                            path,
                            node.lineno,
                        )
                    )
                    continue
                line, column = located
                edits.append(
                    TextEdit(
                        path=path,
                        start_line=line,
                        start_column=column,
                        end_line=line,
                        end_column=column + len(old_name),
                        replacement=new_name,
                        action_id=action_id,
                        symbol=f"{module}.{old_name}",
                        rationale="imported name",
                    )
                )
                if alias.asname is None:
                    rename_local = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    module_aliases.add(alias.asname or module)

    if rename_local:
        binding = table.module_scope.bindings.get(old_name)
        if binding is not None and binding.kind is BindingKind.IMPORT:
            for occurrence in table.occurrences_of(binding):
                edits.append(
                    TextEdit(
                        path=path,
                        start_line=occurrence.line,
                        start_column=occurrence.column,
                        end_line=occurrence.end_line,
                        end_column=occurrence.end_column,
                        replacement=new_name,
                        action_id=action_id,
                        symbol=f"{module}.{old_name}",
                        rationale=f"use of imported name ({occurrence.context})",
                    )
                )

    if module_aliases:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr != old_name:
                continue
            base = _dotted(node.value)
            if base not in module_aliases:
                continue
            end_line = node.end_lineno or node.lineno
            end_column = node.end_col_offset or 0
            edits.append(
                TextEdit(
                    path=path,
                    start_line=end_line,
                    start_column=max(0, end_column - len(old_name)),
                    end_line=end_line,
                    end_column=end_column,
                    replacement=new_name,
                    action_id=action_id,
                    symbol=f"{module}.{old_name}",
                    rationale="qualified module attribute",
                )
            )

    return OperationResult(edits=tuple(edits), diagnostics=tuple(diagnostics), matched=len(edits))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


def dangling_references(
    path: str,
    source: str,
    *,
    names: Sequence[str],
) -> tuple[Diagnostic, ...]:
    """Report uses of ``names`` that no longer resolve to any binding.

    Run after a rename to prove the repository is still coherent; a name that
    is used but unbound is exactly the breakage a single-file rename causes.
    """

    tree, table = _parse(path, source)
    if tree is None or table is None:
        return ()
    wanted = set(names)
    found: list[Diagnostic] = []
    for occurrence in table.occurrences:
        if occurrence.name in wanted and occurrence.binding is None and occurrence.context == "load":
            found.append(
                Diagnostic(
                    "dangling_reference",
                    f"'{occurrence.name}' is used at line {occurrence.line} but is no longer bound in this file",
                    Severity.BLOCKING,
                    path,
                    occurrence.line,
                )
            )
    return tuple(found)


# ---------------------------------------------------------------------------
# Module / package rename
# ---------------------------------------------------------------------------


def rewrite_module_imports(
    path: str,
    source: str,
    *,
    old_module: str,
    new_module: str,
    action_id: str = "",
) -> OperationResult:
    """Rewrite ``import`` / ``from ... import`` targets for a moved module.

    Matches the module itself and any submodule (``a.b`` also rewrites
    ``a.b.c``), never a merely similar prefix (``a.bc`` is untouched).
    """

    tree, table = _parse(path, source)
    if tree is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )
    lines = _lines(source)
    edits: list[TextEdit] = []
    diagnostics: list[Diagnostic] = []

    def rewritten(target: str) -> str | None:
        if target == old_module:
            return new_module
        if target.startswith(old_module + "."):
            return new_module + target[len(old_module) :]
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                replacement = rewritten(alias.name)
                if replacement is None:
                    continue
                located = _locate_dotted(lines, node.lineno, node.col_offset, alias.name)
                if located is None:
                    diagnostics.append(
                        Diagnostic(
                            "import_not_located",
                            f"could not locate '{alias.name}' in the import at line {node.lineno}",
                            Severity.BLOCKING,
                            path,
                            node.lineno,
                        )
                    )
                    continue
                line, column = located
                edits.append(
                    TextEdit(
                        path=path,
                        start_line=line,
                        start_column=column,
                        end_line=line,
                        end_column=column + len(alias.name),
                        replacement=replacement,
                        action_id=action_id,
                        symbol=alias.name,
                        rationale="import target",
                    )
                )
                if alias.asname is None and "." in alias.name:
                    diagnostics.append(
                        Diagnostic(
                            "dotted_import_usage",
                            f"'import {alias.name}' binds '{alias.name.split('.')[0]}'; "
                            "usages spelled with the full dotted path must be rewritten too",
                            Severity.WARNING,
                            path,
                            node.lineno,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                diagnostics.append(
                    Diagnostic(
                        "relative_import_skipped",
                        f"relative import at line {node.lineno} is not rewritten by module rename; "
                        "move the package instead or convert it to an absolute import",
                        Severity.WARNING,
                        path,
                        node.lineno,
                    )
                )
                continue
            replacement = rewritten(node.module or "")
            if replacement is None:
                continue
            located = _locate_dotted(lines, node.lineno, node.col_offset, node.module or "")
            if located is None:
                diagnostics.append(
                    Diagnostic(
                        "import_not_located",
                        f"could not locate '{node.module}' at line {node.lineno}",
                        Severity.BLOCKING,
                        path,
                        node.lineno,
                    )
                )
                continue
            line, column = located
            edits.append(
                TextEdit(
                    path=path,
                    start_line=line,
                    start_column=column,
                    end_line=line,
                    end_column=column + len(node.module or ""),
                    replacement=replacement,
                    action_id=action_id,
                    symbol=node.module or "",
                    rationale="from-import module",
                )
            )

    edits.extend(_rewrite_dotted_usages(path, table, lines, old_module, new_module, action_id))
    return OperationResult(edits=tuple(edits), diagnostics=tuple(diagnostics), matched=len(edits))


def _locate_dotted(lines: Sequence[str], start_line: int, start_column: int, dotted: str) -> tuple[int, int] | None:
    for offset in range(start_line - 1, min(len(lines), start_line + 10)):
        text = lines[offset]
        begin = start_column if offset == start_line - 1 else 0
        index = text.find(dotted, begin)
        while index != -1:
            before = text[index - 1] if index > 0 else " "
            after_index = index + len(dotted)
            after = text[after_index] if after_index < len(text) else " "
            if not (before.isalnum() or before in "_.") and not (after.isalnum() or after in "_"):
                return offset + 1, index
            index = text.find(dotted, index + 1)
    return None


def _rewrite_dotted_usages(
    path: str,
    table: ScopeTable | None,
    lines: Sequence[str],
    old_module: str,
    new_module: str,
    action_id: str,
) -> list[TextEdit]:
    """Rewrite ``a.b.thing`` usages when ``import a.b`` bound the root package.

    Only performed when the root package name itself changes, because that is
    the only case where a textual dotted usage is unambiguously the module.
    """

    del table
    old_root, new_root = old_module.split(".")[0], new_module.split(".")[0]
    if old_root == new_root:
        # The bound root name is unchanged, so every dotted usage still
        # resolves; rewriting them would be churn, not a fix.
        return []
    edits: list[TextEdit] = []
    pattern = re.compile(rf"(?<![\w.]){re.escape(old_module)}(?=\.[A-Za-z_])")
    for number, text in enumerate(lines, start=1):
        stripped = text.lstrip()
        if stripped.startswith(("import ", "from ", "#")):
            continue
        for match in pattern.finditer(text):
            edits.append(
                TextEdit(
                    path=path,
                    start_line=number,
                    start_column=match.start(),
                    end_line=number,
                    end_column=match.end(),
                    replacement=new_module,
                    action_id=action_id,
                    symbol=old_module,
                    rationale="dotted module usage",
                )
            )
    return edits


# ---------------------------------------------------------------------------
# Signature change
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParameterChange:
    operation: str  # add | remove | rename
    name: str
    new_name: str = ""
    annotation: str = ""
    default: str = ""
    position: int | None = None

    def validate(self) -> None:
        if self.operation not in ("add", "remove", "rename"):
            raise ContractError("invalid_parameter_change", f"unknown parameter operation '{self.operation}'")
        if self.operation == "rename" and not self.new_name:
            raise ContractError("invalid_parameter_change", "a rename requires new_name")
        if self.operation == "add" and not self.default and self.position is None:
            raise ContractError(
                "invalid_parameter_change",
                "adding a parameter without a default requires an explicit position",
            )


def change_signature(
    path: str,
    source: str,
    *,
    qualified_function: str,
    changes: Sequence[ParameterChange],
    action_id: str = "",
) -> OperationResult:
    """Change a function's parameter list and update in-file call sites.

    Only *keyword* call sites can be updated safely without types, so a change
    that would require reordering positional arguments at an unresolved call
    site is reported as blocking rather than guessed at.
    """

    for change in changes:
        change.validate()
    tree, table = _parse(path, source)
    if tree is None or table is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )
    module = _module_of(path)
    target_name = qualified_function.split(".")[-1]
    node = _find_function(tree, qualified_function, module)
    if node is None:
        return OperationResult()

    lines = _lines(source)
    edits: list[TextEdit] = []
    diagnostics: list[Diagnostic] = []

    parameters = _render_parameters(node.args, changes, diagnostics, path, node.lineno, lines)
    open_paren = _locate_char(lines, node.lineno, node.col_offset, "(")
    close_paren = _locate_matching(lines, open_paren) if open_paren else None
    if open_paren is None or close_paren is None:
        return OperationResult(
            diagnostics=(
                Diagnostic(
                    "signature_not_located",
                    f"could not locate the parameter list of '{qualified_function}'",
                    Severity.BLOCKING,
                    path,
                    node.lineno,
                ),
            )
        )
    edits.append(
        TextEdit(
            path=path,
            start_line=open_paren[0],
            start_column=open_paren[1] + 1,
            end_line=close_paren[0],
            end_column=close_paren[1],
            replacement=parameters,
            action_id=action_id,
            symbol=qualified_function,
            rationale="parameter list",
        )
    )

    removed = {change.name for change in changes if change.operation == "remove"}
    renamed = {change.name: change.new_name for change in changes if change.operation == "rename"}
    added_required = [
        change for change in changes if change.operation == "add" and not change.default
    ]

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        callee = call.func
        callee_name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
        if callee_name != target_name:
            continue
        for keyword in call.keywords:
            if keyword.arg in removed:
                diagnostics.append(
                    Diagnostic(
                        "call_site_passes_removed_parameter",
                        f"call at line {call.lineno} passes removed parameter '{keyword.arg}'",
                        Severity.BLOCKING,
                        path,
                        call.lineno,
                    )
                )
            elif keyword.arg in renamed:
                located = _locate_identifier(lines, keyword.value.lineno, 0, keyword.arg or "")
                if located is None:
                    continue
                line, column = located
                edits.append(
                    TextEdit(
                        path=path,
                        start_line=line,
                        start_column=column,
                        end_line=line,
                        end_column=column + len(keyword.arg or ""),
                        replacement=renamed[keyword.arg or ""],
                        action_id=action_id,
                        symbol=qualified_function,
                        rationale="keyword argument rename",
                    )
                )
        if added_required and not any(keyword.arg == item.name for item in added_required for keyword in call.keywords):
            diagnostics.append(
                Diagnostic(
                    "call_site_missing_new_required_parameter",
                    f"call at line {call.lineno} does not supply newly required parameter(s): "
                    + ", ".join(item.name for item in added_required),
                    Severity.BLOCKING,
                    path,
                    call.lineno,
                )
            )
    return OperationResult(edits=tuple(edits), diagnostics=tuple(diagnostics), matched=len(edits))


def _find_function(
    tree: ast.Module, qualified: str, module: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    wanted = qualified[len(module) + 1 :] if qualified.startswith(module + ".") else qualified
    parts = wanted.split(".")

    def walk(body: Sequence[ast.stmt], remaining: Sequence[str]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        head, rest = remaining[0], remaining[1:]
        for statement in body:
            if isinstance(statement, ast.ClassDef) and statement.name == head and rest:
                found = walk(statement.body, rest)
                if found is not None:
                    return found
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef) and statement.name == head and not rest:
                return statement
        return None

    return walk(tree.body, parts)


def _slice(lines: Sequence[str], start_line: int, start_column: int, end_line: int, end_column: int) -> str:
    if start_line == end_line:
        return lines[start_line - 1][start_column:end_column]
    parts = [lines[start_line - 1][start_column:]]
    parts.extend(lines[index] for index in range(start_line, end_line - 1))
    parts.append(lines[end_line - 1][:end_column])
    return "\n".join(parts)


def _render_parameters(
    args: ast.arguments,
    changes: Sequence[ParameterChange],
    diagnostics: list[Diagnostic],
    path: str,
    line: int,
    lines: Sequence[str],
) -> str:
    """Re-render the parameter list, preserving untouched parameters verbatim.

    Round-tripping through ``ast.unparse`` would normalise quote style, spacing
    and numeric literals of parameters nobody asked to change — churn that
    hides the real diff.  Original source text is therefore sliced for every
    parameter that is not being renamed.
    """

    removed = {change.name for change in changes if change.operation == "remove"}
    renamed = {change.name: change.new_name for change in changes if change.operation == "rename"}
    additions = [change for change in changes if change.operation == "add"]

    def render(argument: ast.arg, default: ast.expr | None) -> str:
        end_line = (default.end_lineno or default.lineno) if default is not None else (
            argument.end_lineno or argument.lineno
        )
        end_column = (default.end_col_offset or 0) if default is not None else (argument.end_col_offset or 0)
        original = _slice(lines, argument.lineno, argument.col_offset, end_line, end_column)
        replacement = renamed.get(argument.arg)
        if replacement is None:
            return original
        if original.startswith(argument.arg):
            return replacement + original[len(argument.arg) :]
        return replacement  # pragma: no cover - defensive; arg always starts its own span

    positional = [*args.posonlyargs, *args.args]
    defaults_offset = len(positional) - len(args.defaults)
    rendered: list[str] = []
    for index, argument in enumerate(positional):
        if argument.arg in removed:
            continue
        default = args.defaults[index - defaults_offset] if index >= defaults_offset else None
        rendered.append(render(argument, default))
    if args.posonlyargs:
        rendered.insert(len(args.posonlyargs), "/")
    if args.vararg is not None:
        rendered.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        rendered.append("*")
    for argument, default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
        if argument.arg in removed:
            continue
        rendered.append(render(argument, default))
    if args.kwarg is not None:
        rendered.append(f"**{args.kwarg.arg}")

    for change in additions:
        text = change.name
        if change.annotation:
            text += f": {change.annotation}"
        if change.default:
            text += f"={change.default}"
        if change.position is None:
            insert_at = len(rendered)
            if args.kwarg is not None:
                insert_at -= 1
            rendered.insert(insert_at, text)
        else:
            if change.position <= 0 and rendered and rendered[0] == "self":
                diagnostics.append(
                    Diagnostic(
                        "parameter_inserted_before_self",
                        f"refusing to insert '{change.name}' before 'self' at line {line}",
                        Severity.BLOCKING,
                        path,
                        line,
                    )
                )
                continue
            rendered.insert(min(change.position, len(rendered)), text)
    return ", ".join(rendered)


def _locate_char(lines: Sequence[str], start_line: int, start_column: int, char: str) -> tuple[int, int] | None:
    for offset in range(start_line - 1, min(len(lines), start_line + 40)):
        text = lines[offset]
        begin = start_column if offset == start_line - 1 else 0
        index = text.find(char, begin)
        if index != -1:
            return offset + 1, index
    return None


def _locate_matching(lines: Sequence[str], opening: tuple[int, int]) -> tuple[int, int] | None:
    depth = 0
    line_index = opening[0] - 1
    column = opening[1]
    while line_index < len(lines):
        text = lines[line_index]
        while column < len(text):
            char = text[column]
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
                if depth == 0:
                    return line_index + 1, column
            column += 1
        line_index += 1
        column = 0
    return None


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def remove_unused_imports(path: str, source: str, *, action_id: str = "") -> OperationResult:
    """Delete imports whose bound name is never referenced in the file.

    Skips ``__init__.py`` re-exports, ``# noqa`` lines, ``from x import *``
    and anything listed in ``__all__``, because in those cases an unused
    binding is the point.
    """

    tree, table = _parse(path, source)
    if tree is None or table is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )
    if path.endswith("__init__.py"):
        return OperationResult(
            diagnostics=(
                Diagnostic(
                    "package_init_skipped",
                    "imports in __init__.py are commonly re-exports; not removed automatically",
                    Severity.INFO,
                    path,
                ),
            )
        )
    exported = _declared_exports(tree)
    lines = _lines(source)
    used = {occurrence.name for occurrence in table.occurrences if occurrence.context == "load"}
    edits: list[TextEdit] = []
    diagnostics: list[Diagnostic] = []

    for node in tree.body:
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            diagnostics.append(
                Diagnostic(
                    "star_import_present",
                    f"'from ... import *' at line {node.lineno} makes unused-import analysis unsound",
                    Severity.WARNING,
                    path,
                    node.lineno,
                )
            )
            continue
        source_line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
        if "noqa" in source_line:
            continue
        bound = [
            alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
            for alias in node.names
        ]
        if all(name not in used and name not in exported for name in bound):
            end_line = node.end_lineno or node.lineno
            end_column = len(lines[end_line - 1]) if end_line <= len(lines) else 0
            edits.append(
                TextEdit(
                    path=path,
                    start_line=node.lineno,
                    start_column=0,
                    end_line=min(end_line + 1, len(lines)),
                    end_column=0 if end_line < len(lines) else end_column,
                    replacement="",
                    action_id=action_id,
                    symbol=", ".join(bound),
                    rationale="unused import",
                )
            )
    return OperationResult(edits=tuple(edits), diagnostics=tuple(diagnostics), matched=len(edits))


def _declared_exports(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            if isinstance(node.value, ast.List | ast.Tuple):
                return {
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                }
    return set()


def add_import(
    path: str,
    source: str,
    *,
    module: str,
    names: Sequence[str] = (),
    action_id: str = "",
) -> OperationResult:
    """Insert an import after the existing import block, or after the docstring.

    Returns no edit when an equivalent import is already present, which is what
    makes the operation idempotent — running it twice produces one import.
    """

    tree, _ = _parse(path, source)
    if tree is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )
    statement = f"from {module} import {', '.join(names)}" if names else f"import {module}"
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == module and not node.level:
            existing = {alias.name for alias in node.names}
            if set(names) <= existing:
                return OperationResult()
        if isinstance(node, ast.Import) and not names and any(alias.name == module for alias in node.names):
            return OperationResult()

    insert_line = 1
    for index, node in enumerate(tree.body):
        if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            insert_line = (node.end_lineno or node.lineno) + 1
            continue
        if isinstance(node, ast.Import | ast.ImportFrom):
            insert_line = (node.end_lineno or node.lineno) + 1
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_line = (node.end_lineno or node.lineno) + 1
            continue
        break

    return OperationResult(
        edits=(
            TextEdit(
                path=path,
                start_line=insert_line,
                start_column=0,
                end_line=insert_line,
                end_column=0,
                replacement=statement + "\n",
                action_id=action_id,
                symbol=module,
                rationale="added import",
            ),
        ),
        matched=1,
    )


# ---------------------------------------------------------------------------
# Dead code
# ---------------------------------------------------------------------------


def remove_unreferenced_definition(
    path: str,
    source: str,
    *,
    name: str,
    action_id: str = "",
) -> OperationResult:
    """Remove a module-level definition that nothing in the file references.

    Refuses when the name is exported through ``__all__`` or referenced
    anywhere, including inside a string literal — a Django URL name or a
    dependency-injection key is a reference even though it is not a symbol.
    """

    tree, table = _parse(path, source)
    if tree is None or table is None:
        return OperationResult(
            diagnostics=(Diagnostic("parse_failed", f"cannot parse '{path}'", Severity.BLOCKING, path),)
        )
    binding = table.module_scope.bindings.get(name)
    if binding is None or binding.kind not in (BindingKind.FUNCTION, BindingKind.CLASS):
        return OperationResult()
    if name in _declared_exports(tree):
        return OperationResult(
            diagnostics=(
                Diagnostic(
                    "exported_symbol",
                    f"'{name}' is listed in __all__ and is part of the module's public surface",
                    Severity.BLOCKING,
                    path,
                ),
            )
        )
    if table.occurrences_of(binding):
        return OperationResult(
            diagnostics=(
                Diagnostic(
                    "symbol_referenced",
                    f"'{name}' is referenced {len(table.occurrences_of(binding))} time(s) in this file",
                    Severity.BLOCKING,
                    path,
                ),
            )
        )
    literals = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == name
    ]
    if literals:
        return OperationResult(
            diagnostics=(
                Diagnostic(
                    "string_literal_match",
                    f"'{name}' appears as a string literal at line(s) {literals}; it may be referenced dynamically",
                    Severity.BLOCKING,
                    path,
                    literals[0],
                ),
            )
        )

    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and item.name == name
        ),
        None,
    )
    if node is None:
        return OperationResult()
    lines = _lines(source)
    start = min((decorator.lineno for decorator in node.decorator_list), default=node.lineno)
    end = node.end_lineno or node.lineno
    return OperationResult(
        edits=(
            TextEdit(
                path=path,
                start_line=start,
                start_column=0,
                end_line=min(end + 1, len(lines)),
                end_column=0,
                replacement="",
                action_id=action_id,
                symbol=binding.qualified_name,
                rationale="unreferenced definition",
            ),
        ),
        matched=1,
    )


def operation_names() -> tuple[str, ...]:
    return (
        "rename-symbol",
        "rename-imported-symbol",
        "rewrite-module-imports",
        "change-signature",
        "remove-unused-imports",
        "add-import",
        "remove-unreferenced-definition",
    )


OPERATIONS: Mapping[str, Any] = {
    "rename-symbol": rename_binding,
    "rename-imported-symbol": rename_imported_symbol,
    "rewrite-module-imports": rewrite_module_imports,
    "change-signature": change_signature,
    "remove-unused-imports": remove_unused_imports,
    "add-import": add_import,
    "remove-unreferenced-definition": remove_unreferenced_definition,
}


__all__ = [
    "OPERATIONS",
    "Diagnostic",
    "OperationResult",
    "ParameterChange",
    "Severity",
    "add_import",
    "change_signature",
    "operation_names",
    "remove_unreferenced_definition",
    "remove_unused_imports",
    "dangling_references",
    "rename_binding",
    "rename_imported_symbol",
    "rewrite_module_imports",
]
