"""certified-drop-v1: `DROP TABLE [IF EXISTS] <name>` across the four dialects.

Scope came from measurement, not intuition: of 90 blocked DROP statements in
the 97-file corpus, 80 were a bare `DROP TABLE`. Every modifier is refused
because each one means something different on at least one dialect -- those
refusals are asserted here as behaviour, not documented as a limitation.
"""
from __future__ import annotations

import pytest

from elmos_sql_dialect.emitter import emit_drop_table
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError, DropTable
from elmos_sql_dialect.parser import parse_drop_table
from elmos_sql_dialect.scan import _classify

ALL = (Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL)
OTHERS = {
    Dialect.POSTGRES: ("mysql", "oracle", "tsql"),
    Dialect.MYSQL: ("postgres", "oracle", "tsql"),
}


# --------------------------------------------------------------------------
# parse
# --------------------------------------------------------------------------

def test_a_bare_drop_table_parses_into_the_canonical_model() -> None:
    assert parse_drop_table("DROP TABLE users", Dialect.POSTGRES) == DropTable(
        name="users", if_exists=False
    )


def test_if_exists_is_carried_on_the_model_not_decided_by_the_parser() -> None:
    assert parse_drop_table("DROP TABLE IF EXISTS users", Dialect.MYSQL) == DropTable(
        name="users", if_exists=True
    )


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("DROP TABLE users CASCADE", Dialect.POSTGRES),
        ("DROP TABLE users RESTRICT", Dialect.POSTGRES),
        ("DROP TEMPORARY TABLE users", Dialect.MYSQL),
    ],
)
def test_every_refused_modifier_is_refused_with_its_own_code(sql: str, dialect: Dialect) -> None:
    with pytest.raises(DialectError) as caught:
        parse_drop_table(sql, dialect)
    assert caught.value.code == "CERTIFIED_DROP_UNSUPPORTED_MODIFIER"


def test_the_refusal_message_names_the_actual_divergence_not_just_unsupported() -> None:
    """A refusal a reader cannot act on is a refusal that gets patched away."""
    with pytest.raises(DialectError) as caught:
        parse_drop_table("DROP TABLE users CASCADE", Dialect.POSTGRES)
    message = caught.value.message
    assert "PostgreSQL" in message and "Oracle" in message and "MySQL" in message
    assert "CASCADE CONSTRAINTS" in message


def test_a_qualified_table_name_is_refused_with_the_shared_ddl_code() -> None:
    with pytest.raises(DialectError) as caught:
        parse_drop_table("DROP TABLE public.users", Dialect.POSTGRES)
    assert caught.value.code == "CERTIFIED_DDL_NAMESPACE_MAPPING_REQUIRED"


def test_a_quoted_identifier_is_refused() -> None:
    with pytest.raises(DialectError) as caught:
        parse_drop_table('DROP TABLE "users"', Dialect.POSTGRES)
    assert caught.value.code == "CERTIFIED_DDL_QUOTED_IDENTIFIER"


@pytest.mark.parametrize("sql", ["DROP INDEX ix", "DROP SCHEMA app", "DROP VIEW v"])
def test_drops_of_other_object_kinds_are_out_of_this_profile(sql: str) -> None:
    with pytest.raises(DialectError) as caught:
        parse_drop_table(sql, Dialect.POSTGRES)
    assert caught.value.code == "CERTIFIED_DROP_UNSUPPORTED_STATEMENT"


def test_a_create_table_handed_to_the_drop_parser_is_refused() -> None:
    with pytest.raises(DialectError) as caught:
        parse_drop_table("CREATE TABLE t (id INT)", Dialect.POSTGRES)
    assert caught.value.code == "CERTIFIED_DROP_UNSUPPORTED_STATEMENT"


# --------------------------------------------------------------------------
# emit
# --------------------------------------------------------------------------

@pytest.mark.parametrize("dialect", ALL)
def test_a_bare_drop_emits_identically_on_every_dialect(dialect: Dialect) -> None:
    assert emit_drop_table(DropTable(name="users"), dialect) == "DROP TABLE users"


@pytest.mark.parametrize("dialect", [Dialect.POSTGRES, Dialect.MYSQL])
def test_if_exists_emits_where_the_spelling_needs_no_pinned_server_version(
    dialect: Dialect,
) -> None:
    assert emit_drop_table(DropTable(name="users", if_exists=True), dialect) == (
        "DROP TABLE IF EXISTS users"
    )


@pytest.mark.parametrize("dialect", [Dialect.ORACLE, Dialect.TSQL])
def test_if_exists_fails_closed_where_the_spelling_needs_a_pinned_version(
    dialect: Dialect,
) -> None:
    """Dropping the modifier would compile and would look like a success.

    The difference only shows the second time the migration runs: a no-op in
    the source, an error in the target. That is a behaviour change, so it
    fails closed -- the same rule `_if_not_exists_clause` already enforces.
    """
    with pytest.raises(DialectError) as caught:
        emit_drop_table(DropTable(name="users", if_exists=True), dialect)
    assert caught.value.code == "CERTIFIED_DROP_IF_EXISTS_UNSUPPORTED_BY_TARGET"
    assert "2016" in caught.value.message or "23ai" in caught.value.message


# --------------------------------------------------------------------------
# end to end through the engine
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source", [Dialect.POSTGRES, Dialect.MYSQL])
def test_a_bare_drop_round_trips_to_every_other_dialect_and_revalidates(
    source: Dialect,
) -> None:
    for target in OTHERS[source]:
        report = translate_ddl("DROP TABLE users", source.value, target, statement_kind="DROP")
        assert report["status"] == "PASSED", report
        assert report["profile"] == "certified-drop-v1"
        assert report["emitted"] == "DROP TABLE users"
        assert report["validation"]["syntaxStatus"] == "PASSED"


def test_a_refused_statement_is_reported_blocked_not_raised() -> None:
    report = translate_ddl(
        "DROP TABLE users CASCADE", "postgres", "mysql", statement_kind="DROP"
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DROP_UNSUPPORTED_MODIFIER"
    assert report["emitted"] is None


def test_the_drop_profile_is_reported_on_blocked_reports_too() -> None:
    report = translate_ddl(
        "DROP TABLE public.users", "postgres", "mysql", statement_kind="DROP"
    )
    assert report["profile"] == "certified-drop-v1"


# --------------------------------------------------------------------------
# scan integration -- the coverage number must move for the right reason
# --------------------------------------------------------------------------

def test_scan_admits_a_bare_drop_table() -> None:
    import sqlglot

    statement = sqlglot.parse_one("DROP TABLE users", read="postgres")
    assert _classify(statement, Dialect.POSTGRES) == ("IN_SUBSET", None, None)


def test_scan_reports_a_blocked_drop_under_a_drop_specific_code() -> None:
    """Before this profile every DROP fell under the generic
    CERTIFIED_DDL_UNSUPPORTED_STATEMENT, which said only "not a CREATE TABLE".
    """
    import sqlglot

    statement = sqlglot.parse_one("DROP TABLE users CASCADE", read="postgres")
    status, code, _reason = _classify(statement, Dialect.POSTGRES)
    assert (status, code) == ("OUT_OF_SUBSET", "CERTIFIED_DROP_UNSUPPORTED_MODIFIER")


def test_scan_still_refuses_a_drop_of_another_object_kind() -> None:
    import sqlglot

    statement = sqlglot.parse_one("DROP INDEX ix", read="postgres")
    status, code, _reason = _classify(statement, Dialect.POSTGRES)
    assert status == "OUT_OF_SUBSET"
    assert code in {"CERTIFIED_DDL_UNSUPPORTED_STATEMENT", "CERTIFIED_DROP_UNSUPPORTED_STATEMENT"}
