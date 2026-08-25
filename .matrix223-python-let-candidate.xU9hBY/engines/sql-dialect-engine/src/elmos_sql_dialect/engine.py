"""Top-level orchestration: parse -> canonical model -> emit -> validate.

This is the one place that decides PASSED vs BLOCKED. Every other module
raises `DialectError`/`RouteError` on anything outside certified-ddl-v1;
this module is where that becomes a structured, evidence-carrying report
instead of an uncaught exception -- mirroring `engines/polyglot-route-engine`'s
`RouteError` -> `{"status": "BLOCKED", "reason": ...}` convention.
"""
from __future__ import annotations

from typing import Any

from . import emitter, parser
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
) -> dict[str, Any]:
    """Translate one statement from `source_dialect` to `target_dialect`.

    `statement_kind` selects the profile:

      TABLE / INDEX -- certified-ddl-v1
      ALTER         -- certified-alter-v1

    Returns a structured report; never raises for out-of-profile input --
    that is reported as `status: "BLOCKED"`.
    """
    source = _resolve_dialect(source_dialect)
    target = _resolve_dialect(target_dialect)
    if source == target:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER: translating a dialect to itself is not a supported route")
    if statement_kind not in ("TABLE", "INDEX", "ALTER"):
        raise RouteError(
            f"UNSUPPORTED_STATEMENT_KIND: {statement_kind!r} must be TABLE, INDEX or ALTER"
        )
    profile = "certified-alter-v1" if statement_kind == "ALTER" else "certified-ddl-v1"

    try:
        if statement_kind == "TABLE":
            emitted = emitter.emit_create_table(parser.parse_create_table(sql, source), target)
        elif statement_kind == "ALTER":
            emitted = emitter.emit_alter_table(parser.parse_alter_table(sql, source), target)
        else:
            emitted = emitter.emit_create_index(parser.parse_create_index(sql, source), target)
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

    report = validate(emitted, target, dsn)
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
