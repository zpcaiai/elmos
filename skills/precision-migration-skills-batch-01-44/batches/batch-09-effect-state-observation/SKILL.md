---
name: batch-09-effect-state-observation
description: 在普通类型之外显式表达副作用、事务、资源、状态机、协议和可观察行为，以支持真正的行为等价验证。
---

# Batch 09：Effect、State与Observation系统

## Goal

在普通类型之外显式表达副作用、事务、资源、状态机、协议和可观察行为，以支持真正的行为等价验证。

## Position in the system

- Phase: `C 精密语义表示`
- Included skills: `12`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 定义可观察边界
2. 将源语义归一化到受限模型
3. 保留不可丢失信息
4. 标记近似与不支持语义
5. 验证 Schema、一致性和可序列化性

## Shared gates

- 不得把 Null/Missing/Undefined 合并
- 不得隐式缩窄数值范围
- 所有副作用和状态转换必须可追踪

## Dispatch rules

- 当任务涉及 **effect-system** 时，调用 `skills/effect-system/SKILL.md`。
- 当任务涉及 **database-effect-model** 时，调用 `skills/database-effect-model/SKILL.md`。
- 当任务涉及 **message-effect-model** 时，调用 `skills/message-effect-model/SKILL.md`。
- 当任务涉及 **external-call-effect-model** 时，调用 `skills/external-call-effect-model/SKILL.md`。
- 当任务涉及 **resource-lifecycle-model** 时，调用 `skills/resource-lifecycle-model/SKILL.md`。
- 当任务涉及 **transaction-effect-model** 时，调用 `skills/transaction-effect-model/SKILL.md`。
- 当任务涉及 **async-cancellation-model** 时，调用 `skills/async-cancellation-model/SKILL.md`。
- 当任务涉及 **business-state-machine-ir** 时，调用 `skills/business-state-machine-ir/SKILL.md`。
- 当任务涉及 **ui-state-machine-ir** 时，调用 `skills/ui-state-machine-ir/SKILL.md`。
- 当任务涉及 **protocol-and-workflow-ir** 时，调用 `skills/protocol-and-workflow-ir/SKILL.md`。
- 当任务涉及 **observable-behavior-ir** 时，调用 `skills/observable-behavior-ir/SKILL.md`。
- 当任务涉及 **semantic-loss-ledger** 时，调用 `skills/semantic-loss-ledger/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `effect-system` | 定义 Read、Write、Call、Publish、Throw、Spawn、Await、Clock、Random 等统一 Effect。 |
| `database-effect-model` | 表达表读写、事务、锁、隔离级别、触发器和过程代码数据库 Effect。 |
| `message-effect-model` | 表达 Topic、Key、顺序、投递、重试、ACK、DLQ 和逻辑 Exactly-once Effect。 |
| `external-call-effect-model` | 表达外部调用参数、次数、顺序、超时、重试、幂等和不可逆副作用。 |
| `resource-lifecycle-model` | 表达文件、连接、锁、内存、线程、任务和设备资源的获取、使用与释放。 |
| `transaction-effect-model` | 表达事务传播、保存点、提交、回滚、补偿和部分可见性。 |
| `async-cancellation-model` | 表达异步任务、取消传播、Latest-wins、超时、悬挂任务和完成顺序。 |
| `business-state-machine-ir` | 提取和表达订单、支付、库存、权限等业务状态与合法转换。 |
| `ui-state-machine-ir` | 表达 Loading、Success、Failure、Refresh、Submitting 等 UI 状态与事件转换。 |
| `protocol-and-workflow-ir` | 表达重试、Saga、Outbox、审批、消息交互和长流程协议。 |
| `observable-behavior-ir` | 统一返回值、异常、HTTP、状态变更、消息、Trace、UI、导航和性能观察。 |
| `semantic-loss-ledger` | 逐模块记录无损、归一化、近似、需适配、未验证和不支持的语义损失。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
