---
name: batch-26-database-direction-packs
description: 为 Oracle、SQL Server、MySQL 和 PostgreSQL 的 12 条有方向路径分别维护对象、过程、专有能力、数据、性能、切换和回滚。
---

# Batch 26：数据库12条有方向互转包

## Goal

为 Oracle、SQL Server、MySQL 和 PostgreSQL 的 12 条有方向路径分别维护对象、过程、专有能力、数据、性能、切换和回滚。

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

- 当任务涉及 **oracle-to-sqlserver-database-direction-pack** 时，调用 `skills/oracle-to-sqlserver-database-direction-pack/SKILL.md`。
- 当任务涉及 **oracle-to-mysql-database-direction-pack** 时，调用 `skills/oracle-to-mysql-database-direction-pack/SKILL.md`。
- 当任务涉及 **oracle-to-postgresql-database-direction-pack** 时，调用 `skills/oracle-to-postgresql-database-direction-pack/SKILL.md`。
- 当任务涉及 **sqlserver-to-oracle-database-direction-pack** 时，调用 `skills/sqlserver-to-oracle-database-direction-pack/SKILL.md`。
- 当任务涉及 **sqlserver-to-mysql-database-direction-pack** 时，调用 `skills/sqlserver-to-mysql-database-direction-pack/SKILL.md`。
- 当任务涉及 **sqlserver-to-postgresql-database-direction-pack** 时，调用 `skills/sqlserver-to-postgresql-database-direction-pack/SKILL.md`。
- 当任务涉及 **mysql-to-oracle-database-direction-pack** 时，调用 `skills/mysql-to-oracle-database-direction-pack/SKILL.md`。
- 当任务涉及 **mysql-to-sqlserver-database-direction-pack** 时，调用 `skills/mysql-to-sqlserver-database-direction-pack/SKILL.md`。
- 当任务涉及 **mysql-to-postgresql-database-direction-pack** 时，调用 `skills/mysql-to-postgresql-database-direction-pack/SKILL.md`。
- 当任务涉及 **postgresql-to-oracle-database-direction-pack** 时，调用 `skills/postgresql-to-oracle-database-direction-pack/SKILL.md`。
- 当任务涉及 **postgresql-to-sqlserver-database-direction-pack** 时，调用 `skills/postgresql-to-sqlserver-database-direction-pack/SKILL.md`。
- 当任务涉及 **postgresql-to-mysql-database-direction-pack** 时，调用 `skills/postgresql-to-mysql-database-direction-pack/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `oracle-to-sqlserver-database-direction-pack` | 提供从 Oracle 到 SQL Server 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `oracle-to-mysql-database-direction-pack` | 提供从 Oracle 到 MySQL 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `oracle-to-postgresql-database-direction-pack` | 提供从 Oracle 到 PostgreSQL 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `sqlserver-to-oracle-database-direction-pack` | 提供从 SQL Server 到 Oracle 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `sqlserver-to-mysql-database-direction-pack` | 提供从 SQL Server 到 MySQL 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `sqlserver-to-postgresql-database-direction-pack` | 提供从 SQL Server 到 PostgreSQL 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `mysql-to-oracle-database-direction-pack` | 提供从 MySQL 到 Oracle 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `mysql-to-sqlserver-database-direction-pack` | 提供从 MySQL 到 SQL Server 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `mysql-to-postgresql-database-direction-pack` | 提供从 MySQL 到 PostgreSQL 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `postgresql-to-oracle-database-direction-pack` | 提供从 PostgreSQL 到 Oracle 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `postgresql-to-sqlserver-database-direction-pack` | 提供从 PostgreSQL 到 SQL Server 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |
| `postgresql-to-mysql-database-direction-pack` | 提供从 PostgreSQL 到 MySQL 的数据库专用迁移包，覆盖 DDL、DML、过程代码、专有能力、数据迁移、性能、切换和回滚。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
