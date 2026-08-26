"""Typed coverage for the bounded cross-dialect DML routes."""

from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError
from elmos_sql_dialect.parser import parse_insert_select, parse_update


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_single_table_update_has_a_typed_route(target: str) -> None:
    report = translate_ddl(
        "UPDATE cache_entries "
        "SET invalidated_at = COALESCE(invalidated_at, CURRENT_TIMESTAMP), "
        "invalidation_reason = COALESCE(invalidation_reason, 'SCHEMA_UPGRADE') "
        "WHERE invalidated_at IS NULL",
        "postgres",
        target,
        statement_kind="UPDATE",
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] is not None
    assert "COALESCE" in report["emitted"]
    assert "WHERE invalidated_at IS NULL" in report["emitted"]


def test_update_from_remains_fail_closed() -> None:
    report = translate_ddl(
        "UPDATE target SET size_bytes = source.size_bytes "
        "FROM source WHERE target.digest_hex = source.digest_hex",
        "postgres",
        "mysql",
        statement_kind="UPDATE",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_UPDATE_UNSUPPORTED_SOURCE"


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_single_source_insert_select_has_a_typed_route(target: str) -> None:
    report = translate_ddl(
        "INSERT INTO resource_bindings (organization_id, resource_kind, resource_id) "
        "SELECT organization_id, 'PROJECT', project_id FROM object_catalog",
        "postgres",
        target,
        statement_kind="INSERT",
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == (
        "INSERT INTO resource_bindings (organization_id, resource_kind, resource_id) "
        "SELECT organization_id, 'PROJECT', project_id FROM object_catalog"
    )


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_grouped_insert_select_preserves_min_aggregate(target: str) -> None:
    report = translate_ddl(
        "INSERT INTO tenant_work (organization_id, work_pending, next_attempt_at) "
        "SELECT organization_id, TRUE, MIN(recorded_at) "
        "FROM root_reconciliations GROUP BY organization_id",
        "postgres",
        target,
        statement_kind="INSERT",
    )
    assert report["status"] == "PASSED", report
    assert "MIN(recorded_at)" in report["emitted"]
    assert "GROUP BY organization_id" in report["emitted"]


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_inner_join_insert_select_preserves_qualified_sources(target: str) -> None:
    report = translate_ddl(
        "INSERT INTO webhook_routes (repository_id, installation_id, active) "
        "SELECT repository.repository_id, installation.installation_id, "
        "repository.authorization_status = 'AUTHORIZED' AND NOT repository.archived "
        "FROM repositories repository "
        "JOIN installations installation "
        "ON installation.organization_id = repository.organization_id "
        "AND installation.installation_id = repository.installation_id",
        "postgres",
        target,
        statement_kind="INSERT",
    )
    assert report["status"] == "PASSED", report
    assert "INNER JOIN installations installation" in report["emitted"]
    assert "repository.repository_id" in report["emitted"]
    assert "installation.installation_id" in report["emitted"]


def test_joined_insert_select_rejects_outer_join() -> None:
    report = translate_ddl(
        "INSERT INTO target (id) "
        "SELECT left_table.id FROM left_table "
        "LEFT JOIN right_table ON right_table.id = left_table.id",
        "postgres",
        "mysql",
        statement_kind="INSERT",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY"


def test_insert_select_parser_retains_source_names_as_typed_fields() -> None:
    model = parse_insert_select(
        "INSERT INTO target (org, state) SELECT org, 'ACTIVE' FROM source WHERE org IS NOT NULL",
        Dialect.POSTGRES,
    )
    assert model.table == "target"
    assert model.source_table == "source"
    assert model.columns == ("org", "state")
    assert model.predicate is not None


def test_update_parser_rejects_vendor_wall_clock_function() -> None:
    with pytest.raises(DialectError) as exc:
        parse_update(
            "UPDATE cache_entries SET updated_at = clock_timestamp()",
            Dialect.POSTGRES,
        )
    assert "CERTIFIED_DML_UNSUPPORTED_EXPRESSION" in str(exc.value)
