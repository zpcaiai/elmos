"""Typed identifier preservation and target quoting policy.

Quoted source identifiers are not the same thing as arbitrary SQL text.  The
parser records them as canonical string values and the emitter applies the
target dialect's own quoting character.  Unquoted identifiers remain on the
existing conservative path, including the measured MySQL reserved-word
refusal; this module never silently changes case-folding for an unquoted name.
"""

from __future__ import annotations

from .models import Dialect


class CanonicalIdentifier(str):
    """A string-compatible identifier carrying whether the source quoted it."""

    quoted: bool

    def __new__(cls, value: str, *, quoted: bool = False) -> CanonicalIdentifier:
        instance = str.__new__(cls, value)
        instance.quoted = quoted
        return instance


def quote_identifier(name: str, dialect: Dialect, *, force: bool | None = None) -> str:
    """Render one identifier, preserving an explicit source quote decision."""

    should_quote = bool(getattr(name, "quoted", False)) if force is None else force
    if not should_quote:
        return str(name)
    value = str(name)
    if dialect in (Dialect.POSTGRES, Dialect.ORACLE):
        return '"' + value.replace('"', '""') + '"'
    if dialect is Dialect.MYSQL:
        return "`" + value.replace("`", "``") + "`"
    return "[" + value.replace("]", "]]") + "]"


def qualified_name(schema: str | None, name: str, dialect: Dialect) -> str:
    if schema is None:
        return quote_identifier(name, dialect)
    return f"{quote_identifier(schema, dialect)}.{quote_identifier(name, dialect)}"
