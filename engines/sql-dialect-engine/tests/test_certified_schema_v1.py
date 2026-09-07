"""The minimal, side-effect-free CREATE SCHEMA profile."""
from __future__ import annotations

import pytest

from elmos_sql_dialect.emitter import emit_create_schema
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError, Schema
from elmos_sql_dialect.parser import parse_create_schema


@pytest.mark.parametrize("dialect", [Dialect.POSTGRES, Dialect.MYSQL, Dialect.TSQL])
def test_a_bare_schema_is_emitted_on_engines_with_logical_namespaces(dialect: Dialect) -> None:
    assert emit_create_schema(Schema("app"), dialect) == "CREATE SCHEMA app"


@pytest.mark.parametrize(
    ("source", "dialect"), [("mysql", Dialect.POSTGRES), ("postgres", Dialect.MYSQL)]
)
def test_if_not_exists_is_preserved_where_the_target_spells_it(source: str, dialect: Dialect) -> None:
    report = translate_ddl(
        "CREATE SCHEMA IF NOT EXISTS app", source, dialect.value, statement_kind="SCHEMA"
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == "CREATE SCHEMA IF NOT EXISTS app"


def test_sql_server_does_not_silently_drop_schema_rerun_semantics() -> None:
    report = translate_ddl(
        "CREATE SCHEMA IF NOT EXISTS app", "postgres", "tsql", statement_kind="SCHEMA"
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET"


def test_oracle_schema_creation_does_not_create_a_user_as_a_side_effect() -> None:
    report = translate_ddl("CREATE SCHEMA app", "postgres", "oracle", statement_kind="SCHEMA")
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_SCHEMA_UNSUPPORTED_TARGET"


def test_schema_parser_rejects_authorization_and_qualified_names() -> None:
    with pytest.raises(DialectError) as authorization:
        parse_create_schema("CREATE SCHEMA app AUTHORIZATION owner", Dialect.POSTGRES)
    assert authorization.value.code == "CERTIFIED_SCHEMA_UNSUPPORTED_STATEMENT"

    with pytest.raises(DialectError) as qualified:
        parse_create_schema("CREATE SCHEMA public.app", Dialect.POSTGRES)
    assert qualified.value.code == "CERTIFIED_SCHEMA_QUALIFIED_NAME"


def test_flat_same_connector_checks_are_canonicalized_without_changing_logic() -> None:
    report = translate_ddl(
        "CREATE TABLE t (a INT, b INT, c INT, CHECK (a > 0 AND b > 0 AND c > 0))",
        "postgres",
        "mysql",
    )
    assert report["status"] == "PASSED", report
    assert "CHECK (a > 0 AND b > 0 AND c > 0)" in report["emitted"]
