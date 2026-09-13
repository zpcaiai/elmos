"""elmos-sql-dialect: certified SQL DDL and routine translation profiles.

See README.md for the certified subset boundary and why an unbounded "100%
success on any SQL" target is not offered.
"""

from __future__ import annotations

from .engine import translate_ddl, translate_query, translate_sql, translate_upsert

__all__ = [
    "engine",
    "models",
    "parser",
    "routine",
    "advanced",
    "emitter",
    "validator",
    "dialects",
    "toolchains",
    "profiles",
    "identifiers",
    "capabilities",
    "sql_diagnostic_auto_repairer",
    "database_handoff_ledger",
    "procedural_ast_lowerer",
    "translate_ddl",
    "translate_query",
    "translate_sql",
    "translate_upsert",
]

