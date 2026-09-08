"""Three emission defects that only a real server could see.

The engine validates every emission by re-parsing it with sqlglot in the
target's strict mode. That leg is a third-party PARSER, not the target's own
grammar, and it cannot see a statement that parses but that the server refuses.

Executing the whole admitted corpus against a real PostgreSQL 16.13 and
MySQL 8.0.46 found three such classes. Each is asserted here so the syntax leg
is never again the only thing standing behind an emission.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl


def _emit(ddl: str, source: str, target: str, kind: str = "TABLE") -> str:
    report = translate_ddl(ddl, source, target, statement_kind=kind)
    assert report["status"] == "PASSED", report["reasonCode"]
    return report["emitted"]


def _blocked(ddl: str, source: str, target: str, kind: str = "TABLE") -> str:
    report = translate_ddl(ddl, source, target, statement_kind=kind)
    assert report["status"] == "BLOCKED", report
    return report["reasonCode"]


# --------------------------------------------------------------------------
# 1. `REFERENCES t ()` -- emitted SQL no server accepts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_a_reference_without_a_column_list_does_not_emit_empty_parentheses(
    target: str,
) -> None:
    """MySQL reported this as a syntax error near `) ON DELETE NO ACTION`.

    `REFERENCES t` means "the target's primary key" on all four dialects, so
    omitting the list is faithful rather than a guess.
    """
    emitted = _emit(
        "ALTER TABLE orders ADD CONSTRAINT fk_o FOREIGN KEY (customer_id) REFERENCES customers",
        "postgres",
        target,
        kind="ALTER",
    )
    assert "REFERENCES customers" in emitted
    assert "()" not in emitted


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_an_explicit_reference_column_list_is_still_rendered(target: str) -> None:
    emitted = _emit(
        "ALTER TABLE orders ADD CONSTRAINT fk_o FOREIGN KEY (cid) REFERENCES customers (id)",
        "postgres",
        target,
        kind="ALTER",
    )
    assert "REFERENCES customers (id)" in emitted


def test_the_inline_reference_form_also_omits_empty_parentheses() -> None:
    emitted = _emit("CREATE TABLE orders (cid VARCHAR(10) REFERENCES customers)", "postgres", "mysql")
    assert "REFERENCES customers" in emitted
    assert "()" not in emitted


# --------------------------------------------------------------------------
# 2. MySQL error 1170 -- a TEXT column cannot be indexed without a prefix
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE t (user_id TEXT, PRIMARY KEY (user_id))",
        "CREATE TABLE t (user_id TEXT, UNIQUE (user_id))",
        "CREATE TABLE t (user_id TEXT, room_id VARCHAR(10), PRIMARY KEY (user_id, room_id))",
    ],
)
def test_a_text_column_in_a_key_fails_closed_for_mysql(ddl: str) -> None:
    """A prefix index is a WEAKER constraint -- it compares only the first N
    characters, so two different values can satisfy a UNIQUE the source
    rejects. Picking N is a profile decision, not a translation."""
    assert _blocked(ddl, "postgres", "mysql") == "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX"


def test_the_refusal_names_the_offending_columns() -> None:
    report = translate_ddl(
        "CREATE TABLE t (user_id TEXT, room_id TEXT, PRIMARY KEY (user_id, room_id))",
        "postgres",
        "mysql",
    )
    assert "user_id" in report["reason"] and "room_id" in report["reason"]


@pytest.mark.parametrize("target", ["postgres", "oracle", "tsql"])
def test_a_text_key_is_fine_on_every_other_dialect(target: str) -> None:
    """The restriction is MySQL's, so it must not leak into the other three."""
    emitted = _emit("CREATE TABLE t (user_id TEXT, PRIMARY KEY (user_id))", "mysql", target)
    assert "PRIMARY KEY (user_id)" in emitted


def test_a_text_column_that_is_not_a_key_still_translates_to_mysql() -> None:
    emitted = _emit("CREATE TABLE t (id VARCHAR(10) PRIMARY KEY, body TEXT)", "postgres", "mysql")
    assert "LONGTEXT" in emitted


def test_a_text_foreign_key_column_also_fails_closed() -> None:
    assert (
        _blocked(
            "CREATE TABLE t (owner_id TEXT, FOREIGN KEY (owner_id) REFERENCES owners (id))",
            "postgres",
            "mysql",
        )
        == "CERTIFIED_DDL_MYSQL_TEXT_KEY_REQUIRES_PREFIX"
    )


# --------------------------------------------------------------------------
# 3. MySQL error 1101 -- a TEXT column cannot carry a DEFAULT
# --------------------------------------------------------------------------


def test_a_text_column_with_a_default_fails_closed_for_mysql() -> None:
    assert (
        _blocked("CREATE TABLE t (state TEXT DEFAULT 'NEW')", "postgres", "mysql")
        == "CERTIFIED_DDL_MYSQL_TEXT_DEFAULT_UNSUPPORTED"
    )


def test_dropping_the_default_is_explicitly_not_the_fix() -> None:
    report = translate_ddl("CREATE TABLE t (state TEXT DEFAULT 'NEW')", "postgres", "mysql")
    assert "INSERT" in report["reason"]


@pytest.mark.parametrize("target", ["postgres", "oracle", "tsql"])
def test_a_text_default_is_fine_on_every_other_dialect(target: str) -> None:
    emitted = _emit("CREATE TABLE t (state TEXT DEFAULT 'NEW')", "mysql", target)
    assert "DEFAULT 'NEW'" in emitted


# --------------------------------------------------------------------------
# 4. MySQL error 1064 -- an identifier that is a reserved word on the target
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["signal", "rank", "system", "groups", "lead"])
def test_a_column_named_after_a_mysql_reserved_word_fails_closed(name: str) -> None:
    """PostgreSQL accepts these unquoted; MySQL does not.

    sqlglot's mysql dialect does not model reserved words, so the syntax leg
    re-parsed the emission happily and a real server rejected it.
    """
    assert (
        _blocked(f"CREATE TABLE t (id VARCHAR(10), {name} VARCHAR(32))", "postgres", "mysql")
        == "CERTIFIED_DDL_TARGET_RESERVED_IDENTIFIER"
    )


def test_a_table_named_after_a_mysql_reserved_word_fails_closed() -> None:
    assert (
        _blocked("CREATE TABLE groups (id VARCHAR(10))", "postgres", "mysql")
        == "CERTIFIED_DDL_TARGET_RESERVED_IDENTIFIER"
    )


def test_the_refusal_explains_why_quoting_is_not_the_fix() -> None:
    report = translate_ddl("CREATE TABLE t (id VARCHAR(10), signal VARCHAR(32))", "postgres", "mysql")
    assert "read back" in report["reason"]


@pytest.mark.parametrize("target", ["oracle", "tsql"])
def test_the_mysql_reserved_list_does_not_leak_into_other_targets(target: str) -> None:
    """Only MySQL has execution evidence behind it, so only MySQL is gated.

    Oracle and SQL Server have their own reserved words and no rootless local
    instance to prove them against; leaving them ungated is a stated gap, not
    a claim that their identifiers are safe.
    """
    emitted = _emit("CREATE TABLE t (id VARCHAR(10), signal VARCHAR(32))", "postgres", target)
    assert "signal" in emitted


def test_an_added_text_column_with_a_default_fails_closed_for_mysql() -> None:
    """MySQL errno 1101 again, this time through ALTER TABLE ADD COLUMN."""
    assert (
        _blocked(
            "ALTER TABLE runs ADD COLUMN trust_namespace TEXT NOT NULL DEFAULT 'branch'",
            "postgres",
            "mysql",
            kind="ALTER",
        )
        == "CERTIFIED_DDL_MYSQL_TEXT_DEFAULT_UNSUPPORTED"
    )


def test_altering_a_table_whose_name_is_reserved_fails_closed_for_mysql() -> None:
    assert (
        _blocked("ALTER TABLE groups ADD COLUMN c VARCHAR(10)", "postgres", "mysql", kind="ALTER")
        == "CERTIFIED_DDL_TARGET_RESERVED_IDENTIFIER"
    )


def test_a_non_reserved_column_is_unaffected() -> None:
    assert "alert_id" in _emit("CREATE TABLE t (alert_id VARCHAR(64))", "postgres", "mysql")
