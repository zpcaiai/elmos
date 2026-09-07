---
name: migration-knowledge-graph
description: 把源/目标语言、框架、版本、API、Recipe 和失败模式沉淀成迁移知识图。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '10'
  priority: P0
  source_projects: openrewrite,opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-10-migration-knowledge-graph
  source_name: migration-knowledge-graph
  source_path: skills/migration-knowledge-graph/SKILL.md
  source_sha256: sha256:c1b054fd8b92915133e946a64e2c06f9db7b6726c49302f7862ba5441e8aa3aa
  source_contract_sha256: sha256:b4b469e707d9cfbd30af165e123f8c15f7673bcb66e71a11f2f11445f56df89f
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Migration Knowledge Graph

## Goal

把源/目标语言、框架、版本、API、Recipe 和失败模式沉淀成迁移知识图。

## Use when

在 Elmos 需要实现或升级 **Migration Knowledge Graph** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 实体包括 symbol/framework/version/rule/test/failure/evidence
- Recipe applicability 和历史成功率可查询
- 新项目 scan 先匹配已知迁移路径
- 知识节点有来源版本和置信度

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

- [ ] 定义 `migration-knowledge-graph` 的 public interface、input/output/error schemas。
- [ ] 建立 `migration-knowledge-graph` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：实体包括 symbol/framework/version/rule/test/failure/evidence；以及 Recipe applicability 和历史成功率可查询。
- [ ] E2E 场景必须证明从需求到 patch 到验证到证据可完整追踪。
- [ ] 无法证明完成时任务状态必须为 partial/blocked/unknown，而非 completed。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `elmos-orchestrator`
- `verification-loop`
- `self-improving-recipe-system`

## Upstream inspiration

- openrewrite: https://github.com/openrewrite/rewrite @ 4bc18536d99bb86f1ba0f353643de72ef56dd165 (main, Apache-2.0)
- opencode: https://github.com/anomalyco/opencode @ ba72a6ff2b62aaf614b8e745193e86a51be6142c (dev, MIT)
- Source areas: `OpenRewrite + OpenCode fusion; Elmos-specific derived architecture (no direct upstream equivalent)`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:b4b469e707d9cfbd30af165e123f8c15f7673bcb66e71a11f2f11445f56df89f`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
