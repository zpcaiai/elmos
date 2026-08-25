---
name: elmos-harness-runtime-platform
description: 统一 Agent、Session、Tool、Skill、Sandbox、Permission、Approval、Subagent、Async Task、LSP、API 和持久化能力。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P01
  version: 1.0.0
  phase: "Phase 1（可信执行底座）"
  dependencies: "00"
  maturity: commercial-product-blueprint
---

# Elmos 可插拔 Harness 运行时平台

## 使命

复用成熟 Harness 的执行能力，同时让 Elmos 的核心转换算法、数据与完成裁决保持独立可控。

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

**依赖：** P00

- 不决定项目生成/转换语义是否正确；P02/P03/P05 负责。
- 外部 Harness 只通过 Adapter 接入，禁止其内部事件或存储格式泄漏到域层。
- 所有“部分支持”能力必须显式暴露 enforcement/capability，不得静默忽略。

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

- 模型可见事实要么来自持久事件，要么被标记为 transient 且不得影响可回放决策。
- 工具参数在执行前通过 Schema、权限、审批、沙箱和业务 Guard 全部检查。
- confined 请求无法获得 full/accepted enforcement 时必须失败，不得裸执行。
- 审批只有 allowed-once 是授权；unavailable、cancelled、rejected 全部拒绝。
- Subagent 不得超过深度、工具、persona、预算和直接父子授权范围。
- Adapter 升级必须通过跨实现 conformance suite。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/harness-adapter-sdk/SKILL.md` | 为 DeepSeek Harness、OpenCode、OpenHarness、Codex、Claude 和本地运行时提供统一适配合同。 |
| `skills/event-sourced-session-runtime/SKILL.md` | 提供可回放、可恢复、可分叉的 Agent 长任务事实链。 |
| `skills/context-epoch-manager/SKILL.md` | 分离持久历史、当前模型上下文、已接收输入和下一回合参数，保证安全边界。 |
| `skills/tool-runtime/SKILL.md` | 统一工具发现、Schema、Hooks、权限、执行、结果、超时和审计。 |
| `skills/async-task-runtime/SKILL.md` | 支持长时间编译、测试、部署、人工审批和外部系统任务的异步完成。 |
| `skills/continuable-subagent-manager/SKILL.md` | 提供持久子会话、冷恢复、父子授权和受控协作。 |
| `skills/permission-policy-engine/SKILL.md` | 基于 subject/action/resource/context 做 allow/ask/deny 与硬性拒绝。 |
| `skills/approval-gate/SKILL.md` | 为敏感工具和副作用提供 fail-closed 的一次性授权。 |
| `skills/sandbox-runtime/SKILL.md` | 按调用隔离文件副作用，并报告 full/partial enforcement。 |
| `skills/lsp-capability-seam/SKILL.md` | 为仓库理解提供可替换的定义、引用、实现和 hover 查询。 |
| `skills/compaction-and-resume/SKILL.md` | 降低上下文成本且保留任务、决策、文件和证据引用。 |
| `skills/headless-runtime-api/SKILL.md` | 让 Web IDE、CLI、Desktop、CI 和第三方系统共用统一执行内核。 |
| `skills/readiness-dry-run/SKILL.md` | 在昂贵长任务开始前识别模型、凭据、工具、沙箱、磁盘、网络和版本问题。 |

## 必须产出

- P01 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- 至少 native Adapter 与一个外部 Harness Adapter 通过 100% conformance tests。
- Session replay 对已认证事件产生相同的模型输入和策略快照。
- 硬拒绝策略、凭据隔离和沙箱逃逸红队无 Critical/High 未解决项。
- 所有工具失败均产生规范化错误和可审计事件，不出现悬挂 running 状态。
- Headless API/SDK 与 Web/CLI 客户端共享同一状态语义。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| Adapter 崩溃 | 隔离 run，保留 durable session，按政策重启/切换 Adapter；禁止重复副作用。 |
| Session 日志损坏 | 拒绝加载、保留原始 artifact、进入修复/人工审计；不得猜测缺失事件。 |
| 工具无响应 | per-request timeout + run cancellation + idempotency-aware retry。 |
| 上下文压缩丢任务状态 | 结构化 carryover 校验失败则回退到旧 Epoch，不发布 compact。 |
| 沙箱仅 partial | 需要 full 的任务拒绝；允许 partial 的低风险任务必须显式记录。 |
| 权限服务不可用 | fail closed，并输出 blocker；不得采用默认 allow。 |

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
