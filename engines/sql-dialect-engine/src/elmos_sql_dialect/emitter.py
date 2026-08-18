"""Emits certified-ddl-v1 canonical `Table`/`Index` models as target-dialect
DDL text, using the hand-verified per-vendor rendering rules in `dialects.py`
(never sqlglot's generic cross-dialect generator -- see that module's
docstring for why)."""
from __future__ import annotations

from .dialects import (
    check_operator_sql,
    render_auto_increment_suffix,
    render_default,
    render_reference_actions,
    render_type,
)
from .models import (
    AddColumn,
    AddConstraint,
    AlterTable,
    CheckComparison,
    CheckConstraint,
    Column,
    Dialect,
    DialectError,
    DropColumn,
    DropConstraint,
    ForeignKey,
    Index,
    RenameColumn,
    Table,
)


def _render_check_comparison(comparison: CheckComparison) -> str:
    literal = (
        f"'{comparison.literal.replace(chr(39), chr(39) * 2)}'"
        if comparison.literal_is_string
        else comparison.literal
    )
    return f"{comparison.column} {check_operator_sql(comparison.operator)} {literal}"


def _render_column(column: Column, dialect: Dialect) -> str:
    parts = [column.name, render_type(column.type_ref, dialect)]
    if column.auto_increment:
        parts[-1] = parts[-1] + render_auto_increment_suffix(dialect)
    default = (
        None
        if column.default is None
        else f"DEFAULT {render_default(column.default, column.type_ref, dialect)}"
    )
    # Oracle's column_definition grammar is
    #   column datatype [DEFAULT expr] [inline_constraint]
    # so DEFAULT must precede NOT NULL there; `c NUMBER(1) NOT NULL DEFAULT 1`
    # is a syntax error on a real Oracle server (sqlglot parses it, so the
    # syntax-validation leg cannot catch this). MySQL, PostgreSQL and SQL
    # Server accept either order, and `NOT NULL DEFAULT ...` is the
    # conventional spelling there.
    if dialect is Dialect.ORACLE:
        if default is not None:
            parts.append(default)
        if not column.nullable:
            parts.append("NOT NULL")
        return " ".join(parts)
    if not column.nullable:
        parts.append("NOT NULL")
    if default is not None:
        parts.append(default)
    return " ".join(parts)


def _require_mysql_auto_increment_key(table: Table) -> None:
    """MySQL requires every AUTO_INCREMENT column to be a key.

    `CREATE TABLE t (id BIGINT AUTO_INCREMENT)` parses in every SQL grammar
    -- including sqlglot's, so the syntax-validation leg passes it -- and is
    then rejected by the server itself with errno 1075, "Incorrect table
    definition; there can be only one auto column and it must be defined as a
    key". PostgreSQL, Oracle and SQL Server all accept an identity column
    that is not a key, so a table translated *from* one of them is exactly
    where this appears.
    """
    keyed = set(table.primary_key)
    for unique in table.unique_constraints:
        keyed.update(unique)
    for column in table.columns:
        if column.auto_increment and column.name not in keyed:
            raise DialectError(
                "CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY",
                f"MySQL requires the AUTO_INCREMENT column {column.name!r} to be a key "
                "(PRIMARY KEY or UNIQUE); the source dialect's identity column carries no "
                "such requirement, so the translation cannot supply one",
            )


def _render_foreign_key_clause(fk: ForeignKey, dialect: Dialect) -> str:
    base = (
        f"FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.ref_table}"
        f" ({', '.join(fk.ref_columns)})"
    )
    actions = render_reference_actions(fk.on_delete, fk.on_update, dialect)
    return f"{base} {actions}" if actions else base


def emit_create_table(table: Table, dialect: Dialect) -> str:
    if dialect is Dialect.MYSQL:
        _require_mysql_auto_increment_key(table)
    lines: list[str] = [_render_column(c, dialect) for c in table.columns]

    if table.primary_key:
        lines.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")

    for unique in table.unique_constraints:
        lines.append(f"UNIQUE ({', '.join(unique)})")

    for fk in table.foreign_keys:
        clause = _render_foreign_key_clause(fk, dialect)
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


def _render_check_clause(check: CheckConstraint) -> str:
    joiner = " OR " if check.connector is not None and check.connector.value == "OR" else " AND "
    return f"CHECK ({joiner.join(_render_check_comparison(c) for c in check.comparisons)})"


def _named(name: str | None, clause: str) -> str:
    return f"CONSTRAINT {name} {clause}" if name else clause


def emit_alter_table(alter: AlterTable, dialect: Dialect) -> str:
    """Render one certified-alter-v1 model in the target dialect.

    Two rules here are NOT enforceable by the syntax-validation leg, because
    `sqlglot` happily parses both spellings even though the real databases
    reject them. They were verified against each vendor's documented grammar
    and are locked down by tests instead -- the same posture already taken
    for sqlglot's AUTO_INCREMENT/IDENTITY generation defect:

      1. **Oracle has no `ADD COLUMN`.** The keyword `COLUMN` is a syntax
         error there; Oracle spells it `ALTER TABLE t ADD (c NUMBER)`.
         Emitting `ADD COLUMN` would produce a statement sqlglot accepts and
         Oracle refuses.
      2. **SQL Server has no `ALTER TABLE ... RENAME COLUMN`.** It requires
         the `sp_rename` stored procedure, which is a different statement
         kind entirely.
    """
    statements: list[str] = []
    for action in alter.actions:
        if isinstance(action, AddColumn):
            if dialect is Dialect.MYSQL and action.column.auto_increment:
                # Same errno 1075 rule as CREATE TABLE, and certified-alter-v1
                # deliberately refuses the inline PRIMARY KEY / UNIQUE
                # shorthand on an added column, so this statement can never
                # make the new column a key.
                raise DialectError(
                    "CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY",
                    f"MySQL requires the AUTO_INCREMENT column {action.column.name!r} to be a "
                    "key, which a single ADD COLUMN cannot establish; add the column and the "
                    "key as separate statements",
                )
            column_sql = _render_column(action.column, dialect)
            if action.foreign_key is not None:
                column_sql += (
                    f" REFERENCES {action.foreign_key.ref_table}"
                    f" ({', '.join(action.foreign_key.ref_columns)})"
                )
                actions_sql = render_reference_actions(
                    action.foreign_key.on_delete, action.foreign_key.on_update, dialect
                )
                if actions_sql:
                    column_sql += f" {actions_sql}"
            if action.check is not None:
                column_sql += " " + _render_check_clause(action.check)
            if dialect is Dialect.ORACLE:
                # Oracle: no COLUMN keyword; parenthesised column list.
                statements.append(f"ALTER TABLE {alter.table} ADD ({column_sql})")
            elif dialect is Dialect.TSQL:
                # SQL Server: ADD, without the COLUMN keyword.
                statements.append(f"ALTER TABLE {alter.table} ADD {column_sql}")
            else:
                statements.append(f"ALTER TABLE {alter.table} ADD COLUMN {column_sql}")

        elif isinstance(action, DropColumn):
            statements.append(f"ALTER TABLE {alter.table} DROP COLUMN {action.column}")

        elif isinstance(action, RenameColumn):
            if dialect is Dialect.TSQL:
                # T-SQL's only column rename. Quoting follows sp_rename's
                # documented 'table.column' form.
                statements.append(
                    f"EXEC sp_rename '{alter.table}.{action.column}', '{action.new_name}', 'COLUMN'"
                )
            else:
                statements.append(
                    f"ALTER TABLE {alter.table} RENAME COLUMN {action.column} TO {action.new_name}"
                )

        elif isinstance(action, AddConstraint):
            if action.primary_key:
                clause = f"PRIMARY KEY ({', '.join(action.primary_key)})"
            elif action.unique:
                clause = f"UNIQUE ({', '.join(action.unique)})"
            elif action.foreign_key is not None:
                clause = _render_foreign_key_clause(action.foreign_key, dialect)
            else:
                assert action.check is not None  # AddConstraint.__post_init__ guarantees one is set
                clause = _render_check_clause(action.check)
            statements.append(f"ALTER TABLE {alter.table} ADD {_named(action.name, clause)}")

        elif isinstance(action, DropConstraint):
            statements.append(f"ALTER TABLE {alter.table} DROP CONSTRAINT {action.name}")

    return ";\n".join(statements)
