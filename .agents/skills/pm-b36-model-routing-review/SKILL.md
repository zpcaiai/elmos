---
name: pm-b36-model-routing-review
description: "按方向、风险、成本、私有化和历史表现动态选择模型，并用不同模型家族独立审查以降低共因错误. Precision Migration B36 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 36：模型路由与异构审查
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b36-model-routing-review`.
- Immutable source identity: `batch-36-model-routing-review` in `precision-migration-b01-44` (B36).
- Runtime adapter: `model-routing-and-agent-harness`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b36-model-routing-review`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

按方向、风险、成本、私有化和历史表现动态选择模型，并用不同模型家族独立审查以降低共因错误。

## Position in the system

- Phase: `J 模型与Agent执行系统`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 计算风险并拆分任务
2. 选择模型与隔离工作区
3. 执行并收集客观反馈
4. 独立审查和升级
5. 持久化状态、证据、成本与审批

## Shared gates

- Agent不得修改门槛以通过
- 高风险生成与审查应异构
- 所有外部副作用必须幂等或受控

## Dispatch rules

- 当任务涉及 **model-capability-registry** 时，调用 `../pm-b36-model-capability-registry/SKILL.md`。
- 当任务涉及 **task-risk-scoring** 时，调用 `../pm-b36-task-risk-scoring/SKILL.md`。
- 当任务涉及 **language-pair-model-ranking** 时，调用 `../pm-b36-language-pair-model-ranking/SKILL.md`。
- 当任务涉及 **cost-aware-model-routing** 时，调用 `../pm-b36-cost-aware-model-routing/SKILL.md`。
- 当任务涉及 **private-model-routing** 时，调用 `../pm-b36-private-model-routing/SKILL.md`。
- 当任务涉及 **byok-provider-adapter** 时，调用 `../pm-b36-byok-provider-adapter/SKILL.md`。
- 当任务涉及 **heterogeneous-model-review** 时，调用 `../pm-b36-heterogeneous-model-review/SKILL.md`。
- 当任务涉及 **stronger-model-escalation** 时，调用 `../pm-b36-stronger-model-escalation/SKILL.md`。
- 当任务涉及 **model-output-calibration** 时，调用 `../pm-b36-model-output-calibration/SKILL.md`。
- 当任务涉及 **cost-per-accepted-module** 时，调用 `../pm-b36-cost-per-accepted-module/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `model-capability-registry` | 登记模型版本、上下文、工具能力、部署方式、成本和各方向实测指标。 |
| `task-risk-scoring` | 根据动态语义、并发、事务、平台、测试缺口和影响面计算任务风险。 |
| `language-pair-model-ranking` | 按具体语言/框架/数据库方向排名模型，而非依赖通用榜单。 |
| `cost-aware-model-routing` | 在发布门槛不变的前提下最小化每个验收模块的模型与计算成本。 |
| `private-model-routing` | 在数据策略、内网、国产化和硬件约束下选择客户私有模型。 |
| `byok-provider-adapter` | 支持客户自带 OpenAI、Anthropic、Gemini、国产或 OpenAI兼容模型凭证。 |
| `heterogeneous-model-review` | 由不同供应商模型独立生成测试、攻击假设和审查高风险实现。 |
| `stronger-model-escalation` | 当修复轮数、证明失败或风险超阈值时自动升级更强模型或人工。 |
| `model-output-calibration` | 用客观构建、测试、差分和历史数据校准模型置信表达。 |
| `cost-per-accepted-module` | 统计每个通过全部门禁模块的 Token、计算、时间和人工成本。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
