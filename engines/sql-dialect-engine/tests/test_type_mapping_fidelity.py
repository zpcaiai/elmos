"""Regression tests for cross-dialect *type* fidelity.

Each test here pins one defect that shipped in an earlier revision of
`parser._parse_type` / `dialects.render_type`, where the translation produced
syntactically valid DDL in the target dialect that silently held *less* data
than the source column. Syntax validation cannot catch any of them -- the
emitted statement parses fine, it is just the wrong column -- so they are
locked down here by asserting the rendered type text directly.
"""
from __future__ import annotations

import pytest

from elmos_sql_dialect.emitter import emit_create_table
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import (
    CanonicalType,
    DefaultKind,
    Dialect,
    DialectError,
)
from elmos_sql_dialect.parser import parse_create_table


def _emit(ddl: str, source: str, target: str) -> str:
    report = translate_ddl(ddl, source, target)
    assert report["status"] == "PASSED", report
    return report["emitted"]


def _blocked(ddl: str, source: str, target: str) -> str:
    report = translate_ddl(ddl, source, target)
    assert report["status"] == "BLOCKED", report
    assert report["emitted"] is None
    return report["reasonCode"]


# --------------------------------------------------------------------------
# 1. Unbounded VARCHAR must never become VARCHAR(255).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
def test_postgres_unbounded_varchar_becomes_unbounded_text_not_varchar_255(target: str) -> None:
    emitted = _emit("CREATE TABLE t (name VARCHAR)", "postgres", target)
    assert "VARCHAR(255)" not in emitted.upper()
    assert {"mysql": "LONGTEXT", "tsql": "NVARCHAR(MAX)", "oracle": "CLOB"}[target] in emitted


@pytest.mark.parametrize("source", ["mysql", "tsql", "oracle"])
def test_unbounded_varchar_from_a_non_postgres_source_fails_closed(source: str) -> None:
    # Only PostgreSQL defines a bare VARCHAR as unlimited. SQL Server reads it
    # as VARCHAR(1); MySQL and Oracle reject it. Guessing is not an option.
    assert _blocked("CREATE TABLE t (name VARCHAR)", source, "postgres") in (
        "CERTIFIED_DDL_UNBOUNDED_VARCHAR",
        "CERTIFIED_DDL_PARSE_FAILED",
    )


# --------------------------------------------------------------------------
# 2. Unbounded DECIMAL must never become DECIMAL(18, 0) (scale 0 = rounding
#    every fractional value in the column to an integer).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["mysql", "tsql", "oracle"])
def test_unbounded_numeric_fails_closed_instead_of_rounding_to_scale_zero(target: str) -> None:
    assert _blocked("CREATE TABLE t (price NUMERIC)", "postgres", target) == "CERTIFIED_DDL_UNBOUNDED_DECIMAL"


def test_parameterised_decimal_still_translates() -> None:
    assert "DECIMAL(12, 4)" in _emit("CREATE TABLE t (price NUMERIC(12,4))", "postgres", "mysql")


def test_jsonb_literal_default_is_retained_as_a_typed_source_fact() -> None:
    table = parse_create_table(
        "CREATE TABLE t (payload JSONB NOT NULL DEFAULT '{}'::jsonb)", Dialect.POSTGRES
    )
    default = table.columns[0].default
    assert default is not None
    assert default.kind is DefaultKind.STRING
    assert default.literal == "{}"
    assert default.cast_type is not None
    assert default.cast_type.canonical_type is CanonicalType.JSON
    assert default.cast_type.json_binary is True


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_jsonb_literal_default_does_not_get_downgraded_to_plain_json(target: str) -> None:
    assert _blocked(
        "CREATE TABLE t (payload JSONB NOT NULL DEFAULT '{}'::jsonb)", "postgres", target
    ) == "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED"


def test_postgres_array_literal_default_is_retained_as_typed_source_fact() -> None:
    table = parse_create_table(
        "CREATE TABLE t (threshold_bps INTEGER[] NOT NULL DEFAULT ARRAY[5000,8000])",
        Dialect.POSTGRES,
    )
    default = table.columns[0].default
    assert default is not None
    assert default.kind is DefaultKind.ARRAY
    assert [item.value for item in default.array_elements] == ["5000", "8000"]
    assert all(not item.is_string for item in default.array_elements)
    rendered = emit_create_table(table, Dialect.POSTGRES)
    assert "INTEGER[]" in rendered
    assert "DEFAULT ARRAY[5000, 8000]" in rendered


@pytest.mark.parametrize("ddl", [
    "CREATE TABLE t (threshold_bps INTEGER[] DEFAULT ARRAY['5000'])",
    "CREATE TABLE t (threshold_bps INTEGER[] DEFAULT ARRAY[])",
])
def test_array_literal_defaults_fail_closed_on_untyped_or_mismatched_members(ddl: str) -> None:
    with pytest.raises(DialectError):
        parse_create_table(ddl, Dialect.POSTGRES)


def test_array_literal_default_does_not_get_serialized_to_a_non_postgres_type() -> None:
    assert _blocked(
        "CREATE TABLE t (threshold_bps INTEGER[] NOT NULL DEFAULT ARRAY[5000,8000])",
        "postgres",
        "mysql",
    ) == "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED"


def test_decimal_precision_beyond_the_target_maximum_fails_closed() -> None:
    # Postgres allows NUMERIC(1000); Oracle's NUMBER caps at 38 and MySQL's
    # DECIMAL at 65. Emitting NUMBER(50, 2) is DDL Oracle rejects.
    assert _blocked("CREATE TABLE t (v NUMERIC(50,2))", "postgres", "oracle") == (
        "CERTIFIED_DDL_PRECISION_EXCEEDS_TARGET"
    )
    assert "DECIMAL(50, 2)" in _emit("CREATE TABLE t (v NUMERIC(50,2))", "postgres", "mysql")


# --------------------------------------------------------------------------
# 3. TIMESTAMP must not become MySQL's TIMESTAMP (UTC conversion, 2038 limit,
#    implicit ON UPDATE CURRENT_TIMESTAMP).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["postgres", "oracle", "tsql"])
def test_timestamp_becomes_mysql_datetime_not_mysql_timestamp(source: str) -> None:
    ddl = {
        "postgres": "CREATE TABLE t (created_at TIMESTAMP)",
        "oracle": "CREATE TABLE t (created_at TIMESTAMP)",
        "tsql": "CREATE TABLE t (created_at DATETIME2)",
    }[source]
    emitted = _emit(ddl, source, "mysql")
    assert "DATETIME" in emitted.upper()
    assert "TIMESTAMP" not in emitted.upper()


def test_mysql_timestamp_source_still_reads_as_canonical_timestamp() -> None:
    assert "TIMESTAMP" in _emit("CREATE TABLE t (created_at TIMESTAMP)", "mysql", "postgres")


# --------------------------------------------------------------------------
# 4. TEXT must not shrink to MySQL's 64 KiB TEXT.
# --------------------------------------------------------------------------


def test_text_becomes_mysql_longtext_not_text() -> None:
    emitted = _emit("CREATE TABLE t (body TEXT)", "postgres", "mysql")
    assert "LONGTEXT" in emitted


@pytest.mark.parametrize("mysql_text_type", ["TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT"])
def test_every_mysql_text_size_reads_as_canonical_text(mysql_text_type: str) -> None:
    assert "body TEXT" in _emit(f"CREATE TABLE t (body {mysql_text_type})", "mysql", "postgres")


# --------------------------------------------------------------------------
# 5. SQL Server targets must use the Unicode types. VARCHAR/CHAR/TEXT on SQL
#    Server are single-byte code-page types: routing a UTF-8 column into them
#    replaces every unrepresentable character with '?'.
# --------------------------------------------------------------------------


def test_sql_server_target_uses_unicode_character_types() -> None:
    emitted = _emit(
        "CREATE TABLE t (code CHAR(3), name VARCHAR(50), body TEXT)", "postgres", "tsql"
    )
    assert "NCHAR(3)" in emitted
    assert "NVARCHAR(50)" in emitted
    assert "NVARCHAR(MAX)" in emitted


def test_sql_server_nvarchar_round_trips_without_losing_the_n() -> None:
    pg = _emit("CREATE TABLE t (name NVARCHAR(50))", "tsql", "postgres")
    assert "NVARCHAR(50)" in _emit(pg, "postgres", "tsql")


def test_sql_server_nchar_is_accepted_as_a_source_type() -> None:
    assert "CHAR(3)" in _emit("CREATE TABLE t (code NCHAR(3))", "tsql", "postgres")


def test_varchar_beyond_the_sql_server_nvarchar_limit_fails_closed() -> None:
    assert _blocked("CREATE TABLE t (v VARCHAR(6000))", "postgres", "tsql") == (
        "CERTIFIED_DDL_LENGTH_EXCEEDS_TARGET"
    )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("mysql", "LONGBLOB"),
        ("oracle", "BLOB"),
        ("tsql", "VARBINARY(MAX)"),
    ],
)
def test_postgres_bytea_uses_an_unbounded_target_byte_storage_type(
    target: str, expected: str
) -> None:
    # BYTEA has no declared length and accepts arbitrary byte payloads.  The
    # target must therefore use its unbounded byte type, never a bounded
    # BINARY(n)/VARBINARY(n) approximation.
    emitted = _emit("CREATE TABLE t (payload BYTEA)", "postgres", target)
    assert f"payload {expected}" in emitted


def test_postgres_bytea_is_retained_as_unbounded_binary_in_the_canonical_model() -> None:
    table = parse_create_table("CREATE TABLE t (payload BYTEA)", Dialect.POSTGRES)
    type_ref = table.columns[0].type_ref
    assert type_ref.canonical_type is CanonicalType.BINARY
    assert type_ref.length is None
    assert type_ref.binary_fixed is False


def test_fixed_binary_without_a_length_stays_fail_closed() -> None:
    assert _blocked("CREATE TABLE t (payload BINARY)", "postgres", "mysql") == (
        "CERTIFIED_DDL_UNBOUNDED_BINARY"
    )


def test_bare_non_postgres_varbinary_stays_fail_closed() -> None:
    assert _blocked("CREATE TABLE t (payload VARBINARY)", "mysql", "postgres") == (
        "CERTIFIED_DDL_UNBOUNDED_BINARY"
    )


# --------------------------------------------------------------------------
# 6. Oracle targets must spell character length semantics, because Oracle's
#    default is BYTE and every other dialect here counts characters.
# --------------------------------------------------------------------------


def test_oracle_target_uses_char_length_semantics() -> None:
    emitted = _emit("CREATE TABLE t (code CHAR(3), name VARCHAR(50))", "postgres", "oracle")
    assert "CHAR(3 CHAR)" in emitted
    assert "VARCHAR2(50 CHAR)" in emitted


@pytest.mark.parametrize("qualifier", ["", " CHAR", " BYTE"])
def test_oracle_source_accepts_every_length_semantics_spelling(qualifier: str) -> None:
    emitted = _emit(f"CREATE TABLE t (name VARCHAR2(50{qualifier}))", "oracle", "postgres")
    assert "VARCHAR(50)" in emitted


def test_varchar_beyond_the_oracle_limit_fails_closed() -> None:
    assert _blocked("CREATE TABLE t (v VARCHAR(5000))", "postgres", "oracle") == (
        "CERTIFIED_DDL_LENGTH_EXCEEDS_TARGET"
    )


def test_char_beyond_the_mysql_limit_fails_closed() -> None:
    assert _blocked("CREATE TABLE t (v CHAR(300))", "postgres", "mysql") == (
        "CERTIFIED_DDL_LENGTH_EXCEEDS_TARGET"
    )


# --------------------------------------------------------------------------
# 7. MySQL's own spellings for a boolean and for the narrow/unsigned
#    integers, so a real `SHOW CREATE TABLE` / mysqldump round-trips.
# --------------------------------------------------------------------------


def test_mysql_tinyint_1_reads_as_boolean() -> None:
    # MySQL stores BOOLEAN as TINYINT(1) and echoes it back that way, so a
    # schema dumped from a live server used to be untranslatable.
    assert "flag BOOLEAN" in _emit("CREATE TABLE t (flag TINYINT(1))", "mysql", "postgres")
    assert "flag BIT" in _emit("CREATE TABLE t (flag TINYINT(1))", "mysql", "tsql")


def test_mysql_boolean_round_trips_through_its_own_storage_spelling() -> None:
    pg = _emit("CREATE TABLE t (flag BOOLEAN)", "mysql", "postgres")
    assert "flag BOOLEAN" in pg


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("TINYINT", "SMALLINT"),  # -128..127 fits INT16
        ("TINYINT UNSIGNED", "SMALLINT"),  # 0..255 fits INT16
        ("SMALLINT UNSIGNED", "INTEGER"),  # 0..65535 needs INT32
        ("MEDIUMINT", "INTEGER"),
        ("MEDIUMINT UNSIGNED", "INTEGER"),
        ("INT UNSIGNED", "BIGINT"),  # 0..4294967295 needs INT64
    ],
)
def test_narrow_and_unsigned_mysql_integers_widen_without_losing_range(
    declared: str, expected: str
) -> None:
    assert f"v {expected}" in _emit(f"CREATE TABLE t (v {declared})", "mysql", "postgres")


def test_unsigned_bigint_fails_closed_because_no_target_can_hold_it() -> None:
    # 0..18446744073709551615 exceeds INT64, and PostgreSQL/Oracle/SQL Server
    # have no unsigned integer type at all.
    assert _blocked("CREATE TABLE t (id BIGINT UNSIGNED)", "mysql", "postgres") == (
        "CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE"
    )


# --------------------------------------------------------------------------
# 8. PostgreSQL SERIAL and binary64 floating point are typed mappings, not
#    source-keyword passthrough.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_type", "expected_target_type"),
    [
        ("SERIAL", {"mysql": "INT AUTO_INCREMENT", "oracle": "NUMBER(10) GENERATED", "tsql": "INT IDENTITY"}),
        ("BIGSERIAL", {"mysql": "BIGINT AUTO_INCREMENT", "oracle": "NUMBER(19) GENERATED", "tsql": "BIGINT IDENTITY"}),
    ],
)
def test_postgres_serial_types_become_target_native_identity_columns(
    source_type: str, expected_target_type: dict[str, str]
) -> None:
    for target, expected in expected_target_type.items():
        emitted = _emit(f"CREATE TABLE t (id {source_type} PRIMARY KEY)", "postgres", target)
        assert expected in emitted
        assert "SERIAL" not in emitted


def test_serial_is_not_assumed_to_be_postgres_when_declared_by_another_source() -> None:
    assert _blocked("CREATE TABLE t (id SERIAL)", "mysql", "postgres") == (
        "CERTIFIED_DDL_UNSUPPORTED_TYPE"
    )


def test_unknown_user_defined_type_fails_closed_without_an_internal_error() -> None:
    assert _blocked("CREATE TABLE t (id custom_type)", "postgres", "mysql") == (
        "CERTIFIED_DDL_UNSUPPORTED_TYPE"
    )


@pytest.mark.parametrize(
    ("source", "target", "ddl", "expected"),
    [
        ("oracle", "postgres", "BINARY_DOUBLE", "DOUBLE PRECISION"),
        ("postgres", "mysql", "DOUBLE PRECISION", "DOUBLE"),
        ("postgres", "oracle", "DOUBLE PRECISION", "BINARY_DOUBLE"),
        ("postgres", "tsql", "DOUBLE PRECISION", "FLOAT(53)"),
    ],
)
def test_double_maps_to_binary64_without_narrowing(
    source: str, target: str, ddl: str, expected: str
) -> None:
    assert expected in _emit(f"CREATE TABLE t (score {ddl})", source, target)


# --------------------------------------------------------------------------
# 8. MySQL rejects an AUTO_INCREMENT column that is not a key (errno 1075),
#    where the other three dialects accept a non-key identity column. The
#    syntax leg cannot see this: sqlglot parses the statement happily.
# --------------------------------------------------------------------------


def test_identity_column_that_is_not_a_key_fails_closed_for_mysql() -> None:
    ddl = "CREATE TABLE t (id BIGINT GENERATED BY DEFAULT AS IDENTITY, name VARCHAR(10))"
    assert _blocked(ddl, "postgres", "mysql") == "CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY"
    # ... and is fine everywhere else.
    for target in ("oracle", "tsql"):
        assert "IDENTITY" in _emit(ddl, "postgres", target).upper()


@pytest.mark.parametrize("key", ["PRIMARY KEY (id)", "UNIQUE (id)"])
def test_identity_column_that_is_a_key_still_translates_to_mysql(key: str) -> None:
    ddl = f"CREATE TABLE t (id BIGINT GENERATED BY DEFAULT AS IDENTITY, {key})"
    assert "AUTO_INCREMENT" in _emit(ddl, "postgres", "mysql")


def test_adding_an_identity_column_fails_closed_for_mysql() -> None:
    report = translate_ddl(
        "ALTER TABLE t ADD COLUMN id BIGINT GENERATED BY DEFAULT AS IDENTITY",
        "postgres",
        "mysql",
        statement_kind="ALTER",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY"


# --------------------------------------------------------------------------
# 9. Integer widening across a round trip is deliberate, not an oversight:
#    Oracle has no native fixed-width integer, so INT16/INT32/INT64 render as
#    NUMBER(5)/(10)/(19), and NUMBER(p) reads back as DECIMAL(p, 0) rather
#    than an integer -- because NUMBER(10) holds 9999999999, which INT32
#    does *not*. The asymmetry is the safe direction and is pinned here.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "expected"), [("SMALLINT", "NUMBER(5)"), ("INTEGER", "NUMBER(10)"), ("BIGINT", "NUMBER(19)")]
)
def test_integers_render_as_the_documented_oracle_numbers(declared: str, expected: str) -> None:
    assert f"v {expected}" in _emit(f"CREATE TABLE t (v {declared})", "postgres", "oracle")


def test_oracle_number_reads_back_as_decimal_not_as_a_narrower_integer() -> None:
    # NUMBER(10) reaches 9999999999; reading it back as INTEGER would narrow
    # a real Oracle column by more than a factor of four.
    assert "v NUMERIC(10, 0)" in _emit("CREATE TABLE t (v NUMBER(10))", "oracle", "postgres")


# --------------------------------------------------------------------------
# 10. CURRENT_TIMESTAMP on SQL Server must match the DATETIME2 column.
# --------------------------------------------------------------------------


def test_current_timestamp_default_uses_sysdatetime_on_sql_server() -> None:
    emitted = _emit(
        "CREATE TABLE t (created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)", "postgres", "tsql"
    )
    assert "DATETIME2 NOT NULL DEFAULT SYSDATETIME()" in emitted
    assert "GETDATE()" not in emitted


# --------------------------------------------------------------------------
# 11. Clause order inside a column definition. Oracle's grammar is
#     `column datatype [DEFAULT expr] [inline_constraint]`, so DEFAULT must
#     come before NOT NULL; the other three accept either order. sqlglot
#     parses both, so the syntax leg cannot catch the wrong one.
# --------------------------------------------------------------------------


def test_oracle_puts_default_before_not_null() -> None:
    emitted = _emit(
        "CREATE TABLE t (id INT PRIMARY KEY, active BOOLEAN NOT NULL DEFAULT TRUE)",
        "postgres",
        "oracle",
    )
    assert "active NUMBER(1) DEFAULT 1 NOT NULL" in emitted
    assert "NOT NULL DEFAULT" not in emitted


@pytest.mark.parametrize("target", ["mysql", "tsql"])
def test_the_other_dialects_keep_not_null_first(target: str) -> None:
    emitted = _emit(
        "CREATE TABLE t (id INT PRIMARY KEY, n VARCHAR(10) NOT NULL DEFAULT 'x')",
        "postgres",
        target,
    )
    assert "NOT NULL DEFAULT 'x'" in emitted


def test_oracle_added_column_also_orders_default_first() -> None:
    report = translate_ddl(
        "ALTER TABLE t ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE",
        "postgres",
        "oracle",
        statement_kind="ALTER",
    )
    assert report["status"] == "PASSED", report
    assert "DEFAULT 1 NOT NULL" in report["emitted"]
