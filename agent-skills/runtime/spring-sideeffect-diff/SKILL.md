---
name: spring-sideeffect-diff
description: 比较事件、DLQ/retry、缓存 key/TTL、定时任务和外部调用次数/顺序/契约。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-061
  batch: '18'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-061
  source_name: spring-sideeffect-diff
  source_path: skills/spring-sideeffect-diff/SKILL.md
  source_sha256: sha256:10e1e8a41b9be3319765ab28ab84d1d2d42756041ccb8677af5f43e7f080df3b
  source_contract_sha256: sha256:bdefc72092f7485bdc9add49c4b45b6c3287f6342bcb97c99bd0bde99a368ea7
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Messaging Cache Side-effect Differential

## Objective

比较事件、DLQ/retry、缓存 key/TTL、定时任务和外部调用次数/顺序/契约。

## Scope and capabilities

- Async stabilization window
- Schema/header
- Idempotency
- Virtual time
- External reconciliation

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

- side-effect-diff.json
- event-traces
- cache-snapshots

## Execution workflow

1. 恢复隔离 Source/Target runtime
2. 执行同一行为场景
3. 比较 API/DB/Security/Side effects
4. 运行性能、安全与质量 Gate
5. 循环 Repair 直到 Fixpoint
6. 生成 Completion Proof 与 Rollback Evidence

## Implementation tasks

- [ ] 定义 `spring-sideeffect-diff` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `spring-sideeffect-diff` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 environment composer/testcontainers/virtual services
- [ ] 实现 API/DB/Security/MQ comparator DSL
- [ ] 实现 quality adapters 和 test-integrity guard
- [ ] 实现 Verification Fixpoint/loop fingerprint
- [ ] 实现 Claim–Evidence Proof generator/offline verifier

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 额外授权放行必须 fail
- [ ] 事务 commit/rollback/写集合差异必须 fail
- [ ] 事件重复/丢失必须 fail
- [ ] 无 Evidence 的 PASS 变 unknown

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：side-effect-diff.json, event-traces, cache-snapshots。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 独立场景有界并行
- [ ] 按影响图先跑 targeted，周期性全量
- [ ] 记录硬件/环境以解释性能

## Stop, block, or escalate when

- 任一环境不健康/未冻结
- P0 behavior unresolved/unknown
- 新 critical/high 安全问题
- rollback/clean-room 未通过

## Definition of done

- [ ] mandatory violations=0 且 unknown=0
- [ ] 最后全量验证无回归
- [ ] 独立工具可离线验证 Completion Proof
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：side-effect-diff.json, event-traces, cache-snapshots。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `spring-dual-runtime`
- `spring-async-graph`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:bdefc72092f7485bdc9add49c4b45b6c3287f6342bcb97c99bd0bde99a368ea7`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
