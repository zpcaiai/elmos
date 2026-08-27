"""Regression tests for the typed route expansion in this change."""

from __future__ import annotations

import json

import pytest

from elmos_sql_dialect.advanced import emit_trigger, parse_trigger
from elmos_sql_dialect.capabilities import target_capability_matrix
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError
from elmos_sql_dialect.parser import _parse_source_statements, parse_create_table
from elmos_sql_dialect.profiles import NamespaceProfile
from elmos_sql_dialect.routine import parse_create_routine
from elmos_sql_dialect.scan import SourceSchemaCatalog, _record_catalog_statement


def test_namespace_profile_is_digest_bound_and_reported() -> None:
    profile = NamespaceProfile.from_mapping({"app": "tenant"}, name="test-profile")
    report = translate_ddl(
        'CREATE TABLE app."Order Items" ("item id" INT)',
        "postgres",
        "mysql",
        namespace_profile=profile,
    )
    assert report["status"] == "PASSED", report
    assert report["namespaceProfile"] == profile.to_dict()
    assert report["emitted"] == "CREATE TABLE tenant.`Order Items` (\n    `item id` INT\n)"

    payload = json.loads(json.dumps(profile.to_dict()))
    payload["mapping"]["app"] = "other"
    with pytest.raises(DialectError) as caught:
        NamespaceProfile.from_payload(payload)
    assert caught.value.code == "INVALID_NAMESPACE_PROFILE_DIGEST"


def test_narrow_plpgsql_block_is_lowered_without_textual_body_copy() -> None:
    sql = (
        "CREATE FUNCTION app.add_one(IN p INT DEFAULT 1) RETURNS INT LANGUAGE plpgsql "
        "AS $$ DECLARE result INT := 0; BEGIN result := p + 1; RETURN result; END $$"
    )
    routine = parse_create_routine(sql, source_dialect=Dialect.POSTGRES, namespace_map={"app": "tenant"})
    assert type(routine.body).__name__ == "RoutineBlockBody"
    report = translate_ddl(sql, "postgres", "tsql", statement_kind="FUNCTION", namespace_map={"app": "tenant"})
    assert report["status"] == "PASSED", report
    assert "SET @result =" in (report["emitted"] or "")
    assert "RETURN @result" in (report["emitted"] or "")


def test_plpgsql_control_flow_and_dynamic_sql_remain_blocked() -> None:
    for body, code in (
        ("BEGIN IF p > 0 THEN RETURN p; END IF; END", "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE"),
        ("BEGIN EXECUTE 'CREATE TABLE t(id INT)'; RETURN p; END", "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE"),
    ):
        report = translate_ddl(
            f"CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE plpgsql AS $$ {body} $$",
            "postgres",
            "mysql",
            statement_kind="FUNCTION",
        )
        assert report["status"] == "BLOCKED", report
        assert report["reasonCode"] == code


def test_static_do_expands_one_ddl_and_refuses_multiple_or_dynamic_units() -> None:
    report = translate_ddl(
        "DO $$ BEGIN CREATE TABLE t (id INT); END $$;",
        "postgres",
        "oracle",
        statement_kind="DO",
    )
    assert report["status"] == "PASSED", report
    assert "CREATE TABLE t" in (report["emitted"] or "")
    blocked = translate_ddl(
        "DO $$ BEGIN EXECUTE 'CREATE TABLE t(id INT)'; END $$;",
        "postgres",
        "oracle",
        statement_kind="DO",
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["reasonCode"] == "CERTIFIED_STATIC_DO_DYNAMIC_OR_CONTROL_FLOW"


def test_capability_matrix_is_explicit_about_non_common_jsonb_and_array_routes() -> None:
    matrix = {row["feature"]: row for row in target_capability_matrix()}
    assert matrix["jsonb_binary"]["exact_targets"] == ("postgres",)
    assert matrix["array_exact"]["exact_targets"] == ("postgres",)
    assert matrix["routine_trigger_action"]["exact_targets"] == ("postgres",)


def test_null_defaults_are_typed_literals_not_dropped() -> None:
    report = translate_ddl(
        "CREATE TABLE nullable_defaults (id INT PRIMARY KEY, note VARCHAR(32) DEFAULT NULL)",
        "postgres",
        "mysql",
    )
    assert report["status"] == "PASSED", report
    assert "DEFAULT NULL" in (report["emitted"] or "")


def test_dynamic_do_catalog_evidence_is_typed_but_not_an_emission_route() -> None:
    catalog = SourceSchemaCatalog()
    catalog.add_table(
        parse_create_table("CREATE TABLE tenant_rows (id INT PRIMARY KEY)", Dialect.POSTGRES, {"": "dbo"})
    )
    statements = _parse_source_statements(
        "DO $$ DECLARE tenant_table record; BEGIN FOR tenant_table IN "
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP "
        "EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS organization_id varchar(96)', "
        "tenant_table.tablename); "
        "END LOOP; END $$",
        Dialect.POSTGRES,
    )
    assert len(statements) == 1
    _record_catalog_statement(catalog, statements[0], Dialect.POSTGRES, {"": "dbo"})
    assert catalog.type_ref_of("dbo", "tenant_rows", "organization_id") is not None
    assert catalog.evidence[-1]["routeStatus"] == "EVIDENCE_ONLY_NOT_EMITTED"


def test_trigger_ir_preserves_update_of_old_new_and_null_semantics() -> None:
    sql = (
        "CREATE TRIGGER audit_update BEFORE UPDATE OF id, name ON public.users "
        "FOR EACH ROW WHEN (NEW.id IS DISTINCT FROM OLD.id AND NOT (NEW.name = 'x')) "
        "EXECUTE FUNCTION audit_row()"
    )
    trigger = parse_trigger(sql, Dialect.POSTGRES, namespace_map={"public": "dbo"})
    assert trigger.update_columns == ("id", "name")
    assert trigger.when is not None
    emitted = emit_trigger(trigger, Dialect.POSTGRES)
    assert "UPDATE OF id, name" in emitted
    assert "WHEN ((NEW.id IS DISTINCT FROM OLD.id) AND (NOT (NEW.name = 'x')))" in emitted
    assert "ON dbo.users" in emitted
