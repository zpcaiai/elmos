---
name: batch-43-continuous-modernization-learning
description: 持续扫描技术债和框架漂移，把真实失败、成功修复和证据反馈沉淀为更强的规则、方向包和黄金回归。
---

# Batch 43：持续现代化与自演进

## Goal

持续扫描技术债和框架漂移，把真实失败、成功修复和证据反馈沉淀为更强的规则、方向包和黄金回归。

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

- 当任务涉及 **scheduled-repository-analysis** 时，调用 `skills/scheduled-repository-analysis/SKILL.md`。
- 当任务涉及 **technical-debt-drift-detection** 时，调用 `skills/technical-debt-drift-detection/SKILL.md`。
- 当任务涉及 **framework-obsolescence-monitor** 时，调用 `skills/framework-obsolescence-monitor/SKILL.md`。
- 当任务涉及 **security-modernization-scan** 时，调用 `skills/security-modernization-scan/SKILL.md`。
- 当任务涉及 **rule-performance-monitor** 时，调用 `skills/rule-performance-monitor/SKILL.md`。
- 当任务涉及 **counterexample-knowledge-store** 时，调用 `skills/counterexample-knowledge-store/SKILL.md`。
- 当任务涉及 **successful-repair-rule-induction** 时，调用 `skills/successful-repair-rule-induction/SKILL.md`。
- 当任务涉及 **transformation-quality-learning** 时，调用 `skills/transformation-quality-learning/SKILL.md`。
- 当任务涉及 **golden-repository-regression** 时，调用 `skills/golden-repository-regression/SKILL.md`。
- 当任务涉及 **direction-pack-continuous-improvement** 时，调用 `skills/direction-pack-continuous-improvement/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `scheduled-repository-analysis` | 按计划重新分析仓库、依赖、版本、架构、测试和运行风险。 |
| `technical-debt-drift-detection` | 检测新技术债、已修复问题回归和跨仓库治理漂移。 |
| `framework-obsolescence-monitor` | 监控框架生命周期、废弃 API、运行时支持和迁移窗口。 |
| `security-modernization-scan` | 持续识别漏洞、危险 API、依赖、配置、权限和安全现代化需求。 |
| `rule-performance-monitor` | 跟踪规则命中、构建、验证、误报、漏报、修复轮数和成本。 |
| `counterexample-knowledge-store` | 存储方向、源码模式、错误目标、最小反例、根因、修复和版本。 |
| `successful-repair-rule-induction` | 从重复成功修复中归纳新规则、前置条件和测试。 |
| `transformation-quality-learning` | 用真实验收结果校准模型、路由、估计、规则优先级和风险评分。 |
| `golden-repository-regression` | 在代表性黄金仓库矩阵上持续执行转换、构建、差分和证据回归。 |
| `direction-pack-continuous-improvement` | 根据版本、失败、性能和客户私有知识迭代方向包。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
