---
name: batch-24-mysql-proprietary-pack
description: 识别 MySQL 方言、InnoDB、SQL Mode、字符集、复制和平台专有对象并制定迁移策略。
---

# Batch 24：MySQL专有能力包

## Goal

识别 MySQL 方言、InnoDB、SQL Mode、字符集、复制和平台专有对象并制定迁移策略。

## Position in the system

- Phase: `G 数据库精密互转`
- Included skills: `15`
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

- 当任务涉及 **mysql-stored-procedure-and-function** 时，调用 `skills/mysql-stored-procedure-and-function/SKILL.md`。
- 当任务涉及 **mysql-trigger** 时，调用 `skills/mysql-trigger/SKILL.md`。
- 当任务涉及 **mysql-event-scheduler** 时，调用 `skills/mysql-event-scheduler/SKILL.md`。
- 当任务涉及 **mysql-auto-increment** 时，调用 `skills/mysql-auto-increment/SKILL.md`。
- 当任务涉及 **mysql-enum-and-set** 时，调用 `skills/mysql-enum-and-set/SKILL.md`。
- 当任务涉及 **mysql-generated-column** 时，调用 `skills/mysql-generated-column/SKILL.md`。
- 当任务涉及 **mysql-json** 时，调用 `skills/mysql-json/SKILL.md`。
- 当任务涉及 **mysql-spatial** 时，调用 `skills/mysql-spatial/SKILL.md`。
- 当任务涉及 **mysql-on-duplicate-key** 时，调用 `skills/mysql-on-duplicate-key/SKILL.md`。
- 当任务涉及 **mysql-character-set-and-collation** 时，调用 `skills/mysql-character-set-and-collation/SKILL.md`。
- 当任务涉及 **mysql-innodb-transaction-behavior** 时，调用 `skills/mysql-innodb-transaction-behavior/SKILL.md`。
- 当任务涉及 **mysql-implicit-type-conversion** 时，调用 `skills/mysql-implicit-type-conversion/SKILL.md`。
- 当任务涉及 **mysql-sql-mode** 时，调用 `skills/mysql-sql-mode/SKILL.md`。
- 当任务涉及 **mysql-partition** 时，调用 `skills/mysql-partition/SKILL.md`。
- 当任务涉及 **mysql-replication-and-binlog** 时，调用 `skills/mysql-replication-and-binlog/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `mysql-stored-procedure-and-function` | 迁移 MySQL Procedure、Function、变量、游标、Handler 和事务。 |
| `mysql-trigger` | 迁移 MySQL Trigger 的时机、粒度、OLD/NEW、顺序和限制。 |
| `mysql-event-scheduler` | 迁移 Event Scheduler、时区、重复规则和失败处理。 |
| `mysql-auto-increment` | 迁移 AUTO_INCREMENT、步长、偏移、锁模式和复制行为。 |
| `mysql-enum-and-set` | 迁移 ENUM/SET 的顺序、隐式数值、校验和 Schema 演进。 |
| `mysql-generated-column` | 迁移虚拟/存储 Generated Column、表达式和索引。 |
| `mysql-json` | 迁移 JSON 类型、路径、函数、索引和比较语义。 |
| `mysql-spatial` | 迁移空间类型、SRID、函数、索引和坐标语义。 |
| `mysql-on-duplicate-key` | 迁移 ON DUPLICATE KEY UPDATE 的冲突目标、受影响行和触发器行为。 |
| `mysql-character-set-and-collation` | 迁移字符集、Collation、大小写、重音、尾空格和索引限制。 |
| `mysql-innodb-transaction-behavior` | 迁移 InnoDB MVCC、锁、间隙锁、隔离和死锁重试。 |
| `mysql-implicit-type-conversion` | 检测并消除 MySQL 宽松隐式转换、零日期和比较差异。 |
| `mysql-sql-mode` | 迁移 STRICT、ONLY_FULL_GROUP_BY、NO_ZERO_DATE 等 SQL Mode 影响。 |
| `mysql-partition` | 迁移分区类型、分区裁剪、唯一键限制和维护操作。 |
| `mysql-replication-and-binlog` | 迁移 Binlog 格式、GTID、复制拓扑、过滤、冲突和 CDC。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
