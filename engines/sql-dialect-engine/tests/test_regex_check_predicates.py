"""Regex CHECK constraints: admitted by PATTERN, not by operator.

Regex used to be refused wholesale, alongside LIKE, because the three engines
that have it diverge. That refusal was measured against the corpus and cost
418 occurrences across 8 distinct patterns -- every one of them inside the
portable core, and 400 of them the same hash-shape guard. So the narrowing
moved from the operator to the pattern, and two guarantees were added that the
wholesale refusal never had to make explicit:

  1. a pattern using a construct the three engines disagree about is refused;
  2. case sensitivity is PINNED at emission, because MySQL's REGEXP follows the
     column collation and would otherwise silently accept more rows.

SQL Server has no regex predicate, so only the emitter's explicitly bounded
ASCII lowerings are reachable; every other pattern fails closed.
"""
from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import (
    CheckComparison,
    CheckOperator,
    Dialect,
    DialectError,
    require_portable_regex,
)

HASH_CHECK = "CREATE TABLE t (h VARCHAR(64), CHECK (h ~ '^[0-9a-f]{64}$'))"


def _check_line(report: dict) -> str:
    return next(
        line.strip().rstrip(",")
        for line in (report["emitted"] or "").splitlines()
        if "CHECK" in line or "REGEXP_LIKE" in line
    )


# --------------------------------------------------------------------------
# the portable core
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pattern",
    [
        "^[0-9a-f]{64}$",                     # 400 of 418 occurrences in the corpus
        "^sha256:[0-9a-f]{64}$",
        "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        "^[0-9]+$",
        "^(alpha|beta)$",                     # alternation and grouping
    ],
)
def test_the_portable_core_is_admitted(pattern: str) -> None:
    require_portable_regex(pattern)


@pytest.mark.parametrize(
    ("pattern", "construct"),
    [
        (r"^\d+$", "Perl class escape"),
        (r"^\w{3}$", "Perl class escape"),
        ("^(?i)abc$", "group extension"),
        ("^(?:ab)+$", "group extension"),
        (r"^(a)\1$", "backreference"),
        ("^[[:alpha:]]+$", "POSIX named class"),
        (r"^\p{L}+$", "Unicode property"),
    ],
)
def test_a_pattern_the_three_engines_disagree_about_is_refused(
    pattern: str, construct: str
) -> None:
    with pytest.raises(DialectError) as caught:
        require_portable_regex(pattern)
    assert caught.value.code == "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN"


def test_the_pattern_gate_runs_on_model_construction_not_only_on_parse() -> None:
    """A caller building the model directly must not bypass the guarantee."""
    with pytest.raises(DialectError) as caught:
        CheckComparison(
            column="h",
            operator=CheckOperator.MATCHES_REGEX,
            literal=r"^\d+$",
            literal_is_string=True,
        )
    assert caught.value.code == "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN"


# --------------------------------------------------------------------------
# emission: three reachable targets, one refused
# --------------------------------------------------------------------------

ORACLE_HASH_CHECK = (
    "CREATE TABLE t (h VARCHAR(64), CHECK (REGEXP_LIKE(h, '^[0-9a-f]{64}$', 'c')))"
)


def test_postgres_emits_the_operator_form() -> None:
    """Source is Oracle: PostgreSQL is the target here, and `~` is its spelling."""
    report = translate_ddl(ORACLE_HASH_CHECK, "oracle", "postgres", statement_kind="TABLE")
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "h ~ '^[0-9a-f]{64}$'" in report["emitted"]


def test_the_emitted_mysql_form_can_be_read_back_as_a_source() -> None:
    """Round trip: what this engine emits, it must also accept."""
    forward = translate_ddl(HASH_CHECK, "postgres", "mysql", statement_kind="TABLE")
    assert forward["status"] == "PASSED", forward["reasonCode"]
    back = translate_ddl(forward["emitted"], "mysql", "postgres", statement_kind="TABLE")
    assert back["status"] == "PASSED", back["reasonCode"]
    assert "h ~ '^[0-9a-f]{64}$'" in back["emitted"]


# --------------------------------------------------------------------------
# case sensitivity has to be established on the SOURCE side too
# --------------------------------------------------------------------------

def test_a_mysql_regexp_without_a_match_parameter_is_refused() -> None:
    """MySQL's REGEXP follows the column collation, which the statement omits.

    Admitting it would mean guessing the source semantics and then pinning
    that guess on the target.
    """
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (h REGEXP '^[0-9a-f]{64}$'))",
        "mysql",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX"
    assert "collation" in report["reason"]


def test_a_mysql_regexp_that_spells_case_sensitivity_is_admitted() -> None:
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (REGEXP_LIKE(h, '^[0-9a-f]{64}$', 'c')))",
        "mysql",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]


@pytest.mark.parametrize("parameter", ["i", "m", "x", "n"])
def test_any_match_parameter_other_than_case_sensitive_is_refused(parameter: str) -> None:
    """`'i'` is the dangerous one: it would become STRICTER on the target,
    rejecting rows the source accepted."""
    report = translate_ddl(
        f"CREATE TABLE t (h VARCHAR(64), CHECK (REGEXP_LIKE(h, '^[0-9a-f]+$', '{parameter}')))",
        "oracle",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER"


def test_an_oracle_regexp_without_a_match_parameter_is_admitted() -> None:
    """Unlike MySQL, Oracle's default is determinable from the statement."""
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (REGEXP_LIKE(h, '^[0-9a-f]{64}$')))",
        "oracle",
        "postgres",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]


@pytest.mark.parametrize("target", ["mysql", "oracle"])
def test_the_function_form_pins_case_sensitivity_explicitly(target: str) -> None:
    """MySQL's REGEXP follows the column collation.

    Under the 8.0 default (utf8mb4_0900_ai_ci) `^[0-9a-f]{64}$` would also
    accept uppercase hex, making the emitted constraint strictly weaker than
    the source's. The `'c'` match parameter is what stops that, so it is
    asserted rather than left to the target's configuration.
    """
    report = translate_ddl(HASH_CHECK, "postgres", target, statement_kind="TABLE")
    assert report["status"] == "PASSED", report["reasonCode"]
    assert "REGEXP_LIKE(h, '^[0-9a-f]{64}$', 'c')" in report["emitted"]


def test_sql_server_fails_closed_for_an_unbounded_pattern() -> None:
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (h ~ '^[a-f]+$'))",
        "postgres",
        "tsql",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_REGEX_CHECK_UNREACHABLE_ON_TARGET"
    assert report["emitted"] is None


def test_the_sql_server_refusal_explains_the_bounded_lowering_boundary() -> None:
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (h ~ '^[a-f]+$'))",
        "postgres",
        "tsql",
        statement_kind="TABLE",
    )
    assert "regex CHECK" in report["reason"]
    assert "bounded ASCII" in report["reason"]


def test_a_non_portable_pattern_is_blocked_before_any_target_is_chosen() -> None:
    report = translate_ddl(
        r"CREATE TABLE t (h VARCHAR(64), CHECK (h ~ '^\d{64}$'))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN"


# --------------------------------------------------------------------------
# composition with the rest of the CHECK grammar
# --------------------------------------------------------------------------

def test_a_regex_inside_a_nullable_guard_survives_the_round_trip() -> None:
    """`h IS NULL OR h ~ '...'` is the corpus's actual shape, not a bare regex."""
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (h IS NULL OR h ~ '^[0-9a-f]{64}$'))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report["reasonCode"]
    line = _check_line(report)
    assert "h IS NULL OR REGEXP_LIKE(h, '^[0-9a-f]{64}$', 'c')" in line


def test_a_pattern_column_rather_than_a_literal_is_refused() -> None:
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), p VARCHAR(64), CHECK (h ~ p))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "BLOCKED"


def test_a_negated_regex_is_preserved_by_the_typed_boolean_tree() -> None:
    report = translate_ddl(
        "CREATE TABLE t (h VARCHAR(64), CHECK (NOT (h ~ '^[0-9a-f]{64}$')))",
        "postgres",
        "mysql",
        statement_kind="TABLE",
    )
    assert report["status"] == "PASSED", report
    assert "NOT (REGEXP_LIKE(h, '^[0-9a-f]{64}$', 'c'))" in _check_line(report)


def test_the_scan_admits_the_corpus_shape() -> None:
    import sqlglot

    from elmos_sql_dialect.scan import _classify

    statement = sqlglot.parse_one(
        "CREATE TABLE t (h VARCHAR(64) CHECK (h IS NULL OR h ~ '^[0-9a-f]{64}$'))",
        read="postgres",
    )
    assert _classify(statement, Dialect.POSTGRES) == ("IN_SUBSET", None, None)
