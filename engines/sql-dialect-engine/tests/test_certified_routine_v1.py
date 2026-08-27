"""Tests for the typed certified-routine-v1 SQL function subset.

The positive cases exercise the same source AST through all four target
emitters. The negative cases make sure routine metadata and procedural
semantics remain visible rather than being laundered into a scalar function.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.routine import parse_create_routine

PURE_FUNCTION = (
    "CREATE FUNCTION make_key(p VARCHAR(32)) RETURNS VARCHAR(64) "
    "LANGUAGE SQL AS $$ SELECT 'x' || chr(10) || p $$"
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


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        (
            "CREATE FUNCTION public.f(p INT) RETURNS INT LANGUAGE SQL AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_NAMESPACE_MAPPING_REQUIRED",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL STABLE "
            "SQL SECURITY DEFINER AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL IMMUTABLE "
            "AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE plpgsql "
            "AS $$ BEGIN IF p > 0 THEN RETURN p; END IF; END $$",
            "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS TABLE(value INT) LANGUAGE SQL "
            "AS $$ SELECT p $$",
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        ),
        (
            "CREATE FUNCTION f(p INT) RETURNS INT LANGUAGE SQL "
            "AS $$ SELECT p FROM source_table $$",
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
        "CREATE TRIGGER keep_history BEFORE UPDATE ON records "
        "FOR EACH ROW EXECUTE FUNCTION audit_row()",
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
            "CREATE FUNCTION mysql_key(p VARCHAR(32)) RETURNS VARCHAR(64) "
            "RETURN CONCAT('x', p)",
            "mysql",
        ),
        (
            "CREATE FUNCTION tsql_key(@p INT) RETURNS INT "
            "AS BEGIN RETURN @p + 1 END",
            "tsql",
        ),
    )
    for sql, source in source_forms:
        report = translate_ddl(sql, source, "postgres", statement_kind="FUNCTION")
        assert report["status"] == "PASSED", (source, report["reason"])
        assert "LANGUAGE SQL" in (report["emitted"] or "")
