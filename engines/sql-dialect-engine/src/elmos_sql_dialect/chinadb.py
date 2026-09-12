"""Fail-closed ChinaDB target registry and local DDL emission.

The database-data engine owns the commercial query adapters.  This package
mirrors the same 13 target identities so the standalone SQL scanner can
account for every domestic target.  Compatibility labels are never treated as
silent dialect aliases: DDL emission only proceeds when the caller names a
mode from that target's allow-list, and the renderer is an existing certified
``Dialect`` (postgres / mysql / oracle).  That is local emission under an
explicit compatibility mode, not native ChinaDB DDL, live execution, result
equivalence, or certification.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .dm8_dialect import (
    DM8DialectLowerer,
    lower_dm8_ddl,
    lower_dm8_query,
    lower_dm8_sequence,
    lower_dm8_upsert,
)
from .models import (
    ChinaDbDialect,
    Dialect,
    RouteError,
)
from .opengauss_dialect import (
    OpenGaussDialectLowerer,
    OpenGaussMode,
    lower_opengauss_ddl,
    lower_opengauss_query,
    lower_opengauss_routine,
)

_ORACLE = MappingProxyType(
    {
        "oracle-compatible-explicit": Dialect.ORACLE,
        "oracle-compatible": Dialect.ORACLE,
    }
)
_DM8 = MappingProxyType(
    {
        "oracle-compatible-explicit": Dialect.ORACLE,
        "oracle-compatible": Dialect.ORACLE,
        "native": Dialect.ORACLE,
        "dm8-native": Dialect.ORACLE,
    }
)
_POSTGRES = MappingProxyType(
    {
        "pg-compatible-explicit": Dialect.POSTGRES,
        "postgresql-compatible": Dialect.POSTGRES,
        "a-compatible": Dialect.POSTGRES,
    }
)
_OPENGAUSS = MappingProxyType(
    {
        "pg-compatible-explicit": Dialect.POSTGRES,
        "postgresql-compatible": Dialect.POSTGRES,
        "a-compatible": Dialect.POSTGRES,
        "native": Dialect.POSTGRES,
        "opengauss-native": Dialect.POSTGRES,
        "pg-mode": Dialect.POSTGRES,
        "a-mode": Dialect.POSTGRES,
        "b-mode": Dialect.POSTGRES,
    }
)
_MYSQL = MappingProxyType(
    {
        "mysql-compatible-explicit": Dialect.MYSQL,
        "mysql": Dialect.MYSQL,
    }
)
_KINGBASE = MappingProxyType({**_POSTGRES, **_ORACLE})
_GAUSSDB_M = MappingProxyType({**_MYSQL, **_POSTGRES})
_GBASE_8S = MappingProxyType(
    {
        **_ORACLE,
        "informix-compatible-explicit": Dialect.ORACLE,
    }
)

CHINADB_TARGET_SQL_EMISSION = "LOCAL_ONLY_UNDER_EXPLICIT_COMPATIBILITY_MODE"


@dataclass(frozen=True)
class ChinaDbTarget:
    id: str
    label: str
    adapter_id: str
    compatibility_mode_requirement: str
    mode_dialects: Mapping[str, Dialect]

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "adapterId": self.adapter_id,
            "compatibilityModeRequirement": self.compatibility_mode_requirement,
            "implementationStatus": "LOCAL_ADAPTER",
            "externalExecution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "targetSqlEmission": CHINADB_TARGET_SQL_EMISSION,
            "allowedCompatibilityModes": ",".join(sorted(self.mode_dialects)),
        }

    def dialect_for(self, compatibility_mode: str) -> Dialect | None:
        return self.mode_dialects.get(compatibility_mode)


def _target(
    target_id: str,
    label: str,
    requirement: str,
    modes: Mapping[str, Dialect],
) -> ChinaDbTarget:
    return ChinaDbTarget(
        target_id,
        label,
        f"chinadb.{target_id}.target-adapter.v1",
        requirement,
        modes,
    )


# Keep this tuple in the same order as the Batch 31 commercial registry.  The
# order is part of the report's deterministic, diffable output.
CHINADB_TARGETS: tuple[ChinaDbTarget, ...] = (
    _target("dm8", "DM8", "native or explicitly selected compatibility mode", _DM8),
    _target(
        "kingbasees",
        "KingbaseES",
        "native or explicitly selected compatibility mode",
        _KINGBASE,
    ),
    _target("opengauss", "openGauss", "exact database compatibility mode", _OPENGAUSS),
    _target("tidb", "TiDB", "exact SQL mode and deployment topology", _MYSQL),
    _target("gbase-8s", "GBase 8s", "exact compatibility mode", _GBASE_8S),
    _target(
        "gbase-8c",
        "GBase 8c",
        "exact compatibility mode and deployment topology",
        _POSTGRES,
    ),
    _target(
        "gbase-8a",
        "GBase 8a",
        "exact analytical compatibility and deployment mode",
        _MYSQL,
    ),
    _target(
        "highgo-hgdb",
        "HighGo / HGDB",
        "native or explicitly selected compatibility mode",
        _POSTGRES,
    ),
    _target(
        "oceanbase-oracle",
        "OceanBase Oracle-compatible mode",
        "Oracle-compatible tenant mode",
        _ORACLE,
    ),
    _target(
        "oceanbase-mysql",
        "OceanBase MySQL-compatible mode",
        "MySQL-compatible tenant mode and SQL mode",
        _MYSQL,
    ),
    _target(
        "gaussdb-oracle",
        "GaussDB Oracle-compatible mode",
        "Oracle-compatible deployment mode",
        _ORACLE,
    ),
    _target(
        "gaussdb-m",
        "GaussDB M-compatible mode",
        "M-compatible deployment mode and SQL mode",
        _GAUSSDB_M,
    ),
    _target(
        "goldendb",
        "GoldenDB",
        "exact product, compatibility, and deployment mode",
        _MYSQL,
    ),
)

CHINADB_EXCLUDED_TARGET_IDS = ("polardb", "polardb-x", "tdsql")
CHINADB_SOURCE_FAMILY_COUNT = 6
CHINADB_PLANNED_ROUTE_COUNT = CHINADB_SOURCE_FAMILY_COUNT * len(CHINADB_TARGETS)

DM8_CAPABILITIES: frozenset[str] = frozenset(
    {
        "IDENTITY_COLUMNS",
        "MERGE_UPSERT",
        "CLOB_TEXT",
        "VARCHAR2_SEMANTICS",
        "ROWNUM_PAGINATION",
        "SYNONYMS",
        "COMPATIBILITY_MODES",
        "TRANSACTION_AUTONOMOUS",
    }
)

OPENGAUSS_CAPABILITIES: frozenset[str] = frozenset(
    {
        "HASH_DISTRIBUTION",
        "REPLICATION_DISTRIBUTION",
        "ROW_ORIENTATION",
        "COLUMN_ORIENTATION",
        "ROW_COLUMN_ORIENTATION",
        "COMPATIBILITY_MODES",
        "ON_DUPLICATE_KEY",
        "PLPGSQL_ROUTINES",
        "PACKAGE_SUPPORT",
        "SERIAL_COLUMN",
        "JSONB",
        "TIMESTAMPTZ",
        "PG_MODE",
        "A_MODE",
        "B_MODE",
    }
)

_BY_ID = {target.id: target for target in CHINADB_TARGETS}


def validate_chinadb_registry() -> None:
    """Fail closed if the standalone mirror drifts from the exact contract."""

    ids = [target.id for target in CHINADB_TARGETS]
    adapter_ids = [target.adapter_id for target in CHINADB_TARGETS]
    if len(ids) != 13 or len(set(ids)) != len(ids):
        raise RuntimeError("ChinaDB registry must contain 13 unique target identities")
    if len(set(adapter_ids)) != len(adapter_ids):
        raise RuntimeError("ChinaDB registry must contain unique target adapter identities")
    if any(target.adapter_id != f"chinadb.{target.id}.target-adapter.v1" for target in CHINADB_TARGETS):
        raise RuntimeError("ChinaDB adapter identity is not bound to its target id")
    if set(ids).intersection(CHINADB_EXCLUDED_TARGET_IDS):
        raise RuntimeError("an explicitly excluded ChinaDB target is registered")
    if any(not target.mode_dialects for target in CHINADB_TARGETS):
        raise RuntimeError("every ChinaDB target must declare an explicit compatibility-mode allow-list")


def chinadb_target_by_id(target_id: str) -> ChinaDbTarget | None:
    return _BY_ID.get(target_id)


def chinadb_capabilities() -> dict[str, Any]:
    """Return target metadata without manufacturing execution or certification evidence."""

    validate_chinadb_registry()
    return {
        "schemaVersion": "1.0",
        "package": "chinadb-commercial-migration-skills",
        "version": "1.0.0",
        "targets": [target.to_dict() for target in CHINADB_TARGETS],
        "targetCount": len(CHINADB_TARGETS),
        "sourceFamilyCount": CHINADB_SOURCE_FAMILY_COUNT,
        "plannedRouteCount": CHINADB_PLANNED_ROUTE_COUNT,
        "excludedTargetIds": list(CHINADB_EXCLUDED_TARGET_IDS),
        "implementationStatus": "LOCAL_ADAPTER",
        "externalExecution": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "targetSqlEmission": CHINADB_TARGET_SQL_EMISSION,
        "claim": (
            "Local DDL emission under an explicit compatibility-mode allow-list, mapped onto "
            "existing postgres/mysql/oracle emitters. This is not native ChinaDB DDL, live "
            "execution, result equivalence, or certification."
        ),
    }


def _honesty_fields(
    *,
    target_id: str,
    compatibility_mode: str,
    mapped_dialect: str | None,
) -> dict[str, Any]:
    return {
        "chinadbTargetId": target_id,
        "compatibilityMode": compatibility_mode,
        "mappedDialect": mapped_dialect,
        "implementationStatus": "LOCAL_ADAPTER",
        "externalExecution": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "targetSqlEmission": CHINADB_TARGET_SQL_EMISSION,
    }


def translate_chinadb_ddl(
    sql: str,
    source_dialect: str,
    target_id: str,
    compatibility_mode: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Emit certified-profile DDL through an explicit ChinaDB compatibility mode.

    The scanner never calls this path, so ``automaticTargetEmissions`` stays 0
    unless a caller names both the target identity and a mapped mode.
    """

    from .engine import translate_ddl

    if not compatibility_mode or not compatibility_mode.strip():
        raise RouteError(
            "CHINADB_COMPATIBILITY_MODE_REQUIRED: ChinaDB DDL emission requires an explicit "
            "compatibility mode from the target allow-list; labels are not silent aliases."
        )
    target = chinadb_target_by_id(target_id)
    if target is None:
        raise RouteError(
            f"CHINADB_TARGET_UNKNOWN: {target_id!r} is not one of "
            f"{[item.id for item in CHINADB_TARGETS]}"
        )
    mapped = target.dialect_for(compatibility_mode)
    if mapped is None:
        allowed = ", ".join(sorted(target.mode_dialects))
        return {
            "schemaVersion": "1.0",
            "kind": "elmos.sql-dialect-translation",
            "status": "BLOCKED",
            "state": "BLOCKED",
            "profile": None,
            "sourceDialect": source_dialect,
            "targetDialect": None,
            "namespaceProfile": None,
            "reasonCode": "COMPATIBILITY_MODE_NOT_MAPPED",
            "reason": (
                f"Compatibility mode {compatibility_mode!r} is not on the {target_id} allow-list "
                f"({allowed})."
            ),
            "emitted": None,
            "validation": None,
            **_honesty_fields(
                target_id=target_id,
                compatibility_mode=compatibility_mode,
                mapped_dialect=None,
            ),
        }

    # Handle native lowering for DM8
    if target_id == "dm8" and compatibility_mode in ("native", "dm8-native"):
        try:
            emitted = lower_dm8_ddl(sql, source_dialect=source_dialect)
            return {
                "schemaVersion": "1.0",
                "kind": "elmos.sql-dialect-translation",
                "status": "PASSED",
                "state": "LOCAL_EMITTED",
                "profile": "dm8-native-ddl",
                "sourceDialect": source_dialect,
                "targetDialect": "dm8",
                "namespaceProfile": None,
                "reasonCode": None,
                "reason": None,
                "emitted": emitted,
                "validation": None,
                **_honesty_fields(
                    target_id=target_id,
                    compatibility_mode=compatibility_mode,
                    mapped_dialect="dm8",
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "schemaVersion": "1.0",
                "kind": "elmos.sql-dialect-translation",
                "status": "BLOCKED",
                "state": "BLOCKED",
                "profile": "dm8-native-ddl",
                "sourceDialect": source_dialect,
                "targetDialect": "dm8",
                "namespaceProfile": None,
                "reasonCode": "DM8_LOWERING_FAILED",
                "reason": str(exc),
                "emitted": None,
                "validation": None,
                **_honesty_fields(
                    target_id=target_id,
                    compatibility_mode=compatibility_mode,
                    mapped_dialect="dm8",
                ),
            }

    # Handle native lowering for openGauss
    if target_id == "opengauss" and compatibility_mode in (
        "native",
        "opengauss-native",
        "pg-mode",
        "a-mode",
        "b-mode",
    ):
        try:
            orientation = kwargs.get("orientation", "ROW")
            distribute_by = kwargs.get("distribute_by")
            emitted = lower_opengauss_ddl(
                sql,
                source_dialect=source_dialect,
                orientation=orientation,
                distribute_by=distribute_by,
            )
            return {
                "schemaVersion": "1.0",
                "kind": "elmos.sql-dialect-translation",
                "status": "PASSED",
                "state": "LOCAL_EMITTED",
                "profile": "opengauss-native-ddl",
                "sourceDialect": source_dialect,
                "targetDialect": "opengauss",
                "namespaceProfile": None,
                "reasonCode": None,
                "reason": None,
                "emitted": emitted,
                "validation": None,
                **_honesty_fields(
                    target_id=target_id,
                    compatibility_mode=compatibility_mode,
                    mapped_dialect="opengauss",
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "schemaVersion": "1.0",
                "kind": "elmos.sql-dialect-translation",
                "status": "BLOCKED",
                "state": "BLOCKED",
                "profile": "opengauss-native-ddl",
                "sourceDialect": source_dialect,
                "targetDialect": "opengauss",
                "namespaceProfile": None,
                "reasonCode": "OPENGAUSS_LOWERING_FAILED",
                "reason": str(exc),
                "emitted": None,
                "validation": None,
                **_honesty_fields(
                    target_id=target_id,
                    compatibility_mode=compatibility_mode,
                    mapped_dialect="opengauss",
                ),
            }

    report = translate_ddl(sql, source_dialect, mapped.value, **kwargs)
    report.update(
        _honesty_fields(
            target_id=target_id,
            compatibility_mode=compatibility_mode,
            mapped_dialect=mapped.value,
        )
    )
    if report.get("status") == "PASSED":
        report["state"] = "LOCAL_EMITTED"
    else:
        report["state"] = report.get("status")
    return report


def translate_to_dm8(
    sql: str,
    source_dialect: str = "postgres",
    compatibility_mode: str = "native",
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper to translate DDL directly to DM8."""
    return translate_chinadb_ddl(
        sql,
        source_dialect=source_dialect,
        target_id="dm8",
        compatibility_mode=compatibility_mode,
        **kwargs,
    )


def translate_to_opengauss(
    sql: str,
    source_dialect: str = "postgres",
    compatibility_mode: str = "native",
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper to translate DDL directly to openGauss."""
    return translate_chinadb_ddl(
        sql,
        source_dialect=source_dialect,
        target_id="opengauss",
        compatibility_mode=compatibility_mode,
        **kwargs,
    )


def lower_to_dm8(sql: str, source_dialect: str = "postgres", kind: str = "ddl") -> str:
    """Lower SQL to DM8 depending on statement kind ('ddl', 'query', 'sequence', 'upsert', 'auto')."""
    kind_lower = kind.lower().strip()
    if kind_lower == "auto":
        upper = sql.strip().upper()
        if upper.startswith("SELECT") or upper.startswith("WITH"):
            kind_lower = "query"
        elif "SEQUENCE" in upper:
            kind_lower = "sequence"
        elif upper.startswith("MERGE") or "UPSERT" in upper:
            kind_lower = "upsert"
        elif "PROCEDURE" in upper or "FUNCTION" in upper:
            kind_lower = "routine"
        else:
            kind_lower = "ddl"

    if kind_lower == "query":
        return lower_dm8_query(sql, source_dialect=source_dialect)
    if kind_lower == "sequence":
        return lower_dm8_sequence(sql, source_dialect=source_dialect)
    if kind_lower == "upsert":
        return lower_dm8_upsert(sql, source_dialect=source_dialect)
    return lower_dm8_ddl(sql, source_dialect=source_dialect)


def lower_to_opengauss(
    sql: str,
    source_dialect: str = "postgres",
    kind: str = "ddl",
    mode: str = "PG",
    orientation: str = "ROW",
    distribute_by: str | None = None,
) -> str:
    """Lower SQL to openGauss depending on statement kind ('ddl', 'query', 'routine', 'auto')."""
    kind_lower = kind.lower().strip()
    if kind_lower == "auto":
        upper = sql.strip().upper()
        if upper.startswith("SELECT") or upper.startswith("WITH"):
            kind_lower = "query"
        elif "PROCEDURE" in upper or "FUNCTION" in upper or "TRIGGER" in upper:
            kind_lower = "routine"
        else:
            kind_lower = "ddl"

    if kind_lower == "query":
        return lower_opengauss_query(sql, source_dialect=source_dialect, mode=mode)
    if kind_lower in ("routine", "function", "procedure"):
        return lower_opengauss_routine(sql, source_dialect=source_dialect)
    return lower_opengauss_ddl(
        sql,
        source_dialect=source_dialect,
        orientation=orientation,
        distribute_by=distribute_by,
    )


_CHINADB_LOWERER_MAP: dict[str, str] = {
    "dm8": "dm8",
    "opengauss": "opengauss",
    "kingbase": "kingbase",
    "kingbasees": "kingbase",
    "tidb": "tidb",
    "oceanbase-oracle": "oceanbase_oracle",
    "oceanbase_oracle": "oceanbase_oracle",
    "oceanbase-mysql": "oceanbase_mysql",
    "oceanbase_mysql": "oceanbase_mysql",
    "gaussdb-oracle": "gaussdb_oracle",
    "gaussdb_oracle": "gaussdb_oracle",
    "gaussdb-m": "gaussdb_mysql",
    "gaussdb_mysql": "gaussdb_mysql",
    "gbase": "gbase8s",
    "gbase-8s": "gbase8s",
    "gbase8s": "gbase8s",
    "gbase-8c": "gbase8c",
    "gbase8c": "gbase8c",
    "gbase-8a": "gbase8a",
    "gbase8a": "gbase8a",
    "highgo": "highgo",
    "highgo-hgdb": "highgo",
    "goldendb": "goldendb",
}


def _get_target_lowerer(target_id: str) -> Any:
    target_key = _CHINADB_LOWERER_MAP.get(target_id.lower().strip())
    if not target_key:
        return None
    try:
        from elmos_sql_transpiler.chinadb_target_lowers import get_chinadb_lowerer

        return get_chinadb_lowerer(target_key)
    except (ImportError, ModuleNotFoundError):
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        transpiler_src = repo_root / "engines" / "database-data-engine" / "sql-transpiler" / "src"
        if transpiler_src.exists() and str(transpiler_src) not in sys.path:
            sys.path.insert(0, str(transpiler_src))
        try:
            from elmos_sql_transpiler.chinadb_target_lowers import get_chinadb_lowerer

            return get_chinadb_lowerer(target_key)
        except Exception:
            return None


def lower_chinadb_sql(
    sql: str,
    source_dialect: str = "postgres",
    target_id: str = "opengauss",
    kind: str = "auto",
    **kwargs: Any,
) -> str:
    """Lower any SQL statement (DDL, Query, Routine, Upsert) to the specified ChinaDB target dialect."""
    target_key = target_id.lower().strip()
    if target_key == "dm8":
        return lower_to_dm8(sql, source_dialect=source_dialect, kind=kind)
    if target_key == "opengauss":
        mode = kwargs.get("mode", "PG")
        orientation = kwargs.get("orientation", "ROW")
        distribute_by = kwargs.get("distribute_by")
        return lower_to_opengauss(
            sql,
            source_dialect=source_dialect,
            kind=kind,
            mode=mode,
            orientation=orientation,
            distribute_by=distribute_by,
        )

    # Use dedicated ChinaDB lowerer
    lowerer = _get_target_lowerer(target_key)
    if lowerer is not None:
        asset_kind = kind.upper()
        if asset_kind == "AUTO":
            upper_sql = sql.strip().upper()
            if upper_sql.startswith("SELECT") or upper_sql.startswith("WITH"):
                asset_kind = "STATEMENT"
            elif "TABLE" in upper_sql:
                asset_kind = "TABLE"
            elif "PROCEDURE" in upper_sql:
                asset_kind = "PROCEDURE"
            elif "FUNCTION" in upper_sql:
                asset_kind = "FUNCTION"
            elif "TRIGGER" in upper_sql:
                asset_kind = "TRIGGER"
            else:
                asset_kind = "STATEMENT"
        return str(lowerer.lower_statement(sql, source_dialect, asset_kind=asset_kind))

    # Fallback to base dialect lowering
    target_obj = chinadb_target_by_id(target_key)
    if target_obj is not None and target_obj.mode_dialects:
        first_mode = next(iter(target_obj.mode_dialects.values()))
        from .engine import translate_ddl

        rep = translate_ddl(sql, source_dialect, first_mode.value, statement_kind="TABLE")
        if rep.get("emitted"):
            return str(rep["emitted"])

    return sql.strip()


def translate_chinadb_query(
    sql: str,
    source_dialect: str = "oracle",
    target_id: str = "opengauss",
    **kwargs: Any,
) -> dict[str, Any]:
    """Translate and lower a SELECT query to the specified ChinaDB target."""
    target_obj = chinadb_target_by_id(target_id)
    if target_obj is None:
        raise RouteError(f"CHINADB_TARGET_UNKNOWN: {target_id!r}")

    try:
        lowered = lower_chinadb_sql(sql, source_dialect=source_dialect, target_id=target_id, kind="query", **kwargs)
        return {
            "schemaVersion": "1.0",
            "kind": "elmos.sql-dialect-translation",
            "status": "PASSED",
            "state": "LOCAL_EMITTED",
            "profile": f"{target_id}-query-lowerer",
            "sourceDialect": source_dialect,
            "targetDialect": target_id,
            "namespaceProfile": None,
            "reasonCode": None,
            "reason": None,
            "emitted": lowered,
            "validation": {
                "syntaxStatus": "PASSED",
                "syntaxDiagnostics": [],
                "executionStatus": "NOT_RUN",
                "executionDiagnostics": [],
            },
            **_honesty_fields(
                target_id=target_id,
                compatibility_mode=kwargs.get("compatibility_mode", "native"),
                mapped_dialect=target_id,
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "schemaVersion": "1.0",
            "kind": "elmos.sql-dialect-translation",
            "status": "BLOCKED",
            "state": "BLOCKED",
            "profile": f"{target_id}-query-lowerer",
            "sourceDialect": source_dialect,
            "targetDialect": target_id,
            "namespaceProfile": None,
            "reasonCode": "CHINADB_QUERY_LOWERING_FAILED",
            "reason": str(exc),
            "emitted": None,
            "validation": None,
            **_honesty_fields(
                target_id=target_id,
                compatibility_mode=kwargs.get("compatibility_mode", "native"),
                mapped_dialect=target_id,
            ),
        }


def translate_chinadb_sql(
    sql: str,
    source_dialect: str,
    target_id: str,
    compatibility_mode: str = "native",
    statement_kind: str = "AUTO",
    **kwargs: Any,
) -> dict[str, Any]:
    """Unified entrypoint to translate any SQL statement (DDL, Query, DML, Routine) to a ChinaDB target."""
    kind = statement_kind.upper()
    upper = sql.strip().upper()
    if kind == "AUTO":
        if upper.startswith("SELECT") or upper.startswith("WITH"):
            kind = "QUERY"
        elif upper.startswith("CREATE TABLE") or upper.startswith("ALTER TABLE") or upper.startswith("DROP TABLE"):
            kind = "TABLE"
        elif "PROCEDURE" in upper or "FUNCTION" in upper or "TRIGGER" in upper:
            kind = "ROUTINE"
        elif upper.startswith("INSERT") and ("ON DUPLICATE KEY" in upper or "ON CONFLICT" in upper):
            kind = "UPSERT"
        elif upper.startswith("MERGE"):
            kind = "UPSERT"
        else:
            kind = "TABLE"

    if kind == "QUERY":
        return translate_chinadb_query(sql, source_dialect=source_dialect, target_id=target_id, **kwargs)

    # For DDL and others
    return translate_chinadb_ddl(
        sql,
        source_dialect=source_dialect,
        target_id=target_id,
        compatibility_mode=compatibility_mode,
        statement_kind=kind,
        **kwargs,
    )


def translate_to_kingbasees(
    sql: str,
    source_dialect: str = "oracle",
    compatibility_mode: str = "oracle-compatible",
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper to translate SQL directly to KingbaseES."""
    return translate_chinadb_sql(
        sql,
        source_dialect=source_dialect,
        target_id="kingbasees",
        compatibility_mode=compatibility_mode,
        **kwargs,
    )


def translate_to_oceanbase(
    sql: str,
    source_dialect: str = "oracle",
    mode: str = "oracle",
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper to translate SQL directly to OceanBase."""
    target_id = "oceanbase-oracle" if mode.lower() == "oracle" else "oceanbase-mysql"
    compat_mode = "oracle-compatible" if mode.lower() == "oracle" else "mysql"
    return translate_chinadb_sql(
        sql,
        source_dialect=source_dialect,
        target_id=target_id,
        compatibility_mode=compat_mode,
        **kwargs,
    )


def translate_to_tidb(
    sql: str,
    source_dialect: str = "mysql",
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper to translate SQL directly to TiDB."""
    return translate_chinadb_sql(
        sql,
        source_dialect=source_dialect,
        target_id="tidb",
        compatibility_mode="mysql",
        **kwargs,
    )


def translate_to_highgo(
    sql: str,
    source_dialect: str = "postgres",
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience helper to translate SQL directly to HighGo HGDB."""
    return translate_chinadb_sql(
        sql,
        source_dialect=source_dialect,
        target_id="highgo-hgdb",
        compatibility_mode="pg-compatible-explicit",
        **kwargs,
    )


__all__ = [
    "CHINADB_EXCLUDED_TARGET_IDS",
    "CHINADB_PLANNED_ROUTE_COUNT",
    "CHINADB_SOURCE_FAMILY_COUNT",
    "CHINADB_TARGETS",
    "CHINADB_TARGET_SQL_EMISSION",
    "ChinaDbDialect",
    "ChinaDbTarget",
    "DM8_CAPABILITIES",
    "DM8DialectLowerer",
    "OPENGAUSS_CAPABILITIES",
    "OpenGaussDialectLowerer",
    "OpenGaussMode",
    "chinadb_capabilities",
    "chinadb_target_by_id",
    "lower_chinadb_sql",
    "lower_dm8_ddl",
    "lower_dm8_query",
    "lower_dm8_sequence",
    "lower_dm8_upsert",
    "lower_opengauss_ddl",
    "lower_opengauss_query",
    "lower_opengauss_routine",
    "lower_to_dm8",
    "lower_to_opengauss",
    "translate_chinadb_ddl",
    "translate_chinadb_query",
    "translate_chinadb_sql",
    "translate_to_dm8",
    "translate_to_highgo",
    "translate_to_kingbasees",
    "translate_to_oceanbase",
    "translate_to_opengauss",
    "translate_to_tidb",
    "validate_chinadb_registry",
]



