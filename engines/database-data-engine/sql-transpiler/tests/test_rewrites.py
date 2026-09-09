from __future__ import annotations

import sqlite3

import pytest
import sqlglot
from sqlglot import exp

from elmos_sql_transpiler.models import TranspileRequest
from elmos_sql_transpiler.rewrites import (
    AGGREGATE_ORDER_RULE,
    SQLITE_LOWERING_RULE,
    canonicalize_aggregate_order,
    lower_sqlite_group_concat_order,
)
from elmos_sql_transpiler.transpiler import transpile

# SQLite gained ORDER BY inside aggregates (GROUP_CONCAT et al.) in 3.44.0.
# The checked-in profile pins 3.53.3; the guard keeps the test honest on a
# host that runs an older library rather than asserting against a lie.
_SQLITE_AGGREGATE_ORDER_MIN = (3, 44, 0)


def _sqlite_version() -> tuple[int, int, int]:
    parts = sqlite3.sqlite_version.split(".")[:3]
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _transpile(source: str, target: str, sql: str):
    return transpile(
        TranspileRequest(
            query_id="rewrites-test", source_profile=source, target_profile=target, sql=sql
        )
    )


class TestGroupConcatAggregateOrder:
    def test_mysql_shape_is_canonical_and_emits_to_sqlite_with_order(self) -> None:
        result = _transpile(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT GROUP_CONCAT(name ORDER BY name SEPARATOR ',') FROM customers",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        assert "GROUP_CONCAT(name, ',' ORDER BY name)" in " ".join(result.target_sql.split())
        assert "SQLITE_AGGREGATE_ORDER_LOWERED" in result.statements[0].obligations
        assert SQLITE_LOWERING_RULE in {
            trace["ruleId"] for trace in result.metadata["ruleTrace"]
        }

    def test_multi_term_descending_order_and_custom_separator_survive(self) -> None:
        result = _transpile(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT GROUP_CONCAT(name ORDER BY tenant DESC, name SEPARATOR ';') "
            "AS names FROM customers",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        flattened = " ".join(result.target_sql.split())
        assert "ORDER BY tenant DESC, name" in flattened
        assert "';'" in flattened

    def test_default_separator_is_synthesized_not_dangling(self) -> None:
        result = _transpile(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT GROUP_CONCAT(name ORDER BY name) FROM customers",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        flattened = " ".join(result.target_sql.split())
        assert "GROUP_CONCAT(name, ',' ORDER BY name)" in flattened

    def test_sqlite_source_canonicalizes_before_other_targets(self) -> None:
        # Pre-fix behavior: the sqlite-family shape rendered to MySQL as
        # `GROUP_CONCAT(name SEPARATOR ',' ORDER BY name)` -- ORDER BY after
        # SEPARATOR, which real MySQL rejects.
        result = _transpile(
            "sqlite-3.53.3",
            "mysql-8.4.10-lts",
            "SELECT GROUP_CONCAT(name, ',' ORDER BY name) FROM customers",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        flattened = " ".join(result.target_sql.split())
        assert "ORDER BY name SEPARATOR ','" in flattened
        assert "AGGREGATE_ORDER_CANONICALIZED" in result.statements[0].obligations
        assert AGGREGATE_ORDER_RULE in {
            trace["ruleId"] for trace in result.metadata["ruleTrace"]
        }

    def test_sqlite_source_to_sqlserver_uses_within_group(self) -> None:
        result = _transpile(
            "sqlite-3.53.3",
            "sqlserver-2022-cu26",
            "SELECT GROUP_CONCAT(name, ',' ORDER BY name) FROM customers",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        flattened = " ".join(result.target_sql.split())
        assert "WITHIN GROUP (ORDER BY name)" in flattened

    def test_distinct_aggregate_order_to_sqlite_fails_closed(self) -> None:
        # SQLite DISTINCT aggregates accept exactly one argument, so the
        # lowering cannot preserve separator and DISTINCT together.
        result = _transpile(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT GROUP_CONCAT(DISTINCT name ORDER BY name) FROM customers",
        )

        assert result.state == "BLOCKED"
        assert result.target_sql is None
        assert result.diagnostics[0].code == "SQLITE_DISTINCT_AGGREGATE_SEPARATOR_UNSUPPORTED"

    def test_canonicalize_rewrites_sqlite_family_shape_in_place(self) -> None:
        statement = sqlglot.parse_one(
            "SELECT GROUP_CONCAT(name, '|' ORDER BY name DESC) FROM customers", read="sqlite"
        )

        rewritten, fired = canonicalize_aggregate_order(statement)

        assert fired == (AGGREGATE_ORDER_RULE,)
        node = rewritten.find(exp.GroupConcat)
        assert node is not None
        assert isinstance(node.args["this"], exp.Order)
        assert isinstance(node.args["separator"], exp.Literal)
        assert rewritten.sql(dialect="mysql") == (
            "SELECT GROUP_CONCAT(name ORDER BY name DESC SEPARATOR '|') FROM customers"
        )

    def test_lowering_is_inert_for_other_target_dialects(self) -> None:
        statement = sqlglot.parse_one(
            "SELECT GROUP_CONCAT(name ORDER BY name SEPARATOR ',') FROM customers", read="mysql"
        )

        rewritten, fired = lower_sqlite_group_concat_order(statement, "mysql")

        assert fired == ()
        assert rewritten is statement

    def test_runtime_equivalence_stays_not_run_after_rewrite(self) -> None:
        result = _transpile(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT GROUP_CONCAT(name ORDER BY name SEPARATOR ',') FROM customers",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_execution == "NOT_RUN"
        assert result.result_equivalence == "NOT_RUN"
        assert result.certification == "NOT_CERTIFIED"


class TestRealSqliteExecution:
    """Execute the emitted target SQL on the host's real SQLite library.

    This is local execution evidence for the *target side only*; it is not
    source/target result equivalence (the MySQL side has no local runner) and
    not certification.
    """

    def _emit(self, mysql_sql: str) -> str:
        result = _transpile("mysql-8.4.10-lts", "sqlite-3.53.3", mysql_sql)
        assert result.state == "SYNTAX_READY", result.diagnostics
        assert result.target_sql is not None
        return result.target_sql

    def _connection(self) -> sqlite3.Connection:
        if _sqlite_version() < _SQLITE_AGGREGATE_ORDER_MIN:
            pytest.skip(
                f"host sqlite {sqlite3.sqlite_version} predates 3.44 aggregate ORDER BY"
            )
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE customers (tenant TEXT, name TEXT)")
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?)",
            [("t2", "delta"), ("t1", "charlie"), ("t2", "alpha"), ("t1", "bravo")],
        )
        return connection

    def test_ordered_concatenation_matches_mysql_documented_semantics(self) -> None:
        connection = self._connection()
        try:
            target_sql = self._emit(
                "SELECT GROUP_CONCAT(name ORDER BY name SEPARATOR ',') FROM customers"
            )
            rows = connection.execute(target_sql).fetchall()
            assert rows == [("alpha,bravo,charlie,delta",)]
        finally:
            connection.close()

    def test_descending_order_and_custom_separator_execute(self) -> None:
        connection = self._connection()
        try:
            target_sql = self._emit(
                "SELECT GROUP_CONCAT(name ORDER BY name DESC SEPARATOR ';') FROM customers"
            )
            rows = connection.execute(target_sql).fetchall()
            assert rows == [("delta;charlie;bravo;alpha",)]
        finally:
            connection.close()

    def test_multi_term_ordering_executes(self) -> None:
        connection = self._connection()
        try:
            target_sql = self._emit(
                "SELECT GROUP_CONCAT(name ORDER BY tenant, name DESC SEPARATOR '|') "
                "FROM customers"
            )
            rows = connection.execute(target_sql).fetchall()
            assert rows == [("charlie|bravo|delta|alpha",)]
        finally:
            connection.close()


class TestOracleTruncDateFormats:
    def test_month_format_normalizes_and_mysql_emits_month_start(self) -> None:
        result = _transpile(
            "oracle-26ai-ee",
            "mysql-8.4.10-lts",
            "SELECT TRUNC(created_at, 'MM') FROM orders",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        flattened = " ".join(result.target_sql.split())
        # Month start, not the day truncation the raw emitter used to emit.
        assert "STR_TO_DATE(CONCAT(YEAR(created_at), ' ', MONTH(created_at), ' 1')" in flattened
        assert "ORACLE_TRUNC_FORMAT_NORMALIZED" in result.statements[0].obligations

    @pytest.mark.parametrize("fmt", ["YYYY", "SYYYY", "YEAR"])
    def test_year_formats_normalize(self, fmt: str) -> None:
        result = _transpile(
            "oracle-26ai-ee",
            "postgresql-17.5",
            f"SELECT TRUNC(created_at, '{fmt}') FROM orders",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        assert "DATE_TRUNC('year'" in " ".join(result.target_sql.split())

    @pytest.mark.parametrize("fmt", ["DD", "DDD", "J"])
    def test_day_formats_normalize(self, fmt: str) -> None:
        result = _transpile(
            "oracle-26ai-ee",
            "mysql-8.4.10-lts",
            f"SELECT TRUNC(created_at, '{fmt}') FROM orders",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        assert "DATE(created_at)" in " ".join(result.target_sql.split())

    @pytest.mark.parametrize("fmt", ["MON", "MONTH", "Mm"])
    def test_month_format_spellings_normalize(self, fmt: str) -> None:
        result = _transpile(
            "oracle-26ai-ee",
            "duckdb-1.5.4",
            f"SELECT TRUNC(created_at, '{fmt}') FROM orders",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        assert "DATE_TRUNC('month'" in " ".join(result.target_sql.split())

    @pytest.mark.parametrize("fmt", ["Q", "IW", "WW", "DAY", "HH24", "MI", "CC", "IYYY", "RR"])
    def test_unportable_formats_fail_closed(self, fmt: str) -> None:
        result = _transpile(
            "oracle-26ai-ee",
            "postgresql-17.5",
            f"SELECT TRUNC(created_at, '{fmt}') FROM orders",
        )

        assert result.state == "BLOCKED"
        assert result.target_sql is None
        assert result.diagnostics[0].code == "ORACLE_TRUNC_FORMAT_UNSUPPORTED"

    def test_single_argument_trunc_is_ambiguous_and_blocked(self) -> None:
        # Without a format the pinned oracle reader leaves TRUNC(x) as an
        # opaque node: numeric-vs-date is unknowable without a catalog, and
        # no other engine in this set provides TRUNC(...) natively.
        result = _transpile(
            "oracle-26ai-ee",
            "mysql-8.4.10-lts",
            "SELECT TRUNC(created_at) FROM orders",
        )

        assert result.state == "BLOCKED"
        assert result.target_sql is None
        assert result.diagnostics[0].code == "ORACLE_TRUNC_AMBIGUOUS_WITHOUT_FORMAT"

    def test_numeric_trunc_is_typed_and_untouched(self) -> None:
        result = _transpile(
            "oracle-26ai-ee",
            "mysql-8.4.10-lts",
            "SELECT TRUNC(15.79, 1) FROM dual",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        assert "TRUNCATE(15.79, 1)" in " ".join(result.target_sql.split())
        assert "ORACLE_TRUNC_FORMAT_NORMALIZED" not in result.statements[0].obligations

    def test_non_oracle_date_trunc_is_not_gated(self) -> None:
        # postgres-source DATE_TRUNC passes through untouched, including
        # units the Oracle allow-list does not carry.
        result = _transpile(
            "postgresql-17.5",
            "duckdb-1.5.4",
            "SELECT DATE_TRUNC('quarter', created_at) FROM orders",
        )

        assert result.state == "SYNTAX_READY"
        assert result.target_sql is not None
        assert "date_trunc('quarter'" in " ".join(result.target_sql.split()).lower()


class TestOptimizerHints:
    def test_plan_hint_is_stripped_with_obligation(self) -> None:
        result = _transpile(
            "mysql-8.4.10-lts",
            "postgresql-17.5",
            "SELECT /*+ INDEX(orders idx_tenant) */ id FROM orders ORDER BY id",
        )

        assert result.state == "SYNTAX_READY", result.diagnostics
        assert result.target_sql is not None
        assert "INDEX(orders" not in result.target_sql
        assert "OPTIMIZER_HINT_STRIPPED" in result.statements[0].obligations
        assert any(item.code == "OPTIMIZER_HINT_STRIPPED" for item in result.diagnostics)

    def test_use_index_is_stripped(self) -> None:
        result = _transpile(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT id FROM orders USE INDEX (idx_tenant) ORDER BY id",
        )

        assert result.state == "SYNTAX_READY", result.diagnostics
        assert result.target_sql is not None
        assert "USE INDEX" not in result.target_sql.upper()
        assert "OPTIMIZER_HINT_STRIPPED" in result.statements[0].obligations

    def test_nolock_stays_fail_closed(self) -> None:
        result = _transpile(
            "sqlserver-2022-cu26",
            "postgresql-17.5",
            "SELECT id FROM orders WITH (NOLOCK)",
        )

        assert result.state == "BLOCKED"
        assert result.target_sql is None
        assert "LOCKING_HINT_NOT_PORTABLE" in {item.code for item in result.diagnostics}
