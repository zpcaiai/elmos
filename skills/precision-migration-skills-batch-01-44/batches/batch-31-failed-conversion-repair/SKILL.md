---
name: batch-31-failed-conversion-repair
description: 面向 Vue→Flutter 等已有失败转换项目，定位缺失功能和行为差异，生成最小反例并驱动定点修复或重新转换。
---

# Batch 31：失败转换检测与自动修复

## Goal

面向 Vue→Flutter 等已有失败转换项目，定位缺失功能和行为差异，生成最小反例并驱动定点修复或重新转换。

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

- 当任务涉及 **source-target-feature-matrix** 时，调用 `skills/source-target-feature-matrix/SKILL.md`。
- 当任务涉及 **missing-feature-detector** 时，调用 `skills/missing-feature-detector/SKILL.md`。
- 当任务涉及 **behavior-mismatch-classifier** 时，调用 `skills/behavior-mismatch-classifier/SKILL.md`。
- 当任务涉及 **minimal-counterexample-generator** 时，调用 `skills/minimal-counterexample-generator/SKILL.md`。
- 当任务涉及 **suspected-code-slice-locator** 时，调用 `skills/suspected-code-slice-locator/SKILL.md`。
- 当任务涉及 **patch-existing-decision** 时，调用 `skills/patch-existing-decision/SKILL.md`。
- 当任务涉及 **regenerate-module-decision** 时，调用 `skills/regenerate-module-decision/SKILL.md`。
- 当任务涉及 **retranslate-project-decision** 时，调用 `skills/retranslate-project-decision/SKILL.md`。
- 当任务涉及 **manual-redesign-decision** 时，调用 `skills/manual-redesign-decision/SKILL.md`。
- 当任务涉及 **counterexample-guided-repair** 时，调用 `skills/counterexample-guided-repair/SKILL.md`。
- 当任务涉及 **repair-regression-validator** 时，调用 `skills/repair-regression-validator/SKILL.md`。
- 当任务涉及 **repair-evidence-generator** 时，调用 `skills/repair-evidence-generator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `source-target-feature-matrix` | 从源目标仓库建立页面、接口、状态、数据、权限、平台能力和运维功能矩阵。 |
| `missing-feature-detector` | 识别源有目标无、目标仅占位、部分实现和未接线功能。 |
| `behavior-mismatch-classifier` | 将差异分类为请求、状态、路由、数据、副作用、并发、视觉、平台或性能问题。 |
| `minimal-counterexample-generator` | 生成能稳定复现源目标不等价的最小输入、状态和事件轨迹。 |
| `suspected-code-slice-locator` | 将反例映射到最相关的源目标文件、符号、调用和规则。 |
| `patch-existing-decision` | 判断当前目标架构正确且差异局部时是否继续补丁修复。 |
| `regenerate-module-decision` | 判断模块质量或语义偏差过大时是否保留外围并重新生成核心模块。 |
| `retranslate-project-decision` | 判断整体架构、技术选型或功能覆盖过差时是否重新转换整库。 |
| `manual-redesign-decision` | 识别目标平台无直接等价能力或 UX 需重构时的人工设计点。 |
| `counterexample-guided-repair` | 依据结构化反例生成修复候选，并通过构建、测试和双运行迭代收敛。 |
| `repair-regression-validator` | 确保修复解决当前反例且未破坏已通过功能、性能和安全门禁。 |
| `repair-evidence-generator` | 记录差异、根因、补丁、验证、残余风险和最终状态证据。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
