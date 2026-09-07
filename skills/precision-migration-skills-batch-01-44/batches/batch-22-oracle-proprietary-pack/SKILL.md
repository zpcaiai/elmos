---
name: batch-22-oracle-proprietary-pack
description: 识别 Oracle 专有能力并为每项选择直接映射、重写、模拟、外置服务、保留 Oracle 或不支持。
---

# Batch 22：Oracle专有能力包

## Goal

识别 Oracle 专有能力并为每项选择直接映射、重写、模拟、外置服务、保留 Oracle 或不支持。

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

- 当任务涉及 **oracle-plsql-package-and-state** 时，调用 `skills/oracle-plsql-package-and-state/SKILL.md`。
- 当任务涉及 **oracle-autonomous-transaction** 时，调用 `skills/oracle-autonomous-transaction/SKILL.md`。
- 当任务涉及 **oracle-sequence** 时，调用 `skills/oracle-sequence/SKILL.md`。
- 当任务涉及 **oracle-synonym** 时，调用 `skills/oracle-synonym/SKILL.md`。
- 当任务涉及 **oracle-database-link** 时，调用 `skills/oracle-database-link/SKILL.md`。
- 当任务涉及 **oracle-materialized-view** 时，调用 `skills/oracle-materialized-view/SKILL.md`。
- 当任务涉及 **oracle-object-type** 时，调用 `skills/oracle-object-type/SKILL.md`。
- 当任务涉及 **oracle-collection** 时，调用 `skills/oracle-collection/SKILL.md`。
- 当任务涉及 **oracle-bulk-collect-forall** 时，调用 `skills/oracle-bulk-collect-forall/SKILL.md`。
- 当任务涉及 **oracle-hierarchical-query** 时，调用 `skills/oracle-hierarchical-query/SKILL.md`。
- 当任务涉及 **oracle-flashback** 时，调用 `skills/oracle-flashback/SKILL.md`。
- 当任务涉及 **oracle-advanced-queue** 时，调用 `skills/oracle-advanced-queue/SKILL.md`。
- 当任务涉及 **oracle-scheduler** 时，调用 `skills/oracle-scheduler/SKILL.md`。
- 当任务涉及 **oracle-fine-grained-access-control** 时，调用 `skills/oracle-fine-grained-access-control/SKILL.md`。
- 当任务涉及 **oracle-null-and-date-semantics** 时，调用 `skills/oracle-null-and-date-semantics/SKILL.md`。
- 当任务涉及 **oracle-feature-migration-decision** 时，调用 `skills/oracle-feature-migration-decision/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `oracle-plsql-package-and-state` | 迁移 PL/SQL Package、公开/私有成员、初始化和会话级 Package State。 |
| `oracle-autonomous-transaction` | 分析并迁移 Autonomous Transaction 的独立提交、可见性和审计语义。 |
| `oracle-sequence` | 迁移 Sequence、缓存、循环、取值和并发语义。 |
| `oracle-synonym` | 迁移公私有 Synonym、解析优先级、权限和跨 Schema 引用。 |
| `oracle-database-link` | 迁移 Database Link、远程查询、权限、网络和分布式事务。 |
| `oracle-materialized-view` | 迁移物化视图、刷新模式、日志、查询重写和一致性。 |
| `oracle-object-type` | 迁移 Oracle Object Type、继承、方法和表对象。 |
| `oracle-collection` | 迁移 VARRAY、Nested Table、Associative Array 和集合操作。 |
| `oracle-bulk-collect-forall` | 迁移 Bulk Collect、FORALL、批处理异常和性能语义。 |
| `oracle-hierarchical-query` | 迁移 CONNECT BY、START WITH、层级伪列和顺序。 |
| `oracle-flashback` | 迁移 Flashback Query、Table、Database 和审计/历史用途。 |
| `oracle-advanced-queue` | 迁移 Advanced Queue、消费者、优先级、延迟、事务和重试。 |
| `oracle-scheduler` | 迁移 DBMS_SCHEDULER、Job、Program、Chain、窗口和凭证。 |
| `oracle-fine-grained-access-control` | 迁移 VPD/FGAC 策略函数、上下文和行列级安全。 |
| `oracle-null-and-date-semantics` | 处理空字符串等于 NULL、DATE/TIMESTAMP、NLS 和时区语义。 |
| `oracle-feature-migration-decision` | 为 Oracle 专有能力输出 DIRECT_MAP、REWRITE、EMULATE、EXTERNALIZE、RETAIN 或 UNSUPPORTED。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
