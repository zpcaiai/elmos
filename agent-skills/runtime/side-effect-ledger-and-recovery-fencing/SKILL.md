---
name: side-effect-ledger-and-recovery-fencing
description: 把 Tool 副作用、幂等键、reconciliation 和 cluster fencing 统一起来。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '10'
  priority: P0
  source_projects: opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-10-side-effect-ledger-and-recovery-fencing
  source_name: side-effect-ledger-and-recovery-fencing
  source_path: skills/side-effect-ledger-and-recovery-fencing/SKILL.md
  source_sha256: sha256:56308b6377067afcd827a886dd41f1cd3188de91f3889f96237be16f0ceaff83
  source_contract_sha256: sha256:cccd768763ee37f028dbcc8add5e8b36593787f709a4bfd432a85de4ea22628c
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Side-effect Ledger & Recovery Fencing

## Goal

把 Tool 副作用、幂等键、reconciliation 和 cluster fencing 统一起来。

## Use when

在 Elmos 需要实现或升级 **Side-effect Ledger & Recovery Fencing** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 数据库/部署/Git push/发布等操作先登记 ledger
- Worker ownership 有 lease + fencing token
- 恢复先查询外部真实状态再决定 retry/complete
- rollback/compensation 也作为有证据的 durable step

## Non-negotiable contract

- 优先确定性、最小变更、可回滚和可证明完成。
- 所有模型决策都必须有可观测成本、证据和降级路径。
- 任何学习到的新规则先进入候选/认证阶段，不能直接获得生产写权限。
- 跨层缓存必须以内容/语义指纹和版本作为失效边界。

## Execution workflow

1. Classify：把需求拆成 deterministic / agent / tool / human 节点。
2. Plan：构建 typed DAG，声明证据、风险、成本和 rollback。
3. Execute：优先 Recipe，必要时 Agent 只处理语义歧义。
4. Verify：循环修复直到 fixpoint 或达到显式失败边界。
5. Learn：将成功模式写入候选知识/Recipe，但需认证后才能生产复用。

## Implementation tasks

- [ ] 定义 `side-effect-ledger-and-recovery-fencing` 的 public interface、input/output/error schemas。
- [ ] 建立 `side-effect-ledger-and-recovery-fencing` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：数据库/部署/Git push/发布等操作先登记 ledger；以及 Worker ownership 有 lease + fencing token。
- [ ] E2E 场景必须证明从需求到 patch 到验证到证据可完整追踪。
- [ ] 无法证明完成时任务状态必须为 partial/blocked/unknown，而非 completed。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `elmos-orchestrator`
- `verification-loop`
- `self-improving-recipe-system`

## Upstream inspiration

- opencode: https://github.com/anomalyco/opencode @ ba72a6ff2b62aaf614b8e745193e86a51be6142c (dev, MIT)
- Source areas: `OpenRewrite + OpenCode fusion; Elmos-specific derived architecture (no direct upstream equivalent)`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:cccd768763ee37f028dbcc8add5e8b36593787f709a4bfd432a85de4ea22628c`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
