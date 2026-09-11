---
name: agent-step-budget
description: 限制 Agent agentic iteration/turn，避免失控循环和成本爆炸。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '06'
  priority: P0
  source_projects: opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-06-agent-step-budget
  source_name: agent-step-budget
  source_path: skills/agent-step-budget/SKILL.md
  source_sha256: sha256:1792713fc5d78e6800f1ae0824ea3fe1d387c688df9063ddea49965666fbc7e2
  source_contract_sha256: sha256:e7c2f088cd0d1e916151d52e5360986fe60fb328cc72a8a05dfa494d3dca4bb5
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Agent Step Budget

## Goal

限制 Agent agentic iteration/turn，避免失控循环和成本爆炸。

## Use when

在 Elmos 需要实现或升级 **Agent Step Budget** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 每 Agent/任务配置 max steps/turns
- 接近上限时输出剩余工作和阻塞点
- 达到上限是显式 stop reason 而非伪装成功
- 预算可由复杂度/费用策略动态调整

## Non-negotiable contract

- 每个外部副作用必须有 durable identity、状态和审计证据。
- 内存状态不能成为 crash/reconnect 后唯一事实来源。
- 权限在执行前判定，deny 不得被 Agent/模型切换绕过。
- 重试、恢复、取消和并发必须有明确定义的幂等语义。

## Execution workflow

1. Admit：先持久化任务/消息/tool intent 与权限上下文。
2. Plan：在当前安全边界选 Agent/model/tool，并计算预算。
3. Execute：运行单个可审计 step，副作用先登记后执行。
4. Settle：持久化结果/失败/中断，再决定 continuation。
5. Recover：重连/重试从 durable state 恢复，不依赖进程内对象。

## Implementation tasks

- [ ] 定义 `agent-step-budget` 的 public interface、input/output/error schemas。
- [ ] 建立 `agent-step-budget` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：每 Agent/任务配置 max steps/turns；以及 接近上限时输出剩余工作和阻塞点。
- [ ] 模拟进程中断/重复请求/重连后不得重复未确认副作用。
- [ ] 权限为 deny 的路径必须在 handler 被调用前被阻断。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `agent-runtime`
- `model-router`
- `task-planner`

## Upstream inspiration

- opencode: https://github.com/anomalyco/opencode @ ba72a6ff2b62aaf614b8e745193e86a51be6142c (dev, MIT)
- Source areas: `packages/web/src/content/docs/agents.mdx`
- Source areas: `packages/core/src/agent.ts`
- Source areas: `packages/opencode/src/agent/`
- Source areas: `packages/web/src/content/docs/commands.mdx`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:e7c2f088cd0d1e916151d52e5360986fe60fb328cc72a8a05dfa494d3dca4bb5`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
