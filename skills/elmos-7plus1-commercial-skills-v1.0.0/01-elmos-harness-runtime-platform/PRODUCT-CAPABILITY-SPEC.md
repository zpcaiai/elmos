# P01 产品能力规范：Elmos 可插拔 Harness 运行时平台

## 1. 产品定位

统一 Agent、Session、Tool、Skill、Sandbox、Permission、Approval、Subagent、Async Task、LSP、API 和持久化能力。

**客户可感知价值：** 复用成熟 Harness 的执行能力，同时让 Elmos 的核心转换算法、数据与完成裁决保持独立可控。

## 2. 目标用户与场景

- 企业架构师与现代化负责人：需要大型仓库理解、迁移和可审计交付。
- 软件研发团队：需要从需求生成完整项目、自动验证与持续修复。
- 平台/DevOps/SRE：需要长任务恢复、资源治理、成本、SLA、灰度与回滚。
- 安全/合规/审计：需要最小权限、凭据隔离、证据链、SBOM 和数据治理。
- Elmos 内部能力团队：需要稳定公共合同、Benchmark、回归和知识复利。

## 3. 业务目标

- 定义 HarnessRuntime SPI 与 DeepSeek/OpenCode/OpenHarness/Codex/Claude/native Adapter。
- 实现追加式事实日志、可回放 Session、fork/resume、崩溃恢复和上下文 Epoch。
- 实现强类型 Tool Runtime、统一结果、严格 Schema、Hooks、并发、超时、取消和审批。
- 实现同步/后台/延迟任务、跨进程完成、通用 task control 和 continuable subagent。
- 实现 action×resource 权限、硬性敏感路径拒绝、主机凭据隔离和 per-call sandbox。
- 提供 Headless OpenAPI/SSE Runtime Server，让 Web IDE、CLI、Desktop、CI 共用同一执行内核。

## 4. 非目标与产品边界

- 不决定项目生成/转换语义是否正确；P02/P03/P05 负责。
- 外部 Harness 只通过 Adapter 接入，禁止其内部事件或存储格式泄漏到域层。
- 所有“部分支持”能力必须显式暴露 enforcement/capability，不得静默忽略。

## 5. 核心能力地图

| 组件 | 职责 | Capability ID |
| --- | --- | --- |
| Harness SPI & Adapter SDK | 稳定的能力发现、启动、执行、取消、状态、事件和错误合同。 | P01-C01 |
| Reversible Plugin Context | Service Definition/Provider/Consumer、可逆注册、作用域与热重载。 | P01-C02 |
| Event-Sourced Session Runtime | 追加日志、fork/resume/replay、上下文 Epoch、崩溃闭合与格式版本。 | P01-C03 |
| Tool Runtime | 严格 Schema、输出标准化、Hooks、exclusive/parallel、timeouts、approval 和 finalizer。 | P01-C04 |
| Async Task Runtime | sync/background/deferred、跨进程 resolve/fail/cancel、task check/steer/result。 | P01-C05 |
| Subagent Runtime | one-shot/continuable child、持久 lineage、FIFO、冷恢复、直接父授权。 | P01-C06 |
| Permission & Approval Plane | action-resource 策略、硬拒绝、临时/持久授权、可审计决策。 | P01-C07 |
| Sandbox & Workspace Runtime | read-only/workspace-write/full access、执行事实、worktree 与临时目录。 | P01-C08 |
| Context & Compaction Runtime | prompt admission、safe turn boundary、micro/full compaction、结构化 carryover。 | P01-C09 |
| LSP Capability Seam | 按扩展选择 Provider，规范化 definition/reference/implementation/hover。 | P01-C10 |
| Runtime Server & SDK | OpenAPI、SSE、Session/Tool/File/LSP/MCP/Permission API、多客户端。 | P01-C11 |
| Readiness & Conformance | dry-run 检测模型、工具、沙箱、路径、凭据、网络和 Adapter 能力。 | P01-C12 |

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

- 模型可见事实要么来自持久事件，要么被标记为 transient 且不得影响可回放决策。
- 工具参数在执行前通过 Schema、权限、审批、沙箱和业务 Guard 全部检查。
- confined 请求无法获得 full/accepted enforcement 时必须失败，不得裸执行。
- 审批只有 allowed-once 是授权；unavailable、cancelled、rejected 全部拒绝。
- Subagent 不得超过深度、工具、persona、预算和直接父子授权范围。
- Adapter 升级必须通过跨实现 conformance suite。

## 10. 依赖与集成

- 上游依赖：P00。
- 外部 Harness/SDK 均通过 P01/P06 Adapter；上游实现细节不得成为本包持久数据格式。
- 任何完成/发布/认证均依赖 P05 GateDecision。
