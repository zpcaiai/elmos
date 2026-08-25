---
name: post-edit-format-and-patch
description: 文件修改后按项目实际 formatter 规范化，并统一生成可审计 patch。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: 09
  priority: P1
  source_projects: opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-09-post-edit-format-and-patch
  source_name: post-edit-format-and-patch
  source_path: skills/post-edit-format-and-patch/SKILL.md
  source_sha256: sha256:af8b1a4086d124b978674eb01169ce6735eb694be1351f16dd75daf4d6131ac2
  source_contract_sha256: sha256:416044f74f7f2c5c6f261eb6b2f6c8d3369e55a6d87acb7eac236713a8621a6c
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Post-edit Format & Patch

## Goal

文件修改后按项目实际 formatter 规范化，并统一生成可审计 patch。

## Use when

在 Elmos 需要实现或升级 **Post-edit Format & Patch** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 按 extension/config 自动选择 formatter
- custom formatter 支持 env/command/FILE placeholder
- format 只作用于 changed files 且有 timeout
- apply_patch add/update/move/delete 统一路径校验与 permission

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

- [ ] 定义 `post-edit-format-and-patch` 的 public interface、input/output/error schemas。
- [ ] 建立 `post-edit-format-and-patch` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：按 extension/config 自动选择 formatter；以及 custom formatter 支持 env/command/FILE placeholder。
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

- Machine contract: `references/contract.json` (`sha256:416044f74f7f2c5c6f261eb6b2f6c8d3369e55a6d87acb7eac236713a8621a6c`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
