---
name: batch-25-postgresql-proprietary-pack
description: 识别 PostgreSQL 过程语言、扩展、高级类型、索引、复制、FDW 和自定义能力并制定迁移策略。
---

# Batch 25：PostgreSQL专有能力包

## Goal

识别 PostgreSQL 过程语言、扩展、高级类型、索引、复制、FDW 和自定义能力并制定迁移策略。

## Position in the system

- Phase: `G 数据库精密互转`
- Included skills: `16`
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

- 当任务涉及 **postgresql-plpgsql** 时，调用 `skills/postgresql-plpgsql/SKILL.md`。
- 当任务涉及 **postgresql-extension** 时，调用 `skills/postgresql-extension/SKILL.md`。
- 当任务涉及 **postgresql-array-range-composite** 时，调用 `skills/postgresql-array-range-composite/SKILL.md`。
- 当任务涉及 **postgresql-jsonb** 时，调用 `skills/postgresql-jsonb/SKILL.md`。
- 当任务涉及 **postgresql-returning** 时，调用 `skills/postgresql-returning/SKILL.md`。
- 当任务涉及 **postgresql-on-conflict** 时，调用 `skills/postgresql-on-conflict/SKILL.md`。
- 当任务涉及 **postgresql-sequence-and-identity** 时，调用 `skills/postgresql-sequence-and-identity/SKILL.md`。
- 当任务涉及 **postgresql-partial-expression-index** 时，调用 `skills/postgresql-partial-expression-index/SKILL.md`。
- 当任务涉及 **postgresql-materialized-view** 时，调用 `skills/postgresql-materialized-view/SKILL.md`。
- 当任务涉及 **postgresql-listen-notify** 时，调用 `skills/postgresql-listen-notify/SKILL.md`。
- 当任务涉及 **postgresql-logical-replication** 时，调用 `skills/postgresql-logical-replication/SKILL.md`。
- 当任务涉及 **postgresql-logical-decoding** 时，调用 `skills/postgresql-logical-decoding/SKILL.md`。
- 当任务涉及 **postgresql-row-level-security** 时，调用 `skills/postgresql-row-level-security/SKILL.md`。
- 当任务涉及 **postgresql-foreign-data-wrapper** 时，调用 `skills/postgresql-foreign-data-wrapper/SKILL.md`。
- 当任务涉及 **postgresql-event-trigger** 时，调用 `skills/postgresql-event-trigger/SKILL.md`。
- 当任务涉及 **postgresql-custom-operator-and-type** 时，调用 `skills/postgresql-custom-operator-and-type/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `postgresql-plpgsql` | 迁移 PL/pgSQL 块、函数、过程、异常、动态 SQL 和事务限制。 |
| `postgresql-extension` | 盘点并迁移 Extension、版本、对象、权限、二进制依赖和替代方案。 |
| `postgresql-array-range-composite` | 迁移 Array、Range、Multirange、Composite 和相关操作符。 |
| `postgresql-jsonb` | 迁移 JSONB 存储、操作符、路径、GIN/GiST 索引和更新语义。 |
| `postgresql-returning` | 迁移 INSERT/UPDATE/DELETE RETURNING 和应用消费方式。 |
| `postgresql-on-conflict` | 迁移 ON CONFLICT 的冲突目标、排除表和并发语义。 |
| `postgresql-sequence-and-identity` | 迁移 Sequence、Identity、缓存、OWNED BY 和事务外取号。 |
| `postgresql-partial-expression-index` | 迁移 Partial/Expression Index、Predicate 和函数稳定性。 |
| `postgresql-materialized-view` | 迁移物化视图、并发刷新、唯一索引和刷新调度。 |
| `postgresql-listen-notify` | 迁移 LISTEN/NOTIFY 的会话、事务、负载限制和替代消息系统。 |
| `postgresql-logical-replication` | 迁移 Publication、Subscription、Slot、冲突和 DDL 管理。 |
| `postgresql-logical-decoding` | 迁移 Logical Decoding 插件、Slot、LSN、输出和消费恢复。 |
| `postgresql-row-level-security` | 迁移 Policy、USING、WITH CHECK、角色和安全上下文。 |
| `postgresql-foreign-data-wrapper` | 迁移 FDW、Foreign Server、User Mapping、Pushdown 和事务限制。 |
| `postgresql-event-trigger` | 迁移 Event Trigger、DDL 事件、命令标签和递归风险。 |
| `postgresql-custom-operator-and-type` | 迁移自定义 Type、Operator、Cast、Aggregate 和 Operator Class。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
