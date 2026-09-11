---
name: portable-request-vs-local-behavior
description: 可序列化请求/工具定义与本地 executable handler/hooks 强制分离。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: 09
  priority: P1
  source_projects: opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-09-portable-request-vs-local-behavior
  source_name: portable-request-vs-local-behavior
  source_path: skills/portable-request-vs-local-behavior/SKILL.md
  source_sha256: sha256:35ab923c28d8f33c0f23b8a9240f7acbc0c36d77de44131d8dbb0eca9ff656a3
  source_contract_sha256: sha256:f3ae6523cc0c2ee2002662f988e1aae8e33e8c9b34f3bdfdae31389255fd2533
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Portable Request vs Local Behavior

## Goal

可序列化请求/工具定义与本地 executable handler/hooks 强制分离。

## Use when

在 Elmos 需要实现或升级 **Portable Request vs Local Behavior** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- Request 可持久化、hash、replay
- handler 运行时绑定并做 schema 兼容检查
- provider-hosted tool 与 local tool 使用不同类型
- 禁止把闭包/credential 塞进 durable request

## Non-negotiable contract

- Provider/Tool/Skill/Config 的 portable data 与 process-local behavior 分离。
- 所有扩展点必须可 capability negotiation、权限过滤和版本化。
- 大型 tool/config catalog 按需 materialize，避免无界上下文膨胀。
- 企业级 managed policy 具有不可被项目覆盖的最高优先级。

## Execution workflow

1. Resolve：按 config precedence 解析 provider/tool/skill/workspace。
2. Negotiate：验证 schema、capability、permission 和 compatibility。
3. Materialize：只加载当前任务需要的定义/连接/上下文。
4. Execute：通过统一 runtime/protocol 调用并标准化事件。
5. Observe：记录 cost/usage/timeout/cache/health，支持安全降级。

## Implementation tasks

- [ ] 定义 `portable-request-vs-local-behavior` 的 public interface、input/output/error schemas。
- [ ] 建立 `portable-request-vs-local-behavior` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：Request 可持久化、hash、replay；以及 handler 运行时绑定并做 schema 兼容检查。
- [ ] 未知/不支持 provider、tool、skill 或 capability 必须本地 fail-fast。
- [ ] 配置/插件变更后可追踪 resolved 来源且不会泄露 credential。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `tool-registry`
- `provider-runtime`
- `workspace-control-plane`

## Upstream inspiration

- opencode: https://github.com/anomalyco/opencode @ ba72a6ff2b62aaf614b8e745193e86a51be6142c (dev, MIT)
- Source areas: `packages/web/src/content/docs/skills.mdx`
- Source areas: `packages/web/src/content/docs/mcp-servers.mdx`
- Source areas: `packages/web/src/content/docs/lsp.mdx`
- Source areas: `packages/web/src/content/docs/formatters.mdx`
- Source areas: `packages/web/src/content/docs/config.mdx`
- Source areas: `packages/llm/DESIGN.md`
- Source areas: `packages/opencode/src/provider/`
- Source areas: `packages/opencode/src/control-plane/`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:f3ae6523cc0c2ee2002662f988e1aae8e33e8c9b34f3bdfdae31389255fd2533`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
