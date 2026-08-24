# Skill Index

Package version: **1.0.0**  
Total skills: **46**

| # | Skill | Group | Depends on | Main outputs |
|---:|---|---|---|---|
| 1 | `elmos-data-requirement-intake`<br>数据需求摄取与 Workload Requirement IR | database-intelligence | — | `workload-requirements.json`<br>`source-inventory.json`<br>`assumptions-and-gaps.md` |
| 2 | `elmos-workload-profiler`<br>数据与查询工作负载画像 | database-intelligence | `elmos-data-requirement-intake` | `data-profile.json`<br>`query-profile.json`<br>`skew-and-hotspot-report.md` |
| 3 | `elmos-database-capability-registry`<br>数据库与数据技术能力注册表 | database-intelligence | — | `database-capabilities.json`<br>`technology-adapters.json`<br>`evidence-index.json` |
| 4 | `elmos-database-constraint-filter`<br>数据库硬约束过滤器 | database-intelligence | `elmos-data-requirement-intake`<br>`elmos-workload-profiler`<br>`elmos-database-capability-registry` | `feasible-candidates.json`<br>`rejected-candidates.json`<br>`constraint-proof.json` |
| 5 | `elmos-database-mcda-ranker`<br>多目标数据库排序与敏感性分析 | database-intelligence | `elmos-database-constraint-filter` | `candidate-ranking.json`<br>`pareto-frontier.json`<br>`sensitivity-report.md` |
| 6 | `elmos-polyglot-persistence-planner`<br>多模数据库与数据所有权规划 | database-intelligence | `elmos-database-mcda-ranker` | `persistence-portfolio.json`<br>`data-ownership-map.md`<br>`synchronization-contracts.json` |
| 7 | `elmos-data-architecture-adr`<br>数据架构决策记录与证据 | database-intelligence | `elmos-polyglot-persistence-planner` | `ADR-data-architecture.md`<br>`decision-ledger.json`<br>`architecture-baseline.json` |
| 8 | `elmos-database-benchmark-harness`<br>数据库与数据引擎基准验证 | database-intelligence | `elmos-workload-profiler`<br>`elmos-database-capability-registry` | `benchmark-plan.json`<br>`benchmark-results.json`<br>`benchmark-report.md` |
| 9 | `elmos-database-cost-capacity-planner`<br>容量、TCO 与成本边界规划 | database-intelligence | `elmos-database-mcda-ranker`<br>`elmos-database-benchmark-harness` | `capacity-plan.json`<br>`tco-scenarios.json`<br>`cost-risk-report.md` |
| 10 | `elmos-database-schema-physical-design`<br>Schema、索引、分区与物理设计生成 | database-intelligence | `elmos-polyglot-persistence-planner` | `logical-model.json`<br>`physical-schema/`<br>`index-partition-plan.md` |
| 11 | `elmos-database-ha-dr`<br>数据库高可用、备份与灾难恢复 | database-intelligence | `elmos-polyglot-persistence-planner` | `ha-dr-topology.md`<br>`backup-policy.json`<br>`restore-runbook.md` |
| 12 | `elmos-database-security-multitenancy`<br>数据库安全与多租户隔离 | database-intelligence | `elmos-data-requirement-intake`<br>`elmos-polyglot-persistence-planner` | `database-security-model.md`<br>`tenant-isolation-policy.json`<br>`access-matrix.csv` |
| 13 | `elmos-database-migration-modernization`<br>数据库迁移、分拆与现代化 | database-intelligence | `elmos-polyglot-persistence-planner`<br>`elmos-database-schema-physical-design`<br>`elmos-database-ha-dr`<br>+1 more | `migration-dag.json`<br>`cutover-plan.md`<br>`rollback-plan.md` |
| 14 | `elmos-bigdata-project-classifier`<br>大数据项目类型与价值流分类 | bigdata-core | `elmos-data-requirement-intake`<br>`elmos-workload-profiler` | `bigdata-project-classification.json`<br>`scenario-map.md`<br>`capability-needs.json` |
| 15 | `elmos-bigdata-pattern-selector`<br>Lambda、Kappa、统一流批、湖仓与联邦模式选择 | bigdata-core | `elmos-bigdata-project-classifier`<br>`elmos-database-capability-registry`<br>`elmos-database-mcda-ranker` | `architecture-pattern-decision.json`<br>`dataflow-architecture.md`<br>`pattern-adr.md` |
| 16 | `elmos-ingestion-connector-planner`<br>多源数据采集与连接器规划 | bigdata-core | `elmos-bigdata-pattern-selector` | `ingestion-plan.json`<br>`connector-matrix.json`<br>`source-contracts/` |
| 17 | `elmos-cdc-event-backbone`<br>CDC、事件总线与数据契约 | bigdata-core | `elmos-ingestion-connector-planner`<br>`elmos-database-security-multitenancy` | `cdc-topology.md`<br>`event-contracts/`<br>`topic-design.json` |
| 18 | `elmos-batch-processing-generator`<br>离线批处理与 ETL/ELT 项目生成 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-ingestion-connector-planner`<br>`elmos-database-schema-physical-design` | `pipelines/batch/`<br>`batch-dag.json`<br>`incremental-strategy.md` |
| 19 | `elmos-stream-processing-generator`<br>实时流处理项目生成 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-cdc-event-backbone`<br>`elmos-database-schema-physical-design` | `pipelines/stream/`<br>`state-and-watermark-design.md`<br>`stream-tests/` |
| 20 | `elmos-lakehouse-generator`<br>数据湖与湖仓一体项目生成 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-ingestion-connector-planner`<br>`elmos-batch-processing-generator`<br>+1 more | `lakehouse/`<br>`table-layout-plan.json`<br>`catalog-design.md` |
| 21 | `elmos-warehouse-olap-serving`<br>数据仓库、实时 OLAP 与查询服务 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-lakehouse-generator`<br>`elmos-polyglot-persistence-planner` | `analytics-serving/`<br>`olap-model.json`<br>`materialization-plan.md` |
| 22 | `elmos-federated-query-data-fabric`<br>联邦查询、数据虚拟化与 Data Fabric 覆盖层 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-polyglot-persistence-planner`<br>`elmos-database-capability-registry` | `federation-topology.md`<br>`connector-catalog.json`<br>`pushdown-policy.json` |
| 23 | `elmos-data-modeling-semantic-layer`<br>数据建模、分层与语义指标 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-database-schema-physical-design`<br>`elmos-lakehouse-generator`<br>+1 more | `data-model/`<br>`metrics-catalog.json`<br>`semantic-layer/` |
| 24 | `elmos-metadata-catalog-lineage`<br>元数据、数据目录与端到端血缘 | bigdata-core | `elmos-data-modeling-semantic-layer` | `metadata-platform/`<br>`lineage-policy.json`<br>`ownership-map.json` |
| 25 | `elmos-data-quality-observability`<br>数据质量、可观测性与 Data SLO | bigdata-core | `elmos-data-modeling-semantic-layer`<br>`elmos-metadata-catalog-lineage` | `data-contracts/`<br>`quality-tests/`<br>`data-slos.json` |
| 26 | `elmos-orchestration-backfill-replay`<br>数据编排、回填、重放与幂等恢复 | bigdata-core | `elmos-ingestion-connector-planner`<br>`elmos-batch-processing-generator`<br>`elmos-stream-processing-generator`<br>+1 more | `orchestration/`<br>`backfill-plan.json`<br>`replay-runbook.md` |
| 27 | `elmos-feature-store-ml-pipeline`<br>特征平台、训练数据与在线推理管道 | bigdata-core | `elmos-data-modeling-semantic-layer`<br>`elmos-orchestration-backfill-replay` | `feature-platform/`<br>`feature-definitions/`<br>`training-datasets/` |
| 28 | `elmos-bigdata-api-dashboard`<br>数据 API、BI、可视化与实时大屏 | bigdata-core | `elmos-warehouse-olap-serving`<br>`elmos-data-modeling-semantic-layer` | `data-api/`<br>`dashboards/`<br>`bi-model/` |
| 29 | `elmos-bigdata-infra-deployment`<br>大数据基础设施、IaC 与多环境部署 | bigdata-core | `elmos-bigdata-pattern-selector`<br>`elmos-ingestion-connector-planner`<br>`elmos-cdc-event-backbone`<br>+5 more | `infra/`<br>`docker-compose.yml`<br>`helm/` |
| 30 | `elmos-bigdata-security-governance`<br>大数据安全、治理、生命周期与合规 | bigdata-core | `elmos-database-security-multitenancy`<br>`elmos-metadata-catalog-lineage`<br>`elmos-bigdata-infra-deployment` | `governance/`<br>`classification-policy.json`<br>`retention-policy.json` |
| 31 | `elmos-bigdata-test-validation`<br>大数据全栈测试与行为等价验证 | bigdata-core | `elmos-batch-processing-generator`<br>`elmos-stream-processing-generator`<br>`elmos-lakehouse-generator`<br>+4 more | `tests/`<br>`test-matrix.json`<br>`validation-report.md` |
| 32 | `elmos-bigdata-performance-chaos`<br>性能、压力、容量与混沌验证 | bigdata-core | `elmos-database-benchmark-harness`<br>`elmos-database-cost-capacity-planner`<br>`elmos-bigdata-infra-deployment`<br>+1 more | `performance-tests/`<br>`chaos-scenarios.json`<br>`capacity-envelope.json` |
| 33 | `elmos-bigdata-cost-autotuning`<br>大数据成本优化与安全自动调优 | bigdata-core | `elmos-database-cost-capacity-planner`<br>`elmos-data-quality-observability`<br>`elmos-bigdata-performance-chaos` | `optimization-plan.json`<br>`tuning-policies/`<br>`before-after-report.md` |
| 34 | `elmos-bigdata-auto-repair`<br>大数据故障诊断与受控自动修复 | bigdata-core | `elmos-data-quality-observability`<br>`elmos-orchestration-backfill-replay`<br>`elmos-bigdata-test-validation`<br>+2 more | `incident-bundle/`<br>`root-cause-ranking.json`<br>`repair-plan.json` |
| 35 | `elmos-bigdata-evidence-certification`<br>大数据项目证据包与生产认证 | bigdata-core | `elmos-data-architecture-adr`<br>`elmos-bigdata-security-governance`<br>`elmos-bigdata-test-validation`<br>+3 more | `evidence-bundle/`<br>`readiness-scorecard.json`<br>`production-certificate.md` |
| 36 | `elmos-bigdata-project-orchestrator`<br>数据库选型与大数据项目端到端编排 | orchestration | `elmos-data-requirement-intake`<br>`elmos-workload-profiler`<br>`elmos-database-capability-registry`<br>+26 more | `generated-project/`<br>`architecture-and-decisions/`<br>`evidence-bundle/` |
| 37 | `elmos-template-offline-warehouse`<br>离线企业数仓项目模板 | bigdata-templates | `elmos-bigdata-project-orchestrator` | `template-plan.json`<br>`generated-project/` |
| 38 | `elmos-template-realtime-analytics`<br>实时计算与实时分析模板 | bigdata-templates | `elmos-bigdata-project-orchestrator` | `template-plan.json`<br>`generated-project/` |
| 39 | `elmos-template-realtime-user-profile`<br>实时用户画像与 Customer 360 模板 | bigdata-templates | `elmos-bigdata-project-orchestrator`<br>`elmos-feature-store-ml-pipeline` | `template-plan.json`<br>`generated-project/` |
| 40 | `elmos-template-recommendation-system`<br>推荐系统数据与在线服务模板 | bigdata-templates | `elmos-bigdata-project-orchestrator`<br>`elmos-feature-store-ml-pipeline` | `template-plan.json`<br>`generated-project/` |
| 41 | `elmos-template-iot-timeseries`<br>IoT、工业与时序数据项目模板 | bigdata-templates | `elmos-bigdata-project-orchestrator` | `template-plan.json`<br>`generated-project/` |
| 42 | `elmos-template-fraud-risk`<br>实时风控与反欺诈数据项目模板 | bigdata-templates | `elmos-bigdata-project-orchestrator`<br>`elmos-feature-store-ml-pipeline` | `template-plan.json`<br>`generated-project/` |
| 43 | `elmos-template-log-observability`<br>日志、指标、Trace 与安全分析模板 | bigdata-templates | `elmos-bigdata-project-orchestrator` | `template-plan.json`<br>`generated-project/` |
| 44 | `elmos-template-data-governance-platform`<br>企业数据目录、质量、血缘与治理平台模板 | bigdata-templates | `elmos-bigdata-project-orchestrator` | `template-plan.json`<br>`generated-project/` |
| 45 | `elmos-template-vector-knowledge-analytics`<br>向量检索、知识与分析数据平台模板 | bigdata-templates | `elmos-bigdata-project-orchestrator` | `template-plan.json`<br>`generated-project/` |
| 46 | `elmos-template-cdc-migration-modernization`<br>CDC 迁移、实时复制与旧数据平台现代化模板 | bigdata-templates | `elmos-bigdata-project-orchestrator`<br>`elmos-database-migration-modernization` | `template-plan.json`<br>`generated-project/` |
