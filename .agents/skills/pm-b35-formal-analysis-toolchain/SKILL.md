---
name: pm-b35-formal-analysis-toolchain
description: "组合 SMT、关系验证、符号/合流执行、抽象解释、TLA+、Alloy 与运行证据，形成分层形式验证体系. Precision Migration B35 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 35：SMT、符号执行与模型检查
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b35-formal-analysis-toolchain`.
- Immutable source identity: `batch-35-formal-analysis-toolchain` in `precision-migration-b01-44` (B35).
- Runtime adapter: `formal-and-advanced-verification`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b35-formal-analysis-toolchain`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

组合 SMT、关系验证、符号/合流执行、抽象解释、TLA+、Alloy 与运行证据，形成分层形式验证体系。

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

- 当任务涉及 **smt-translation-validator** 时，调用 `../pm-b35-smt-translation-validator/SKILL.md`。
- 当任务涉及 **relational-verification** 时，调用 `../pm-b35-relational-verification/SKILL.md`。
- 当任务涉及 **symbolic-execution** 时，调用 `../pm-b35-symbolic-execution/SKILL.md`。
- 当任务涉及 **concolic-differential-execution** 时，调用 `../pm-b35-concolic-differential-execution/SKILL.md`。
- 当任务涉及 **abstract-interpretation** 时，调用 `../pm-b35-abstract-interpretation/SKILL.md`。
- 当任务涉及 **tla-state-machine-generator** 时，调用 `../pm-b35-tla-state-machine-generator/SKILL.md`。
- 当任务涉及 **model-checking-runner** 时，调用 `../pm-b35-model-checking-runner/SKILL.md`。
- 当任务涉及 **alloy-architecture-validator** 时，调用 `../pm-b35-alloy-architecture-validator/SKILL.md`。
- 当任务涉及 **proof-counterexample-to-test** 时，调用 `../pm-b35-proof-counterexample-to-test/SKILL.md`。
- 当任务涉及 **formal-runtime-evidence-merger** 时，调用 `../pm-b35-formal-runtime-evidence-merger/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `smt-translation-validator` | 将源目标 Core IR 编码为 SMT 关系，证明等价或寻找反例。 |
| `relational-verification` | 验证两个实现之间的输入、状态、输出和 Effect 关系。 |
| `symbolic-execution` | 对关键切片探索符号路径并求解崩溃、违规和不等价输入。 |
| `concolic-differential-execution` | 结合具体执行与符号约束扩展源目标差分路径覆盖。 |
| `abstract-interpretation` | 推断范围、Nullability、可达状态、异常、资源和动态类型近似。 |
| `tla-state-machine-generator` | 从业务/协议 IR 生成 TLA+ 状态机、安全性和活性性质。 |
| `model-checking-runner` | 运行状态空间探索、对称约简、边界配置和反例提取。 |
| `alloy-architecture-validator` | 用 Alloy 验证模块、权限、所有权、Schema 和架构关系约束。 |
| `proof-counterexample-to-test` | 把 SMT、Lean、模型检查或符号执行反例转换为永久回归测试。 |
| `formal-runtime-evidence-merger` | 合并形式证明覆盖与运行时验证证据，并显式标记假设和未建模部分。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
