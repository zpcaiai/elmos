---
name: pm-b32-advanced-dynamic-validation
description: "使用反例搜索、变异、系统化调度、故障注入和确定性回放覆盖普通测试难以触达的语义风险. Precision Migration B32 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 32：Fuzz、Mutation、并发与故障验证
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b32-advanced-dynamic-validation`.
- Immutable source identity: `batch-32-advanced-dynamic-validation` in `precision-migration-b01-44` (B32).
- Runtime adapter: `differential-test-and-repair`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b32-advanced-dynamic-validation`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

使用反例搜索、变异、系统化调度、故障注入和确定性回放覆盖普通测试难以触达的语义风险。

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

- 当任务涉及 **differential-fuzzing** 时，调用 `../pm-b32-differential-fuzzing/SKILL.md`。
- 当任务涉及 **coverage-guided-fuzzing** 时，调用 `../pm-b32-coverage-guided-fuzzing/SKILL.md`。
- 当任务涉及 **metamorphic-testing** 时，调用 `../pm-b32-metamorphic-testing/SKILL.md`。
- 当任务涉及 **language-pair-mutation-testing** 时，调用 `../pm-b32-language-pair-mutation-testing/SKILL.md`。
- 当任务涉及 **systematic-concurrency-exploration** 时，调用 `../pm-b32-systematic-concurrency-exploration/SKILL.md`。
- 当任务涉及 **fault-injection** 时，调用 `../pm-b32-fault-injection/SKILL.md`。
- 当任务涉及 **crash-point-exploration** 时，调用 `../pm-b32-crash-point-exploration/SKILL.md`。
- 当任务涉及 **retry-idempotency-validation** 时，调用 `../pm-b32-retry-idempotency-validation/SKILL.md`。
- 当任务涉及 **transaction-atomicity-validation** 时，调用 `../pm-b32-transaction-atomicity-validation/SKILL.md`。
- 当任务涉及 **resource-leak-validation** 时，调用 `../pm-b32-resource-leak-validation/SKILL.md`。
- 当任务涉及 **performance-stress-validation** 时，调用 `../pm-b32-performance-stress-validation/SKILL.md`。
- 当任务涉及 **deterministic-record-replay** 时，调用 `../pm-b32-deterministic-record-replay/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `differential-fuzzing` | 向源目标输入同一随机或变异数据并比较输出、状态和副作用。 |
| `coverage-guided-fuzzing` | 利用覆盖反馈扩展输入，发现新路径、崩溃、超时和不等价。 |
| `metamorphic-testing` | 在缺乏精确 Oracle 时使用输入变换与输出关系验证行为性质。 |
| `language-pair-mutation-testing` | 注入特定语言方向常见错误，验证专用测试和验证器是否能杀死 Mutant。 |
| `systematic-concurrency-exploration` | 接管调度点并探索关键线程、任务、Future、goroutine 和消息交错。 |
| `fault-injection` | 注入网络、数据库、消息、磁盘、依赖、权限和资源故障。 |
| `crash-point-exploration` | 在事务、写入、消息、ACK、补偿和持久化边界注入进程崩溃。 |
| `retry-idempotency-validation` | 验证超时、重试、重复投递和幂等键不会造成重复副作用。 |
| `transaction-atomicity-validation` | 验证失败路径无部分提交、事务边界正确且源目标可见性一致。 |
| `resource-leak-validation` | 检测线程、任务、连接、文件、内存、句柄、订阅和设备资源泄漏。 |
| `performance-stress-validation` | 在代表负载和极端负载下验证延迟、吞吐、稳定性和资源门槛。 |
| `deterministic-record-replay` | 记录输入、外部返回、时间、随机、调度和状态并可确定性重放。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
