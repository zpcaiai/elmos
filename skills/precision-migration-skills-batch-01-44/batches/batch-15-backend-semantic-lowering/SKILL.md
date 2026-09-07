---
name: batch-15-backend-semantic-lowering
description: 将常见跨语言语义鸿沟显式 Lowering，并为类型、Effect、资源、并发、框架和运维语义建立验证义务。
---

# Batch 15：后端通用语义转换能力

## Goal

将常见跨语言语义鸿沟显式 Lowering，并为类型、Effect、资源、并发、框架和运维语义建立验证义务。

## Position in the system

- Phase: `E 后端语言互转`
- Included skills: `14`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 使用语言原生前端恢复语义
2. Lower到Typed/Effect/State IR
3. 应用方向专用规则和依赖映射
4. 生成目标惯用代码
5. 构建、测试、双运行并按反例修复

## Shared gates

- 错误路径、事务和副作用必须保持
- 并发/取消/资源语义不得靠编译通过替代验证
- Direction Pack外的语义必须阻断或升级

## Dispatch rules

- 当任务涉及 **exception-to-result-error-lowering** 时，调用 `skills/exception-to-result-error-lowering/SKILL.md`。
- 当任务涉及 **null-to-option-pointer-lowering** 时，调用 `skills/null-to-option-pointer-lowering/SKILL.md`。
- 当任务涉及 **inheritance-to-composition-lowering** 时，调用 `skills/inheritance-to-composition-lowering/SKILL.md`。
- 当任务涉及 **interface-trait-protocol-lowering** 时，调用 `skills/interface-trait-protocol-lowering/SKILL.md`。
- 当任务涉及 **generic-type-lowering** 时，调用 `skills/generic-type-lowering/SKILL.md`。
- 当任务涉及 **collection-pipeline-lowering** 时，调用 `skills/collection-pipeline-lowering/SKILL.md`。
- 当任务涉及 **sync-async-lowering** 时，调用 `skills/sync-async-lowering/SKILL.md`。
- 当任务涉及 **thread-goroutine-future-lowering** 时，调用 `skills/thread-goroutine-future-lowering/SKILL.md`。
- 当任务涉及 **resource-ownership-lowering** 时，调用 `skills/resource-ownership-lowering/SKILL.md`。
- 当任务涉及 **reflection-elimination** 时，调用 `skills/reflection-elimination/SKILL.md`。
- 当任务涉及 **dependency-injection-lowering** 时，调用 `skills/dependency-injection-lowering/SKILL.md`。
- 当任务涉及 **orm-and-transaction-lowering** 时，调用 `skills/orm-and-transaction-lowering/SKILL.md`。
- 当任务涉及 **configuration-lowering** 时，调用 `skills/configuration-lowering/SKILL.md`。
- 当任务涉及 **logging-observability-lowering** 时，调用 `skills/logging-observability-lowering/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `exception-to-result-error-lowering` | 在异常、Result、error tuple、panic 和错误码之间保持错误路径与清理语义。 |
| `null-to-option-pointer-lowering` | 在 Null、Option、Nullable、Pointer、zero value 和 Missing 之间安全映射。 |
| `inheritance-to-composition-lowering` | 把类继承、模板方法和基类状态转换为组合、嵌入、委托或 Trait。 |
| `interface-trait-protocol-lowering` | 在 Interface、Trait、Protocol、结构类型和动态协议之间映射契约。 |
| `generic-type-lowering` | 处理泛型擦除、实例化、约束、协变、Trait bound 和运行时类型。 |
| `collection-pipeline-lowering` | 在 Stream、LINQ、Iterator、Loop、Generator 和 Array pipeline 之间保持顺序与惰性。 |
| `sync-async-lowering` | 在同步、Future、Promise、Task、asyncio 和阻塞边界之间安全迁移。 |
| `thread-goroutine-future-lowering` | 映射线程、goroutine、Task、Future、channel、锁、取消和调度语义。 |
| `resource-ownership-lowering` | 迁移 GC、RAII、ARC、Ownership、Borrow、Dispose、defer 和上下文管理。 |
| `reflection-elimination` | 通过代码生成、注册表、显式映射或兼容层消除无法迁移的反射和动态加载。 |
| `dependency-injection-lowering` | 映射容器、生命周期、Scope、拦截、代理、工厂和条件绑定。 |
| `orm-and-transaction-lowering` | 映射 ORM 实体、Tracking、查询、Lazy load、事务传播、锁和并发控制。 |
| `configuration-lowering` | 迁移配置源、优先级、环境、Secret、动态刷新和类型绑定。 |
| `logging-observability-lowering` | 迁移日志、指标、Trace、Correlation、错误报告和语义约定。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
