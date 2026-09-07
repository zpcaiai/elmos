---
name: batch-30-dual-run-differential
description: 让源系统和目标系统在同一输入、环境和初始状态下并行运行，并比较完整可观察行为。
---

# Batch 30：源目标双运行与行为差分

## Goal

让源系统和目标系统在同一输入、环境和初始状态下并行运行，并比较完整可观察行为。

## Position in the system

- Phase: `H 测试、验证与自动修复`
- Included skills: `12`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 评估或生成测试
2. 同步环境并双运行
3. 比较输出、状态和副作用
4. 搜索最小反例
5. 驱动修复并执行全量回归

## Shared gates

- 未解释差异必须阻断
- 测试弱化和删除必须阻断
- 关键不变量、权限和不可逆副作用必须100%通过

## Dispatch rules

- 当任务涉及 **source-target-dual-runner** 时，调用 `skills/source-target-dual-runner/SKILL.md`。
- 当任务涉及 **input-and-environment-synchronizer** 时，调用 `skills/input-and-environment-synchronizer/SKILL.md`。
- 当任务涉及 **clock-random-uuid-controller** 时，调用 `skills/clock-random-uuid-controller/SKILL.md`。
- 当任务涉及 **http-differential-comparator** 时，调用 `skills/http-differential-comparator/SKILL.md`。
- 当任务涉及 **database-state-comparator** 时，调用 `skills/database-state-comparator/SKILL.md`。
- 当任务涉及 **message-side-effect-comparator** 时，调用 `skills/message-side-effect-comparator/SKILL.md`。
- 当任务涉及 **external-call-comparator** 时，调用 `skills/external-call-comparator/SKILL.md`。
- 当任务涉及 **trace-graph-comparator** 时，调用 `skills/trace-graph-comparator/SKILL.md`。
- 当任务涉及 **ui-semantic-tree-comparator** 时，调用 `skills/ui-semantic-tree-comparator/SKILL.md`。
- 当任务涉及 **visual-differential-comparator** 时，调用 `skills/visual-differential-comparator/SKILL.md`。
- 当任务涉及 **navigation-and-storage-comparator** 时，调用 `skills/navigation-and-storage-comparator/SKILL.md`。
- 当任务涉及 **performance-differential-comparator** 时，调用 `skills/performance-differential-comparator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `source-target-dual-runner` | 编排源目标构建、启动、健康检查、隔离、执行和结果收集。 |
| `input-and-environment-synchronizer` | 同步输入、配置、依赖、数据库、外部返回、Locale、时区和平台状态。 |
| `clock-random-uuid-controller` | 注入可控时钟、随机种子、UUID、序列和调度点，降低非确定噪声。 |
| `http-differential-comparator` | 比较状态码、Header、Body、错误、顺序、流、超时和重试。 |
| `database-state-comparator` | 比较相关表、事务、约束、序列、触发器和最终数据库状态。 |
| `message-side-effect-comparator` | 比较消息 Topic、Key、Header、Payload、次数、顺序、重试和 DLQ。 |
| `external-call-comparator` | 比较外部调用参数、次数、顺序、幂等、超时、错误和不可逆意图。 |
| `trace-graph-comparator` | 比较规范化 Trace 图、关键偏序和业务语义 Span。 |
| `ui-semantic-tree-comparator` | 比较 Role、Name、State、Value、可见、可用、焦点和组件层级。 |
| `visual-differential-comparator` | 比较关键区域、布局、文本、主题、响应式和感知视觉差异。 |
| `navigation-and-storage-comparator` | 比较路由栈、返回、深链、本地存储、缓存和恢复状态。 |
| `performance-differential-comparator` | 比较延迟、吞吐、CPU、内存、GC、帧率、启动和资源泄漏。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
