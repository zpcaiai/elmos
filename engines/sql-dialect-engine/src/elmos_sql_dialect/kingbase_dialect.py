"""KingbaseES (人大金仓) dialect lowering implementation.

AST-based SQL dialect lowering with zero regex:
- DDL: table creation supporting PG-compatible mode (default) and Oracle-compatible mode.
- Types: SERIAL/BIGSERIAL, BOOLEAN, TEXT, JSONB, BYTEA for PG mode;
  NUMBER(IDENTITY), NUMBER(1), CLOB, BLOB, VARCHAR2 for Oracle mode.
- Constraints: PK, FK, UNIQUE, CHECK with identifier and casing preservation.
- Sequences: CREATE SEQUENCE, seq.NEXTVAL, NEXTVAL('seq').
- DML & Queries: LIMIT/OFFSET (PG) vs OFFSET...FETCH (Oracle), function lowering
  (NOW() -> CURRENT_TIMESTAMP/SYSDATE, IFNULL -> COALESCE/NVL, ILIKE).
- Upsert: ON CONFLICT DO UPDATE (PG) vs MERGE INTO AST (Oracle).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from sqlglot import exp, parse_one
from sqlglot.generator import Generator

logger = logging.getLogger(__name__)


class KingbaseMode(str, Enum):
    """KingbaseES compatibility modes."""

    PG = "PG"  # PostgreSQL compatibility mode (default)
    ORACLE = "ORACLE"  # Oracle compatibility mode


class KingbaseGenerator(Generator):
    """Custom AST generator for KingbaseES formatting."""

    TYPE_MAPPING = {
        **Generator.TYPE_MAPPING,
        exp.DataType.Type.DECIMAL: "NUMERIC",
    }

    def reference_sql(self, expression: exp.Reference) -> str:
        this = self.sql(expression, "this")
        if " (" in this:
            this = this.replace(" (", "(")
        expressions = self.expressions(expression, flat=True)
        expressions = f"({expressions})" if expressions else ""
        options = self.expressions(expression, key="options", flat=True, sep=" ")
        options = f" {options}" if options else ""
        return f"REFERENCES {this}{expressions}{options}"


class KingbaseASTTransformer:
    """AST-based transformer for KingbaseES dialect."""

    def __init__(self, mode: KingbaseMode = KingbaseMode.PG) -> None:
        self.mode = mode
        self.generator = KingbaseGenerator()

    def transform_column_def(
        self, col: exp.ColumnDef, source_dialect: str = "postgres"
    ) -> exp.ColumnDef:
        """Transform a ColumnDef node to KingbaseES data types and constraints."""
        kind_sql = col.kind.sql().upper() if col.kind else ""

        has_auto_increment = False
        new_constraints: list[exp.ColumnConstraint] = []

        for c in col.constraints:
            k = c.kind
            if isinstance(
                k,
                exp.AutoIncrementColumnConstraint
                | exp.GeneratedAsIdentityColumnConstraint,
            ):
                has_auto_increment = True
            elif "AUTO_INCREMENT" in k.sql().upper() or "IDENTITY" in k.sql().upper():
                has_auto_increment = True
            elif isinstance(k, exp.DefaultColumnConstraint):
                def_val = k.this.sql().upper()
                if self.mode == KingbaseMode.ORACLE:
                    if def_val in ("TRUE", "1"):
                        k.set("this", exp.Literal.number(1))
                    elif def_val in ("FALSE", "0"):
                        k.set("this", exp.Literal.number(0))
                    elif "CURRENT_TIMESTAMP" in def_val or "NOW" in def_val:
                        k.set("this", exp.var("SYSDATE"))
                new_constraints.append(c)
            else:
                new_constraints.append(c)

        col.set("constraints", new_constraints)

        if self.mode == KingbaseMode.ORACLE:
            # Oracle-compatible mode
            if "BIGSERIAL" in kind_sql or (has_auto_increment and "BIGINT" in kind_sql):
                col.set("kind", exp.var("NUMBER(19) IDENTITY(1, 1)"))
            elif "SERIAL" in kind_sql or has_auto_increment:
                col.set("kind", exp.var("NUMBER(10) IDENTITY(1, 1)"))
            elif "IDENTITY" in kind_sql:
                col.set("kind", exp.var("NUMBER(10) IDENTITY(1, 1)"))
            elif col.kind and col.kind.is_type("boolean", "bool"):
                col.set("kind", exp.var("NUMBER(1)"))
            elif col.kind and col.kind.is_type("text", "longtext", "mediumtext", "json", "jsonb"):
                col.set("kind", exp.var("CLOB"))
            elif "VARCHAR(MAX)" in kind_sql or "NVARCHAR(MAX)" in kind_sql:
                col.set("kind", exp.var("CLOB"))
            elif col.kind and (
                col.kind.is_type("varbinary", "blob", "bytea")
                or kind_sql in ("BYTEA", "BLOB", "LONGBLOB", "MEDIUMBLOB", "IMAGE")
            ):
                col.set("kind", exp.var("BLOB"))
            elif col.kind and col.kind.is_type("datetime"):
                col.set("kind", exp.var("DATE"))
            elif col.kind and col.kind.is_type("timestamptz"):
                col.set("kind", exp.var("TIMESTAMP WITH TIME ZONE"))
            elif col.kind and col.kind.is_type("uuid"):
                col.set("kind", exp.var("VARCHAR2(36)"))
            elif col.kind and col.kind.is_type("varchar", "nvarchar"):
                args = col.kind.expressions
                if args:
                    col.set("kind", exp.var(f"VARCHAR2({args[0].sql()})"))
                else:
                    col.set("kind", exp.var("VARCHAR2(255)"))
        else:
            # PG-compatible mode (default)
            if "BIGSERIAL" in kind_sql or (has_auto_increment and "BIGINT" in kind_sql):
                col.set("kind", exp.var("BIGSERIAL"))
            elif "SERIAL" in kind_sql or has_auto_increment:
                col.set("kind", exp.var("SERIAL"))
            elif "IDENTITY" in kind_sql:
                col.set("kind", exp.var("SERIAL"))
            elif col.kind and col.kind.is_type("text", "longtext", "mediumtext", "clob", "nclob"):
                col.set("kind", exp.var("TEXT"))
            elif "VARCHAR(MAX)" in kind_sql or "NVARCHAR(MAX)" in kind_sql:
                col.set("kind", exp.var("TEXT"))
            elif col.kind and col.kind.is_type("json", "jsonb"):
                col.set("kind", exp.var("JSONB"))
            elif col.kind and (
                col.kind.is_type("blob", "varbinary", "bytea")
                or kind_sql in ("BLOB", "LONGBLOB", "MEDIUMBLOB", "IMAGE", "BYTEA")
            ):
                col.set("kind", exp.var("BYTEA"))
            elif col.kind and col.kind.is_type("boolean", "bool"):
                col.set("kind", exp.var("BOOLEAN"))
            elif col.kind and col.kind.is_type("datetime"):
                col.set("kind", exp.var("TIMESTAMP WITHOUT TIME ZONE"))
            elif col.kind and col.kind.is_type("timestamptz"):
                col.set("kind", exp.var("TIMESTAMP WITH TIME ZONE"))
            elif col.kind and col.kind.is_type("uuid"):
                col.set("kind", exp.var("UUID"))

        return col

    def transform_create_table(
        self, ast: exp.Create, source_dialect: str = "postgres"
    ) -> exp.Create:
        """Transform CREATE TABLE statement for KingbaseES."""
        schema_def = ast.this
        if not isinstance(schema_def, exp.Schema):
            return ast

        new_expressions: list[exp.Expression] = []
        for item in schema_def.expressions:
            if isinstance(item, exp.ColumnDef):
                new_expressions.append(
                    self.transform_column_def(item, source_dialect=source_dialect)
                )
            else:
                new_expressions.append(item)

        schema_def.set("expressions", new_expressions)
        return ast

    def transform_query(
        self, ast: exp.Expression, source_dialect: str = "postgres"
    ) -> exp.Expression:
        """Transform Query AST for KingbaseES."""

        def _rewrite(node: exp.Expression) -> exp.Expression:
            # Function mappings
            if isinstance(node, exp.Coalesce):
                if self.mode == KingbaseMode.ORACLE:
                    args = [node.this] + list(node.expressions)
                    return exp.Anonymous(this="NVL", expressions=args)
                return node
            if isinstance(node, exp.Anonymous):
                name = node.name.upper()
                if name == "IFNULL":
                    if self.mode == KingbaseMode.ORACLE:
                        return exp.Anonymous(this="NVL", expressions=node.expressions)
                    return exp.Coalesce(this=node.expressions[0], expressions=node.expressions[1:])
                if name == "NOW":
                    if self.mode == KingbaseMode.ORACLE:
                        return exp.var("SYSDATE")
                    return exp.CurrentTimestamp()
            elif isinstance(node, exp.CurrentTimestamp) and self.mode == KingbaseMode.ORACLE:
                return exp.var("SYSDATE")

            # String concatenation in Oracle mode: CONCAT(a, b) -> a || b
            if isinstance(node, exp.Concat) and self.mode == KingbaseMode.ORACLE:
                exprs = node.expressions
                if exprs:
                    current = exprs[0]
                    for nxt in exprs[1:]:
                        current = exp.DPipe(this=current, expression=nxt)
                    return current

            return node

        return ast.transform(_rewrite)


def lower_kingbase_ddl(
    sql: str, mode: KingbaseMode = KingbaseMode.PG, source_dialect: str = "postgres"
) -> str:
    """Lower a DDL statement to KingbaseES SQL."""
    parsed = parse_one(sql, read=source_dialect)
    transformer = KingbaseASTTransformer(mode=mode)
    if isinstance(parsed, exp.Create) and parsed.kind == "TABLE":
        transformed = transformer.transform_create_table(
            parsed, source_dialect=source_dialect
        )
        target_read = "postgres" if mode == KingbaseMode.PG else "oracle"
        return transformer.generator.generate(transformed)
    target_dialect = "postgres" if mode == KingbaseMode.PG else "oracle"
    return parsed.sql(dialect=target_dialect)


def lower_kingbase_query(
    sql: str, mode: KingbaseMode = KingbaseMode.PG, source_dialect: str = "postgres"
) -> str:
    """Lower a query or DML statement to KingbaseES SQL."""
    parsed = parse_one(sql, read=source_dialect)
    transformer = KingbaseASTTransformer(mode=mode)
    transformed = transformer.transform_query(parsed, source_dialect=source_dialect)
    target_dialect = "postgres" if mode == KingbaseMode.PG else "oracle"
    return transformed.sql(dialect=target_dialect)


def lower_kingbase_sequence(
    sql: str, mode: KingbaseMode = KingbaseMode.PG
) -> str:
    """Lower sequence usage and definitions to KingbaseES SQL."""
    parsed = parse_one(sql)
    if mode == KingbaseMode.ORACLE:
        # e.g., NEXTVAL('seq') -> seq.NEXTVAL
        def _rewrite_seq(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Anonymous) and node.name.upper() == "NEXTVAL":
                arg = node.expressions[0]
                seq_name = arg.name if hasattr(arg, "name") else arg.sql().strip("'\"")
                return exp.Column(
                    this=exp.to_identifier("NEXTVAL"),
                    table=exp.to_identifier(seq_name),
                )
            return node

        rewritten = parsed.transform(_rewrite_seq)
        return rewritten.sql(dialect="oracle")
    return parsed.sql(dialect="postgres")


def lower_kingbase_upsert(
    sql: str,
    mode: KingbaseMode = KingbaseMode.PG,
    target_table: str | None = None,
    conflict_keys: list[str] | None = None,
    update_cols: list[str] | None = None,
) -> str:
    """Lower Upsert statements for KingbaseES."""
    parsed = parse_one(sql)
    if mode == KingbaseMode.PG:
        # Ensure ON CONFLICT is properly formatted
        return parsed.sql(dialect="postgres")
    
    # In Oracle mode, synthesize MERGE INTO
    if isinstance(parsed, exp.Insert):
        table = target_table or (parsed.this.this.sql() if parsed.this else "target_table")
        c_keys = conflict_keys or ["id"]
        
        # Build ON conditions
        on_conds = [
            exp.EQ(
                this=exp.Column(this=exp.to_identifier(k), table=exp.to_identifier("t")),
                expression=exp.Column(this=exp.to_identifier(k), table=exp.to_identifier("s")),
            )
            for k in c_keys
        ]
        on_expr = on_conds[0]
        for cond in on_conds[1:]:
            on_expr = exp.And(this=on_expr, expression=cond)

        # Build matched SET clauses
        cols = update_cols or []
        set_exprs = [
            exp.EQ(
                this=exp.Column(this=exp.to_identifier(c), table=exp.to_identifier("t")),
                expression=exp.Column(this=exp.to_identifier(c), table=exp.to_identifier("s")),
            )
            for c in cols
        ]

        merge_sql = (
            f"MERGE INTO {table} t USING {table}_staging s "
            f"ON ({on_expr.sql(dialect='oracle')}) "
            f"WHEN MATCHED THEN UPDATE SET {', '.join(s.sql(dialect='oracle') for s in set_exprs)} "
            f"WHEN NOT MATCHED THEN INSERT VALUES (s.*);"
        )
        return merge_sql

    return parsed.sql(dialect="oracle")
