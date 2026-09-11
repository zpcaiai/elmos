"""openGauss dialect lowering implementation.

AST-based SQL dialect lowering with zero regex:
- DDL: table creation with `DISTRIBUTE BY HASH(...)` (based on primary key or first column),
  storage attributes `WITH (ORIENTATION = ROW/COLUMN)`.
- Types: SERIAL/BIGSERIAL, BYTEA, TEXT, NUMERIC, TIMESTAMPTZ, JSONB, and conversions
  from Oracle (NUMBER, VARCHAR2, CLOB, BLOB), MySQL (AUTO_INCREMENT, TINYINT, DATETIME),
  and T-SQL (IDENTITY, UNIQUEIDENTIFIER, etc.) via ColumnDef AST transformation.
- Modes: PG mode (PostgreSQL compatible), A mode (Oracle compatible), B mode (MySQL compatible).
- Functions & Procedures: AST-based routine lowering with `AS $$ ... $$ LANGUAGE plpgsql;`.
"""

from __future__ import annotations

import logging
from enum import Enum

from sqlglot import exp, parse_one
from sqlglot.generator import Generator

logger = logging.getLogger(__name__)


class OpenGaussMode(str, Enum):
    """openGauss compatibility modes."""

    PG = "PG"  # PostgreSQL compatibility (default)
    A = "A"  # Oracle compatibility mode
    B = "B"  # MySQL compatibility mode


class OpenGaussGenerator(Generator):
    """Custom AST generator for openGauss formatting."""

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


class OpenGaussASTTransformer:
    """AST-based transformer for openGauss / MogDB dialect."""

    def __init__(self, mode: OpenGaussMode = OpenGaussMode.PG) -> None:
        self.mode = mode
        self.generator = OpenGaussGenerator()

    def transform_column_def(
        self, col: exp.ColumnDef, source_dialect: str = "postgres"
    ) -> exp.ColumnDef:
        """Transform a ColumnDef node to openGauss data types and constraints."""
        kind_sql = col.kind.sql().upper() if col.kind else ""

        has_auto_increment = False
        new_constraints: list[exp.ColumnConstraint] = []

        for c in col.constraints:
            k = c.kind
            if isinstance(k, exp.AutoIncrementColumnConstraint | exp.GeneratedAsIdentityColumnConstraint):
                has_auto_increment = True
            elif "AUTO_INCREMENT" in k.sql().upper() or "IDENTITY" in k.sql().upper():
                has_auto_increment = True
            else:
                new_constraints.append(c)

        col.set("constraints", new_constraints)

        # 1. Serial / Auto Increment / Identity
        if "BIGSERIAL" in kind_sql or (has_auto_increment and "BIGINT" in kind_sql):
            col.set("kind", exp.var("BIGSERIAL"))
        elif "SERIAL" in kind_sql or has_auto_increment:
            col.set("kind", exp.var("SERIAL"))
        elif "IDENTITY" in kind_sql:
            col.set("kind", exp.var("SERIAL"))

        # 2. Text / String types
        elif col.kind and col.kind.is_type("text", "longtext", "mediumtext", "clob", "nclob"):
            col.set("kind", exp.var("TEXT"))
        elif "VARCHAR(MAX)" in kind_sql or "NVARCHAR(MAX)" in kind_sql:
            col.set("kind", exp.var("TEXT"))
        elif "TINYTEXT" in kind_sql:
            col.set("kind", exp.var("VARCHAR(255)"))
        elif col.kind and col.kind.is_type("varchar2", "nvarchar2"):
            if self.mode != OpenGaussMode.A:
                args = col.kind.expressions
                col.set("kind", exp.DataType.build("VARCHAR", expressions=args) if args else exp.var("VARCHAR"))

        # 3. Binary / LOB types -> BYTEA
        elif col.kind and (
            col.kind.is_type("bytea", "blob", "longblob", "mediumblob", "tinyblob", "varbinary")
            or kind_sql in ("BLOB", "LONGBLOB", "MEDIUMBLOB", "TINYBLOB", "RAW", "IMAGE")
        ):
            col.set("kind", exp.var("BYTEA"))
        elif "VARBINARY(MAX)" in kind_sql:
            col.set("kind", exp.var("BYTEA"))

        # 4. Numeric types
        elif col.kind and (col.kind.is_type("number", "decimal") or "NUMBER" in kind_sql or "DECIMAL" in kind_sql):
            args = col.kind.expressions
            if args:
                col.set("kind", exp.var(f"NUMERIC({', '.join(a.sql() for a in args)})"))
            else:
                col.set("kind", exp.var("NUMERIC"))
        elif kind_sql == "DOUBLE":
            col.set("kind", exp.var("DOUBLE PRECISION"))
        elif kind_sql == "BINARY_DOUBLE":
            col.set("kind", exp.var("DOUBLE PRECISION"))
        elif kind_sql == "BINARY_FLOAT":
            col.set("kind", exp.var("REAL"))
        elif kind_sql == "TINYINT":
            col.set("kind", exp.var("SMALLINT"))

        # 5. Date / Time types
        elif col.kind and col.kind.is_type("datetime"):
            col.set("kind", exp.var("TIMESTAMP"))
        elif "DATETIME2" in kind_sql:
            col.set("kind", exp.var("TIMESTAMP"))

        # 6. UUID / Boolean
        elif col.kind and col.kind.is_type("uuid"):
            col.set("kind", exp.var("UUID"))
        elif kind_sql in ("UUID", "UNIQUEIDENTIFIER"):
            col.set("kind", exp.var("UUID"))
        elif (col.kind and col.kind.is_type("boolean", "bool")) or kind_sql == "BIT":
            col.set("kind", exp.var("BOOLEAN"))

        return col

    def extract_distribution_key(self, ast: exp.Create) -> str:
        """Extract primary key column or first column from CREATE TABLE AST."""
        if not isinstance(ast.this, exp.Schema):
            return "id"

        schema = ast.this
        # 1. Table-level primary key: PRIMARY KEY (col1, col2, ...)
        for expr in schema.expressions:
            if isinstance(expr, exp.PrimaryKey):
                cols = [c.name for c in expr.expressions]
                if cols:
                    return ", ".join(cols)

        # 2. Column-level primary key: col TYPE PRIMARY KEY
        for expr in schema.expressions:
            if isinstance(expr, exp.ColumnDef):
                for c in expr.constraints:
                    if isinstance(c.kind, exp.PrimaryKeyColumnConstraint):
                        return expr.name

        # 3. Fallback to first column defined
        for expr in schema.expressions:
            if isinstance(expr, exp.ColumnDef):
                return expr.name

        return "id"

    def lower_data_types(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower data types from other engines to native openGauss equivalents via AST."""
        stripped = sql.strip().rstrip(";")
        is_full_create = stripped.upper().startswith("CREATE ")
        read_dialect = "mysql" if "AUTO_INCREMENT" in sql.upper() else source_dialect

        parse_target = stripped if is_full_create else f"CREATE TABLE _dummy ({stripped})"
        try:
            ast = parse_one(parse_target, read=read_dialect)
        except Exception:
            try:
                ast = parse_one(parse_target)
            except Exception:
                return sql

        def _xform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.ColumnDef):
                return self.transform_column_def(node, source_dialect)
            return node

        transformed = ast.transform(_xform)

        if is_full_create:
            return self.generator.generate(transformed)

        if isinstance(transformed.this, exp.Schema):
            cols = transformed.this.expressions
            return ", ".join(self.generator.generate(c) for c in cols)
        return self.generator.generate(transformed)

    def lower_ddl(
        self,
        sql: str,
        source_dialect: str = "postgres",
        orientation: str = "ROW",
        distribute_by: str | None = None,
        standalone: bool = False,
    ) -> str:
        """Lower table creation DDL to openGauss with orientation and distribution attributes via AST."""
        read_dialect = "mysql" if "AUTO_INCREMENT" in sql.upper() else source_dialect
        ast = parse_one(sql.strip().rstrip(";"), read=read_dialect)

        if isinstance(ast, exp.Create):
            ast.set("exists", False)
            dist_key = distribute_by if distribute_by else self.extract_distribution_key(ast)
        else:
            dist_key = distribute_by or "id"

        def _xform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.ColumnDef):
                return self.transform_column_def(node, source_dialect)
            return node

        transformed = ast.transform(_xform)
        base_sql = self.generator.generate(transformed).strip().rstrip(";")

        orientation_clause = f"WITH (ORIENTATION = {orientation.upper()})"
        if standalone:
            return f"{base_sql} {orientation_clause};"
        distribute_clause = f"DISTRIBUTE BY HASH({dist_key})"

        return f"{base_sql} {orientation_clause} {distribute_clause};"

    def lower_query(
        self,
        sql: str,
        source_dialect: str = "postgres",
        mode: str | OpenGaussMode | None = None,
    ) -> str:
        """Lower SELECT/DML queries to openGauss under specified compatibility mode via AST."""
        active_mode = OpenGaussMode(mode) if mode else self.mode
        read_dialect = "mysql" if ("LIMIT " in sql.upper() and "," in sql) else source_dialect

        ast = parse_one(sql.strip(), read=read_dialect)

        def _xform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Fetch):
                offset_node = ast.args.get("offset")
                count_node = node.this
                return exp.Limit(this=count_node, expression=offset_node)

            if active_mode == OpenGaussMode.PG:
                if isinstance(node, exp.Table) and node.name.upper() == "DUAL":
                    return exp.var("")

                if isinstance(node, exp.Anonymous | exp.Func):
                    name = node.name.upper()
                    if name in ("NVL", "IFNULL", "ISNULL"):
                        args = [node.this] + list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        return exp.Anonymous(this="COALESCE", expressions=args)
                    if name in ("NOW", "SYSDATE"):
                        return exp.var("CURRENT_TIMESTAMP")
                    if name in ("UUID", "NEWID"):
                        return exp.Anonymous(this="gen_random_uuid")
                    if name == "GROUP_CONCAT":
                        args = list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        delim = exp.Literal.string(",")
                        return exp.Anonymous(this="STRING_AGG", expressions=[args[0], delim])

            elif active_mode == OpenGaussMode.A:
                if isinstance(node, exp.Coalesce):
                    args = [node.this, *list(node.expressions)]
                    if len(args) == 2:
                        return exp.Anonymous(this="NVL", expressions=args)

            elif active_mode == OpenGaussMode.B:
                if isinstance(node, exp.Coalesce):
                    args = [node.this, *list(node.expressions)]
                    return exp.Anonymous(this="IFNULL", expressions=args)

            return node

        transformed = ast.transform(_xform)
        return transformed.sql(dialect="postgres")

    def lower_routine(
        self,
        sql: str,
        source_dialect: str = "postgres",
        routine_type: str | None = None,
    ) -> str:
        """Lower function or procedure to openGauss `$$` envelope with `LANGUAGE plpgsql;`."""
        if "$$" in sql and "plpgsql" in sql.lower():
            return sql.strip()

        try:
            ast = parse_one(sql.strip(), read=source_dialect)
        except Exception:
            try:
                ast = parse_one(sql.strip(), read="postgres")
            except Exception:
                ast = None

        target_kind = (routine_type or "").upper().strip()
        if not target_kind:
            if "FUNCTION" in sql.upper():
                target_kind = "FUNCTION"
            else:
                target_kind = "PROCEDURE"

        if ast and isinstance(ast, exp.Create | exp.Block):
            create_node = ast if isinstance(ast, exp.Create) else ast.find(exp.Create)
            if create_node:
                fn_node = create_node.find(exp.UserDefinedFunction)
                fn_sig = fn_node.sql(dialect="postgres") if fn_node else "unnamed()"
                ret_node = create_node.find(exp.ReturnsProperty)
                ret_type = ret_node.this.sql(dialect="postgres") if ret_node else "VOID"

                body_sql = ""
                if create_node.expression:
                    body_sql = create_node.expression.sql(dialect="postgres")
                elif isinstance(ast, exp.Block):
                    statements = [
                        e.sql(dialect="postgres") for e in ast.expressions if not isinstance(e, exp.Create)
                    ]
                    body_sql = ";\n    ".join(statements)

                if not body_sql.strip():
                    body_sql = "NULL;"

                header = f"CREATE OR REPLACE {target_kind} {fn_sig}"
                if target_kind == "FUNCTION":
                    header = f"{header} RETURNS {ret_type}"

                return (
                    f"{header}\n"
                    f"AS $$\n"
                    f"BEGIN\n"
                    f"    {body_sql};\n"
                    f"END;\n"
                    f"$$ LANGUAGE plpgsql;"
                )

        cleaned = sql.strip().rstrip(";")
        if "LANGUAGE plpgsql" not in cleaned:
            cleaned = f"{cleaned} LANGUAGE plpgsql;"
        return cleaned


class OpenGaussDialectLowerer:
    """Dedicated SQL dialect lowerer for openGauss / MogDB."""

    def __init__(self, mode: OpenGaussMode = OpenGaussMode.PG) -> None:
        self.mode = mode
        self.transformer = OpenGaussASTTransformer(mode=mode)

    def lower_data_types(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower data types from other engines to native openGauss equivalents via AST."""
        return self.transformer.lower_data_types(sql, source_dialect=source_dialect)

    def extract_distribution_key(self, sql: str) -> str:
        """Detect primary key or first column to use as openGauss hash distribution key."""
        try:
            ast = parse_one(sql)
            if isinstance(ast, exp.Create):
                return self.transformer.extract_distribution_key(ast)
        except Exception as err:
            logger.debug("Failed to extract distribution key via AST: %s", err)
        return "id"

    def lower_ddl(
        self,
        sql: str,
        source_dialect: str = "postgres",
        orientation: str = "ROW",
        distribute_by: str | None = None,
        standalone: bool = False,
    ) -> str:
        """Lower table creation DDL to openGauss with orientation and distribution attributes."""
        return self.transformer.lower_ddl(
            sql,
            source_dialect=source_dialect,
            orientation=orientation,
            distribute_by=distribute_by,
            standalone=standalone,
        )

    def lower_create_table(
        self,
        sql: str,
        source_dialect: str = "postgres",
        orientation: str = "ROW",
        distribute_column: str | None = None,
    ) -> str:
        """Alias for lower_ddl."""
        return self.lower_ddl(
            sql,
            source_dialect=source_dialect,
            orientation=orientation,
            distribute_by=distribute_column,
        )

    def lower_query(
        self,
        sql: str,
        source_dialect: str = "postgres",
        mode: str | OpenGaussMode | None = None,
    ) -> str:
        """Lower SELECT/DML queries to openGauss in specified compatibility mode."""
        return self.transformer.lower_query(sql, source_dialect=source_dialect, mode=mode)

    def lower_function(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower function declaration to openGauss `$$` envelope with `LANGUAGE plpgsql;`."""
        return self.transformer.lower_routine(sql, source_dialect=source_dialect, routine_type="FUNCTION")

    def lower_procedure(self, sql: str, source_dialect: str = "postgres") -> str:
        """Lower procedure declaration to openGauss `$$` envelope with `LANGUAGE plpgsql;`."""
        return self.transformer.lower_routine(sql, source_dialect=source_dialect, routine_type="PROCEDURE")

    def lower_routine(
        self,
        sql: str,
        source_dialect: str = "postgres",
        routine_type: str | None = None,
    ) -> str:
        """Lower function or procedure to openGauss plpgsql format."""
        return self.transformer.lower_routine(sql, source_dialect=source_dialect, routine_type=routine_type)


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------

_DEFAULT_LOWERER = OpenGaussDialectLowerer()


def lower_opengauss_ddl(
    sql: str,
    source_dialect: str = "postgres",
    orientation: str = "ROW",
    distribute_by: str | None = None,
    standalone: bool = False,
) -> str:
    """Lower DDL statement to openGauss with ORIENTATION and DISTRIBUTE BY attributes."""
    return _DEFAULT_LOWERER.lower_ddl(
        sql,
        source_dialect=source_dialect,
        orientation=orientation,
        distribute_by=distribute_by,
        standalone=standalone,
    )


def lower_opengauss_query(
    sql: str,
    source_dialect: str = "postgres",
    mode: str = "PG",
) -> str:
    """Lower query to openGauss under specified compatibility mode."""
    return _DEFAULT_LOWERER.lower_query(sql, source_dialect=source_dialect, mode=mode)


def lower_opengauss_routine(sql: str, source_dialect: str = "postgres") -> str:
    """Lower function or procedure to openGauss plpgsql envelope."""
    return _DEFAULT_LOWERER.lower_routine(sql, source_dialect=source_dialect)
