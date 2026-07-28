"""Parses one CREATE TABLE / CREATE INDEX statement in a source dialect into
the `certified-ddl-v1` canonical model (`models.Table` / `models.Index`).

Uses `sqlglot.parse_one` as the real, dialect-aware parsing frontend -- the
same kind of "real compiler frontend, not string matching" choice this
repository already made for general-purpose code (JDK Tree API, Roslyn,
CPython AST, TS Compiler API in `engines/polyglot-route-engine`). Every
sqlglot AST shape this module does not explicitly recognize raises
`DialectError` rather than being approximated or dropped -- this is the
fail-closed boundary of certified-ddl-v1, verified against actual sqlglot
30.14.0 parse trees (see the AST dumps referenced in code review notes / the
README) rather than assumed.
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.expressions import DataType

from .dialects import IDENTIFIER_PATTERN
from .models import (
    CanonicalType,
    CanonicalTypeRef,
    CheckComparison,
    CheckConnector,
    CheckConstraint,
    CheckOperator,
    Column,
    ColumnDefault,
    Dialect,
    DefaultKind,
    DialectError,
    ForeignKey,
    Index,
    ReferentialAction,
    Table,
)

_IDENTIFIER_RE = re.compile(f"^{IDENTIFIER_PATTERN}$")

_TYPE_MAP: dict[DataType.Type, CanonicalType] = {  # type: ignore[valid-type]
    DataType.Type.BOOLEAN: CanonicalType.BOOLEAN,
    DataType.Type.SMALLINT: CanonicalType.INT16,
    DataType.Type.INT: CanonicalType.INT32,
    DataType.Type.BIGINT: CanonicalType.INT64,
    DataType.Type.DECIMAL: CanonicalType.DECIMAL,
    DataType.Type.CHAR: CanonicalType.CHAR,
    DataType.Type.VARCHAR: CanonicalType.VARCHAR,
    DataType.Type.NVARCHAR: CanonicalType.VARCHAR,
    DataType.Type.TEXT: CanonicalType.TEXT,
    DataType.Type.DATE: CanonicalType.DATE,
    DataType.Type.TIMESTAMP: CanonicalType.TIMESTAMP,
    # MySQL's plain TIMESTAMP, SQL Server's DATETIME/DATETIME2, and any
    # tz-aware TIMESTAMP form all collapse to the certified-ddl-v1 canonical
    # TIMESTAMP: this profile does not model timezone-awareness or the
    # DATETIME/DATETIME2 precision distinction separately. Documented in README.
    DataType.Type.TIMESTAMPTZ: CanonicalType.TIMESTAMP,
    DataType.Type.DATETIME: CanonicalType.TIMESTAMP,
    DataType.Type.DATETIME2: CanonicalType.TIMESTAMP,
    # SQL Server's BIT is its boolean type.
    DataType.Type.BIT: CanonicalType.BOOLEAN,
}

_CHECK_OPERATOR_MAP: dict[type, CheckOperator] = {
    exp.EQ: CheckOperator.EQ,
    exp.NEQ: CheckOperator.NE,
    exp.LT: CheckOperator.LT,
    exp.LTE: CheckOperator.LE,
    exp.GT: CheckOperator.GT,
    exp.GTE: CheckOperator.GE,
}

_REFERENTIAL_ACTION_MAP = {
    "CASCADE": ReferentialAction.CASCADE,
    "SET NULL": ReferentialAction.SET_NULL,
    "RESTRICT": ReferentialAction.RESTRICT,
    "NO ACTION": ReferentialAction.NO_ACTION,
}


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise DialectError(code, message)


def _plain_identifier(node: exp.Expression | None, what: str) -> str:
    _require(node is not None, "CERTIFIED_DDL_MISSING_IDENTIFIER", f"{what} is missing")
    ident = node
    if isinstance(ident, exp.Column):
        ident = ident.this
    if isinstance(ident, exp.Ordered):
        inner = ident.this
        return _plain_identifier(inner, what)
    _require(isinstance(ident, exp.Identifier), "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
              f"{what} is not a plain identifier ({type(ident).__name__})")
    assert isinstance(ident, exp.Identifier)  # narrows for mypy; _require already enforced this at runtime
    _require(not ident.args.get("quoted"), "CERTIFIED_DDL_QUOTED_IDENTIFIER",
              f"{what} {ident.this!r} uses a quoted/escaped identifier, which is outside certified-ddl-v1")
    name = ident.this
    _require(bool(_IDENTIFIER_RE.match(name)), "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
              f"{what} {name!r} is not a plain [A-Za-z_][A-Za-z0-9_]* identifier")
    return name


def _require_single_statement(sql: str, source_dialect: Dialect) -> exp.Expression:
    try:
        statements = [s for s in sqlglot.parse(sql, read=source_dialect.value) if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise DialectError("CERTIFIED_DDL_PARSE_FAILED", f"{source_dialect.value} parser rejected input: {exc}") from exc
    _require(len(statements) == 1, "CERTIFIED_DDL_MULTIPLE_STATEMENTS",
              f"certified-ddl-v1 accepts exactly one statement per call, found {len(statements)}")
    return statements[0]  # type: ignore[return-value]  # sqlglot's stub uses an internal "Expr" alias here


def _parse_type(data_type: exp.DataType) -> CanonicalTypeRef:
    sqlglot_type = data_type.this
    params = list(data_type.expressions or [])

    if sqlglot_type == DataType.Type.VARCHAR and params:
        first = params[0].this
        if isinstance(first, exp.Var) and str(first.this).upper() == "MAX":
            return CanonicalTypeRef(canonical_type=CanonicalType.TEXT)

    canonical = _TYPE_MAP.get(sqlglot_type)
    _require(canonical is not None, "CERTIFIED_DDL_UNSUPPORTED_TYPE",
              f"column type {sqlglot_type} is outside certified-ddl-v1's type allowlist")
    assert canonical is not None  # narrows for mypy; _require already enforced this at runtime

    def _param_int(index: int) -> int | None:
        if index >= len(params):
            return None
        literal = params[index].this
        _require(isinstance(literal, exp.Literal) and not literal.is_string, "CERTIFIED_DDL_UNSUPPORTED_TYPE_PARAM",
                  f"type parameter #{index + 1} of {sqlglot_type} is not a plain integer literal")
        return int(literal.this)

    if canonical == CanonicalType.DECIMAL:
        return CanonicalTypeRef(canonical_type=canonical, precision=_param_int(0), scale=_param_int(1))
    if canonical == CanonicalType.CHAR:
        return CanonicalTypeRef(canonical_type=canonical, length=_param_int(0))
    if canonical == CanonicalType.VARCHAR:
        return CanonicalTypeRef(canonical_type=canonical, length=_param_int(0))
    return CanonicalTypeRef(canonical_type=canonical)


def _parse_default(node: exp.Expression, type_ref: CanonicalTypeRef) -> ColumnDefault:
    if isinstance(node, exp.CurrentTimestamp):
        _require(type_ref.canonical_type == CanonicalType.TIMESTAMP, "CERTIFIED_DDL_DEFAULT_TYPE_MISMATCH",
                  "CURRENT_TIMESTAMP default is only supported on TIMESTAMP columns")
        return ColumnDefault(kind=DefaultKind.CURRENT_TIMESTAMP)
    if isinstance(node, exp.Boolean):
        return ColumnDefault(kind=DefaultKind.BOOLEAN, literal="true" if node.this else "false")
    if isinstance(node, exp.Literal):
        if node.is_string:
            return ColumnDefault(kind=DefaultKind.STRING, literal=str(node.this))
        # SQL Server has no boolean literal; source DDL for a BIT/BOOLEAN column
        # spells its default as the numeric literal 0 or 1 (see e.g. T-SQL
        # `active BIT NOT NULL DEFAULT 1`). Route it through DefaultKind.BOOLEAN
        # so dialects.render_default renders the correct target-dialect spelling
        # (TRUE/FALSE for Postgres/MySQL, 1/0 for Oracle/SQL Server) instead of
        # emitting a bare numeric literal that Postgres/MySQL would reject
        # against a real BOOLEAN column.
        if type_ref.canonical_type == CanonicalType.BOOLEAN and str(node.this) in ("0", "1"):
            return ColumnDefault(kind=DefaultKind.BOOLEAN, literal="true" if str(node.this) == "1" else "false")
        return ColumnDefault(kind=DefaultKind.NUMBER, literal=str(node.this))
    raise DialectError("CERTIFIED_DDL_UNSUPPORTED_DEFAULT",
                        f"DEFAULT expression of kind {type(node).__name__} is outside certified-ddl-v1 "
                        "(only literals and CURRENT_TIMESTAMP are supported)")


def _parse_check_comparison(node: exp.Expression) -> CheckComparison:
    operator = _CHECK_OPERATOR_MAP.get(type(node))
    _require(operator is not None, "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              f"CHECK comparison operator {type(node).__name__} is outside certified-ddl-v1")
    assert operator is not None  # narrows for mypy; _require already enforced this at runtime
    column = _plain_identifier(node.this, "CHECK left-hand column")
    literal = node.expression
    _require(isinstance(literal, exp.Literal), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              "CHECK right-hand side must be a plain literal")
    return CheckComparison(column=column, operator=operator, literal=str(literal.this),
                            literal_is_string=bool(literal.is_string))


def _parse_check(node: exp.Expression) -> tuple[tuple[CheckComparison, ...], CheckConnector | None]:
    if isinstance(node, (exp.And, exp.Or)):
        left, right = node.this, node.expression
        if isinstance(left, (exp.And, exp.Or)) or isinstance(right, (exp.And, exp.Or)):
            raise DialectError("CERTIFIED_DDL_MULTI_LEVEL_CHECK",
                                "certified-ddl-v1 supports only a single flat AND/OR of two plain comparisons, "
                                "not nested boolean expressions")
        connector = CheckConnector.AND if isinstance(node, exp.And) else CheckConnector.OR
        return (_parse_check_comparison(left), _parse_check_comparison(right)), connector
    return (_parse_check_comparison(node),), None


def _column_constraints(
    col_def: exp.ColumnDef, type_ref: CanonicalTypeRef
) -> tuple[bool, ColumnDefault | None, bool, bool, bool]:
    """Returns (nullable, default, auto_increment, primary_key_shorthand, unique_shorthand)."""
    nullable = True
    default: ColumnDefault | None = None
    auto_increment = False
    primary_key_shorthand = False
    unique_shorthand = False
    for constraint in col_def.constraints or []:
        kind = constraint.kind
        if isinstance(kind, exp.NotNullColumnConstraint):
            nullable = False
        elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
            primary_key_shorthand = True
            nullable = False
        elif isinstance(kind, (exp.AutoIncrementColumnConstraint, exp.GeneratedAsIdentityColumnConstraint)):
            auto_increment = True
        elif isinstance(kind, exp.DefaultColumnConstraint):
            default = _parse_default(kind.this, type_ref)
        elif isinstance(kind, exp.UniqueColumnConstraint) and kind.this is None:
            unique_shorthand = True
        else:
            raise DialectError("CERTIFIED_DDL_UNSUPPORTED_COLUMN_CONSTRAINT",
                                f"column constraint {type(kind).__name__} is outside certified-ddl-v1")
    return nullable, default, auto_increment, primary_key_shorthand, unique_shorthand


def parse_create_table(sql: str, source_dialect: Dialect) -> Table:
    statement = _require_single_statement(sql, source_dialect)
    _require(isinstance(statement, exp.Create) and statement.args.get("kind") == "TABLE",
              "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "certified-ddl-v1 only accepts a single CREATE TABLE statement")
    for flag in ("replace", "exists", "unique", "concurrently"):
        _require(not statement.args.get(flag), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
                  f"CREATE TABLE modifier {flag!r} is outside certified-ddl-v1")

    schema = statement.this
    _require(isinstance(schema, exp.Schema), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "malformed CREATE TABLE")
    table_ref = schema.this
    _require(isinstance(table_ref, exp.Table) and table_ref.args.get("db") is None and table_ref.args.get("catalog") is None,
              "CERTIFIED_DDL_QUALIFIED_TABLE_NAME",
              "certified-ddl-v1 requires an unqualified table name (no schema/catalog prefix)")
    table_name = _plain_identifier(table_ref.this, "table name")

    columns: list[Column] = []
    primary_key: list[str] = []
    unique_constraints: list[tuple[str, ...]] = []
    foreign_keys: list[ForeignKey] = []
    check_constraints: list[CheckConstraint] = []

    for item in schema.expressions:
        if isinstance(item, exp.ColumnDef):
            column_name = _plain_identifier(item.this, "column name")
            _require(item.kind is not None, "CERTIFIED_DDL_UNSUPPORTED_TABLE_ITEM",
                      f"column {column_name!r} is missing a type")
            assert item.kind is not None  # narrows for mypy; _require already enforced this at runtime
            type_ref = _parse_type(item.kind)
            nullable, default, auto_increment, pk_shorthand, unique_shorthand = _column_constraints(item, type_ref)
            columns.append(Column(name=column_name, type_ref=type_ref, nullable=nullable,
                                   default=default, auto_increment=auto_increment))
            if pk_shorthand:
                primary_key.append(column_name)
            if unique_shorthand:
                unique_constraints.append((column_name,))
        elif isinstance(item, exp.PrimaryKey):
            primary_key.extend(_plain_identifier(e, "PRIMARY KEY column") for e in item.expressions)
        elif isinstance(item, exp.Constraint):
            name = _plain_identifier(item.this, "constraint name") if item.this is not None else None
            _require(len(item.expressions) == 1, "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT",
                      "a named constraint must contain exactly one constraint clause")
            _apply_table_constraint(item.expressions[0], name, primary_key, unique_constraints,
                                     foreign_keys, check_constraints)
        elif isinstance(item, (exp.UniqueColumnConstraint, exp.ForeignKey, exp.CheckColumnConstraint)):
            # Unnamed table-level UNIQUE(...) / FOREIGN KEY(...) / CHECK(...), i.e. no
            # `CONSTRAINT <name>` prefix -- sqlglot represents these as bare nodes
            # directly in the table body rather than wrapped in exp.Constraint.
            _apply_table_constraint(item, None, primary_key, unique_constraints, foreign_keys, check_constraints)
        else:
            raise DialectError("CERTIFIED_DDL_UNSUPPORTED_TABLE_ITEM",
                                f"table-level item {type(item).__name__} is outside certified-ddl-v1 "
                                "(no partitioning, triggers, storage options, generated columns, or inheritance)")

    return Table(name=table_name, columns=tuple(columns), primary_key=tuple(primary_key),
                 unique_constraints=tuple(unique_constraints), foreign_keys=tuple(foreign_keys),
                 check_constraints=tuple(check_constraints))


def _apply_table_constraint(inner: exp.Expression, name: str | None, primary_key: list[str],
                             unique_constraints: list[tuple[str, ...]], foreign_keys: list[ForeignKey],
                             check_constraints: list[CheckConstraint]) -> None:
    if isinstance(inner, exp.PrimaryKey):
        primary_key.extend(_plain_identifier(e, "PRIMARY KEY column") for e in inner.expressions)
    elif isinstance(inner, exp.UniqueColumnConstraint):
        target = inner.this
        _require(isinstance(target, exp.Schema), "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT",
                  "table-level UNIQUE must list explicit columns")
        unique_constraints.append(tuple(_plain_identifier(e, "UNIQUE column") for e in target.expressions))
    elif isinstance(inner, exp.ForeignKey):
        columns = tuple(_plain_identifier(e, "FOREIGN KEY column") for e in inner.expressions)
        reference = inner.args.get("reference")
        _require(reference is not None, "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT", "FOREIGN KEY requires REFERENCES")
        assert reference is not None  # narrows for mypy; _require already enforced this at runtime
        ref_schema = reference.this
        ref_table_node = ref_schema.this if isinstance(ref_schema, exp.Schema) else ref_schema
        ref_table = _plain_identifier(ref_table_node.this if isinstance(ref_table_node, exp.Table) else ref_table_node,
                                       "FOREIGN KEY reference table")
        ref_columns = tuple(_plain_identifier(e, "FOREIGN KEY reference column")
                             for e in (ref_schema.expressions if isinstance(ref_schema, exp.Schema) else []))
        on_delete = ReferentialAction.NO_ACTION
        on_update = ReferentialAction.NO_ACTION
        for option in reference.args.get("options") or []:
            option_sql = str(option).upper()
            for prefix, attr in (("ON DELETE ", "on_delete"), ("ON UPDATE ", "on_update")):
                if option_sql.startswith(prefix):
                    action = _REFERENTIAL_ACTION_MAP.get(option_sql[len(prefix):].strip())
                    _require(action is not None, "CERTIFIED_DDL_UNSUPPORTED_REFERENTIAL_ACTION",
                              f"referential action {option_sql!r} is outside certified-ddl-v1")
                    assert action is not None  # narrows for mypy; _require already enforced this at runtime
                    if attr == "on_delete":
                        on_delete = action
                    else:
                        on_update = action
        foreign_keys.append(ForeignKey(columns=columns, ref_table=ref_table, ref_columns=ref_columns,
                                        on_delete=on_delete, on_update=on_update, name=name))
    elif isinstance(inner, exp.CheckColumnConstraint):
        comparisons, connector = _parse_check(inner.this)
        check_constraints.append(CheckConstraint(comparisons=comparisons, connector=connector, name=name))
    else:
        raise DialectError("CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT",
                            f"named constraint clause {type(inner).__name__} is outside certified-ddl-v1")


def parse_create_index(sql: str, source_dialect: Dialect) -> Index:
    statement = _require_single_statement(sql, source_dialect)
    _require(isinstance(statement, exp.Create) and statement.args.get("kind") == "INDEX",
              "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "certified-ddl-v1 only accepts a single CREATE INDEX statement here")
    for flag in ("replace", "exists", "concurrently"):
        _require(not statement.args.get(flag), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
                  f"CREATE INDEX modifier {flag!r} is outside certified-ddl-v1")
    index_node = statement.this
    _require(isinstance(index_node, exp.Index), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "malformed CREATE INDEX")
    index_name = _plain_identifier(index_node.this, "index name")
    table_node = index_node.args.get("table")
    _require(isinstance(table_node, exp.Table) and table_node.args.get("db") is None,
              "CERTIFIED_DDL_QUALIFIED_TABLE_NAME", "certified-ddl-v1 requires an unqualified table name")
    table_name = _plain_identifier(table_node.this, "index table name")
    params = index_node.args.get("params")
    _require(params is not None, "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "CREATE INDEX requires a column list")
    columns = tuple(_plain_identifier(c, "index column") for c in params.args.get("columns") or [])
    return Index(name=index_name, table=table_name, columns=columns, unique=bool(statement.args.get("unique")))
