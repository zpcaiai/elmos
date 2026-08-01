---
name: pm-b13-neurosymbolic-candidate-generation
description: "组合确定性规则、LLM、检索、E-Graph、适配器和可验证性排序，生成多个候选并让客观验证器淘汰错误方案. Precision Migration B13 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 13：候选生成与神经符号转换
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b13-neurosymbolic-candidate-generation`.
- Immutable source identity: `batch-13-neurosymbolic-candidate-generation` in `precision-migration-b01-44` (B13).
- Runtime adapter: `semantic-recovery-and-ir`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b13-neurosymbolic-candidate-generation`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

组合确定性规则、LLM、检索、E-Graph、适配器和可验证性排序，生成多个候选并让客观验证器淘汰错误方案。

## Position in the system

- Phase: `D 转换定义与规则引擎`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 验证规则前置条件
2. 优先使用确定性规则
3. 对长尾生成多个候选
4. 按可验证性和成本排序
5. 运行最小构建/静态验证并输出结果集

## Shared gates

- 生成者不是最终裁判
- 不允许静默跳过不支持语义
- 所有修改必须有来源和回滚

## Dispatch rules

- 当任务涉及 **deterministic-rule-generator** 时，调用 `../pm-b13-deterministic-rule-generator/SKILL.md`。
- 当任务涉及 **llm-candidate-generator** 时，调用 `../pm-b13-llm-candidate-generator/SKILL.md`。
- 当任务涉及 **multi-candidate-search** 时，调用 `../pm-b13-multi-candidate-search/SKILL.md`。
- 当任务涉及 **egraph-equivalence-search** 时，调用 `../pm-b13-egraph-equivalence-search/SKILL.md`。
- 当任务涉及 **library-api-rag** 时，调用 `../pm-b13-library-api-rag/SKILL.md`。
- 当任务涉及 **adapter-and-shim-generator** 时，调用 `../pm-b13-adapter-and-shim-generator/SKILL.md`。
- 当任务涉及 **idiomatic-target-code-generator** 时，调用 `../pm-b13-idiomatic-target-code-generator/SKILL.md`。
- 当任务涉及 **unsupported-semantics-classifier** 时，调用 `../pm-b13-unsupported-semantics-classifier/SKILL.md`。
- 当任务涉及 **candidate-cost-ranker** 时，调用 `../pm-b13-candidate-cost-ranker/SKILL.md`。
- 当任务涉及 **candidate-verifiability-ranker** 时，调用 `../pm-b13-candidate-verifiability-ranker/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `deterministic-rule-generator` | 从已验证规则和 IR Lowering 确定性生成候选，避免重复推理。 |
| `llm-candidate-generator` | 向模型提供最小语义切片、契约、方向包和验收测试，生成受约束候选。 |
| `multi-candidate-search` | 并行生成架构、库映射和实现候选，并保留差异与来源。 |
| `egraph-equivalence-search` | 对局部纯表达式和数据流进行等价饱和，选择目标语言最优形式。 |
| `library-api-rag` | 检索目标语言真实 API、版本、导入、示例、语义条件和替代库。 |
| `adapter-and-shim-generator` | 在无法无损翻译时生成兼容层、RPC、FFI、Schema Carrier 或临时 Shim。 |
| `idiomatic-target-code-generator` | 在保持契约前提下生成目标语言惯用、可维护、可测试的实现。 |
| `unsupported-semantics-classifier` | 将无法可靠转换的语义分类为需适配、需重构、保留源服务或不支持。 |
| `candidate-cost-ranker` | 按生成成本、运行成本、依赖、维护和迁移风险对候选排序。 |
| `candidate-verifiability-ranker` | 优先选择更易类型检查、证明、差分和运行验证的候选。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
