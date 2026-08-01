---
name: batch-21-stored-procedure-conversion
description: 将 PL/SQL、T-SQL、PL/pgSQL、MySQL Procedure 等数据库程序解析为可转换、可测试和可验证的过程语义。
---

# Batch 21：复杂存储过程与数据库程序转换

## Goal

将 PL/SQL、T-SQL、PL/pgSQL、MySQL Procedure 等数据库程序解析为可转换、可测试和可验证的过程语义。

## Position in the system

- Phase: `G 数据库精密互转`
- Included skills: `14`
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

- 当任务涉及 **stored-procedure-parser** 时，调用 `skills/stored-procedure-parser/SKILL.md`。
- 当任务涉及 **procedure-cfg-builder** 时，调用 `skills/procedure-cfg-builder/SKILL.md`。
- 当任务涉及 **cursor-semantics-converter** 时，调用 `skills/cursor-semantics-converter/SKILL.md`。
- 当任务涉及 **dynamic-sql-converter** 时，调用 `skills/dynamic-sql-converter/SKILL.md`。
- 当任务涉及 **exception-handler-converter** 时，调用 `skills/exception-handler-converter/SKILL.md`。
- 当任务涉及 **transaction-boundary-converter** 时，调用 `skills/transaction-boundary-converter/SKILL.md`。
- 当任务涉及 **temporary-object-converter** 时，调用 `skills/temporary-object-converter/SKILL.md`。
- 当任务涉及 **package-state-converter** 时，调用 `skills/package-state-converter/SKILL.md`。
- 当任务涉及 **trigger-semantics-converter** 时，调用 `skills/trigger-semantics-converter/SKILL.md`。
- 当任务涉及 **scheduled-event-converter** 时，调用 `skills/scheduled-event-converter/SKILL.md`。
- 当任务涉及 **procedure-side-effect-analyzer** 时，调用 `skills/procedure-side-effect-analyzer/SKILL.md`。
- 当任务涉及 **procedure-symbolic-validator** 时，调用 `skills/procedure-symbolic-validator/SKILL.md`。
- 当任务涉及 **procedure-differential-test-generator** 时，调用 `skills/procedure-differential-test-generator/SKILL.md`。
- 当任务涉及 **procedure-performance-validator** 时，调用 `skills/procedure-performance-validator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `stored-procedure-parser` | 解析过程、函数、Package、变量、游标、异常、事务和动态 SQL。 |
| `procedure-cfg-builder` | 构建过程代码控制流、调用图、数据流、事务和副作用图。 |
| `cursor-semantics-converter` | 转换显式/隐式游标、游标属性、批量提取、顺序和资源关闭。 |
| `dynamic-sql-converter` | 解析、枚举、参数化和重写动态 SQL，并检测注入与不可解析路径。 |
| `exception-handler-converter` | 映射异常类别、处理顺序、回滚、继续执行和错误返回。 |
| `transaction-boundary-converter` | 映射隐式/显式提交、自治事务、保存点、传播和失败可见性。 |
| `temporary-object-converter` | 转换临时表、表变量、临时 Schema、会话状态和生命周期。 |
| `package-state-converter` | 将 Package 公私有成员、会话状态和初始化转换为 Schema、模块或服务状态。 |
| `trigger-semantics-converter` | 转换触发器时机、粒度、顺序、递归、OLD/NEW 和副作用。 |
| `scheduled-event-converter` | 转换数据库 Job、Event、Scheduler 到目标调度器或外部工作流。 |
| `procedure-side-effect-analyzer` | 总结过程对表、序列、消息、外部调用、事务和权限的副作用。 |
| `procedure-symbolic-validator` | 对关键过程切片执行符号或关系验证，寻找源目标反例。 |
| `procedure-differential-test-generator` | 从签名、分支、数据约束和源行为生成双库差分测试。 |
| `procedure-performance-validator` | 比较执行计划、IO、CPU、临时空间、锁、吞吐和延迟。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
