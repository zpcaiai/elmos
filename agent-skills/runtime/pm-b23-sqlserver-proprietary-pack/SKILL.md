---
name: pm-b23-sqlserver-proprietary-pack
description: "识别 T-SQL 和 SQL Server 平台能力，形成目标数据库或外部平台的安全迁移策略. Precision Migration B23 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 23：SQL Server专有能力包
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b23-sqlserver-proprietary-pack`.
- Immutable source identity: `batch-23-sqlserver-proprietary-pack` in `precision-migration-b01-44` (B23).
- Runtime adapter: `database-and-data-route`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b23-sqlserver-proprietary-pack`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

识别 T-SQL 和 SQL Server 平台能力，形成目标数据库或外部平台的安全迁移策略。

## Position in the system

- Phase: `G 数据库精密互转`
- Included skills: `17`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 盘点对象与专有能力
2. Lower到Database Semantic IR
3. 应用有方向数据库包
4. 执行双库数据/过程差分
5. 评估计划、性能、CDC、切换和回滚

## Shared gates

- NULL、空字符串、时间、精度和Collation必须专项验证
- 复杂过程必须比较状态和副作用
- 性能与并发退化不能被功能通过掩盖

## Dispatch rules

- 当任务涉及 **sqlserver-tsql** 时，调用 `../pm-b23-sqlserver-tsql/SKILL.md`。
- 当任务涉及 **sqlserver-identity-and-sequence** 时，调用 `../pm-b23-sqlserver-identity-and-sequence/SKILL.md`。
- 当任务涉及 **sqlserver-merge** 时，调用 `../pm-b23-sqlserver-merge/SKILL.md`。
- 当任务涉及 **sqlserver-try-catch** 时，调用 `../pm-b23-sqlserver-try-catch/SKILL.md`。
- 当任务涉及 **sqlserver-table-variable** 时，调用 `../pm-b23-sqlserver-table-variable/SKILL.md`。
- 当任务涉及 **sqlserver-temporary-table** 时，调用 `../pm-b23-sqlserver-temporary-table/SKILL.md`。
- 当任务涉及 **sqlserver-agent** 时，调用 `../pm-b23-sqlserver-agent/SKILL.md`。
- 当任务涉及 **sqlserver-service-broker** 时，调用 `../pm-b23-sqlserver-service-broker/SKILL.md`。
- 当任务涉及 **sqlserver-clr-stored-procedure** 时，调用 `../pm-b23-sqlserver-clr-stored-procedure/SKILL.md`。
- 当任务涉及 **sqlserver-linked-server** 时，调用 `../pm-b23-sqlserver-linked-server/SKILL.md`。
- 当任务涉及 **sqlserver-indexed-view** 时，调用 `../pm-b23-sqlserver-indexed-view/SKILL.md`。
- 当任务涉及 **sqlserver-temporal-table** 时，调用 `../pm-b23-sqlserver-temporal-table/SKILL.md`。
- 当任务涉及 **sqlserver-cdc-and-change-tracking** 时，调用 `../pm-b23-sqlserver-cdc-and-change-tracking/SKILL.md`。
- 当任务涉及 **sqlserver-row-level-security** 时，调用 `../pm-b23-sqlserver-row-level-security/SKILL.md`。
- 当任务涉及 **sqlserver-always-encrypted** 时，调用 `../pm-b23-sqlserver-always-encrypted/SKILL.md`。
- 当任务涉及 **sqlserver-ssis-dependency** 时，调用 `../pm-b23-sqlserver-ssis-dependency/SKILL.md`。
- 当任务涉及 **sqlserver-query-hint-and-plan** 时，调用 `../pm-b23-sqlserver-query-hint-and-plan/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `sqlserver-tsql` | 迁移 T-SQL 语法、批次、变量、函数、错误和系统对象。 |
| `sqlserver-identity-and-sequence` | 迁移 IDENTITY、Sequence、SET IDENTITY_INSERT 和取号行为。 |
| `sqlserver-merge` | 迁移 MERGE，并评估并发、重复匹配和目标平台安全替代。 |
| `sqlserver-try-catch` | 迁移 TRY/CATCH、THROW、RAISERROR、XACT_STATE 和错误语义。 |
| `sqlserver-table-variable` | 迁移 Table Variable、统计、作用域和性能行为。 |
| `sqlserver-temporary-table` | 迁移本地/全局临时表、生命周期、统计、并发和缓存。 |
| `sqlserver-agent` | 迁移 SQL Agent Job、Step、Schedule、Operator、Proxy 和历史。 |
| `sqlserver-service-broker` | 迁移 Service Broker 队列、会话、合同、事务和激活。 |
| `sqlserver-clr-stored-procedure` | 迁移 SQL CLR、程序集、权限集和外部代码依赖。 |
| `sqlserver-linked-server` | 迁移 Linked Server、四段名、OPENQUERY、权限和分布式事务。 |
| `sqlserver-indexed-view` | 迁移 Indexed View、Schema binding、限制和优化器使用。 |
| `sqlserver-temporal-table` | 迁移系统版本时间表、历史表、查询和保留策略。 |
| `sqlserver-cdc-and-change-tracking` | 迁移 CDC、Change Tracking、位点、保留和消费接口。 |
| `sqlserver-row-level-security` | 迁移 Predicate Function、Security Policy 和上下文。 |
| `sqlserver-always-encrypted` | 迁移 Always Encrypted、密钥、驱动端加解密和查询限制。 |
| `sqlserver-ssis-dependency` | 识别并迁移 SSIS Package、连接、数据流、控制流和调度依赖。 |
| `sqlserver-query-hint-and-plan` | 处理 NOLOCK、UPDLOCK、INDEX、RECOMPILE、Plan Guide 和目标执行计划。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
