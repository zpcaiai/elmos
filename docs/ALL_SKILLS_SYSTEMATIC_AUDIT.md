# ELMOS 全量 4,352 Skills 系统化审计与全景档案

## 1. 审计统计概览

- **技能总数**：`4352` 个标准技能规范 (`SKILL.md`)
- **审计耗时**：`5.13` 秒
- **Frontmatter 格式合规率**：`100.0%` (4,352 / 4,352 均合法具备 YAML Frontmatter)

### 状态分布

| 声明实现状态 | 技能数量 | 占比 |
| :--- | :---: | :---: |
| `DECLARED` | 2320 | 53.3% |
| `VERIFIED` | 587 | 13.5% |
| `production-contract` | 473 | 10.9% |
| `supported` | 198 | 4.5% |
| `SPECIFICATION_IMPORTED` | 196 | 4.5% |
| `BLUEPRINT_IMPORTED` | 100 | 2.3% |
| `IMPLEMENTED` | 72 | 1.7% |
| `PRODUCTION_CODE_COMPLETE` | 60 | 1.4% |
| `directly` | 51 | 1.2% |
| `SPEC_ONLY` | 47 | 1.1% |
| `vocabulary` | 44 | 1.0% |
| `test-ready-not-run` | 35 | 0.8% |
| `PARTIAL_LOCAL_IMPLEMENTED` | 26 | 0.6% |
| `only` | 24 | 0.6% |
| `alone` | 23 | 0.5% |

### 核心批次与类别分布

| 批次 / 类别前缀 | 技能数量 | 核心领域 |
| :--- | :---: | :--- |
| `elmos` | 1324 | Foundry v3 原子技能、多语言语义编译器、多模态摄取与工作台 |
| `pm` | 632 | Precision Migration 高精度迁移内核 B01-B44 |
| `tst` | 117 | 严格测试套件、防作弊验证器与认证门禁 |
| `spring` | 75 | Spring 老项目向 Boot 3/4 现代化核心路线与场景 |
| `legacy` | 63 | 遗留企业系统与传统 Web 现代化 (Struts, Servlet, JSP 等) |
| `etgb` | 50 | 企业级测试治理与基准套件 (ETGB) |
| `chinadb` | 47 | ChinaDB 商业国产数据库迁移套件 (13 国产库) |
| `conv` | 42 | 产品收敛与参考架构蓝图 (Convergence Roadmap P0-P3) |
| `autonomous` | 41 | 自主 QA 与自愈控制平面 (Autonomous QA & Self-Healing) |
| `b37` | 36 | 扩展市场、SDK 与商业闭环 |
| `skill` | 29 | 专用领域工程与领域契约 |
| `gr` | 29 | 黄金路线 (Golden Route) 严苛标准与凭证 |
| `data` | 25 | 专用领域工程与领域契约 |
| `b40` | 24 | 供应链安全与合规审计 |
| `b31` | 22 | 数据库与数据平台迁移 |
| `b34` | 22 | 超大规模代码库组合扩展 |
| `b35` | 22 | 高级正确性与形式化验证 |
| `b38` | 22 | 版本部署矩阵与升级门禁 |
| `b39` | 22 | 全局 SRE 运维与灾备 |
| `b42` | 22 | 被监管 Agent 工厂与自治等级 |
| `b45` | 22 | 成熟产品综合认证终审门禁 |
| `model` | 22 | 专用领域工程与领域契约 |
| `semantic` | 21 | 专用领域工程与领域契约 |
| `b29` | 20 | 多语言转换有向路线 |
| `b30` | 20 | 多框架版本现代化 |
| `b32` | 20 | 大前端与客户端组件现代化 |
| `b33` | 20 | 云原生、IaC 与 DevOps 现代化 |
| `b41` | 20 | 迁移知识飞轮与预测 |
| `b43` | 20 | 产品生命周期与 LTS 兼容性 |
| `b44` | 20 | FinOps 计量计费与经济学模型 |
| `miniapp` | 19 | 小程序跨端生成与适配 |
| `b36` | 18 | IDE、CLI 与开发者工作流 |
| `batch` | 17 | B81-B95 专用与遗留语言 (COBOL, RPG, SAS 等) |
| `cross` | 17 | 专用领域工程与领域契约 |
| `repository` | 17 | 专用领域工程与领域契约 |

## 2. 关键业务线与批次全量技能明细 (节选核心批次)


### 批次 `b31` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b31-canonical-database-ir` | Implement or extend the typed canonical database IR for catalogs, schemas, types, tables, constraint | Skill 1183 | `DECLARED` |
| `b31-constraint-index-partition-migration` | Migrate primary, unique, foreign, check, exclusion constraints, indexes, clustering, partitioning, s | Skill 1187 | `DECLARED` |
| `b31-data-contract-catalog-lineage` | Migrate and govern data contracts, catalog metadata, ownership, classifications, SLOs, schema versio | Skill 1198 | `DECLARED` |
| `b31-data-correctness-performance-cutover` | Validate schema, data, queries, routines, transactions, pipelines, performance, backfill, CDC, dual- | Skill 1201 | `DECLARED` |
| `b31-data-pipeline-migration` | Migrate ETL, ELT, streaming, batch, and orchestration workflows using typed pipeline IR while preser | Skill 1196 | `depends` |
| `b31-data-quality-repair` | Implement data profiling, quality rules, anomaly classification, duplicate and referential checks, m | Skill 1197 | `DECLARED` |
| `b31-database-certification-gate` | Run the conservative Batch 31 certification gate for a database or data-platform pack and emit certi | Skill 1202 | `change` |
| `b31-database-estate-discovery` | Discover and fingerprint database estates, schemas, runtime workloads, security, storage, dependenci | Skill 1182 | `DECLARED` |
| `b31-database-modernization-factory` | Implement and certify a directional, version-specific database or data-platform modernization pack w | Skill 1181 | `requires` |
| `b31-dialect-provider-capability-matrix` | Create and maintain exact database dialect, engine version, edition, extension, driver, and provider | Skill 1184 | `with` |
| `b31-etl-elt-discovery` | Discover ETL, ELT, batch, streaming, orchestration, schedules, sources, sinks, transformations, chec | Skill 1195 | `DECLARED` |
| `b31-orm-database-contract` | Coordinate ORM mappings, existing database schema, migration ownership, query generation, converters | Skill 1194 | `DECLARED` |
| `b31-query-plan-performance` | Compare source and target query plans, cardinality, statistics, indexes, latency, throughput, resour | Skill 1192 | `DECLARED` |
| `b31-query-semantic-migration` | Parse and migrate SQL, JPQL/HQL, ORM-generated, dynamic, and native queries through typed query IR w | Skill 1191 | `DECLARED` |
| `b31-relational-route-pack-certifier` | Implement and certify exact directional Oracle, SQL Server, MySQL, and PostgreSQL route packs, inclu | Skill 1200 | `DECLARED` |
| `b31-routine-trigger-migration` | Migrate database functions, procedures, packages, triggers, dynamic SQL, cursors, exceptions, transa | Skill 1190 | `DECLARED` |
| `b31-schema-table-column-migration` | Implement schema, namespace, table, column, default, comment, ownership, and object-name migration t | Skill 1185 | `DECLARED` |
| `b31-sequence-identity-generated-columns` | Migrate sequences, identity/auto-increment keys, generated and computed columns, defaults, allocatio | Skill 1188 | `DECLARED` |
| `b31-transaction-isolation-locking` | Migrate and verify autocommit, transaction boundaries, isolation, savepoints, locking, MVCC, deadloc | Skill 1193 | `DECLARED` |
| `b31-type-precision-null-collation` | Implement and certify cross-engine data type, precision, scale, null, charset, collation, time-zone, | Skill 1186 | `DECLARED` |
| `b31-view-materialized-view-migration` | Migrate views, indexed/materialized views, refresh policies, dependencies, security context, updatab | Skill 1189 | `DECLARED` |
| `b31-warehouse-lakehouse-analytics` | Migrate warehouses, lakehouses, dimensional models, SCD logic, aggregates, semantic metrics, BI mode | Skill 1199 | `DECLARED` |

### 批次 `chinadb` (47 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `chinadb-00-migration-program-orchestrator` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Migration Pro | - | `SPEC_ONLY` |
| `chinadb-01-estate-inventory-assessment` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Estate Invent | - | `SPEC_ONLY` |
| `chinadb-02-semantic-db-ir` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Semantic Data | - | `SPEC_ONLY` |
| `chinadb-03-rule-mutation-dsl` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Rule & Mutati | - | `SPEC_ONLY` |
| `chinadb-04-data-movement-cdc` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Commercial Da | - | `SPEC_ONLY` |
| `chinadb-05-ddl-auto-conversion` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for DDL Automatic | - | `SPEC_ONLY` |
| `chinadb-06-sql-auto-conversion` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for SQL Automatic | - | `SPEC_ONLY` |
| `chinadb-07-plsql-tsql-conversion` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for PL/SQL & T-SQ | - | `SPEC_ONLY` |
| `chinadb-08-application-code-auto-refactor` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Application C | - | `SPEC_ONLY` |
| `chinadb-09-behavior-equivalence-verification` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Behavioral Eq | - | `SPEC_ONLY` |
| `chinadb-10-performance-equivalence-verification` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Performance E | - | `SPEC_ONLY` |
| `chinadb-11-guarded-auto-repair` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Guarded Autom | - | `SPEC_ONLY` |
| `chinadb-12-cutover-rollback` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Cutover, Rehe | - | `SPEC_ONLY` |
| `chinadb-13-production-migration-certification` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for E1-E5 Product | - | `SPEC_ONLY` |
| `chinadb-14-security-governance` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Security, Sec | - | `SPEC_ONLY` |
| `chinadb-15-evidence-ledger-reproducibility` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Evidence Ledg | - | `SPEC_ONLY` |
| `chinadb-16-release-ci-quality-gates` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Release CI &  | - | `SPEC_ONLY` |
| `chinadb-20-source-oracle-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Oracle Source | - | `SPEC_ONLY` |
| `chinadb-21-source-sqlserver-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for SQL Server /  | - | `SPEC_ONLY` |
| `chinadb-22-source-postgresql-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for PostgreSQL So | - | `SPEC_ONLY` |
| `chinadb-23-source-mysql-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for MySQL / Maria | - | `SPEC_ONLY` |
| `chinadb-24-source-db2-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for DB2 LUW Sourc | - | `SPEC_ONLY` |
| `chinadb-25-source-sybase-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Sybase ASE So | - | `SPEC_ONLY` |
| `chinadb-30-app-java-spring-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Java / Spring | - | `SPEC_ONLY` |
| `chinadb-31-app-dotnet-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for .NET Database | - | `SPEC_ONLY` |
| `chinadb-32-app-python-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Python Databa | - | `SPEC_ONLY` |
| `chinadb-33-app-nodejs-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Node.js / Typ | - | `SPEC_ONLY` |
| `chinadb-34-app-go-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Go Database R | - | `SPEC_ONLY` |
| `chinadb-40-target-dm8` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for DM8 Target Ad | - | `SPEC_ONLY` |
| `chinadb-41-target-kingbasees` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for KingbaseES Ta | - | `SPEC_ONLY` |
| `chinadb-42-target-opengauss` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for openGauss Tar | - | `SPEC_ONLY` |
| `chinadb-43-target-tidb` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for TiDB Target A | - | `SPEC_ONLY` |
| `chinadb-44-target-gbase8s` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GBase 8s Targ | - | `SPEC_ONLY` |
| `chinadb-45-target-gbase8c` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GBase 8c Targ | - | `SPEC_ONLY` |
| `chinadb-46-target-gbase8a` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GBase 8a Targ | - | `SPEC_ONLY` |
| `chinadb-47-target-highgo` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for HighGo / HGDB | - | `SPEC_ONLY` |
| `chinadb-48-target-oceanbase-oracle` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for OceanBase Ora | - | `SPEC_ONLY` |
| `chinadb-49-target-oceanbase-mysql` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for OceanBase MyS | - | `SPEC_ONLY` |
| `chinadb-50-target-gaussdb-oracle` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GaussDB Oracl | - | `SPEC_ONLY` |
| `chinadb-51-target-gaussdb-m` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GaussDB M-Com | - | `SPEC_ONLY` |
| `chinadb-52-target-goldendb` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GoldenDB Targ | - | `SPEC_ONLY` |
| `chinadb-60-route-support-matrix` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Route Support | - | `SPEC_ONLY` |
| `chinadb-61-fixture-corpus-and-mutation-tests` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Commercial Fi | - | `SPEC_ONLY` |
| `chinadb-62-benchmark-lab` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Database Migr | - | `SPEC_ONLY` |
| `chinadb-63-migration-estimation-commercial-report` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Commercial As | - | `SPEC_ONLY` |
| `chinadb-64-vendor-native-tool-bridge` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Vendor-Native | - | `SPEC_ONLY` |
| `chinadb-65-observability-migration-control-plane` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Migration Obs | - | `SPEC_ONLY` |

### 批次 `b38` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b38-air-gapped-edition` | Implement and verify Batch 38 Skill 1333 for air gapped edition. Use when work requires Air-gapped E | Skill 1333 | `supported` |
| `b38-customer-vpc-edition` | Implement and verify Batch 38 Skill 1330 for customer vpc edition. Use when work requires Customer V | Skill 1330 | `supported` |
| `b38-database-expand-contract-upgrade` | Implement and verify Batch 38 Skill 1341 for database expand contract upgrade. Use when work require | Skill 1341 | `supported` |
| `b38-dedicated-saas-edition` | Implement and verify Batch 38 Skill 1329 for dedicated saas edition. Use when work requires Dedicate | Skill 1329 | `supported` |
| `b38-deployment-upgrade-gate` | Implement and verify Batch 38 Skill 1346 for deployment upgrade gate. Use when work requires Batch 3 | Skill 1346 | `supported` |
| `b38-edge-plant-restricted-edition` | Implement and verify Batch 38 Skill 1334 for edge plant restricted edition. Use when work requires E | Skill 1334 | `supported` |
| `b38-edition-responsibility-matrix` | Implement and verify Batch 38 Skill 1326 for edition responsibility matrix. Use when work requires E | Skill 1326 | `supported` |
| `b38-enterprise-deployment-upgrade-factory` | Implement and verify Batch 38 Skill 1325 for enterprise deployment upgrade factory. Use when work re | Skill 1325 | `supported` |
| `b38-multiregion-active-active-edition` | Implement and verify Batch 38 Skill 1335 for multiregion active active edition. Use when work requir | Skill 1335 | `supported` |
| `b38-multitenant-saas-edition` | Implement and verify Batch 38 Skill 1328 for multitenant saas edition. Use when work requires Multi- | Skill 1328 | `supported` |
| `b38-offline-signed-update-bundle` | Implement and verify Batch 38 Skill 1343 for offline signed update bundle. Use when work requires \u | Skill 1343 | `supported` |
| `b38-plane-topology-governance` | Implement and verify Batch 38 Skill 1336 for plane topology governance. Use when work requires \u657 | Skill 1336 | `supported` |
| `b38-platform-version-compatibility` | Implement and verify Batch 38 Skill 1338 for platform version compatibility. Use when work requires  | Skill 1338 | `supported` |
| `b38-portable-control-plane` | Implement and verify Batch 38 Skill 1327 for portable control plane. Use when work requires Control  | Skill 1327 | `supported` |
| `b38-private-sovereign-cloud-edition` | Implement and verify Batch 38 Skill 1332 for private sovereign cloud edition. Use when work requires | Skill 1332 | `supported` |
| `b38-recipe-pack-extension-upgrade` | Implement and verify Batch 38 Skill 1342 for recipe pack extension upgrade. Use when work requires R | Skill 1342 | `supported` |
| `b38-runner-version-compatibility` | Implement and verify Batch 38 Skill 1339 for runner version compatibility. Use when work requires Ru | Skill 1339 | `supported` |
| `b38-self-hosted-edition` | Implement and verify Batch 38 Skill 1331 for self hosted edition. Use when work requires Self-hosted | Skill 1331 | `supported` |
| `b38-tenant-edition-migration` | Implement and verify Batch 38 Skill 1337 for tenant edition migration. Use when work requires Tenant | Skill 1337 | `supported` |
| `b38-upgrade-rollback-disaster-recovery` | Implement and verify Batch 38 Skill 1345 for upgrade rollback disaster recovery. Use when work requi | Skill 1345 | `supported` |
| `b38-workflow-version-long-run-recovery` | Implement and verify Batch 38 Skill 1340 for workflow version long run recovery. Use when work requi | Skill 1340 | `supported` |
| `b38-zero-downtime-upgrade` | Implement and verify Batch 38 Skill 1344 for zero downtime upgrade. Use when work requires Zero-down | Skill 1344 | `supported` |

### 批次 `b39` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b39-autoscaling-capacity-control` | Implement and verify Batch 39 Skill 1353 for autoscaling capacity control. Use when work requires \u | Skill 1353 | `supported` |
| `b39-backup-restore-recovery` | Implement and verify Batch 39 Skill 1355 for backup restore recovery. Use when work requires Backup\ | Skill 1355 | `supported` |
| `b39-change-management-freeze` | Implement and verify Batch 39 Skill 1361 for change management freeze. Use when work requires Change | Skill 1361 | `supported` |
| `b39-chaos-resilience-fault-injection` | Implement and verify Batch 39 Skill 1363 for chaos resilience fault injection. Use when work require | Skill 1363 | `supported` |
| `b39-customer-status-communication` | Implement and verify Batch 39 Skill 1359 for customer status communication. Use when work requires \ | Skill 1359 | `supported` |
| `b39-enterprise-support-sla` | Implement and verify Batch 39 Skill 1360 for enterprise support sla. Use when work requires \u4f01\u | Skill 1360 | `supported` |
| `b39-error-budget-governance` | Implement and verify Batch 39 Skill 1349 for error budget governance. Use when work requires Error B | Skill 1349 | `supported` |
| `b39-global-observability-telemetry` | Implement and verify Batch 39 Skill 1350 for global observability telemetry. Use when work requires  | Skill 1350 | `supported` |
| `b39-global-operations-gate` | Implement and verify Batch 39 Skill 1368 for global operations gate. Use when work requires Batch 39 | Skill 1368 | `supported` |
| `b39-global-sre-operations-factory` | Implement and verify Batch 39 Skill 1347 for global sre operations factory. Use when work requires \ | Skill 1347 | `supported` |
| `b39-incident-command` | Implement and verify Batch 39 Skill 1356 for incident command. Use when work requires Incident Comma | Skill 1356 | `supported` |
| `b39-job-fairness-tenant-isolation` | Implement and verify Batch 39 Skill 1352 for job fairness tenant isolation. Use when work requires J | Skill 1352 | `supported` |
| `b39-multiregion-failover` | Implement and verify Batch 39 Skill 1354 for multiregion failover. Use when work requires \u591a\u53 | Skill 1354 | `supported` |
| `b39-oncall-follow-the-sun` | Implement and verify Batch 39 Skill 1358 for oncall follow the sun. Use when work requires On-call\u | Skill 1358 | `supported` |
| `b39-operations-evidence-reporting` | Implement and verify Batch 39 Skill 1367 for operations evidence reporting. Use when work requires \ | Skill 1367 | `supported` |
| `b39-platform-cost-anomaly-monitoring` | Implement and verify Batch 39 Skill 1362 for platform cost anomaly monitoring. Use when work require | Skill 1362 | `supported` |
| `b39-problem-root-cause-loop` | Implement and verify Batch 39 Skill 1357 for problem root cause loop. Use when work requires Problem | Skill 1357 | `supported` |
| `b39-production-readiness-review` | Implement and verify Batch 39 Skill 1364 for production readiness review. Use when work requires Pro | Skill 1364 | `supported` |
| `b39-scheduled-restore-dr-exercise` | Implement and verify Batch 39 Skill 1366 for scheduled restore dr exercise. Use when work requires \ | Skill 1366 | `supported` |
| `b39-service-catalog-sli-slo` | Implement and verify Batch 39 Skill 1348 for service catalog sli slo. Use when work requires Service | Skill 1348 | `supported` |
| `b39-sla-service-credit-governance` | Implement and verify Batch 39 Skill 1365 for sla service credit governance. Use when work requires \ | Skill 1365 | `supported` |
| `b39-tenant-project-migration-health` | Implement and verify Batch 39 Skill 1351 for tenant project migration health. Use when work requires | Skill 1351 | `supported` |

### 批次 `b40` (24 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b40-ai-model-supply-chain` | Implement and verify Batch 40 Skill 1386 for ai model supply chain. Use when work requires AI/ML-BOM | Skill 1386 | `supported` |
| `b40-artifact-container-signing` | Implement and verify Batch 40 Skill 1382 for artifact container signing. Use when work requires Arti | Skill 1382 | `supported` |
| `b40-compliance-control-crosswalk` | Implement and verify Batch 40 Skill 1389 for compliance control crosswalk. Use when work requires IS | Skill 1389 | `supported` |
| `b40-container-kubernetes-iac-scanning` | Implement and verify Batch 40 Skill 1378 for container kubernetes iac scanning. Use when work requir | Skill 1378 | `supported` |
| `b40-customer-audit-evidence` | Implement and verify Batch 40 Skill 1390 for customer audit evidence. Use when work requires \u5ba2\ | Skill 1390 | `supported` |
| `b40-dast-iast-integration` | Implement and verify Batch 40 Skill 1375 for dast iast integration. Use when work requires DAST\u548 | Skill 1375 | `supported` |
| `b40-dependency-sca-governance` | Implement and verify Batch 40 Skill 1376 for dependency sca governance. Use when work requires Depen | Skill 1376 | `supported` |
| `b40-independent-security-assessment` | Implement and verify Batch 40 Skill 1391 for independent security assessment. Use when work requires | Skill 1391 | `supported` |
| `b40-isolated-trusted-builder` | Implement and verify Batch 40 Skill 1384 for isolated trusted builder. Use when work requires \u9694 | Skill 1384 | `supported` |
| `b40-license-ip-provenance` | Implement and verify Batch 40 Skill 1381 for license ip provenance. Use when work requires License\u | Skill 1381 | `supported` |
| `b40-psirt-security-incident` | Implement and verify Batch 40 Skill 1388 for psirt security incident. Use when work requires PSIRT\u | Skill 1388 | `supported` |
| `b40-runner-update-supply-chain` | Implement and verify Batch 40 Skill 1385 for runner update supply chain. Use when work requires Runn | Skill 1385 | `supported` |
| `b40-sast-integration` | Implement and verify Batch 40 Skill 1374 for sast integration. Use when work requires SAST\u96c6\u62 | Skill 1374 | `supported` |
| `b40-sbom-component-identity` | Implement and verify Batch 40 Skill 1379 for sbom component identity. Use when work requires SBOM\u7 | Skill 1379 | `supported` |
| `b40-secret-credential-scanning` | Implement and verify Batch 40 Skill 1377 for secret credential scanning. Use when work requires Secr | Skill 1377 | `supported` |
| `b40-secure-code-review-approval` | Implement and verify Batch 40 Skill 1373 for secure code review approval. Use when work requires Sec | Skill 1373 | `supported` |
| `b40-secure-sdlc-ssdf` | Implement and verify Batch 40 Skill 1370 for secure sdlc ssdf. Use when work requires Secure SDLC\u5 | Skill 1370 | `supported` |
| `b40-security-architecture-review` | Implement and verify Batch 40 Skill 1372 for security architecture review. Use when work requires Se | Skill 1372 | `supported` |
| `b40-security-supply-chain-gate` | Implement and verify Batch 40 Skill 1392 for security supply chain gate. Use when work requires Batc | Skill 1392 | `supported` |
| `b40-slsa-provenance` | Implement and verify Batch 40 Skill 1383 for slsa provenance. Use when work requires SLSA Provenance | Skill 1383 | `supported` |
| `b40-supply-chain-compliance-factory` | Implement and verify Batch 40 Skill 1369 for supply chain compliance factory. Use when work requires | Skill 1369 | `supported` |
| `b40-threat-modeling` | Implement and verify Batch 40 Skill 1371 for threat modeling. Use when work requires Threat Modeling | Skill 1371 | `supported` |
| `b40-vex-applicability` | Implement and verify Batch 40 Skill 1380 for vex applicability. Use when work requires VEX\u548c\u6f | Skill 1380 | `supported` |
| `b40-vulnerability-patch-sla` | Implement and verify Batch 40 Skill 1387 for vulnerability patch sla. Use when work requires \u6f0f\ | Skill 1387 | `supported` |

### 批次 `b41` (20 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b41-automation-buildgreen-prediction` | Implement and verify Batch 41 Skill 1401 for automation buildgreen prediction. Use when work require | Skill 1401 | `supported` |
| `b41-diagnostic-root-cause-recommendation` | Implement and verify Batch 41 Skill 1404 for diagnostic root cause recommendation. Use when work req | Skill 1404 | `supported` |
| `b41-effort-duration-cost-prediction` | Implement and verify Batch 41 Skill 1402 for effort duration cost prediction. Use when work requires | Skill 1402 | `supported` |
| `b41-holdout-feedback-calibration` | Implement and verify Batch 41 Skill 1409 for holdout feedback calibration. Use when work requires Ho | Skill 1409 | `supported` |
| `b41-human-curation-governance` | Implement and verify Batch 41 Skill 1410 for human curation governance. Use when work requires Human | Skill 1410 | `supported` |
| `b41-knowledge-confidence-provenance` | Implement and verify Batch 41 Skill 1405 for knowledge confidence provenance. Use when work requires | Skill 1405 | `supported` |
| `b41-knowledge-flywheel-gate` | Implement and verify Batch 41 Skill 1412 for knowledge flywheel gate. Use when work requires Batch 4 | Skill 1412 | `supported` |
| `b41-knowledge-freshness-versioning` | Implement and verify Batch 41 Skill 1406 for knowledge freshness versioning. Use when work requires  | Skill 1406 | `supported` |
| `b41-knowledge-graph-ontology` | Implement and verify Batch 41 Skill 1394 for knowledge graph ontology. Use when work requires Migrat | Skill 1394 | `supported` |
| `b41-knowledge-isolation` | Implement and verify Batch 41 Skill 1407 for knowledge isolation. Use when work requires \u516c\u517 | Skill 1407 | `supported` |
| `b41-knowledge-marketplace-sharing` | Implement and verify Batch 41 Skill 1411 for knowledge marketplace sharing. Use when work requires \ | Skill 1411 | `supported` |
| `b41-migration-entity-relations` | Implement and verify Batch 41 Skill 1395 for migration entity relations. Use when work requires \u98 | Skill 1395 | `supported` |
| `b41-migration-knowledge-factory` | Implement and verify Batch 41 Skill 1393 for migration knowledge factory. Use when work requires \u8 | Skill 1393 | `supported` |
| `b41-migration-risk-prediction` | Implement and verify Batch 41 Skill 1400 for migration risk prediction. Use when work requires \u8fc | Skill 1400 | `supported` |
| `b41-migration-run-ingestion` | Implement and verify Batch 41 Skill 1396 for migration run ingestion. Use when work requires Migrati | Skill 1396 | `supported` |
| `b41-pattern-antipattern-extraction` | Implement and verify Batch 41 Skill 1397 for pattern antipattern extraction. Use when work requires  | Skill 1397 | `supported` |
| `b41-privacy-preserving-learning` | Implement and verify Batch 41 Skill 1408 for privacy preserving learning. Use when work requires \u9 | Skill 1408 | `supported` |
| `b41-recipe-mapping-recommendation` | Implement and verify Batch 41 Skill 1398 for recipe mapping recommendation. Use when work requires R | Skill 1398 | `supported` |
| `b41-similar-project-retrieval` | Implement and verify Batch 41 Skill 1399 for similar project retrieval. Use when work requires \u76f | Skill 1399 | `supported` |
| `b41-target-stack-recommendation` | Implement and verify Batch 41 Skill 1403 for target stack recommendation. Use when work requires \u7 | Skill 1403 | `supported` |

### 批次 `b42` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b42-agent-autonomy-levels` | Implement and verify Batch 42 Skill 1432 for agent autonomy levels. Use when work requires Agent\u81 | Skill 1432 | `supported` |
| `b42-agent-budget-resource-limits` | Implement and verify Batch 42 Skill 1426 for agent budget resource limits. Use when work requires Ag | Skill 1426 | `supported` |
| `b42-agent-eval-benchmark` | Implement and verify Batch 42 Skill 1427 for agent eval benchmark. Use when work requires Agent Eval | Skill 1427 | `supported` |
| `b42-agent-factory-gate` | Implement and verify Batch 42 Skill 1434 for agent factory gate. Use when work requires Batch 42\u62 | Skill 1434 | `supported` |
| `b42-agent-incident-killswitch-rollback` | Implement and verify Batch 42 Skill 1430 for agent incident killswitch rollback. Use when work requi | Skill 1430 | `supported` |
| `b42-agent-memory-state-governance` | Implement and verify Batch 42 Skill 1424 for agent memory state governance. Use when work requires A | Skill 1424 | `supported` |
| `b42-agent-migration-factory` | Implement and verify Batch 42 Skill 1413 for agent migration factory. Use when work requires \u6210\ | Skill 1413 | `supported` |
| `b42-agent-red-team` | Implement and verify Batch 42 Skill 1429 for agent red team. Use when work requires Agent Red Team\u | Skill 1429 | `supported` |
| `b42-agent-shadow-canary` | Implement and verify Batch 42 Skill 1428 for agent shadow canary. Use when work requires Shadow\u300 | Skill 1428 | `supported` |
| `b42-agent-team-topology` | Implement and verify Batch 42 Skill 1414 for agent team topology. Use when work requires Agent Team  | Skill 1414 | `supported` |
| `b42-agent-tool-permissions` | Implement and verify Batch 42 Skill 1422 for agent tool permissions. Use when work requires Agent To | Skill 1422 | `supported` |
| `b42-deterministic-execution-agent` | Implement and verify Batch 42 Skill 1416 for deterministic execution agent. Use when work requires D | Skill 1416 | `supported` |
| `b42-human-approval-takeover` | Implement and verify Batch 42 Skill 1421 for human approval takeover. Use when work requires Human A | Skill 1421 | `supported` |
| `b42-language-framework-specialist-agent` | Implement and verify Batch 42 Skill 1417 for language framework specialist agent. Use when work requ | Skill 1417 | `supported` |
| `b42-migration-planner-agent` | Implement and verify Batch 42 Skill 1415 for migration planner agent. Use when work requires Migrati | Skill 1415 | `supported` |
| `b42-minimal-context-evidence` | Implement and verify Batch 42 Skill 1423 for minimal context evidence. Use when work requires \u6700 | Skill 1423 | `supported` |
| `b42-model-routing-provider-failover` | Implement and verify Batch 42 Skill 1425 for model routing provider failover. Use when work requires | Skill 1425 | `supported` |
| `b42-multiagent-consensus-arbitration` | Implement and verify Batch 42 Skill 1433 for multiagent consensus arbitration. Use when work require | Skill 1433 | `supported` |
| `b42-policy-enforcement-agent` | Implement and verify Batch 42 Skill 1419 for policy enforcement agent. Use when work requires Policy | Skill 1419 | `supported` |
| `b42-recipe-candidate-agent` | Implement and verify Batch 42 Skill 1431 for recipe candidate agent. Use when work requires \u81ea\u | Skill 1431 | `supported` |
| `b42-supervisor-coordination-agent` | Implement and verify Batch 42 Skill 1420 for supervisor coordination agent. Use when work requires S | Skill 1420 | `supported` |
| `b42-verification-agent` | Implement and verify Batch 42 Skill 1418 for verification agent. Use when work requires Verification | Skill 1418 | `supported` |

### 批次 `b43` (20 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b43-automated-upgrade-tooling` | Implement and verify Batch 43 Skill 1448 for automated upgrade tooling. Use when work requires \u81e | Skill 1448 | `supported` |
| `b43-compatibility-test-matrix` | Implement and verify Batch 43 Skill 1452 for compatibility test matrix. Use when work requires \u516 | Skill 1452 | `supported` |
| `b43-customer-upgrade-readiness` | Implement and verify Batch 43 Skill 1447 for customer upgrade readiness. Use when work requires \u5b | Skill 1447 | `supported` |
| `b43-database-migration-compatibility` | Implement and verify Batch 43 Skill 1443 for database migration compatibility. Use when work require | Skill 1443 | `supported` |
| `b43-deprecation-removal` | Implement and verify Batch 43 Skill 1446 for deprecation removal. Use when work requires Deprecation | Skill 1446 | `supported` |
| `b43-event-schema-compatibility` | Implement and verify Batch 43 Skill 1438 for event schema compatibility. Use when work requires Even | Skill 1438 | `supported` |
| `b43-feature-flag-progressive-enable` | Implement and verify Batch 43 Skill 1449 for feature flag progressive enable. Use when work requires | Skill 1449 | `supported` |
| `b43-product-lifecycle-factory` | Implement and verify Batch 43 Skill 1435 for product lifecycle factory. Use when work requires \u4ea | Skill 1435 | `supported` |
| `b43-product-lifecycle-gate` | Implement and verify Batch 43 Skill 1454 for product lifecycle gate. Use when work requires Batch 43 | Skill 1454 | `supported` |
| `b43-psp-uir-schema-compatibility` | Implement and verify Batch 43 Skill 1441 for psp uir schema compatibility. Use when work requires PS | Skill 1441 | `supported` |
| `b43-public-api-compatibility` | Implement and verify Batch 43 Skill 1437 for public api compatibility. Use when work requires Public | Skill 1437 | `supported` |
| `b43-recipe-pack-extension-compatibility` | Implement and verify Batch 43 Skill 1442 for recipe pack extension compatibility. Use when work requ | Skill 1442 | `supported` |
| `b43-release-channel-governance` | Implement and verify Batch 43 Skill 1444 for release channel governance. Use when work requires LTS\ | Skill 1444 | `supported` |
| `b43-release-documentation` | Implement and verify Batch 43 Skill 1453 for release documentation. Use when work requires Changelog | Skill 1453 | `supported` |
| `b43-rolling-mixed-version-upgrade` | Implement and verify Batch 43 Skill 1450 for rolling mixed version upgrade. Use when work requires R | Skill 1450 | `supported` |
| `b43-runner-protocol-compatibility` | Implement and verify Batch 43 Skill 1440 for runner protocol compatibility. Use when work requires R | Skill 1440 | `supported` |
| `b43-sdk-compatibility` | Implement and verify Batch 43 Skill 1439 for sdk compatibility. Use when work requires SDK\u517c\u5b | Skill 1439 | `supported` |
| `b43-security-fix-backport` | Implement and verify Batch 43 Skill 1451 for security fix backport. Use when work requires \u5b89\u5 | Skill 1451 | `supported` |
| `b43-support-eol-policy` | Implement and verify Batch 43 Skill 1445 for support eol policy. Use when work requires \u652f\u6301 | Skill 1445 | `supported` |
| `b43-version-specification` | Implement and verify Batch 43 Skill 1436 for version specification. Use when work requires \u4ea7\u5 | Skill 1436 | `supported` |

### 批次 `b44` (20 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b44-artifact-retention-egress-economics` | Implement and verify Batch 44 Skill 1462 for artifact retention egress economics. Use when work requ | Skill 1462 | `supported` |
| `b44-assessment-poc-project-quote` | Implement and verify Batch 44 Skill 1466 for assessment poc project quote. Use when work requires As | Skill 1466 | `supported` |
| `b44-budget-quota-cost-guardrail` | Implement and verify Batch 44 Skill 1468 for budget quota cost guardrail. Use when work requires Bud | Skill 1468 | `supported` |
| `b44-cache-incremental-cost-optimization` | Implement and verify Batch 44 Skill 1469 for cache incremental cost optimization. Use when work requ | Skill 1469 | `supported` |
| `b44-cost-scenario-forecast` | Implement and verify Batch 44 Skill 1471 for cost scenario forecast. Use when work requires \u6210\u | Skill 1471 | `supported` |
| `b44-cost-taxonomy-economic-model` | Implement and verify Batch 44 Skill 1456 for cost taxonomy economic model. Use when work requires \u | Skill 1456 | `supported` |
| `b44-customer-roi-tco-value` | Implement and verify Batch 44 Skill 1472 for customer roi tco value. Use when work requires \u5ba2\u | Skill 1472 | `supported` |
| `b44-customer-route-edition-margin` | Implement and verify Batch 44 Skill 1467 for customer route edition margin. Use when work requires \ | Skill 1467 | `supported` |
| `b44-economics-maturity-gate` | Implement and verify Batch 44 Skill 1474 for economics maturity gate. Use when work requires Batch 4 | Skill 1474 | `supported` |
| `b44-human-expert-cost` | Implement and verify Batch 44 Skill 1463 for human expert cost. Use when work requires \u4eba\u5de5R | Skill 1463 | `supported` |
| `b44-migration-finops-factory` | Implement and verify Batch 44 Skill 1455 for migration finops factory. Use when work requires \u8fc1 | Skill 1455 | `supported` |
| `b44-model-agent-economics` | Implement and verify Batch 44 Skill 1461 for model agent economics. Use when work requires \u6a21\u5 | Skill 1461 | `supported` |
| `b44-packaging-pricing-model` | Implement and verify Batch 44 Skill 1465 for packaging pricing model. Use when work requires \u4ea7\ | Skill 1465 | `supported` |
| `b44-provider-resource-routing` | Implement and verify Batch 44 Skill 1470 for provider resource routing. Use when work requires \u6a2 | Skill 1470 | `supported` |
| `b44-resource-metering` | Implement and verify Batch 44 Skill 1457 for resource metering. Use when work requires Runner\u3001\ | Skill 1457 | `supported` |
| `b44-runner-fleet-economics` | Implement and verify Batch 44 Skill 1460 for runner fleet economics. Use when work requires Runner\u | Skill 1460 | `supported` |
| `b44-showback-chargeback` | Implement and verify Batch 44 Skill 1458 for showback chargeback. Use when work requires \u6210\u672 | Skill 1458 | `supported` |
| `b44-support-hypercare-operations-cost` | Implement and verify Batch 44 Skill 1464 for support hypercare operations cost. Use when work requir | Skill 1464 | `supported` |
| `b44-usage-billing-reconciliation` | Implement and verify Batch 44 Skill 1473 for usage billing reconciliation. Use when work requires \u | Skill 1473 | `supported` |
| `b44-verified-workload-unit-cost` | Implement and verify Batch 44 Skill 1459 for verified workload unit cost. Use when work requires Ver | Skill 1459 | `supported` |

### 批次 `b45` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 状态 |
| :--- | :--- | :--- | :---: |
| `b45-customer-value-certification` | Implement and verify Batch 45 Skill 1488 for customer value certification. Use when work requires \u | Skill 1488 | `supported` |
| `b45-deployment-matrix-certification` | Implement and verify Batch 45 Skill 1485 for deployment matrix certification. Use when work requires | Skill 1485 | `supported` |
| `b45-design-partner-reference-validation` | Implement and verify Batch 45 Skill 1489 for design partner reference validation. Use when work requ | Skill 1489 | `supported` |
| `b45-developer-experience-certification` | Implement and verify Batch 45 Skill 1484 for developer experience certification. Use when work requi | Skill 1484 | `supported` |
| `b45-economics-profitability-certification` | Implement and verify Batch 45 Skill 1487 for economics profitability certification. Use when work re | Skill 1487 | `supported` |
| `b45-ecosystem-certification` | Implement and verify Batch 45 Skill 1486 for ecosystem certification. Use when work requires SDK\u30 | Skill 1486 | `supported` |
| `b45-edition-route-vertical-certification` | Implement and verify Batch 45 Skill 1495 for edition route vertical certification. Use when work req | Skill 1495 | `supported` |
| `b45-functional-depth-certification` | Implement and verify Batch 45 Skill 1477 for functional depth certification. Use when work requires  | Skill 1477 | `supported` |
| `b45-independent-expert-validation` | Implement and verify Batch 45 Skill 1490 for independent expert validation. Use when work requires \ | Skill 1490 | `supported` |
| `b45-mature-product-certification` | Implement and verify Batch 45 Skill 1475 for mature product certification. Use when work requires \u | Skill 1475 | `supported` |
| `b45-mature-product-evidence-pack` | Implement and verify Batch 45 Skill 1494 for mature product evidence pack. Use when work requires Ma | Skill 1494 | `supported` |
| `b45-mature-product-final-gate` | Implement and verify Batch 45 Skill 1496 for mature product final gate. Use when work requires Batch | Skill 1496 | `supported` |
| `b45-mature-release-readiness` | Implement and verify Batch 45 Skill 1491 for mature release readiness. Use when work requires Mature | Skill 1491 | `supported` |
| `b45-maturity-model-editions` | Implement and verify Batch 45 Skill 1476 for maturity model editions. Use when work requires \u4ea7\ | Skill 1476 | `supported` |
| `b45-product-governance-accountability` | Implement and verify Batch 45 Skill 1492 for product governance accountability. Use when work requir | Skill 1492 | `supported` |
| `b45-residual-risk-register` | Implement and verify Batch 45 Skill 1493 for residual risk register. Use when work requires \u7efc\u | Skill 1493 | `supported` |
| `b45-route-breadth-certification` | Implement and verify Batch 45 Skill 1478 for route breadth certification. Use when work requires \u8 | Skill 1478 | `supported` |
| `b45-scale-performance-certification` | Implement and verify Batch 45 Skill 1480 for scale performance certification. Use when work requires | Skill 1480 | `supported` |
| `b45-security-data-certification` | Implement and verify Batch 45 Skill 1481 for security data certification. Use when work requires \u5 | Skill 1481 | `supported` |
| `b45-semantic-behavior-certification` | Implement and verify Batch 45 Skill 1479 for semantic behavior certification. Use when work requires | Skill 1479 | `supported` |
| `b45-sre-reliability-dr-certification` | Implement and verify Batch 45 Skill 1482 for sre reliability dr certification. Use when work require | Skill 1482 | `supported` |
| `b45-target-maintainability-certification` | Implement and verify Batch 45 Skill 1483 for target maintainability certification. Use when work req | Skill 1483 | `supported` |
