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

from .models import Dialect, RouteError

_ORACLE = MappingProxyType(
    {
        "oracle-compatible-explicit": Dialect.ORACLE,
        "oracle-compatible": Dialect.ORACLE,
    }
)
_POSTGRES = MappingProxyType(
    {
        "pg-compatible-explicit": Dialect.POSTGRES,
        "postgresql-compatible": Dialect.POSTGRES,
        "a-compatible": Dialect.POSTGRES,
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
    _target("dm8", "DM8", "native or explicitly selected compatibility mode", _ORACLE),
    _target(
        "kingbasees",
        "KingbaseES",
        "native or explicitly selected compatibility mode",
        _KINGBASE,
    ),
    _target("opengauss", "openGauss", "exact database compatibility mode", _POSTGRES),
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
