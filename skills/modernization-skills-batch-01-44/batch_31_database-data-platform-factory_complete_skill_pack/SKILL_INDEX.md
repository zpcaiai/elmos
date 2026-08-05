# Skill Index

Batch 31: **Database and Data-Platform Modernization Factory**

| # | Skill | Purpose | Risk |
|---:|---|---|---|
| 1 | `b31-database-data-platform-factory-orchestrator` | 编排本 Batch 的所有能力、前置证书、状态机、暂停恢复取消、人工门禁和最终证书。 | critical |
| 2 | `b31-database-data-platform-factory-domain-model` | 定义稳定 ID、版本化 Schema、状态、输入输出、Unknown 保留、摘要和兼容策略。 | high |
| 3 | `b31-database-data-platform-factory-discovery-inventory` | 从源码、制品、运行、配置、文档和人工声明中发现资产，保存分母、来源和未知项。 | medium |
| 4 | `b31-database-data-platform-factory-capability-planning` | 建立能力矩阵、候选方案、约束、依赖、优先级、成本与执行计划。 | high |
| 5 | `b31-database-data-platform-factory-deterministic-engine` | 实现可重放、稳定排序、内容寻址、幂等和有界执行的确定性核心。 | critical |
| 6 | `b31-database-data-platform-factory-adapter-provider` | 通过签名适配器连接语言、框架、数据库、云、工具或外部 Provider，保留能力边界。 | high |
| 7 | `b31-database-data-platform-factory-workflow-runtime` | 在统一 Durable Workflow 和隔离 Runner 中执行任务，管理租约、检查点、副作用和补偿。 | critical |
| 8 | `b31-database-data-platform-factory-lineage-reconciliation` | 连接输入、决策、变换、输出、验证和证书，处理差异、冲突、重放和对账。 | high |
| 9 | `b31-database-data-platform-factory-security-policy` | 落实默认拒绝、最小权限、租户隔离、Secret、供应链、隐私和策略执行。 | critical |
| 10 | `b31-database-data-platform-factory-human-approval` | 为高影响、不确定、不可逆和例外决策建立解释、审批、过期与责任边界。 | high |
| 11 | `b31-database-data-platform-factory-observability-economics` | 采集日志、Trace、指标、分母、SLO、资源、成本、人工工时和商业可行性。 | medium |
| 12 | `b31-database-data-platform-factory-corpus-benchmark` | 建设正例、负例、边界、Holdout、代表性和对抗性 Corpus，并执行基准和回归。 | high |
| 13 | `b31-database-data-platform-factory-failure-recovery` | 分类失败、隔离影响、保存证据、回滚到安全点、恢复运行并阻止假成功。 | critical |
| 14 | `b31-database-data-platform-factory-integration-api` | 提供版本化 API、事件、Webhook、SDK 和导入导出，保证幂等、鉴权和兼容。 | high |
| 15 | `b31-database-data-platform-factory-lifecycle-recertification` | 管理 draft、experimental、limited、certified、deprecated、retired、revoked 及证据过期传播。 | high |
| 16 | `b31-database-data-platform-factory-certification-gate` | 只依据不可变证据签发最强可证明状态；缺证据、未知或阻断项必须降级或拒绝。 | critical |

## Dependency Rule

所有 Skills 继承 `BATCH30_COMPATIBILITY.md`，并由 orchestrator 和 certification-gate 汇聚。
