---
name: batch-08-canonical-type-system
description: 建立跨语言统一且不丢失关键语义的类型系统，作为类型恢复、Lowering、验证和代码生成的共同契约。
---

# Batch 08：Canonical Type System

## Goal

建立跨语言统一且不丢失关键语义的类型系统，作为类型恢复、Lowering、验证和代码生成的共同契约。

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

- 当任务涉及 **canonical-primitive-types** 时，调用 `skills/canonical-primitive-types/SKILL.md`。
- 当任务涉及 **numeric-semantics-model** 时，调用 `skills/numeric-semantics-model/SKILL.md`。
- 当任务涉及 **decimal-and-rounding-model** 时，调用 `skills/decimal-and-rounding-model/SKILL.md`。
- 当任务涉及 **null-missing-undefined-model** 时，调用 `skills/null-missing-undefined-model/SKILL.md`。
- 当任务涉及 **option-result-union-model** 时，调用 `skills/option-result-union-model/SKILL.md`。
- 当任务涉及 **generic-and-variance-model** 时，调用 `skills/generic-and-variance-model/SKILL.md`。
- 当任务涉及 **collection-semantics-model** 时，调用 `skills/collection-semantics-model/SKILL.md`。
- 当任务涉及 **datetime-timezone-model** 时，调用 `skills/datetime-timezone-model/SKILL.md`。
- 当任务涉及 **serialization-type-model** 时，调用 `skills/serialization-type-model/SKILL.md`。
- 当任务涉及 **refinement-type-contracts** 时，调用 `skills/refinement-type-contracts/SKILL.md`。
- 当任务涉及 **ownership-and-lifetime-model** 时，调用 `skills/ownership-and-lifetime-model/SKILL.md`。
- 当任务涉及 **gradual-type-recovery** 时，调用 `skills/gradual-type-recovery/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `canonical-primitive-types` | 定义位宽、符号、编码、布尔、字节、字符串和基础值类型的统一语义。 |
| `numeric-semantics-model` | 建模整数溢出、浮点、NaN、Infinity、负零、除法和取模差异。 |
| `decimal-and-rounding-model` | 建模精度、Scale、舍入模式、溢出和货币语义。 |
| `null-missing-undefined-model` | 严格区分 Null、Missing、Undefined、Empty、Zero value 和未初始化。 |
| `option-result-union-model` | 统一 Option、Result、Union、错误分支和封闭代数数据类型。 |
| `generic-and-variance-model` | 建模泛型约束、擦除、实例化、协变、逆变和高阶类型差异。 |
| `collection-semantics-model` | 建模顺序、唯一性、相等、哈希、可变性、惰性与并发集合语义。 |
| `datetime-timezone-model` | 建模 Instant、Local time、Offset、时区、精度、闰秒和夏令时。 |
| `serialization-type-model` | 统一 JSON、Protobuf、数据库、消息和配置的可观察序列化表示。 |
| `refinement-type-contracts` | 为范围、非空、唯一、排序、守恒和权限等性质生成精化类型契约。 |
| `ownership-and-lifetime-model` | 统一所有权、借用、别名、可变性、资源生命周期和线程安全语义。 |
| `gradual-type-recovery` | 结合静态分析、运行 Trace、Schema 和测试恢复动态语言真实类型与对象形状。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
