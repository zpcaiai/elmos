---
name: batch-19-database-semantic-ir
description: 建立厂商中立的数据库 Schema、SQL、过程代码、事务、专有能力、复制和性能语义表示。
---

# Batch 19：Database Semantic IR

## Goal

建立厂商中立的数据库 Schema、SQL、过程代码、事务、专有能力、复制和性能语义表示。

## Position in the system

- Phase: `G 数据库精密互转`
- Included skills: `12`
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

- 当任务涉及 **database-schema-ir** 时，调用 `skills/database-schema-ir/SKILL.md`。
- 当任务涉及 **sql-expression-ir** 时，调用 `skills/sql-expression-ir/SKILL.md`。
- 当任务涉及 **query-plan-ir** 时，调用 `skills/query-plan-ir/SKILL.md`。
- 当任务涉及 **database-type-system** 时，调用 `skills/database-type-system/SKILL.md`。
- 当任务涉及 **constraint-and-index-ir** 时，调用 `skills/constraint-and-index-ir/SKILL.md`。
- 当任务涉及 **transaction-isolation-ir** 时，调用 `skills/transaction-isolation-ir/SKILL.md`。
- 当任务涉及 **procedure-control-flow-ir** 时，调用 `skills/procedure-control-flow-ir/SKILL.md`。
- 当任务涉及 **trigger-and-event-ir** 时，调用 `skills/trigger-and-event-ir/SKILL.md`。
- 当任务涉及 **sequence-identity-ir** 时，调用 `skills/sequence-identity-ir/SKILL.md`。
- 当任务涉及 **database-security-ir** 时，调用 `skills/database-security-ir/SKILL.md`。
- 当任务涉及 **replication-and-cdc-ir** 时，调用 `skills/replication-and-cdc-ir/SKILL.md`。
- 当任务涉及 **database-effect-ir** 时，调用 `skills/database-effect-ir/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `database-schema-ir` | 表达 Schema、表、列、类型、默认值、约束、注释和依赖。 |
| `sql-expression-ir` | 表达查询、DML、表达式、函数、窗口、层级、JSON、空间和方言扩展。 |
| `query-plan-ir` | 表达访问路径、Join、排序、聚合、并行、统计、代价和运行时指标。 |
| `database-type-system` | 统一数据库数值、字符、日期、布尔、LOB、JSON、数组、空间和自定义类型。 |
| `constraint-and-index-ir` | 表达主外键、唯一、检查、索引、分区、聚簇、部分和表达式索引。 |
| `transaction-isolation-ir` | 表达隔离级别、锁、MVCC、保存点、死锁、重试和可见性。 |
| `procedure-control-flow-ir` | 表达存储过程、函数、游标、异常、动态 SQL、临时对象和事务控制流。 |
| `trigger-and-event-ir` | 表达行级/语句级、前/后触发器、事件调度、执行顺序和递归。 |
| `sequence-identity-ir` | 表达 Sequence、Identity、Auto Increment、缓存、回退和并发生成。 |
| `database-security-ir` | 表达用户、角色、授权、RLS、加密、审计和安全上下文。 |
| `replication-and-cdc-ir` | 表达日志、位点、快照、增量、顺序、冲突、Exactly-once 和切换。 |
| `database-effect-ir` | 表达 SQL 和过程代码对数据、事务、序列、外部系统和审计的副作用。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
