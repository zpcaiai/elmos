---
name: batch-20-database-schema-data-migration
description: 完成 Schema、数据类型、对象、全量、增量、校验、切换和回滚的基础迁移闭环。
---

# Batch 20：数据库Schema与数据迁移基础

## Goal

完成 Schema、数据类型、对象、全量、增量、校验、切换和回滚的基础迁移闭环。

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

- 当任务涉及 **schema-inventory** 时，调用 `skills/schema-inventory/SKILL.md`。
- 当任务涉及 **data-type-mapping** 时，调用 `skills/data-type-mapping/SKILL.md`。
- 当任务涉及 **table-and-constraint-converter** 时，调用 `skills/table-and-constraint-converter/SKILL.md`。
- 当任务涉及 **index-and-partition-converter** 时，调用 `skills/index-and-partition-converter/SKILL.md`。
- 当任务涉及 **view-and-materialized-view-converter** 时，调用 `skills/view-and-materialized-view-converter/SKILL.md`。
- 当任务涉及 **sequence-and-identity-converter** 时，调用 `skills/sequence-and-identity-converter/SKILL.md`。
- 当任务涉及 **data-profile-and-quality-analysis** 时，调用 `skills/data-profile-and-quality-analysis/SKILL.md`。
- 当任务涉及 **full-load-migration** 时，调用 `skills/full-load-migration/SKILL.md`。
- 当任务涉及 **incremental-cdc-migration** 时，调用 `skills/incremental-cdc-migration/SKILL.md`。
- 当任务涉及 **data-checksum-validation** 时，调用 `skills/data-checksum-validation/SKILL.md`。
- 当任务涉及 **row-level-differential-validation** 时，调用 `skills/row-level-differential-validation/SKILL.md`。
- 当任务涉及 **cutover-and-rollback-plan** 时，调用 `skills/cutover-and-rollback-plan/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `schema-inventory` | 盘点数据库对象、依赖、大小、变更频率、权限、过程代码和专有能力。 |
| `data-type-mapping` | 映射数据类型、精度、Scale、编码、时区、NULL、默认值和边界行为。 |
| `table-and-constraint-converter` | 转换表、列、主外键、唯一、检查、默认值和依赖顺序。 |
| `index-and-partition-converter` | 转换索引、分区、聚簇、表达式、部分索引和存储布局。 |
| `view-and-materialized-view-converter` | 转换普通视图、物化视图、刷新策略、权限和依赖。 |
| `sequence-and-identity-converter` | 转换 Sequence、Identity、Auto Increment 和应用取号方式。 |
| `data-profile-and-quality-analysis` | 分析 NULL、空字符串、越界、重复、孤儿、编码、时区和数据倾斜。 |
| `full-load-migration` | 规划和执行可恢复、可分片、可校验的全量数据迁移。 |
| `incremental-cdc-migration` | 规划和执行日志/触发器/时间戳增量迁移及位点恢复。 |
| `data-checksum-validation` | 执行表级、分区级、列级和业务聚合校验。 |
| `row-level-differential-validation` | 对关键表执行行级规范化 Diff，并分类差异。 |
| `cutover-and-rollback-plan` | 设计停机、低停机、双写、切流、回滚和数据收敛方案。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
