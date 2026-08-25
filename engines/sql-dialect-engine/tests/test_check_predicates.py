"""certified-ddl-v1 CHECK: null tests, IN and BETWEEN.

Chosen by measurement. `CERTIFIED_DDL_UNSUPPORTED_CHECK` was 458 blocked
constraints across 6 distinct reasons in a scan of 89 real `.sql` files, and
three reasons were 429 of the 458:

      376x  Is        (IS NULL / IS NOT NULL)
       49x  In        (IN (literal, ...))
        4x  Between   (BETWEEN literal AND literal)

The profile's stated reason for being narrow is "no function calls, no
subqueries, since function names are exactly where dialects diverge most".
These three are operators, not function calls: SQL-92 core, spelled and meant
identically by PostgreSQL, MySQL, Oracle and SQL Server. That is why they need
no per-dialect rendering, while the ones that genuinely diverge stay out.
"""
from __future__ import annotations

import itertools

import pytest

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect

ALL = [d.value for d in Dialect]
PAIRS = [(s, t) for s, t in itertools.permutations(ALL, 2)]


def _check_line(report: dict) -> str:
    return next(line.strip() for line in report["emitted"].splitlines() if "CHECK" in line)


@pytest.mark.parametrize(("source", "target"), PAIRS)
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("CREATE TABLE t (a INT, CHECK (a IS NULL))", "CHECK (a IS NULL)"),
        ("CREATE TABLE t (a INT, CHECK (a IS NOT NULL))", "CHECK (a IS NOT NULL)"),
        ("CREATE TABLE t (a INT, CHECK (a BETWEEN 1 AND 9))", "CHECK (a BETWEEN 1 AND 9)"),
        (
            "CREATE TABLE t (s VARCHAR(8), CHECK (s IN ('A', 'B', 'C')))",
            "CHECK (s IN ('A', 'B', 'C'))",
        ),
    ],
)
def test_the_three_universal_predicates_render_identically_everywhere(
    source: str, target: str, sql: str, expected: str
) -> None:
    """Identical spelling on every one of the twelve directed pairs.

    `IS NOT NULL` is the case that makes this test worth having: sqlglot parses
    it as `Is(negate=True)` from PostgreSQL and as `Not(Is(...))` from the other
    three, so handling only one shape silently admits it from one source
    dialect and refuses it from the rest.
    """

    report = translate_ddl(sql, source, target, statement_kind="TABLE")
    assert report["status"] == "PASSED", report["reasonCode"]
    assert _check_line(report) == expected
    assert report["validation"]["syntaxStatus"] == "PASSED"


def test_predicates_compose_with_the_existing_binary_comparisons() -> None:
    report = translate_ddl(
        "CREATE TABLE t (a INT, s VARCHAR(8), CHECK (a > 0 AND s IN ('A', 'B')))",
        "postgres",
        "oracle",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert _check_line(report) == "CHECK (a > 0 AND s IN ('A', 'B'))"


def test_string_members_are_quoted_and_embedded_quotes_doubled() -> None:
    report = translate_ddl(
        "CREATE TABLE t (s VARCHAR(8), CHECK (s IN ('o''brien', 'b')))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert _check_line(report) == "CHECK (s IN ('o''brien', 'b'))"


@pytest.mark.parametrize(
    ("label", "sql"),
    [
        # `~` / REGEXP / REGEXP_LIKE / nothing at all in T-SQL.
        ("regex", "CREATE TABLE t (s VARCHAR(8), CHECK (s ~ '^[a-f]+$'))"),
        # MySQL's default collation is case-insensitive, so the same predicate
        # accepts different rows on different targets.
        ("like", "CREATE TABLE t (s VARCHAR(8), CHECK (s LIKE 'a%'))"),
        # Parses as `Is` too, but Oracle has no boolean type and no IS TRUE.
        ("is-true", "CREATE TABLE t (b BOOLEAN, CHECK (b IS TRUE))"),
        # PostgreSQL-only.
        ("between-symmetric", "CREATE TABLE t (a INT, CHECK (a BETWEEN SYMMETRIC 9 AND 1))"),
        # Not present in the measured corpus; left out rather than shipped untested.
        ("not-in", "CREATE TABLE t (a INT, CHECK (a NOT IN (1, 2)))"),
        # A subquery is the other half of the original narrowing rationale.
        ("in-subquery", "CREATE TABLE t (a INT, CHECK (a IN (SELECT x FROM u)))"),
        # Still a function call.
        ("function", "CREATE TABLE t (s VARCHAR(8), CHECK (LENGTH(s) > 2))"),
    ],
)
def test_the_genuinely_divergent_predicates_are_still_refused(label: str, sql: str) -> None:
    report = translate_ddl(sql, "postgres", "mysql", statement_kind="TABLE")
    assert report["status"] == "BLOCKED", f"{label} was admitted"
    assert report["emitted"] is None


def test_a_doubly_negated_null_test_is_refused() -> None:
    report = translate_ddl(
        "CREATE TABLE t (a INT, CHECK (NOT (a IS NOT NULL)))",
        "mysql",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"


@pytest.mark.parametrize(("source", "target"), [("postgres", "mysql"), ("mysql", "oracle")])
def test_redundant_parentheses_around_a_check_are_unwrapped(
    source: str, target: str
) -> None:
    """Purely syntactic: 19 occurrences in the measured corpus, no semantics."""

    report = translate_ddl(
        "CREATE TABLE t (a INT, CHECK ((a > 0)))", source, target, statement_kind="TABLE"
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert _check_line(report) == "CHECK (a > 0)"


def test_parentheses_inside_a_conjunction_are_unwrapped_too() -> None:
    report = translate_ddl(
        "CREATE TABLE t (a INT, b INT, CHECK ((a > 0) AND (b IS NOT NULL)))",
        "postgres",
        "tsql",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert _check_line(report) == "CHECK (a > 0 AND b IS NOT NULL)"


def test_absurdly_nested_parentheses_fail_closed_rather_than_recursing() -> None:
    sql = "CREATE TABLE t (a INT, CHECK (" + "(" * 12 + "a > 0" + ")" * 12 + "))"
    report = translate_ddl(sql, "postgres", "mysql", statement_kind="TABLE")
    assert report["status"] == "BLOCKED"
