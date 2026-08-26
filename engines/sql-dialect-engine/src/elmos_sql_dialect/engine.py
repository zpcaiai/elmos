"""Top-level orchestration: parse -> canonical model -> emit -> validate.

This is the one place that decides PASSED vs BLOCKED. Every other module
raises `DialectError`/`RouteError` on anything outside the active certified
profiles;
this module is where that becomes a structured, evidence-carrying report
instead of an uncaught exception -- mirroring `engines/polyglot-route-engine`'s
`RouteError` -> `{"status": "BLOCKED", "reason": ...}` convention.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import emitter, parser
from .advanced import (
    emit_comment,
    emit_privilege,
    emit_procedure,
    emit_table_function,
    emit_trigger,
    emit_view,
    parse_comment,
    parse_create_view,
    parse_privilege,
    parse_procedure,
    parse_row_policy,
    parse_table_function,
    parse_trigger,
)
from .models import Dialect, DialectError, RouteError
from .validator import validate


def _resolve_dialect(value: str) -> Dialect:
    try:
        return Dialect(value)
    except ValueError as exc:
        raise RouteError(f"UNSUPPORTED_DIALECT: {value!r} is not one of {[d.value for d in Dialect]}") from exc


def translate_ddl(
    sql: str,
    source_dialect: str,
    target_dialect: str,
    *,
    statement_kind: str = "TABLE",
    dsn: str | None = None,
    namespace_map: Mapping[str, str] | None = None,
    catalog: emitter.ColumnCatalogLike | None = None,
    comment_catalog: emitter.CommentColumnCatalogLike | None = None,
) -> dict[str, Any]:
    """Translate one statement from `source_dialect` to `target_dialect`.

    `statement_kind` selects the profile:

      TABLE / INDEX -- certified-ddl-v1
      ALTER         -- certified-alter-v1
      DROP          -- certified-drop-v1
      SCHEMA        -- certified-schema-v1
      FUNCTION / PROCEDURE / TRIGGER -- certified-routine-v1
      VIEW / COMMENT / GRANT / REVOKE -- typed database object profiles
      POLICY -- explicit RLS target-route blocker

    Returns a structured report; never raises for out-of-profile input --
    that is reported as `status: "BLOCKED"`.

    ``catalog`` is optional source-schema context for standalone indexes and
    constraints. It is consulted only for target rules that need a column type
    (currently MySQL TEXT keys); absent context remains unknown rather than
    being treated as evidence of safety.

    ``comment_catalog`` is optional full source-schema context for MySQL
    column comments. MySQL's MODIFY COLUMN form must repeat the complete
    type/nullability/default/identity definition; a type-only catalogue is
    deliberately insufficient and remains blocked.
    """
    source = _resolve_dialect(source_dialect)
    target = _resolve_dialect(target_dialect)
    if source == target:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER: translating a dialect to itself is not a supported route")
    if statement_kind not in (
        "TABLE", "INDEX", "ALTER", "DROP", "SCHEMA", "FUNCTION", "PROCEDURE", "TRIGGER",
        "VIEW", "COMMENT", "GRANT", "REVOKE", "POLICY",
    ):
        raise RouteError(
            f"UNSUPPORTED_STATEMENT_KIND: {statement_kind!r} must be TABLE, INDEX, ALTER, DROP, "
            "SCHEMA, FUNCTION, PROCEDURE, TRIGGER, VIEW, COMMENT, GRANT, REVOKE or POLICY"
        )
    profile = {
        "ALTER": "certified-alter-v1",
        "DROP": "certified-drop-v1",
            "SCHEMA": "certified-schema-v1",
            "VIEW": "certified-view-v1",
            "COMMENT": "certified-comment-v1",
            "GRANT": "certified-privilege-v1",
            "REVOKE": "certified-privilege-v1",
            "POLICY": "certified-rls-v1",
        "FUNCTION": "certified-routine-v1",
        "PROCEDURE": "certified-routine-v1",
        "TRIGGER": "certified-routine-v1",
    }.get(statement_kind, "certified-ddl-v1")

    try:
        if statement_kind == "TABLE":
            emitted = emitter.emit_create_table(parser.parse_create_table(sql, source, namespace_map), target)
        elif statement_kind == "ALTER":
            emitted = emitter.emit_alter_table(
                parser.parse_alter_table(sql, source, namespace_map), target, catalog
            )
        elif statement_kind == "DROP":
            emitted = emitter.emit_drop_table(parser.parse_drop_table(sql, source, namespace_map), target)
        elif statement_kind == "SCHEMA":
            emitted = emitter.emit_create_schema(parser.parse_create_schema(sql, source, namespace_map), target)
        elif statement_kind == "FUNCTION":
            from .routine import emit_create_function, parse_create_routine

            try:
                table_function = parse_table_function(sql, source, namespace_map)
            except DialectError as exc:
                if exc.code == "CERTIFIED_ROUTINE_NOT_TABLE_FUNCTION":
                    emitted = emit_create_function(parse_create_routine(sql, source, namespace_map), target)
                else:
                    # A RETURNS TABLE declaration is still a routine even
                    # when its body is outside the table-function subset.
                    # Re-run the scalar parser only to recover its explicit
                    # table-return blocker; never silently downgrade it to a
                    # scalar conversion.
                    try:
                        parse_create_routine(sql, source, namespace_map)
                    except DialectError as scalar_error:
                        raise scalar_error from exc
                    raise
            else:
                emitted = emit_table_function(table_function, target)
        elif statement_kind == "PROCEDURE":
            emitted = emit_procedure(parse_procedure(sql, source, namespace_map), target)
        elif statement_kind == "TRIGGER":
            emitted = emit_trigger(parse_trigger(sql, source, namespace_map), target)
        elif statement_kind == "VIEW":
            emitted = emit_view(parse_create_view(sql, source, namespace_map), target)
        elif statement_kind == "COMMENT":
            emitted = emit_comment(parse_comment(sql, source, namespace_map), target, comment_catalog)
        elif statement_kind in ("GRANT", "REVOKE"):
            emitted = emit_privilege(parse_privilege(sql, source, namespace_map), target)
        elif statement_kind == "POLICY":
            parse_row_policy(sql, source)
            raise AssertionError("parse_row_policy is a permanent fail-closed route")  # pragma: no cover
        else:
            emitted = emitter.emit_create_index(
                parser.parse_create_index(sql, source, namespace_map), target, catalog
            )
    except DialectError as exc:
        return {
            "schemaVersion": "1.0",
            "kind": "elmos.sql-dialect-translation",
            "status": "BLOCKED",
            "profile": profile,
            "sourceDialect": source.value,
            "targetDialect": target.value,
            "reasonCode": exc.code,
            "reason": exc.message,
            "emitted": None,
            "validation": None,
        }

    report = validate(
        emitted,
        target,
        dsn,
        routine=statement_kind in ("FUNCTION", "PROCEDURE", "TRIGGER"),
    )
    status = "PASSED" if report.passed() else "FAILED"
    return {
        "schemaVersion": "1.0",
        "kind": "elmos.sql-dialect-translation",
        "status": status,
        "profile": profile,
        "sourceDialect": source.value,
        "targetDialect": target.value,
        "reasonCode": None if status == "PASSED" else (
            "CERTIFIED_ALTER_TARGET_VALIDATION_FAILED" if statement_kind == "ALTER"
            else "CERTIFIED_DROP_TARGET_VALIDATION_FAILED" if statement_kind == "DROP"
            else "CERTIFIED_SCHEMA_TARGET_VALIDATION_FAILED" if statement_kind == "SCHEMA"
            else "CERTIFIED_VIEW_TARGET_VALIDATION_FAILED" if statement_kind == "VIEW"
            else "CERTIFIED_COMMENT_TARGET_VALIDATION_FAILED" if statement_kind == "COMMENT"
            else "CERTIFIED_PRIVILEGE_TARGET_VALIDATION_FAILED" if statement_kind in ("GRANT", "REVOKE")
            else "CERTIFIED_ROUTINE_TARGET_VALIDATION_FAILED"
            if statement_kind in ("FUNCTION", "PROCEDURE", "TRIGGER")
            else "CERTIFIED_DDL_TARGET_VALIDATION_FAILED"
        ),
        "reason": None if status == "PASSED" else "; ".join(report.syntax_diagnostics),
        "emitted": emitted,
        "validation": {
            "syntaxStatus": report.syntax_status,
            "syntaxDiagnostics": list(report.syntax_diagnostics),
            "executionStatus": report.execution_status,
            "executionDiagnostics": list(report.execution_diagnostics),
        },
    }
