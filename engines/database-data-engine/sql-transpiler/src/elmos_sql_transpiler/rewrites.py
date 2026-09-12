"""Typed source normalization and target lowering rules for known
dialect-conditional constructs.

Three boundaries are handled here instead of being left to whatever the
pinned parser happens to raise:

* Aggregate ORDER BY inside ``GROUP_CONCAT``. The mysql-family parse stores
  it as ``this=Order(this=expr|Distinct, expressions=[...])`` while the
  sqlite-family parse stores it as ``separator=Order(this=<separator
  literal>, expressions=[...])``. Each family's *generator* only renders its
  own shape: the sqlite generator raises ``doesn't support ORDER BY`` for the
  mysql shape, and the mysql generator renders the sqlite shape with the
  separator before the ORDER BY (``GROUP_CONCAT(x SEPARATOR ',' ORDER BY
  x)``), which real MySQL rejects. Canonicalizing to the mysql shape and
  lowering it back to the sqlite shape immediately before sqlite emission
  makes both directions faithful. SQLite has supported aggregate ORDER BY
  since 3.44.0; the pinned 3.53.3 host executes it (verified by test).

* Oracle ``TRUNC(date, fmt)``. The oracle reader produces ``DateTrunc`` with
  the *oracle* format token kept verbatim, which downstream generators either
  reject (``Unexpected interval unit: MM``) or silently mistranslate
  (``DATE(x)`` -- day truncation -- for ``'MM'``). The format token is
  normalized to a canonical unit from an exact allow-list; every other date
  format fails closed with its own diagnostic instead of an accidental
  generator error.

* Oracle ``TRUNC(x)`` with one argument is ambiguous between numeric and
  date truncation and reaches the pipeline as an opaque ``Anonymous`` node
  that is emitted verbatim (``TRUNC(x)``), which no other engine here
  provides. It fails closed. Numeric ``TRUNC(x, d)`` parses to a typed
  ``Trunc`` node and is not touched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot import exp
from sqlglot.errors import UnsupportedError

AGGREGATE_ORDER_CANONICALIZED = "AGGREGATE_ORDER_CANONICALIZED"
ORACLE_TRUNC_FORMAT_NORMALIZED = "ORACLE_TRUNC_FORMAT_NORMALIZED"
SQLITE_AGGREGATE_ORDER_LOWERED = "SQLITE_AGGREGATE_ORDER_LOWERED"

AGGREGATE_ORDER_RULE = "core.canonicalize-aggregate-order"
SQLITE_LOWERING_RULE = "core.lower-sqlite-group-concat-order"
ORACLE_TRUNC_RULE = "core.normalize-oracle-trunc-format"

#: Both MySQL and SQLite default the GROUP_CONCAT separator to a comma, so
#: synthesizing it when the source relied on the default is value-preserving.
_DEFAULT_AGGREGATE_SEPARATOR = ","

#: Verified-portable Oracle TRUNC date formats, normalized to the canonical
#: unit vocabulary the target generators implement. Quarter, week, ISO-year,
#: day-of-week and time-of-day truncation have locale- or calendar-dependent
#: semantics with no faithful portable mapping and stay blocked.
_ORACLE_TRUNC_UNITS = {
    "SYYYY": "year",
    "YYYY": "year",
    "YEAR": "year",
    "MM": "month",
    "MON": "month",
    "MONTH": "month",
    "DD": "day",
    "DDD": "day",
    "J": "day",
}
_ORACLE_TRUNC_ALLOW_LIST = "YYYY/SYYYY/YEAR, MM/MON/MONTH, DD/DDD/J"

HINT_STRIP_RULE = "core.strip-optimizer-hints"
OPTIMIZER_HINT_STRIPPED = "OPTIMIZER_HINT_STRIPPED"

_LOCKING_HINT_TOKENS = frozenset(
    {
        "NOLOCK",
        "READUNCOMMITTED",
        "READCOMMITTED",
        "REPEATABLEREAD",
        "SERIALIZABLE",
        "UPDLOCK",
        "XLOCK",
        "TABLOCK",
        "TABLOCKX",
        "PAGLOCK",
        "ROWLOCK",
        "HOLDLOCK",
        "NOWAIT",
        "READPAST",
    }
)
_HINT_COMMENT = re.compile(r"/\*\+")
_LOCKING_IN_SOURCE = re.compile(
    r"\b(?:WITH\s*\(\s*)?(NOLOCK|READUNCOMMITTED|UPDLOCK|XLOCK|TABLOCKX?|"
    r"HOLDLOCK|READPAST|NOWAIT)\b",
    re.IGNORECASE,
)
_INDEX_HINT_IN_SOURCE = re.compile(r"\b(?:USE|FORCE|IGNORE)\s+INDEX\b", re.IGNORECASE)
_OPTION_HINT_IN_SOURCE = re.compile(r"\bOPTION\s*\(", re.IGNORECASE)


class RewriteBlocked(UnsupportedError):
    """A typed rewrite refused to proceed. Unlike a bare parser complaint,
    the code and message are authored here, carry no customer SQL fragments,
    and name the exact boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _materialized_args(node: exp.Expression, allowed: frozenset[str]) -> set[str]:
    """Arg keys holding a value outside ``allowed``.

    sqlglot's ``args`` dict may contain keys explicitly set to ``None``
    (``siblings`` on ``Order`` is the common one); those carry no semantics
    and must not trip the unmappable-argument guard.
    """
    return {key for key, value in node.args.items() if value is not None and key not in allowed}


def canonicalize_aggregate_order(
    statement: exp.Expression,
) -> tuple[exp.Expression, tuple[str, ...]]:
    """Normalize every ``GROUP_CONCAT`` aggregate ORDER BY into one canonical
    shape: ``this=Order(...)``, ``separator=Literal | None``.

    Mutates and returns the statement, plus the rule id once per statement in
    which at least one node was rewritten.
    """
    fired: list[str] = []
    for node in list(statement.find_all(exp.GroupConcat)):
        unmappable = _materialized_args(node, frozenset({"this", "separator"}))
        if unmappable:
            raise RewriteBlocked(
                "AGGREGATE_ORDER_UNMAPPABLE",
                "GROUP_CONCAT carries argument(s) the canonical aggregate-order "
                "shape cannot represent; refusing to drop them silently",
            )
        this = node.args.get("this")
        separator = node.args.get("separator")
        if isinstance(this, exp.Order):
            if separator is not None and not isinstance(separator, exp.Literal):
                raise RewriteBlocked(
                    "AGGREGATE_ORDER_UNMAPPABLE",
                    "GROUP_CONCAT separator is not a literal in the canonical "
                    "aggregate-order shape",
                )
            continue
        if isinstance(separator, exp.Order):
            order = separator
            order_extra = _materialized_args(order, frozenset({"this", "expressions"}))
            if order_extra:
                raise RewriteBlocked(
                    "AGGREGATE_ORDER_UNMAPPABLE",
                    "aggregate ORDER BY carries argument(s) the canonical shape cannot represent",
                )
            separator_literal = order.args.get("this")
            if separator_literal is not None and not isinstance(separator_literal, exp.Literal):
                raise RewriteBlocked(
                    "AGGREGATE_ORDER_UNMAPPABLE",
                    "the separator carried inside the aggregate ORDER BY is not a literal",
                )
            expressions = order.args.get("expressions") or []
            if not expressions:
                raise RewriteBlocked(
                    "AGGREGATE_ORDER_UNMAPPABLE",
                    "aggregate ORDER BY arrived with no ordering terms; the "
                    "ordering would be silently dropped",
                )
            replacement = exp.GroupConcat(
                this=exp.Order(
                    this=this.copy() if this is not None else None,
                    expressions=[item.copy() for item in expressions],
                ),
                separator=(separator_literal.copy() if separator_literal is not None else None),
            )
            node.replace(replacement)
            if AGGREGATE_ORDER_RULE not in fired:
                fired.append(AGGREGATE_ORDER_RULE)
    return statement, tuple(fired)


def lower_sqlite_group_concat_order(
    statement: exp.Expression,
    target_dialect: str,
) -> tuple[exp.Expression, tuple[str, ...]]:
    """Lower the canonical aggregate-order shape into the sqlite-native
    ``GROUP_CONCAT(expr, sep ORDER BY ...)`` form immediately before emission.

    The sqlite generator raises for the canonical shape; it renders its own
    shape faithfully (including DESC and multiple ordering terms). When no
    separator literal is present the shared comma default is synthesized,
    because rendering the shape without one emits a dangling comma that real
    SQLite rejects.
    """
    if target_dialect != "sqlite":
        return statement, ()
    fired: list[str] = []
    for node in list(statement.find_all(exp.GroupConcat)):
        this = node.args.get("this")
        if not isinstance(this, exp.Order):
            continue
        inner = this.args.get("this")
        if isinstance(inner, exp.Distinct):
            raise RewriteBlocked(
                "SQLITE_DISTINCT_AGGREGATE_SEPARATOR_UNSUPPORTED",
                "SQLite DISTINCT aggregates accept exactly one argument, so the "
                "separator required by the aggregate ORDER BY lowering cannot "
                "be preserved; GROUP_CONCAT(DISTINCT ... ORDER BY ...) stays "
                "blocked for SQLite targets",
            )
        order_extra = _materialized_args(this, frozenset({"this", "expressions"}))
        if order_extra:
            raise RewriteBlocked(
                "AGGREGATE_ORDER_UNMAPPABLE",
                "aggregate ORDER BY carries argument(s) the SQLite lowering cannot represent",
            )
        expressions = this.args.get("expressions") or []
        if not expressions:
            raise RewriteBlocked(
                "AGGREGATE_ORDER_UNMAPPABLE",
                "aggregate ORDER BY arrived with no ordering terms; the "
                "ordering would be silently dropped",
            )
        separator = node.args.get("separator")
        if separator is not None and not isinstance(separator, exp.Literal):
            raise RewriteBlocked(
                "AGGREGATE_ORDER_UNMAPPABLE",
                "GROUP_CONCAT separator is not a literal in the SQLite lowering",
            )
        separator_literal = (
            separator.copy()
            if separator is not None
            else exp.Literal.string(_DEFAULT_AGGREGATE_SEPARATOR)
        )
        replacement = exp.GroupConcat(
            this=inner.copy() if inner is not None else None,
            separator=exp.Order(
                this=separator_literal,
                expressions=[item.copy() for item in expressions],
            ),
        )
        node.replace(replacement)
        if SQLITE_LOWERING_RULE not in fired:
            fired.append(SQLITE_LOWERING_RULE)
    return statement, tuple(fired)


def normalize_oracle_date_trunc(
    statement: exp.Expression,
) -> tuple[exp.Expression, tuple[str, ...]]:
    """Normalize Oracle ``TRUNC(date, fmt)`` format tokens to canonical units
    and fail closed for every Oracle TRUNC form the pinned reader left
    untyped."""
    fired: list[str] = []
    for node in list(statement.find_all(exp.Anonymous)):
        name = node.this
        if isinstance(name, str) and name.upper() == "TRUNC":
            raise RewriteBlocked(
                "ORACLE_TRUNC_AMBIGUOUS_WITHOUT_FORMAT",
                "Oracle TRUNC was not recognized as a typed date or numeric "
                "truncation; a single-argument TRUNC is ambiguous between "
                "numeric and date truncation and is emitted verbatim by no "
                "other engine in this profile set. Supply an explicit date "
                "format or numeric scale",
            )
    for trunc_node in list(statement.find_all(exp.DateTrunc)):
        unit = trunc_node.args.get("unit")
        if not (isinstance(unit, exp.Literal) and unit.is_string):
            raise RewriteBlocked(
                "ORACLE_TRUNC_FORMAT_UNSUPPORTED",
                "Oracle TRUNC date format is missing or not a string literal; "
                f"verified allow-list: {_ORACLE_TRUNC_ALLOW_LIST}",
            )
        canonical = _ORACLE_TRUNC_UNITS.get(str(unit.this).upper())
        if canonical is None:
            raise RewriteBlocked(
                "ORACLE_TRUNC_FORMAT_UNSUPPORTED",
                "Oracle TRUNC date format is outside the verified allow-list "
                f"({_ORACLE_TRUNC_ALLOW_LIST}); quarter, week, ISO-year, "
                "day-of-week and time-of-day truncation have no faithful "
                "portable mapping and stay blocked",
            )
        trunc_node.set("unit", exp.Literal.string(canonical))
        if ORACLE_TRUNC_RULE not in fired:
            fired.append(ORACLE_TRUNC_RULE)
    return statement, tuple(fired)


@dataclass(frozen=True)
class SourceHintScan:
    locking: bool
    plan_hint: bool


def inspect_source_hints(sql: str) -> SourceHintScan:
    """Detect vendor hints in the raw source text.

    Plan-hint comments (``/*+ ... */``) are often dropped by the parser
    before they become AST nodes. Scanning the source keeps
    ``silentDropTolerance = 0``: a dropped optimizer comment is still
    recorded, and a locking hint is still blocked.
    """
    return SourceHintScan(
        locking=_LOCKING_IN_SOURCE.search(sql) is not None,
        plan_hint=(
            _HINT_COMMENT.search(sql) is not None
            or _INDEX_HINT_IN_SOURCE.search(sql) is not None
            or _OPTION_HINT_IN_SOURCE.search(sql) is not None
        ),
    )


def _hint_token(node: exp.Expression) -> str:
    if isinstance(node, exp.Var):
        return str(node.this).upper()
    if isinstance(node, exp.Identifier):
        return str(node.this).upper()
    this = node.args.get("this")
    if isinstance(this, exp.Expression):
        return _hint_token(this)
    if this is not None:
        return str(this).upper()
    return ""


def strip_optimizer_hints(
    statement: exp.Expression,
) -> tuple[exp.Expression, tuple[str, ...]]:
    """Remove plan/index hints from the typed AST.

    Locking and isolation hints change which rows a query may observe, so
    they fail closed instead of being stripped.
    """
    fired = False
    for table in list(statement.find_all(exp.Table)):
        hints = list(table.args.get("hints") or [])
        if not hints:
            continue
        kept: list[exp.Expression] = []
        for hint in hints:
            tokens = {_hint_token(hint), *(_hint_token(item) for item in hint.expressions or [])}
            if tokens & _LOCKING_HINT_TOKENS:
                raise RewriteBlocked(
                    "LOCKING_HINT_NOT_PORTABLE",
                    "Locking and isolation hints (NOLOCK, HOLDLOCK, UPDLOCK and "
                    "related table hints) change concurrency semantics and are "
                    "not stripped or rewritten",
                )
            fired = True
        table.set("hints", kept or None)
    for select in list(statement.find_all(exp.Select)):
        if select.args.get("hint") is not None:
            select.set("hint", None)
            fired = True
        options = list(select.args.get("options") or [])
        if options:
            select.set("options", None)
            fired = True
    if statement.find(exp.Hint) is not None:
        for hint in list(statement.find_all(exp.Hint)):
            hint.pop()
            fired = True
    return statement, ((HINT_STRIP_RULE,) if fired else ())
