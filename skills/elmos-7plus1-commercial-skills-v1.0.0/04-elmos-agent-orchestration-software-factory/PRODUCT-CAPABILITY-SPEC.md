# P04 产品能力规范：Elmos 多 Agent 编排与自主软件工厂

## 1. 产品定位

以 Symphony-style reconciler、任务 DAG、隔离 workspace、专业化 Agent、可续接子 Agent、Workpad、Review 和 Proof-of-Work 组织大型项目生成与跨库转换。

**客户可感知价值：** 将复杂长任务拆成可管理、可恢复、可并行、可验收的工程单元，降低单 Agent 上下文过载、自我审查和假完成。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 实现 repo-owned WORKFLOW、任务源 Adapter、轮询/事件 reconciliation 和动态配置。
- 每个 Issue/Task 使用隔离、持久、可清理的 workspace/worktree。
- 定义 Analyst/Discovery/Scout/IR/Planner/Generator/Reviewer/Verifier/Gap/Repair/Security/Perf 等角色。
- 支持 one-shot 与 continuable subagent、父子 lineage、报告、steering、interrupt 和 budget。
- 实现全局/租户/项目/状态/工具/模型多层并发与 admission control。
- 实现 retry/backoff/stall/doom-loop/escalation、幂等恢复和副作用隔离。
- 以单一 Workpad 管理计划、验收、验证、发现、PR 反馈和 handoff。
- 将 CI、review、diff、媒体、复杂度、安全与行为证据组成 Proof-of-Work。

## 4. 非目标与产品边界

- 调度器负责工作，不负责改变语义真相或降低 P05 Gate。
- Agent 角色是权限和责任边界，不是提示词别名。
- 外部 issue tracker 只是任务源，仓库内 workpad/contract/evidence 才是执行记录。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Workflow & Tracker Adapters | GitHub/Linear/Jira/GitLab/自有队列的统一 Issue contract。 | P04-C01 |
| Reconciliation Scheduler | 轮询/事件触发、状态重对账、run admission、stop/retry/remove。 | P04-C02 |
| Task DAG Orchestrator | 依赖、优先级、风险、并行、阻塞、资源和证据传播。 | P04-C03 |
| Workspace/Worktree Manager | 隔离创建、初始化 Hook、持久化、清理、路径安全和缓存。 | P04-C04 |
| Specialized Agent Registry | 角色、model、tools、persona、budget、permissions、input/output schema。 | P04-C05 |
| Continuable Collaboration Manager | child session、FIFO follow-up、report、steer、interrupt、lineage。 | P04-C06 |
| Admission & Concurrency Controller | 全局/租户/项目/状态/资源配额和公平调度。 | P04-C07 |
| Recovery & Doom-loop Controller | backoff、stalled detection、deterministic loop fingerprint、升级/切换策略。 | P04-C08 |
| Workpad & Progress Journal | 唯一计划/验收/验证记录、环境 stamp、milestone 和 blocker。 | P04-C09 |
| Review & Feedback Coordinator | PR top-level/inline/review 状态、机器人与人工反馈闭环。 | P04-C10 |
| Proof-of-Work Assembler | CI、测试、diff、媒体、性能、安全、复杂度和证据汇总。 | P04-C11 |
| Operations Dashboard | runs、queues、budgets、rate limits、ETA、errors、stalls、human gates。 | P04-C12 |

## 6. 关键用户旅程

### 6.1 新项目生成

1. 导入自然语言、多模态需求与商业约束。
2. 通过 P02/P03 建立需求、能力、架构与实施 DAG。
3. P04 调度专业 Agent，P01 负责可靠执行，P06 负责模型/Provider 路由。
4. P05 执行覆盖、差分、E2E、非功能与证据 Gate。
5. P00 返回系统墙钟 ETA、真实成本、交付物、风险、认证与回滚。
6. P07 只沉淀经过验证且授权的可复用知识。

### 6.2 跨语言/跨框架/跨库转换

1. 固定源仓库 revision 和运行环境，P02 扫描并建立 Repository Graph/IR/Ledger。
2. P03 选择规则、生成 Target IR、代码、迁移与双运行计划。
3. P04 分任务并行实施；Generator 与 Verifier 分权。
4. P05 在相同场景下比较源/目标行为，发现 gap 后进入 Repair Loop。
5. 只有 Evidence Gate 通过才允许切流、合并或认证。

## 7. 商业版本建议

| 版本 | 能力范围 | 限制 |
| --- | --- | --- |
| Community/Developer | 单用户、本地仓库、基础运行与报告 | 无企业 SLA；默认不含生产 cutover。 |
| Team | 团队项目、共享规则、并发、CI/PR、成本与质量 Dashboard | 组织内知识隔离。 |
| Enterprise | 多租户、SSO/RBAC、私有部署、BYOK/ZDR、审计、SLA、E1–E5 | 需客户安全与数据政策配置。 |
| Regulated | 金融/医疗/工业等专用基线、双人审批、WORM 证据、区域部署 | 按场景认证，不承诺无限通用。 |

## 8. 成功指标

- **结果指标：** Requirement coverage、Capability coverage、Behavioral equivalence、Critical unknown gaps、人工介入率。
- **运行指标：** 成功恢复率、重复副作用率、任务完成时长、模型/工具成本、缓存命中与 Provider fallback。
- **商业指标：** 项目毛利、交付周期、试点转付费、复购、SLA 违约、支持成本。
- **知识复利：** trusted rules 数量、复用率、规则命中后的质量/成本改善、bad-rule escape rate。

指标必须带 scenario/规模/版本/样本量/置信区间；不发布无上下文的统一“准确率”。

## 9. 硬不变量

- 同一任务在任一时刻只有一个 authoritative active run，除非明确 shadow/canary。
- 任务状态每轮从外部源和 durable run state 重对账，禁止只相信内存。
- workspace key 经过 sanitize/canonicalize，禁止逃出 root。
- Generator 与最终 Verifier/Reviewer 权限分离，Verifier 默认无代码写权限。
- 重试不得重复已提交副作用；所有副作用具备 idempotency/compensation 语义。
- 进入 Human Review/Done 前必须完成所有验收、PR 反馈和 P05 证据。

## 10. 依赖与集成

- 上游依赖：P00, P01, P02, P03, P05, P06。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。
