"""Regression tests for the defects an earlier revision shipped as PASSED.

All four were reproduced against sqlglot before being fixed; none of them is a
syntax error, so neither the emit leg nor the target re-parse leg could see
any of them.
"""
from __future__ import annotations

import re

import pytest
import sqlglot

from elmos_sql_transpiler.models import TranspileRequest
from elmos_sql_transpiler.transpiler import transpile

PG = "postgresql-17.5"
PG18 = "postgresql-18.4"
MY = "mysql-8.4.10-lts"
MS = "sqlserver-2022-cu26"
ORA = "oracle-26ai-ee"
LITE = "sqlite-3.53.3"
DUCK = "duckdb-1.5.4"

_PLACEHOLDER_SQL = {
    PG: "SELECT id FROM t WHERE a = $1 AND b = $2 ORDER BY id",
    PG18: "SELECT id FROM t WHERE a = $1 AND b = $2 ORDER BY id",
    MY: "SELECT id FROM t WHERE a = ? AND b = ? ORDER BY id",
    MS: "SELECT id FROM t WHERE a = @p1 AND b = @p2 ORDER BY id",
    ORA: "SELECT id FROM t WHERE a = :one AND b = :two ORDER BY id",
    LITE: "SELECT id FROM t WHERE a = ? AND b = ? ORDER BY id",
    DUCK: "SELECT id FROM t WHERE a = $1 AND b = $2 ORDER BY id",
}

#: What a bind parameter actually looks like in each target engine.
_VALID_TOKEN = {
    "postgres": re.compile(r"^\$\d+$"),
    "mysql": re.compile(r"^\?$"),
    "tsql": re.compile(r"^@[A-Za-z_][A-Za-z0-9_]*$"),
    "oracle": re.compile(r"^:[A-Za-z_][A-Za-z0-9_]*$"),
    "sqlite": re.compile(r"^\?$"),
    "duckdb": re.compile(r"^\$\d+$"),
}

_DIALECT_OF = {
    PG: "postgres",
    PG18: "postgres",
    MY: "mysql",
    MS: "tsql",
    ORA: "oracle",
    LITE: "sqlite",
    DUCK: "duckdb",
}


def _emit(sql: str, source: str, target: str) -> str:
    result = transpile(
        TranspileRequest(query_id="t", sql=sql, source_profile=source, target_profile=target)
    )
    assert result.state == "SYNTAX_READY", [d.code for d in result.diagnostics]
    assert result.target_sql is not None
    return result.target_sql


# --------------------------------------------------------------------------
# 1. Bind parameters must survive as bind parameters.
#
#    Before the fix, sqlglot's generator rendered each parameter node with
#    whatever syntax the target generator uses for that node *type*, which is
#    not a placeholder in the target engine:
#      postgres $1 -> mysql @1 (a session variable), oracle @1, tsql @1
#      tsql @p1    -> postgres $p1 (invalid)
#      oracle :one -> postgres %(one)s (psycopg client syntax, not SQL)
#      mysql ?     -> postgres %s
#    Every one of those was reported SYNTAX_READY with parameterContract
#    PASSED, and would have silently bound nothing at runtime.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", list(_PLACEHOLDER_SQL))
@pytest.mark.parametrize("target", list(_PLACEHOLDER_SQL))
def test_every_route_emits_real_target_placeholders(source: str, target: str) -> None:
    if _DIALECT_OF[source] == _DIALECT_OF[target]:
        pytest.skip("same dialect")
    emitted = _emit(_PLACEHOLDER_SQL[source], source, target)
    target_dialect = _DIALECT_OF[target]
    parsed = sqlglot.parse_one(emitted.rstrip(";\n"), read=target_dialect)
    tokens = [
        node.sql(dialect=target_dialect)
        for node in parsed.walk()
        if node.key in ("placeholder", "parameter")
    ]
    assert len(tokens) == 2, emitted
    for token in tokens:
        assert _VALID_TOKEN[target_dialect].match(token), f"{token!r} in {emitted!r}"


def test_numbered_targets_keep_one_number_per_source_parameter() -> None:
    emitted = _emit("SELECT id FROM t WHERE a = :x AND b = :y AND c = :x ORDER BY id", ORA, PG)
    assert "$1" in emitted and "$2" in emitted
    assert "$3" not in emitted  # :x is one parameter, bound once


def test_named_targets_keep_the_source_name() -> None:
    sql = _PLACEHOLDER_SQL[MS].replace("@p1", "@one").replace("@p2", "@two")
    assert ":one" in _emit(sql, MS, ORA)


def test_repeated_parameter_into_an_anonymous_target_fails_closed() -> None:
    # `?` is positional and anonymous: one placeholder is one bound value, so a
    # source parameter used twice cannot keep its binding arity.
    result = transpile(
        TranspileRequest(
            query_id="repeat",
            sql="SELECT id FROM t WHERE a = $1 OR b = $1 ORDER BY id",
            source_profile=PG,
            target_profile=MY,
        )
    )
    assert result.state == "BLOCKED"
    assert result.diagnostics[0].code == "UNSUPPORTED_SEMANTICS"


def test_repeated_parameter_into_a_numbered_target_is_fine() -> None:
    emitted = _emit("SELECT id FROM t WHERE a = ? OR b = ? ORDER BY id", MY, PG)
    assert "$1" in emitted and "$2" in emitted


def test_parameterless_sql_is_untouched() -> None:
    assert "?" not in _emit("SELECT id FROM t ORDER BY id", PG, MY)


# --------------------------------------------------------------------------
# 2. Positional GROUP BY / ORDER BY against a wildcard projection.
#    Before the fix this emitted `ORDER BY *` / `GROUP BY *`, which sqlglot
#    re-parses happily and every real server rejects.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders ORDER BY 1",
        "SELECT * FROM orders GROUP BY 1",
        "SELECT t.*, 1 AS one FROM t ORDER BY 1",
        "SELECT *, 1 AS one FROM t ORDER BY 2",
    ],
)
def test_positional_reference_against_a_wildcard_fails_closed(sql: str) -> None:
    result = transpile(
        TranspileRequest(query_id="star", sql=sql, source_profile=PG, target_profile=MY)
    )
    assert result.state == "BLOCKED", result.target_sql
    assert result.diagnostics[0].code == "UNSUPPORTED_SEMANTICS"


def test_positional_reference_without_a_wildcard_still_normalizes() -> None:
    emitted = _emit("SELECT id, name FROM t GROUP BY 1 ORDER BY 2", PG, MY)
    assert "GROUP BY" in emitted
    assert "GROUP BY\n  1" not in emitted


# --------------------------------------------------------------------------
# 3. Value-level divergences that are legal SQL on both sides.
# --------------------------------------------------------------------------


def _codes(sql: str, source: str, target: str) -> set[str]:
    result = transpile(
        TranspileRequest(query_id="w", sql=sql, source_profile=source, target_profile=target)
    )
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_integer_division_difference_is_reported() -> None:
    # postgres 7 / 2 = 3; mysql 7 / 2 = 3.5000.
    assert "INTEGER_DIVISION_SEMANTICS_DIFFER" in _codes(
        "SELECT total / count AS v FROM t ORDER BY v", PG, MY
    )
    assert "INTEGER_DIVISION_SEMANTICS_DIFFER" in _codes(
        "SELECT total / count AS v FROM t ORDER BY v", MS, ORA
    )


def test_integer_division_is_not_reported_when_both_sides_agree() -> None:
    assert "INTEGER_DIVISION_SEMANTICS_DIFFER" not in _codes(
        "SELECT total / count AS v FROM t ORDER BY v", PG, MS
    )
    assert "INTEGER_DIVISION_SEMANTICS_DIFFER" not in _codes(
        "SELECT total FROM t ORDER BY total", PG, MY
    )


def test_identifier_case_folding_difference_is_reported() -> None:
    # postgres folds `Foo` to `foo`; MySQL keeps `Foo` and is case-sensitive
    # for table names on Linux.
    assert "IDENTIFIER_CASE_FOLDING_DIFFERS" in _codes(
        "SELECT Foo FROM Bar ORDER BY Foo", PG, MY
    )


def test_identifier_case_folding_is_not_reported_for_already_folded_sql() -> None:
    assert "IDENTIFIER_CASE_FOLDING_DIFFERS" not in _codes(
        "SELECT foo FROM bar ORDER BY foo", PG, MY
    )
    assert "IDENTIFIER_CASE_FOLDING_DIFFERS" not in _codes(
        'SELECT "Foo" FROM "Bar" ORDER BY "Foo"', PG, MY
    )


def test_division_obligation_is_recorded_on_the_statement() -> None:
    result = transpile(
        TranspileRequest(
            query_id="div",
            sql="SELECT a / b AS v FROM t ORDER BY v",
            source_profile=PG,
            target_profile=MY,
        )
    )
    assert "INTEGER_DIVISION_SEMANTICS" in result.statements[0].obligations


# --------------------------------------------------------------------------
# 4. The parser build is pinned by the profile catalog, like every other
#    exact dependency in this repository.
# --------------------------------------------------------------------------


def test_translation_refuses_an_unpinned_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("elmos_sql_transpiler.transpiler._SQLGLOT_VERSION", "0.0.0")
    with pytest.raises(RuntimeError, match="EXACT_PARSER_MISMATCH"):
        transpile(
            TranspileRequest(query_id="p", sql="SELECT 1", source_profile=PG, target_profile=MY)
        )
