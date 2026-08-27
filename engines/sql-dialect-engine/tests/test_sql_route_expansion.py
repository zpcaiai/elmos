"""Regression tests for the typed route expansion in this change."""

from __future__ import annotations

import json

import pytest

from elmos_sql_dialect.advanced import (
    emit_comment,
    emit_privilege,
    emit_trigger,
    parse_comment,
    parse_privilege,
    parse_trigger,
)
from elmos_sql_dialect.capabilities import target_capability_matrix
from elmos_sql_dialect.emitter import emit_create_index, emit_create_table, emit_row_security
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import (
    CheckComparison,
    CheckValueFunction,
    CommentObjectKind,
    Dialect,
    DialectError,
    IndexExpressionKind,
    RowSecurityAction,
)
from elmos_sql_dialect.parser import (
    _parse_source_statements,
    parse_create_index,
    parse_create_table,
    parse_row_security,
)
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
    assert matrix["row_security_control"]["exact_targets"] == ("postgres",)


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
        "EXECUTE FUNCTION public.audit_row()"
    )
    trigger = parse_trigger(sql, Dialect.POSTGRES, namespace_map={"public": "dbo"})
    assert trigger.update_columns == ("id", "name")
    assert trigger.routine_schema == "dbo"
    assert trigger.when is not None
    emitted = emit_trigger(trigger, Dialect.POSTGRES)
    assert "UPDATE OF id, name" in emitted
    assert "WHEN ((NEW.id IS DISTINCT FROM OLD.id) AND (NOT (NEW.name = 'x')))" in emitted
    assert "ON dbo.users" in emitted
    assert "EXECUTE FUNCTION dbo.audit_row()" in emitted


@pytest.mark.parametrize("action", ["ENABLE", "FORCE", "DISABLE", "NO FORCE"])
def test_row_security_control_is_typed_and_postgres_target_bound(action: str) -> None:
    command = parse_row_security(
        f'ALTER TABLE public."Order" {action} ROW LEVEL SECURITY',
        Dialect.POSTGRES,
        namespace_map={"public": "dbo"},
    )
    assert command.action is RowSecurityAction(action)
    assert command.schema == "dbo"
    assert command.table == "Order"
    assert emit_row_security(command, Dialect.POSTGRES) == (
        f'ALTER TABLE dbo."Order" {action} ROW LEVEL SECURITY'
    )


def test_row_security_is_not_downgraded_to_privileges_on_other_targets() -> None:
    report = translate_ddl(
        "ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY",
        "postgres",
        "mysql",
        statement_kind="RLS",
        namespace_map={"public": "dbo"},
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED"


def test_postgres_role_comment_is_typed_without_cross_target_fallback() -> None:
    comment = parse_comment(
        "COMMENT ON ROLE elmos_scheduler IS 'non-login scheduler role'",
        Dialect.POSTGRES,
    )
    assert comment.object_kind is CommentObjectKind.ROLE
    assert emit_comment(comment, Dialect.POSTGRES) == (
        "COMMENT ON ROLE elmos_scheduler IS 'non-login scheduler role'"
    )
    report = translate_ddl(
        "COMMENT ON ROLE elmos_scheduler IS 'non-login scheduler role'",
        "postgres",
        "mysql",
        statement_kind="COMMENT",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_COMMENT_TARGET_UNSUPPORTED"


def test_sql_server_role_comment_uses_database_principal_extended_property() -> None:
    report = translate_ddl(
        "COMMENT ON ROLE elmos_scheduler IS 'non-login scheduler role'",
        "postgres",
        "tsql",
        statement_kind="COMMENT",
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] == (
        "EXEC sys.sp_addextendedproperty @name = N'MS_Description', "
        "@value = N'non-login scheduler role', "
        "@level0type = N'USER', @level0name = N'elmos_scheduler'"
    )


def test_sql_server_role_comment_still_respects_extended_property_value_limit() -> None:
    comment = parse_comment(
        "COMMENT ON ROLE elmos_scheduler IS 'non-login scheduler role'",
        Dialect.POSTGRES,
    )
    long_comment = type(comment)(
        object_kind=comment.object_kind,
        object_name=comment.object_name,
        text="x" * 3751,
        table_name=comment.table_name,
        schema=comment.schema,
        table_schema=comment.table_schema,
        routine_argument_types=comment.routine_argument_types,
        routine_argument_type_refs=comment.routine_argument_type_refs,
    )
    with pytest.raises(DialectError, match="CERTIFIED_COMMENT_TARGET_VALUE_TOO_LARGE"):
        emit_comment(long_comment, Dialect.TSQL)


def test_routine_identity_catalog_gates_signatureless_target_routes() -> None:
    catalog = SourceSchemaCatalog()
    statements = _parse_source_statements(
        "CREATE FUNCTION public.audit_row(p_id INT) RETURNS INT LANGUAGE sql AS $$ SELECT p_id $$;",
        Dialect.POSTGRES,
    )
    assert len(statements) == 1
    _record_catalog_statement(catalog, statements[0], Dialect.POSTGRES, {"public": "dbo"})

    privilege = parse_privilege(
        "REVOKE EXECUTE ON FUNCTION public.audit_row(integer) FROM PUBLIC",
        Dialect.POSTGRES,
        {"public": "dbo"},
    )
    assert privilege.routine_argument_type_refs
    assert emit_privilege(privilege, Dialect.ORACLE, catalog) == "REVOKE EXECUTE ON dbo.audit_row FROM PUBLIC"
    assert emit_privilege(privilege, Dialect.TSQL, catalog) == (
        "REVOKE EXECUTE ON OBJECT::dbo.audit_row FROM PUBLIC"
    )
    with pytest.raises(DialectError, match="CERTIFIED_PRIVILEGE_PRINCIPAL_UNSUPPORTED_BY_TARGET"):
        emit_privilege(privilege, Dialect.MYSQL, catalog)

    comment = parse_comment(
        "COMMENT ON FUNCTION public.audit_row(integer) IS 'audit row'",
        Dialect.POSTGRES,
        {"public": "dbo"},
    )
    assert emit_comment(comment, Dialect.MYSQL, routine_catalog=catalog) == (
        "ALTER FUNCTION dbo.audit_row COMMENT 'audit row'"
    )


def test_routine_identity_catalog_refuses_ambiguous_overloads() -> None:
    catalog = SourceSchemaCatalog()
    for sql in (
        "CREATE FUNCTION public.f(p INT) RETURNS INT LANGUAGE sql AS $$ SELECT p $$",
        "CREATE FUNCTION public.f(p BIGINT) RETURNS INT LANGUAGE sql AS $$ SELECT 1 $$",
    ):
        statements = _parse_source_statements(sql, Dialect.POSTGRES)
        assert len(statements) == 1
        _record_catalog_statement(catalog, statements[0], Dialect.POSTGRES, {"public": "dbo"})
    privilege = parse_privilege(
        "REVOKE EXECUTE ON FUNCTION public.f(integer) FROM PUBLIC",
        Dialect.POSTGRES,
        {"public": "dbo"},
    )
    with pytest.raises(DialectError, match="CERTIFIED_PRIVILEGE_ROUTINE_SIGNATURE_REQUIRED"):
        emit_privilege(privilege, Dialect.ORACLE, catalog)


@pytest.mark.parametrize(
    ("sql", "kind", "expected"),
    [
        (
            "CREATE UNIQUE INDEX recipe_name_uq ON public.recipes ((payload ->> 'recipeName'))",
            IndexExpressionKind.JSON_TEXT_PATH,
            "payload ->> 'recipeName'",
        ),
        (
            "CREATE UNIQUE INDEX account_email_uq ON public.accounts (LOWER(email))",
            IndexExpressionKind.LOWER,
            "LOWER(email)",
        ),
    ],
)
def test_typed_expression_index_keys_are_structured_and_source_renderable(
    sql: str, kind: IndexExpressionKind, expected: str
) -> None:
    index = parse_create_index(sql, Dialect.POSTGRES, namespace_map={"public": "dbo"})
    assert index.columns[0].expression is not None
    assert index.columns[0].expression.kind is kind
    assert "ON dbo." in emit_create_index(index, Dialect.POSTGRES)
    assert expected in emit_create_index(index, Dialect.POSTGRES)


def test_typed_expression_index_keys_remain_blocked_without_target_proof() -> None:
    report = translate_ddl(
        "CREATE UNIQUE INDEX account_email_uq ON accounts (LOWER(email))",
        "postgres",
        "mysql",
        statement_kind="INDEX",
    )
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_DDL_INDEX_EXPRESSION_UNSUPPORTED_BY_TARGET"


def test_jsonb_typeof_check_is_typed_and_target_bound() -> None:
    ddl = "CREATE TABLE payloads (payload JSONB NOT NULL CHECK (JSONB_TYPEOF(payload) = 'object'))"
    table = parse_create_table(ddl, Dialect.POSTGRES)
    check = table.check_constraints[0].expression
    assert isinstance(check, CheckComparison)
    assert check.left_expression is not None
    assert check.left_expression.function is CheckValueFunction.JSONB_TYPEOF
    blocked = translate_ddl(ddl, "postgres", "mysql")
    assert blocked["status"] == "BLOCKED", blocked
    assert blocked["reasonCode"] == "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED"


def test_jsonb_top_level_key_check_is_typed_and_target_bound() -> None:
    ddl = "CREATE TABLE payloads (payload JSONB NOT NULL CHECK (payload ? 'quotaAllocationId'))"
    table = parse_create_table(ddl, Dialect.POSTGRES)
    check = table.check_constraints[0].expression
    assert isinstance(check, CheckComparison)
    assert check.left_expression is not None
    assert check.left_expression.function is CheckValueFunction.JSONB_HAS_KEY
    assert check.left_expression.argument is not None
    assert check.left_expression.argument.value == "quotaAllocationId"
    assert "payload ? 'quotaAllocationId'" in emit_create_table(table, Dialect.POSTGRES)
    blocked = translate_ddl(ddl, "postgres", "mysql")
    assert blocked["status"] == "BLOCKED", blocked
    assert blocked["reasonCode"] == "CERTIFIED_DDL_JSON_BINARY_SEMANTICS_UNSUPPORTED"


def test_array_length_check_is_typed_and_target_bound() -> None:
    ddl = "CREATE TABLE api_keys (scopes TEXT[] CHECK (ARRAY_LENGTH(scopes, 1) BETWEEN 1 AND 24))"
    table = parse_create_table(ddl, Dialect.POSTGRES)
    check = table.check_constraints[0].expression
    assert isinstance(check, CheckComparison)
    assert check.left_expression is not None
    assert check.left_expression.function.value == "ARRAY_LENGTH"
    blocked = translate_ddl(ddl, "postgres", "oracle")
    assert blocked["status"] == "BLOCKED", blocked
    assert blocked["reasonCode"] == "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED"


def test_array_cardinality_and_null_element_checks_are_typed_and_target_bound() -> None:
    ddl = (
        "CREATE TABLE cache_entries ("
        "action_component_names TEXT[], "
        "action_component_values TEXT[], "
        "CHECK (CARDINALITY(action_component_names) = CARDINALITY(action_component_values)), "
        "CHECK (ARRAY_POSITION(action_component_names, NULL) IS NULL)"
        ")"
    )
    table = parse_create_table(ddl, Dialect.POSTGRES)
    first, second = table.check_constraints
    assert isinstance(first.expression, CheckComparison)
    assert first.expression.left_expression is not None
    assert first.expression.left_expression.function is CheckValueFunction.ARRAY_CARDINALITY
    assert first.expression.right_expression is not None
    assert isinstance(second.expression, CheckComparison)
    assert second.expression.left_expression is not None
    assert second.expression.left_expression.function is CheckValueFunction.ARRAY_POSITION
    assert second.expression.left_expression.argument is not None
    assert second.expression.left_expression.argument.is_null
    blocked = translate_ddl(ddl, "postgres", "mysql")
    assert blocked["status"] == "BLOCKED", blocked
    assert blocked["reasonCode"] == "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED"


def test_array_containment_check_is_typed_and_target_bound() -> None:
    ddl = (
        "CREATE TABLE usage_alert_preferences ("
        "threshold_bps INTEGER[] NOT NULL DEFAULT ARRAY[5000,8000], "
        "CHECK (threshold_bps <@ ARRAY[1000,2500,5000,7500,8000,9000,9500,10000])"
        ")"
    )
    table = parse_create_table(ddl, Dialect.POSTGRES)
    check = table.check_constraints[0].expression
    assert isinstance(check, CheckComparison)
    assert check.left_expression is not None
    assert check.left_expression.function is CheckValueFunction.ARRAY_CONTAINED_BY
    assert [item.value for item in check.left_expression.arguments] == [
        "1000",
        "2500",
        "5000",
        "7500",
        "8000",
        "9000",
        "9500",
        "10000",
    ]
    assert "threshold_bps <@ ARRAY[1000, 2500" in emit_create_table(table, Dialect.POSTGRES)
    blocked = translate_ddl(ddl, "postgres", "mysql")
    assert blocked["status"] == "BLOCKED", blocked
    assert blocked["reasonCode"] == "CERTIFIED_DDL_ARRAY_TARGET_UNSUPPORTED"


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_is_distinct_from_literal_preserves_null_semantics(target: str) -> None:
    report = translate_ddl(
        "CREATE TABLE states (status VARCHAR(16) CHECK (status IS DISTINCT FROM 'READY'))",
        "postgres",
        target,
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"] is not None
    assert "READY" in report["emitted"]
