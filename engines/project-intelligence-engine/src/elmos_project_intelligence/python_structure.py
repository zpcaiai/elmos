"""Parser-backed Python declarations and imports for graph projection.

The line-regex scan in :mod:`.domain` guesses at declarations one physical
line at a time.  For Python the standard library ships the language's own
parser, so there is no reason to guess: this module lifts declarations and
imports out of a real ``ast`` tree.

Two properties are deliberate.

* **Nothing here performs an effect.**  The source arrives as text, exactly
  the way a dispatched handler receives it.  No file is opened, no process is
  spawned, no socket is created, so the module is safe to call from inside a
  handler governed by the dispatch audit guard.
* **Failure is visible, never silent.**  A file the parser rejects returns
  ``None`` so the caller can fall back to the regex scan and *say so*.
  Returning an empty inventory instead would look identical to a file that
  genuinely declares nothing, which is the failure mode this module exists to
  remove.

The records produced here are intentionally minimal.  Identity, language, and
digest belong to the caller, which already owns those rules.
"""

from __future__ import annotations

import ast
from typing import Any, Final


#: Marker recorded on facts a real parser produced.
ORIGIN_PARSED: Final[str] = "PARSED"

#: Marker recorded on facts the fallback line-regex scan produced.
ORIGIN_REGEX: Final[str] = "REGEX"

_PYTHON_SUFFIXES: Final[tuple[str, ...]] = (".py", ".pyi")

#: Declaration kinds.  ``class`` and ``function`` keep the exact spelling the
#: regex scan already uses for every other language, so a consumer that groups
#: by ``kind`` keeps working.  ``module`` and ``async-function`` are additions
#: the regex scan was never able to express.
_KIND_BY_NODE: Final[dict[type, str]] = {
    ast.ClassDef: "class",
    ast.FunctionDef: "function",
    ast.AsyncFunctionDef: "async-function",
}


def is_python_path(path: str) -> bool:
    """Return whether *path* names a file this module can parse."""

    lowered = path.lower()
    return lowered.endswith(_PYTHON_SUFFIXES)


def module_structure(text: str, path: str) -> dict[str, Any] | None:
    """Return parsed declarations and imports for *text*.

    ``None`` means the text is not valid Python.  That is a fallback signal
    for the caller, not an error: a repository routinely contains templates,
    partially written files, and sources for a newer interpreter than the one
    running this engine.
    """

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        # ValueError covers embedded NUL bytes; RecursionError covers a
        # pathologically nested expression.  Both mean "this text is not a
        # tree we can trust", which is the same answer as a syntax error.
        return None

    symbols: list[dict[str, Any]] = [
        {
            "kind": "module",
            "name": path,
            "qualified_name": path,
            "line": 1,
        }
    ]
    imports: list[dict[str, Any]] = []
    _walk(tree.body, scope=(), symbols=symbols, imports=imports)
    return {"symbols": symbols, "imports": imports}


def _walk(
    body: list[ast.stmt],
    *,
    scope: tuple[str, ...],
    symbols: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> None:
    """Collect declarations and imports from *body* and everything under it.

    The walk descends through every statement, not only through declarations,
    so a class defined inside an ``if TYPE_CHECKING:`` block or a function
    defined inside a ``try:`` is found.  The line-regex scan happened to catch
    those because it ignored structure entirely; a tree walk that only
    followed declaration bodies would have been a regression.
    """

    for statement in body:
        kind = _KIND_BY_NODE.get(type(statement))
        if kind is not None:
            # Narrow for the type checker; _KIND_BY_NODE only maps these three.
            assert isinstance(
                statement, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            qualified = (*scope, statement.name)
            symbols.append(
                {
                    "kind": kind,
                    "name": statement.name,
                    "qualified_name": ".".join(qualified),
                    "line": statement.lineno,
                }
            )
            _walk(
                statement.body,
                scope=qualified,
                symbols=symbols,
                imports=imports,
            )
            continue

        if isinstance(statement, ast.Import):
            for alias in statement.names:
                imports.append({"to": alias.name, "line": statement.lineno})
            continue

        if isinstance(statement, ast.ImportFrom):
            # ``from . import x`` has no module name; the dots are the target.
            # The regex scan could not express a relative import at all.
            target = "." * statement.level + (statement.module or "")
            imports.append({"to": target, "line": statement.lineno})
            continue

        for child in _child_bodies(statement):
            _walk(child, scope=scope, symbols=symbols, imports=imports)


def _child_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    """Return the nested statement lists of a non-declaration statement."""

    bodies: list[list[ast.stmt]] = []
    for attribute in ("body", "orelse", "finalbody"):
        value = getattr(statement, attribute, None)
        if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
            bodies.append(value)
    for handler in getattr(statement, "handlers", []) or []:
        if isinstance(handler, ast.ExceptHandler):
            bodies.append(handler.body)
    for case in getattr(statement, "cases", []) or []:
        body = getattr(case, "body", None)
        if isinstance(body, list):
            bodies.append(body)
    return bodies


__all__ = [
    "ORIGIN_PARSED",
    "ORIGIN_REGEX",
    "is_python_path",
    "module_structure",
]
