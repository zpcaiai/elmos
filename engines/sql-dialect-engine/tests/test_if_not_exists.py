"""`IF NOT EXISTS` in certified-ddl-v1 -- admitted, and never silently dropped.

Why it is in the profile at all: a scan of 89 real `.sql` files
(5,297 statements) found `CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER` was 54
blocked statements across only 4 distinct reasons -- the densest blocker in the
profile that is a *spelling* rather than a semantic gap.

Why it is not simply always emitted: the four certified dialects disagree, and
the disagreement is not symmetric between tables and indexes. MySQL has
`CREATE TABLE IF NOT EXISTS` and has no `CREATE INDEX IF NOT EXISTS`.

Why dropping it is not an option: the modifier decides what the SECOND run of a
migration does. Source says no-op, target-without-it says error. That is a
behaviour change, so it fails closed like every other one here.

The support table is backed by execution against real servers (PostgreSQL
16.15, MySQL 8.0.46) in `.ai/measurement-2026-08-21/if-not-exists-evidence.json`
-- including the refusal: real MySQL answers `CREATE INDEX IF NOT EXISTS` with
error 1064.
"""
from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl

_TABLE = (
    "CREATE TABLE IF NOT EXISTS orders ("
    "id BIGINT PRIMARY KEY, total DECIMAL(12,2) NOT NULL)"
)
_INDEX = "CREATE INDEX IF NOT EXISTS idx_orders_total ON orders (total)"
_PLAIN_TABLE = "CREATE TABLE orders (id BIGINT PRIMARY KEY, total DECIMAL(12,2) NOT NULL)"


@pytest.mark.parametrize(
    ("source", "target"),
    [("mysql", "postgres"), ("oracle", "postgres"), ("tsql", "postgres"), ("postgres", "mysql")],
)
def test_table_if_not_exists_survives_to_targets_that_can_say_it(
    source: str, target: str
) -> None:
    report = translate_ddl(_TABLE, source, target, statement_kind="TABLE")
    assert report["status"] == "PASSED", report["reasonCode"]
    assert report["emitted"].startswith("CREATE TABLE IF NOT EXISTS orders")
    assert report["validation"]["syntaxStatus"] == "PASSED"


def test_index_if_not_exists_survives_to_postgres() -> None:
    report = translate_ddl(_INDEX, "mysql", "postgres", statement_kind="INDEX")
    assert report["status"] == "PASSED", report["reasonCode"]
    assert report["emitted"].startswith("CREATE INDEX IF NOT EXISTS idx_orders_total")


@pytest.mark.parametrize("target", ["oracle", "tsql"])
def test_table_if_not_exists_fails_closed_for_targets_that_cannot_say_it(
    target: str,
) -> None:
    report = translate_ddl(_TABLE, "postgres", target, statement_kind="TABLE")
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET"
    # The decisive property: no statement is handed back at all. Emitting the
    # table without the modifier would pass every syntax check and change what
    # a re-run does.
    assert report["emitted"] is None


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_index_if_not_exists_fails_closed_including_mysql(target: str) -> None:
    """MySQL is the asymmetric one: it takes the table form and not the index form."""

    report = translate_ddl(_INDEX, "postgres", target, statement_kind="INDEX")
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET"
    assert report["emitted"] is None


@pytest.mark.parametrize(
    ("source", "target"),
    [("postgres", "oracle"), ("postgres", "tsql"), ("mysql", "oracle"), ("oracle", "tsql")],
)
def test_a_statement_without_the_modifier_is_unaffected_on_every_target(
    source: str, target: str
) -> None:
    """The widening must not narrow anything: no modifier, no new refusal."""

    report = translate_ddl(_PLAIN_TABLE, source, target, statement_kind="TABLE")
    assert report["status"] == "PASSED", report["reasonCode"]
    assert report["emitted"].startswith("CREATE TABLE orders")
    assert "IF NOT EXISTS" not in report["emitted"]


def test_the_modifier_is_not_invented_when_the_source_did_not_ask_for_it() -> None:
    report = translate_ddl(_PLAIN_TABLE, "mysql", "postgres", statement_kind="TABLE")
    assert "IF NOT EXISTS" not in report["emitted"]


def test_other_create_modifiers_are_still_refused() -> None:
    """`exists` left the refusal list; `replace` and friends did not."""

    report = translate_ddl(
        "CREATE OR REPLACE TABLE orders (id BIGINT PRIMARY KEY)",
        "mysql",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER"
