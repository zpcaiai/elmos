---
name: pm-b04-target-recommendation
description: "判断用户指定目标是否真正适合实际应用，并比较目标语言、框架、部署形态和迁移策略的长期收益与风险. Precision Migration B04 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 04：目标语言与目标架构建议
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b04-target-recommendation`.
- Immutable source identity: `batch-04-target-recommendation` in `precision-migration-b01-44` (B04).
- Runtime adapter: `assessment-and-target-planning`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b04-target-recommendation`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

判断用户指定目标是否真正适合实际应用，并比较目标语言、框架、部署形态和迁移策略的长期收益与风险。

## Position in the system

- Phase: `A 市场、评估与转换决策`
- Included skills: `8`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 确认决策问题与可比较边界
2. 收集可验证证据并标准化
3. 应用评分/比较/试点模型
4. 显式列出未知项和敏感假设
5. 输出推荐、备选与拒绝条件

## Shared gates

- 不得给出无依据的单点正确率
- 所有预测必须带区间、置信度和证据
- 收益低于风险时必须允许 DO_NOT_CONVERT

## Dispatch rules

- 当任务涉及 **target-language-suitability-analysis** 时，调用 `../pm-b04-target-language-suitability-analysis/SKILL.md`。
- 当任务涉及 **target-framework-selector** 时，调用 `../pm-b04-target-framework-selector/SKILL.md`。
- 当任务涉及 **target-platform-benefit-analysis** 时，调用 `../pm-b04-target-platform-benefit-analysis/SKILL.md`。
- 当任务涉及 **migration-alternative-generator** 时，调用 `../pm-b04-migration-alternative-generator/SKILL.md`。
- 当任务涉及 **architecture-migration-strategy** 时，调用 `../pm-b04-architecture-migration-strategy/SKILL.md`。
- 当任务涉及 **do-not-convert-advisor** 时，调用 `../pm-b04-do-not-convert-advisor/SKILL.md`。
- 当任务涉及 **team-capability-fit-analysis** 时，调用 `../pm-b04-team-capability-fit-analysis/SKILL.md`。
- 当任务涉及 **migration-business-case** 时，调用 `../pm-b04-migration-business-case/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `target-language-suitability-analysis` | 分析目标语言在性能、并发、安全、生态、人才、维护、部署和迁移风险方面的适配度。 |
| `target-framework-selector` | 基于业务形态、非功能需求、团队能力和生态成熟度选择目标框架。 |
| `target-platform-benefit-analysis` | 判断跨 Web、移动端、ArkUI、小程序或桌面平台迁移能否带来真实业务收益。 |
| `migration-alternative-generator` | 生成整体转换、局部转换、双端保留、服务化、兼容层和重新设计等替代方案。 |
| `architecture-migration-strategy` | 选择 Strangler、Rewrite、Wrap、Retain、Replatform、模块重建或服务拆分策略。 |
| `do-not-convert-advisor` | 当收益低于风险、目标不适合或缺乏等价能力时，明确给出不转换或先治理建议。 |
| `team-capability-fit-analysis` | 评估团队对目标语言、框架、工具链、运维和长期维护的能力匹配与培训成本。 |
| `migration-business-case` | 汇总成本、收益、风险、TCO、机会成本和退出能力，形成可决策的商业论证。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
