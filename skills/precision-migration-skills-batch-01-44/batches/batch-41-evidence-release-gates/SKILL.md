---
name: batch-41-evidence-release-gates
description: 把转换来源、证明、测试、差分、性能、风险和语义损失汇聚为可签名的证据包和硬性发布门禁。
---

# Batch 41：正确性证据与发布门禁

## Goal

把转换来源、证明、测试、差分、性能、风险和语义损失汇聚为可签名的证据包和硬性发布门禁。

## Position in the system

- Phase: `L 证据、上线和产品化`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 汇总证据与未解决项
2. 执行硬性发布门禁
3. 影子/Canary/渐进切换
4. 监控并自动回滚
5. 沉淀反例、规则和企业交付能力

## Shared gates

- 未解决阻断项必须为0
- 生产副作用必须可抑制、可回滚或经批准
- 证据、环境和产物必须可追踪与签名

## Dispatch rules

- 当任务涉及 **evidence-manifest** 时，调用 `skills/evidence-manifest/SKILL.md`。
- 当任务涉及 **conversion-provenance** 时，调用 `skills/conversion-provenance/SKILL.md`。
- 当任务涉及 **rule-proof-certificate** 时，调用 `skills/rule-proof-certificate/SKILL.md`。
- 当任务涉及 **module-equivalence-certificate** 时，调用 `skills/module-equivalence-certificate/SKILL.md`。
- 当任务涉及 **runtime-evidence-package** 时，调用 `skills/runtime-evidence-package/SKILL.md`。
- 当任务涉及 **semantic-loss-report** 时，调用 `skills/semantic-loss-report/SKILL.md`。
- 当任务涉及 **unresolved-obligation-report** 时，调用 `skills/unresolved-obligation-report/SKILL.md`。
- 当任务涉及 **release-gate-engine** 时，调用 `skills/release-gate-engine/SKILL.md`。
- 当任务涉及 **correctness-level-classifier** 时，调用 `skills/correctness-level-classifier/SKILL.md`。
- 当任务涉及 **certificate-signing** 时，调用 `skills/certificate-signing/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `evidence-manifest` | 索引本次迁移的规则、模型、工具链、测试、证明、差异、审批和产物。 |
| `conversion-provenance` | 追踪每段目标代码由何规则、Agent、输入、版本和修复生成。 |
| `rule-proof-certificate` | 记录转换规则适用条件、证明、测试、反例和内核验收。 |
| `module-equivalence-certificate` | 记录关键模块源目标类型、结果、状态、Effect 和观察等价证据。 |
| `runtime-evidence-package` | 打包双运行、Fuzz、Mutation、并发、故障、性能、UI 和真机结果。 |
| `semantic-loss-report` | 报告每项无损、归一化、近似、适配、未验证和不支持语义。 |
| `unresolved-obligation-report` | 列出所有未证明、未测试、未知、超时、规格冲突和阻断项。 |
| `release-gate-engine` | 以硬门槛而非平均分决定是否允许发布、灰度或要求人工。 |
| `correctness-level-classifier` | 将结果分类为语法、构建、类型、局部语义、组合行为、系统性质和生产证据等级。 |
| `certificate-signing` | 对证据、产物、规则、环境和审批生成不可篡改签名。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
