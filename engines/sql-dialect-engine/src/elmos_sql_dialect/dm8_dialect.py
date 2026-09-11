"""Dameng (DM8) dialect lowering implementation.

AST-based SQL dialect lowering with zero regex:
- DDL: table creation, column type mappings (SERIAL/AUTO_INCREMENT -> IDENTITY(1,1),
  BOOLEAN -> BIT, TEXT -> CLOB, BYTEA/BLOB -> BLOB, VARCHAR(n), etc.), constraints (PK, FK, UNIQUE, CHECK).
- Sequences: CREATE SEQUENCE, seq.NEXTVAL, NEXTVAL('seq').
- DML/Query lowering: LIMIT/OFFSET standardizing, DUAL table support, functions
  (NOW() -> SYSDATE, IFNULL -> NVL, ILIKE -> REGEXP_LIKE or LOWER() LIKE LOWER(), INSTR, SUBSTR, DECODE).
- Upsert lowering: MySQL ON DUPLICATE KEY UPDATE / Postgres ON CONFLICT -> DM8 MERGE INTO AST.
"""

from __future__ import annotations

from sqlglot import exp, parse_one
from sqlglot.generator import Generator


class DM8Generator(Generator):
    """Custom AST generator for DM8 formatting."""

    def reference_sql(self, expression: exp.Reference) -> str:
        this = self.sql(expression, "this")
        if " (" in this:
            this = this.replace(" (", "(")
        expressions = self.expressions(expression, flat=True)
        expressions = f"({expressions})" if expressions else ""
        options = self.expressions(expression, key="options", flat=True, sep=" ")
        options = f" {options}" if options else ""
        return f"REFERENCES {this}{expressions}{options}"


class DM8ASTTransformer:
    """AST-based transformer for Dameng 8 (DM8) dialect."""

    def __init__(self, ilike_strategy: str = "regexp_like") -> None:
        self.ilike_strategy = ilike_strategy
        self.generator = DM8Generator()

    def transform_column_def(self, col: exp.ColumnDef) -> exp.ColumnDef:
        """Transform a ColumnDef node to DM8 data types and default constraints."""
        kind_sql = col.kind.sql().upper() if col.kind else ""
        is_serial = "SERIAL" in kind_sql
        is_bigserial = "BIGSERIAL" in kind_sql

        has_identity = False
        new_constraints: list[exp.ColumnConstraint] = []

        for c in col.constraints:
            k = c.kind
            if isinstance(k, exp.AutoIncrementColumnConstraint | exp.GeneratedAsIdentityColumnConstraint):
                has_identity = True
            elif "IDENTITY" in k.sql().upper():
                has_identity = True
            elif isinstance(k, exp.DefaultColumnConstraint):
                def_val = k.this.sql().upper()
                if def_val == "TRUE":
                    k.set("this", exp.Literal.number(1))
                elif def_val == "FALSE":
                    k.set("this", exp.Literal.number(0))
                elif "CURRENT_TIMESTAMP" in def_val or "NOW" in def_val:
                    k.set("this", exp.var("SYSDATE"))
                new_constraints.append(c)
            else:
                new_constraints.append(c)

        col.set("constraints", new_constraints)

        if is_bigserial:
            col.set("kind", exp.var("BIGINT IDENTITY(1, 1)"))
        elif is_serial:
            col.set("kind", exp.var("INT IDENTITY(1, 1)"))
        elif has_identity:
            base_type = kind_sql.replace("IDENTITY", "").strip() or "INT"
            col.set("kind", exp.var(f"{base_type} IDENTITY(1, 1)"))
        elif col.kind and col.kind.is_type("boolean", "bool"):
            col.set("kind", exp.var("BIT"))
        elif col.kind and col.kind.is_type("text", "longtext", "mediumtext", "json", "jsonb"):
            col.set("kind", exp.var("CLOB"))
        elif "VARCHAR(MAX)" in kind_sql or "NVARCHAR(MAX)" in kind_sql:
            col.set("kind", exp.var("CLOB"))
        elif col.kind and (
            col.kind.is_type("varbinary", "blob", "bytea")
            or kind_sql in ("BYTEA", "BLOB", "LONGBLOB", "MEDIUMBLOB", "IMAGE")
        ):
            col.set("kind", exp.var("BLOB"))
        elif "VARBINARY(MAX)" in kind_sql:
            col.set("kind", exp.var("BLOB"))
        elif col.kind and col.kind.is_type("timestamptz"):
            col.set("kind", exp.var("TIMESTAMP WITH TIME ZONE"))
        elif col.kind and col.kind.is_type("datetime"):
            col.set("kind", exp.var("TIMESTAMP"))
        elif "DATETIME2" in kind_sql:
            col.set("kind", exp.var("TIMESTAMP"))
        elif col.kind and col.kind.is_type("uuid"):
            col.set("kind", exp.var("VARCHAR(36)"))
        elif kind_sql in ("UUID", "UNIQUEIDENTIFIER"):
            col.set("kind", exp.var("VARCHAR(36)"))
        elif kind_sql == "DOUBLE PRECISION":
            col.set("kind", exp.var("DOUBLE"))

        return col

    def transform_function_node(self, node: exp.Expression) -> exp.Expression:
        """Transform function and expression AST nodes for DM8."""
        if isinstance(node, exp.Anonymous | exp.Func):
            name = node.name.upper()
            if name == "NOW":
                return exp.var("SYSDATE")
            if name in ("IFNULL", "ISNULL"):
                args = node.expressions if hasattr(node, "expressions") and node.expressions else [node.this]
                return exp.Anonymous(this="NVL", expressions=args)
            if name in ("GEN_RANDOM_UUID", "UUID", "NEWID"):
                return exp.Anonymous(this="RAWTOHEX", expressions=[exp.Anonymous(this="SYS_GUID")])
            if name in ("NEXTVAL", "CURRVAL") and node.expressions:
                first_expr = node.expressions[0]
                seq_name = first_expr.this if isinstance(first_expr, exp.Literal) else first_expr.sql()
                seq_name = seq_name.strip("'\"")
                return exp.Column(this=exp.var(name), table=exp.to_identifier(seq_name))

        if isinstance(node, exp.CurrentTimestamp):
            return exp.var("SYSTIMESTAMP")

        if isinstance(node, exp.Coalesce):
            args = [node.this, *list(node.expressions)]
            if len(args) == 2:
                return exp.Anonymous(this="NVL", expressions=args)

        if isinstance(node, exp.Uuid):
            return exp.Anonymous(this="RAWTOHEX", expressions=[exp.Anonymous(this="SYS_GUID")])

        if isinstance(node, exp.Substring):
            args = [node.this]
            if node.args.get("start"):
                args.append(node.args["start"])
            if node.args.get("length"):
                args.append(node.args["length"])
            return exp.Anonymous(this="SUBSTR", expressions=args)

        if isinstance(node, exp.ILike):
            if self.ilike_strategy == "lower":
                return exp.Like(
                    this=exp.Lower(this=node.this),
                    expression=exp.Lower(this=node.expression),
                )
            return exp.Anonymous(
                this="REGEXP_LIKE",
                expressions=[node.this, node.expression, exp.Literal.string("i")],
            )

        if isinstance(node, exp.Column):
            col_name = node.name.upper()
            if col_name in ("NEXTVAL", "CURRVAL") and node.table:
                return exp.Column(this=exp.var(col_name), table=node.args["table"])

        return node

    def lower_data_types(self, sql: str, source_dialect: str = "postgres") -> str:
        """Map data types from source dialect to DM8 equivalents via AST."""
        read_dialect = "mysql" if "AUTO_INCREMENT" in sql.upper() else source_dialect
        stripped = sql.strip().rstrip(";")

        is_full_create = stripped.upper().startswith("CREATE ")
        parse_target = stripped if is_full_create else f"CREATE TABLE _dummy ({stripped})"

        try:
            ast = parse_one(parse_target, read=read_dialect)
        except Exception:
            ast = parse_one(parse_target)

        def _xform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.ColumnDef):
                return self.transform_column_def(node)
            return node

        transformed = ast.transform(_xform)

        if is_full_create:
            return self.generator.generate(transformed)

        cols = transformed.this.expressions
        return ", ".join(self.generator.generate(c) for c in cols)

    def lower_ddl(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower DDL statements for DM8 via AST."""
        read_dialect = "mysql" if "AUTO_INCREMENT" in sql.upper() else source_dialect
        ast = parse_one(sql.strip(), read=read_dialect)

        if isinstance(ast, exp.Create):
            ast.set("exists", False)

        def _xform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.ColumnDef):
                return self.transform_column_def(node)
            return node

        transformed = ast.transform(_xform)
        return self.generator.generate(transformed) + ";"

    def lower_sequence(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower sequence creation and usage via AST."""
        stripped = sql.strip()
        has_semicolon = stripped.endswith(";")
        ast = parse_one(stripped, read=source_dialect)

        if isinstance(ast, exp.Create) and ast.kind.upper() == "SEQUENCE":
            ast.set("exists", False)
            out = self.generator.generate(ast)
            return f"{out};" if has_semicolon else out

        transformed = ast.transform(self.transform_function_node)
        out = self.generator.generate(transformed)
        return f"{out};" if has_semicolon else out

    def lower_functions(self, sql: str) -> str:
        """Lower built-in functions to DM8 equivalents via AST."""
        stripped = sql.strip()
        has_semicolon = stripped.endswith(";")
        try:
            ast = parse_one(stripped)
        except Exception:
            ast = parse_one(stripped, read="postgres")

        transformed = ast.transform(self.transform_function_node)
        out = self.generator.generate(transformed)
        return f"{out};" if has_semicolon else out

    def lower_limit_offset(self, sql: str) -> str:
        """Lower LIMIT/OFFSET clauses to DM8 standard `LIMIT count OFFSET offset` via AST."""
        stripped = sql.strip()
        has_semicolon = stripped.endswith(";")

        read_dialect: str | None = None
        upper = stripped.upper()
        if "TOP " in upper:
            read_dialect = "tsql"
        elif "LIMIT " in upper and "," in upper:
            read_dialect = "mysql"

        ast = parse_one(stripped, read=read_dialect) if read_dialect else parse_one(stripped)
        if isinstance(ast.args.get("limit"), exp.Fetch):
            fetch = ast.args["limit"]
            ast.set("limit", exp.Limit(expression=fetch.args["count"]))
        out = self.generator.generate(ast)
        return f"{out};" if has_semicolon else out

    def ensure_dual_table(self, sql: str) -> str:
        """Ensure constant/expression-only SELECT queries have FROM DUAL for DM8."""
        stripped = sql.strip()
        has_semicolon = stripped.endswith(";")
        ast = parse_one(stripped)

        if isinstance(ast, exp.Select) and not ast.args.get("from_"):
            ast.from_("DUAL", copy=False)

        out = self.generator.generate(ast)
        return f"{out};" if has_semicolon else out

    def lower_query(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower complete SELECT query to DM8 via AST."""
        stripped = sql.strip()
        has_semicolon = stripped.endswith(";")

        upper = stripped.upper()
        read_dialect: str | None = None
        if "TOP " in upper:
            read_dialect = "tsql"
        elif "LIMIT " in upper and "," in upper:
            read_dialect = "mysql"

        # Prefer generic parse so NOW() is Anonymous rather than forced to CurrentTimestamp
        try:
            ast = parse_one(stripped, read=read_dialect) if read_dialect else parse_one(stripped)
        except Exception:
            ast = parse_one(stripped, read=source_dialect)

        transformed = ast.transform(self.transform_function_node)

        if isinstance(transformed, exp.Select):
            if isinstance(transformed.args.get("limit"), exp.Fetch):
                fetch = transformed.args["limit"]
                transformed.set("limit", exp.Limit(expression=fetch.args["count"]))
            if not transformed.args.get("from_"):
                transformed.from_("DUAL", copy=False)

        out = self.generator.generate(transformed)
        return f"{out};" if has_semicolon else out


    def wrap_with_rownum(self, query: str, limit: int, offset: int = 0) -> str:
        """Wrap query using DM8 / Oracle ROWNUM pagination pattern."""
        clean = query.strip().rstrip(";")
        if offset > 0:
            max_r = offset + limit
            return (
                f"SELECT * FROM (SELECT inner_query.*, ROWNUM AS rnum FROM ({clean}) inner_query "
                f"WHERE ROWNUM <= {max_r}) WHERE rnum > {offset};"
            )
        return f"SELECT * FROM ({clean}) WHERE ROWNUM <= {limit};"

    def lower_upsert(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower MySQL ON DUPLICATE KEY UPDATE / Postgres ON CONFLICT to DM8 MERGE INTO AST."""
        read_dialect = "mysql" if "DUPLICATE" in sql.upper() else source_dialect
        try:
            ast = parse_one(sql.strip().rstrip(";"), read=read_dialect)
        except Exception:
            return sql

        if not isinstance(ast, exp.Insert):
            return sql

        conflict = ast.args.get("conflict")
        if not conflict:
            return sql

        table_name = ast.this.this.sql()
        cols = [col.name for col in ast.this.expressions]

        if isinstance(ast.expression, exp.Values) and ast.expression.expressions:
            val_tuple = ast.expression.expressions[0]
            vals = [v.sql() for v in val_tuple.expressions]
        else:
            return sql

        conflict_keys: list[str] = []
        if conflict.args.get("conflict_keys"):
            for k in conflict.args["conflict_keys"]:
                conflict_keys.append(k.this.name if isinstance(k, exp.Ordered) else k.name)
        if not conflict_keys:
            conflict_keys = [cols[0]]

        src_select_parts = [f"{val} AS {col}" for col, val in zip(cols, vals, strict=False)]
        src_subquery = f"SELECT {', '.join(src_select_parts)} FROM DUAL"

        on_conds = [f"{table_name}.{pk} = src.{pk}" for pk in conflict_keys]
        on_clause = " AND ".join(on_conds)

        src_cols_str = ", ".join(f"src.{c}" for c in cols)
        insert_clause = f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({src_cols_str})"

        action_str = str(conflict.args.get("action") or "").upper()
        if "NOTHING" in action_str:
            return f"MERGE INTO {table_name} USING ({src_subquery}) src ON ({on_clause}) {insert_clause};"

        def _repl_excluded(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Column) and node.table.upper() == "EXCLUDED":
                return exp.Column(this=node.this, table=exp.to_identifier("src"))
            if isinstance(node, exp.Anonymous) and node.name.upper() == "VALUES":
                return exp.Column(this=node.expressions[0], table=exp.to_identifier("src"))
            return node

        set_exprs: list[str] = []
        for eq in conflict.expressions:
            set_exprs.append(eq.transform(_repl_excluded).sql())

        update_clause = f"WHEN MATCHED THEN UPDATE SET {', '.join(set_exprs)}"
        return f"MERGE INTO {table_name} USING ({src_subquery}) src ON ({on_clause}) {update_clause} {insert_clause};"


class DM8DialectLowerer:
    """Dedicated SQL dialect lowerer for Dameng 8 (DM8)."""

    def __init__(self, ilike_strategy: str = "regexp_like") -> None:
        self.ilike_strategy = ilike_strategy
        self.transformer = DM8ASTTransformer(ilike_strategy=ilike_strategy)

    def lower_data_types(self, sql: str, source_dialect: str = "postgres") -> str:
        return self.transformer.lower_data_types(sql, source_dialect=source_dialect)

    def lower_ddl(self, sql: str, source_dialect: str = "postgres") -> str:
        return self.transformer.lower_ddl(sql, source_dialect=source_dialect)

    def lower_sequence(self, sql: str, source_dialect: str = "postgres") -> str:
        return self.transformer.lower_sequence(sql, source_dialect=source_dialect)

    def lower_functions(self, sql: str) -> str:
        return self.transformer.lower_functions(sql)

    def lower_limit_offset(self, sql: str) -> str:
        return self.transformer.lower_limit_offset(sql)

    def ensure_dual_table(self, sql: str) -> str:
        return self.transformer.ensure_dual_table(sql)

    def lower_query(self, sql: str, source_dialect: str = "postgres") -> str:
        return self.transformer.lower_query(sql, source_dialect=source_dialect)

    def wrap_with_rownum(self, query: str, limit: int, offset: int = 0) -> str:
        return self.transformer.wrap_with_rownum(query, limit=limit, offset=offset)

    def lower_upsert(self, sql: str, source_dialect: str = "postgres") -> str:
        return self.transformer.lower_upsert(sql, source_dialect=source_dialect)


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------

_DEFAULT_LOWERER = DM8DialectLowerer()


def lower_dm8_ddl(sql: str, source_dialect: str = "postgres") -> str:
    """Lower source DDL to DM8 dialect."""
    return _DEFAULT_LOWERER.lower_ddl(sql, source_dialect=source_dialect)


def lower_dm8_query(sql: str, source_dialect: str = "postgres") -> str:
    """Lower source query to DM8 dialect."""
    return _DEFAULT_LOWERER.lower_query(sql, source_dialect=source_dialect)


def lower_dm8_sequence(sql: str, source_dialect: str = "postgres") -> str:
    """Lower sequence definition or access to DM8 dialect."""
    return _DEFAULT_LOWERER.lower_sequence(sql, source_dialect=source_dialect)


def lower_dm8_upsert(sql: str, source_dialect: str = "postgres") -> str:
    """Lower upsert statements to DM8 MERGE INTO."""
    return _DEFAULT_LOWERER.lower_upsert(sql, source_dialect=source_dialect)

