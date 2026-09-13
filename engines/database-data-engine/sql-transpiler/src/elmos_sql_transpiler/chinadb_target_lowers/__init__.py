"""ChinaDB Dedicated Target Lowerers Package.

Provides 13 industrial target lowerers for domestic database engines:
1. Dameng 8 (DM8)
2. KingbaseES (V8/V9)
3. openGauss / MogDB
4. TiDB (v6/v7)
5. GBase 8s (Informix-based)
6. GBase 8c (Distributed openGauss)
7. GBase 8a (MPP Columnar)
8. HighGo DB (HGDB)
9. OceanBase (Oracle Mode)
10. OceanBase (MySQL Mode)
11. GaussDB (Oracle Mode)
12. GaussDB (MySQL Mode)
13. ZTE GoldenDB
"""

from __future__ import annotations

from elmos_sql_transpiler.chinadb_target_lowers.base_lowerer import (
    ChinaDbTargetLowerer,
    DialectLoweringRule,
)
from elmos_sql_transpiler.chinadb_target_lowers.dm8_lowerer import Dm8TargetLowerer
from elmos_sql_transpiler.chinadb_target_lowers.gaussdb_mysql_lowerer import (
    GaussDbMysqlTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.gaussdb_oracle_lowerer import (
    GaussDbOracleTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.gbase8a_lowerer import (
    GBase8aTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.gbase8c_lowerer import (
    GBase8cTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.gbase8s_lowerer import (
    GBase8sTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.goldendb_lowerer import (
    GoldenDbTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.highgo_lowerer import (
    HighGoTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.kingbase_lowerer import (
    KingbaseTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.oceanbase_mysql_lowerer import (
    OceanBaseMysqlTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.oceanbase_oracle_lowerer import (
    OceanBaseOracleTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.opengauss_lowerer import (
    OpenGaussTargetLowerer,
)
from elmos_sql_transpiler.chinadb_target_lowers.tidb_lowerer import (
    TidbTargetLowerer,
)

_TARGET_REGISTRY: dict[str, type[ChinaDbTargetLowerer]] = {
    "dm8": Dm8TargetLowerer,
    "kingbase": KingbaseTargetLowerer,
    "opengauss": OpenGaussTargetLowerer,
    "tidb": TidbTargetLowerer,
    "gbase8s": GBase8sTargetLowerer,
    "gbase8c": GBase8cTargetLowerer,
    "gbase8a": GBase8aTargetLowerer,
    "highgo": HighGoTargetLowerer,
    "oceanbase_oracle": OceanBaseOracleTargetLowerer,
    "oceanbase_mysql": OceanBaseMysqlTargetLowerer,
    "gaussdb_oracle": GaussDbOracleTargetLowerer,
    "gaussdb_mysql": GaussDbMysqlTargetLowerer,
    "goldendb": GoldenDbTargetLowerer,
}


def get_chinadb_lowerer(target_id: str) -> ChinaDbTargetLowerer:
    """Retrieve an instantiated lowerer for the specified domestic database."""
    target_key = target_id.lower().strip()
    cls = _TARGET_REGISTRY.get(target_key)
    if cls is None:
        raise ValueError(
            f"Unsupported ChinaDB target '{target_id}'. "
            f"Available targets: {list(_TARGET_REGISTRY.keys())}"
        )
    return cls()


def list_supported_targets() -> list[str]:
    """List all 13 supported ChinaDB target IDs."""
    return sorted(_TARGET_REGISTRY.keys())


__all__ = [
    "ChinaDbTargetLowerer",
    "DialectLoweringRule",
    "Dm8TargetLowerer",
    "GBase8aTargetLowerer",
    "GBase8cTargetLowerer",
    "GBase8sTargetLowerer",
    "GaussDbMysqlTargetLowerer",
    "GaussDbOracleTargetLowerer",
    "GoldenDbTargetLowerer",
    "HighGoTargetLowerer",
    "KingbaseTargetLowerer",
    "OceanBaseMysqlTargetLowerer",
    "OceanBaseOracleTargetLowerer",
    "OpenGaussTargetLowerer",
    "TidbTargetLowerer",
    "get_chinadb_lowerer",
    "list_supported_targets",
]
