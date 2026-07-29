"""Bind-parameter placeholders, rewritten into the target dialect's own
spelling -- or refused when no faithful spelling exists.

`sqlglot`'s generator does not translate placeholders between dialects. It
renders each parameter node with whatever syntax the *target generator*
happens to use for that node type, which for every cross-engine pair in this
profile set is something the target server does not read as a placeholder at
all. Reproduced against sqlglot 30.13/30.14 before this module was written:

    postgres `$1`   -> mysql `@1`      -- a MySQL *session variable*, not a
                                          bind parameter: the driver binds
                                          nothing and the server compares
                                          against an unset (NULL) variable
    postgres `$1`   -> oracle `@1`     -- not a bind variable
    tsql     `@p1`  -> postgres `$p1`  -- invalid: `$` takes digits
    oracle   `:one` -> postgres `%(one)s` -- psycopg *client* syntax, not SQL
    mysql    `?`    -> postgres `%s`      -- likewise

None of these are syntax errors that the target re-parse leg would catch,
because sqlglot re-parses its own spelling happily. So a parameterised query
translated with the pre-fix code reported PASSED and then silently matched
the wrong rows (or none) at runtime.

This module rewrites every placeholder into the target's real syntax, keeps
one source parameter mapped to exactly one target parameter, and fails closed
when the target's placeholder style cannot preserve the binding arity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot import exp
from sqlglot.errors import UnsupportedError

#: How each supported dialect spells a bind parameter, with the node shape
#: that renders it (verified by round-tripping each dialect's own syntax
#: through `parse_one(...).sql(dialect=...)`):
#:
#:   numbered   postgres `$1`  Parameter(Literal(n))
#:              duckdb   `$1`  Placeholder("n")
#:   anonymous  mysql    `?`   Placeholder()
#:              sqlite   `?`   Placeholder()
#:   named      tsql     `@p1` Parameter(Var("p1"))
#:              oracle   `:p1` Placeholder("p1")
NUMBERED = "numbered"
ANONYMOUS = "anonymous"
NAMED = "named"

_STYLE: dict[str, str] = {
    "postgres": NUMBERED,
    "duckdb": NUMBERED,
    "mysql": ANONYMOUS,
    "sqlite": ANONYMOUS,
    "tsql": NAMED,
    "oracle": NAMED,
}

#: What a *valid* placeholder looks like once rendered in that dialect. Used
#: as a post-condition on the emitted SQL: anything else is refused rather
#: than shipped.
_TOKEN_PATTERN: dict[str, re.Pattern[str]] = {
    "postgres": re.compile(r"^\$\d+$"),
    "duckdb": re.compile(r"^\$\d+$"),
    "mysql": re.compile(r"^\?$"),
    "sqlite": re.compile(r"^\?$"),
    "tsql": re.compile(r"^@[A-Za-z_][A-Za-z0-9_]*$"),
    "oracle": re.compile(r"^:[A-Za-z_][A-Za-z0-9_]*$"),
}

_NAME_CHARS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class PlaceholderRewrite:
    """One source parameter and the target parameter it became."""

    source_token: str
    target_token: str
    ordinal: int


def is_placeholder(node: exp.Expression) -> bool:
    return node.key in ("placeholder", "parameter")


def placeholder_nodes(expression: exp.Expression) -> list[exp.Expression]:
    """Every placeholder in document order."""
    return [node for node in expression.walk() if is_placeholder(node)]


def _target_node(dialect: str, ordinal: int, name: str) -> exp.Expression:
    style = _STYLE[dialect]
    if style == ANONYMOUS:
        return exp.Placeholder()
    if style == NUMBERED:
        if dialect == "postgres":
            return exp.Parameter(this=exp.Literal.number(ordinal))
        return exp.Placeholder(this=str(ordinal))
    if dialect == "tsql":
        return exp.Parameter(this=exp.Var(this=name))
    return exp.Placeholder(this=name)


def _identity(node: exp.Expression, source_dialect: str, position: int) -> str:
    """What makes two occurrences *the same* parameter.

    With an anonymous source style every `?` is its own parameter, so the
    identity has to be positional. With a numbered or named style two
    occurrences of `$1` are one parameter bound once.
    """
    if _STYLE[source_dialect] == ANONYMOUS:
        return f"#{position}"
    return node.sql(dialect=source_dialect)


def _derived_name(source_token: str, ordinal: int) -> str:
    stripped = source_token.lstrip("$:@")
    if _NAME_CHARS.match(stripped):
        return stripped
    return f"p{ordinal}"


def rewrite(
    statement: exp.Expression,
    source_dialect: str,
    target_dialect: str,
) -> tuple[exp.Expression, tuple[PlaceholderRewrite, ...]]:
    """Rewrite `statement`'s placeholders into `target_dialect` syntax.

    Returns the rewritten statement (a copy) and the ordered source -> target
    mapping, so a caller knows how to bind. Raises `UnsupportedError` when the
    route cannot preserve the binding contract.
    """
    nodes = placeholder_nodes(statement)
    if not nodes:
        return statement, ()

    for dialect in (source_dialect, target_dialect):
        if dialect not in _STYLE:
            raise UnsupportedError(
                f"bind parameters are not portable to or from {dialect!r}: no placeholder "
                "syntax is registered for that dialect"
            )

    rewritten = statement.copy()
    nodes = placeholder_nodes(rewritten)

    ordinals: dict[str, int] = {}
    tokens: dict[str, str] = {}
    mapping: list[PlaceholderRewrite] = []
    for position, node in enumerate(nodes):
        identity = _identity(node, source_dialect, position)
        source_token = node.sql(dialect=source_dialect)
        if identity in ordinals:
            if _STYLE[target_dialect] == ANONYMOUS:
                # `?` is positional and anonymous: one placeholder is one
                # bound value. A source parameter used twice would need the
                # caller to bind the same value twice, which silently changes
                # the parameter contract, so this fails closed instead.
                raise UnsupportedError(
                    f"source parameter {source_token} is used more than once, and "
                    f"{target_dialect} placeholders are positional and anonymous, so the "
                    "binding arity cannot be preserved"
                )
            ordinal = ordinals[identity]
            target_token = tokens[identity]
        else:
            ordinal = len(ordinals) + 1
            ordinals[identity] = ordinal
            replacement = _target_node(
                target_dialect, ordinal, _derived_name(source_token, ordinal)
            )
            target_token = replacement.sql(dialect=target_dialect)
            tokens[identity] = target_token
        replacement = _target_node(
            target_dialect, ordinal, _derived_name(source_token, ordinal)
        )
        node.replace(replacement)
        mapping.append(
            PlaceholderRewrite(
                source_token=source_token, target_token=target_token, ordinal=ordinal
            )
        )

    return rewritten, tuple(mapping)


def verify_tokens(statement: exp.Expression, target_dialect: str) -> None:
    """Post-condition: every placeholder in the emitted statement really is a
    placeholder in the target dialect."""
    pattern = _TOKEN_PATTERN.get(target_dialect)
    if pattern is None:
        if placeholder_nodes(statement):
            raise UnsupportedError(
                f"no placeholder syntax is registered for {target_dialect!r}"
            )
        return
    for node in placeholder_nodes(statement):
        token = node.sql(dialect=target_dialect)
        if not pattern.match(token):
            raise UnsupportedError(
                f"{token!r} is not a bind parameter in {target_dialect}; emitting it would "
                "silently turn a bound value into a variable reference or a literal"
            )
