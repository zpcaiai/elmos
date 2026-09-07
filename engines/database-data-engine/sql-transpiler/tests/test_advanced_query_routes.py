from __future__ import annotations

import pytest

from elmos_sql_transpiler.models import ParameterContract, TranspileRequest
from elmos_sql_transpiler.profiles import route_matrix
from elmos_sql_transpiler.transpiler import transpile

_ROUTES = route_matrix()


@pytest.mark.parametrize("route", _ROUTES, ids=lambda r: r.id)
def test_all_42_routes_transpile_window_functions_and_coalesce(route) -> None:
    sql = (
        "SELECT id, tenant_id, COALESCE(status, 'UNKNOWN') AS status, "
        "DENSE_RANK() OVER (PARTITION BY tenant_id ORDER BY amount_cents DESC) AS rnk, "
        "LAG(amount_cents, 1) OVER (PARTITION BY tenant_id ORDER BY id) AS prev_amount "
        "FROM orders WHERE amount_cents > 0"
    )
    result = transpile(
        TranspileRequest(
            query_id=f"window-{route.id}",
            source_profile=route.source_profile,
            target_profile=route.target_profile,
            sql=sql,
        )
    )

    assert result.state == "SYNTAX_READY", f"Route {route.id} failed: {result.rejection_reason}"
    assert result.syntax_parse == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.target_sql is not None
    assert result.metadata["silentFallbackUsed"] is False


@pytest.mark.parametrize("route", _ROUTES, ids=lambda r: r.id)
def test_all_42_routes_transpile_cte_and_case_expressions(route) -> None:
    sql = (
        "WITH tenant_summary AS ("
        "  SELECT tenant_id, COUNT(*) AS cnt, SUM(amount_cents) AS total "
        "  FROM orders GROUP BY tenant_id"
        ") "
        "SELECT tenant_id, cnt, total, "
        "CASE WHEN total > 100000 THEN 'TIER_1' "
        "WHEN total > 50000 THEN 'TIER_2' ELSE 'TIER_3' END AS tier "
        "FROM tenant_summary WHERE cnt >= 1 ORDER BY total DESC"
    )
    result = transpile(
        TranspileRequest(
            query_id=f"cte-{route.id}",
            source_profile=route.source_profile,
            target_profile=route.target_profile,
            sql=sql,
        )
    )

    assert result.state == "SYNTAX_READY", f"Route {route.id} failed: {result.rejection_reason}"
    assert result.syntax_parse == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.target_sql is not None
    assert result.metadata["silentFallbackUsed"] is False


@pytest.mark.parametrize("route", _ROUTES, ids=lambda r: r.id)
def test_all_42_routes_transpile_typed_parameters(route) -> None:
    sql = (
        "SELECT id, tenant_id, amount_cents FROM orders "
        "WHERE tenant_id = :tenant_id AND amount_cents >= :min_cents "
        "ORDER BY id LIMIT 50"
    )
    params = (
        ParameterContract(name="tenant_id", logical_type="unicode-text", nullable=False),
        ParameterContract(name="min_cents", logical_type="integer", nullable=False),
    )
    result = transpile(
        TranspileRequest(
            query_id=f"param-{route.id}",
            source_profile=route.source_profile,
            target_profile=route.target_profile,
            sql=sql,
            parameters=params,
        )
    )

    assert result.state == "SYNTAX_READY", f"Route {route.id} failed: {result.rejection_reason}"
    assert result.syntax_parse == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.parameter_contract == "PASSED"
    assert result.target_sql is not None

    target = route.target_profile
    if "oracle" in target:
        assert ":tenant_id" in result.target_sql or ":p1" in result.target_sql
    elif "sqlserver" in target:
        assert "@" in result.target_sql
    elif "mysql" in target or "sqlite" in target:
        assert "?" in result.target_sql
    elif "postgresql" in target or "duckdb" in target:
        assert "$" in result.target_sql


@pytest.mark.parametrize("route", _ROUTES, ids=lambda r: r.id)
def test_all_42_routes_transpile_subqueries_and_exists(route) -> None:
    sql = (
        "SELECT o1.id, o1.tenant_id, o1.amount_cents FROM orders o1 "
        "WHERE EXISTS ("
        "  SELECT 1 FROM orders o2 WHERE o2.tenant_id = o1.tenant_id AND o2.amount_cents > 50000"
        ") AND o1.id IN (SELECT id FROM orders WHERE status = 'PAID')"
    )
    result = transpile(
        TranspileRequest(
            query_id=f"subquery-{route.id}",
            source_profile=route.source_profile,
            target_profile=route.target_profile,
            sql=sql,
        )
    )

    assert result.state == "SYNTAX_READY", f"Route {route.id} failed: {result.rejection_reason}"
    assert result.syntax_parse == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.target_sql is not None


@pytest.mark.parametrize("route", _ROUTES, ids=lambda r: r.id)
def test_all_42_routes_transpile_set_operations(route) -> None:
    sql = (
        "SELECT tenant_id FROM orders WHERE amount_cents > 10000 "
        "INTERSECT "
        "SELECT tenant_id FROM orders WHERE status = 'PAID'"
    )
    result = transpile(
        TranspileRequest(
            query_id=f"setop-{route.id}",
            source_profile=route.source_profile,
            target_profile=route.target_profile,
            sql=sql,
        )
    )

    assert result.state == "SYNTAX_READY", f"Route {route.id} failed: {result.rejection_reason}"
    assert result.syntax_parse == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.target_sql is not None

