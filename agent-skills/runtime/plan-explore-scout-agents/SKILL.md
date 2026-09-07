---
name: plan-explore-scout-agents
description: 把只读规划、本仓探索、外部依赖研究拆成不同权限角色。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '06'
  priority: P0
  source_projects: opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-06-plan-explore-scout-agents
  source_name: plan-explore-scout-agents
  source_path: skills/plan-explore-scout-agents/SKILL.md
  source_sha256: sha256:0cda17069adec2d3bae233a9b4ad4d6a13c6e62bf810ba34626c0b23bcfc7f92
  source_contract_sha256: sha256:9bf0b11e97c9329c4e6197f003c5303e466868f7ae10f0cd6c8cca1d88a9bf14
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Plan / Explore / Scout Agents

## Goal

把只读规划、本仓探索、外部依赖研究拆成不同权限角色。

## Use when

在 Elmos 需要实现或升级 **Plan / Explore / Scout Agents** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- Plan 默认禁止写操作
- Explore 只访问本仓搜索/读取/LSP
- Scout 只访问外部文档/依赖缓存
- Build 只有在计划和权限满足后才获得写能力

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

- [ ] 定义 `plan-explore-scout-agents` 的 public interface、input/output/error schemas。
- [ ] 建立 `plan-explore-scout-agents` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：Plan 默认禁止写操作；以及 Explore 只访问本仓搜索/读取/LSP。
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

- Machine contract: `references/contract.json` (`sha256:9bf0b11e97c9329c4e6197f003c5303e466868f7ae10f0cd6c8cca1d88a9bf14`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
