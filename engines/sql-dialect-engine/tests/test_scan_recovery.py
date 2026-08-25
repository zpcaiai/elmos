"""One unreadable statement must not discard the whole file.

`scan_repository` splits with the real parser on purpose -- splitting on ";"
miscounts semicolons inside string literals, `$$`-quoted bodies and
`BEGIN ... END` blocks. But when the parser refused the *file*, every statement
in it collapsed into a single `CERTIFIED_DDL_PARSE_FAILED` finding.

Measured on the checked-in corpus that was 750 KB of real schema across five
files, each killed by exactly one construct:

    pagila / sakila (postgres)  CREATE FUNCTION f(timestamp with time zone)
    chinook                     `\\c chinook;` -- a psql client directive
    sakila (mysql)              `password VARCHAR(40) BINARY`
    employees (mysql)           `DROP TABLE IF EXISTS a, b, c`

The lost coverage was the smaller problem. The larger one is that it FLATTERED
every ratio: the hardest files contributed 1 to the denominator instead of
hundreds.

The parser remains the primary splitter; these tests pin the fallback.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import report_to_dict, scan_repository
from elmos_sql_dialect.statement_splitter import split_statements


def _scan(tmp_path: Path, sql: str, dialect: Dialect = Dialect.POSTGRES) -> dict:
    (tmp_path / "schema.sql").write_text(sql, encoding="utf-8")
    return report_to_dict(scan_repository(tmp_path, dialect))


# --- the fallback splitter -------------------------------------------------
@pytest.mark.parametrize(
    ("label", "sql", "expected"),
    [
        ("plain", "CREATE TABLE a (x INT); CREATE TABLE b (y INT);", 2),
        ("semicolon in a string", "INSERT INTO t VALUES ('a;b'); SELECT 1;", 2),
        ("doubled quote", "INSERT INTO t VALUES ('o''brien; x'); SELECT 2;", 2),
        (
            "dollar-quoted body",
            "CREATE FUNCTION f() RETURNS int AS $$ BEGIN; RETURN 1; END; $$ LANGUAGE plpgsql;"
            " SELECT 3;",
            2,
        ),
        (
            "tagged dollar quote",
            "CREATE FUNCTION f() RETURNS int AS $body$ SELECT 1; $body$ LANGUAGE sql; SELECT 4;",
            2,
        ),
        ("line comment", "SELECT 1; -- a; comment\nSELECT 2;", 2),
        ("block comment", "/* a; b */ SELECT 1; SELECT 2;", 2),
        ("quoted identifier", 'CREATE TABLE "a;b" (x INT); SELECT 1;', 2),
        ("backtick identifier", "CREATE TABLE `a;b` (x INT); SELECT 1;", 2),
        ("no trailing semicolon", "SELECT 1; SELECT 2", 2),
    ],
)
def test_the_fallback_splitter_respects_everything_that_may_contain_a_semicolon(
    label: str, sql: str, expected: int
) -> None:
    assert len(split_statements(sql)) == expected, label


def test_the_fallback_splitter_reports_the_starting_line_of_each_statement() -> None:
    statements = split_statements(
        "CREATE TABLE a (x INT);\n\nCREATE TABLE b (\n  y INT\n);\n\nSELECT 1;\n"
    )
    assert [s.start_line for s in statements] == [1, 3, 7]


# --- recovery end to end ---------------------------------------------------
def test_a_single_unreadable_statement_no_longer_discards_the_file(
    tmp_path: Path,
) -> None:
    """`DROP TABLE IF EXISTS a, b` is the real employees.sql killer."""

    report = _scan(
        tmp_path,
        "CREATE TABLE a (x INT NOT NULL);\n"
        "DROP TABLE IF EXISTS a, b;\n"
        "CREATE TABLE c (y INT NOT NULL);\n",
        Dialect.MYSQL,
    )
    assert report["totals"]["discovered"] == 3
    assert report["totals"]["inSubset"] == 2
    codes = {b["reason_code"] for b in report["blockers"]}
    assert "CERTIFIED_DDL_PARSE_FAILED" in codes


def test_a_psql_client_directive_gets_its_own_code_not_a_parse_failure(
    tmp_path: Path,
) -> None:
    """`\\c` never reaches a server. Calling it a parse failure would blame the
    dialect grammar for a client-side construct."""

    report = _scan(
        tmp_path,
        "\\c chinook;\nCREATE TABLE a (x INT NOT NULL);\n",
    )
    codes = {b["reason_code"] for b in report["blockers"]}
    assert "CERTIFIED_DDL_CLIENT_DIRECTIVE" in codes
    assert "CERTIFIED_DDL_PARSE_FAILED" not in codes
    assert report["totals"]["inSubset"] == 1


def test_the_unreadable_statement_carries_a_line_number(tmp_path: Path) -> None:
    report = _scan(
        tmp_path,
        "CREATE TABLE a (x INT NOT NULL);\n\n\nDROP TABLE IF EXISTS a, b;\n",
        Dialect.MYSQL,
    )
    failures = [
        finding
        for finding in report["findings"]
        if finding["reason_code"] == "CERTIFIED_DDL_PARSE_FAILED"
    ]
    assert failures, "expected the unreadable statement to be reported"
    assert "line 4" in failures[0]["reason"]


def test_a_file_the_parser_accepts_is_unaffected_by_the_fallback(
    tmp_path: Path,
) -> None:
    """The primary path must keep using the real parser, byte for byte."""

    report = _scan(
        tmp_path,
        "CREATE TABLE a (x INT NOT NULL);\nCREATE TABLE b (y INT NOT NULL);\n",
    )
    assert report["totals"]["discovered"] == 2
    assert report["totals"]["inSubset"] == 2
    assert report["blockers"] == []


def test_recovery_does_not_silently_upgrade_anything_to_in_subset(
    tmp_path: Path,
) -> None:
    """Recovered statements are judged by the same `_classify` as any other."""

    report = _scan(
        tmp_path,
        "DROP TABLE IF EXISTS a, b;\nCREATE VIEW v AS SELECT 1;\nCREATE TABLE t (x INT NOT NULL);\n",
        Dialect.MYSQL,
    )
    assert report["totals"]["inSubset"] == 1
    assert report["totals"]["outOfSubset"] == 2
    assert report["totals"]["scanErrors"] == 0
