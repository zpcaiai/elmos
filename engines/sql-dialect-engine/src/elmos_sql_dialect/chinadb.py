"""The fail-closed ChinaDB target registry used by the SQL coverage ledger.

The database-data engine owns the full commercial migration package.  The
small registry here intentionally mirrors only its target identities so the
standalone SQL scanner can account for every domestic target without turning
compatibility labels into dialect aliases.  A target becomes an automatic
translation target only after an exact versioned adapter, target parser and
independent evidence are registered; none of those are present in this
package today.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ChinaDbTarget:
    id: str
    label: str
    adapter_id: str
    compatibility_mode_requirement: str

    def to_dict(self) -> dict[str, str]:
        value = asdict(self)
        return {
            "id": value["id"],
            "label": value["label"],
            "adapterId": value["adapter_id"],
            "compatibilityModeRequirement": value["compatibility_mode_requirement"],
            "implementationStatus": "SPEC_ONLY",
            "externalExecution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


# Keep this tuple in the same order as the Batch 31 commercial registry.  The
# order is part of the report's deterministic, diffable output.
CHINADB_TARGETS: tuple[ChinaDbTarget, ...] = (
    ChinaDbTarget("dm8", "DM8", "chinadb.dm8.target-adapter.v1", "native or explicitly selected compatibility mode"),
    ChinaDbTarget(
        "kingbasees",
        "KingbaseES",
        "chinadb.kingbasees.target-adapter.v1",
        "native or explicitly selected compatibility mode",
    ),
    ChinaDbTarget("opengauss", "openGauss", "chinadb.opengauss.target-adapter.v1", "exact database compatibility mode"),
    ChinaDbTarget("tidb", "TiDB", "chinadb.tidb.target-adapter.v1", "exact SQL mode and deployment topology"),
    ChinaDbTarget("gbase-8s", "GBase 8s", "chinadb.gbase-8s.target-adapter.v1", "exact compatibility mode"),
    ChinaDbTarget(
        "gbase-8c",
        "GBase 8c",
        "chinadb.gbase-8c.target-adapter.v1",
        "exact compatibility mode and deployment topology",
    ),
    ChinaDbTarget(
        "gbase-8a",
        "GBase 8a",
        "chinadb.gbase-8a.target-adapter.v1",
        "exact analytical compatibility and deployment mode",
    ),
    ChinaDbTarget(
        "highgo-hgdb",
        "HighGo / HGDB",
        "chinadb.highgo-hgdb.target-adapter.v1",
        "native or explicitly selected compatibility mode",
    ),
    ChinaDbTarget(
        "oceanbase-oracle",
        "OceanBase Oracle-compatible mode",
        "chinadb.oceanbase-oracle.target-adapter.v1",
        "Oracle-compatible tenant mode",
    ),
    ChinaDbTarget(
        "oceanbase-mysql",
        "OceanBase MySQL-compatible mode",
        "chinadb.oceanbase-mysql.target-adapter.v1",
        "MySQL-compatible tenant mode and SQL mode",
    ),
    ChinaDbTarget(
        "gaussdb-oracle",
        "GaussDB Oracle-compatible mode",
        "chinadb.gaussdb-oracle.target-adapter.v1",
        "Oracle-compatible deployment mode",
    ),
    ChinaDbTarget(
        "gaussdb-m",
        "GaussDB M-compatible mode",
        "chinadb.gaussdb-m.target-adapter.v1",
        "M-compatible deployment mode and SQL mode",
    ),
    ChinaDbTarget(
        "goldendb",
        "GoldenDB",
        "chinadb.goldendb.target-adapter.v1",
        "exact product, compatibility, and deployment mode",
    ),
)

CHINADB_EXCLUDED_TARGET_IDS = ("polardb", "polardb-x", "tdsql")
CHINADB_SOURCE_FAMILY_COUNT = 6
CHINADB_PLANNED_ROUTE_COUNT = CHINADB_SOURCE_FAMILY_COUNT * len(CHINADB_TARGETS)


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


def chinadb_capabilities() -> dict[str, Any]:
    """Return target metadata without manufacturing renderer evidence."""

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
        "implementationStatus": "SPEC_ONLY",
        "externalExecution": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "targetSqlEmission": "PROHIBITED_UNTIL_EXACT_ADAPTER_AND_EVIDENCE",
        "claim": (
            "Domestic target identity and route-disposition accounting only; "
            "no target renderer, target execution, equivalence, or certification evidence."
        ),
    }
