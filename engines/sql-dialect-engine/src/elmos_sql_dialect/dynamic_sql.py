"""Dynamic SQL constant folding, safety boundary, and target transpilation.

Batch 31 and docs/batch31/QUALITY_GATES.md require that dynamic SQL (EXECUTE IMMEDIATE,
dynamic string execution) fails closed against unverified runtime concatenation.
However, when dynamic SQL queries are constructed from pure string literals and
constant concatenations, they can be statically folded, validated, and safely transpiled.
"""

from __future__ import annotations

import re
from typing import cast

import sqlglot
from sqlglot import exp

from .models import Dialect, DialectError


def fold_constant_sql_expression(node: exp.Expression) -> str:
    """Fold a string expression into its constant string value if purely static.

    Fails closed if the expression depends on runtime variables, columns, or non-deterministic functions.
    """
    if isinstance(node, exp.Literal) and node.is_string:
        return str(node.this)

    # String concatenation: node is exp.Concat or exp.DPipe
    if isinstance(node, exp.DPipe):
        left = fold_constant_sql_expression(node.this)
        right = fold_constant_sql_expression(node.expression)
        return left + right

    if isinstance(node, exp.Concat):
        parts = [fold_constant_sql_expression(e) for e in node.expressions]
        return "".join(parts)

    raise DialectError(
        "CERTIFIED_DYNAMIC_SQL_UNSAFE",
        f"Dynamic SQL expression {node.sql()!r} is not a verifiable static constant concatenation",
    )


def extract_and_transpile_dynamic_sql(
    dynamic_stmt: str,
    source_dialect: Dialect,
    target_dialect: Dialect,
) -> str:
    """Extract a constant-folded dynamic SQL query, transpile it to the target dialect,

    and re-wrap it in the target's dynamic execution statement.
    """
    parsed = sqlglot.parse_one(dynamic_stmt, read=source_dialect.value)

    raw_query: str | None = None
    if isinstance(parsed, exp.Command):
        # e.g., EXECUTE IMMEDIATE '...'
        cmd_text = parsed.sql().strip()
        m = re.search(r"EXECUTE\s+IMMEDIATE\s+(.+)$", cmd_text, re.IGNORECASE)
        if m:
            expr_str = m.group(1).rstrip(";")
            expr_ast = cast(exp.Expression, sqlglot.parse_one(expr_str, read=source_dialect.value))
            raw_query = fold_constant_sql_expression(expr_ast)
    elif isinstance(parsed, exp.Anonymous) and parsed.this.upper() == "EXECUTE IMMEDIATE":
        # parsed as Anonymous function or command
        args = list(parsed.expressions)
        if args:
            raw_query = fold_constant_sql_expression(args[0])

    if raw_query is None:
        # Fallback regex for EXECUTE IMMEDIATE / sp_executesql
        m = re.search(r"EXECUTE\s+IMMEDIATE\s+'([^']*(?:''[^']*)*)'", dynamic_stmt, re.IGNORECASE)
        if m:
            raw_query = m.group(1).replace("''", "'")
        else:
            m_tsql = re.search(r"EXEC\s+sp_executesql\s+N'([^']*(?:''[^']*)*)'", dynamic_stmt, re.IGNORECASE)
            if m_tsql:
                raw_query = m_tsql.group(1).replace("''", "'")

    if raw_query is None:
        raise DialectError(
            "CERTIFIED_DYNAMIC_SQL_UNSUPPORTED",
            f"Unable to safely extract constant query from dynamic statement: {dynamic_stmt!r}",
        )

    # Transpile the folded query using SQLGlot
    try:
        transpiled_query = sqlglot.transpile(
            raw_query,
            read=source_dialect.value,
            write=target_dialect.value,
        )[0]
    except Exception as exc:
        raise DialectError(
            "CERTIFIED_DYNAMIC_SQL_TRANSPILE_FAILED",
            f"Failed to transpile inner dynamic query {raw_query!r}: {exc}",
        ) from exc

    escaped_query = transpiled_query.replace("'", "''")

    # Wrap in target dynamic SQL syntax
    if target_dialect is Dialect.TSQL:
        return f"EXEC sp_executesql N'{escaped_query}';"
    elif target_dialect in (Dialect.ORACLE, Dialect.POSTGRES):
        return f"EXECUTE IMMEDIATE '{escaped_query}';"
    elif target_dialect is Dialect.MYSQL:
        # MySQL PREPARE + EXECUTE pattern
        return (
            f"SET @dyn_stmt = '{escaped_query}';\n"
            f"PREPARE stmt FROM @dyn_stmt;\n"
            f"EXECUTE stmt;\n"
            f"DEALLOCATE PREPARE stmt;"
        )
    return f"EXECUTE IMMEDIATE '{escaped_query}';"
