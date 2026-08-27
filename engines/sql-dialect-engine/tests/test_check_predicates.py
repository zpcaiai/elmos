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


@pytest.mark.parametrize("source", ["postgres", "mysql"])
@pytest.mark.parametrize("target", ["postgres", "mysql", "oracle", "tsql"])
def test_default_space_trim_is_a_typed_cross_dialect_check_value(
    source: str, target: str
) -> None:
    if source == target:
        pytest.skip("same-dialect translation is not a supported route")
    spelling = "btrim" if source == "postgres" else "trim"
    report = translate_ddl(
        f"CREATE TABLE t (s VARCHAR(16), CHECK ({spelling}(s) <> ''))",
        source,
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "TRIM(s) <> ''" in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_null_test_equality_expands_to_an_exact_boolean_truth_table(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE t (a VARCHAR(8), b VARCHAR(8), CHECK ((a IS NULL) = (b IS NULL)))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "a IS NULL AND b IS NULL" in report["emitted"]
    assert "a IS NOT NULL AND b IS NOT NULL" in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_predicate_and_null_test_equality_preserves_check_three_valued_logic(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE t (session_state VARCHAR(16), quarantine_id VARCHAR(128), "
        "CHECK ((session_state = 'QUARANTINED') = (quarantine_id IS NOT NULL)))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "session_state = 'QUARANTINED' AND quarantine_id IS NOT NULL" in report["emitted"]
    assert "NOT (session_state = 'QUARANTINED')" in report["emitted"]
    assert "NOT (quarantine_id IS NOT NULL)" in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_postgres_nonfinite_double_check_literals_remain_fail_closed(target: str) -> None:
    report = translate_ddl(
        "ALTER TABLE audit_events ADD CONSTRAINT c CHECK "
        "(metric_value IS NULL OR metric_value NOT IN ('Infinity'::float8, '-Infinity'::float8))",
        "postgres",
        target,
        statement_kind="ALTER",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_SPECIAL_FLOAT_UNSUPPORTED_BY_TARGET"


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_same_typed_numeric_column_addition_is_preserved_in_checks(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE t (a DECIMAL(30,0), b DECIMAL(30,0), limit_value DECIMAL(30,0), "
        "CHECK (a + b <= limit_value))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "(a + b) <= limit_value" in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_mixed_boolean_levels_are_emitted_with_their_source_parentheses(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE t (a INT, b INT, c INT, CHECK ((a > 0 AND b > 0) OR c = 3))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "CHECK ((a > 0 AND b > 0) OR c = 3)" in report["emitted"]


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
        # MySQL's default collation is case-insensitive, so the same predicate
        # accepts different rows on different targets.
        ("like", "CREATE TABLE t (s VARCHAR(8), CHECK (s LIKE 'a%'))"),
        # Parses as `Is` too, but Oracle has no boolean type and no IS TRUE.
        ("is-true", "CREATE TABLE t (b BOOLEAN, CHECK (b IS TRUE))"),
        # PostgreSQL-only.
        ("between-symmetric", "CREATE TABLE t (a INT, CHECK (a BETWEEN SYMMETRIC 9 AND 1))"),
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


@pytest.mark.parametrize(
    ("pattern", "fragment"),
    [
        ("^[0-9a-f]{64}$", "DATALENGTH(CONVERT(nvarchar(max), s)) = 128"),
        ("^[0-9a-f]{40}$", "DATALENGTH(CONVERT(nvarchar(max), s)) = 80"),
        ("^sha256:[0-9a-f]{64}$", "LEFT(CONVERT(nvarchar(max), s) COLLATE Latin1_General_100_BIN2, 7) = N'sha256:'"),
        ("^[0-9]+$", "DATALENGTH(CONVERT(nvarchar(max), s)) >= 2"),
    ],
)
def test_bounded_ascii_regexes_have_a_binary_collation_sql_server_lowering(
    pattern: str, fragment: str
) -> None:
    report = translate_ddl(
        f"CREATE TABLE t (s TEXT, CHECK (s ~ '{pattern}'))",
        "postgres",
        "tsql",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report
    assert fragment in report["emitted"]
    assert "COLLATE Latin1_General_100_BIN2" in report["emitted"]


def test_regex_is_refused_when_sql_server_has_no_proven_equivalent() -> None:
    report = translate_ddl(
        "CREATE TABLE t (s VARCHAR(8), CHECK (s ~ '^[a-f]+$'))",
        "postgres",
        "tsql",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_REGEX_CHECK_UNREACHABLE_ON_TARGET"


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
@pytest.mark.parametrize("pattern", ["/%", "%*%"])
def test_non_collation_bearing_like_patterns_are_portable(target: str, pattern: str) -> None:
    report = translate_ddl(
        f"CREATE TABLE t (s TEXT, CHECK (s LIKE '{pattern}'))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert f"s LIKE '{pattern}'" in report["emitted"]


def test_like_with_letters_remains_fail_closed_for_collation_drift() -> None:
    report = translate_ddl(
        "CREATE TABLE t (s TEXT, CHECK (s LIKE 'a%'))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN"


def test_nested_not_preserves_a_doubly_negated_null_test() -> None:
    report = translate_ddl(
        "CREATE TABLE t (a INT, CHECK (NOT (a IS NOT NULL)))",
        "mysql",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "NOT (a IS NOT NULL)" in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_timestamp_interval_checks_use_target_native_typed_arithmetic(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE t (issued_at TIMESTAMP, expires_at TIMESTAMP, "
        "CHECK (expires_at <= issued_at + interval '15 minutes'))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    expected = {
        "mysql": "DATE_ADD(issued_at, INTERVAL 15 MINUTE)",
        "oracle": "issued_at + INTERVAL '15' MINUTE",
        "tsql": "DATEADD(MINUTE, 15, issued_at)",
    }[target]
    assert expected in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_column_to_column_and_boolean_checks_render_without_literal_coercion(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE t (enabled BOOLEAN, created_at TIMESTAMP, updated_at TIMESTAMP, "
        "CHECK (enabled AND updated_at >= created_at AND enabled = true))",
        "postgres",
        target,
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "updated_at >= created_at" in report["emitted"]
    assert ("enabled = 1" if target in {"oracle", "tsql"} else "enabled = TRUE") in report["emitted"]


def test_boolean_checks_are_type_checked_in_the_canonical_model() -> None:
    report = translate_ddl(
        "CREATE TABLE t (count INT, CHECK (count = true))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNSUPPORTED_CHECK"


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
