# Migration Capability Matrix

`Native leverage` describes useful first-party capabilities; it does not remove the need for independent semantic verification.

| Target | Preferred route(s) | Native leverage | Required platform differentiation |
|---|---|---|---|
| DM8 | Oracle/SQL Server -> DM8 | DTS/SQLark can assist assessment, objects and data movement | AST-level SQL/PL conversion, app refactor, diff verification, repair, E1-E5 evidence |
| KingbaseES | Oracle/SQL Server -> KingbaseES | KDMS/KDTS and compatibility modes | unresolved object conversion, application SQL/driver/API rewrite, behavior/perf certification |
| openGauss | Oracle/MySQL/PostgreSQL -> openGauss | DataKit/migration tooling and Oracle migration capabilities | route/version rule packs, app refactor, replay/differential verification, vendor-neutral evidence |
| TiDB | MySQL + Oracle/SQL Server modernization -> TiDB | DM for MySQL-compatible ingestion | stored procedure/function/trigger decomposition into SQL/app/event/scheduler logic; distributed behavior/perf verification |
| GBase 8s | Oracle/DB2/SQL Server -> 8s | MTK/RTSync and Oracle-compatible objects | code-level conversion, app refactor, multi-path consistency, certification |
| GBase 8c | Oracle/PostgreSQL-class workloads -> 8c | vendor migration practices | distributed transaction/sequence/partition semantics, app and performance modernization |
| GBase 8a | Oracle/Teradata-class analytics -> 8a | orato8a / migration tooling | OLAP SQL rewrite, physical design, distribution-key tuning, workload-level equivalence |
| HighGo | Oracle/DB2/SQL Server -> HGDB | HgMigration and Oracle compatibility lineage | application rewrite, unsupported construct remediation, behavior/perf evidence |
| OceanBase Oracle | Oracle -> OceanBase Oracle mode | OMS/OMA + Oracle-compatible mode | application reconstruction, unsupported Oracle edge cases, distributed semantic/perf certification |
| OceanBase MySQL | MySQL/PostgreSQL-class -> OceanBase MySQL mode | OMS + MySQL-compatible mode | SQL/app conversion and distributed behavior/performance validation |
| GaussDB Oracle | Oracle -> GaussDB Oracle-compatible | UGO conversion/assessment | gap repair, app refactor, package/type incompatibility handling, independent certification |
| GaussDB M | MySQL -> GaussDB M-compatible | compatibility settings + migration services | SQL/app semantics and operational/performance certification |
| GoldenDB | Oracle/MySQL-class financial workloads -> GoldenDB | vendor capabilities vary by product/version | strict capability discovery, banking-grade semantic/perf/HA/cutover certification |

## Nine capability layers

Each target adapter MUST connect to all nine shared layers. A target-specific skill may declare a construct `NATIVE`, `REWRITE`, `LIFT_TO_APP`, `EMULATE_WITH_APPROVAL`, or `UNSUPPORTED`. `UNSUPPORTED` never silently degrades.
