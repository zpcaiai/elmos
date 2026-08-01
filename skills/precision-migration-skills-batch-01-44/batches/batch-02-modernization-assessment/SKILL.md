---
name: batch-02-modernization-assessment
description: 在任何转换前恢复应用架构、功能、依赖、技术债、阻断项和现代化选择，并生成面向管理与工程团队的评估结论。
---

# Batch 02：应用现代化自动评估

## Goal

在任何转换前恢复应用架构、功能、依赖、技术债、阻断项和现代化选择，并生成面向管理与工程团队的评估结论。

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

- 当任务涉及 **repository-modernization-assessment** 时，调用 `skills/repository-modernization-assessment/SKILL.md`。
- 当任务涉及 **application-architecture-recovery** 时，调用 `skills/application-architecture-recovery/SKILL.md`。
- 当任务涉及 **modernization-readiness-score** 时，调用 `skills/modernization-readiness-score/SKILL.md`。
- 当任务涉及 **modernization-blocker-discovery** 时，调用 `skills/modernization-blocker-discovery/SKILL.md`。
- 当任务涉及 **technical-debt-inventory** 时，调用 `skills/technical-debt-inventory/SKILL.md`。
- 当任务涉及 **modernization-option-comparator** 时，调用 `skills/modernization-option-comparator/SKILL.md`。
- 当任务涉及 **representative-slice-pilot** 时，调用 `skills/representative-slice-pilot/SKILL.md`。
- 当任务涉及 **assessment-report-generator** 时，调用 `skills/assessment-report-generator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `repository-modernization-assessment` | 对源仓库执行端到端现代化评估，覆盖架构、代码、依赖、数据、安全、测试、运维和团队适配。 |
| `application-architecture-recovery` | 从静态代码、配置、部署文件和运行 Trace 中恢复应用模块、边界、调用、数据与部署架构。 |
| `modernization-readiness-score` | 从可转换性、测试、可观测性、依赖、风险和组织准备度计算可解释的现代化就绪评分。 |
| `modernization-blocker-discovery` | 发现反射、动态加载、原生库、私有框架、平台 API、隐式事务和未观测行为等阻断项。 |
| `technical-debt-inventory` | 生成版本、框架、依赖、安全、架构、测试和运维技术债清单，并按风险和收益排序。 |
| `modernization-option-comparator` | 比较保留、升级、重新平台化、重构、重写、包装和退役等现代化路径。 |
| `representative-slice-pilot` | 自动选择代表性语义切片执行试转换，以校准正确率、修复轮数、成本和风险。 |
| `assessment-report-generator` | 输出管理层摘要、技术评估、风险登记、路线图和可审计证据索引。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
