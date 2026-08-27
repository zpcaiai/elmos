"""Parses certified DDL statements in a source dialect into canonical models.

CREATE TABLE / CREATE INDEX use the `certified-ddl-v1` model; ALTER TABLE,
DROP TABLE, and CREATE SCHEMA have their own narrow profile models.

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
from collections.abc import Mapping
from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.expressions import DataType
from sqlglot.tokens import Tokenizer

from .dialects import IDENTIFIER_PATTERN
from .models import (
    AddColumn,
    AddConstraint,
    AlterAction,
    AlterTable,
    CanonicalType,
    CanonicalTypeRef,
    CheckBooleanExpression,
    CheckComparison,
    CheckConnector,
    CheckConstraint,
    CheckExpression,
    CheckIntervalUnit,
    CheckLiteral,
    CheckNotExpression,
    CheckOperator,
    CheckValueExpression,
    CheckValueFunction,
    CheckValueOperator,
    Column,
    ColumnDefault,
    DefaultKind,
    Dialect,
    DialectError,
    DmlAggregate,
    DmlAggregateFunction,
    DmlCoalesce,
    DmlColumn,
    DmlCurrentTimestamp,
    DmlExpression,
    DmlJoin,
    DmlJoinCondition,
    DmlLiteral,
    DmlPredicate,
    DropColumn,
    DropConstraint,
    DropTable,
    ForeignKey,
    Index,
    IndexColumn,
    InsertLiteral,
    InsertSelectStatement,
    InsertStatement,
    ReferentialAction,
    RenameColumn,
    Schema,
    Table,
    UpdateAssignment,
    UpdateStatement,
)

_IDENTIFIER_RE = re.compile(f"^{IDENTIFIER_PATTERN}$")
_NUMERIC_LITERAL_RE = re.compile(r"-?(?:0|[0-9]+)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")

_TYPE_MAP: dict[DataType.Type, CanonicalType] = {  # type: ignore[valid-type]
    DataType.Type.BOOLEAN: CanonicalType.BOOLEAN,
    DataType.Type.SMALLINT: CanonicalType.INT16,
    DataType.Type.INT: CanonicalType.INT32,
    DataType.Type.BIGINT: CanonicalType.INT64,
    # DOUBLE is the common IEEE-754 binary64 family. FLOAT is deliberately
    # not included: MySQL's FLOAT is binary32 while other vendors commonly
    # default it to binary64, so the spelling alone cannot establish width.
    DataType.Type.DOUBLE: CanonicalType.FLOAT64,
    # Narrower or unsigned vendor integers widen to the smallest canonical
    # integer that holds their entire documented range, so no value is ever
    # narrowed: TINYINT is -128..127 and TINYINT UNSIGNED 0..255 (both inside
    # INT16); MEDIUMINT is +-8388607 and its unsigned form 0..16777215 (inside
    # INT32); SMALLINT UNSIGNED is 0..65535 (INT32); INT UNSIGNED is
    # 0..4294967295 (INT64). BIGINT UNSIGNED reaches 18446744073709551615,
    # which no canonical integer holds -- handled explicitly in _parse_type.
    DataType.Type.TINYINT: CanonicalType.INT16,
    DataType.Type.UTINYINT: CanonicalType.INT16,
    DataType.Type.USMALLINT: CanonicalType.INT32,
    DataType.Type.MEDIUMINT: CanonicalType.INT32,
    DataType.Type.UMEDIUMINT: CanonicalType.INT32,
    DataType.Type.UINT: CanonicalType.INT64,
    DataType.Type.DECIMAL: CanonicalType.DECIMAL,
    DataType.Type.CHAR: CanonicalType.CHAR,
    # SQL Server's NCHAR is its Unicode fixed-length type; the canonical CHAR
    # is Unicode-capable by definition (see dialects.render_type, which emits
    # NCHAR/NVARCHAR on SQL Server precisely so Unicode survives the route).
    DataType.Type.NCHAR: CanonicalType.CHAR,
    DataType.Type.VARCHAR: CanonicalType.VARCHAR,
    DataType.Type.NVARCHAR: CanonicalType.VARCHAR,
    DataType.Type.TEXT: CanonicalType.TEXT,
    # MySQL's four TEXT sizes are all "unbounded character data" as far as
    # certified-ddl-v1 models it. The canonical TEXT renders as the *largest*
    # of each vendor's forms (LONGTEXT on MySQL, NVARCHAR(MAX) on SQL Server,
    # CLOB on Oracle) so a translation is always a widening, never a silent
    # size reduction.
    DataType.Type.LONGTEXT: CanonicalType.TEXT,
    DataType.Type.MEDIUMTEXT: CanonicalType.TEXT,
    DataType.Type.TINYTEXT: CanonicalType.TEXT,
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

_SERIAL_TYPES: dict[DataType.Type, CanonicalType] = {  # type: ignore[valid-type]
    DataType.Type.SERIAL: CanonicalType.INT32,
    DataType.Type.BIGSERIAL: CanonicalType.INT64,
}

_JSON_TYPE = DataType.Type.JSON
_JSONB_TYPE = DataType.Type.JSONB
_ARRAY_TYPE = DataType.Type.ARRAY
_VARBINARY_TYPE = DataType.Type.VARBINARY
_BINARY_TYPE = DataType.Type.BINARY
_BLOB_TYPE = DataType.Type.BLOB

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


def _quoted_literal_end(sql: str, start: int) -> int | None:
    """Return the end of one ordinary SQL string literal, if present.

    This is a lexical helper for PostgreSQL's legal ``'a' 'b'`` literal
    concatenation. It does not interpret SQL expressions or decide whether a
    statement is safe; the normalized text still goes through sqlglot and the
    typed parsers below.
    """
    if start >= len(sql) or sql[start] != "'":
        return None
    index = start + 1
    while index < len(sql):
        if sql[index] != "'":
            index += 1
            continue
        if index + 1 < len(sql) and sql[index + 1] == "'":
            index += 2
            continue
        return index + 1
    return None


def _dollar_quote_end(sql: str, start: int) -> int | None:
    """Return the end of a PostgreSQL dollar-quoted block, if present."""
    if start >= len(sql) or sql[start] != "$":
        return None
    index = start + 1
    while index < len(sql) and (sql[index].isalnum() or sql[index] == "_"):
        index += 1
    if index >= len(sql) or sql[index] != "$":
        return None
    delimiter = sql[start : index + 1]
    closing = sql.find(delimiter, index + 1)
    return len(sql) if closing < 0 else closing + len(delimiter)


def _coalesce_adjacent_string_literals(sql: str) -> str:
    """Normalize only ordinary adjacent string literals.

    PostgreSQL concatenates string literals separated by whitespace. sqlglot's
    PostgreSQL frontend rejects that otherwise valid spelling in several
    COMMENT statements. Keep comments, quoted identifiers, and dollar-quoted
    routine bodies opaque; only ``'left' whitespace 'right'`` is joined.
    """
    output: list[str] = []
    index = 0
    while index < len(sql):
        if sql.startswith("--", index):
            newline = sql.find("\n", index)
            end = len(sql) if newline < 0 else newline
            output.append(sql[index:end])
            index = end
            continue
        if sql.startswith("/*", index):
            closing = sql.find("*/", index + 2)
            end = len(sql) if closing < 0 else closing + 2
            output.append(sql[index:end])
            index = end
            continue
        dollar_end = _dollar_quote_end(sql, index)
        if dollar_end is not None:
            output.append(sql[index:dollar_end])
            index = dollar_end
            continue
        if sql[index] == '"':
            end = index + 1
            while end < len(sql):
                if sql[end] == '"':
                    if end + 1 < len(sql) and sql[end + 1] == '"':
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            output.append(sql[index:end])
            index = end
            continue
        if sql[index] == "'":
            first_end = _quoted_literal_end(sql, index)
            if first_end is not None:
                next_literal = first_end
                while next_literal < len(sql) and sql[next_literal].isspace():
                    next_literal += 1
                second_end = _quoted_literal_end(sql, next_literal) if next_literal < len(sql) else None
                if second_end is not None:
                    output.append(sql[index : first_end - 1])
                    output.append(sql[next_literal + 1 : second_end - 1])
                    end = second_end
                    while True:
                        next_literal = end
                        while next_literal < len(sql) and sql[next_literal].isspace():
                            next_literal += 1
                        next_end = _quoted_literal_end(sql, next_literal) if next_literal < len(sql) else None
                        if next_end is None:
                            break
                        output.append(sql[next_literal + 1 : next_end - 1])
                        end = next_end
                    output.append("'")
                    index = end
                    continue
                output.append(sql[index:first_end])
                index = first_end
                continue
        output.append(sql[index])
        index += 1
    return "".join(output)


def _recover_multi_action_alter(
    sql: str,
    source_dialect: Dialect,
) -> list[exp.Expression] | None:
    """Recover a narrow, typed multi-action ALTER that sqlglot made opaque.

    PostgreSQL permits several ALTER TABLE actions separated by top-level
    commas. sqlglot parses some combinations as ``Command`` when one action
    is less common, even though each individual action has a normal ALTER AST.
    Split only at lexical top-level commas, parse every resulting action with
    sqlglot, and rebuild one normal ALTER AST. No text is interpreted as a
    column definition here; the existing typed ALTER parser remains the sole
    semantic admission gate.
    """
    if source_dialect is not Dialect.POSTGRES:
        return None
    normalized = _coalesce_adjacent_string_literals(sql)
    tokens = Tokenizer(dialect=source_dialect.value).tokenize(normalized)
    if tokens and tokens[-1].token_type.name == "SEMICOLON":
        tokens = tokens[:-1]
    if len(tokens) < 5:
        return None
    if tokens[0].text.upper() != "ALTER" or tokens[1].text.upper() != "TABLE":
        return None

    depth = 0
    action_index: int | None = None
    top_level_commas = []
    for index, token in enumerate(tokens[2:], start=2):
        lexeme_type = token.token_type.name
        if lexeme_type == "L_PAREN":
            depth += 1
        elif lexeme_type == "R_PAREN":
            depth -= 1
        elif depth == 0 and lexeme_type == "COMMA":
            top_level_commas.append(token)
        elif depth == 0 and token.text.upper() in {"ADD", "DROP", "RENAME", "ALTER"}:
            if action_index is None:
                action_index = index
    if action_index is None or not top_level_commas:
        return None

    prefix = normalized[tokens[0].start : tokens[action_index].start]
    spans: list[str] = []
    start = tokens[action_index].start
    for comma in top_level_commas:
        spans.append(normalized[start : comma.start])
        start = comma.end + 1
    spans.append(normalized[start : tokens[-1].end + 1])

    actions: list[exp.Expression] = []
    table_node: exp.Expression | None = None
    for span in spans:
        try:
            action_statement = sqlglot.parse_one(prefix + span, read=source_dialect.value)
        except sqlglot.errors.SqlglotError:
            return None
        if not isinstance(action_statement, exp.Alter):
            return None
        statement_actions = action_statement.args.get("actions") or []
        if len(statement_actions) != 1:
            return None
        action = statement_actions[0]
        if isinstance(action, exp.Drop) and any(
            action.args.get(flag) for flag in ("cascade", "restrict")
        ):
            return None
        if isinstance(action, exp.ColumnDef) and action.args.get("exists"):
            return None
        # Keep the compatibility route narrower than the full ALTER model.
        # The emitter may need to split actions for Oracle and SQL Server;
        # splitting a DROP/RENAME/ALTER alongside an ADD could change the
        # source statement's atomicity or dependency ordering. Such mixes
        # remain explicit blockers even when every individual action parses.
        if not isinstance(action, exp.ColumnDef | exp.AddConstraint):
            return None
        if table_node is None:
            table_node = action_statement.this
        elif action_statement.this != table_node:
            return None
        actions.append(action)
    if table_node is None or not actions:
        return None
    return [exp.Alter(this=table_node, kind="TABLE", actions=actions)]


def _parse_source_statements(sql: str, source_dialect: Dialect) -> list[exp.Expression]:
    try:
        statements = cast(
            list[exp.Expression],
            [s for s in sqlglot.parse(sql, read=source_dialect.value) if s is not None],
        )
        if any(isinstance(statement, exp.Command) for statement in statements):
            recovered = _recover_multi_action_alter(sql, source_dialect)
            if recovered is not None:
                return recovered
        return statements
    except sqlglot.errors.SqlglotError as parse_error:
        if source_dialect is not Dialect.POSTGRES:
            raise
        normalized = _coalesce_adjacent_string_literals(sql)
        if normalized != sql:
            try:
                statements = cast(
                    list[exp.Expression],
                    [s for s in sqlglot.parse(normalized, read=source_dialect.value) if s is not None],
                )
                if any(isinstance(statement, exp.Command) for statement in statements):
                    recovered = _recover_multi_action_alter(normalized, source_dialect)
                    if recovered is not None:
                        return recovered
                return statements
            except sqlglot.errors.SqlglotError:
                # The literal normalizer is also used for COMMENT statements;
                # if the dialect grammar still cannot retain a constraint's
                # table target, continue to the exact compatibility route.
                pass

        recovered = _recover_multi_action_alter(normalized, source_dialect)
        if recovered is not None:
            return recovered

        # sqlglot 30.14.0 does not retain PostgreSQL's `ON <table>` portion
        # when parsing COMMENT ON CONSTRAINT. Keep this compatibility path
        # deliberately lexical and exact: only the eight-token, unqualified,
        # single-string form is materialised into the normal typed Comment
        # route. Anything more complex remains a source-format blocker.
        fallback_sql = normalized
        tokens = Tokenizer(dialect=source_dialect.value).tokenize(fallback_sql)
        if tokens and tokens[-1].token_type.name == "SEMICOLON":
            tokens = tokens[:-1]
        if (
            len(tokens) == 8
            and [token.text.upper() for token in tokens[:3]] == ["COMMENT", "ON", "CONSTRAINT"]
            and tokens[4].text.upper() == "ON"
            and tokens[6].text.upper() == "IS"
        ):
            identifier_tokens = (tokens[3], tokens[5])
            if (
                all(token.token_type.name == "VAR" for token in identifier_tokens)
                and tokens[7].token_type.name == "STRING"
            ):
                table = exp.Table(this=exp.Identifier(this=tokens[5].text, quoted=False))
                table.set("constraint", exp.Identifier(this=tokens[3].text, quoted=False))
                return [
                    exp.Comment(
                        this=table,
                        kind="CONSTRAINT",
                        expression=exp.Literal(this=tokens[7].text, is_string=True),
                    )
                ]
        raise parse_error


def _plain_identifier(node: exp.Expression | None, what: str) -> str:
    _require(node is not None, "CERTIFIED_DDL_MISSING_IDENTIFIER", f"{what} is missing")
    ident = node
    if isinstance(ident, exp.Column):
        ident = ident.this
    if isinstance(ident, exp.Ordered):
        inner = ident.this
        return _plain_identifier(inner, what)
    _require(
        isinstance(ident, exp.Identifier),
        "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
        f"{what} is not a plain identifier ({type(ident).__name__})",
    )
    assert isinstance(ident, exp.Identifier)  # narrows for mypy; _require already enforced this at runtime
    _require(
        not ident.args.get("quoted"),
        "CERTIFIED_DDL_QUOTED_IDENTIFIER",
        f"{what} {ident.this!r} uses a quoted/escaped identifier, which is outside certified-ddl-v1",
    )
    name = ident.this
    assert isinstance(name, str)  # narrows for mypy; the regex check below enforces it at runtime
    _require(
        bool(_IDENTIFIER_RE.match(name)),
        "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
        f"{what} {name!r} is not a plain [A-Za-z_][A-Za-z0-9_]* identifier",
    )
    return name


def _mapped_table_name(
    node: exp.Expression | None,
    what: str,
    namespace_map: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    """Read a table reference and apply an explicit source->target namespace map.

    Qualification is not discarded.  A qualified source name is accepted only
    when the caller supplies a concrete mapping, and the mapped namespace is
    retained in the canonical model for target emission.
    """
    _require(
        isinstance(node, exp.Table), "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE", f"{what} is not a table reference"
    )
    assert isinstance(node, exp.Table)
    _require(
        node.args.get("catalog") is None,
        "CERTIFIED_DDL_QUALIFIED_TABLE_NAME",
        f"{what} has a catalog prefix; catalog mapping is not configured",
    )
    table_name = _plain_identifier(node.this, what)
    schema_node = node.args.get("db")
    if schema_node is None:
        if namespace_map is not None and "" in namespace_map:
            default_target_schema = namespace_map[""]
            _require(
                bool(_IDENTIFIER_RE.match(default_target_schema)),
                "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
                f"mapped target default schema {default_target_schema!r} is not a plain identifier",
            )
            return default_target_schema, table_name
        return None, table_name
    source_schema = _plain_identifier(schema_node, f"{what} schema")
    target_schema = None if namespace_map is None else namespace_map.get(source_schema)
    _require(
        target_schema is not None,
        "CERTIFIED_DDL_NAMESPACE_MAPPING_REQUIRED",
        f"{what} is qualified by source schema {source_schema!r}; provide an explicit namespace_map",
    )
    assert target_schema is not None
    _require(
        bool(_IDENTIFIER_RE.match(target_schema)),
        "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
        f"mapped target schema {target_schema!r} is not a plain identifier",
    )
    return target_schema, table_name


def _require_single_statement(sql: str, source_dialect: Dialect) -> exp.Expression:
    try:
        statements = _parse_source_statements(sql, source_dialect)
    except sqlglot.errors.SqlglotError as exc:
        raise DialectError(
            "CERTIFIED_DDL_PARSE_FAILED", f"{source_dialect.value} parser rejected input: {exc}"
        ) from exc
    _require(
        len(statements) == 1,
        "CERTIFIED_DDL_MULTIPLE_STATEMENTS",
        f"certified-ddl-v1 accepts exactly one statement per call, found {len(statements)}",
    )
    return statements[0]


def _statement(sql: str | exp.Expression, source_dialect: Dialect) -> exp.Expression:
    """Accept either raw SQL or a statement already parsed from it.

    `scan` splits a file with this very parser, so by the time it calls in
    here it is already holding the parsed statement. Serialising that node
    back to text just so this module can parse it again costs two thirds of
    the work per statement, repeated for every statement in a repository, and
    `scan` is the highest-frequency entry point in the engine.

    Passing the node through is also the more faithful of the two: it is the
    node the splitter produced, not one recovered from a source-to-source
    round trip. An already-parsed statement carries the single-statement
    property by construction, which is exactly what
    `_require_single_statement` has to establish for text.
    """
    if isinstance(sql, exp.Expression):
        return sql
    return _require_single_statement(sql, source_dialect)


def _parse_type(data_type: exp.DataType, source_dialect: Dialect) -> CanonicalTypeRef:
    sqlglot_type = data_type.this
    params = list(data_type.expressions or [])

    if sqlglot_type == _JSON_TYPE:
        return CanonicalTypeRef(canonical_type=CanonicalType.JSON)
    if sqlglot_type == _JSONB_TYPE:
        return CanonicalTypeRef(canonical_type=CanonicalType.JSON, json_binary=True)
    if sqlglot_type == _ARRAY_TYPE:
        _require(
            len(params) == 1 and isinstance(params[0], exp.DataType),
            "CERTIFIED_DDL_UNSUPPORTED_TYPE_PARAM",
            "ARRAY must declare exactly one typed element type",
        )
        assert isinstance(params[0], exp.DataType)
        element_type = _parse_type(params[0], source_dialect)
        _require(
            element_type.canonical_type is not CanonicalType.ARRAY,
            "CERTIFIED_DDL_UNSUPPORTED_TYPE",
            "nested arrays require a target-specific collection route",
        )
        return CanonicalTypeRef(canonical_type=CanonicalType.ARRAY, element_type=element_type)
    if sqlglot_type in {_VARBINARY_TYPE, _BINARY_TYPE, _BLOB_TYPE}:
        binary_fixed = sqlglot_type == _BINARY_TYPE
        if sqlglot_type == _BLOB_TYPE and not params:
            raise DialectError(
                "CERTIFIED_DDL_UNBOUNDED_BINARY",
                "unbounded BLOB/BYTEA storage needs an explicit target LOB policy",
            )
        length = None
        if params:
            literal = params[0].this
            _require(
                isinstance(literal, exp.Literal) and not literal.is_string,
                "CERTIFIED_DDL_UNSUPPORTED_TYPE_PARAM",
                "binary length must be a plain integer literal",
            )
            length = int(literal.this)
        _require(
            length is not None,
            "CERTIFIED_DDL_UNBOUNDED_BINARY",
            "unbounded binary storage cannot be mapped without a target LOB contract",
        )
        return CanonicalTypeRef(canonical_type=CanonicalType.BINARY, length=length, binary_fixed=binary_fixed)

    if sqlglot_type in _SERIAL_TYPES:
        _require(
            source_dialect is Dialect.POSTGRES,
            "CERTIFIED_DDL_UNSUPPORTED_TYPE",
            f"{sqlglot_type} is PostgreSQL SERIAL syntax and is not portable when its source dialect is not PostgreSQL",
        )
        return CanonicalTypeRef(canonical_type=_SERIAL_TYPES[sqlglot_type])

    if sqlglot_type in (DataType.Type.VARCHAR, DataType.Type.NVARCHAR) and params:
        first = params[0].this
        if isinstance(first, exp.Var) and str(first.this).upper() == "MAX":
            return CanonicalTypeRef(canonical_type=CanonicalType.TEXT)

    if sqlglot_type == DataType.Type.UBIGINT:
        # 0..18446744073709551615 does not fit INT64, and PostgreSQL, Oracle
        # and SQL Server have no unsigned integer type at all. DECIMAL(20, 0)
        # is the exact substitute, but it is a different type class (no
        # integer arithmetic or index semantics), so this asks rather than
        # decides.
        raise DialectError(
            "CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE",
            "BIGINT UNSIGNED reaches 18446744073709551615, which no canonical integer type "
            "holds and which PostgreSQL, Oracle and SQL Server cannot express; declare the "
            "column as DECIMAL(20, 0) in the source if that substitution is acceptable",
        )

    if sqlglot_type == DataType.Type.TINYINT and params:
        # MySQL has no distinct boolean storage: `BOOLEAN` *is* TINYINT(1),
        # and that is what SHOW CREATE TABLE / mysqldump emit for a column
        # declared BOOLEAN. Reading TINYINT(1) back as a canonical BOOLEAN is
        # what makes a real MySQL schema dump round-trip. A TINYINT(1) used as
        # a small integer instead (MySQL allows -128..127 in it regardless of
        # the display width) is outside this reading; declare it TINYINT(4) or
        # SMALLINT to get the integer mapping.
        width = params[0].this
        if isinstance(width, exp.Literal) and not width.is_string and int(width.this) == 1:
            return CanonicalTypeRef(canonical_type=CanonicalType.BOOLEAN)

    canonical = _TYPE_MAP.get(sqlglot_type)
    _require(
        canonical is not None,
        "CERTIFIED_DDL_UNSUPPORTED_TYPE",
        f"column type {sqlglot_type} is outside certified-ddl-v1's type allowlist",
    )
    assert canonical is not None  # narrows for mypy; _require already enforced this at runtime

    def _param_int(index: int) -> int | None:
        if index >= len(params):
            return None
        literal = params[index].this
        _require(
            isinstance(literal, exp.Literal) and not literal.is_string,
            "CERTIFIED_DDL_UNSUPPORTED_TYPE_PARAM",
            f"type parameter #{index + 1} of {sqlglot_type} is not a plain integer literal",
        )
        return int(literal.this)

    if canonical == CanonicalType.DECIMAL:
        precision = _param_int(0)
        # An unparameterised DECIMAL/NUMBER is *arbitrary* precision and scale
        # in PostgreSQL and Oracle. There is no such type in MySQL or SQL
        # Server, and substituting a default (the pre-fix behaviour used
        # DECIMAL(18, 0)) silently rounds every fractional value in the table
        # to an integer. certified-ddl-v1 fails closed instead.
        _require(
            precision is not None,
            "CERTIFIED_DDL_UNBOUNDED_DECIMAL",
            f"{sqlglot_type} without an explicit precision is arbitrary-precision in "
            f"{source_dialect.value}; no fixed-precision target type preserves it, so "
            "certified-ddl-v1 requires DECIMAL(p) or DECIMAL(p, s)",
        )
        return CanonicalTypeRef(canonical_type=canonical, precision=precision, scale=_param_int(1))
    if canonical in (CanonicalType.CHAR, CanonicalType.VARCHAR):
        length = _param_int(0)
        if canonical == CanonicalType.VARCHAR and length is None:
            # PostgreSQL's bare `VARCHAR` is explicitly unlimited (equivalent
            # to TEXT). SQL Server's bare `VARCHAR` means VARCHAR(1); MySQL
            # and Oracle reject the bare form outright. Only the PostgreSQL
            # reading is safe to carry across dialects.
            _require(
                source_dialect == Dialect.POSTGRES,
                "CERTIFIED_DDL_UNBOUNDED_VARCHAR",
                f"VARCHAR without a length is not portable from {source_dialect.value} "
                "(SQL Server reads it as VARCHAR(1); MySQL and Oracle reject it); "
                "declare an explicit length",
            )
            return CanonicalTypeRef(canonical_type=CanonicalType.TEXT)
        # Oracle spells its length semantics inline -- VARCHAR2(50 CHAR) /
        # VARCHAR2(50 BYTE). Either qualifier is accepted here: BYTE lengths
        # are the narrower reading, so treating the number as a character
        # count when re-emitting is always a widening, never a truncation.
        return CanonicalTypeRef(canonical_type=canonical, length=length)
    return CanonicalTypeRef(canonical_type=canonical)


def _parse_default(node: exp.Expression, type_ref: CanonicalTypeRef) -> ColumnDefault:
    if isinstance(node, exp.CurrentTimestamp):
        _require(
            type_ref.canonical_type == CanonicalType.TIMESTAMP,
            "CERTIFIED_DDL_DEFAULT_TYPE_MISMATCH",
            "CURRENT_TIMESTAMP default is only supported on TIMESTAMP columns",
        )
        return ColumnDefault(kind=DefaultKind.CURRENT_TIMESTAMP)
    if isinstance(node, exp.Cast):
        # PostgreSQL migration DDL commonly spells JSONB defaults as either
        # `'{}'::jsonb` or `CAST('{}' AS JSONB)`.  This is not an arbitrary
        # expression: it is a string literal plus an explicit, typed cast.
        # Preserve the cast in the canonical model so the source-side parser
        # does not discard storage semantics.  Target emitters still reject
        # json_binary where the target has no exact equivalent.
        target = node.args.get("to")
        literal = node.this
        _require(
            isinstance(target, exp.DataType)
            and target.this == _JSONB_TYPE
            and isinstance(literal, exp.Literal)
            and literal.is_string,
            "CERTIFIED_DDL_UNSUPPORTED_DEFAULT",
            "typed defaults are limited to string literals explicitly cast to JSONB",
        )
        _require(
            type_ref.canonical_type is CanonicalType.JSON and type_ref.json_binary,
            "CERTIFIED_DDL_DEFAULT_TYPE_MISMATCH",
            "a JSONB default requires a JSONB column",
        )
        return ColumnDefault(
            kind=DefaultKind.STRING,
            literal=str(literal.this),
            cast_type=CanonicalTypeRef(canonical_type=CanonicalType.JSON, json_binary=True),
        )
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
    raise DialectError(
        "CERTIFIED_DDL_UNSUPPORTED_DEFAULT",
        f"DEFAULT expression of kind {type(node).__name__} is outside certified-ddl-v1 "
        "(only literals and CURRENT_TIMESTAMP are supported)",
    )


def _check_literal(node: exp.Expression | None, what: str) -> CheckLiteral:
    if isinstance(node, exp.Boolean):
        return CheckLiteral(value="true" if node.this else "false", is_boolean=True)
    _require(isinstance(node, exp.Literal), "CERTIFIED_DDL_UNSUPPORTED_CHECK", f"{what} must be a plain literal")
    assert isinstance(node, exp.Literal)  # narrows for mypy
    return CheckLiteral(value=str(node.this), is_string=bool(node.is_string))


def _parse_check_left_value(node: exp.Expression, what: str) -> tuple[str, CheckValueExpression | None]:
    if isinstance(node, exp.Trim):
        _require(
            node.expression is None,
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "TRIM CHECK expressions must use the default space character",
        )
        column = _plain_identifier(node.this, what)
        return column, CheckValueExpression(column=column, function=CheckValueFunction.TRIM)
    if isinstance(node, exp.Anonymous) and str(node.this).upper() == "BTRIM":
        arguments = list(node.expressions or [])
        _require(
            len(arguments) == 1,
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "BTRIM CHECK expressions must have one column argument",
        )
        column = _plain_identifier(arguments[0], what)
        return column, CheckValueExpression(column=column, function=CheckValueFunction.TRIM)
    if isinstance(node, exp.Add) and isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Column):
        column = _plain_identifier(node.this, what)
        right_column = _plain_identifier(node.expression, "CHECK value right-hand column")
        return column, CheckValueExpression(
            column=column,
            operator=CheckValueOperator.ADD,
            right_column=right_column,
        )
    return _plain_identifier(node, what), None


def _parse_check_comparison(node: exp.Expression, source_dialect: Dialect) -> CheckExpression:
    # --- `NOT (x IS NULL)`, which is how mysql/oracle/tsql spell IS NOT NULL --
    # The boolean-tree builder canonicalizes this one spelling difference. Any
    # other NOT is retained as a typed CheckNotExpression instead of being
    # algebraically rewritten.
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
        inner = node.this
        _require(
            isinstance(inner.expression, exp.Null),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "certified-ddl-v1 supports IS [NOT] NULL only; IS TRUE/FALSE has no Oracle equivalent",
        )
        _require(
            not inner.args.get("negate"),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "the canonical null-test spelling must not be doubly negated",
        )
        return CheckComparison(
            column=_plain_identifier(inner.this, "CHECK left-hand column"),
            operator=CheckOperator.IS_NOT_NULL,
        )

    # --- null tests -------------------------------------------------------
    # `IS NULL` and `IS NOT NULL` are the same sqlglot node, told apart by a
    # `negate` flag. `IS TRUE` is also an `Is`, and is refused: Oracle has no
    # boolean type and no `IS TRUE`.
    if isinstance(node, exp.Is):
        _require(
            isinstance(node.expression, exp.Null),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "certified-ddl-v1 supports IS [NOT] NULL only; IS TRUE/FALSE has no Oracle equivalent",
        )
        column = _plain_identifier(node.this, "CHECK left-hand column")
        operator = CheckOperator.IS_NOT_NULL if node.args.get("negate") else CheckOperator.IS_NULL
        return CheckComparison(column=column, operator=operator)

    # A bare BOOLEAN column in a CHECK is an assertion of truth. The table
    # model verifies the referenced column is actually BOOLEAN before any
    # target SQL is emitted; this prevents accidentally treating an integer as
    # a boolean while still allowing Oracle/T-SQL renderers to use 1/0 storage.
    if isinstance(node, exp.Column):
        return CheckComparison(column=_plain_identifier(node, "CHECK boolean column"), operator=CheckOperator.IS_TRUE)

    # --- set membership ---------------------------------------------------
    if isinstance(node, exp.In):
        _require(
            not node.args.get("query"),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "CHECK IN (subquery) is outside certified-ddl-v1",
        )
        column = _plain_identifier(node.this, "CHECK left-hand column")
        members = node.args.get("expressions") or []
        _require(bool(members), "CERTIFIED_DDL_UNSUPPORTED_CHECK", "CHECK IN requires a literal list")
        return CheckComparison(
            column=column,
            operator=CheckOperator.IN,
            literals=tuple(_check_literal(m, "CHECK IN member") for m in members),
        )

    # LIKE is admitted only for patterns whose result is independent of
    # collation/escaping rules (the model applies that guard). This covers
    # path/host shape checks such as '/%' and '%*%' without pretending that
    # arbitrary case-bearing LIKE is portable.
    if isinstance(node, exp.Like):
        column = _plain_identifier(node.this, "CHECK LIKE left-hand column")
        literal = node.expression
        _require(
            isinstance(literal, exp.Literal) and literal.is_string,
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "LIKE CHECK pattern must be a string literal",
        )
        return CheckComparison(
            column=column,
            operator=CheckOperator.LIKE,
            literal=str(literal.this),
            literal_is_string=True,
        )

    # --- range membership -------------------------------------------------
    # `BETWEEN SYMMETRIC` is PostgreSQL-only, so it is refused rather than
    # normalised away.
    if isinstance(node, exp.Between):
        _require(
            not node.args.get("symmetric"),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "BETWEEN SYMMETRIC is PostgreSQL-only and outside certified-ddl-v1",
        )
        column = _plain_identifier(node.this, "CHECK left-hand column")
        return CheckComparison(
            column=column,
            operator=CheckOperator.BETWEEN,
            literals=(
                _check_literal(node.args.get("low"), "CHECK BETWEEN lower bound"),
                _check_literal(node.args.get("high"), "CHECK BETWEEN upper bound"),
            ),
        )

    # sqlglot represents PostgreSQL `~`, MySQL `REGEXP`, and Oracle/MySQL
    # REGEXP_LIKE as one RegexpLike node.  The source spelling still matters:
    # MySQL without an explicit `c` flag inherits collation sensitivity, so
    # accepting it would make the source semantics depend on session/schema
    # configuration that is not in this statement.
    if isinstance(node, exp.RegexpLike):
        column = _plain_identifier(node.this, "CHECK regex left-hand column")
        literal = node.expression
        _require(
            isinstance(literal, exp.Literal) and literal.is_string,
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "regex CHECK pattern must be a string literal",
        )
        flag = node.args.get("flag")
        pattern = str(literal.this)
        if source_dialect is Dialect.MYSQL and flag is None:
            raise DialectError(
                "CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX",
                "MySQL REGEXP without an explicit case-sensitive 'c' match parameter "
                "inherits collation sensitivity; certified-ddl-v1 refuses to guess it",
            )
        if flag is not None:
            _require(
                isinstance(flag, exp.Literal) and flag.is_string,
                "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER",
                "regex match parameter must be a string literal",
            )
            _require(
                str(flag.this) == "c",
                "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER",
                "only the explicit case-sensitive regex match parameter 'c' is portable",
            )
        return CheckComparison(
            column=column,
            operator=CheckOperator.MATCHES_REGEX,
            literal=pattern,
            literal_is_string=True,
        )

    # Oracle has no SQL boolean type, so `(a IS NULL) = (b IS NULL)` cannot be
    # emitted as a direct predicate comparison there. Expand equality of two
    # null tests into its exact truth table instead. The operands are already
    # total boolean predicates, so this is a semantic identity, not a
    # three-valued-logic rewrite of arbitrary expressions.
    left_is: exp.Expression | None = None
    right_is: exp.Expression | None = None
    if isinstance(node, exp.EQ):
        left_is = _unwrap_check_parens(node.this)
        right_is = _unwrap_check_parens(node.expression)
        if not isinstance(left_is, exp.Is) or not isinstance(right_is, exp.Is):
            left_is = None
            right_is = None
    if isinstance(left_is, exp.Is) and isinstance(right_is, exp.Is):
        _require(
            isinstance(left_is.expression, exp.Null) and isinstance(right_is.expression, exp.Null),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "boolean CHECK equality is limited to IS NULL predicates",
        )

        def null_test(item: exp.Is) -> tuple[str, bool]:
            return _plain_identifier(item.this, "CHECK null-test column"), not bool(item.args.get("negate"))

        left_column, left_true_is_null = null_test(left_is)
        right_column, right_true_is_null = null_test(right_is)

        def test(column: str, true_is_null: bool, expected: bool) -> CheckComparison:
            is_null = true_is_null if expected else not true_is_null
            return CheckComparison(
                column=column,
                operator=CheckOperator.IS_NULL if is_null else CheckOperator.IS_NOT_NULL,
            )

        return CheckBooleanExpression(
            connector=CheckConnector.OR,
            operands=(
                CheckBooleanExpression(
                    connector=CheckConnector.AND,
                    operands=(test(left_column, left_true_is_null, True), test(right_column, right_true_is_null, True)),
                ),
                CheckBooleanExpression(
                    connector=CheckConnector.AND,
                    operands=(
                        test(left_column, left_true_is_null, False),
                        test(right_column, right_true_is_null, False),
                    ),
                ),
            ),
        )

    # --- binary comparisons ----------------------------------------------
    binary_operator: CheckOperator | None = _CHECK_OPERATOR_MAP.get(type(node))
    _require(
        binary_operator is not None,
        "CERTIFIED_DDL_UNSUPPORTED_CHECK",
        f"CHECK comparison operator {type(node).__name__} is outside certified-ddl-v1",
    )
    assert binary_operator is not None  # narrows for mypy; _require already enforced this at runtime
    column, left_expression = _parse_check_left_value(node.this, "CHECK left-hand column")
    literal = node.expression
    if isinstance(literal, exp.Column):
        return CheckComparison(
            column=column,
            operator=binary_operator,
            right_column=_plain_identifier(literal, "CHECK right-hand column"),
            left_expression=left_expression,
        )
    if isinstance(literal, exp.Boolean):
        return CheckComparison(
            column=column,
            operator=binary_operator,
            literal="true" if literal.this else "false",
            literal_is_boolean=True,
        )
    if isinstance(literal, exp.Add):
        interval_column = literal.this
        interval = literal.expression
        _require(
            isinstance(interval_column, exp.Column) and isinstance(interval, exp.Interval),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "timestamp CHECK arithmetic must be column plus a bounded interval",
        )
        interval_literal = interval.this
        _require(
            isinstance(interval_literal, exp.Literal) and str(interval_literal.this).isdigit(),
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "timestamp CHECK intervals must use a non-negative integer literal",
        )
        unit_text = str(interval.args.get("unit", "")).upper().rstrip("S")
        _require(
            unit_text in {unit.value for unit in CheckIntervalUnit},
            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
            "timestamp CHECK intervals are limited to seconds, minutes, hours, and days",
        )
        return CheckComparison(
            column=column,
            operator=binary_operator,
            right_interval_column=_plain_identifier(interval_column, "CHECK interval column"),
            right_interval_value=int(str(interval_literal.this)),
            right_interval_unit=CheckIntervalUnit(unit_text),
        )
    _require(
        isinstance(literal, exp.Literal),
        "CERTIFIED_DDL_UNSUPPORTED_CHECK",
        "CHECK right-hand side must be a plain literal",
    )
    return CheckComparison(
        column=column,
        operator=binary_operator,
        literal=str(literal.this),
        literal_is_string=bool(literal.is_string),
        left_expression=left_expression,
    )


_MAX_CHECK_PAREN_DEPTH = 8


def _unwrap_check_parens(node: exp.Expression) -> exp.Expression:
    """Strip redundant parentheses around a CHECK body.

    Purely syntactic: `CHECK ((a > 0))` and `CHECK (a > 0)` are the same
    constraint to all four dialects, and both re-render identically. Bounded
    so deeply nested input fails closed rather than recursing.
    """

    depth = 0
    while isinstance(node, exp.Paren):
        depth += 1
        if depth > _MAX_CHECK_PAREN_DEPTH:
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                f"CHECK nests more than {_MAX_CHECK_PAREN_DEPTH} redundant parentheses",
            )
        node = node.this
    return node


def _parse_check(
    node: exp.Expression, source_dialect: Dialect
) -> tuple[tuple[CheckComparison, ...], CheckConnector | None, CheckExpression | None]:
    def build(current: exp.Expression, depth: int) -> CheckExpression:
        if depth > 16:
            raise DialectError(
                "CERTIFIED_DDL_MULTI_LEVEL_CHECK",
                "CHECK boolean nesting exceeds the bounded canonical form",
            )
        current = _unwrap_check_parens(current)
        if isinstance(current, exp.And | exp.Or):
            connector = CheckConnector.AND if isinstance(current, exp.And) else CheckConnector.OR
            return CheckBooleanExpression(
                connector=connector,
                operands=(build(current.this, depth + 1), build(current.expression, depth + 1)),
            )
        if isinstance(current, exp.Not):
            # PostgreSQL renders `IS NOT NULL` as Is(negate=True), while
            # MySQL/Oracle/T-SQL often arrive as NOT(Is(NULL)). Canonicalize
            # only that standard spelling; all other NOT expressions retain
            # their exact child tree.
            if isinstance(current.this, exp.Is) and not current.this.args.get("negate"):
                return _parse_check_comparison(current, source_dialect)
            return CheckNotExpression(operand=build(current.this, depth + 1))
        return _parse_check_comparison(current, source_dialect)

    expression = build(_unwrap_check_parens(node), 0)
    # Preserve the compact legacy representation for the common flat case.
    if isinstance(expression, CheckBooleanExpression):

        def flatten(current: CheckExpression) -> tuple[CheckComparison, ...] | None:
            if isinstance(current, CheckComparison):
                return (current,)
            if isinstance(current, CheckNotExpression):
                return None
            if current.connector is not expression.connector:
                return None
            operands: list[CheckComparison] = []
            for operand in current.operands:
                flattened = flatten(operand)
                if flattened is None:
                    return None
                operands.extend(flattened)
            return tuple(operands)

        comparisons = flatten(expression)
        if comparisons is not None:
            return comparisons, expression.connector, None
    return (), None, expression


def _column_constraints(
    col_def: exp.ColumnDef,
    type_ref: CanonicalTypeRef,
    column_name: str,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> tuple[bool, ColumnDefault | None, bool, bool, bool, ForeignKey | None, list[CheckConstraint]]:
    """Returns (nullable, default, auto_increment, primary_key_shorthand,
    unique_shorthand, inline_foreign_key, inline_checks).

    Inline `REFERENCES` and inline `CHECK` are the same constraints as their
    table-level spellings, so they are lifted into the SAME canonical
    fields rather than modelled separately -- otherwise two schemas that
    are identical to every database would produce different canonical
    models and emit differently.
    """
    nullable = True
    default: ColumnDefault | None = None
    auto_increment = False
    primary_key_shorthand = False
    unique_shorthand = False
    inline_foreign_key: ForeignKey | None = None
    inline_checks: list[CheckConstraint] = []
    for constraint in col_def.constraints or []:
        kind = constraint.kind
        if isinstance(kind, exp.NotNullColumnConstraint):
            nullable = False
        elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
            primary_key_shorthand = True
            nullable = False
        elif isinstance(kind, exp.AutoIncrementColumnConstraint | exp.GeneratedAsIdentityColumnConstraint):
            auto_increment = True
        elif isinstance(kind, exp.DefaultColumnConstraint):
            default = _parse_default(kind.this, type_ref)
        elif isinstance(kind, exp.UniqueColumnConstraint) and kind.this is None:
            unique_shorthand = True
        elif isinstance(kind, exp.Reference):
            # `b_id INTEGER REFERENCES b(id)` -- identical in meaning to a
            # table-level FOREIGN KEY (b_id) REFERENCES b(id).
            _require(
                inline_foreign_key is None,
                "CERTIFIED_DDL_UNSUPPORTED_COLUMN_CONSTRAINT",
                f"column {column_name!r} declares more than one inline REFERENCES",
            )
            inline_foreign_key = _parse_reference(kind, (column_name,), None, namespace_map)
        elif isinstance(kind, exp.CheckColumnConstraint):
            # `n INTEGER CHECK (n > 0)` -- lifted to a table-level CHECK,
            # which is how every target dialect renders it anyway.
            comparisons, connector, expression = _parse_check(kind.this, source_dialect)
            inline_checks.append(
                CheckConstraint(comparisons=comparisons, connector=connector, expression=expression, name=None)
            )
        else:
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_COLUMN_CONSTRAINT",
                f"column constraint {type(kind).__name__} is outside certified-ddl-v1",
            )
    return (
        nullable,
        default,
        auto_increment,
        primary_key_shorthand,
        unique_shorthand,
        inline_foreign_key,
        inline_checks,
    )


def parse_create_table(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Table:
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Create) and statement.args.get("kind") == "TABLE",
        "CERTIFIED_DDL_UNSUPPORTED_STATEMENT",
        "certified-ddl-v1 only accepts a single CREATE TABLE statement",
    )
    for flag in ("replace", "unique", "concurrently"):
        _require(
            not statement.args.get(flag),
            "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
            f"CREATE TABLE modifier {flag!r} is outside certified-ddl-v1",
        )
    # `exists` (IF NOT EXISTS) is admitted and carried in the model instead of
    # being refused at the door. Measured on 89 real .sql files it was 54 of
    # the blocked statements across only 4 distinct reasons -- the densest
    # blocker in the profile that is a spelling rather than a semantic gap.
    # Whether it survives translation is the TARGET's question, decided in
    # `emitter`, because the answer differs per dialect.
    if_not_exists = bool(statement.args.get("exists"))

    schema = statement.this
    _require(isinstance(schema, exp.Schema), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "malformed CREATE TABLE")
    table_ref = schema.this
    table_schema, table_name = _mapped_table_name(table_ref, "table name", namespace_map)

    columns: list[Column] = []
    primary_key: list[str] = []
    unique_constraints: list[tuple[str, ...]] = []
    foreign_keys: list[ForeignKey] = []
    check_constraints: list[CheckConstraint] = []

    for item in schema.expressions:
        if isinstance(item, exp.ColumnDef):
            column_name = _plain_identifier(item.this, "column name")
            _require(
                item.kind is not None,
                "CERTIFIED_DDL_UNSUPPORTED_TABLE_ITEM",
                f"column {column_name!r} is missing a type",
            )
            assert item.kind is not None  # narrows for mypy; _require already enforced this at runtime
            type_ref = _parse_type(item.kind, source_dialect)
            (nullable, default, auto_increment, pk_shorthand, unique_shorthand, inline_fk, inline_checks) = (
                _column_constraints(item, type_ref, column_name, source_dialect, namespace_map)
            )
            auto_increment = auto_increment or item.kind.this in _SERIAL_TYPES
            columns.append(
                Column(
                    name=column_name,
                    type_ref=type_ref,
                    nullable=nullable,
                    default=default,
                    auto_increment=auto_increment,
                )
            )
            if pk_shorthand:
                primary_key.append(column_name)
            if unique_shorthand:
                unique_constraints.append((column_name,))
            if inline_fk is not None:
                foreign_keys.append(inline_fk)
            check_constraints.extend(inline_checks)
        elif isinstance(item, exp.PrimaryKey):
            primary_key.extend(_plain_identifier(e, "PRIMARY KEY column") for e in item.expressions)
        elif isinstance(item, exp.Constraint):
            name = _plain_identifier(item.this, "constraint name") if item.this is not None else None
            _require(
                len(item.expressions) == 1,
                "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT",
                "a named constraint must contain exactly one constraint clause",
            )
            _apply_table_constraint(
                item.expressions[0],
                name,
                primary_key,
                unique_constraints,
                foreign_keys,
                check_constraints,
                source_dialect,
                namespace_map,
            )
        elif isinstance(item, exp.UniqueColumnConstraint | exp.ForeignKey | exp.CheckColumnConstraint):
            # Unnamed table-level UNIQUE(...) / FOREIGN KEY(...) / CHECK(...), i.e. no
            # `CONSTRAINT <name>` prefix -- sqlglot represents these as bare nodes
            # directly in the table body rather than wrapped in exp.Constraint.
            _apply_table_constraint(
                item,
                None,
                primary_key,
                unique_constraints,
                foreign_keys,
                check_constraints,
                source_dialect,
                namespace_map,
            )
        else:
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_TABLE_ITEM",
                f"table-level item {type(item).__name__} is outside certified-ddl-v1 "
                "(no partitioning, triggers, storage options, generated columns, or inheritance)",
            )

    return Table(
        name=table_name,
        columns=tuple(columns),
        primary_key=tuple(primary_key),
        unique_constraints=tuple(unique_constraints),
        foreign_keys=tuple(foreign_keys),
        check_constraints=tuple(check_constraints),
        if_not_exists=if_not_exists,
        schema=table_schema,
    )


def _parse_reference(
    reference: exp.Expression,
    columns: tuple[str, ...],
    name: str | None,
    namespace_map: Mapping[str, str] | None = None,
) -> ForeignKey:
    """Build a canonical ForeignKey from a REFERENCES clause.

    Shared by the table-level `FOREIGN KEY (c) REFERENCES t(c)` form and the
    inline `c INTEGER REFERENCES t(c)` column form. They are the same
    constraint written two ways -- every one of the four dialects accepts
    both and treats them identically -- so they must produce the same
    canonical model. Supporting only one of them was a real gap: a scan of
    117 real migration files found 403 statements blocked purely because
    their foreign key was written inline.
    """
    ref_schema = reference.this
    ref_table_node = ref_schema.this if isinstance(ref_schema, exp.Schema) else ref_schema
    ref_namespace, ref_table = _mapped_table_name(
        ref_table_node if isinstance(ref_table_node, exp.Table) else None,
        "FOREIGN KEY reference table",
        namespace_map,
    )
    ref_columns = tuple(
        _plain_identifier(e, "FOREIGN KEY reference column")
        for e in (ref_schema.expressions if isinstance(ref_schema, exp.Schema) else [])
    )
    on_delete = ReferentialAction.NO_ACTION
    on_update = ReferentialAction.NO_ACTION
    for option in reference.args.get("options") or []:
        option_sql = str(option).upper()
        for prefix, attr in (("ON DELETE ", "on_delete"), ("ON UPDATE ", "on_update")):
            if option_sql.startswith(prefix):
                action = _REFERENTIAL_ACTION_MAP.get(option_sql[len(prefix) :].strip())
                _require(
                    action is not None,
                    "CERTIFIED_DDL_UNSUPPORTED_REFERENTIAL_ACTION",
                    f"referential action {option_sql!r} is outside certified-ddl-v1",
                )
                assert action is not None  # narrows for mypy; _require already enforced this at runtime
                if attr == "on_delete":
                    on_delete = action
                else:
                    on_update = action
    return ForeignKey(
        columns=columns,
        ref_table=ref_table,
        ref_columns=ref_columns,
        on_delete=on_delete,
        on_update=on_update,
        name=name,
        ref_schema=ref_namespace,
    )


def _apply_table_constraint(
    inner: exp.Expression,
    name: str | None,
    primary_key: list[str],
    unique_constraints: list[tuple[str, ...]],
    foreign_keys: list[ForeignKey],
    check_constraints: list[CheckConstraint],
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> None:
    if isinstance(inner, exp.PrimaryKey):
        primary_key.extend(_plain_identifier(e, "PRIMARY KEY column") for e in inner.expressions)
    elif isinstance(inner, exp.UniqueColumnConstraint):
        target = inner.this
        _require(
            isinstance(target, exp.Schema),
            "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT",
            "table-level UNIQUE must list explicit columns",
        )
        unique_constraints.append(tuple(_plain_identifier(e, "UNIQUE column") for e in target.expressions))
    elif isinstance(inner, exp.ForeignKey):
        columns = tuple(_plain_identifier(e, "FOREIGN KEY column") for e in inner.expressions)
        reference = inner.args.get("reference")
        _require(reference is not None, "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT", "FOREIGN KEY requires REFERENCES")
        assert reference is not None  # narrows for mypy; _require already enforced this at runtime
        foreign_keys.append(_parse_reference(reference, columns, name, namespace_map))
    elif isinstance(inner, exp.CheckColumnConstraint):
        comparisons, connector, expression = _parse_check(inner.this, source_dialect)
        check_constraints.append(
            CheckConstraint(comparisons=comparisons, connector=connector, expression=expression, name=name)
        )
    else:
        raise DialectError(
            "CERTIFIED_DDL_UNSUPPORTED_CONSTRAINT",
            f"named constraint clause {type(inner).__name__} is outside certified-ddl-v1",
        )


def parse_create_index(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Index:
    source_text = sql if isinstance(sql, str) else None
    if source_text is not None:
        # sqlglot normalises `NULLS LAST` to the same AST flags as a plain
        # ascending key. Inspect the source tokens as a syntax-preservation
        # guard so that this otherwise invisible modifier cannot be dropped.
        tokens = sqlglot.tokenize(source_text, read=source_dialect.value)
        for index, token in enumerate(tokens[:-1]):
            if token.text.upper() == "NULLS" and tokens[index + 1].text.upper() in {"FIRST", "LAST"}:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_INDEX_ORDER",
                    "index NULLS FIRST/LAST placement is not part of the four-dialect common profile",
                )
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Create) and statement.args.get("kind") == "INDEX",
        "CERTIFIED_DDL_UNSUPPORTED_STATEMENT",
        "certified-ddl-v1 only accepts a single CREATE INDEX statement here",
    )
    for flag in ("replace", "concurrently"):
        _require(
            not statement.args.get(flag),
            "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
            f"CREATE INDEX modifier {flag!r} is outside certified-ddl-v1",
        )
    index_if_not_exists = bool(statement.args.get("exists"))
    index_node = statement.this
    _require(isinstance(index_node, exp.Index), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "malformed CREATE INDEX")
    index_name = _plain_identifier(index_node.this, "index name")
    table_node = index_node.args.get("table")
    table_schema, table_name = _mapped_table_name(table_node, "index table name", namespace_map)
    params = index_node.args.get("params")
    _require(params is not None, "CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "CREATE INDEX requires a column list")
    unexpected_params = {
        key
        for key, value in params.args.items()
        if key not in {"columns", "with_storage", "where", "include", "using"} and value not in (None, False, [], ())
    }
    _require(
        not unexpected_params,
        "CERTIFIED_DDL_UNSUPPORTED_INDEX_MODIFIER",
        "CREATE INDEX modifiers are outside the common profile: " + ", ".join(sorted(unexpected_params)),
    )
    index_columns: list[IndexColumn] = []
    for column in params.args.get("columns") or []:
        descending = False
        if isinstance(column, exp.Ordered):
            desc = column.args.get("desc")
            nulls_first = column.args.get("nulls_first")
            _require(
                not (nulls_first and desc is False),
                "CERTIFIED_DDL_UNSUPPORTED_INDEX_ORDER",
                "index NULLS FIRST/LAST placement is not part of the four-dialect common profile",
            )
            _require(
                not (desc is True and nulls_first is False),
                "CERTIFIED_DDL_UNSUPPORTED_INDEX_ORDER",
                "index NULLS LAST placement is not part of the four-dialect common profile",
            )
            descending = desc is True
            column = column.this
        index_columns.append(IndexColumn(name=_plain_identifier(column, "index column"), descending=descending))
    where = params.args.get("where")
    predicate = None
    if where is not None:
        _require(
            isinstance(where, exp.Where),
            "CERTIFIED_DDL_UNSUPPORTED_INDEX_MODIFIER",
            "index WHERE predicate is malformed",
        )
        predicate = _parse_check(where.this, source_dialect)[2]
        if predicate is None:
            comparisons, connector, _ = _parse_check(where.this, source_dialect)
            predicate = (
                CheckBooleanExpression(
                    connector=connector or CheckConnector.AND,
                    operands=tuple(comparisons),
                )
                if len(comparisons) > 1
                else (comparisons[0] if comparisons else None)
            )
        _require(predicate is not None, "CERTIFIED_DDL_UNSUPPORTED_INDEX_MODIFIER", "index WHERE predicate is empty")
    include_node = params.args.get("include")
    include_nodes: list[exp.Expression] = []
    if include_node is not None:
        if isinstance(include_node, exp.Identifier):
            include_nodes = [include_node]
        elif isinstance(include_node, exp.Schema):
            include_nodes = list(include_node.expressions)
        elif isinstance(include_node, list):
            include_nodes = include_node
        else:
            raise DialectError("CERTIFIED_DDL_UNSUPPORTED_INDEX_MODIFIER", "index INCLUDE list is malformed")
    using_node = params.args.get("using")
    using = None if using_node is None else str(using_node.this if hasattr(using_node, "this") else using_node).lower()
    return Index(
        name=index_name,
        table=table_name,
        columns=tuple(index_columns),
        unique=bool(statement.args.get("unique")),
        if_not_exists=index_if_not_exists,
        table_schema=table_schema,
        include=tuple(_plain_identifier(node, "index included column") for node in include_nodes),
        predicate=predicate,
        using=using,
    )


def parse_drop_table(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> DropTable:
    """Parse the portable `DROP TABLE [IF EXISTS] name` profile."""
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Drop) and str(statement.args.get("kind", "")).upper() == "TABLE",
        "CERTIFIED_DROP_UNSUPPORTED_STATEMENT",
        "certified-drop-v1 only accepts a single DROP TABLE statement",
    )
    _require(
        not any(statement.args.get(flag) for flag in ("temporary", "cascade", "restrict", "purge", "constraints")),
        "CERTIFIED_DROP_UNSUPPORTED_MODIFIER",
        "DROP TABLE modifiers are not portable: PostgreSQL/Oracle/MySQL/SQL Server "
        "use different dependency and cleanup semantics (for example CASCADE CONSTRAINTS in Oracle)",
    )
    table = statement.this
    table_schema, table_name = _mapped_table_name(table, "table name", namespace_map)
    return DropTable(
        name=table_name,
        if_exists=bool(statement.args.get("exists")),
        schema=table_schema,
    )


def parse_create_schema(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Schema:
    """Parse the minimal `CREATE SCHEMA [IF NOT EXISTS] name` profile."""
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "SCHEMA",
        "CERTIFIED_SCHEMA_UNSUPPORTED_STATEMENT",
        "certified-schema-v1 only accepts a single CREATE SCHEMA statement",
    )
    _require(
        not any(statement.args.get(flag) for flag in ("replace", "unique", "concurrently")),
        "CERTIFIED_SCHEMA_UNSUPPORTED_MODIFIER",
        "CREATE SCHEMA modifiers outside IF NOT EXISTS are not in certified-schema-v1",
    )
    schema = statement.this
    _require(
        isinstance(schema, exp.Table) and schema.args.get("this") is None and schema.args.get("catalog") is None,
        "CERTIFIED_SCHEMA_QUALIFIED_NAME",
        "certified-schema-v1 requires one unqualified schema name",
    )
    schema_name = _plain_identifier(schema.args.get("db"), "schema name")
    if namespace_map is not None and schema_name in namespace_map:
        schema_name = namespace_map[schema_name]
        _require(
            bool(_IDENTIFIER_RE.match(schema_name)),
            "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
            f"mapped target schema {schema_name!r} is not a plain identifier",
        )
    return Schema(
        name=schema_name,
        if_not_exists=bool(statement.args.get("exists")),
    )


def _parse_insert_literal(node: exp.Expression) -> InsertLiteral:
    if isinstance(node, exp.Null):
        return InsertLiteral(is_null=True)
    if isinstance(node, exp.Boolean):
        return InsertLiteral(value="true" if bool(node.this) else "false", is_boolean=True)
    if isinstance(node, exp.Literal):
        value = str(node.this)
        if node.is_string:
            return InsertLiteral(value=value, is_string=True)
        _require(
            bool(_NUMERIC_LITERAL_RE.fullmatch(value)),
            "CERTIFIED_INSERT_UNSUPPORTED_EXPRESSION",
            f"numeric INSERT literal {value!r} is not a portable decimal/scientific literal",
        )
        return InsertLiteral(value=value)
    if isinstance(node, exp.Neg):
        inner = node.this
        _require(
            isinstance(inner, exp.Literal) and not inner.is_string,
            "CERTIFIED_INSERT_UNSUPPORTED_EXPRESSION",
            "unary negative INSERT values must apply directly to a numeric literal",
        )
        assert isinstance(inner, exp.Literal)
        value = "-" + str(inner.this)
        _require(
            bool(_NUMERIC_LITERAL_RE.fullmatch(value)),
            "CERTIFIED_INSERT_UNSUPPORTED_EXPRESSION",
            f"numeric INSERT literal {value!r} is not portable",
        )
        return InsertLiteral(value=value)
    raise DialectError(
        "CERTIFIED_INSERT_UNSUPPORTED_EXPRESSION",
        f"INSERT VALUES expression {type(node).__name__} is outside the literal-only route",
    )


def parse_insert(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> InsertStatement:
    """Parse a fixed-column, literal-only INSERT seed into typed IR.

    The route intentionally rejects query sources and conflict policies. Both
    change which rows are written or what a rerun does, and neither can be
    recovered from a list of VALUES literals.
    """
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Insert),
        "CERTIFIED_INSERT_UNSUPPORTED_STATEMENT",
        "certified-insert-v1 only accepts one INSERT statement",
    )
    assert isinstance(statement, exp.Insert)
    for flag in (
        "hint",
        "is_function",
        "stored",
        "by_name",
        "exists",
        "where",
        "partition",
        "settings",
        "default",
        "conflict",
        "returning",
        "overwrite",
        "alternative",
        "ignore",
        "source",
    ):
        _require(
            not statement.args.get(flag),
            "CERTIFIED_INSERT_UNSUPPORTED_MODIFIER",
            f"INSERT modifier {flag!r} is outside certified-insert-v1",
        )

    target = statement.this
    _require(
        isinstance(target, exp.Schema) and isinstance(target.this, exp.Table),
        "CERTIFIED_INSERT_UNSUPPORTED_TARGET",
        "INSERT target must be one plain table with an explicit column list",
    )
    assert isinstance(target, exp.Schema)
    assert isinstance(target.this, exp.Table)
    table_schema, table = _mapped_table_name(target.this, "INSERT target table", namespace_map)
    columns = tuple(_plain_identifier(item, "INSERT target column") for item in target.expressions)
    _require(
        bool(columns),
        "CERTIFIED_INSERT_COLUMN_LIST_REQUIRED",
        "literal INSERT requires an explicit target column list",
    )

    values = statement.expression
    _require(
        isinstance(values, exp.Values),
        "CERTIFIED_INSERT_UNSUPPORTED_SOURCE",
        "INSERT source must be a VALUES clause; INSERT ... SELECT is outside the route",
    )
    assert isinstance(values, exp.Values)
    rows: list[tuple[InsertLiteral, ...]] = []
    for row in values.expressions:
        _require(
            isinstance(row, exp.Tuple),
            "CERTIFIED_INSERT_UNSUPPORTED_SOURCE",
            "INSERT VALUES must contain explicit row tuples",
        )
        assert isinstance(row, exp.Tuple)
        rows.append(tuple(_parse_insert_literal(item) for item in row.expressions))
    return InsertStatement(table=table, columns=columns, rows=tuple(rows), schema=table_schema)


_DML_PREDICATE_OPERATORS = frozenset(
    {
        CheckOperator.EQ,
        CheckOperator.NE,
        CheckOperator.LT,
        CheckOperator.LE,
        CheckOperator.GT,
        CheckOperator.GE,
        CheckOperator.IS_NULL,
        CheckOperator.IS_NOT_NULL,
    }
)


def _parse_dml_column(
    node: exp.Expression,
    what: str,
    allowed_qualifiers: frozenset[str] = frozenset(),
) -> DmlColumn:
    _require(isinstance(node, exp.Column), "CERTIFIED_DML_UNSUPPORTED_PREDICATE", f"{what} must be a column")
    assert isinstance(node, exp.Column)
    qualifier_node = node.args.get("table")
    qualifier = None if qualifier_node is None else _plain_identifier(qualifier_node, f"{what} qualifier")
    if qualifier is not None:
        _require(
            qualifier.casefold() in allowed_qualifiers,
            "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
            f"{what} qualifier {qualifier!r} is outside the joined source scope",
        )
    return DmlColumn(_plain_identifier(node.this, what), qualifier=qualifier)


def _parse_join_predicate(
    node: exp.Expression,
    allowed_qualifiers: frozenset[str],
) -> tuple[DmlJoinCondition, ...]:
    if isinstance(node, exp.And):
        left = node.this
        right = node.expression
        _require(
            isinstance(left, exp.Expression) and isinstance(right, exp.Expression),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "JOIN equality predicate is incomplete",
        )
        return _parse_join_predicate(left, allowed_qualifiers) + _parse_join_predicate(right, allowed_qualifiers)
    _require(
        isinstance(node, exp.EQ),
        "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
        "joined INSERT SELECT supports equality conditions only",
    )
    assert isinstance(node, exp.EQ)
    left = _parse_dml_column(node.this, "JOIN left column", allowed_qualifiers)
    right = _parse_dml_column(node.expression, "JOIN right column", allowed_qualifiers)
    _require(
        left.qualifier != right.qualifier,
        "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
        "JOIN equality must relate two different query sources",
    )
    return (DmlJoinCondition(left, right),)


def _parse_qualified_dml_predicate(
    node: exp.Expression,
    allowed_qualifiers: frozenset[str],
) -> CheckExpression:
    if isinstance(node, exp.And | exp.Or):
        left = node.this
        right = node.expression
        _require(
            isinstance(left, exp.Expression) and isinstance(right, exp.Expression),
            "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
            "DML boolean predicate is incomplete",
        )
        return CheckBooleanExpression(
            CheckConnector.AND if isinstance(node, exp.And) else CheckConnector.OR,
            (
                _parse_qualified_dml_predicate(left, allowed_qualifiers),
                _parse_qualified_dml_predicate(right, allowed_qualifiers),
            ),
        )
    if isinstance(node, exp.Not):
        _require(
            isinstance(node.this, exp.Expression),
            "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
            "DML NOT predicate is incomplete",
        )
        operand = node.this
        if isinstance(operand, exp.Column):
            column = _parse_dml_column(operand, "DML boolean column", allowed_qualifiers)
            return CheckNotExpression(
                CheckComparison(column=column.name, column_qualifier=column.qualifier, operator=CheckOperator.IS_TRUE)
            )
        return CheckNotExpression(_parse_qualified_dml_predicate(operand, allowed_qualifiers))
    if isinstance(node, exp.Is):
        _require(
            isinstance(node.expression, exp.Null),
            "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
            "DML predicates support IS NULL and IS NOT NULL only",
        )
        column = _parse_dml_column(node.this, "DML null-test column", allowed_qualifiers)
        return CheckComparison(
            column=column.name,
            column_qualifier=column.qualifier,
            operator=CheckOperator.IS_NOT_NULL if node.args.get("negate") else CheckOperator.IS_NULL,
        )
    if isinstance(node, exp.Column):
        column = _parse_dml_column(node, "DML boolean column", allowed_qualifiers)
        return CheckComparison(column=column.name, column_qualifier=column.qualifier, operator=CheckOperator.IS_TRUE)
    binary_operator = _CHECK_OPERATOR_MAP.get(type(node))
    _require(
        binary_operator in _DML_PREDICATE_OPERATORS,
        "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
        f"DML predicate operator {type(node).__name__} is outside the bounded route",
    )
    assert binary_operator is not None
    column = _parse_dml_column(node.this, "DML predicate column", allowed_qualifiers)
    right = node.expression
    if isinstance(right, exp.Column):
        right_column = _parse_dml_column(right, "DML predicate right column", allowed_qualifiers)
        return CheckComparison(
            column=column.name,
            column_qualifier=column.qualifier,
            operator=binary_operator,
            right_column=right_column.name,
            right_column_qualifier=right_column.qualifier,
        )
    if isinstance(right, exp.Boolean):
        return CheckComparison(
            column=column.name,
            column_qualifier=column.qualifier,
            operator=binary_operator,
            literal="true" if right.this else "false",
            literal_is_boolean=True,
        )
    _require(
        isinstance(right, exp.Literal),
        "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
        "DML predicate right-hand side must be a literal or column",
    )
    assert isinstance(right, exp.Literal)
    return CheckComparison(
        column=column.name,
        column_qualifier=column.qualifier,
        operator=binary_operator,
        literal=str(right.this),
        literal_is_string=bool(right.is_string),
    )


def _parse_dml_predicate(
    node: exp.Expression,
    source_dialect: Dialect,
    allowed_qualifiers: frozenset[str] = frozenset(),
) -> CheckExpression:
    if allowed_qualifiers:
        return _parse_qualified_dml_predicate(node, allowed_qualifiers)
    comparisons, connector, expression = _parse_check(node, source_dialect)
    parsed: CheckExpression
    if expression is not None:
        parsed = expression
    elif len(comparisons) == 1:
        parsed = comparisons[0]
    else:
        parsed = CheckBooleanExpression(connector or CheckConnector.AND, tuple(comparisons))

    def verify(item: CheckExpression) -> None:
        if isinstance(item, CheckComparison):
            _require(
                item.operator in _DML_PREDICATE_OPERATORS,
                "CERTIFIED_DML_UNSUPPORTED_PREDICATE",
                f"DML predicate operator {item.operator.value!r} is outside the bounded route",
            )
        elif isinstance(item, CheckBooleanExpression):
            for operand in item.operands:
                verify(operand)
        else:
            verify(item.operand)

    verify(parsed)
    return parsed


def _parse_dml_expression(
    node: exp.Expression,
    source_dialect: Dialect,
    allowed_qualifiers: frozenset[str] = frozenset(),
) -> DmlExpression:
    if isinstance(node, exp.Column):
        qualifier_node = node.args.get("table")
        qualifier = None if qualifier_node is None else _plain_identifier(qualifier_node, "DML source column qualifier")
        _require(
            qualifier is None or qualifier.casefold() in allowed_qualifiers,
            "CERTIFIED_DML_UNSUPPORTED_EXPRESSION",
            "DML source column qualifier is outside the joined source scope",
        )
        return DmlColumn(_plain_identifier(node.this, "DML source column"), qualifier=qualifier)
    if isinstance(node, exp.Null | exp.Boolean | exp.Literal | exp.Neg):
        return DmlLiteral(_parse_insert_literal(node))
    if isinstance(node, exp.CurrentTimestamp):
        return DmlCurrentTimestamp()
    if isinstance(node, exp.Coalesce):
        values = [node.this, *(node.expressions or [])]
        _require(
            len(values) == 2 and isinstance(values[0], exp.Column),
            "CERTIFIED_DML_UNSUPPORTED_EXPRESSION",
            "DML COALESCE is limited to one source column and one typed fallback",
        )
        assert isinstance(values[0], exp.Column)
        column = _parse_dml_expression(values[0], source_dialect, allowed_qualifiers)
        _require(
            isinstance(column, DmlColumn),
            "CERTIFIED_DML_UNSUPPORTED_EXPRESSION",
            "DML COALESCE must start with one source column",
        )
        assert isinstance(column, DmlColumn)
        fallback = _parse_dml_expression(values[1], source_dialect, allowed_qualifiers)
        _require(
            isinstance(fallback, DmlLiteral | DmlCurrentTimestamp),
            "CERTIFIED_DML_UNSUPPORTED_EXPRESSION",
            "DML COALESCE fallback must be a literal or transaction timestamp",
        )
        assert isinstance(fallback, DmlLiteral | DmlCurrentTimestamp)
        return DmlCoalesce(column, fallback)
    if isinstance(node, exp.Min):
        _require(
            isinstance(node.this, exp.Column),
            "CERTIFIED_DML_UNSUPPORTED_EXPRESSION",
            "MIN in the bounded INSERT SELECT route must aggregate one source column",
        )
        assert isinstance(node.this, exp.Column)
        column = _parse_dml_expression(node.this, source_dialect, allowed_qualifiers)
        assert isinstance(column, DmlColumn)
        return DmlAggregate(DmlAggregateFunction.MIN, column)
    if isinstance(node, exp.EQ | exp.NEQ | exp.LT | exp.LTE | exp.GT | exp.GTE | exp.Is | exp.And | exp.Or):
        return DmlPredicate(_parse_dml_predicate(node, source_dialect, allowed_qualifiers))
    raise DialectError(
        "CERTIFIED_DML_UNSUPPORTED_EXPRESSION",
        f"DML expression node {type(node).__name__} is outside the typed portable route",
    )


def _parse_insert_target(
    statement: exp.Insert,
    namespace_map: Mapping[str, str] | None,
) -> tuple[str | None, str, tuple[str, ...]]:
    target = statement.this
    _require(
        isinstance(target, exp.Schema) and isinstance(target.this, exp.Table),
        "CERTIFIED_INSERT_UNSUPPORTED_TARGET",
        "INSERT target must be one plain table with an explicit column list",
    )
    assert isinstance(target, exp.Schema)
    assert isinstance(target.this, exp.Table)
    table_schema, table = _mapped_table_name(target.this, "INSERT target table", namespace_map)
    columns = tuple(_plain_identifier(item, "INSERT target column") for item in target.expressions)
    _require(
        bool(columns),
        "CERTIFIED_INSERT_COLUMN_LIST_REQUIRED",
        "INSERT requires an explicit target column list",
    )
    return table_schema, table, columns


def parse_insert_select(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> InsertSelectStatement:
    """Parse a bounded INSERT ... SELECT into typed IR.

    The source query deliberately has no subqueries, ordering, limits, CTEs,
    conflict policy, or vendor clock function. It may use a finite sequence of
    INNER JOINs whose ON clause is only an AND of qualified equalities. These
    restrictions preserve row-set and rerun semantics instead of treating a
    SELECT as opaque source text.
    """
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Insert),
        "CERTIFIED_INSERT_UNSUPPORTED_STATEMENT",
        "certified-dml-v1 only accepts one INSERT statement",
    )
    assert isinstance(statement, exp.Insert)
    for flag in (
        "hint",
        "is_function",
        "stored",
        "by_name",
        "exists",
        "partition",
        "settings",
        "default",
        "conflict",
        "returning",
        "overwrite",
        "alternative",
        "ignore",
    ):
        _require(
            not statement.args.get(flag),
            "CERTIFIED_INSERT_UNSUPPORTED_MODIFIER",
            f"INSERT modifier {flag!r} is outside certified-dml-v1",
        )
    source = statement.expression
    _require(
        isinstance(source, exp.Select),
        "CERTIFIED_INSERT_UNSUPPORTED_SOURCE",
        "INSERT source must be one SELECT in the bounded route",
    )
    assert isinstance(source, exp.Select)
    _require(
        not any(
            source.args.get(flag)
            for flag in ("distinct", "having", "qualify", "order", "limit", "offset", "with")
        ),
        "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
        "INSERT SELECT supports bounded INNER JOINs without ordering, limits or CTEs",
    )
    from_clause = source.args.get("from_")
    _require(
        isinstance(from_clause, exp.From) and isinstance(from_clause.this, exp.Table),
        "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
        "INSERT SELECT needs exactly one source table",
    )
    assert isinstance(from_clause, exp.From)
    assert isinstance(from_clause.this, exp.Table)
    source_schema, source_table = _mapped_table_name(from_clause.this, "INSERT SELECT source table", namespace_map)
    joins: list[DmlJoin] = []
    source_alias_node = from_clause.this.args.get("alias")
    source_alias: str | None = None
    if source.args.get("joins"):
        _require(
            isinstance(source_alias_node, exp.TableAlias) and isinstance(source_alias_node.this, exp.Identifier),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "joined INSERT SELECT sources require a plain base-table alias",
        )
        assert isinstance(source_alias_node, exp.TableAlias)
        assert isinstance(source_alias_node.this, exp.Identifier)
        source_alias = _plain_identifier(source_alias_node.this, "INSERT SELECT source alias")
    else:
        _require(
            source_alias_node is None,
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "source table aliases need a joined query-scope route",
        )
    known_aliases = frozenset({source_alias.casefold()}) if source_alias is not None else frozenset()
    for join in source.args.get("joins") or []:
        _require(
            isinstance(join, exp.Join)
            and not join.args.get("side")
            and not join.args.get("kind")
            and not join.args.get("pivots"),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "only plain INNER JOIN is supported in the bounded INSERT SELECT route",
        )
        assert isinstance(join, exp.Join)
        join_table = join.this
        _require(
            isinstance(join_table, exp.Table),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "JOIN source must be one plain table",
        )
        assert isinstance(join_table, exp.Table)
        alias_node = join_table.args.get("alias")
        _require(
            isinstance(alias_node, exp.TableAlias) and isinstance(alias_node.this, exp.Identifier),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "JOIN sources require a plain alias",
        )
        assert isinstance(alias_node, exp.TableAlias)
        assert isinstance(alias_node.this, exp.Identifier)
        alias = _plain_identifier(alias_node.this, "INSERT SELECT JOIN alias")
        _require(
            alias.casefold() not in known_aliases,
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            f"duplicate INSERT SELECT query source alias {alias!r}",
        )
        join_schema, join_name = _mapped_table_name(join_table, "INSERT SELECT JOIN table", namespace_map)
        _require(
            join.args.get("on") is not None,
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "JOIN requires an ON equality predicate",
        )
        assert isinstance(join.args.get("on"), exp.Expression)
        aliases = frozenset((*known_aliases, alias.casefold()))
        conditions = _parse_join_predicate(join.args["on"], aliases)
        joins.append(DmlJoin(join_name, alias, conditions, schema=join_schema))
        known_aliases = aliases
    table_schema, table, columns = _parse_insert_target(statement, namespace_map)
    expressions = tuple(
        _parse_dml_expression(item, source_dialect, known_aliases) for item in source.expressions
    )
    _require(
        len(columns) == len(expressions),
        "CERTIFIED_INSERT_ARITY_MISMATCH",
        "INSERT SELECT projection must match the target column list",
    )
    where = source.args.get("where")
    predicate = None
    if where is not None:
        _require(
            isinstance(where, exp.Where),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "INSERT SELECT WHERE clause is malformed",
        )
        predicate = _parse_dml_predicate(where.this, source_dialect, known_aliases)
    group_by: tuple[str, ...] = ()
    group = source.args.get("group")
    if group is not None:
        _require(
            isinstance(group, exp.Group),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "INSERT SELECT GROUP BY clause is malformed",
        )
        group_by = tuple(_plain_identifier(item, "INSERT SELECT GROUP BY column") for item in group.expressions)
        _require(
            bool(group_by),
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
            "INSERT SELECT GROUP BY requires at least one column",
        )
    return InsertSelectStatement(
        table=table,
        columns=columns,
        source_table=source_table,
        expressions=expressions,
        predicate=predicate,
        group_by=group_by,
        schema=table_schema,
        source_schema=source_schema,
        source_alias=source_alias,
        joins=tuple(joins),
    )


def parse_insert_statement(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> InsertStatement | InsertSelectStatement:
    """Select the literal or bounded SELECT INSERT profile without widening either."""
    try:
        return parse_insert(sql, source_dialect, namespace_map)
    except DialectError as exc:
        if exc.code != "CERTIFIED_INSERT_UNSUPPORTED_SOURCE":
            raise
        return parse_insert_select(sql, source_dialect, namespace_map)


def parse_update(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> UpdateStatement:
    """Parse a single-table UPDATE with typed values and predicates."""
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Update),
        "CERTIFIED_UPDATE_UNSUPPORTED_STATEMENT",
        "certified-dml-v1 only accepts one UPDATE statement",
    )
    assert isinstance(statement, exp.Update)
    _require(
        statement.args.get("from_") is None,
        "CERTIFIED_UPDATE_UNSUPPORTED_SOURCE",
        "UPDATE ... FROM changes row-source semantics and needs a target-specific route",
    )
    _require(
        not any(statement.args.get(flag) for flag in ("order", "limit", "with")),
        "CERTIFIED_UPDATE_UNSUPPORTED_MODIFIER",
        "UPDATE ORDER BY, LIMIT and CTE modifiers are outside certified-dml-v1",
    )
    schema, table = _mapped_table_name(statement.this, "UPDATE target table", namespace_map)
    assignments: list[UpdateAssignment] = []
    for item in statement.expressions:
        _require(
            isinstance(item, exp.EQ) and isinstance(item.this, exp.Column),
            "CERTIFIED_UPDATE_UNSUPPORTED_ASSIGNMENT",
            "UPDATE assignments must be plain column = typed expression pairs",
        )
        assert isinstance(item, exp.EQ)
        assert isinstance(item.this, exp.Column)
        _require(
            item.this.args.get("table") is None,
            "CERTIFIED_UPDATE_UNSUPPORTED_ASSIGNMENT",
            "UPDATE assignment targets must be unqualified columns",
        )
        target = _plain_identifier(item.this.this, "UPDATE assignment target")
        assignments.append(UpdateAssignment(target, _parse_dml_expression(item.expression, source_dialect)))
    where = statement.args.get("where")
    predicate = None
    if where is not None:
        _require(
            isinstance(where, exp.Where),
            "CERTIFIED_UPDATE_UNSUPPORTED_PREDICATE",
            "UPDATE WHERE clause is malformed",
        )
        predicate = _parse_dml_predicate(where.this, source_dialect)
    return UpdateStatement(table=table, assignments=tuple(assignments), predicate=predicate, schema=schema)


def _alter_table_name(
    statement: exp.Alter,
    namespace_map: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    table_ref = statement.this
    _require(isinstance(table_ref, exp.Table), "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT", "malformed ALTER TABLE")
    return _mapped_table_name(table_ref, "table name", namespace_map)


def _parse_add_column(
    col_def: exp.ColumnDef,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> AddColumn:
    column_name = _plain_identifier(col_def.this, "column name")
    _require(
        col_def.kind is not None,
        "CERTIFIED_ALTER_MISSING_TYPE",
        f"added column {column_name!r} is missing a type",
    )
    assert col_def.kind is not None  # narrows for mypy; _require enforced it at runtime
    type_ref = _parse_type(col_def.kind, source_dialect)
    (nullable, default, auto_increment, pk_shorthand, unique_shorthand, inline_fk, inline_checks) = _column_constraints(
        col_def, type_ref, column_name, source_dialect, namespace_map
    )
    auto_increment = auto_increment or col_def.kind.this in _SERIAL_TYPES
    # A PRIMARY KEY or UNIQUE shorthand on an added column is a table-level
    # constraint change wearing a column's clothes, and the four dialects
    # differ on whether it may be combined with ADD COLUMN at all. Adding
    # the column and the constraint as separate actions is the portable
    # form, so this refuses the shorthand rather than silently splitting it.
    _require(
        not pk_shorthand,
        "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT",
        f"inline PRIMARY KEY on added column {column_name!r} is outside certified-alter-v1; "
        "add the column and the constraint as separate actions",
    )
    _require(
        not unique_shorthand,
        "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT",
        f"inline UNIQUE on added column {column_name!r} is outside certified-alter-v1; "
        "add the column and the constraint as separate actions",
    )
    _require(
        len(inline_checks) <= 1,
        "CERTIFIED_ALTER_UNSUPPORTED_COLUMN_CONSTRAINT",
        f"added column {column_name!r} declares more than one inline CHECK",
    )
    column = Column(
        name=column_name,
        type_ref=type_ref,
        nullable=nullable,
        default=default,
        auto_increment=auto_increment,
    )
    return AddColumn(column=column, foreign_key=inline_fk, check=inline_checks[0] if inline_checks else None)


def _parse_alter_constraint(
    inner: exp.Expression,
    name: str | None,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> AddConstraint:
    if isinstance(inner, exp.PrimaryKey):
        return AddConstraint(
            name=name, primary_key=tuple(_plain_identifier(e, "PRIMARY KEY column") for e in inner.expressions)
        )
    if isinstance(inner, exp.UniqueColumnConstraint):
        target = inner.this
        _require(
            isinstance(target, exp.Schema),
            "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT",
            "ADD UNIQUE must list explicit columns",
        )
        return AddConstraint(name=name, unique=tuple(_plain_identifier(e, "UNIQUE column") for e in target.expressions))
    if isinstance(inner, exp.ForeignKey):
        columns = tuple(_plain_identifier(e, "FOREIGN KEY column") for e in inner.expressions)
        reference = inner.args.get("reference")
        _require(reference is not None, "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT", "ADD FOREIGN KEY requires REFERENCES")
        assert reference is not None  # narrows for mypy; _require enforced it at runtime
        return AddConstraint(name=name, foreign_key=_parse_reference(reference, columns, name, namespace_map))
    if isinstance(inner, exp.CheckColumnConstraint):
        comparisons, connector, expression = _parse_check(inner.this, source_dialect)
        return AddConstraint(
            name=name,
            check=CheckConstraint(comparisons=comparisons, connector=connector, expression=expression, name=name),
        )
    raise DialectError(
        "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT",
        f"ADD CONSTRAINT clause {type(inner).__name__} is outside certified-alter-v1",
    )


def parse_alter_table(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> AlterTable:
    """Parse one ALTER TABLE into the canonical certified-alter-v1 model."""
    statement = _statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Alter),
        "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT",
        "certified-alter-v1 only accepts a single ALTER TABLE statement",
    )
    assert isinstance(statement, exp.Alter)  # narrows for mypy
    _require(
        str(statement.args.get("kind", "TABLE")).upper() == "TABLE",
        "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT",
        f"ALTER {statement.args.get('kind')} is outside certified-alter-v1",
    )
    _require(
        not statement.args.get("exists"),
        "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT_MODIFIER",
        "ALTER TABLE IF EXISTS is outside certified-alter-v1",
    )

    table_schema, table = _alter_table_name(statement, namespace_map)
    actions: list[AlterAction] = []
    for action in statement.args.get("actions") or []:
        if isinstance(action, exp.ColumnDef):
            actions.append(_parse_add_column(action, source_dialect, namespace_map))
        elif isinstance(action, exp.AlterRename):
            raise DialectError("CERTIFIED_ALTER_UNSUPPORTED_ACTION", "RENAME TABLE is outside certified-alter-v1")
        elif isinstance(action, exp.RenameColumn):
            _require(
                not action.args.get("exists"),
                "CERTIFIED_ALTER_UNSUPPORTED_STATEMENT_MODIFIER",
                "RENAME COLUMN IF EXISTS is outside certified-alter-v1",
            )
            actions.append(
                RenameColumn(
                    column=_plain_identifier(action.this, "renamed column"),
                    new_name=_plain_identifier(action.args.get("to"), "new column name"),
                )
            )
        elif isinstance(action, exp.AddConstraint):
            for inner in action.expressions:
                if isinstance(inner, exp.Constraint):
                    constraint_name = (
                        _plain_identifier(inner.this, "constraint name") if inner.this is not None else None
                    )
                    _require(
                        len(inner.expressions) == 1,
                        "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT",
                        "a named constraint must contain exactly one constraint clause",
                    )
                    actions.append(
                        _parse_alter_constraint(inner.expressions[0], constraint_name, source_dialect, namespace_map)
                    )
                else:
                    actions.append(_parse_alter_constraint(inner, None, source_dialect, namespace_map))
        elif isinstance(action, exp.Drop):
            drop_kind = str(action.args.get("kind", "")).upper()
            if drop_kind == "COLUMN":
                actions.append(
                    DropColumn(
                        column=_plain_identifier(
                            action.this.this if isinstance(action.this, exp.Column) else action.this, "dropped column"
                        )
                    )
                )
            elif drop_kind == "CONSTRAINT":
                # sqlglot wraps the constraint name in a Table node here,
                # so the identifier has to be unwrapped one level.
                target = action.this
                if isinstance(target, exp.Table | exp.Column):
                    target = target.this
                actions.append(DropConstraint(name=_plain_identifier(target, "dropped constraint")))
            else:
                raise DialectError(
                    "CERTIFIED_ALTER_UNSUPPORTED_ACTION",
                    f"ALTER TABLE DROP {drop_kind or '?'} is outside certified-alter-v1",
                )
        else:
            raise DialectError(
                "CERTIFIED_ALTER_UNSUPPORTED_ACTION",
                f"ALTER TABLE action {type(action).__name__} is outside certified-alter-v1 "
                "(column type/nullability/default changes need the column's full type, "
                "which a single ALTER statement does not carry)",
            )
    return AlterTable(table=table, actions=tuple(actions), schema=table_schema)
