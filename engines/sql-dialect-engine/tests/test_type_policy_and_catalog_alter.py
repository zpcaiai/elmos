from __future__ import annotations

import pytest

from elmos_sql_dialect.catalog import ColumnCatalog
from elmos_sql_dialect.emitter import emit_alter_table, emit_create_table
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import (
    AlterColumnType,
    CanonicalType,
    CanonicalTypeRef,
    Dialect,
    DialectError,
    DropNotNull,
    SetNotNull,
    TypeMigrationPolicy,
)
from elmos_sql_dialect.parser import parse_alter_table, parse_create_table


def test_unsigned_bigint_with_decimal20_policy() -> None:
    policy = TypeMigrationPolicy(unsigned_bigint="decimal20")
    sql = "CREATE TABLE t (val BIGINT UNSIGNED NOT NULL)"
    table = parse_create_table(sql, Dialect.MYSQL, type_policy=policy)
    col = table.columns[0]
    assert col.type_ref.canonical_type == CanonicalType.DECIMAL
    assert col.type_ref.precision == 20
    assert col.type_ref.scale == 0

    pg_ddl = emit_create_table(table, Dialect.POSTGRES)
    assert "NUMERIC(20, 0)" in pg_ddl or "DECIMAL(20, 0)" in pg_ddl


def test_unsigned_bigint_with_checked_bigint_policy() -> None:
    policy = TypeMigrationPolicy(unsigned_bigint="checked_bigint")
    sql = "CREATE TABLE t (val BIGINT UNSIGNED NOT NULL)"
    table = parse_create_table(sql, Dialect.MYSQL, type_policy=policy)
    col = table.columns[0]
    assert col.type_ref.canonical_type == CanonicalType.INT64

    pg_ddl = emit_create_table(table, Dialect.POSTGRES)
    assert "BIGINT" in pg_ddl


def test_unsigned_bigint_fails_closed_without_policy() -> None:
    sql = "CREATE TABLE t (val BIGINT UNSIGNED NOT NULL)"
    with pytest.raises(DialectError) as exc:
        parse_create_table(sql, Dialect.MYSQL)
    assert exc.value.code == "CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE"


def test_unbounded_decimal_policy() -> None:
    policy = TypeMigrationPolicy(unbounded_decimal="decimal38_10")
    sql = "CREATE TABLE t (amount DECIMAL NOT NULL)"
    table = parse_create_table(sql, Dialect.POSTGRES, type_policy=policy)
    col = table.columns[0]
    assert col.type_ref.canonical_type == CanonicalType.DECIMAL
    assert col.type_ref.precision == 38
    assert col.type_ref.scale == 10

    mysql_ddl = emit_create_table(table, Dialect.MYSQL)
    assert "DECIMAL(38, 10)" in mysql_ddl


def test_unbounded_varchar_policy() -> None:
    policy = TypeMigrationPolicy(unbounded_varchar="text")
    sql = "CREATE TABLE t (bio VARCHAR NOT NULL)"
    table = parse_create_table(sql, Dialect.POSTGRES, type_policy=policy)
    col = table.columns[0]
    assert col.type_ref.canonical_type == CanonicalType.TEXT

    mysql_ddl = emit_create_table(table, Dialect.MYSQL)
    assert "LONGTEXT" in mysql_ddl or "TEXT" in mysql_ddl


def test_alter_table_set_not_null_with_catalog() -> None:
    catalog = ColumnCatalog({"users": {"email": CanonicalType.VARCHAR}}, {})
    sql = "ALTER TABLE users ALTER COLUMN email SET NOT NULL"
    parsed = parse_alter_table(sql, Dialect.POSTGRES, allow_alter_column=True)
    assert len(parsed.actions) == 1
    assert isinstance(parsed.actions[0], SetNotNull)
    assert parsed.actions[0].column == "email"

    pg_sql = emit_alter_table(parsed, Dialect.POSTGRES, catalog=catalog)
    assert pg_sql == "ALTER TABLE users ALTER COLUMN email SET NOT NULL"

    oracle_sql = emit_alter_table(parsed, Dialect.ORACLE, catalog=catalog)
    assert oracle_sql == "ALTER TABLE users MODIFY (email NOT NULL)"

    mysql_sql = emit_alter_table(parsed, Dialect.MYSQL, catalog=catalog)
    assert mysql_sql == "ALTER TABLE users MODIFY COLUMN email VARCHAR(255) NOT NULL"

    tsql_sql = emit_alter_table(parsed, Dialect.TSQL, catalog=catalog)
    assert tsql_sql == "ALTER TABLE users ALTER COLUMN email NVARCHAR(255) NOT NULL"


def test_alter_table_drop_not_null_with_catalog() -> None:
    catalog = ColumnCatalog({"users": {"email": CanonicalType.VARCHAR}}, {})
    sql = "ALTER TABLE users ALTER COLUMN email DROP NOT NULL"
    parsed = parse_alter_table(sql, Dialect.POSTGRES, allow_alter_column=True)
    assert len(parsed.actions) == 1
    assert isinstance(parsed.actions[0], DropNotNull)

    mysql_sql = emit_alter_table(parsed, Dialect.MYSQL, catalog=catalog)
    assert mysql_sql == "ALTER TABLE users MODIFY COLUMN email VARCHAR(255) NULL"


def test_alter_table_alter_column_type() -> None:
    sql = "ALTER TABLE users ALTER COLUMN age TYPE BIGINT"
    parsed = parse_alter_table(sql, Dialect.POSTGRES, allow_alter_column=True)
    assert len(parsed.actions) == 1
    assert isinstance(parsed.actions[0], AlterColumnType)
    assert parsed.actions[0].column == "age"
    assert parsed.actions[0].type_ref.canonical_type == CanonicalType.INT64

    assert emit_alter_table(parsed, Dialect.POSTGRES) == "ALTER TABLE users ALTER COLUMN age TYPE BIGINT"
    assert emit_alter_table(parsed, Dialect.ORACLE) == "ALTER TABLE users MODIFY (age NUMBER(19))"
    assert emit_alter_table(parsed, Dialect.MYSQL) == "ALTER TABLE users MODIFY COLUMN age BIGINT"
    assert emit_alter_table(parsed, Dialect.TSQL) == "ALTER TABLE users ALTER COLUMN age BIGINT"


def test_translate_ddl_alter_table_with_catalog() -> None:
    catalog = ColumnCatalog({"users": {"email": CanonicalType.VARCHAR}}, {})
    res = translate_ddl(
        "ALTER TABLE users ALTER COLUMN email SET NOT NULL",
        "postgres",
        "mysql",
        statement_kind="ALTER",
        catalog=catalog,
    )
    assert res["status"] == "PASSED"
    assert res["emitted"] == "ALTER TABLE users MODIFY COLUMN email VARCHAR(255) NOT NULL"
