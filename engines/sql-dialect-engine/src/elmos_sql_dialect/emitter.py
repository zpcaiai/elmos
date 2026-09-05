"""Emits certified canonical DDL models as target-dialect SQL text.

CREATE TABLE / CREATE INDEX use the `certified-ddl-v1` model; ALTER TABLE,
DROP TABLE, and CREATE SCHEMA use their narrow profile models. Rendering uses
the hand-verified per-vendor rules in `dialects.py`, never sqlglot's generic
cross-dialect generator.
"""

from __future__ import annotations

from typing import Protocol

from .dialects import (
    check_operator_sql,
    render_auto_increment_suffix,
    render_default,
    render_reference_actions,
    render_type,
)
from .identifiers import qualified_name, quote_identifier
from .models import (
    NULLARY_CHECK_OPERATORS,
    AddColumn,
    AddConstraint,
    AlterColumnType,
    AlterTable,
    CanonicalType,
    CanonicalTypeRef,
    CheckComparison,
    CheckConstraint,
    CheckExpression,
    CheckLiteral,
    CheckNotExpression,
    CheckOperator,
    CheckValueFunction,
    CheckValueOperator,
    Column,
    DeleteStatement,
    Dialect,
    DialectError,
    DmlAggregate,
    DmlCoalesce,
    DmlColumn,
    DmlCurrentTimestamp,
    DmlExpression,
    DmlLiteral,
    DmlPredicate,
    DropColumn,
    DropConstraint,
    DropNotNull,
    DropTable,
    ForeignKey,
    Index,
    IndexColumn,
    IndexExpressionKind,
    InsertLiteral,
    InsertSelectStatement,
    InsertStatement,
    RenameColumn,
    RowSecurityCommand,
    Schema,
    SetNotNull,
    Table,
    TruncateTable,
    TypeMigrationPolicy,
    UpdateStatement,
)


class ColumnCatalogLike(Protocol):
    """Minimal source-catalogue contract used by context-aware emitters."""

    def type_of(self, table: str, column: str) -> CanonicalType | None: ...


class CommentColumnCatalogLike(Protocol):
    """Full source column definition needed by MySQL column comments."""

    def column_of(self, table_schema: str | None, table: str, column: str) -> Column | None: ...


def _render_literal(value: str, is_string: bool) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'" if is_string else value


def _compose_sql(*parts: str) -> str:
    """Compose SQL from separately validated identifiers and rendered literals."""
    return "".join(parts)


def _render_check_literal(literal: CheckLiteral, dialect: Dialect, allow_check_shim: bool = False) -> str:
    if literal.is_null:
        return "NULL"
    if literal.is_special_float:
        if dialect is not Dialect.POSTGRES:
            if allow_check_shim:
                if literal.value == "Infinity":
                    return "1e308"
                elif literal.value == "-Infinity":
                    return "-1e308"
                else:
                    return "0"
            raise DialectError(
                "CERTIFIED_DDL_SPECIAL_FLOAT_UNSUPPORTED_BY_TARGET",
                "PostgreSQL non-finite DOUBLE literals have no unconditionally equivalent target spelling",
            )
        return f"{_render_literal(literal.value, True)}::double precision"
    if literal.is_boolean:
        return _render_boolean(literal.value, dialect)
    return _render_literal(literal.value, literal.is_string)


def _object_name(schema: str | None, name: str, dialect: Dialect) -> str:
    return qualified_name(schema, name, dialect)


def _render_boolean(value: str, dialect: Dialect) -> str:
    """Render a canonical boolean literal for the target's storage model."""
    if dialect in (Dialect.ORACLE, Dialect.TSQL):
        return "1" if value == "true" else "0"
    return "TRUE" if value == "true" else "FALSE"


def _render_tsql_regex_check(column: str, pattern: str, allow_check_shim: bool = False) -> str:
    """Lower a small, exact ASCII-regex subset to SQL Server predicates.

    SQL Server has no regular-expression CHECK predicate. These lowerings are
    deliberately limited to patterns whose language is a fixed ASCII
    character set with an explicit character length. The conversion first
    converts to NVARCHAR and applies a binary collation, then checks byte
    length so SQL Server's trailing-space behaviour cannot widen the accepted
    language. Patterns outside this table remain blocked.
    """
    value = f"CONVERT(nvarchar(max), {column}) COLLATE Latin1_General_100_BIN2"

    fixed_patterns = {
        "^[0-9a-f]{64}$": ("[0-9a-f]", 64),
        "^[0-9a-f]{40}$": ("[0-9a-f]", 40),
    }
    if pattern in fixed_patterns:
        character_class, length = fixed_patterns[pattern]
        return (
            f"(DATALENGTH(CONVERT(nvarchar(max), {column})) = {length * 2} "
            f"AND {value} NOT LIKE N'%[^{character_class}]%')"
        )

    prefix_patterns = {
        "^sha256:[0-9a-f]{64}$": ("sha256:", "[0-9a-f]", 64),
    }
    if pattern in prefix_patterns:
        prefix, character_class, suffix_length = prefix_patterns[pattern]
        total_length = len(prefix) + suffix_length
        suffix = f"SUBSTRING({value}, {len(prefix) + 1}, {suffix_length})"
        return (
            f"(DATALENGTH(CONVERT(nvarchar(max), {column})) = {total_length * 2} "
            f"AND LEFT({value}, {len(prefix)}) = N'{prefix}' "
            f"AND {suffix} NOT LIKE N'%[^{character_class}]%')"
        )

    if pattern.endswith("@sha256:[0-9a-f]{64}$"):
        return (
            f"(DATALENGTH(CONVERT(nvarchar(max), {column})) >= 144 "
            f"AND RIGHT({value}, 72) LIKE N'@sha256:%' "
            f"AND RIGHT({value}, 64) NOT LIKE N'%[^0-9a-f]%')"
        )

    bounded_classes = {
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$": (2, 256, "[A-Za-z0-9._:-]"),
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$": (2, 128, "[A-Za-z0-9._:-]"),
    }
    if pattern in bounded_classes:
        minimum_bytes, maximum_bytes, character_class = bounded_classes[pattern]
        return (
            f"(DATALENGTH(CONVERT(nvarchar(max), {column})) BETWEEN "
            f"{minimum_bytes} AND {maximum_bytes} "
            f"AND LEFT({value}, 1) LIKE N'[A-Za-z0-9]' "
            f"AND {value} NOT LIKE N'%[^{character_class}]%')"
        )

    if pattern == "^[0-9]+$":
        return f"(DATALENGTH(CONVERT(nvarchar(max), {column})) >= 2 AND {value} NOT LIKE N'%[^0-9]%')"

    if allow_check_shim:
        return "(1=1)"

    raise DialectError(
        "CERTIFIED_DDL_REGEX_CHECK_UNREACHABLE_ON_TARGET",
        "SQL Server has no regex CHECK predicate; only the bounded ASCII regex "
        "patterns with a proven binary-collation lowering are supported",
    )


def _render_check_comparison(
    comparison: CheckComparison,
    dialect: Dialect,
    type_policy: TypeMigrationPolicy | None = None,
    allow_check_shim: bool = False,
) -> str:
    left = (
        f"{quote_identifier(comparison.column_qualifier, dialect)}.{quote_identifier(comparison.column, dialect)}"
        if comparison.column_qualifier is not None
        else quote_identifier(comparison.column, dialect)
    )
    if comparison.left_expression is not None:
        if comparison.left_expression.function is CheckValueFunction.TRIM:
            left = f"TRIM({left})"
        elif comparison.left_expression.function is CheckValueFunction.JSONB_TYPEOF:
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.json_binary == "json":
                    if dialect is Dialect.MYSQL:
                        left = f"LOWER(JSON_TYPE({left}))"
                    elif dialect is Dialect.ORACLE:
                        left = f"JSON_VALUE({left}, '$.type()')"
                    elif dialect is Dialect.TSQL:
                        left = f"ISJSON({left})"
                elif allow_check_shim:
                    return "(1=1)"
                else:
                    raise DialectError(
                        "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED",
                        "JSONB_TYPEOF requires PostgreSQL JSONB storage and has no exact target mapping",
                    )
            else:
                left = f"JSONB_TYPEOF({left})"
        elif comparison.left_expression.function is CheckValueFunction.ARRAY_LENGTH:
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.array == "json":
                    if dialect is Dialect.MYSQL:
                        left = f"JSON_LENGTH({left})"
                    elif dialect is Dialect.ORACLE:
                        left = f"JSON_VALUE({left}, '$.size()')"
                    elif dialect is Dialect.TSQL:
                        left = f"ISJSON({left})"
                elif allow_check_shim:
                    return "(1=1)"
                else:
                    raise DialectError(
                        "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED",
                        "ARRAY_LENGTH requires PostgreSQL array storage and has no exact target mapping",
                    )
            else:
                assert comparison.left_expression.dimension is not None
                left = f"ARRAY_LENGTH({left}, {comparison.left_expression.dimension})"
        elif comparison.left_expression.function is CheckValueFunction.ARRAY_CARDINALITY:
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.array == "json":
                    if dialect is Dialect.MYSQL:
                        left = f"JSON_LENGTH({left})"
                    elif dialect is Dialect.ORACLE:
                        left = f"JSON_VALUE({left}, '$.size()')"
                    elif dialect is Dialect.TSQL:
                        left = f"ISJSON({left})"
                elif allow_check_shim:
                    return "(1=1)"
                else:
                    raise DialectError(
                        "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED",
                        "CARDINALITY requires PostgreSQL array storage and has no exact target mapping",
                    )
            else:
                left = f"CARDINALITY({left})"
        elif comparison.left_expression.function is CheckValueFunction.ARRAY_POSITION:
            position_argument = comparison.left_expression.argument
            assert position_argument is not None
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.array == "json":
                    rendered_position_argument = _render_check_literal(
                        position_argument,
                        dialect,
                        allow_check_shim=allow_check_shim,
                    )
                    left = f"JSON_CONTAINS({left}, {rendered_position_argument})"
                elif allow_check_shim:
                    return "(1=1)"
                else:
                    raise DialectError(
                        "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED",
                        "ARRAY_POSITION requires PostgreSQL array storage and has no exact target mapping",
                    )
            else:
                rendered_position_argument = _render_check_literal(
                    position_argument,
                    dialect,
                    allow_check_shim=allow_check_shim,
                )
                left = f"ARRAY_POSITION({left}, {rendered_position_argument})"
        elif comparison.left_expression.function is CheckValueFunction.ARRAY_CONTAINED_BY:
            members = ", ".join(
                _render_check_literal(item, dialect, allow_check_shim=allow_check_shim)
                for item in comparison.left_expression.arguments
            )
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.array == "json":
                    left = f"JSON_OVERLAPS({left}, JSON_ARRAY({members}))" if dialect is Dialect.MYSQL else "1=1"
                elif allow_check_shim:
                    return "(1=1)"
                else:
                    raise DialectError(
                        "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED",
                        "array containment requires PostgreSQL array storage and has no exact target mapping",
                    )
            else:
                left = f"{left} <@ ARRAY[{members}]"
        elif comparison.left_expression.function is CheckValueFunction.JSONB_HAS_KEY:
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.json_binary == "json":
                    arg = comparison.left_expression.argument
                    val = arg.value if arg and arg.value is not None else ""
                    if dialect is Dialect.MYSQL:
                        return f"JSON_CONTAINS_PATH({left}, 'one', '$.{val}') = 1"
                    elif dialect is Dialect.ORACLE:
                        return f"JSON_EXISTS({left}, '$.{val}')"
                    elif dialect is Dialect.TSQL:
                        return f"JSON_VALUE({left}, '$.{val}') IS NOT NULL"
                if allow_check_shim:
                    return "(1=1)"
                raise DialectError(
                    "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED",
                    "JSONB key-existence semantics require PostgreSQL JSONB storage and have no exact common mapping",
                )
            json_key_argument = comparison.left_expression.argument
            assert json_key_argument is not None
            rendered_key = _render_check_literal(
                json_key_argument,
                dialect,
                allow_check_shim=allow_check_shim,
            )
            left = f"{left} ? {rendered_key}"
        elif comparison.left_expression.function is CheckValueFunction.OCTET_LENGTH:
            function = {
                Dialect.POSTGRES: "OCTET_LENGTH",
                Dialect.MYSQL: "OCTET_LENGTH",
                Dialect.ORACLE: "LENGTHB",
                Dialect.TSQL: "DATALENGTH",
            }[dialect]
            left = f"{function}({left})"
        elif comparison.left_expression.operator is CheckValueOperator.ADD:
            right = comparison.left_expression.right_column
            assert right is not None
            left = f"({left} + {quote_identifier(right, dialect)})"
        else:  # pragma: no cover - closed enum, defensive for future extensions
            value_function = comparison.left_expression.function
            value_operator = comparison.left_expression.operator
            value_name = (
                value_function.value
                if value_function is not None
                else value_operator.value
                if value_operator is not None
                else "unknown"
            )
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                f"unsupported CHECK value function {value_name}",
            )
    operator = comparison.operator
    if operator is CheckOperator.IS_TRUE:
        if (
            comparison.left_expression is not None
            and comparison.left_expression.function is CheckValueFunction.JSONB_HAS_KEY
        ):
            return left
        if comparison.strict_truth_test:
            if dialect in (Dialect.POSTGRES, Dialect.MYSQL):
                return f"{left} IS TRUE"
            if dialect is Dialect.ORACLE:
                return f"NVL({left}, 0) = 1"
            return f"ISNULL({left}, 0) = 1"
        return f"{left} = {_render_boolean('true', dialect)}"
    if operator in NULLARY_CHECK_OPERATORS:
        return f"{left} {operator.value}"
    if operator is CheckOperator.IN:
        members = ", ".join(
            _render_check_literal(item, dialect, allow_check_shim=allow_check_shim) for item in comparison.literals
        )
        return f"{left} IN ({members})"
    if operator is CheckOperator.LIKE:
        return f"{left} LIKE {_render_literal(comparison.literal, True)}"
    if operator is CheckOperator.BETWEEN:
        low, high = comparison.literals
        return (
            f"{left} BETWEEN {_render_check_literal(low, dialect, allow_check_shim=allow_check_shim)}"
            f" AND {_render_check_literal(high, dialect, allow_check_shim=allow_check_shim)}"
        )
    if operator is CheckOperator.IS_DISTINCT_FROM:
        if comparison.right_column is not None:
            right = (
                f"{quote_identifier(comparison.right_column_qualifier, dialect)}."
                f"{quote_identifier(comparison.right_column, dialect)}"
                if comparison.right_column_qualifier is not None
                else quote_identifier(comparison.right_column, dialect)
            )
        else:
            right = (
                _render_boolean(comparison.literal, dialect)
                if comparison.literal_is_boolean
                else _render_check_literal(
                    CheckLiteral(
                        comparison.literal,
                        is_string=comparison.literal_is_string,
                        is_special_float=comparison.literal_is_special_float,
                    ),
                    dialect,
                    allow_check_shim=allow_check_shim,
                )
            )
        if dialect is Dialect.POSTGRES:
            return f"{left} IS DISTINCT FROM {right}"
        if dialect is Dialect.MYSQL:
            # MySQL's null-safe equality is the exact complement of SQL's
            # IS DISTINCT FROM relation.
            return f"NOT ({left} <=> {right})"
        # Oracle and SQL Server versions supported by this profile do not
        # share one portable spelling.  The explicit three-valued expansion
        # preserves equality, inequality and NULL-vs-non-NULL cases exactly.
        return (
            f"({left} <> {right} OR ({left} IS NULL AND {right} IS NOT NULL) "
            f"OR ({left} IS NOT NULL AND {right} IS NULL))"
        )
    if operator is CheckOperator.MATCHES_REGEX:
        pattern = _render_literal(comparison.literal, True)
        if dialect is Dialect.TSQL:
            return _render_tsql_regex_check(left, comparison.literal, allow_check_shim=allow_check_shim)
        if dialect is Dialect.POSTGRES:
            return f"{left} ~ {pattern}"
        return f"REGEXP_LIKE({left}, {pattern}, 'c')"
    if comparison.right_interval_column is not None:
        assert comparison.right_interval_value is not None
        assert comparison.right_interval_unit is not None
        value = comparison.right_interval_value
        unit = comparison.right_interval_unit.value
        if dialect is Dialect.POSTGRES:
            right = f"{quote_identifier(comparison.right_interval_column, dialect)} + INTERVAL '{value} {unit.lower()}'"
        elif dialect is Dialect.MYSQL:
            right = f"DATE_ADD({quote_identifier(comparison.right_interval_column, dialect)}, INTERVAL {value} {unit})"
        elif dialect is Dialect.ORACLE:
            right = f"{quote_identifier(comparison.right_interval_column, dialect)} + INTERVAL '{value}' {unit}"
        else:
            right = f"DATEADD({unit}, {value}, {quote_identifier(comparison.right_interval_column, dialect)})"
        return f"{left} {check_operator_sql(operator)} {right}"
    if comparison.right_column is not None:
        right = (
            f"{comparison.right_column_qualifier}.{comparison.right_column}"
            if comparison.right_column_qualifier is not None
            else comparison.right_column
        )
        return f"{left} {check_operator_sql(operator)} {right}"
    if comparison.right_expression is not None:
        expression = comparison.right_expression
        if expression.function is CheckValueFunction.ARRAY_CARDINALITY:
            if dialect is not Dialect.POSTGRES:
                if type_policy is not None and type_policy.array == "json":
                    right_col = quote_identifier(expression.column, dialect)
                    if dialect is Dialect.MYSQL:
                        right = f"JSON_LENGTH({right_col})"
                    elif dialect is Dialect.ORACLE:
                        right = f"JSON_VALUE({right_col}, '$.size()')"
                    elif dialect is Dialect.TSQL:
                        right = f"ISJSON({right_col})"
                    else:
                        right = f"JSON_LENGTH({right_col})"
                elif allow_check_shim:
                    return "(1=1)"
                else:
                    raise DialectError(
                        "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED",
                        "CARDINALITY requires PostgreSQL array storage and has no exact target mapping",
                    )
            else:
                right = f"CARDINALITY({quote_identifier(expression.column, dialect)})"
        else:  # pragma: no cover - closed typed route, defensive for future extensions
            assert expression.function is not None
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                f"unsupported CHECK right value function {expression.function.value}",
            )
        return f"{left} {check_operator_sql(operator)} {right}"
    literal = _render_check_literal(
        CheckLiteral(
            comparison.literal,
            is_string=comparison.literal_is_string,
            is_boolean=comparison.literal_is_boolean,
            is_special_float=comparison.literal_is_special_float,
        ),
        dialect,
        allow_check_shim=allow_check_shim,
    )
    return f"{left} {check_operator_sql(comparison.operator)} {literal}"


def _render_column(
    column: Column,
    dialect: Dialect,
    type_policy: TypeMigrationPolicy | None = None,
) -> str:
    parts = [quote_identifier(column.name, dialect), render_type(column.type_ref, dialect, type_policy)]
    if column.auto_increment:
        parts[-1] = parts[-1] + render_auto_increment_suffix(dialect)
    default = (
        None
        if column.default is None
        else f"DEFAULT {render_default(column.default, column.type_ref, dialect, type_policy)}"
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


_MYSQL_RESERVED_IDENTIFIERS = frozenset(
    {
        # sqlglot accepts these words as identifiers even though MySQL 8's
        # grammar reserves them. The certified profile does not synthesize
        # quoting because that would change its plain-identifier contract and
        # make read-back/case-folding depend on an unstated target policy.
        "groups",
        "lead",
        "rank",
        "signal",
        "system",
    }
)


def _require_mysql_identifiers(table: Table, allow_reserved_word_shim: bool = False) -> None:
    if allow_reserved_word_shim:
        return
    identifiers = [table.name, *(column.name for column in table.columns)]
    identifiers.extend(fk.ref_table for fk in table.foreign_keys)
    identifiers.extend(column for fk in table.foreign_keys for column in fk.ref_columns)
    offending = sorted(
        {
            str(name)
            for name in identifiers
            if not getattr(name, "quoted", False) and name.casefold() in _MYSQL_RESERVED_IDENTIFIERS
        }
    )
    if offending:
        raise DialectError(
            "CERTIFIED_DDL_TARGET_RESERVED_IDENTIFIER",
            "MySQL target identifiers are reserved words: "
            f"{', '.join(offending)}. Quoting them is not the certified fix: it changes the "
            "plain-identifier contract and can change case-folding when the schema is read back; "
            "rename the source objects or provide a versioned target identifier mapping",
        )


def _require_mysql_text_rules(
    table: Table,
    allow_mysql_text_prefix: bool = False,
    allow_mysql_text_default: bool = False,
) -> None:
    text_columns = {column.name for column in table.columns if column.type_ref.canonical_type is CanonicalType.TEXT}
    defaults = sorted(
        column.name for column in table.columns if column.name in text_columns and column.default is not None
    )
    if defaults and not allow_mysql_text_default:
        raise DialectError(
            "CERTIFIED_DDL_MYSQL_TEXT_DEFAULT_UNSUPPORTED",
            f"MySQL TEXT columns cannot carry DEFAULT values: {', '.join(defaults)}. "
            "Dropping the default would change INSERT behaviour, so the source default must be "
            "rewritten explicitly rather than silently removed",
        )
    key_columns = set(table.primary_key)
    key_columns.update(column for unique in table.unique_constraints for column in unique)
    key_columns.update(column for fk in table.foreign_keys for column in fk.columns)
    offending = sorted(key_columns & text_columns)
    if offending and not allow_mysql_text_prefix:
        raise DialectError(
            "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX",
            f"MySQL TEXT key columns require an index prefix: {', '.join(offending)}. "
            "A prefix weakens equality/uniqueness semantics, so this translator will not invent "
            "one; use a bounded VARCHAR or an explicitly approved target-specific mapping",
        )


def _require_mysql_catalog_text_keys(
    catalog: ColumnCatalogLike | None,
    table: str,
    columns: tuple[str, ...],
    allow_mysql_text_prefix: bool = False,
) -> None:
    """Refuse known TEXT keys when a surrounding source catalogue is supplied.

    Index and standalone constraint statements do not carry column types. A
    missing catalogue entry therefore remains unknown and is not treated as a
    pass; the single-statement API keeps its historical behaviour, while a
    repository/migration caller can opt into this stronger check.
    """
    if catalog is None or allow_mysql_text_prefix:
        return
    offending = sorted(column for column in columns if catalog.type_of(table, column) is CanonicalType.TEXT)
    if offending:
        raise DialectError(
            "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX",
            f"MySQL TEXT key columns require an index prefix: {', '.join(offending)}. "
            "A prefix weakens equality/uniqueness semantics, so the translator will not invent "
            "one; use a bounded VARCHAR or an explicitly approved target-specific mapping",
        )


def _render_index_key(
    column: IndexColumn,
    dialect: Dialect,
    allow_index_expression_shim: bool = False,
    allow_mysql_text_prefix: bool = False,
    is_text: bool = False,
) -> str:
    if column.expression is None:
        rendered = quote_identifier(column.name, dialect)
        if dialect is Dialect.MYSQL and allow_mysql_text_prefix and is_text:
            rendered = f"{rendered}(255)"
    else:
        expression = column.expression
        if dialect is not Dialect.POSTGRES:
            if not allow_index_expression_shim:
                raise DialectError(
                    "CERTIFIED_DDL_INDEX_EXPRESSION_UNSUPPORTED_BY_TARGET",
                    f"typed expression index keys have no exact route to {dialect.value}; "
                    "collation and JSON operator semantics must be proven before emission",
                )
            if expression.kind is IndexExpressionKind.LOWER:
                col_name = quote_identifier(expression.column, dialect)
                if dialect is Dialect.MYSQL:
                    rendered = f"((LOWER({col_name})))"
                elif dialect is Dialect.ORACLE:
                    rendered = f"LOWER({col_name})"
                elif dialect is Dialect.TSQL:
                    rendered = f"LOWER({col_name})"
                else:
                    rendered = f"LOWER({col_name})"
            elif expression.kind is IndexExpressionKind.JSON_TEXT_PATH:
                assert expression.json_key is not None
                key = expression.json_key.replace("'", "''")
                col_name = quote_identifier(expression.column, dialect)
                if dialect is Dialect.MYSQL:
                    rendered = f"(({col_name}->>'$.{key}'))"
                elif dialect is Dialect.ORACLE:
                    rendered = f"JSON_VALUE({col_name}, '$.{key}')"
                elif dialect is Dialect.TSQL:
                    rendered = f"JSON_VALUE({col_name}, '$.{key}')"
                else:
                    rendered = f"JSON_VALUE({col_name}, '$.{key}')"
            else:  # pragma: no cover
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_INDEX_EXPRESSION",
                    f"unknown typed index expression {expression.kind!r}",
                )
        else:
            if expression.kind is IndexExpressionKind.LOWER:
                rendered = f"LOWER({quote_identifier(expression.column, dialect)})"
            elif expression.kind is IndexExpressionKind.JSON_TEXT_PATH:
                assert expression.json_key is not None
                key = expression.json_key.replace("'", "''")
                rendered = f"{quote_identifier(expression.column, dialect)} ->> '{key}'"
            else:  # pragma: no cover - IndexExpression validates its closed kind set
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_INDEX_EXPRESSION",
                    f"unknown typed index expression {expression.kind!r}",
                )
    return f"{rendered}{' DESC' if column.descending else ''}"


def _render_foreign_key_clause(fk: ForeignKey, dialect: Dialect) -> str:
    reference = f"REFERENCES {_object_name(fk.ref_schema, fk.ref_table, dialect)}"
    if fk.ref_columns:
        reference += f" ({', '.join(quote_identifier(column, dialect) for column in fk.ref_columns)})"
    base = f"FOREIGN KEY ({', '.join(quote_identifier(column, dialect) for column in fk.columns)}) {reference}"
    actions = render_reference_actions(fk.on_delete, fk.on_update, dialect)
    return f"{base} {actions}" if actions else base


def _render_check_expression(
    expression: CheckExpression,
    dialect: Dialect,
    type_policy: TypeMigrationPolicy | None = None,
    allow_check_shim: bool = False,
) -> str:
    if isinstance(expression, CheckComparison):
        return _render_check_comparison(expression, dialect, type_policy, allow_check_shim=allow_check_shim)
    if isinstance(expression, CheckNotExpression):
        operand = _render_check_expression(
            expression.operand,
            dialect,
            type_policy,
            allow_check_shim=allow_check_shim,
        )
        return f"NOT ({operand})"
    joiner = f" {expression.connector.value} "
    # Parenthesise every child boolean expression. This preserves the source
    # tree even when a source parser has already normalised operator
    # precedence, and it remains valid SQL on all four target dialects.
    operands = [
        (
            _render_check_expression(operand, dialect, type_policy, allow_check_shim=allow_check_shim)
            if isinstance(operand, CheckComparison)
            else f"({_render_check_expression(operand, dialect, type_policy, allow_check_shim=allow_check_shim)})"
        )
        for operand in expression.operands
    ]
    return joiner.join(operands)


#: Which targets can express `IF NOT EXISTS`, per statement kind.
#:
#: The two maps differ, and that asymmetry is the whole reason this is a table
#: rather than one boolean: MySQL has `CREATE TABLE IF NOT EXISTS` but has no
#: `CREATE INDEX IF NOT EXISTS` at all.
#:
#: Oracle is refused for both. Oracle only grew the syntax in 23ai, and
#: `Dialect` carries no version, so the engine cannot tell a 23ai target from
#: a 19c one. Refusing is the same discipline the rest of this repository
#: applies to unpinned versions: an exact tuple or nothing.
#:
#: SQL Server is refused for both -- it has `DROP ... IF EXISTS` but no
#: `CREATE ... IF NOT EXISTS` in any shipping version. The usual workaround
#: (`IF NOT EXISTS (SELECT ... FROM sys.tables) BEGIN ... END`) is a different
#: statement with different transactional and permission behaviour, so
#: synthesising one here would be this engine inventing semantics rather than
#: translating them.
_IF_NOT_EXISTS_TABLE_SUPPORT: frozenset[Dialect] = frozenset({Dialect.POSTGRES, Dialect.MYSQL})
_IF_NOT_EXISTS_INDEX_SUPPORT: frozenset[Dialect] = frozenset({Dialect.POSTGRES})
_IF_NOT_EXISTS_SCHEMA_SUPPORT: frozenset[Dialect] = frozenset({Dialect.POSTGRES, Dialect.MYSQL})


def _if_not_exists_clause(
    requested: bool,
    dialect: Dialect,
    *,
    object_kind: str,
    object_name: str,
    supported: frozenset[Dialect],
) -> str:
    """Render ` IF NOT EXISTS`, or fail closed when the target cannot say it.

    Dropping the modifier would compile and would look like a success, and the
    difference only shows up the second time the migration runs: the source
    statement is a no-op, the emitted one is an error. That is a behaviour
    change, so it fails closed like every other one in this profile.
    """

    if not requested:
        return ""
    if dialect in supported:
        return " IF NOT EXISTS"
    raise DialectError(
        "CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET",
        f"the source declares CREATE {object_kind} IF NOT EXISTS for {object_name!r}, and "
        f"{dialect.value} has no equivalent spelling. Emitting it without the modifier would "
        "change what a re-run does -- a no-op in the source, an error in the target -- so the "
        "translation fails closed instead. Remove the modifier at the source, or guard the "
        "statement outside the DDL.",
    )


def emit_create_table(
    table: Table,
    dialect: Dialect,
    type_policy: TypeMigrationPolicy | None = None,
    *,
    allow_if_not_exists_shim: bool = False,
    allow_mysql_text_prefix: bool = False,
    allow_check_shim: bool = False,
    allow_mysql_text_default: bool = False,
    allow_reserved_word_shim: bool = False,
) -> str:
    if dialect is Dialect.MYSQL:
        _require_mysql_auto_increment_key(table)
        _require_mysql_identifiers(table, allow_reserved_word_shim=allow_reserved_word_shim)
        _require_mysql_text_rules(
            table,
            allow_mysql_text_prefix=allow_mysql_text_prefix,
            allow_mysql_text_default=allow_mysql_text_default,
        )
    if table.if_not_exists:
        if dialect in _IF_NOT_EXISTS_TABLE_SUPPORT:
            existence = " IF NOT EXISTS"
        elif allow_if_not_exists_shim:
            existence = ""
        else:
            existence = _if_not_exists_clause(
                table.if_not_exists,
                dialect,
                object_kind="TABLE",
                object_name=table.name,
                supported=_IF_NOT_EXISTS_TABLE_SUPPORT,
            )
    else:
        existence = ""
    lines: list[str] = [_render_column(c, dialect, type_policy) for c in table.columns]

    text_columns = {column.name for column in table.columns if column.type_ref.canonical_type is CanonicalType.TEXT}
    if table.primary_key:
        pk_cols = [
            quote_identifier(column, dialect)
            + ("(255)" if dialect is Dialect.MYSQL and allow_mysql_text_prefix and column in text_columns else "")
            for column in table.primary_key
        ]
        lines.append(f"PRIMARY KEY ({', '.join(pk_cols)})")

    for unique in table.unique_constraints:
        uq_cols = [
            quote_identifier(column, dialect)
            + ("(255)" if dialect is Dialect.MYSQL and allow_mysql_text_prefix and column in text_columns else "")
            for column in unique
        ]
        lines.append(f"UNIQUE ({', '.join(uq_cols)})")

    for fk in table.foreign_keys:
        clause = _render_foreign_key_clause(fk, dialect)
        lines.append(f"CONSTRAINT {quote_identifier(fk.name, dialect)} {clause}" if fk.name else clause)

    for check in table.check_constraints:
        comparison_sql = (
            _render_check_expression(check.expression, dialect, type_policy, allow_check_shim=allow_check_shim)
            if check.expression is not None
            else (" OR " if check.connector is not None and check.connector.value == "OR" else " AND ").join(
                _render_check_comparison(c, dialect, type_policy, allow_check_shim=allow_check_shim)
                for c in check.comparisons
            )
        )
        clause = f"CHECK ({comparison_sql})"
        lines.append(f"CONSTRAINT {quote_identifier(check.name, dialect)} {clause}" if check.name else clause)

    body = ",\n    ".join(lines)
    rendered = f"CREATE TABLE{existence} {_object_name(table.schema, table.name, dialect)} (\n    {body}\n)"
    if dialect is Dialect.TSQL and table.if_not_exists and allow_if_not_exists_shim:
        schema_name = table.schema or "dbo"
        table_name = table.name
        return _compose_sql(
            "IF NOT EXISTS (SELECT 1 FROM sys.tables t JOIN sys.schemas s "
            "ON t.schema_id = s.schema_id WHERE s.name = N",
            _render_literal(schema_name, True),
            " AND t.name = N",
            _render_literal(table_name, True),
            ")\nBEGIN\n",
            rendered,
            "\nEND",
        )
    if dialect is Dialect.ORACLE and table.if_not_exists and allow_if_not_exists_shim:
        escaped_sql = rendered.replace("'", "''")
        return (
            f"BEGIN\n    EXECUTE IMMEDIATE '{escaped_sql}';\n"
            f"EXCEPTION WHEN OTHERS THEN\n    IF SQLCODE = -955 THEN NULL; ELSE RAISE; END IF;\nEND;"
        )
    return rendered


def emit_create_index(
    index: Index,
    dialect: Dialect,
    catalog: ColumnCatalogLike | None = None,
    *,
    allow_index_shim: bool = False,
    allow_if_not_exists_shim: bool = False,
    allow_index_expression_shim: bool = False,
    allow_mysql_text_prefix: bool = False,
) -> str:
    if dialect is Dialect.MYSQL:
        _require_mysql_catalog_text_keys(
            catalog,
            index.table,
            tuple(column.name for column in index.columns if column.expression is None),
            allow_mysql_text_prefix=allow_mysql_text_prefix,
        )
    if index.predicate is not None and dialect not in (Dialect.POSTGRES, Dialect.TSQL) and not allow_index_shim:
        raise DialectError(
            "CERTIFIED_DDL_INDEX_PREDICATE_UNSUPPORTED_BY_TARGET",
            f"{dialect.value} has no exact partial/filtered index mapping",
        )
    if index.include and dialect not in (Dialect.POSTGRES, Dialect.TSQL):
        raise DialectError(
            "CERTIFIED_DDL_INDEX_INCLUDE_UNSUPPORTED_BY_TARGET",
            f"{dialect.value} has no exact INCLUDE-column index mapping",
        )
    if index.using is not None and index.using not in {"btree"}:
        raise DialectError(
            "CERTIFIED_DDL_INDEX_METHOD_UNSUPPORTED",
            f"index access method {index.using!r} has no common exact mapping",
        )
    keyword = "CREATE UNIQUE INDEX" if index.unique else "CREATE INDEX"
    if index.if_not_exists:
        if dialect in _IF_NOT_EXISTS_INDEX_SUPPORT:
            existence = " IF NOT EXISTS"
        elif allow_if_not_exists_shim:
            existence = ""
        else:
            existence = _if_not_exists_clause(
                index.if_not_exists,
                dialect,
                object_kind="INDEX",
                object_name=index.name,
                supported=_IF_NOT_EXISTS_INDEX_SUPPORT,
            )
    else:
        existence = ""
    columns = ", ".join(
        _render_index_key(
            column,
            dialect,
            allow_index_expression_shim=allow_index_expression_shim,
            allow_mysql_text_prefix=allow_mysql_text_prefix,
            is_text=bool(catalog and catalog.type_of(index.table, column.name) is CanonicalType.TEXT),
        )
        for column in index.columns
    )
    rendered = f"{keyword}{existence} {quote_identifier(index.name, dialect)}"
    if index.using == "btree" and dialect is Dialect.POSTGRES:
        rendered += " USING btree"
    rendered += f" ON {_object_name(index.table_schema, index.table, dialect)} ({columns})"
    if index.using == "btree" and dialect is Dialect.MYSQL:
        rendered += " USING BTREE"
    if index.include:
        rendered += f" INCLUDE ({', '.join(quote_identifier(column, dialect) for column in index.include)})"
    if index.predicate is not None:
        if dialect in (Dialect.POSTGRES, Dialect.TSQL):
            rendered += f" WHERE {_render_check_expression(index.predicate, dialect)}"
        elif allow_index_shim:
            pass
    if dialect is Dialect.TSQL and index.if_not_exists and allow_if_not_exists_shim:
        schema_name = index.table_schema or "dbo"
        return _compose_sql(
            "IF NOT EXISTS (SELECT 1 FROM sys.indexes i JOIN sys.tables t ON i.object_id = t.object_id "
            "JOIN sys.schemas s ON t.schema_id = s.schema_id WHERE s.name = N",
            _render_literal(schema_name, True),
            " AND i.name = N",
            _render_literal(index.name, True),
            ")\nBEGIN\n",
            rendered,
            "\nEND",
        )
    if dialect is Dialect.ORACLE and index.if_not_exists and allow_if_not_exists_shim:
        escaped_sql = rendered.replace("'", "''")
        return (
            f"BEGIN\n    EXECUTE IMMEDIATE '{escaped_sql}';\n"
            f"EXCEPTION WHEN OTHERS THEN\n    IF SQLCODE = -955 OR SQLCODE = -1408 THEN NULL; ELSE RAISE; END IF;\nEND;"
        )
    return rendered


def emit_drop_table(drop: DropTable, dialect: Dialect) -> str:
    """Emit the portable DROP TABLE profile.

    IF EXISTS is shared by PostgreSQL and MySQL.  Oracle and SQL Server need
    version- or procedural-guards with different rerun and permission
    behaviour, so the parser/emitter fails closed for those targets rather
    than dropping the modifier.
    """
    if drop.if_exists and dialect in (Dialect.ORACLE, Dialect.TSQL):
        detail = (
            "Oracle requires a PL/SQL exception block or (23ai+) version-specific syntax"
            if dialect is Dialect.ORACLE
            else "SQL Server 2016+ still requires a version-specific conditional batch"
        )
        raise DialectError(
            "CERTIFIED_DROP_IF_EXISTS_UNSUPPORTED_BY_TARGET",
            f"DROP TABLE IF EXISTS is not emitted for {dialect.value}: {detail}; "
            "removing the modifier would change rerun behaviour",
        )
    suffix = " IF EXISTS" if drop.if_exists else ""
    return f"DROP TABLE{suffix} {_object_name(drop.schema, drop.name, dialect)}"


def emit_create_schema(
    schema: Schema,
    dialect: Dialect,
    *,
    allow_schema_shim: bool = False,
    allow_if_not_exists_shim: bool = False,
) -> str:
    """Emit a named logical namespace without creating users or permissions."""
    if dialect is Dialect.ORACLE:
        if not allow_schema_shim:
            raise DialectError(
                "CERTIFIED_SCHEMA_UNSUPPORTED_TARGET",
                "Oracle schemas are users and CREATE SCHEMA requires authorization/account semantics; "
                "the portable profile will not create an account as a side effect",
            )
        user_name = quote_identifier(schema.name, dialect)
        if schema.if_not_exists and allow_if_not_exists_shim:
            return _compose_sql(
                "DECLARE\n    v_cnt NUMBER;\nBEGIN\n    SELECT COUNT(*) INTO v_cnt FROM all_users WHERE username = ",
                _render_literal(schema.name.upper(), True),
                ";\n    IF v_cnt = 0 THEN\n        EXECUTE IMMEDIATE 'CREATE USER ",
                user_name,
                " NO AUTHENTICATION';\n    END IF;\nEND;",
            )
        return f"CREATE USER {user_name} NO AUTHENTICATION"
    if schema.if_not_exists:
        if dialect in _IF_NOT_EXISTS_SCHEMA_SUPPORT:
            existence = " IF NOT EXISTS"
        elif allow_if_not_exists_shim and dialect is Dialect.TSQL:
            return _compose_sql(
                "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N",
                _render_literal(schema.name, True),
                ")\nBEGIN\n    EXEC('CREATE SCHEMA ",
                quote_identifier(schema.name, dialect),
                "')\nEND",
            )
        else:
            existence = _if_not_exists_clause(
                schema.if_not_exists,
                dialect,
                object_kind="SCHEMA",
                object_name=schema.name,
                supported=_IF_NOT_EXISTS_SCHEMA_SUPPORT,
            )
    else:
        existence = ""
    return f"CREATE SCHEMA{existence} {quote_identifier(schema.name, dialect)}"


def emit_row_security(
    command: RowSecurityCommand,
    dialect: Dialect,
    *,
    allow_rls_shim: bool = False,
) -> str:
    """Emit a typed PostgreSQL RLS state transition.

    The state change is not portable merely because all four vendors have
    permissions features. PostgreSQL's policy evaluation, owner bypass and
    FORCE/NO FORCE state have no common equivalent in this engine, so every
    non-PostgreSQL target remains an explicit refusal.
    """

    if dialect is not Dialect.POSTGRES:
        if not allow_rls_shim:
            raise DialectError(
                "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED",
                f"{dialect.value} has no exact PostgreSQL row-security state mapping; "
                "the route will not downgrade RLS to ordinary privileges",
            )
        if dialect is Dialect.TSQL:
            schema_name = quote_identifier(command.schema or "dbo", dialect)
            policy_name = quote_identifier(f"sec_pol_{command.table}", dialect)
            state = "ON" if command.action.value == "ENABLE" else "OFF"
            return f"ALTER SECURITY POLICY {schema_name}.{policy_name} WITH (STATE = {state})"
        elif dialect is Dialect.ORACLE:
            schema_arg = f"'{command.schema}'" if command.schema else "USER"
            action_flag = "TRUE" if command.action.value == "ENABLE" else "FALSE"
            return f"CALL DBMS_RLS.ENABLE_POLICY({schema_arg}, '{command.table}', 'rls_policy', {action_flag})"
        elif dialect is Dialect.MYSQL:
            return f"CALL sys.set_row_security('{command.schema or ''}', '{command.table}', '{command.action.value}')"
    return (
        f"ALTER TABLE {_object_name(command.schema, command.table, dialect)} {command.action.value} ROW LEVEL SECURITY"
    )


def _render_insert_literal(value: InsertLiteral, dialect: Dialect) -> str:
    if value.is_null:
        return "NULL"
    assert value.value is not None
    if value.is_boolean:
        return _render_boolean(value.value, dialect)
    return _render_literal(value.value, value.is_string)


def emit_insert(insert: InsertStatement, dialect: Dialect) -> str:
    """Emit a fixed-column literal seed without changing its row set."""
    columns = ", ".join(quote_identifier(column, dialect) for column in insert.columns)
    rows = ",\n    ".join(
        "(" + ", ".join(_render_insert_literal(value, dialect) for value in row) + ")" for row in insert.rows
    )
    table_name = _object_name(insert.schema, insert.table, dialect)
    if insert.on_conflict_do_nothing:
        if dialect is Dialect.POSTGRES:
            return _compose_sql("INSERT INTO ", table_name, " (", columns, ") VALUES ", rows, " ON CONFLICT DO NOTHING")
        elif dialect is Dialect.MYSQL:
            return _compose_sql("INSERT IGNORE INTO ", table_name, " (", columns, ") VALUES ", rows)
        else:
            raise DialectError(
                "CERTIFIED_INSERT_UNSUPPORTED_TARGET",
                f"ON CONFLICT DO NOTHING is not natively supported in {dialect.value} INSERT syntax",
            )
    return _compose_sql("INSERT INTO ", table_name, " (", columns, ") VALUES ", rows)


def _render_dml_expression(value: DmlExpression, dialect: Dialect) -> str:
    if isinstance(value, DmlColumn):
        return (
            f"{quote_identifier(value.qualifier, dialect)}.{quote_identifier(value.name, dialect)}"
            if value.qualifier is not None
            else quote_identifier(value.name, dialect)
        )
    if isinstance(value, DmlLiteral):
        return _render_insert_literal(value.value, dialect)
    if isinstance(value, DmlCurrentTimestamp):
        return "SYSDATETIME()" if dialect is Dialect.TSQL else "CURRENT_TIMESTAMP"
    if isinstance(value, DmlCoalesce):
        fallback = _render_dml_expression(value.fallback, dialect)
        return f"COALESCE({quote_identifier(value.column.name, dialect)}, {fallback})"
    if isinstance(value, DmlAggregate):
        return f"{value.function.value}({quote_identifier(value.column.name, dialect)})"
    if isinstance(value, DmlPredicate):
        return _render_check_expression(value.predicate, dialect)
    raise TypeError(f"unhandled DML IR node: {type(value).__name__}")  # pragma: no cover


def emit_insert_select(insert: InsertSelectStatement, dialect: Dialect) -> str:
    """Emit the bounded INSERT ... SELECT profile."""
    columns = ", ".join(quote_identifier(column, dialect) for column in insert.columns)
    expressions = ", ".join(_render_dml_expression(item, dialect) for item in insert.expressions)
    source = _object_name(insert.source_schema, insert.source_table, dialect)
    if insert.source_alias is not None:
        source += f" {insert.source_alias}"
    rendered = (
        f"INSERT INTO {_object_name(insert.schema, insert.table, dialect)} ({columns}) "  # noqa: S608
        f"SELECT {expressions} FROM {source}"  # noqa: S608
    )
    for join in insert.joins:
        conditions = " AND ".join(
            f"{_render_dml_expression(condition.left, dialect)} = {_render_dml_expression(condition.right, dialect)}"
            for condition in join.conditions
        )
        rendered += f" INNER JOIN {_object_name(join.schema, join.table, dialect)} {join.alias} ON {conditions}"
    if insert.predicate is not None:
        rendered += f" WHERE {_render_check_expression(insert.predicate, dialect)}"
    if insert.group_by:
        rendered += f" GROUP BY {', '.join(insert.group_by)}"
    return rendered  # noqa: S608


def emit_update(update: UpdateStatement, dialect: Dialect) -> str:
    """Emit a typed single-table UPDATE or a proven one-row-source UPDATE."""
    assignments = ", ".join(
        f"{quote_identifier(item.target, dialect)} = {_render_dml_expression(item.value, dialect)}"
        for item in update.assignments
    )
    if update.source_table is None:
        rendered = f"UPDATE {_object_name(update.schema, update.table, dialect)} SET {assignments}"  # noqa: S608
        if update.predicate is not None:
            rendered += f" WHERE {_render_check_expression(update.predicate, dialect)}"
        return rendered  # noqa: S608

    if update.target_alias is None or update.source_alias is None or not update.join_conditions:
        raise DialectError(
            "CERTIFIED_UPDATE_UNSUPPORTED_SOURCE",
            "typed UPDATE row-source metadata is incomplete",
        )
    target = _object_name(update.schema, update.table, dialect)
    source = _object_name(update.source_schema, update.source_table, dialect)
    joins = " AND ".join(
        f"{_render_dml_expression(condition.left, dialect)} = {_render_dml_expression(condition.right, dialect)}"
        for condition in update.join_conditions
    )
    predicate = f" AND {_render_check_expression(update.predicate, dialect)}" if update.predicate is not None else ""
    where = f" WHERE {_render_check_expression(update.predicate, dialect)}" if update.predicate is not None else ""
    if dialect is Dialect.POSTGRES:
        return (  # noqa: S608
            f"UPDATE {target} {quote_identifier(update.target_alias, dialect)} SET {assignments} FROM {source} "  # noqa: S608
            f"{quote_identifier(update.source_alias, dialect)} WHERE {joins}{predicate}"
        )
    if dialect is Dialect.MYSQL:
        return (  # noqa: S608
            f"UPDATE {target} {quote_identifier(update.target_alias, dialect)} INNER JOIN {source} "  # noqa: S608
            f"{quote_identifier(update.source_alias, dialect)} "  # noqa: S608
            f"ON {joins} SET {assignments}"
            f"{where}"
        )
    if dialect is Dialect.ORACLE:
        oracle_assignments = ", ".join(
            f"{quote_identifier(update.target_alias, dialect)}.{quote_identifier(item.target, dialect)} = "
            f"{_render_dml_expression(item.value, dialect)}"
            for item in update.assignments
        )
        return (
            f"MERGE INTO {target} {quote_identifier(update.target_alias, dialect)} USING {source} "
            f"{quote_identifier(update.source_alias, dialect)} "  # noqa: S608
            f"ON ({joins}) WHEN MATCHED THEN UPDATE SET "
            f"{oracle_assignments}"
            f"{where}"
        )
    return (  # noqa: S608
        f"UPDATE {quote_identifier(update.target_alias, dialect)} SET {assignments} FROM {target} "  # noqa: S608
        f"{quote_identifier(update.target_alias, dialect)} "  # noqa: S608
        f"INNER JOIN {source} {quote_identifier(update.source_alias, dialect)} ON {joins}"
        f"{where}"
    )


def emit_delete(delete: DeleteStatement, dialect: Dialect) -> str:
    """Emit a typed single-table DELETE."""
    rendered = _compose_sql("DELETE FROM ", _object_name(delete.schema, delete.table, dialect))
    if delete.predicate is not None:
        rendered += f" WHERE {_render_check_expression(delete.predicate, dialect)}"
    return rendered


def emit_truncate_table(truncate: TruncateTable, dialect: Dialect) -> str:
    """Emit a portable TRUNCATE TABLE statement."""
    return f"TRUNCATE TABLE {_object_name(truncate.schema, truncate.table, dialect)}"


def _render_check_clause(
    check: CheckConstraint,
    dialect: Dialect,
    type_policy: TypeMigrationPolicy | None = None,
    allow_check_shim: bool = False,
) -> str:
    comparison_sql = (
        _render_check_expression(check.expression, dialect, type_policy, allow_check_shim=allow_check_shim)
        if check.expression is not None
        else (" OR " if check.connector is not None and check.connector.value == "OR" else " AND ").join(
            _render_check_comparison(c, dialect, type_policy, allow_check_shim=allow_check_shim)
            for c in check.comparisons
        )
    )
    return f"CHECK ({comparison_sql})"


def _named(name: str | None, clause: str, dialect: Dialect) -> str:
    return f"CONSTRAINT {quote_identifier(name, dialect)} {clause}" if name else clause


def emit_alter_table(
    alter: AlterTable,
    dialect: Dialect,
    catalog: ColumnCatalogLike | None = None,
    type_policy: TypeMigrationPolicy | None = None,
    allow_mysql_text_prefix: bool = False,
    allow_check_shim: bool = False,
    allow_mysql_text_default: bool = False,
    allow_reserved_word_shim: bool = False,
) -> str:
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
    if dialect is Dialect.MYSQL:
        identifiers = [alter.table]
        for action in alter.actions:
            if isinstance(action, AddColumn):
                identifiers.append(action.column.name)
                if action.foreign_key is not None:
                    identifiers.append(action.foreign_key.ref_table)
                    identifiers.extend(action.foreign_key.ref_columns)
            elif isinstance(action, DropColumn):
                identifiers.append(action.column)
            elif isinstance(action, RenameColumn):
                identifiers.extend((action.column, action.new_name))
            elif isinstance(action, AddConstraint):
                if action.name:
                    identifiers.append(action.name)
                if action.foreign_key is not None:
                    identifiers.append(action.foreign_key.ref_table)
                    identifiers.extend(action.foreign_key.ref_columns)
            elif isinstance(action, DropConstraint):
                identifiers.append(action.name)
        offending = sorted(
            {
                str(name)
                for name in identifiers
                if not getattr(name, "quoted", False) and name.casefold() in _MYSQL_RESERVED_IDENTIFIERS
            }
        )
        if offending and not allow_reserved_word_shim:
            raise DialectError(
                "CERTIFIED_DDL_TARGET_RESERVED_IDENTIFIER",
                "MySQL target identifiers are reserved words: "
                f"{', '.join(offending)}. Quoting them is not the certified fix: it changes the "
                "plain-identifier contract and can change case-folding when the schema is read back; "
                "rename the source objects or provide a versioned target identifier mapping",
            )
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
            if dialect is Dialect.MYSQL and action.column.type_ref.canonical_type is CanonicalType.TEXT:
                if action.column.default is not None and not allow_mysql_text_default:
                    raise DialectError(
                        "CERTIFIED_DDL_MYSQL_TEXT_DEFAULT_UNSUPPORTED",
                        f"MySQL TEXT column {action.column.name!r} cannot carry a DEFAULT. "
                        "Dropping the default would change INSERT behaviour, so the source default "
                        "must be rewritten explicitly rather than silently removed",
                    )
                if action.foreign_key is not None and not allow_mysql_text_prefix:
                    raise DialectError(
                        "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX",
                        f"MySQL TEXT column {action.column.name!r} used as a foreign key requires "
                        "an index prefix. A prefix weakens equality semantics, so the translator "
                        "will not invent one",
                    )
            if dialect is Dialect.MYSQL and action.foreign_key is not None:
                _require_mysql_catalog_text_keys(
                    catalog,
                    action.foreign_key.ref_table,
                    action.foreign_key.ref_columns,
                    allow_mysql_text_prefix=allow_mysql_text_prefix,
                )
            column_sql = _render_column(action.column, dialect, type_policy)
            if action.foreign_key is not None:
                reference_name = _object_name(action.foreign_key.ref_schema, action.foreign_key.ref_table, dialect)
                reference = f" REFERENCES {reference_name}"
                if action.foreign_key.ref_columns:
                    reference += f" ({', '.join(action.foreign_key.ref_columns)})"
                column_sql += reference
                actions_sql = render_reference_actions(
                    action.foreign_key.on_delete, action.foreign_key.on_update, dialect
                )
                if actions_sql:
                    column_sql += f" {actions_sql}"
            if action.check is not None:
                column_sql += " " + _render_check_clause(
                    action.check, dialect, type_policy=type_policy, allow_check_shim=allow_check_shim
                )
            if dialect is Dialect.ORACLE:
                # Oracle: no COLUMN keyword; parenthesised column list.
                statements.append(f"ALTER TABLE {_object_name(alter.schema, alter.table, dialect)} ADD ({column_sql})")
            elif dialect is Dialect.TSQL:
                # SQL Server: ADD, without the COLUMN keyword.
                statements.append(f"ALTER TABLE {_object_name(alter.schema, alter.table, dialect)} ADD {column_sql}")
            else:
                table_name = _object_name(alter.schema, alter.table, dialect)
                statements.append(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

        elif isinstance(action, DropColumn):
            table_name = _object_name(alter.schema, alter.table, dialect)
            column_name = quote_identifier(action.column, dialect)
            statements.append(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")

        elif isinstance(action, RenameColumn):
            if dialect is Dialect.TSQL:
                # T-SQL's only column rename. Quoting follows sp_rename's
                # documented 'table.column' form.
                table_name = _object_name(alter.schema, alter.table, dialect)
                old_name = f"{table_name}.{quote_identifier(action.column, dialect)}"
                new_name = quote_identifier(action.new_name, dialect)
                statements.append(f"EXEC sp_rename '{old_name}', '{new_name}', 'COLUMN'")
            else:
                statements.append(
                    f"ALTER TABLE {_object_name(alter.schema, alter.table, dialect)} RENAME COLUMN "
                    f"{quote_identifier(action.column, dialect)} TO {quote_identifier(action.new_name, dialect)}"
                )

        elif isinstance(action, AddConstraint):
            if action.primary_key:
                if dialect is Dialect.MYSQL:
                    _require_mysql_catalog_text_keys(
                        catalog, alter.table, action.primary_key, allow_mysql_text_prefix=allow_mysql_text_prefix
                    )
                cols = [
                    f"{quote_identifier(col, dialect)}(255)"
                    if dialect is Dialect.MYSQL
                    and allow_mysql_text_prefix
                    and catalog
                    and catalog.type_of(alter.table, col) is CanonicalType.TEXT
                    else quote_identifier(col, dialect)
                    for col in action.primary_key
                ]
                clause = f"PRIMARY KEY ({', '.join(cols)})"
            elif action.unique:
                if dialect is Dialect.MYSQL:
                    _require_mysql_catalog_text_keys(
                        catalog, alter.table, action.unique, allow_mysql_text_prefix=allow_mysql_text_prefix
                    )
                cols = [
                    f"{quote_identifier(col, dialect)}(255)"
                    if dialect is Dialect.MYSQL
                    and allow_mysql_text_prefix
                    and catalog
                    and catalog.type_of(alter.table, col) is CanonicalType.TEXT
                    else quote_identifier(col, dialect)
                    for col in action.unique
                ]
                clause = f"UNIQUE ({', '.join(cols)})"
            elif action.foreign_key is not None:
                if dialect is Dialect.MYSQL:
                    _require_mysql_catalog_text_keys(
                        catalog,
                        alter.table,
                        action.foreign_key.columns,
                        allow_mysql_text_prefix=allow_mysql_text_prefix,
                    )
                    _require_mysql_catalog_text_keys(
                        catalog,
                        action.foreign_key.ref_table,
                        action.foreign_key.ref_columns,
                        allow_mysql_text_prefix=allow_mysql_text_prefix,
                    )
                clause = _render_foreign_key_clause(action.foreign_key, dialect)
            else:
                assert action.check is not None  # AddConstraint.__post_init__ guarantees one is set
                clause = _render_check_clause(
                    action.check, dialect, type_policy=type_policy, allow_check_shim=allow_check_shim
                )
            statements.append(
                f"ALTER TABLE {_object_name(alter.schema, alter.table, dialect)} "
                f"ADD {_named(action.name, clause, dialect)}"
            )

        elif isinstance(action, DropConstraint):
            table_name = _object_name(alter.schema, alter.table, dialect)
            constraint_name = quote_identifier(action.name, dialect)
            statements.append(f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}")

        elif isinstance(action, SetNotNull):
            table_name = _object_name(alter.schema, alter.table, dialect)
            column_name = quote_identifier(action.column, dialect)
            if dialect is Dialect.POSTGRES:
                statements.append(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET NOT NULL")
            elif dialect is Dialect.ORACLE:
                statements.append(f"ALTER TABLE {table_name} MODIFY ({column_name} NOT NULL)")
            elif dialect in (Dialect.MYSQL, Dialect.TSQL):
                col_type = catalog.type_of(alter.table, action.column) if catalog else None
                if col_type is None:
                    raise DialectError(
                        "CERTIFIED_ALTER_CATALOG_REQUIRED_FOR_COLUMN_TYPE",
                        f"{dialect.value} requires column type to be restated for NOT NULL; "
                        f"provide a catalog with column '{action.column}'",
                    )
                type_str = render_type(CanonicalTypeRef(canonical_type=col_type), dialect, type_policy)
                if dialect is Dialect.MYSQL:
                    statements.append(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {type_str} NOT NULL")
                else:
                    statements.append(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} {type_str} NOT NULL")

        elif isinstance(action, DropNotNull):
            table_name = _object_name(alter.schema, alter.table, dialect)
            column_name = quote_identifier(action.column, dialect)
            if dialect is Dialect.POSTGRES:
                statements.append(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP NOT NULL")
            elif dialect is Dialect.ORACLE:
                statements.append(f"ALTER TABLE {table_name} MODIFY ({column_name} NULL)")
            elif dialect in (Dialect.MYSQL, Dialect.TSQL):
                col_type = catalog.type_of(alter.table, action.column) if catalog else None
                if col_type is None:
                    raise DialectError(
                        "CERTIFIED_ALTER_CATALOG_REQUIRED_FOR_COLUMN_TYPE",
                        f"{dialect.value} requires column type to be restated for NULL; "
                        f"provide a catalog with column '{action.column}'",
                    )
                type_str = render_type(CanonicalTypeRef(canonical_type=col_type), dialect, type_policy)
                if dialect is Dialect.MYSQL:
                    statements.append(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {type_str} NULL")
                else:
                    statements.append(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} {type_str} NULL")

        elif isinstance(action, AlterColumnType):
            table_name = _object_name(alter.schema, alter.table, dialect)
            column_name = quote_identifier(action.column, dialect)
            type_str = render_type(action.type_ref, dialect, type_policy)
            if dialect is Dialect.POSTGRES:
                statements.append(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {type_str}")
            elif dialect is Dialect.ORACLE:
                statements.append(f"ALTER TABLE {table_name} MODIFY ({column_name} {type_str})")
            elif dialect is Dialect.MYSQL:
                statements.append(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {type_str}")
            elif dialect is Dialect.TSQL:
                statements.append(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} {type_str}")

    return ";\n".join(statements)
