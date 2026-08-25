---
name: spring-route-orchestrator
description: 编排 Eligibility→Baseline→Intelligence→Plan→Transform→Repair→Verify→Proof→Delivery。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-009
  batch: '12'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-009
  source_name: spring-route-orchestrator
  source_path: skills/spring-route-orchestrator/SKILL.md
  source_sha256: sha256:40cc1275975824447189735242f9f8b27da459cd0735d233af19e6e5deb64717
  source_contract_sha256: sha256:d092c4247bc985246a69d44350786137b8f8b8225e5166bb43d3d64f83837bf0
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
  dependency_graph_role: entrypoint-with-downstream-successors
  runtime_dependency_closure_status: NOT_IMPLEMENTED
  planning_preview_state: DRAFT_ONLY
---

# Spring Golden Route Orchestrator

## Objective

编排 Eligibility→Baseline→Intelligence→Plan→Transform→Repair→Verify→Proof→Delivery。

## Scope and capabilities

- 固定阶段与硬 Gate
- Durable pause/resume/cancel
- Typed node inputs/outputs
- 阶段补偿与回滚
- SSE/API 可观察

## Explicit boundaries

- 本 Skill 只对其声明的输入、Route Contract、Target Profile 和 Acceptance Contract 负责。
- 不支持、未知或无法验证的语义必须输出 `unsupported`/`unknown`，不得静默近似。
- 静态 Skills/Schema/Fixture 验证不等于目标 Elmos 仓库已实现该能力。
- Roadmap 或候选能力不得在 UI、报价或公开声明中呈现为 current certified capability。

## Required inputs

- Frozen repository/environment snapshot 或对应版本化业务输入。
- Tenant、project、run/task identity 和 permission context。
- 适用的 Route/Policy/Profile/Schema 版本。
- 上游依赖、客户责任或人工审批（适用时）。

## Required outputs

- migration-run.json
- phase-events
- delivery-result.json

## Execution workflow

1. 冻结 Source/Target Profile 与 Route Contract
2. 发现源仓技术、模块和关键能力
3. 拆分 Maven、数据、安全、异步与 unsupported 子路线
4. 建立阶段 Gate、审批与回滚
5. 执行交付/接管完整性审查

## Implementation tasks

- [ ] 定义 `spring-route-orchestrator` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `spring-route-orchestrator` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 Golden Route durable workflow
- [ ] 实现 Source/Target profile registry
- [ ] 实现 Maven multi-module 与 framework capability matrix
- [ ] 建立 Unsupported Semantics treatment workflow
- [ ] 实现 Delivery Bundle/PR/Rollback contract

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] Route Contract 漂移必须阻断执行
- [ ] 全 reactor clean verify 失败不得交付
- [ ] 关键 unsupported 无 treatment 不得认证

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：migration-run.json, phase-events, delivery-result.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 资格与 Source Profile 目标 5–15 分钟机器时间
- [ ] 支持 24h+ 长任务和阶段 checkpoint

## Stop, block, or escalate when

- Baseline 无法重建
- 关键私有依赖不可访问
- P0 capability 无目标映射/验证器
- rollback 未验证

## Definition of done

- [ ] 从冻结 snapshot 到 delivery bundle 的 clean-room E2E 可重复
- [ ] 每项源能力映射 preserved/transformed/retained/unsupported/unknown
- [ ] 所有 mandatory Gate 证据完整
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：migration-run.json, phase-events, delivery-result.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `elmos-spring-route-boundary`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:d092c4247bc985246a69d44350786137b8f8b8225e5166bb43d3d64f83837bf0`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
- The source `dependencies` array records prerequisite order, not a complete executable closure; downstream phase Skills remain visible only in `docs/spring-golden-route-commercial-skills/installed-manifest.json`.
- Until exact runtime dependencies and a typed preview contract are implemented, assessment-only responses must be labeled `DRAFT_ONLY`; required execution outputs remain absent and every execution phase remains `NOT_RUN`.
