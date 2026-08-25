# 上游能力精华提炼与 Elmos 吸收决策

本文件记录本次研究中真正值得进入 Elmos 的能力，以及它们应进入哪个包、以什么边界吸收。它不是上游项目的替代文档，也不复制其源码。

## 1. OpenAI Harness Engineering

### 提炼出的工程原则

1. **人负责方向和验收，Agent 负责执行。** 提升自主性依赖环境设计、反馈回路和仓库结构，而非让模型“更努力”。
2. **仓库即系统记录。** 产品规范、架构、计划、可靠性、安全、运行手册和证据应可被 Agent 从仓库读取。
3. **AGENTS.md 应是短地图。** 只指向真实知识源，详细信息渐进披露；避免一个巨型说明文件变陈旧。
4. **架构约束机械化。** 分层、依赖方向、公共 API 和设计不变量通过 lint/structural tests 强制，而非仅写文档。
5. **Agent 可自助观察应用。** 每个 worktree 具备可运行实例、浏览器/DOM/截图能力和可查询 logs/metrics/traces。
6. **Agent 互审与反馈闭环。** 生成、Review、验证、修复角色分离；失败要转化为工具、约束、文档或测试能力。
7. **持续垃圾回收。** Agent 产量上升会放大结构熵，需要 Golden Principles、文档园丁和持续清理。

### 进入 Elmos

- P00：仓库记录、AGENTS 地图、架构不变量、文档园丁、Golden Principles。
- P02：仓库可读性与渐进披露，生成的 Schema/图/IR 成为 Agent 可查询资产。
- P04：worktree、本地应用、Agent Review、工作记录和 proof-of-work。
- P05：机械化反馈、验证和修复闭环。
- P07：把失败回灌为经过验证的能力，而不是堆积 Prompt。

### 明确不照搬

- 不把公开实践中的代码规模、PR 数量或效率作为 Elmos 已实现效果。
- 不把“Agent 能运行很久”当作正确性指标；长任务必须受预算、无进展和 Evidence Gate 约束。

## 2. OpenAI Symphony

### 核心运行模型

- 仓库拥有 `WORKFLOW.md`，定义 tracker、workspace、hooks、并发、Agent 参数和状态规则。
- 长运行服务持续获取任务并重对账外部 issue 状态与内部 run 状态。
- 一个任务一个隔离、持久 workspace；调度器保持单一权威活动 run。
- 全局和按状态并发有界；配置可动态重载，失败保留 last-known-good。
- 失败有指数退避、stalled detection、stop/retry/remove 协议。
- 外部 tracker 工具在 host 侧执行；tracker 凭据和别名从 coding-agent 子环境清除。
- 结构化事件暴露 turn、usage、rate limit、error 和 dashboard 状态。
- Workpad 作为计划、验收和验证的工作记录；PR 反馈需要完整 sweep。
- Handoff 依赖 CI、review、复杂度和媒体等 proof-of-work，而非 Agent 文本总结。

### 进入 Elmos

- P00：`ELMOS_WORKFLOW.md` 编译、动态配置、last-known-good。
- P01：workspace 生命周期 Hook、host tool credential boundary、结构化 run events。
- P04：reconciler、task source adapters、bounded concurrency、workpad、PR feedback、proof-of-work。
- P05：把 proof-of-work 进一步升级为 Requirements/Capabilities/Behavior Evidence Gate。

### Elmos 的增强

- Symphony 以 issue/workspace/run 为核心；Elmos 再加入 Requirement/Capability/IR/Gap/Evidence 领域状态。
- Elmos 的“完成”不由 tracker terminal state 决定；tracker 只能反映 P05 的裁决结果。

## 3. DeepSeek Harness

### Cordis 与能力 Seam

- 共享 context、typed services/events 和 reversible effects 让插件注册、监听和热卸载可控。
- Service Definition、Provider、Consumer 三角色形成可替换能力 seam；调用方不绑定平台实现。
- 模型、工具、Session、Agent loop、Persistence、LSP、Sandbox、Approval、Subagent 都可组合。

### Session 与持久化

- Session 是追加式 typed event log；模型可见事实必须能从日志重建。
- 事件有连续序号、严格序列化、turn 边界和 lineage；未知必需事件 fail closed。
- 崩溃恢复保留已提交事件，并把未完成回合闭合为 interrupted。
- JSONL/SQLite 等后端可替换，SessionHeader 记录 cwd、origin、delegation depth 和 seed/format。

### Tool Runtime

- 强类型 Schema、闭合结果词汇、规范化渲染和可取消 call identity。
- pre/wrapper/post/final pipeline；允许 parallel/exclusive 调度和作用域 allow/deny。
- Guard 的权限只能收紧，不能在下游重新放宽。

### Subagent

- one-shot 和 continuable child；capability flags 对不支持能力 fail loud。
- durable child session、FIFO continuation、冷恢复、直接父子授权、深度和工具过滤。
- child-first disposal、report 与 interrupt 形成可治理层级。

### Sandbox 与 Approval

- 沙箱策略按调用解析，区分 read-only/workspace-write/danger-full-access。
- enforcement 明确报告 full/partial；confined 请求无可用 Provider 时不得静默裸执行。
- 审批结果闭合为 allowed-once/rejected/cancelled/unavailable，只有 allowed-once 放行。

### 进入 Elmos

- P01：Harness SPI、event-sourced session、tools、subagents、persistence、sandbox、approval、LSP。
- P02：LSP 作为可选语义证据，不作为最终正确性裁决。
- P04：持久子 Agent 和层级协作。
- P05：事件/工具/审批/沙箱事实进入 Evidence Bundle。

## 4. HKUDS OpenHarness

### 值得吸收的产品化能力

- **Dry-run/readiness：** 在开始昂贵任务前检测模型、Provider、凭据、工具、MCP、权限和环境。
- **Permission Checker：** 路径、命令和工具策略；敏感凭据路径硬拒绝且不可覆盖。
- **Compaction：** 先缩减旧大工具输出，再做结构化全摘要；保留任务状态与附件引用，超长 Prompt 可恢复重试。
- **MCP/Provider profiles：** 多 Provider 配置、认证来源和自动重连。
- **Autopilot：** 统一队列、去重指纹、来源评分、Append-only journal、worktree、小步执行、验证 Gate、repair/stop reason、release human gate。
- **Hooks/Skills/Memory/Channels：** 形成可扩展个人版和企业版产品面。

### 进入 Elmos

- P01：readiness、权限硬拒绝、compaction、MCP reconnect、resume。
- P04：Autopilot queue/journal/worktree/verification/release policy。
- P05：verification policy、repair stop reason。
- P06：Provider profiles 与认证来源，但统一到 Elmos Route/Data Policy。

### Elmos 的增强

- Autopilot 的完成与自动合并必须再经过 P05 Capability/Evidence Gate。
- 个人版/企业版渠道不直接获得底层工具权限；仍经 P01 PDP/approval/sandbox。

## 5. OpenCode

### Agent 与权限

- Build/Plan 主 Agent；General/Explore/Scout 子 Agent；另有 compaction/title/summary 等隐藏角色。
- 每个角色可独立配置 model、prompt、steps、tools 和 permissions。
- 权限按 `action × resource` 通配规则求值，支持 allow/ask/deny、持久授权和带纠正反馈的拒绝。

### Session Core

- 把已接收输入、持久历史、模型运行、Context Epoch、位置范围的 tools/permissions/fs 与执行协调分开。
- 输入只在安全 Provider turn 边界进入模型；中途 steering 不污染进行中的请求。
- durable events 与 live UI events 分离，网络/嵌入客户端共享同一 HTTP 边界。

### LSP、Skills、Plugins、Server

- 多语言 LSP 提供 diagnostics 和语义导航，但也明确存在同步、内存和版本问题。
- 按需发现 `SKILL.md`，并对 Skill 应用 allow/ask/deny。
- Plugin Hooks 覆盖 command/file/LSP/message/permission/session/tool/compaction 等生命周期。
- Headless OpenAPI Server 暴露 Session、child/fork/abort/revert、permission、file/symbol、LSP/MCP 和事件；TUI/Desktop/IDE 是客户端。

### 进入 Elmos

- P01：Context Epoch、action-resource permission、Skill permission、Plugin Hooks、Headless API/SDK。
- P02：LSP + AST/Compiler 双轨；LSP 只做导航和补充证据。
- P04：专业角色、child session、Plan/Build/Explore/Scout 分工。
- P00：公共 API 边界和严格包依赖方向。

## 6. OpenRouter Go/TypeScript/Python SDK

### API 与 Provider 能力

- 类型化多模型 API、streaming、retries、typed errors、models/providers/analytics/guardrails/keys/BYOK 等资源。
- Provider Preferences 可表达 fallback、数据收集、ZDR、only/ignore/order、max price、preferred latency/throughput、quantization 和 required parameters。
- Python 同步/异步资源管理、TypeScript/Go 生成客户端和流式模式可作为 Adapter 参考。

### 进入 Elmos

- P06 Catalog/Invoke/Usage/Health Adapter；所有 SDK 类型封装在 Facade 后。
- Provider Preferences 进入硬约束和候选排序，但 Elmos 增加 task-fit、verified quality、tenant policy 和系统 ETA。
- P01 只接收规范化 usage/stream/event，不依赖某语言 SDK 的内部对象。

## 7. OpenRouter TypeScript Agent

### 长任务控制精华

- 多轮总 token/cost 聚合，而不是只看最终回合。
- step/tool/token/cost/finish reason 等 stop conditions 和全运行 abort。
- 确定性的 doom-loop fingerprint，可 observe/steer/block/stop/escalate。
- sync/background/deferred tool 生命周期，跨进程 resolve/fail/cancel。
- 通用 `task` 控制：status/log/transcript/steer/result/cancel。
- 子 Agent 作为后台多轮任务；工具可单独设 timeout/concurrency/approval。
- Typed Hooks 覆盖模型、工具、权限、prompt、stop 和 session。
- Tool-set activation 与动态 allowed tools；保持 tools 数组稳定可保留 Prompt cache 前缀。

### 进入 Elmos

- P01：Async Task、stop/abort、Hooks、总 usage、动态工具开放。
- P04：doom-loop、task control、subagent tools。
- P05：成本/轮次/无进展是 Repair Gate 的一部分。
- P06：总成本、缓存稳定性和 route escalation。

## 8. OpenRouter Skills

### Skill 设计与评测精华

- 以 decision tree 明确何时查模型、何时解析精确实体、何时比较 benchmark。
- 模型解析输出 confidence；家族证据与具体可路由模型区分。
- Benchmark 保留 source-specific scale、as-of、引用和当前 endpoint availability gate。
- 长评测把运行目录/步骤文件作为已付费工作的事实源，防止跳步骤、伪造回答或错误恢复。

### 进入 Elmos

- P00/P01：按需 Skills、步骤状态与恢复。
- P05：评测无伪造、全尝试入分母、证据与运行状态绑定。
- P06：模型实体解析、benchmark prior、availability gate。
- P07：可复现 Eval 与知识晋升证据。

## 9. 最终吸收优先级

| 优先级 | 立即吸收 | 原因 |
| --- | --- | --- |
| P0 | Event Session、Capability Seam、Permission/Sandbox、WORKFLOW/Reconciler、Repository Graph/IR、Coverage/Evidence Gate | 直接决定可靠性、完整度和安全边界。 |
| P1 | 专业 Agent、continuable child、async task、doom loop、Headless API、模型硬约束路由 | 提高长任务规模化和产品体验。 |
| P2 | 多渠道、实验模型审计、专项模型训练、复杂 Autopilot | 必须建立 verified 基线后再扩展。 |

## 10. 不应吸收成核心依赖的内容

- 上游私有事件/数据库格式。
- 预览 API 的隐式默认行为。
- 模型或 Provider 自报的质量排名。
- Agent 自己的完成判断。
- 无证据的 Memory、Prompt 技巧和单项目 workaround。
