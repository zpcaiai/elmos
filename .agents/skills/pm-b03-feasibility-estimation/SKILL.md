---
name: pm-b03-feasibility-estimation
description: "基于项目特征、方向包成熟度、测试资产和代表切片试点，给出有区间、有置信度、可校准的转换预测. Precision Migration B03 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 03：转换可行性、正确率和耗时预测
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b03-feasibility-estimation`.
- Immutable source identity: `batch-03-feasibility-estimation` in `precision-migration-b01-44` (B03).
- Runtime adapter: `assessment-and-target-planning`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b03-feasibility-estimation`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

基于项目特征、方向包成熟度、测试资产和代表切片试点，给出有区间、有置信度、可校准的转换预测。

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

- 当任务涉及 **conversion-feasibility-estimator** 时，调用 `../pm-b03-conversion-feasibility-estimator/SKILL.md`。
- 当任务涉及 **conversion-success-range-estimator** 时，调用 `../pm-b03-conversion-success-range-estimator/SKILL.md`。
- 当任务涉及 **estimate-confidence-calibrator** 时，调用 `../pm-b03-estimate-confidence-calibrator/SKILL.md`。
- 当任务涉及 **conversion-duration-estimator** 时，调用 `../pm-b03-conversion-duration-estimator/SKILL.md`。
- 当任务涉及 **conversion-cost-estimator** 时，调用 `../pm-b03-conversion-cost-estimator/SKILL.md`。
- 当任务涉及 **iteration-count-planner** 时，调用 `../pm-b03-iteration-count-planner/SKILL.md`。
- 当任务涉及 **manual-effort-estimator** 时，调用 `../pm-b03-manual-effort-estimator/SKILL.md`。
- 当任务涉及 **conversion-risk-register** 时，调用 `../pm-b03-conversion-risk-register/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `conversion-feasibility-estimator` | 判断整体转换、局部迁移、兼容层、重新设计或保持源实现的可行性。 |
| `conversion-success-range-estimator` | 估算自动覆盖率、首轮构建率、功能等价率、行为等价率和生产就绪概率区间。 |
| `estimate-confidence-calibrator` | 依据样本量、同类历史、未知项和试点结果校准预测置信度，避免虚假精确。 |
| `conversion-duration-estimator` | 分解估算扫描、建模、生成、构建、测试、差分、修复、性能和人工审核耗时。 |
| `conversion-cost-estimator` | 估算模型、计算、工具链、测试环境、人工、私有部署和持续维护成本。 |
| `iteration-count-planner` | 根据风险和预期失败类型规划转换、构建修复、差分修复和升级模型的轮次。 |
| `manual-effort-estimator` | 估算需要人工处理的比例、工作量、技能组合和关键审批点。 |
| `conversion-risk-register` | 维护语义、依赖、数据、并发、性能、平台、合规和交付风险及其缓解措施。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
