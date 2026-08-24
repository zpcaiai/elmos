# Vendor Capability Baseline Notes — 2026-08-13

These notes are implementation assumptions to be re-validated against exact deployed versions. They are not substitutes for target capability discovery.

- **DM8 / Dameng:** official DM8 documentation describes heterogeneous migration tooling and DTS/SQLark; Oracle-to-DM guidance includes object/data migration and compatibility considerations.
- **KingbaseES:** official manuals describe KDMS/KDTS and Oracle migration, plus Oracle/MySQL/PostgreSQL/SQL Server compatibility modes in current documentation.
- **openGauss:** current official docs include DataKit migration capabilities; current release notes document Oracle full/incremental/reverse migration and data validation/replay comparison capabilities.
- **TiDB:** official docs describe strong MySQL compatibility and TiDB DM for MySQL-compatible migration; stored procedures/functions are not a supported compatibility feature, so procedural logic may need decomposition/lift-to-app.
- **GBase 8s:** official GBase materials describe Oracle-compatible object coverage, MTK migration and RTSync real-time/reverse synchronization.
- **GBase 8a:** official materials document Oracle extraction/migration tooling such as orato8a and MPP/analytical migration scenarios.
- **HighGo / HGDB:** official documentation lists HgMigration tooling; HighGo's Oracle compatibility work and IvorySQL lineage are useful context, but enterprise HGDB capabilities must be discovered separately by version.
- **OceanBase:** current official OMS documentation supports Oracle schema/full/incremental migration to Oracle-compatible tenants; OceanBase documents Oracle-compatible SQL/procedural coverage and explicit incompatibilities; OMA provides assessment/application reconstruction suggestions.
- **GaussDB:** current Huawei UGO documentation covers Oracle-to-GaussDB conversion/assessment and compatibility modes; detailed conversion docs include known unsupported constructs such as ANYDATA and advanced-package mappings.
- **GoldenDB:** official product materials emphasize financial/telecom core workloads. Because public fine-grained syntax/tool capability details vary, the adapter requires a deployment-specific capability snapshot before enabling conversion rules.

Source domains used during package preparation: eco.dameng.com, help.kingbase.com.cn, docs.opengauss.org, docs.pingcap.com, gbase.cn, highgo.com, oceanbase.com, support.huaweicloud.com, goldendb.com.
