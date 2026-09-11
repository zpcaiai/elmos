---
name: spring-deterministic-share
description: 量化并提升 Recipe/编译器/结构化 Tool 自动完成的风险加权比例。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-048
  batch: '16'
  priority: P1
  risk: high
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-048
  source_name: spring-deterministic-share
  source_path: skills/spring-deterministic-share/SKILL.md
  source_sha256: sha256:21e3a7204e20b61ba963f7d0b7a3e533850ffe0d3fb5abccc583ad31fa4c8bc6
  source_contract_sha256: sha256:fd19364dcd0623f9c09374f2e3d46dbb877b18cda52afd111fb846591df6ae1b
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Deterministic Coverage Optimizer

## Objective

量化并提升 Recipe/编译器/结构化 Tool 自动完成的风险加权比例。

## Scope and capabilities

- Semantic operation share
- Agent/Human share
- 高风险加权
- Patch→Recipe candidate ROI
- 毛利影响

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

- deterministic-coverage.json
- candidate-backlog.json

## Execution workflow

1. 从 Route/Graph 生成 typed Migration DAG
2. 按许可证/能力选择 Transformation Provider
3. 先迁移 Build/Dependencies
4. 执行 API/Config Recipe 多轮 Fixpoint
5. 统计确定性覆盖并输出未解决语义

## Implementation tasks

- [ ] 定义 `spring-deterministic-share` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `spring-deterministic-share` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 DAG compiler 与 cycle/side-effect validation
- [ ] 实现 OpenRewrite Adapter conformance
- [ ] 实现 Elmos Native Recipe SDK/Pack
- [ ] 实现 License-aware Router
- [ ] 实现 Maven/Config/API migrator 与 Recipe scheduler

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] Recipe before/after/negative/idempotency fixtures
- [ ] 最终 no-op cycle
- [ ] 无 provenance change 阻断
- [ ] 受限制 Recipe 无授权不能执行

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：deterministic-coverage.json, candidate-backlog.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 共享 Parser/Type/Template cache
- [ ] 只扫描受影响文件/模块
- [ ] Recipe cycle 资源上限

## Stop, block, or escalate when

- DAG cycle、P0 无 verifier 或副作用无 reconcile
- Recipe 振荡/持续变化
- 许可不允许
- unowned/parse-loss diff

## Definition of done

- [ ] 确定性变换可重复、最小、可回滚和可归因
- [ ] 全量 Recipe 最终收敛
- [ ] Agent 只接收剩余业务歧义
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：deterministic-coverage.json, candidate-backlog.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `spring-recipe-fixpoint`
- `repo-semantic-accounting`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:fd19364dcd0623f9c09374f2e3d46dbb877b18cda52afd111fb846591df6ae1b`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
