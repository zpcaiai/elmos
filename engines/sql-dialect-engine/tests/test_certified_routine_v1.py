"""Tests for the typed certified-routine-v1 SQL function subset.

The positive cases exercise the same source AST through all four target
emitters. The negative cases make sure routine metadata and procedural
semantics remain visible rather than being laundered into a scalar function.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.advanced import emit_table_function, parse_table_function
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError, RoutineLanguage
from elmos_sql_dialect.routine import emit_create_function, parse_create_routine, parse_routine_identity

PURE_FUNCTION = (
    "CREATE FUNCTION make_key(p VARCHAR(32)) RETURNS VARCHAR(64) LANGUAGE SQL AS $$ SELECT 'x' || chr(10) || p $$"
)


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_pure_sql_function_is_emitted_in_native_target_syntax(target: str) -> None:
    report = translate_ddl(PURE_FUNCTION, "postgres", target, statement_kind="FUNCTION")
    assert report["status"] == "PASSED", report["reason"]
    emitted = report["emitted"] or ""
    assert "make_key" in emitted
    assert "p" in emitted
    assert "CHAR(10)" in emitted if target in {"mysql", "tsql"} else "CHR(10)" in emitted
    assert report["validation"]["executionStatus"] == "EXECUTION_NOT_ATTEMPTED"


def test_function_parser_builds_typed_body_instead_of_preserving_source_text() -> None:
    routine = parse_create_routine(PURE_FUNCTION, Dialect.POSTGRES)
    assert routine.name == "make_key"
    assert routine.parameters[0].type_ref.length == 32
    assert routine.return_type is not None
    assert routine.return_type.length == 64
    assert routine.body is not None
    assert "chr" not in repr(routine.body).lower()


def test_source_routine_ir_retains_nonportable_metadata_for_target_gate() -> None:
    routine = parse_create_routine(
        "CREATE FUNCTION guarded(p INT) RETURNS INT LANGUAGE SQL STABLE STRICT SECURITY DEFINER AS $$ SELECT p $$",
        Dialect.POSTGRES,
    )
    assert routine.strict is True
    assert routine.security_definer is True
    assert routine.search_path == ()
    assert routine.stability is not None

    report = translate_ddl(
        "CREATE FUNCTION guarded(p INT) RETURNS INT LANGUAGE SQL STABLE STRICT SECURITY DEFINER AS $$ SELECT p $$",
        "postgres",
        "mysql",
        statement_kind="FUNCTION",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET"


def test_static_plpgsql_return_query_table_function_has_a_typed_query_route() -> None:
    sql = (
        "CREATE FUNCTION active_users(p_min_id INT) RETURNS TABLE(id INT) "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "RETURN QUERY SELECT id FROM users WHERE id > 0; END; $$"
    )
    table_function = parse_table_function(sql, Dialect.POSTGRES)
    assert table_function.language is RoutineLanguage.PLPGSQL
    assert table_function.query.table == "users"
    report = translate_ddl(sql, "postgres", "tsql", statement_kind="FUNCTION")
    assert report["status"] == "PASSED", report
    assert report["emitted"] == (
        "CREATE FUNCTION active_users(@p_min_id INT) RETURNS TABLE AS RETURN (SELECT id FROM users WHERE id > 0)"
    )


def test_table_function_security_context_does_not_enter_static_route() -> None:
    sql = (
        "CREATE FUNCTION active_users() RETURNS TABLE(id INT) LANGUAGE plpgsql "
        "SECURITY DEFINER SET search_path = public "
        "AS $$ BEGIN RETURN QUERY SELECT id FROM users; END; $$"
    )
    report = translate_ddl(sql, "postgres", "tsql", statement_kind="FUNCTION")
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED"


def test_table_function_security_context_with_shim() -> None:
    sql = (
        "CREATE FUNCTION active_users() RETURNS TABLE(id INT) LANGUAGE plpgsql "
        "SECURITY DEFINER SET search_path = public "
        "AS $$ BEGIN RETURN QUERY SELECT id FROM users; END; $$"
    )
    report_tsql = translate_ddl(sql, "postgres", "tsql", statement_kind="FUNCTION", allow_routine_shim=True)
    assert report_tsql["status"] == "PASSED", report_tsql
    assert "CREATE FUNCTION active_users() RETURNS TABLE AS RETURN" in report_tsql["emitted"]

    # Note: translating dialect to itself raises RouteError, so test via emit_table_function directly
    tf = parse_table_function(sql, Dialect.POSTGRES)
    assert tf.security_definer is True
    assert tf.search_path == ("<source-defined>",)
    pg_emitted = emit_table_function(tf, Dialect.POSTGRES, allow_routine_shim=True)
    assert "SECURITY DEFINER" in pg_emitted


def test_scalar_routine_security_definer_shims() -> None:
    sql = "CREATE FUNCTION get_val(p INT) RETURNS INT LANGUAGE SQL SECURITY DEFINER AS $$ SELECT p $$"
    report_my = translate_ddl(sql, "postgres", "mysql", statement_kind="FUNCTION", allow_routine_shim=True)
    assert report_my["status"] == "PASSED", report_my
    assert "SQL SECURITY DEFINER" in report_my["emitted"]

    report_ora = translate_ddl(sql, "postgres", "oracle", statement_kind="FUNCTION", allow_routine_shim=True)
    assert report_ora["status"] == "PASSED", report_ora
    assert "AUTHID DEFINER" in report_ora["emitted"]

    report_tsql = translate_ddl(sql, "postgres", "tsql", statement_kind="FUNCTION", allow_routine_shim=True)
    assert report_tsql["status"] == "PASSED", report_tsql
    assert "WITH EXECUTE AS OWNER" in report_tsql["emitted"]


def test_default_namespace_is_applied_to_typed_routine_identity() -> None:
    identity = parse_routine_identity(
        "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL AS $$ SELECT p $$",
        Dialect.POSTGRES,
        namespace_map={"": "dbo"},
    )
    assert identity.schema == "dbo"


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        (
            "CREATE FUNCTION public.f(p INT) RETURNS INT LANGUAGE SQL AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_NAMESPACE_MAPPING_REQUIRED",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL STABLE SQL SECURITY DEFINER AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL IMMUTABLE AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE plpgsql AS $$ BEGIN IF p > 0 THEN RETURN p; END IF; END $$",
            "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS TABLE(value INT) LANGUAGE SQL AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL AS $$ SELECT p FROM source_table $$",
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        ),
    ],
)
def test_unsupported_function_semantics_fail_closed(sql: str, code: str) -> None:
    report = translate_ddl(sql, "postgres", "mysql", statement_kind="FUNCTION")
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == code
    assert report["emitted"] is None


def test_procedure_is_not_relabelled_as_a_function() -> None:
    report = translate_ddl(
        "CREATE PROCEDURE write_audit(p INT) LANGUAGE SQL AS $$ SELECT p $$",
        "postgres",
        "mysql",
        statement_kind="PROCEDURE",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_ROUTINE_UNSUPPORTED_BODY"


def test_trigger_is_not_relabelled_as_a_function() -> None:
    report = translate_ddl(
        "CREATE TRIGGER keep_history BEFORE UPDATE ON records FOR EACH ROW EXECUTE FUNCTION audit_row()",
        "postgres",
        "mysql",
        statement_kind="TRIGGER",
    )
    assert report["status"] == "BLOCKED"
    assert report["reasonCode"] == "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED"


def test_common_expression_functions_are_typed_and_rendered() -> None:
    sql = (
        "CREATE FUNCTION normalized(p VARCHAR(32)) RETURNS VARCHAR(32) "
        "LANGUAGE SQL AS $$ SELECT coalesce(trim(upper(p)), 'UNKNOWN') $$"
    )
    for target in ("mysql", "oracle", "tsql"):
        report = translate_ddl(sql, "postgres", target, statement_kind="FUNCTION")
        assert report["status"] == "PASSED", (target, report["reason"])
        assert "COALESCE" in (report["emitted"] or "")


def test_mysql_and_tsql_direct_return_functions_are_source_supported() -> None:
    source_forms = (
        (
            "CREATE FUNCTION mysql_key(p VARCHAR(32)) RETURNS VARCHAR(64) RETURN CONCAT('x', p)",
            "mysql",
        ),
        (
            "CREATE FUNCTION tsql_key(@p INT) RETURNS INT AS BEGIN RETURN @p + 1 END",
            "tsql",
        ),
    )
    for sql, source in source_forms:
        report = translate_ddl(sql, source, "postgres", statement_kind="FUNCTION")
        assert report["status"] == "PASSED", (source, report["reason"])
        assert "LANGUAGE SQL" in (report["emitted"] or "")


def test_routine_stability_shim_cross_dialect() -> None:
    from sqlglot import parse_one

    sql = (
        "CREATE FUNCTION elmos_cas_key(p VARCHAR) RETURNS TEXT "
        "LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT 'key/' || p $$"
    )
    stmt = parse_one(sql, read="postgres")
    routine = parse_create_routine(stmt, Dialect.POSTGRES, {"": "dbo", "public": "dbo"})

    # Without shim, fails closed on target emission
    with pytest.raises(DialectError) as exc:
        emit_create_function(routine, Dialect.MYSQL, allow_routine_shim=False)
    assert exc.value.code in (
        "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET",
        "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET",
    )

    # With allow_routine_shim, translates to all four dialects
    emitted_pg = emit_create_function(routine, Dialect.POSTGRES, allow_routine_shim=True)
    assert "IMMUTABLE" in emitted_pg

    emitted_mysql = emit_create_function(routine, Dialect.MYSQL, allow_routine_shim=True)
    assert "DETERMINISTIC" in emitted_mysql

    emitted_oracle = emit_create_function(routine, Dialect.ORACLE, allow_routine_shim=True)
    assert "DETERMINISTIC" in emitted_oracle

    emitted_tsql = emit_create_function(routine, Dialect.TSQL, allow_routine_shim=True)
    assert "CREATE FUNCTION dbo.elmos_cas_key" in emitted_tsql
