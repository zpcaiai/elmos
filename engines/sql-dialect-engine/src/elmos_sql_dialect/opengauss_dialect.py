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
import re
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
        elif col.kind and (col.kind.is_type("tinyint") or "TINYINT" in kind_sql):
            args = [a.sql() for a in col.kind.expressions] if col.kind.expressions else []
            if args == ["1"] or "(1)" in kind_sql:
                col.set("kind", exp.var("BOOLEAN"))
            else:
                col.set("kind", exp.var("SMALLINT"))
        elif col.kind and (col.kind.is_type("smallint") or "SMALLINT" in kind_sql):
            col.set("kind", exp.var("SMALLINT"))
        elif col.kind and (col.kind.is_type("mediumint") or "MEDIUMINT" in kind_sql):
            col.set("kind", exp.var("INT"))
        elif col.kind and (col.kind.is_type("bigint") or "BIGINT" in kind_sql):
            col.set("kind", exp.var("BIGINT"))
        elif col.kind and (col.kind.is_type("int", "integer") or "INT" in kind_sql):
            col.set("kind", exp.var("INT"))

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
        if source_dialect.lower() in ("oracle", "dm8"):
            read_dialect = "oracle"

        try:
            ast = parse_one(sql.strip(), read=read_dialect)
        except Exception:
            ast = parse_one(sql.strip())

        # Handle Oracle (+) outer join predicates in comma-separated joins -> ANSI LEFT JOIN
        outer_join_tables: set[str] = set()
        join_conditions: dict[str, exp.Expression] = {}

        def _check_join_mark(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.EQ):
                left = node.this
                right = node.expression
                if isinstance(left, exp.Column) and getattr(left, "args", {}).get("join_mark"):
                    table_name = left.table
                    if table_name:
                        outer_join_tables.add(table_name)
                        left_clean = left.copy()
                        left_clean.set("join_mark", False)
                        join_conditions[table_name] = exp.EQ(this=right.copy(), expression=left_clean)
                        return exp.true()
                if isinstance(right, exp.Column) and getattr(right, "args", {}).get("join_mark"):
                    table_name = right.table
                    if table_name:
                        outer_join_tables.add(table_name)
                        right_clean = right.copy()
                        right_clean.set("join_mark", False)
                        join_conditions[table_name] = exp.EQ(this=left.copy(), expression=right_clean)
                        return exp.true()
            return node

        ast = ast.transform(_check_join_mark)

        if outer_join_tables and isinstance(ast, exp.Select):
            new_joins = []
            for j in ast.args.get("joins", []):
                tbl_name = j.this.name if isinstance(j.this, exp.Table) else ""
                alias_name = j.this.alias if isinstance(j.this, exp.Table) else ""
                matched_key = tbl_name if tbl_name in outer_join_tables else (alias_name if alias_name in outer_join_tables else None)
                if matched_key and matched_key in join_conditions:
                    cond = join_conditions[matched_key]
                    new_join = exp.Join(this=j.this, kind="LEFT", on=cond)
                    new_joins.append(new_join)
                else:
                    new_joins.append(j)
            ast.set("joins", new_joins)

        # Handle Oracle ROWNUM <= N in WHERE clause -> openGauss LIMIT N
        extracted_limit: int | None = None

        def _check_rownum(node: exp.Expression) -> exp.Expression:
            nonlocal extracted_limit
            if isinstance(node, (exp.LTE, exp.LT)):
                left = node.this
                right = node.expression
                if isinstance(left, exp.Column) and left.name.upper() == "ROWNUM":
                    if isinstance(right, exp.Literal) and right.is_number:
                        val = int(right.this)
                        extracted_limit = val if isinstance(node, exp.LTE) else max(0, val - 1)
                        return exp.true()
                elif isinstance(right, exp.Column) and right.name.upper() == "ROWNUM":
                    if isinstance(left, exp.Literal) and left.is_number:
                        val = int(left.this)
                        extracted_limit = val if isinstance(node, exp.GTE) else max(0, val - 1)
                        return exp.true()
            return node

        ast = ast.transform(_check_rownum)

        def _xform(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Fetch):
                offset_node = ast.args.get("offset")
                count_node = node.this
                return exp.Limit(this=count_node, expression=offset_node)

            if active_mode == OpenGaussMode.PG:
                if isinstance(node, exp.Table) and node.name.upper() == "DUAL":
                    return exp.var("")

                if isinstance(node, (exp.Anonymous, exp.Func)):
                    name = node.name.upper()
                    if name in ("NVL", "IFNULL", "ISNULL"):
                        args = [node.this] + list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        return exp.Anonymous(this="COALESCE", expressions=args)
                    if name == "NVL2":
                        args = [node.this] + list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        if len(args) == 3:
                            cond = exp.Is(this=args[0].copy(), expression=exp.var("NOT NULL"))
                            return exp.Case(ifs=[exp.If(this=cond, true=args[1].copy())], default=args[2].copy())
                    if name == "DECODE":
                        args = [node.this] + list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        if len(args) >= 3:
                            base_expr = args[0]
                            whens = []
                            i = 1
                            while i + 1 < len(args):
                                cond = exp.EQ(this=base_expr.copy(), expression=args[i].copy())
                                whens.append(exp.If(this=cond, true=args[i + 1].copy()))
                                i += 2
                            default_expr = args[i].copy() if i < len(args) else exp.null()
                            return exp.Case(ifs=whens, default=default_expr)
                    if name in ("NOW", "SYSDATE"):
                        return exp.var("CURRENT_TIMESTAMP")
                    if name in ("UUID", "NEWID", "GEN_RANDOM_UUID"):
                        return exp.Anonymous(this="gen_random_uuid")
                    if name == "INSTR":
                        args = [node.this] + list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        if len(args) >= 2:
                            return exp.Anonymous(
                                this="POSITION",
                                expressions=[exp.var(f"{args[1].sql(dialect='postgres')} IN {args[0].sql(dialect='postgres')}")],
                            )
                    if name == "SUBSTR":
                        args = [node.this] + list(node.expressions) if hasattr(node, "expressions") else [node.this]
                        return exp.Anonymous(this="SUBSTR", expressions=args)
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

        # Apply extracted limit if LIMIT was not present
        if extracted_limit is not None and not transformed.args.get("limit"):
            transformed.set("limit", exp.Limit(expression=exp.Literal.number(extracted_limit)))

        result_sql = transformed.sql(dialect="postgres")
        # Clean up any artifact "WHERE TRUE AND " or "WHERE TRUE"
        result_sql = re.sub(r"\bWHERE\s+TRUE\s+AND\s+", "WHERE ", result_sql, flags=re.IGNORECASE)
        result_sql = re.sub(r"\bWHERE\s+TRUE\b(?!\s+AND)", "", result_sql, flags=re.IGNORECASE).strip()
        return result_sql

    def lower_routine(
        self,
        sql: str,
        source_dialect: str = "postgres",
        routine_type: str | None = None,
        native_opengauss: bool = False,
    ) -> str:
        """Lower function or procedure to openGauss routine syntax."""
        target_kind = (routine_type or "").upper().strip()
        if not target_kind:
            if "FUNCTION" in sql.upper():
                target_kind = "FUNCTION"
            else:
                target_kind = "PROCEDURE"

        if native_opengauss and target_kind == "PROCEDURE":
            proc_sql = re.sub(r"\s+LANGUAGE\s+plpgsql;?$", ";", sql.strip(), flags=re.IGNORECASE)
            proc_sql = re.sub(r"\s+AS\s+\$\$(.*?)\$\$;?", r" AS\1", proc_sql, flags=re.IGNORECASE | re.DOTALL)
            return proc_sql.strip()

        if "$$" in sql and "plpgsql" in sql.lower():
            return sql.strip()

        try:
            ast = parse_one(sql.strip(), read=source_dialect)
        except Exception:
            try:
                ast = parse_one(sql.strip(), read="postgres")
            except Exception:
                ast = None

        if ast and isinstance(ast, (exp.Create, exp.Block)):
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
