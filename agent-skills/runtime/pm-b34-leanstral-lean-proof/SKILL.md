---
name: pm-b34-leanstral-lean-proof
description: "使用 Leanstral 自动化 Lean 4 定理、引理和证明修复，由 Lean Kernel 对证明证书作最终可信裁决. Precision Migration B34 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 34：Leanstral与Lean证明工程
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b34-leanstral-lean-proof`.
- Immutable source identity: `batch-34-leanstral-lean-proof` in `precision-migration-b01-44` (B34).
- Runtime adapter: `formal-and-advanced-verification`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b34-leanstral-lean-proof`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

使用 Leanstral 自动化 Lean 4 定理、引理和证明修复，由 Lean Kernel 对证明证书作最终可信裁决。

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

- 当任务涉及 **semantic-core-lean-model** 时，调用 `../pm-b34-semantic-core-lean-model/SKILL.md`。
- 当任务涉及 **lean-theorem-generator** 时，调用 `../pm-b34-lean-theorem-generator/SKILL.md`。
- 当任务涉及 **leanstral-proof-synthesis** 时，调用 `../pm-b34-leanstral-proof-synthesis/SKILL.md`。
- 当任务涉及 **leanstral-proof-repair** 时，调用 `../pm-b34-leanstral-proof-repair/SKILL.md`。
- 当任务涉及 **lemma-library-retrieval** 时，调用 `../pm-b34-lemma-library-retrieval/SKILL.md`。
- 当任务涉及 **proof-build-runner** 时，调用 `../pm-b34-proof-build-runner/SKILL.md`。
- 当任务涉及 **sorry-and-axiom-detector** 时，调用 `../pm-b34-sorry-and-axiom-detector/SKILL.md`。
- 当任务涉及 **lean-kernel-certificate** 时，调用 `../pm-b34-lean-kernel-certificate/SKILL.md`。
- 当任务涉及 **proof-regression-ci** 时，调用 `../pm-b34-proof-regression-ci/SKILL.md`。
- 当任务涉及 **unproved-obligation-ledger** 时，调用 `../pm-b34-unproved-obligation-ledger/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `semantic-core-lean-model` | 把 Semantic Core、类型、Effect、状态和求值关系编码为 Lean 定义。 |
| `lean-theorem-generator` | 从证明义务生成 Lean 定理陈述、上下文、前置条件和辅助结构。 |
| `leanstral-proof-synthesis` | 使用 Leanstral 生成证明、辅助引理和策略候选。 |
| `leanstral-proof-repair` | 根据 Lean 编译与语言服务器反馈定位并修复证明失败。 |
| `lemma-library-retrieval` | 检索项目、Mathlib、方向包和历史证明中的可复用引理。 |
| `proof-build-runner` | 运行 lake build、目标定理检查、资源限制和结果规范化。 |
| `sorry-and-axiom-detector` | 阻止 sorry、未批准公理、不透明逃逸和不可信证明依赖。 |
| `lean-kernel-certificate` | 记录 Lean 版本、依赖摘要、定理、Axiom 报告和内核验收结果。 |
| `proof-regression-ci` | 在 IR、规则、生成器和依赖变化时持续重跑证明回归。 |
| `unproved-obligation-ledger` | 记录 PROVED、DISPROVED、UNKNOWN、TIMEOUT、UNSUPPORTED 和规格冲突。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
