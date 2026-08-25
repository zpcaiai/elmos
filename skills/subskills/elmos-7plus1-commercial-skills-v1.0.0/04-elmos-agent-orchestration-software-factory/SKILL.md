---
name: elmos-agent-orchestration-software-factory
description: 以 Symphony-style reconciler、任务 DAG、隔离 workspace、专业化 Agent、可续接子 Agent、Workpad、Review 和 Proof-of-Work 组织大型项目生成与跨库转换。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P04
  version: 1.0.0
  phase: "Phase 2（商业软件工厂）"
  dependencies: "00, 01, 02, 03, 05, 06"
  maturity: commercial-product-blueprint
---

# Elmos 多 Agent 编排与自主软件工厂

## 使命

将复杂长任务拆成可管理、可恢复、可并行、可验收的工程单元，降低单 Agent 上下文过载、自我审查和假完成。

## 何时调用

- 用户或上游任务明确需要本包的能力范围。
- 本包依赖的输入或合同发生版本变化，需要重新构建、验证或迁移。
- P05、生产监控、上游 breaking change 或客户验收发现本包相关缺口。
- 不应调用本包来绕过其他包的边界；详见“禁止事项”。

## 必需输入

- 目标仓库或项目生成需求，以及不可变 source revision / request revision。
- 租户、项目、隐私、预算、时间、允许的模型/Provider/工具和审批策略。
- 上游 Package 输出与其 Schema 版本；缺少依赖时必须阻断。
- 选定 Phase、目标 maturity（prototype/internal-beta/commercial-ga）和认证等级。

## 依赖与边界

**依赖：** P00, P01, P02, P03, P05, P06

- 调度器负责工作，不负责改变语义真相或降低 P05 Gate。
- Agent 角色是权限和责任边界，不是提示词别名。
- 外部 issue tracker 只是任务源，仓库内 workpad/contract/evidence 才是执行记录。

## 执行工作流

1. 读取本包 `PRODUCT-CAPABILITY-SPEC.md`、`ARCHITECTURE.md` 与 `ACCEPTANCE-GATES.md`，确认范围和硬不变量。
2. 执行 `readiness`：检查依赖包、Schema、源版本、权限、沙箱、模型、工具、预算和环境。
3. 创建或更新本包 Workpad：计划、验收、验证、风险、假设、阻塞与证据索引。
4. 按 `PHASE-PLAN.md` 和 `IMPLEMENTATION-BACKLOG.md` 选择最小可交付工作流，不跨越未通过的 Phase Gate。
5. 执行子 Skills；所有输出使用 `schemas/` 与根目录共享 Schema 校验，并写入版本化事件/台账。
6. 运行 `BENCHMARKS-AND-EVALS.md` 中与变更相关的定向测试和影响闭包回归。
7. 把结果送入 P05 Evidence Gate；失败则进入诊断/修复，禁止用文本声明替代证据。
8. 通过后生成 handoff：变更、证据、残余风险、成本、系统 ETA、回滚和兼容性。

## 硬不变量

- 同一任务在任一时刻只有一个 authoritative active run，除非明确 shadow/canary。
- 任务状态每轮从外部源和 durable run state 重对账，禁止只相信内存。
- workspace key 经过 sanitize/canonicalize，禁止逃出 root。
- Generator 与最终 Verifier/Reviewer 权限分离，Verifier 默认无代码写权限。
- 重试不得重复已提交副作用；所有副作用具备 idempotency/compensation 语义。
- 进入 Human Review/Done 前必须完成所有验收、PR 反馈和 P05 证据。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/workflow-tracker-adapter/SKILL.md` | 统一 GitHub/Linear/Jira/GitLab/内部队列的 Issue 状态、标签、链接和评论。 |
| `skills/reconciliation-scheduler/SKILL.md` | 持续把外部任务状态、运行状态与工作流合同收敛到一致。 |
| `skills/task-dag-orchestrator/SKILL.md` | 按依赖、风险、资源和验证门调度项目生成/转换任务。 |
| `skills/workspace-worktree-manager/SKILL.md` | 为每个任务创建安全、持久、可恢复的仓库副本。 |
| `skills/specialized-agent-registry/SKILL.md` | 把职责、输入输出、模型、工具、权限和预算变成可组合角色合同。 |
| `skills/continuable-collaboration-manager/SKILL.md` | 管理父子 Agent 的持久会话、消息、报告和中断。 |
| `skills/admission-concurrency-controller/SKILL.md` | 控制全局、租户、项目、状态、模型、工具与数据库资源竞争。 |
| `skills/retry-stall-doomloop-controller/SKILL.md` | 区分可重试错误、任务无进展和模型重复行为，并分级恢复。 |
| `skills/workpad-progress-journal/SKILL.md` | 维护单一计划、验收、验证、环境、发现和 blocker 记录。 |
| `skills/review-feedback-coordinator/SKILL.md` | 收集并闭环 PR 顶层、inline、review summary、机器人和人工反馈。 |
| `skills/proof-of-work-assembler/SKILL.md` | 把代码、测试、CI、媒体、性能、安全、复杂度和 P05 证据组装成可审查交付。 |
| `skills/human-review-handoff/SKILL.md` | 在自动验证完成后以最少认知负担交给人类审批、重做或合并。 |

## 必须产出

- P04 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- 所有 active task 可从 durable state 重建，不依赖单进程内存。
- 并发/重试测试中无重复提交、重复 PR、重复数据迁移等副作用。
- Workpad 的 Plan/Acceptance/Validation 与真实完成状态一致。
- 进入 Human Review 前 outstanding actionable feedback=0 且 P05 Gate=pass。
- Tracker 凭据与生产 Secret 不出现在 Agent 环境、日志、证据或生成仓库。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| Tracker 暂时不可用 | 使用 last snapshot、暂停新调度、保持 active run 策略并指数退避。 |
| 任务运行卡住 | fingerprint 进展、注入 steering、切换更强模型/角色、最终 stop 并保留证据。 |
| workspace 污染/冲突 | 隔离该 workspace，重新从 Pin 创建；不复用未知状态。 |
| review 循环无穷 | 按反馈 ID 去重，识别互相冲突的要求并升级人工决策。 |
| 子 Agent 失联 | 从 durable child session 冷恢复或标记 interrupted；父任务继续安全处理。 |

## 禁止事项

- 禁止把“模型说已完成”“代码看起来合理”“大部分测试通过”作为完成证据。
- 禁止静默忽略 unsupported capability、低置信结论、失败 Hook、partial sandbox 或过期证据。
- 禁止跨租户复用代码、Prompt、Trace、规则或修复案例，除非有明确 scope 与授权。
- 禁止直接跟随上游 main/dev/preview；必须使用 Pin、Adapter 和 conformance tests。
- 禁止降低验收标准来修复失败；应修改实现、扩大证据或明确 blocker/waiver。

## 参考文件

- `README.md`
- `PRODUCT-CAPABILITY-SPEC.md`
- `ARCHITECTURE.md`
- `PHASE-PLAN.md`
- `INTERFACE-CONTRACTS.md`
- `DATA-AND-EVENT-MODEL.md`
- `SECURITY-AND-GOVERNANCE.md`
- `OBSERVABILITY-AND-SLO.md`
- `BENCHMARKS-AND-EVALS.md`
- `ACCEPTANCE-GATES.md`
- `FAILURE-MODES-AND-RECOVERY.md`
- `IMPLEMENTATION-BACKLOG.md`
