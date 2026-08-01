---
name: batch-33-proof-obligations
description: 从 Typed/Effect/State/Observation IR 自动生成可由 SMT、Lean 或模型检查器处理的转换证明义务。
---

# Batch 33：Proof Obligation Generation

## Goal

从 Typed/Effect/State/Observation IR 自动生成可由 SMT、Lean 或模型检查器处理的转换证明义务。

## Position in the system

- Phase: `I 形式化证明`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 固定语义与定理陈述
2. 生成或编码证明义务
3. 调用Lean/SMT/模型检查
4. 最小化反例并回写测试
5. 由可信内核/求解器签发结果

## Shared gates

- Leanstral/LLM不能自行宣布QED
- UNKNOWN/TIMEOUT不能视为通过
- 规格正确性必须与源行为和业务确认交叉验证

## Dispatch rules

- 当任务涉及 **type-preservation-obligation** 时，调用 `skills/type-preservation-obligation/SKILL.md`。
- 当任务涉及 **numeric-semantics-obligation** 时，调用 `skills/numeric-semantics-obligation/SKILL.md`。
- 当任务涉及 **nullability-preservation-obligation** 时，调用 `skills/nullability-preservation-obligation/SKILL.md`。
- 当任务涉及 **effect-preservation-obligation** 时，调用 `skills/effect-preservation-obligation/SKILL.md`。
- 当任务涉及 **state-refinement-obligation** 时，调用 `skills/state-refinement-obligation/SKILL.md`。
- 当任务涉及 **pure-function-equivalence-obligation** 时，调用 `skills/pure-function-equivalence-obligation/SKILL.md`。
- 当任务涉及 **serializer-roundtrip-obligation** 时，调用 `skills/serializer-roundtrip-obligation/SKILL.md`。
- 当任务涉及 **permission-non-expansion-obligation** 时，调用 `skills/permission-non-expansion-obligation/SKILL.md`。
- 当任务涉及 **transaction-invariant-obligation** 时，调用 `skills/transaction-invariant-obligation/SKILL.md`。
- 当任务涉及 **trace-refinement-obligation** 时，调用 `skills/trace-refinement-obligation/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `type-preservation-obligation` | 生成源表达式有类型则目标表达式具有映射类型的类型保持义务。 |
| `numeric-semantics-obligation` | 生成位宽、溢出、精度、舍入、NaN 和边界语义保持义务。 |
| `nullability-preservation-obligation` | 生成 Null、Missing、Undefined、Option、Pointer 和 zero value 的保持义务。 |
| `effect-preservation-obligation` | 生成必需 Effect 不缺失、危险新增 Effect 为空的证明义务。 |
| `state-refinement-obligation` | 生成目标状态机对源状态机的 Simulation/Refinement 义务。 |
| `pure-function-equivalence-obligation` | 生成纯函数在前置条件下对所有输入结果等价的关系义务。 |
| `serializer-roundtrip-obligation` | 生成编码、解码、规范化和跨语言 Carrier 的 Round-trip 义务。 |
| `permission-non-expansion-obligation` | 生成迁移后权限集合不扩大、拒绝规则不弱化的义务。 |
| `transaction-invariant-obligation` | 生成原子性、守恒、幂等、回滚和状态可见性的事务义务。 |
| `trace-refinement-obligation` | 生成目标可观察 Trace 对源合法 Trace 的精化或等价义务。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
