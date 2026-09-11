---
name: gr-cache
description: 建立 Blob→Parse→IR→Graph→Query→Context→Provider 分层缓存和依赖感知失效。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-092
  batch: '22'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-092
  source_name: gr-cache
  source_path: skills/gr-cache/SKILL.md
  source_sha256: sha256:8e953bce668656050b7e058023d33575c40a7eb2a5f9cda4ce0d3934baf051a5
  source_contract_sha256: sha256:75e41ef53604a1e7591956cbf0fe062a92005e1adf7998ca516cc1beac53415a
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Hierarchical Incremental Cache

## Objective

建立 Blob→Parse→IR→Graph→Query→Context→Provider 分层缓存和依赖感知失效。

## Scope and capabilities

- Content/version fingerprint
- Tenant isolation
- Stale correctness
- Poison detection
- Hit/cost analytics

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

- cache-manifest.json
- invalidation-graph.json
- cache-metrics.json

## Execution workflow

1. 按仓库规模和 Portfolio Graph 分片
2. 执行公平容量调度和分层缓存
3. 跨仓按 wave 迁移/验证/回滚
4. 挖掘经授权 Semantic Patch
5. 认证 Recipe 并摄取 Migration KG
6. 在 Spring L3 后评估下一路线

## Implementation tasks

- [ ] 定义 `gr-cache` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `gr-cache` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 large-repo/multi-repo scheduler
- [ ] 实现 tenant/project/model/tool capacity controls
- [ ] 实现 dependency-aware hierarchical cache
- [ ] 实现 privacy-aware patch mining
- [ ] 实现 Recipe candidate certification/Migration KG/Portfolio stage gate

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] S3/S4/S5 scale 与 fault injection
- [ ] 缓存 stale/poison/tenant leakage
- [ ] 候选 Recipe positive/negative/holdout/idempotency
- [ ] 多仓共享 DB/API compatibility

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：cache-manifest.json, invalidation-graph.json, cache-metrics.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 支持 3M+ MRLOC 参考容量并有 backpressure
- [ ] 缓存 hit/cost/stale 全可观测
- [ ] 数百仓 Campaign 公平调度

## Stop, block, or escalate when

- 资源预算持续超限
- 跨仓合同无兼容/rollback
- 客户无学习授权
- 候选 Recipe 有 P0 regression/许可问题

## Definition of done

- [ ] >500k/>1M flagship clean-room 案例满足 L3
- [ ] Certified Recipe 默认最小权限且可撤销
- [ ] 下一路线使用独立 Contract/Benchmark/L3 Gate
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：cache-manifest.json, invalidation-graph.json, cache-metrics.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `gr-capacity`
- `spring-repo-graph`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:75e41ef53604a1e7591956cbf0fe062a92005e1adf7998ca516cc1beac53415a`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
