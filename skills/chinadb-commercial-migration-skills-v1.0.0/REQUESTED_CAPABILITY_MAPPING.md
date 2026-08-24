# Requested Commercial Capability -> Skills Mapping

| Requested capability | Primary skills | Supporting skills | Production acceptance |
|---|---|---|---|
| Data movement `$` | `04-data-movement-cdc` | 12, 14, 64, target adapters | E2 + cutover CDC gap = 0 + reconciliation |
| DDL automatic conversion `$$` | `05-ddl-auto-conversion` | 02, 03, target adapters | E1 compile/apply + catalog diff + E2 constraints |
| SQL automatic conversion `$$$` | `06-sql-auto-conversion` | 02, 03, 09, target adapters | E3 differential semantics on critical corpus |
| PL/SQL / T-SQL conversion `$$$$` | `07-plsql-tsql-conversion` | Oracle/T-SQL sources, app adapters, targets | compile/native OR lift-to-app + E3 transaction/side effects |
| Application code auto-refactor `$$$$$` | `08-application-code-auto-refactor` | 30–34 | clean build + integration + E3 app-visible behavior |
| Behavioral equivalence `$$$$$` | `09-behavior-equivalence-verification` | 61 fixture mutation tests | E3: zero P0/P1 mismatch, critical scenarios 100% |
| Performance equivalence `$$$$$` | `10-performance-equivalence-verification` | 62 benchmark lab, target plan hooks | E4 route-specific SLO policy |
| Automatic repair `$$$$$$` | `11-guarded-auto-repair` | 03 mutations, 09/10 verification | patch must rerun affected gates; high-risk requires approval |
| Production migration certification `$$$$$$` | `13-production-migration-certification` | 12 cutover, 14 security, 15 evidence | E1–E5 certificate tied to exact release candidate |

## Target coverage

Target adapter skills: DM8, KingbaseES, openGauss, TiDB, GBase 8s, GBase 8c, GBase 8a, HighGo/HGDB, OceanBase Oracle mode, OceanBase MySQL mode, GaussDB Oracle-compatible, GaussDB M-compatible, GoldenDB.

Excluded by request: PolarDB, PolarDB-X, TDSQL.
