---
name: batch-27-application-database-joint-migration
description: 把数据库迁移与应用驱动、ORM、原生 SQL、事务、锁、错误码和性能一起转换和验证。
---

# Batch 27：应用代码与数据库联合迁移

## Goal

把数据库迁移与应用驱动、ORM、原生 SQL、事务、锁、错误码和性能一起转换和验证。

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

- 当任务涉及 **embedded-sql-discovery** 时，调用 `skills/embedded-sql-discovery/SKILL.md`。
- 当任务涉及 **orm-dialect-migration** 时，调用 `skills/orm-dialect-migration/SKILL.md`。
- 当任务涉及 **jdbc-ado-odbc-driver-migration** 时，调用 `skills/jdbc-ado-odbc-driver-migration/SKILL.md`。
- 当任务涉及 **query-builder-migration** 时，调用 `skills/query-builder-migration/SKILL.md`。
- 当任务涉及 **native-query-rewriter** 时，调用 `skills/native-query-rewriter/SKILL.md`。
- 当任务涉及 **stored-procedure-call-rewriter** 时，调用 `skills/stored-procedure-call-rewriter/SKILL.md`。
- 当任务涉及 **transaction-api-rewriter** 时，调用 `skills/transaction-api-rewriter/SKILL.md`。
- 当任务涉及 **pagination-and-locking-rewriter** 时，调用 `skills/pagination-and-locking-rewriter/SKILL.md`。
- 当任务涉及 **database-error-code-mapping** 时，调用 `skills/database-error-code-mapping/SKILL.md`。
- 当任务涉及 **application-database-dual-validation** 时，调用 `skills/application-database-dual-validation/SKILL.md`。
- 当任务涉及 **query-plan-regression-analysis** 时，调用 `skills/query-plan-regression-analysis/SKILL.md`。
- 当任务涉及 **cross-layer-performance-tuning** 时，调用 `skills/cross-layer-performance-tuning/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `embedded-sql-discovery` | 发现源码、模板、配置、报表和脚本中的嵌入式 SQL 与动态片段。 |
| `orm-dialect-migration` | 迁移 ORM Dialect、实体映射、查询语言、生成策略和迁移脚本。 |
| `jdbc-ado-odbc-driver-migration` | 迁移 JDBC、ADO.NET、ODBC、驱动配置、连接串、参数和类型绑定。 |
| `query-builder-migration` | 迁移 Query Builder、Criteria、DSL、表达式树和方言扩展。 |
| `native-query-rewriter` | 重写原生查询、Hint、锁、分页、函数、JSON、日期和返回类型。 |
| `stored-procedure-call-rewriter` | 迁移过程调用、IN/OUT 参数、结果集、返回码、事务和异常。 |
| `transaction-api-rewriter` | 迁移应用事务 API、传播、隔离、超时、重试和补偿。 |
| `pagination-and-locking-rewriter` | 迁移分页、稳定排序、FOR UPDATE、锁提示、Skip locked 和并发行为。 |
| `database-error-code-mapping` | 映射唯一、外键、死锁、超时、序列化失败和供应商错误码。 |
| `application-database-dual-validation` | 在相同输入和初始数据下比较应用+数据库的输出、状态和副作用。 |
| `query-plan-regression-analysis` | 比较目标查询计划、估算、实际行数、IO、锁和资源退化。 |
| `cross-layer-performance-tuning` | 联合调优 SQL、索引、ORM、连接池、批处理、缓存和应用调用模式。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
