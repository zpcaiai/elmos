---
name: batch-37-agentic-migration-harness
description: 把迁移拆分为可暂停、可恢复、可重试、可审计的任务图，并让多个隔离Agent在客观门禁下协作。
---

# Batch 37：Agentic Migration Harness

## Goal

把迁移拆分为可暂停、可恢复、可重试、可审计的任务图，并让多个隔离Agent在客观门禁下协作。

## Position in the system

- Phase: `J 模型与Agent执行系统`
- Included skills: `12`
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

- 当任务涉及 **migration-task-decomposer** 时，调用 `skills/migration-task-decomposer/SKILL.md`。
- 当任务涉及 **semantic-slice-task-planner** 时，调用 `skills/semantic-slice-task-planner/SKILL.md`。
- 当任务涉及 **multi-agent-worktree-manager** 时，调用 `skills/multi-agent-worktree-manager/SKILL.md`。
- 当任务涉及 **build-repair-agent** 时，调用 `skills/build-repair-agent/SKILL.md`。
- 当任务涉及 **test-migration-agent** 时，调用 `skills/test-migration-agent/SKILL.md`。
- 当任务涉及 **difference-diagnosis-agent** 时，调用 `skills/difference-diagnosis-agent/SKILL.md`。
- 当任务涉及 **proof-agent** 时，调用 `skills/proof-agent/SKILL.md`。
- 当任务涉及 **security-review-agent** 时，调用 `skills/security-review-agent/SKILL.md`。
- 当任务涉及 **human-approval-gate** 时，调用 `skills/human-approval-gate/SKILL.md`。
- 当任务涉及 **pause-resume-cancel** 时，调用 `skills/pause-resume-cancel/SKILL.md`。
- 当任务涉及 **retry-and-idempotency** 时，调用 `skills/retry-and-idempotency/SKILL.md`。
- 当任务涉及 **token-and-resource-governance** 时，调用 `skills/token-and-resource-governance/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `migration-task-decomposer` | 按依赖、风险、模块、语言和验证边界拆分迁移任务图。 |
| `semantic-slice-task-planner` | 为每个 Agent 准备最小语义切片、契约、规则、工具和验收条件。 |
| `multi-agent-worktree-manager` | 为并行 Agent 创建隔离 Worktree/Workspace，控制冲突、合并和回滚。 |
| `build-repair-agent` | 消费结构化编译/构建诊断，生成最小修复并持续验证。 |
| `test-migration-agent` | 迁移源测试、保留 Oracle、补充目标测试并阻止弱化断言。 |
| `difference-diagnosis-agent` | 分析源目标差分、定位根因、提出修复或规格冲突分类。 |
| `proof-agent` | 生成证明义务、调用 Leanstral/SMT、解释反例并回写测试。 |
| `security-review-agent` | 独立审查权限、输入、Secret、供应链、沙箱和生成代码安全。 |
| `human-approval-gate` | 在高风险、规格冲突、语义损失、生产切流和例外放行处要求人工批准。 |
| `pause-resume-cancel` | 持久化任务状态、证据和副作用，支持安全暂停、恢复和取消。 |
| `retry-and-idempotency` | 确保 Agent 工具调用、构建、数据初始化和外部副作用可安全重试。 |
| `token-and-resource-governance` | 按任务、租户、模型、阶段和风险治理 Token、计算、并发和预算。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
