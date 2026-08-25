---
name: gr-data-model
description: 实现多租户、事件化、可恢复、可审计的 PostgreSQL 域模型。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-065
  batch: '19'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-065
  source_name: gr-data-model
  source_path: skills/gr-data-model/SKILL.md
  source_sha256: sha256:0535687e43cf0e7362751da2f0238906cd585fc70b3839ffe0f8469e0cda13c1
  source_contract_sha256: sha256:0e918c4ae90a82e609aefcc84c49817d657bf2a6edbda455ee811fe78dbefd6d
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Golden Route Data Model

## Objective

实现多租户、事件化、可恢复、可审计的 PostgreSQL 域模型。

## Scope and capabilities

- Tenant/project/snapshot/profile/run
- DAG/Agent/Model/Tool/Recipe/Patch
- Verification/Evidence/Claim/Proof
- Quote/Pilot/Benchmark
- RLS/partition/index

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

- postgres-migrations
- ERD.md
- data-retention-plan.json

## Execution workflow

1. 定义聚合、事件和 RLS 数据模型
2. 把大 Artifact 存 Evidence Store 并登记 hash
3. 把 Claim 链接到 Evidence
4. 记录 trace/metrics/cost/progress
5. 执行保留、脱敏、导出与删除

## Implementation tasks

- [ ] 定义 `gr-data-model` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `gr-data-model` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 PostgreSQL migrations/RLS/partition/index
- [ ] 实现 event catalog/outbox/replay
- [ ] 实现 CAS/Object Evidence Store
- [ ] 实现 Claim–Evidence Ledger/Proof queries
- [ ] 实现 OpenTelemetry、cost ledger、ETA/customer status、retention

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 跨租户访问零泄漏
- [ ] 历史事件 replay 一致
- [ ] Evidence 篡改被检测
- [ ] 失败/重试成本不丢失

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：postgres-migrations, ERD.md, data-retention-plan.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 高量 run_events 分区与分页
- [ ] 高基数 metric 控制
- [ ] 大 Artifact 流式存储

## Stop, block, or escalate when

- RLS/backup/restore 失败
- Evidence hash mismatch
- 价格/usage 缺失却试图输出 actual
- 保留/法律策略冲突

## Definition of done

- [ ] 每个 run 可从事件和 Evidence 审计
- [ ] 每个成本归因到执行单元
- [ ] 客户状态与 durable state/claims 一致
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：postgres-migrations, ERD.md, data-retention-plan.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- None

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:0e918c4ae90a82e609aefcc84c49817d657bf2a6edbda455ee811fe78dbefd6d`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
