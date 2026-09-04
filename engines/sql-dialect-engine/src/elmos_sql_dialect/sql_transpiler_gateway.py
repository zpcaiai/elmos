"""Fail-closed adapter for the repository's typed SQL transpiler.

The unified CLI used to perform SQL rewrites with regular expressions and then
reported every result as ``VERIFIED_SEMANTIC_EQUIVALENCE``. Apart from changing
tokens inside string literals, that path could move an Oracle ``ROWNUM``
predicate ahead of the remaining ``WHERE`` predicate and produce invalid SQL.

This module is now only an adapter. It delegates exact-profile requests to the
typed SQL engine in ``engines/database-data-engine/sql-transpiler`` and preserves
that engine's evidence boundary. Generic dialect-only requests, unavailable
engines, unbound ChinaDB targets, and semantic constructs that survive target
emission unchanged are blocked without emitting candidate SQL.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict


class SupportedDialect(str, Enum):
    ORACLE = "oracle"
    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"
    TSQL = "tsql"
    SQLITE = "sqlite"
    DUCKDB = "duckdb"
    DM8 = "dm8"
    TIDB = "tidb"
    OCEANBASE_ORACLE = "oceanbase-oracle"
    OCEANBASE_MYSQL = "oceanbase-mysql"
    OPENGAUSS = "opengauss"
    KINGBASEES = "kingbasees"
    GBASE = "gbase"
    HIGHGO = "highgo-hgdb"
    GOLDENDB = "goldendb"


_CORE_DIALECTS = {
    "oracle": "oracle",
    "postgres": "postgres",
    "mysql": "mysql",
    "sqlserver": "tsql",
    "tsql": "tsql",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
}
_KNOWN_DIALECTS = frozenset(item.value for item in SupportedDialect)


class _BlockedCommon(TypedDict):
    sql: str
    source_dialect: str
    target_dialect: str
    source_profile: str | None
    target_profile: str | None


@dataclass
class SqlTranspileResult:
    source_dialect: str
    target_dialect: str
    source_sql: str
    target_sql: str | None
    status: str = "BLOCKED"
    source_profile: str | None = None
    target_profile: str | None = None
    transformed_constructs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    semantic_equivalence: str = "NOT_VERIFIED"
    reason_code: str | None = None
    reason: str | None = None
    verification: dict[str, Any] = field(default_factory=dict)
    merkle_receipt: str = ""


def _receipt(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _class_name(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    value = node.get("c")
    return value.rsplit(".", 1)[-1] if isinstance(value, str) else ""


def _ast_has_class(ast_dump: Any, *names: str) -> bool:
    if not isinstance(ast_dump, list):
        return False
    wanted = set(names)
    return any(_class_name(node) in wanted for node in ast_dump)


def _ast_has_unquoted_identifier(
    ast_dump: Any,
    value: str,
    *,
    parent_class: str,
    require_unqualified: bool = False,
) -> bool:
    """Inspect a SQLGlot dump without reparsing or scanning SQL text.

    SQLGlot dumps are a flat node list. Each child stores its parent's list
    index in ``i``. Walking those typed relationships lets the gateway
    distinguish the Oracle pseudocolumn ``ROWNUM`` from ``'ROWNUM'`` and from a
    quoted user column with the same spelling.
    """

    if not isinstance(ast_dump, list):
        return False
    for identifier_index, identifier in enumerate(ast_dump):
        if _class_name(identifier) != "Identifier":
            continue
        value_nodes = [
            node
            for node in ast_dump
            if isinstance(node, dict)
            and node.get("i") == identifier_index
            and node.get("k") == "this"
        ]
        if not any(str(node.get("v", "")).upper() == value.upper() for node in value_nodes):
            continue
        if any(
            isinstance(node, dict)
            and node.get("i") == identifier_index
            and node.get("k") == "quoted"
            and node.get("v") is True
            for node in ast_dump
        ):
            continue
        parent_index = identifier.get("i")
        if not isinstance(parent_index, int) or not (0 <= parent_index < len(ast_dump)):
            continue
        if _class_name(ast_dump[parent_index]) != parent_class:
            continue
        if require_unqualified and any(
            isinstance(node, dict)
            and node.get("i") == parent_index
            and node.get("k") in {"table", "db", "catalog"}
            for node in ast_dump
        ):
            continue
        return True
    return False


def _post_emission_blocker(
    statements: Any,
    *,
    source_dialect: str,
    target_dialect: str,
) -> tuple[str, str] | None:
    """Reject known source-only semantics that the target AST still contains."""

    if not isinstance(statements, tuple | list):
        return "TYPED_ENGINE_RESULT_INVALID", "Typed engine returned no inspectable statement IR."
    for statement in statements:
        source_ast = getattr(statement, "source_ast", None)
        target_ast = getattr(statement, "target_ast", None)
        if source_dialect == "oracle" and target_dialect != "oracle":
            source_has_rownum = _ast_has_unquoted_identifier(
                source_ast,
                "ROWNUM",
                parent_class="Column",
                require_unqualified=True,
            )
            target_has_rownum = _ast_has_unquoted_identifier(
                target_ast,
                "ROWNUM",
                parent_class="Column",
                require_unqualified=True,
            )
            if source_has_rownum and target_has_rownum:
                return (
                    "UNSUPPORTED_ORACLE_ROWNUM_SEMANTICS",
                    "Oracle ROWNUM survived target emission as a column reference; "
                    "pagination semantics are not preserved.",
                )
            source_has_dual = _ast_has_unquoted_identifier(
                source_ast,
                "DUAL",
                parent_class="Table",
                require_unqualified=True,
            )
            target_has_dual = _ast_has_unquoted_identifier(
                target_ast,
                "DUAL",
                parent_class="Table",
                require_unqualified=True,
            )
            if source_has_dual and target_has_dual:
                return (
                    "UNSUPPORTED_ORACLE_DUAL_SEMANTICS",
                    "Oracle DUAL survived target emission as a physical table reference "
                    "without a bound compatibility contract.",
                )
            if _ast_has_class(source_ast, "Connect", "Prior") and _ast_has_class(
                target_ast, "Connect", "Prior"
            ):
                return (
                    "UNSUPPORTED_ORACLE_HIERARCHICAL_QUERY",
                    "Oracle hierarchical-query nodes survived target emission without a recursive-query lowering.",
                )
        if source_dialect != target_dialect and _ast_has_class(source_ast, "Anonymous") and _ast_has_class(
            target_ast, "Anonymous"
        ):
            return (
                "UNBOUND_FUNCTION_SEMANTICS",
                "An unclassified function survived cross-dialect emission without a versioned capability binding.",
            )
    return None


class SqlTranspilerGateway:
    """Adapter from the legacy CLI schema to the exact typed SQL engine."""

    def __init__(
        self,
        *,
        typed_transpile: Callable[[Any], Any] | None = None,
        request_factory: Callable[..., Any] | None = None,
    ) -> None:
        if (typed_transpile is None) != (request_factory is None):
            raise ValueError("typed_transpile and request_factory must be supplied together")
        self._typed_transpile = typed_transpile
        self._request_factory = request_factory

    def _blocked(
        self,
        *,
        sql: str,
        source_dialect: str,
        target_dialect: str,
        source_profile: str | None,
        target_profile: str | None,
        reason_code: str,
        reason: str,
        warnings: list[str] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> SqlTranspileResult:
        payload = {
            "sourceDialect": source_dialect,
            "targetDialect": target_dialect,
            "sourceProfile": source_profile,
            "targetProfile": target_profile,
            "sourceDigest": f"sha256:{hashlib.sha256(sql.encode('utf-8')).hexdigest()}",
            "status": "BLOCKED",
            "reasonCode": reason_code,
        }
        return SqlTranspileResult(
            source_dialect=source_dialect,
            target_dialect=target_dialect,
            source_sql=sql.strip(),
            target_sql=None,
            status="BLOCKED",
            source_profile=source_profile,
            target_profile=target_profile,
            warnings=warnings or [],
            semantic_equivalence="NOT_VERIFIED",
            reason_code=reason_code,
            reason=reason,
            verification=verification or {
                "syntaxParse": "NOT_RUN",
                "targetEmit": "NOT_RUN",
                "targetReparse": "NOT_RUN",
                "sourceExecution": "NOT_RUN",
                "targetExecution": "NOT_RUN",
                "resultEquivalence": "NOT_RUN",
                "gatewaySemanticGuard": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            merkle_receipt=_receipt(payload),
        )

    def _load_typed_engine(self) -> tuple[Callable[[Any], Any], Callable[..., Any]]:
        if self._typed_transpile is not None and self._request_factory is not None:
            return self._typed_transpile, self._request_factory
        models = importlib.import_module("elmos_sql_transpiler.models")
        transpiler = importlib.import_module("elmos_sql_transpiler.transpiler")
        return transpiler.transpile, models.TranspileRequest

    def transpile(
        self,
        sql: str,
        src_dialect: str,
        tgt_dialect: str,
        *,
        source_profile: str | None = None,
        target_profile: str | None = None,
    ) -> SqlTranspileResult:
        src = src_dialect.lower().strip()
        tgt = tgt_dialect.lower().strip()
        normalized_sql = sql.strip()
        common: _BlockedCommon = {
            "sql": normalized_sql,
            "source_dialect": src,
            "target_dialect": tgt,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }
        if not normalized_sql:
            return self._blocked(
                **common,
                reason_code="SQL_INPUT_REQUIRED",
                reason="SQL input must not be empty.",
            )
        if src not in _KNOWN_DIALECTS or tgt not in _KNOWN_DIALECTS:
            return self._blocked(
                **common,
                reason_code="UNSUPPORTED_DIALECT",
                reason="The requested dialect is not registered by the gateway.",
            )
        if not source_profile or not target_profile:
            return self._blocked(
                **common,
                reason_code="EXACT_PROFILE_REQUIRED",
                reason=(
                    "Cross-dialect SQL translation requires exact source and target profile IDs; "
                    "generic dialect names do not bind engine versions, editions, drivers, collations, or SQL modes."
                ),
            )
        if source_profile == target_profile:
            return self._blocked(
                **common,
                reason_code="SOURCE_AND_TARGET_PROFILE_MUST_DIFFER",
                reason="Source and target SQL profiles must differ.",
            )
        if src not in _CORE_DIALECTS or tgt not in _CORE_DIALECTS:
            return self._blocked(
                **common,
                reason_code="EXACT_TARGET_ADAPTER_REQUIRED",
                reason=(
                    "This dialect is catalog-only in the gateway. A versioned typed target adapter and "
                    "provider evidence are required before target SQL may be emitted."
                ),
            )

        try:
            typed_transpile, request_factory = self._load_typed_engine()
        except (ImportError, ModuleNotFoundError):
            return self._blocked(
                **common,
                reason_code="TYPED_QUERY_ENGINE_UNAVAILABLE",
                reason="The repository-owned typed SQL transpiler is not installed in this CLI runtime.",
            )

        query_id = f"unified-cli-{hashlib.sha256(normalized_sql.encode('utf-8')).hexdigest()[:24]}"
        try:
            typed_result = typed_transpile(
                request_factory(
                    query_id=query_id,
                    source_profile=source_profile,
                    target_profile=target_profile,
                    sql=normalized_sql,
                )
            )
        except ValueError:
            return self._blocked(
                **common,
                reason_code="EXACT_PROFILE_INVALID",
                reason="One or both exact SQL profile IDs are invalid for the typed engine.",
            )
        except RuntimeError as exc:
            code = (
                "EXACT_PARSER_MISMATCH"
                if str(exc).startswith("EXACT_PARSER_MISMATCH")
                else "TYPED_ENGINE_INTEGRITY_ERROR"
            )
            return self._blocked(
                **common,
                reason_code=code,
                reason="The typed engine failed its parser or adapter identity check.",
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed adapter boundary
            return self._blocked(
                **common,
                reason_code="TYPED_ENGINE_FAULTED",
                reason=f"The typed engine raised an unexpected {type(exc).__name__}; no target SQL was emitted.",
            )

        typed_source = getattr(typed_result, "source_profile", None)
        typed_target = getattr(typed_result, "target_profile", None)
        if (
            getattr(typed_source, "id", None) != source_profile
            or getattr(typed_target, "id", None) != target_profile
            or getattr(typed_source, "dialect", None) != _CORE_DIALECTS[src]
            or getattr(typed_target, "dialect", None) != _CORE_DIALECTS[tgt]
        ):
            return self._blocked(
                **common,
                reason_code="TYPED_ENGINE_IDENTITY_MISMATCH",
                reason="Typed engine result identity does not match the requested route.",
            )

        typed_payload = typed_result.to_dict(include_sql=True)
        verification = dict(typed_payload.get("verification", {}))
        diagnostics = list(typed_payload.get("diagnostics", []))
        warning_text = [
            f"{item.get('code', 'UNKNOWN')}: {item.get('message', '')}"
            for item in diagnostics
            if isinstance(item, dict)
        ]
        if getattr(typed_result, "state", None) != "SYNTAX_READY" or getattr(typed_result, "target_sql", None) is None:
            first = diagnostics[0] if diagnostics and isinstance(diagnostics[0], dict) else {}
            return self._blocked(
                **common,
                reason_code=str(first.get("code", "TYPED_TRANSLATION_BLOCKED")),
                reason=str(first.get("message", "The typed SQL engine blocked this route.")),
                warnings=warning_text,
                verification=verification,
            )

        semantic_blocker = _post_emission_blocker(
            getattr(typed_result, "statements", ()),
            source_dialect=_CORE_DIALECTS[src],
            target_dialect=_CORE_DIALECTS[tgt],
        )
        if semantic_blocker is not None:
            reason_code, reason = semantic_blocker
            verification["gatewaySemanticGuard"] = "FAILED"
            verification["resultEquivalence"] = "NOT_RUN"
            return self._blocked(
                **common,
                reason_code=reason_code,
                reason=reason,
                warnings=warning_text,
                verification=verification,
            )

        metadata = getattr(typed_result, "metadata", {})
        traces = metadata.get("ruleTrace", []) if isinstance(metadata, dict) else []
        transformed = [
            str(trace["ruleId"])
            for trace in traces
            if isinstance(trace, dict) and isinstance(trace.get("ruleId"), str)
        ]
        transformed = list(dict.fromkeys(transformed))
        target_sql = str(typed_result.target_sql)
        verification["gatewaySemanticGuard"] = "PASSED"
        receipt_payload = {
            "sourceProfile": source_profile,
            "targetProfile": target_profile,
            "sourceDigest": getattr(typed_result, "source_digest", None),
            "targetDigest": getattr(typed_result, "target_digest", None),
            "status": "SYNTAX_READY",
            "semanticEquivalence": "NOT_VERIFIED",
            "verification": verification,
        }
        return SqlTranspileResult(
            source_dialect=src,
            target_dialect=tgt,
            source_sql=normalized_sql,
            target_sql=target_sql,
            status="SYNTAX_READY",
            source_profile=source_profile,
            target_profile=target_profile,
            transformed_constructs=transformed,
            warnings=warning_text,
            semantic_equivalence="NOT_VERIFIED",
            reason_code="RUNTIME_EQUIVALENCE_NOT_RUN",
            reason=(
                "Typed parse, emission, and target reparse passed; source/target execution, "
                "result and error equivalence, performance, security, and certification remain NOT_RUN."
            ),
            verification=verification,
            merkle_receipt=_receipt(receipt_payload),
        )

    def diff_schemas(self, source_ddl: str, target_ddl: str) -> dict[str, Any]:
        """Compare declared table identities without claiming schema equivalence."""

        src_tables = set(re.findall(r"CREATE\s+TABLE\s+([a-zA-Z0-9_]+)", source_ddl, re.IGNORECASE))
        tgt_tables = set(re.findall(r"CREATE\s+TABLE\s+([a-zA-Z0-9_]+)", target_ddl, re.IGNORECASE))
        added_tables = sorted(tgt_tables - src_tables)
        removed_tables = sorted(src_tables - tgt_tables)
        common_tables = sorted(src_tables & tgt_tables)
        return {
            "source_tables_count": len(src_tables),
            "target_tables_count": len(tgt_tables),
            "added_tables": added_tables,
            "removed_tables": removed_tables,
            "common_tables": common_tables,
            "status": "NO_REMOVALS_DETECTED" if not removed_tables else "BREAKING_REMOVALS_DETECTED",
            "semantic_equivalence": "NOT_VERIFIED",
        }


def get_supported_dialects() -> list[dict[str, str]]:
    return [
        {
            "id": "oracle",
            "name": "Oracle Database",
            "type": "commercial",
            "translation_status": "EXACT_PROFILE_REQUIRED",
        },
        {
            "id": "postgres",
            "name": "PostgreSQL",
            "type": "open_source",
            "translation_status": "EXACT_PROFILE_REQUIRED",
        },
        {
            "id": "mysql",
            "name": "MySQL",
            "type": "open_source",
            "translation_status": "EXACT_PROFILE_REQUIRED",
        },
        {
            "id": "sqlserver",
            "name": "Microsoft SQL Server",
            "type": "commercial",
            "translation_status": "EXACT_PROFILE_REQUIRED",
        },
        {"id": "dm8", "name": "Dameng DM8", "type": "chinadb", "translation_status": "SPEC_ONLY"},
        {
            "id": "kingbasees",
            "name": "KingbaseES",
            "type": "chinadb",
            "translation_status": "SPEC_ONLY",
        },
        {"id": "tidb", "name": "PingCAP TiDB", "type": "chinadb", "translation_status": "SPEC_ONLY"},
        {
            "id": "oceanbase-oracle",
            "name": "OceanBase Oracle Mode",
            "type": "chinadb",
            "translation_status": "SPEC_ONLY",
        },
        {
            "id": "oceanbase-mysql",
            "name": "OceanBase MySQL Mode",
            "type": "chinadb",
            "translation_status": "SPEC_ONLY",
        },
        {"id": "opengauss", "name": "openGauss", "type": "chinadb", "translation_status": "SPEC_ONLY"},
        {
            "id": "highgo-hgdb",
            "name": "HighGo HGDB",
            "type": "chinadb",
            "translation_status": "SPEC_ONLY",
        },
        {"id": "gbase", "name": "GBase family", "type": "chinadb", "translation_status": "SPEC_ONLY"},
        {"id": "goldendb", "name": "GoldenDB", "type": "chinadb", "translation_status": "SPEC_ONLY"},
    ]
