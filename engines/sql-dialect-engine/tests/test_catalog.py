"""The catalogue turns two blind statement kinds into decidable ones.

`CREATE INDEX` and `ALTER TABLE ADD CONSTRAINT` do not carry their columns'
types, so against MySQL the engine could not tell whether the key was over a
TEXT column -- and emitted SQL the server rejects with error 1170. Executing
the corpus found 201 of them.

The rule under test is deliberately asymmetric: a catalogue that KNOWS the
column is TEXT refuses; a catalogue that has not seen the column says nothing.
Absence of evidence must not become evidence of absence.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.catalog import ColumnCatalog
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import CanonicalType, Dialect
from elmos_sql_dialect.parser import parse_alter_table, parse_create_table

TEXT_TABLE = "CREATE TABLE access_tokens (token TEXT, user_id VARCHAR(64))"


def _catalog(*ddl: str) -> ColumnCatalog:
    catalog = ColumnCatalog()
    for statement in ddl:
        catalog.add_table(parse_create_table(statement, Dialect.POSTGRES))
    return catalog


def test_a_catalog_records_canonical_types_per_table() -> None:
    catalog = _catalog(TEXT_TABLE)
    assert catalog.type_of("access_tokens", "token") is CanonicalType.TEXT
    assert catalog.type_of("access_tokens", "user_id") is CanonicalType.VARCHAR


def test_an_unseen_column_is_unknown_not_absent() -> None:
    """None must mean "not in the catalogue", never "fine"."""
    assert _catalog(TEXT_TABLE).type_of("access_tokens", "nope") is None
    assert _catalog(TEXT_TABLE).type_of("other_table", "token") is None


def test_lookup_is_case_folded() -> None:
    """The four dialects disagree about unquoted-identifier case folding, so a
    case-sensitive catalogue would miss `ON Access_Tokens (Token)`."""
    catalog = _catalog(TEXT_TABLE)
    assert catalog.type_of("ACCESS_TOKENS", "TOKEN") is CanonicalType.TEXT


def test_add_column_extends_the_catalog() -> None:
    catalog = _catalog(TEXT_TABLE)
    catalog.apply_alter(parse_alter_table("ALTER TABLE access_tokens ADD COLUMN note TEXT", Dialect.POSTGRES))
    assert catalog.type_of("access_tokens", "note") is CanonicalType.TEXT


def test_drop_and_rename_keep_the_catalog_truthful() -> None:
    catalog = _catalog(TEXT_TABLE)
    catalog.apply_alter(parse_alter_table("ALTER TABLE access_tokens DROP COLUMN token", Dialect.POSTGRES))
    assert catalog.type_of("access_tokens", "token") is None
    catalog.apply_alter(
        parse_alter_table("ALTER TABLE access_tokens RENAME COLUMN user_id TO owner_id", Dialect.POSTGRES)
    )
    assert catalog.type_of("access_tokens", "owner_id") is CanonicalType.VARCHAR
    assert catalog.type_of("access_tokens", "user_id") is None


# --------------------------------------------------------------------------
# the behaviour the catalogue exists for
# --------------------------------------------------------------------------

INDEX_ON_TEXT = "CREATE INDEX ix_token ON access_tokens (token)"
UNIQUE_ON_TEXT = "ALTER TABLE access_tokens ADD CONSTRAINT u_token UNIQUE (token)"


@pytest.mark.parametrize(("ddl", "kind"), [(INDEX_ON_TEXT, "INDEX"), (UNIQUE_ON_TEXT, "ALTER")])
def test_without_a_catalog_the_engine_does_not_guess(ddl: str, kind: str) -> None:
    """The previous behaviour, kept deliberately: one statement carries no type,
    so the engine emits rather than inventing a refusal it cannot justify."""
    report = translate_ddl(ddl, "postgres", "mysql", statement_kind=kind)
    assert report["status"] == "PASSED", report["reasonCode"]


@pytest.mark.parametrize(("ddl", "kind"), [(INDEX_ON_TEXT, "INDEX"), (UNIQUE_ON_TEXT, "ALTER")])
def test_with_a_catalog_a_text_key_fails_closed_for_mysql(ddl: str, kind: str) -> None:
    report = translate_ddl(ddl, "postgres", "mysql", statement_kind=kind, catalog=_catalog(TEXT_TABLE))
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX"


@pytest.mark.parametrize(("ddl", "kind"), [(INDEX_ON_TEXT, "INDEX"), (UNIQUE_ON_TEXT, "ALTER")])
def test_a_catalog_that_has_not_seen_the_table_changes_nothing(ddl: str, kind: str) -> None:
    report = translate_ddl(
        ddl,
        "postgres",
        "mysql",
        statement_kind=kind,
        catalog=_catalog("CREATE TABLE unrelated (a VARCHAR(10))"),
    )
    assert report["status"] == "PASSED", report["reasonCode"]


def test_a_non_text_key_is_unaffected_by_the_catalog() -> None:
    report = translate_ddl(
        "CREATE INDEX ix_user ON access_tokens (user_id)",
        "postgres",
        "mysql",
        statement_kind="INDEX",
        catalog=_catalog(TEXT_TABLE),
    )
    assert report["status"] == "PASSED", report["reasonCode"]


@pytest.mark.parametrize("target", ["postgres", "oracle", "tsql"])
def test_the_catalog_rule_is_mysql_only(target: str) -> None:
    report = translate_ddl(INDEX_ON_TEXT, "mysql", target, statement_kind="INDEX", catalog=_catalog(TEXT_TABLE))
    assert report["status"] == "PASSED", report["reasonCode"]


def test_a_foreign_key_over_a_text_column_also_fails_closed() -> None:
    report = translate_ddl(
        "ALTER TABLE access_tokens ADD CONSTRAINT fk_t FOREIGN KEY (token) REFERENCES o (id)",
        "postgres",
        "mysql",
        statement_kind="ALTER",
        catalog=_catalog(TEXT_TABLE),
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX"


def test_a_primary_key_declared_in_a_separate_alter_is_recorded() -> None:
    """pg_dump-style schemas put the key in an ALTER, not the CREATE TABLE.

    Missing this left the catalogue with nine tables and zero keys on the
    northwind corpus -- the exact corpus where MySQL then demanded a
    referenced column list the catalogue could no longer supply.
    """
    catalog = _catalog("CREATE TABLE region (region_id VARCHAR(10), description VARCHAR(60))")
    assert catalog.primary_key_of("region") is None
    catalog.apply_alter(
        parse_alter_table(
            "ALTER TABLE region ADD CONSTRAINT region_pkey PRIMARY KEY (region_id)",
            Dialect.POSTGRES,
        )
    )
    assert catalog.primary_key_of("region") == ("region_id",)


def test_an_inline_primary_key_is_recorded_too() -> None:
    catalog = _catalog("CREATE TABLE region (region_id VARCHAR(10) PRIMARY KEY)")
    assert catalog.primary_key_of("region") == ("region_id",)
