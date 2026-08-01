---
name: batch-01-competition-positioning
description: 持续识别国内外现代化、代码转换、数据库迁移和验证产品的能力边界，并形成可执行的差异化与商业切入策略。
---

# Batch 01：竞争格局与产品定位

## Goal

持续识别国内外现代化、代码转换、数据库迁移和验证产品的能力边界，并形成可执行的差异化与商业切入策略。

## Position in the system

- Phase: `A 市场、评估与转换决策`
- Included skills: `6`
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

- 当任务涉及 **competitor-capability-radar** 时，调用 `skills/competitor-capability-radar/SKILL.md`。
- 当任务涉及 **capability-gap-analyzer** 时，调用 `skills/capability-gap-analyzer/SKILL.md`。
- 当任务涉及 **build-buy-partner-decision** 时，调用 `skills/build-buy-partner-decision/SKILL.md`。
- 当任务涉及 **platform-commoditization-risk** 时，调用 `skills/platform-commoditization-risk/SKILL.md`。
- 当任务涉及 **vertical-market-selector** 时，调用 `skills/vertical-market-selector/SKILL.md`。
- 当任务涉及 **differentiation-strategy-generator** 时，调用 `skills/differentiation-strategy-generator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `competitor-capability-radar` | 持续跟踪竞争产品、开源项目和云平台在评估、转换、验证、私有化与发布治理方面的能力变化。 |
| `capability-gap-analyzer` | 将本系统能力与选定竞争者进行结构化对比，找出缺口、重叠、领先点与优先补齐项。 |
| `build-buy-partner-decision` | 依据战略重要性、成熟度、成本、数据壁垒和交付责任，决定自研、采购、集成或合作。 |
| `platform-commoditization-risk` | 评估某项转换或验证能力被基础模型、云厂商或开源工具快速商品化的风险。 |
| `vertical-market-selector` | 从语言方向、行业、客户类型和交付痛点中选择最有商业闭环的垂直市场。 |
| `differentiation-strategy-generator` | 生成模型中立、深度验证、私有部署、行业语义和证据交付导向的差异化方案。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
