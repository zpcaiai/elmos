# ELMOS 全量 4669 Skills 系统化审计与全景档案

## 1. 审计统计概览

- **技能总数**：`4669` 个标准技能规范 (`SKILL.md`)
- **审计耗时**：`3.14` 秒
- **Frontmatter 格式合规率**：`100.0%` (4669 / 4669 均合法具备 YAML Frontmatter)

### 四层宏观状态分布 (与平台总体演进目标对齐)

| 宏观分类 | 技能数量 | 占比 | 核心定义与保障 |
| :--- | :---: | :---: | :--- |
| `[VERIFIED / CODE_COMPLETE]` | **2162** | **46.3%** | 具备 Python 专属 Handler、双根契约与真实测试验证 (Exit Code 0) |
| `[DECLARED / SPEC_ONLY]` | **1617** | **34.6%** | 已完成规范向可执行代码实现的转化，属于待下发或上游锁定规范 |
| `[PRODUCTION_CONTRACT]` | **473** | **10.1%** | 保持生产契约稳定，生产核心数据模型与控制门禁 |
| `[TEST_READY / BOUNDED]` | **417** | **8.9%** | 受控沙箱与局部控制平面状态，具备离线可运行测试与有界环境 |

### 细分声明实现状态 TOP 15

| 细分实现状态 | 技能数量 | 占比 |
| :--- | :---: | :---: |
| `VERIFIED` | 2162 | 46.3% |
| `DECLARED` | 1566 | 33.5% |
| `production-contract` | 473 | 10.1% |
| `LOCAL_CONTROL_PLANE` | 102 | 2.2% |
| `BLUEPRINT_IMPORTED` | 101 | 2.2% |
| `RUNTIME_BOUND_NOT_EXECUTED` | 87 | 1.9% |
| `SPEC_ONLY` | 47 | 1.0% |
| `test-ready-not-run` | 35 | 0.7% |
| `LOCAL_EXECUTED_SELF_ATTESTED` | 29 | 0.6% |
| `PARTIAL_LOCAL_IMPLEMENTED` | 26 | 0.6% |
| `BOUNDED_LOCAL_IMPLEMENTED` | 19 | 0.4% |
| `LOCAL_IMPLEMENTED_UNQUALIFIED` | 11 | 0.2% |
| `PLANNING_ONLY_IMPLEMENTED` | 5 | 0.1% |
| `LOCAL_IMPLEMENTED_BOUNDED` | 1 | 0.0% |
| `GUIDANCE_ONLY_NOT_EXECUTABLE` | 1 | 0.0% |

### 核心批次与类别分布

| 批次 / 类别前缀 | 技能数量 | 核心领域 |
| :--- | :---: | :--- |
| `elmos` | 1416 | Foundry v3 原子技能、多语言语义编译器、多模态摄取与工作台 |
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
| `data` | 27 | 专用领域工程与领域契约 |
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
| `cross` | 18 | 专用领域工程与领域契约 |
| `repository` | 18 | 专用领域工程与领域契约 |
| `batch` | 17 | B81-B95 专属微严认证门禁技能 |

## 2. 关键业务线与批次全量技能明细 (节选核心批次)


### 批次 `b31` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b31-canonical-database-ir` | Implement or extend the typed canonical database IR for catalogs, schemas, types, tables,  | Skill 1183 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-constraint-index-partition-migration` | Migrate primary, unique, foreign, check, exclusion constraints, indexes, clustering, parti | Skill 1187 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-data-contract-catalog-lineage` | Migrate and govern data contracts, catalog metadata, ownership, classifications, SLOs, sch | Skill 1198 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-data-correctness-performance-cutover` | Validate schema, data, queries, routines, transactions, pipelines, performance, backfill,  | Skill 1201 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-data-pipeline-migration` | Migrate ETL, ELT, streaming, batch, and orchestration workflows using typed pipeline IR wh | Skill 1196 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-data-quality-repair` | Implement data profiling, quality rules, anomaly classification, duplicate and referential | Skill 1197 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-database-certification-gate` | Run the conservative Batch 31 certification gate for a database or data-platform pack and  | Skill 1202 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-database-estate-discovery` | Discover and fingerprint database estates, schemas, runtime workloads, security, storage,  | Skill 1182 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-database-modernization-factory` | Implement and certify a directional, version-specific database or data-platform modernizat | Skill 1181 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-dialect-provider-capability-matrix` | Create and maintain exact database dialect, engine version, edition, extension, driver, an | Skill 1184 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-etl-elt-discovery` | Discover ETL, ELT, batch, streaming, orchestration, schedules, sources, sinks, transformat | Skill 1195 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-orm-database-contract` | Coordinate ORM mappings, existing database schema, migration ownership, query generation,  | Skill 1194 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-query-plan-performance` | Compare source and target query plans, cardinality, statistics, indexes, latency, throughp | Skill 1192 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-query-semantic-migration` | Parse and migrate SQL, JPQL/HQL, ORM-generated, dynamic, and native queries through typed  | Skill 1191 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-relational-route-pack-certifier` | Implement and certify exact directional Oracle, SQL Server, MySQL, and PostgreSQL route pa | Skill 1200 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-routine-trigger-migration` | Migrate database functions, procedures, packages, triggers, dynamic SQL, cursors, exceptio | Skill 1190 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-schema-table-column-migration` | Implement schema, namespace, table, column, default, comment, ownership, and object-name m | Skill 1185 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-sequence-identity-generated-columns` | Migrate sequences, identity/auto-increment keys, generated and computed columns, defaults, | Skill 1188 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-transaction-isolation-locking` | Migrate and verify autocommit, transaction boundaries, isolation, savepoints, locking, MVC | Skill 1193 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-type-precision-null-collation` | Implement and certify cross-engine data type, precision, scale, null, charset, collation,  | Skill 1186 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-view-materialized-view-migration` | Migrate views, indexed/materialized views, refresh policies, dependencies, security contex | Skill 1189 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b31-warehouse-lakehouse-analytics` | Migrate warehouses, lakehouses, dimensional models, SCD logic, aggregates, semantic metric | Skill 1199 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `chinadb` (47 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `chinadb-00-migration-program-orchestrator` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Mig | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-01-estate-inventory-assessment` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Est | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-02-semantic-db-ir` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Sem | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-03-rule-mutation-dsl` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Rul | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-04-data-movement-cdc` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Com | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-05-ddl-auto-conversion` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for DDL | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-06-sql-auto-conversion` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for SQL | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-07-plsql-tsql-conversion` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for PL/ | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-08-application-code-auto-refactor` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for App | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-09-behavior-equivalence-verification` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Beh | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-10-performance-equivalence-verification` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Per | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-11-guarded-auto-repair` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Gua | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-12-cutover-rollback` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Cut | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-13-production-migration-certification` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for E1- | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-14-security-governance` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Sec | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-15-evidence-ledger-reproducibility` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Evi | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-16-release-ci-quality-gates` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Rel | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-20-source-oracle-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Ora | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-21-source-sqlserver-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for SQL | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-22-source-postgresql-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Pos | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-23-source-mysql-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for MyS | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-24-source-db2-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for DB2 | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-25-source-sybase-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Syb | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-30-app-java-spring-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Jav | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-31-app-dotnet-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for .NE | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-32-app-python-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Pyt | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-33-app-nodejs-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Nod | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-34-app-go-adapter` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Go  | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-40-target-dm8` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for DM8 | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-41-target-kingbasees` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Kin | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-42-target-opengauss` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for ope | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-43-target-tidb` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for TiD | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-44-target-gbase8s` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GBa | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-45-target-gbase8c` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GBa | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-46-target-gbase8a` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for GBa | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-47-target-highgo` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Hig | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-48-target-oceanbase-oracle` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Oce | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-49-target-oceanbase-mysql` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Oce | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-50-target-gaussdb-oracle` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Gau | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-51-target-gaussdb-m` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Gau | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-52-target-goldendb` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Gol | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-60-route-support-matrix` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Rou | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-61-fixture-corpus-and-mutation-tests` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Com | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-62-benchmark-lab` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Dat | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-63-migration-estimation-commercial-report` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Com | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-64-vendor-native-tool-bridge` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Ven | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |
| `chinadb-65-observability-migration-control-plane` | Use when ELMOS must follow the ChinaDB commercial database-migration specification for Mig | - | `[DECLARED / SPEC_ONLY]` | `SPEC_ONLY` |

### 批次 `b38` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b38-air-gapped-edition` | Implement and verify Batch 38 Skill 1333 for air gapped edition. Use when work requires Ai | Skill 1333 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-customer-vpc-edition` | Implement and verify Batch 38 Skill 1330 for customer vpc edition. Use when work requires  | Skill 1330 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-database-expand-contract-upgrade` | Implement and verify Batch 38 Skill 1341 for database expand contract upgrade. Use when wo | Skill 1341 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-dedicated-saas-edition` | Implement and verify Batch 38 Skill 1329 for dedicated saas edition. Use when work require | Skill 1329 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-deployment-upgrade-gate` | Implement and verify Batch 38 Skill 1346 for deployment upgrade gate. Use when work requir | Skill 1346 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-edge-plant-restricted-edition` | Implement and verify Batch 38 Skill 1334 for edge plant restricted edition. Use when work  | Skill 1334 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-edition-responsibility-matrix` | Implement and verify Batch 38 Skill 1326 for edition responsibility matrix. Use when work  | Skill 1326 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-enterprise-deployment-upgrade-factory` | Implement and verify Batch 38 Skill 1325 for enterprise deployment upgrade factory. Use wh | Skill 1325 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-multiregion-active-active-edition` | Implement and verify Batch 38 Skill 1335 for multiregion active active edition. Use when w | Skill 1335 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-multitenant-saas-edition` | Implement and verify Batch 38 Skill 1328 for multitenant saas edition. Use when work requi | Skill 1328 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-offline-signed-update-bundle` | Implement and verify Batch 38 Skill 1343 for offline signed update bundle. Use when work r | Skill 1343 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-plane-topology-governance` | Implement and verify Batch 38 Skill 1336 for plane topology governance. Use when work requ | Skill 1336 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-platform-version-compatibility` | Implement and verify Batch 38 Skill 1338 for platform version compatibility. Use when work | Skill 1338 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-portable-control-plane` | Implement and verify Batch 38 Skill 1327 for portable control plane. Use when work require | Skill 1327 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-private-sovereign-cloud-edition` | Implement and verify Batch 38 Skill 1332 for private sovereign cloud edition. Use when wor | Skill 1332 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-recipe-pack-extension-upgrade` | Implement and verify Batch 38 Skill 1342 for recipe pack extension upgrade. Use when work  | Skill 1342 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-runner-version-compatibility` | Implement and verify Batch 38 Skill 1339 for runner version compatibility. Use when work r | Skill 1339 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-self-hosted-edition` | Implement and verify Batch 38 Skill 1331 for self hosted edition. Use when work requires S | Skill 1331 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-tenant-edition-migration` | Implement and verify Batch 38 Skill 1337 for tenant edition migration. Use when work requi | Skill 1337 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-upgrade-rollback-disaster-recovery` | Implement and verify Batch 38 Skill 1345 for upgrade rollback disaster recovery. Use when  | Skill 1345 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-workflow-version-long-run-recovery` | Implement and verify Batch 38 Skill 1340 for workflow version long run recovery. Use when  | Skill 1340 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b38-zero-downtime-upgrade` | Implement and verify Batch 38 Skill 1344 for zero downtime upgrade. Use when work requires | Skill 1344 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b39` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b39-autoscaling-capacity-control` | Implement and verify Batch 39 Skill 1353 for autoscaling capacity control. Use when work r | Skill 1353 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-backup-restore-recovery` | Implement and verify Batch 39 Skill 1355 for backup restore recovery. Use when work requir | Skill 1355 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-change-management-freeze` | Implement and verify Batch 39 Skill 1361 for change management freeze. Use when work requi | Skill 1361 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-chaos-resilience-fault-injection` | Implement and verify Batch 39 Skill 1363 for chaos resilience fault injection. Use when wo | Skill 1363 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-customer-status-communication` | Implement and verify Batch 39 Skill 1359 for customer status communication. Use when work  | Skill 1359 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-enterprise-support-sla` | Implement and verify Batch 39 Skill 1360 for enterprise support sla. Use when work require | Skill 1360 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-error-budget-governance` | Implement and verify Batch 39 Skill 1349 for error budget governance. Use when work requir | Skill 1349 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-global-observability-telemetry` | Implement and verify Batch 39 Skill 1350 for global observability telemetry. Use when work | Skill 1350 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-global-operations-gate` | Implement and verify Batch 39 Skill 1368 for global operations gate. Use when work require | Skill 1368 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-global-sre-operations-factory` | Implement and verify Batch 39 Skill 1347 for global sre operations factory. Use when work  | Skill 1347 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-incident-command` | Implement and verify Batch 39 Skill 1356 for incident command. Use when work requires Inci | Skill 1356 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-job-fairness-tenant-isolation` | Implement and verify Batch 39 Skill 1352 for job fairness tenant isolation. Use when work  | Skill 1352 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-multiregion-failover` | Implement and verify Batch 39 Skill 1354 for multiregion failover. Use when work requires  | Skill 1354 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-oncall-follow-the-sun` | Implement and verify Batch 39 Skill 1358 for oncall follow the sun. Use when work requires | Skill 1358 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-operations-evidence-reporting` | Implement and verify Batch 39 Skill 1367 for operations evidence reporting. Use when work  | Skill 1367 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-platform-cost-anomaly-monitoring` | Implement and verify Batch 39 Skill 1362 for platform cost anomaly monitoring. Use when wo | Skill 1362 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-problem-root-cause-loop` | Implement and verify Batch 39 Skill 1357 for problem root cause loop. Use when work requir | Skill 1357 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-production-readiness-review` | Implement and verify Batch 39 Skill 1364 for production readiness review. Use when work re | Skill 1364 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-scheduled-restore-dr-exercise` | Implement and verify Batch 39 Skill 1366 for scheduled restore dr exercise. Use when work  | Skill 1366 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-service-catalog-sli-slo` | Implement and verify Batch 39 Skill 1348 for service catalog sli slo. Use when work requir | Skill 1348 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-sla-service-credit-governance` | Implement and verify Batch 39 Skill 1365 for sla service credit governance. Use when work  | Skill 1365 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b39-tenant-project-migration-health` | Implement and verify Batch 39 Skill 1351 for tenant project migration health. Use when wor | Skill 1351 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b40` (24 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b40-ai-model-supply-chain` | Implement and verify Batch 40 Skill 1386 for ai model supply chain. Use when work requires | Skill 1386 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-artifact-container-signing` | Implement and verify Batch 40 Skill 1382 for artifact container signing. Use when work req | Skill 1382 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-compliance-control-crosswalk` | Implement and verify Batch 40 Skill 1389 for compliance control crosswalk. Use when work r | Skill 1389 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-container-kubernetes-iac-scanning` | Implement and verify Batch 40 Skill 1378 for container kubernetes iac scanning. Use when w | Skill 1378 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-customer-audit-evidence` | Implement and verify Batch 40 Skill 1390 for customer audit evidence. Use when work requir | Skill 1390 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-dast-iast-integration` | Implement and verify Batch 40 Skill 1375 for dast iast integration. Use when work requires | Skill 1375 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-dependency-sca-governance` | Implement and verify Batch 40 Skill 1376 for dependency sca governance. Use when work requ | Skill 1376 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-independent-security-assessment` | Implement and verify Batch 40 Skill 1391 for independent security assessment. Use when wor | Skill 1391 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-isolated-trusted-builder` | Implement and verify Batch 40 Skill 1384 for isolated trusted builder. Use when work requi | Skill 1384 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-license-ip-provenance` | Implement and verify Batch 40 Skill 1381 for license ip provenance. Use when work requires | Skill 1381 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-psirt-security-incident` | Implement and verify Batch 40 Skill 1388 for psirt security incident. Use when work requir | Skill 1388 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-runner-update-supply-chain` | Implement and verify Batch 40 Skill 1385 for runner update supply chain. Use when work req | Skill 1385 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-sast-integration` | Implement and verify Batch 40 Skill 1374 for sast integration. Use when work requires SAST | Skill 1374 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-sbom-component-identity` | Implement and verify Batch 40 Skill 1379 for sbom component identity. Use when work requir | Skill 1379 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-secret-credential-scanning` | Implement and verify Batch 40 Skill 1377 for secret credential scanning. Use when work req | Skill 1377 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-secure-code-review-approval` | Implement and verify Batch 40 Skill 1373 for secure code review approval. Use when work re | Skill 1373 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-secure-sdlc-ssdf` | Implement and verify Batch 40 Skill 1370 for secure sdlc ssdf. Use when work requires Secu | Skill 1370 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-security-architecture-review` | Implement and verify Batch 40 Skill 1372 for security architecture review. Use when work r | Skill 1372 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-security-supply-chain-gate` | Implement and verify Batch 40 Skill 1392 for security supply chain gate. Use when work req | Skill 1392 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-slsa-provenance` | Implement and verify Batch 40 Skill 1383 for slsa provenance. Use when work requires SLSA  | Skill 1383 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-supply-chain-compliance-factory` | Implement and verify Batch 40 Skill 1369 for supply chain compliance factory. Use when wor | Skill 1369 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-threat-modeling` | Implement and verify Batch 40 Skill 1371 for threat modeling. Use when work requires Threa | Skill 1371 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-vex-applicability` | Implement and verify Batch 40 Skill 1380 for vex applicability. Use when work requires VEX | Skill 1380 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b40-vulnerability-patch-sla` | Implement and verify Batch 40 Skill 1387 for vulnerability patch sla. Use when work requir | Skill 1387 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b41` (20 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b41-automation-buildgreen-prediction` | Implement and verify Batch 41 Skill 1401 for automation buildgreen prediction. Use when wo | Skill 1401 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-diagnostic-root-cause-recommendation` | Implement and verify Batch 41 Skill 1404 for diagnostic root cause recommendation. Use whe | Skill 1404 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-effort-duration-cost-prediction` | Implement and verify Batch 41 Skill 1402 for effort duration cost prediction. Use when wor | Skill 1402 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-holdout-feedback-calibration` | Implement and verify Batch 41 Skill 1409 for holdout feedback calibration. Use when work r | Skill 1409 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-human-curation-governance` | Implement and verify Batch 41 Skill 1410 for human curation governance. Use when work requ | Skill 1410 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-knowledge-confidence-provenance` | Implement and verify Batch 41 Skill 1405 for knowledge confidence provenance. Use when wor | Skill 1405 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-knowledge-flywheel-gate` | Implement and verify Batch 41 Skill 1412 for knowledge flywheel gate. Use when work requir | Skill 1412 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-knowledge-freshness-versioning` | Implement and verify Batch 41 Skill 1406 for knowledge freshness versioning. Use when work | Skill 1406 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-knowledge-graph-ontology` | Implement and verify Batch 41 Skill 1394 for knowledge graph ontology. Use when work requi | Skill 1394 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-knowledge-isolation` | Implement and verify Batch 41 Skill 1407 for knowledge isolation. Use when work requires \ | Skill 1407 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-knowledge-marketplace-sharing` | Implement and verify Batch 41 Skill 1411 for knowledge marketplace sharing. Use when work  | Skill 1411 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-migration-entity-relations` | Implement and verify Batch 41 Skill 1395 for migration entity relations. Use when work req | Skill 1395 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-migration-knowledge-factory` | Implement and verify Batch 41 Skill 1393 for migration knowledge factory. Use when work re | Skill 1393 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-migration-risk-prediction` | Implement and verify Batch 41 Skill 1400 for migration risk prediction. Use when work requ | Skill 1400 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-migration-run-ingestion` | Implement and verify Batch 41 Skill 1396 for migration run ingestion. Use when work requir | Skill 1396 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-pattern-antipattern-extraction` | Implement and verify Batch 41 Skill 1397 for pattern antipattern extraction. Use when work | Skill 1397 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-privacy-preserving-learning` | Implement and verify Batch 41 Skill 1408 for privacy preserving learning. Use when work re | Skill 1408 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-recipe-mapping-recommendation` | Implement and verify Batch 41 Skill 1398 for recipe mapping recommendation. Use when work  | Skill 1398 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-similar-project-retrieval` | Implement and verify Batch 41 Skill 1399 for similar project retrieval. Use when work requ | Skill 1399 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b41-target-stack-recommendation` | Implement and verify Batch 41 Skill 1403 for target stack recommendation. Use when work re | Skill 1403 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b42` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b42-agent-autonomy-levels` | Implement and verify Batch 42 Skill 1432 for agent autonomy levels. Use when work requires | Skill 1432 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-budget-resource-limits` | Implement and verify Batch 42 Skill 1426 for agent budget resource limits. Use when work r | Skill 1426 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-eval-benchmark` | Implement and verify Batch 42 Skill 1427 for agent eval benchmark. Use when work requires  | Skill 1427 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-factory-gate` | Implement and verify Batch 42 Skill 1434 for agent factory gate. Use when work requires Ba | Skill 1434 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-incident-killswitch-rollback` | Implement and verify Batch 42 Skill 1430 for agent incident killswitch rollback. Use when  | Skill 1430 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-memory-state-governance` | Implement and verify Batch 42 Skill 1424 for agent memory state governance. Use when work  | Skill 1424 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-migration-factory` | Implement and verify Batch 42 Skill 1413 for agent migration factory. Use when work requir | Skill 1413 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-red-team` | Implement and verify Batch 42 Skill 1429 for agent red team. Use when work requires Agent  | Skill 1429 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-shadow-canary` | Implement and verify Batch 42 Skill 1428 for agent shadow canary. Use when work requires S | Skill 1428 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-team-topology` | Implement and verify Batch 42 Skill 1414 for agent team topology. Use when work requires A | Skill 1414 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-agent-tool-permissions` | Implement and verify Batch 42 Skill 1422 for agent tool permissions. Use when work require | Skill 1422 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-deterministic-execution-agent` | Implement and verify Batch 42 Skill 1416 for deterministic execution agent. Use when work  | Skill 1416 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-human-approval-takeover` | Implement and verify Batch 42 Skill 1421 for human approval takeover. Use when work requir | Skill 1421 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-language-framework-specialist-agent` | Implement and verify Batch 42 Skill 1417 for language framework specialist agent. Use when | Skill 1417 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-migration-planner-agent` | Implement and verify Batch 42 Skill 1415 for migration planner agent. Use when work requir | Skill 1415 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-minimal-context-evidence` | Implement and verify Batch 42 Skill 1423 for minimal context evidence. Use when work requi | Skill 1423 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-model-routing-provider-failover` | Implement and verify Batch 42 Skill 1425 for model routing provider failover. Use when wor | Skill 1425 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-multiagent-consensus-arbitration` | Implement and verify Batch 42 Skill 1433 for multiagent consensus arbitration. Use when wo | Skill 1433 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-policy-enforcement-agent` | Implement and verify Batch 42 Skill 1419 for policy enforcement agent. Use when work requi | Skill 1419 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-recipe-candidate-agent` | Implement and verify Batch 42 Skill 1431 for recipe candidate agent. Use when work require | Skill 1431 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-supervisor-coordination-agent` | Implement and verify Batch 42 Skill 1420 for supervisor coordination agent. Use when work  | Skill 1420 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b42-verification-agent` | Implement and verify Batch 42 Skill 1418 for verification agent. Use when work requires Ve | Skill 1418 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b43` (20 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b43-automated-upgrade-tooling` | Implement and verify Batch 43 Skill 1448 for automated upgrade tooling. Use when work requ | Skill 1448 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-compatibility-test-matrix` | Implement and verify Batch 43 Skill 1452 for compatibility test matrix. Use when work requ | Skill 1452 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-customer-upgrade-readiness` | Implement and verify Batch 43 Skill 1447 for customer upgrade readiness. Use when work req | Skill 1447 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-database-migration-compatibility` | Implement and verify Batch 43 Skill 1443 for database migration compatibility. Use when wo | Skill 1443 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-deprecation-removal` | Implement and verify Batch 43 Skill 1446 for deprecation removal. Use when work requires D | Skill 1446 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-event-schema-compatibility` | Implement and verify Batch 43 Skill 1438 for event schema compatibility. Use when work req | Skill 1438 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-feature-flag-progressive-enable` | Implement and verify Batch 43 Skill 1449 for feature flag progressive enable. Use when wor | Skill 1449 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-product-lifecycle-factory` | Implement and verify Batch 43 Skill 1435 for product lifecycle factory. Use when work requ | Skill 1435 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-product-lifecycle-gate` | Implement and verify Batch 43 Skill 1454 for product lifecycle gate. Use when work require | Skill 1454 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-psp-uir-schema-compatibility` | Implement and verify Batch 43 Skill 1441 for psp uir schema compatibility. Use when work r | Skill 1441 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-public-api-compatibility` | Implement and verify Batch 43 Skill 1437 for public api compatibility. Use when work requi | Skill 1437 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-recipe-pack-extension-compatibility` | Implement and verify Batch 43 Skill 1442 for recipe pack extension compatibility. Use when | Skill 1442 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-release-channel-governance` | Implement and verify Batch 43 Skill 1444 for release channel governance. Use when work req | Skill 1444 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-release-documentation` | Implement and verify Batch 43 Skill 1453 for release documentation. Use when work requires | Skill 1453 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-rolling-mixed-version-upgrade` | Implement and verify Batch 43 Skill 1450 for rolling mixed version upgrade. Use when work  | Skill 1450 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-runner-protocol-compatibility` | Implement and verify Batch 43 Skill 1440 for runner protocol compatibility. Use when work  | Skill 1440 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-sdk-compatibility` | Implement and verify Batch 43 Skill 1439 for sdk compatibility. Use when work requires SDK | Skill 1439 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-security-fix-backport` | Implement and verify Batch 43 Skill 1451 for security fix backport. Use when work requires | Skill 1451 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-support-eol-policy` | Implement and verify Batch 43 Skill 1445 for support eol policy. Use when work requires \u | Skill 1445 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b43-version-specification` | Implement and verify Batch 43 Skill 1436 for version specification. Use when work requires | Skill 1436 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b44` (20 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b44-artifact-retention-egress-economics` | Implement and verify Batch 44 Skill 1462 for artifact retention egress economics. Use when | Skill 1462 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-assessment-poc-project-quote` | Implement and verify Batch 44 Skill 1466 for assessment poc project quote. Use when work r | Skill 1466 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-budget-quota-cost-guardrail` | Implement and verify Batch 44 Skill 1468 for budget quota cost guardrail. Use when work re | Skill 1468 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-cache-incremental-cost-optimization` | Implement and verify Batch 44 Skill 1469 for cache incremental cost optimization. Use when | Skill 1469 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-cost-scenario-forecast` | Implement and verify Batch 44 Skill 1471 for cost scenario forecast. Use when work require | Skill 1471 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-cost-taxonomy-economic-model` | Implement and verify Batch 44 Skill 1456 for cost taxonomy economic model. Use when work r | Skill 1456 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-customer-roi-tco-value` | Implement and verify Batch 44 Skill 1472 for customer roi tco value. Use when work require | Skill 1472 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-customer-route-edition-margin` | Implement and verify Batch 44 Skill 1467 for customer route edition margin. Use when work  | Skill 1467 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-economics-maturity-gate` | Implement and verify Batch 44 Skill 1474 for economics maturity gate. Use when work requir | Skill 1474 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-human-expert-cost` | Implement and verify Batch 44 Skill 1463 for human expert cost. Use when work requires \u4 | Skill 1463 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-migration-finops-factory` | Implement and verify Batch 44 Skill 1455 for migration finops factory. Use when work requi | Skill 1455 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-model-agent-economics` | Implement and verify Batch 44 Skill 1461 for model agent economics. Use when work requires | Skill 1461 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-packaging-pricing-model` | Implement and verify Batch 44 Skill 1465 for packaging pricing model. Use when work requir | Skill 1465 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-provider-resource-routing` | Implement and verify Batch 44 Skill 1470 for provider resource routing. Use when work requ | Skill 1470 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-resource-metering` | Implement and verify Batch 44 Skill 1457 for resource metering. Use when work requires Run | Skill 1457 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-runner-fleet-economics` | Implement and verify Batch 44 Skill 1460 for runner fleet economics. Use when work require | Skill 1460 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-showback-chargeback` | Implement and verify Batch 44 Skill 1458 for showback chargeback. Use when work requires \ | Skill 1458 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-support-hypercare-operations-cost` | Implement and verify Batch 44 Skill 1464 for support hypercare operations cost. Use when w | Skill 1464 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-usage-billing-reconciliation` | Implement and verify Batch 44 Skill 1473 for usage billing reconciliation. Use when work r | Skill 1473 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b44-verified-workload-unit-cost` | Implement and verify Batch 44 Skill 1459 for verified workload unit cost. Use when work re | Skill 1459 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b45` (22 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b45-customer-value-certification` | Implement and verify Batch 45 Skill 1488 for customer value certification. Use when work r | Skill 1488 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-deployment-matrix-certification` | Implement and verify Batch 45 Skill 1485 for deployment matrix certification. Use when wor | Skill 1485 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-design-partner-reference-validation` | Implement and verify Batch 45 Skill 1489 for design partner reference validation. Use when | Skill 1489 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-developer-experience-certification` | Implement and verify Batch 45 Skill 1484 for developer experience certification. Use when  | Skill 1484 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-economics-profitability-certification` | Implement and verify Batch 45 Skill 1487 for economics profitability certification. Use wh | Skill 1487 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-ecosystem-certification` | Implement and verify Batch 45 Skill 1486 for ecosystem certification. Use when work requir | Skill 1486 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-edition-route-vertical-certification` | Implement and verify Batch 45 Skill 1495 for edition route vertical certification. Use whe | Skill 1495 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-functional-depth-certification` | Implement and verify Batch 45 Skill 1477 for functional depth certification. Use when work | Skill 1477 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-independent-expert-validation` | Implement and verify Batch 45 Skill 1490 for independent expert validation. Use when work  | Skill 1490 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-mature-product-certification` | Implement and verify Batch 45 Skill 1475 for mature product certification. Use when work r | Skill 1475 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-mature-product-evidence-pack` | Implement and verify Batch 45 Skill 1494 for mature product evidence pack. Use when work r | Skill 1494 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-mature-product-final-gate` | Implement and verify Batch 45 Skill 1496 for mature product final gate. Use when work requ | Skill 1496 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-mature-release-readiness` | Implement and verify Batch 45 Skill 1491 for mature release readiness. Use when work requi | Skill 1491 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-maturity-model-editions` | Implement and verify Batch 45 Skill 1476 for maturity model editions. Use when work requir | Skill 1476 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-product-governance-accountability` | Implement and verify Batch 45 Skill 1492 for product governance accountability. Use when w | Skill 1492 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-residual-risk-register` | Implement and verify Batch 45 Skill 1493 for residual risk register. Use when work require | Skill 1493 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-route-breadth-certification` | Implement and verify Batch 45 Skill 1478 for route breadth certification. Use when work re | Skill 1478 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-scale-performance-certification` | Implement and verify Batch 45 Skill 1480 for scale performance certification. Use when wor | Skill 1480 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-security-data-certification` | Implement and verify Batch 45 Skill 1481 for security data certification. Use when work re | Skill 1481 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-semantic-behavior-certification` | Implement and verify Batch 45 Skill 1479 for semantic behavior certification. Use when wor | Skill 1479 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-sre-reliability-dr-certification` | Implement and verify Batch 45 Skill 1482 for sre reliability dr certification. Use when wo | Skill 1482 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b45-target-maintainability-certification` | Implement and verify Batch 45 Skill 1483 for target maintainability certification. Use whe | Skill 1483 | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b81` (12 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b81-cics-transaction-modernizer` | Use when ELMOS must run cics transaction modernizer for Batch 81 COBOL / JCL / REXX / CICS | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-cobol-business-rule-recovery` | Use when ELMOS must run cobol business rule recovery for Batch 81 COBOL / JCL / REXX / CIC | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-cobol-parser-and-semantic-model` | Use when ELMOS must run cobol parser and semantic model for Batch 81 COBOL / JCL / REXX /  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-cobol-to-java-dotnet-generator` | Use when ELMOS must run cobol to java dotnet generator for Batch 81 COBOL / JCL / REXX / C | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-copybook-canonical-schema-compiler` | Use when ELMOS must run copybook canonical schema compiler for Batch 81 COBOL / JCL / REXX | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-ims-vsam-db2-data-adapter` | Use when ELMOS must run ims vsam db2 data adapter for Batch 81 COBOL / JCL / REXX / CICS / | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-jcl-batch-workflow-modeler` | Use when ELMOS must run jcl batch workflow modeler for Batch 81 COBOL / JCL / REXX / CICS  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-mainframe-api-event-extractor` | Use when ELMOS must run mainframe api event extractor for Batch 81 COBOL / JCL / REXX / CI | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-mainframe-cutover-decommission-planner` | Use when ELMOS must run mainframe cutover decommission planner for Batch 81 COBOL / JCL /  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-mainframe-estate-discovery-and-inventory` | Use when ELMOS must run mainframe estate discovery and inventory for Batch 81 COBOL / JCL  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-mainframe-parallel-run-verifier` | Use when ELMOS must run mainframe parallel run verifier for Batch 81 COBOL / JCL / REXX /  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b81-mainframe-security-operations-mapper` | Use when ELMOS must run mainframe security operations mapper for Batch 81 COBOL / JCL / RE | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b82` (12 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b82-abap-cloud-rap-generator` | Use when ELMOS must run abap cloud rap generator for Batch 82 SAP ABAP / ABAP Cloud / CDS  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-abap-dictionary-cds-modeler` | Use when ELMOS must run abap dictionary cds modeler for Batch 82 SAP ABAP / ABAP Cloud / C | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-abap-unit-atc-test-generator` | Use when ELMOS must run abap unit atc test generator for Batch 82 SAP ABAP / ABAP Cloud /  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-bapi-rfc-idoc-contract-extractor` | Use when ELMOS must run bapi rfc idoc contract extractor for Batch 82 SAP ABAP / ABAP Clou | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-classic-abap-parser-and-semantic-model` | Use when ELMOS must run classic abap parser and semantic model for Batch 82 SAP ABAP / ABA | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-custom-table-data-migration-planner` | Use when ELMOS must run custom table data migration planner for Batch 82 SAP ABAP / ABAP C | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-dynpro-to-fiori-ui-modernizer` | Use when ELMOS must run dynpro to fiori ui modernizer for Batch 82 SAP ABAP / ABAP Cloud / | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-enhancement-user-exit-clean-core-analyzer` | Use when ELMOS must run enhancement user exit clean core analyzer for Batch 82 SAP ABAP /  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-sap-btp-extension-generator` | Use when ELMOS must run sap btp extension generator for Batch 82 SAP ABAP / ABAP Cloud / C | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-sap-cutover-regression-certifier` | Use when ELMOS must run sap cutover regression certifier for Batch 82 SAP ABAP / ABAP Clou | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-sap-landscape-discovery-and-inventory` | Use when ELMOS must run sap landscape discovery and inventory for Batch 82 SAP ABAP / ABAP | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b82-transport-change-dependency-planner` | Use when ELMOS must run transport change dependency planner for Batch 82 SAP ABAP / ABAP C | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b83` (12 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b83-database-code-test-harness-generator` | Use when ELMOS must run database code test harness generator for Batch 83 PL/SQL / T-SQL / | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-database-logic-retain-refactor-extract-decider` | Use when ELMOS must run database logic retain refactor extract decider for Batch 83 PL/SQL | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-database-program-modernization-certifier` | Use when ELMOS must run database program modernization certifier for Batch 83 PL/SQL / T-S | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-database-program-unit-discovery` | Use when ELMOS must run database program unit discovery for Batch 83 PL/SQL / T-SQL / PL/p | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-dynamic-sql-injection-safety-analyzer` | Use when ELMOS must run dynamic sql injection safety analyzer for Batch 83 PL/SQL / T-SQL  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-plpgsql-sqlpl-parser-and-semantic-model` | Use when ELMOS must run plpgsql sqlpl parser and semantic model for Batch 83 PL/SQL / T-SQ | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-plsql-parser-and-semantic-model` | Use when ELMOS must run plsql parser and semantic model for Batch 83 PL/SQL / T-SQL / PL/p | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-procedure-to-service-generator` | Use when ELMOS must run procedure to service generator for Batch 83 PL/SQL / T-SQL / PL/pg | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-stored-procedure-business-rule-extractor` | Use when ELMOS must run stored procedure business rule extractor for Batch 83 PL/SQL / T-S | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-transaction-concurrency-equivalence-verifier` | Use when ELMOS must run transaction concurrency equivalence verifier for Batch 83 PL/SQL / | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-trigger-job-dblink-impact-analyzer` | Use when ELMOS must run trigger job dblink impact analyzer for Batch 83 PL/SQL / T-SQL / P | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b83-tsql-parser-and-semantic-model` | Use when ELMOS must run tsql parser and semantic model for Batch 83 PL/SQL / T-SQL / PL/pg | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |

### 批次 `b88` (12 个技能)

| 技能名称 | 核心职责 | 关键任务/验收ID | 宏观状态 | 细分状态 |
| :--- | :--- | :--- | :---: | :---: |
| `b88-5250-ui-to-web-modernizer` | Use when ELMOS must run 5250 ui to web modernizer for Batch 88 IBM i RPG / CL / DDS / DB2  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-cl-job-workflow-modeler` | Use when ELMOS must run cl job workflow modeler for Batch 88 IBM i RPG / CL / DDS / DB2 fo | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-cl-to-workflow-batch-generator` | Use when ELMOS must run cl to workflow batch generator for Batch 88 IBM i RPG / CL / DDS / | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-db2i-data-access-mapper` | Use when ELMOS must run db2i data access mapper for Batch 88 IBM i RPG / CL / DDS / DB2 fo | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-dds-display-printer-file-modeler` | Use when ELMOS must run dds display printer file modeler for Batch 88 IBM i RPG / CL / DDS | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-ibmi-cutover-certifier` | Use when ELMOS must run ibmi cutover certifier for Batch 88 IBM i RPG / CL / DDS / DB2 for | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-ibmi-integration-adapter` | Use when ELMOS must run ibmi integration adapter for Batch 88 IBM i RPG / CL / DDS / DB2 f | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-ibmi-landscape-discovery-and-inventory` | Use when ELMOS must run ibmi landscape discovery and inventory for Batch 88 IBM i RPG / CL | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-ibmi-parallel-run-record-verifier` | Use when ELMOS must run ibmi parallel run record verifier for Batch 88 IBM i RPG / CL / DD | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-ile-service-program-binding-analyzer` | Use when ELMOS must run ile service program binding analyzer for Batch 88 IBM i RPG / CL / | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-rpg-parser-and-semantic-model` | Use when ELMOS must run rpg parser and semantic model for Batch 88 IBM i RPG / CL / DDS /  | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
| `b88-rpg-to-java-dotnet-generator` | Use when ELMOS must run rpg to java dotnet generator for Batch 88 IBM i RPG / CL / DDS / D | - | `[VERIFIED / CODE_COMPLETE]` | `VERIFIED` |
