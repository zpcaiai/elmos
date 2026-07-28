"""Emits certified-ddl-v1 canonical `Table`/`Index` models as target-dialect
DDL text, using the hand-verified per-vendor rendering rules in `dialects.py`
(never sqlglot's generic cross-dialect generator -- see that module's
docstring for why)."""
from __future__ import annotations

from .dialects import (
    check_operator_sql,
    referential_action_sql,
    render_auto_increment_suffix,
    render_default,
    render_type,
)
from .models import CheckComparison, Column, Dialect, Index, Table


def _render_check_comparison(comparison: CheckComparison) -> str:
    literal = f"'{comparison.literal.replace(chr(39), chr(39) * 2)}'" if comparison.literal_is_string else comparison.literal
    return f"{comparison.column} {check_operator_sql(comparison.operator)} {literal}"


def _render_column(column: Column, dialect: Dialect) -> str:
    parts = [column.name, render_type(column.type_ref, dialect)]
    if column.auto_increment:
        parts[-1] = parts[-1] + render_auto_increment_suffix(dialect)
    if not column.nullable:
        parts.append("NOT NULL")
    if column.default is not None:
        parts.append(f"DEFAULT {render_default(column.default, column.type_ref, dialect)}")
    return " ".join(parts)


def emit_create_table(table: Table, dialect: Dialect) -> str:
    lines: list[str] = [_render_column(c, dialect) for c in table.columns]

    if table.primary_key:
        lines.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")

    for unique in table.unique_constraints:
        lines.append(f"UNIQUE ({', '.join(unique)})")

    for fk in table.foreign_keys:
        clause = (
            f"FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.ref_table} ({', '.join(fk.ref_columns)})"
            f" ON DELETE {referential_action_sql(fk.on_delete)} ON UPDATE {referential_action_sql(fk.on_update)}"
        )
        lines.append(f"CONSTRAINT {fk.name} {clause}" if fk.name else clause)

    for check in table.check_constraints:
        joiner = " OR " if check.connector is not None and check.connector.value == "OR" else " AND "
        comparison_sql = joiner.join(_render_check_comparison(c) for c in check.comparisons)
        clause = f"CHECK ({comparison_sql})"
        lines.append(f"CONSTRAINT {check.name} {clause}" if check.name else clause)

    body = ",\n    ".join(lines)
    return f"CREATE TABLE {table.name} (\n    {body}\n)"


def emit_create_index(index: Index, dialect: Dialect) -> str:
    keyword = "CREATE UNIQUE INDEX" if index.unique else "CREATE INDEX"
    return f"{keyword} {index.name} ON {index.table} ({', '.join(index.columns)})"
