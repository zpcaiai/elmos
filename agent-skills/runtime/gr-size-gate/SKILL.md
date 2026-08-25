---
name: gr-size-gate
description: 要求 ≥20 unseen；S1≥5、S2≥7、Large+≥5、＞500k≥3、＞1M≥1。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-076
  batch: '20'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-076
  source_name: gr-size-gate
  source_path: skills/gr-size-gate/SKILL.md
  source_sha256: sha256:f1d0392588df545bcf562c8ef03441657d39a88f8e8936073dff3f943c60be53
  source_contract_sha256: sha256:15e8b42050f96720d43a65b19b2f168977c52cb80094f1455ca6816acfb81c98
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# L3 Size Distribution Gate

## Objective

要求 ≥20 unseen；S1≥5、S2≥7、Large+≥5、>500k≥3、>1M≥1。

## Scope and capabilities

- Strong Large 复杂度附加条件
- Audited MRLOC
- Independent family
- Success+failure distribution
- Hard gate

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

- size-gate-result.json
- distribution-table.json

## Execution workflow

1. 建立分层 Benchmark Corpus
2. 验证 unseen/family 独立性
3. 运行 No-Cheating 与 Failure Denominator
4. 运行规模分布和 Clean-room
5. 综合技术/商业证据执行 L3 Gate
6. 认证公开声明

## Implementation tasks

- [ ] 定义 `gr-size-gate` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `gr-size-gate` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 corpus registry/holdout partition
- [ ] 实现 family fingerprint/access audit
- [ ] 实现 no-cheating validator
- [ ] 实现 L3 size/denominator/clean-room evaluators
- [ ] 实现 public claim registry/expiry/revocation

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 有效 L3 fixture 通过
- [ ] 少于 20/3 客户/规模门 fixture 失败
- [ ] fork/branch/generated 灌水 fixture 失败
- [ ] 失败案例 retroactive exclusion 失败

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：size-gate-result.json, distribution-table.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 数百案例可在分钟级重算
- [ ] 公开验证不读取客户源码正文

## Stop, block, or escalate when

- 任何 hard gate unknown/fail
- 付费客户记录不可验证
- MRLOC 未审计
- clean-room 依赖隐藏人工修复

## Definition of done

- [ ] L3 结果可由 manifest+validator 独立重算
- [ ] 所有失败留在分母
- [ ] 公开声明有 Evidence、日期、授权和撤销机制
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：size-gate-result.json, distribution-table.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `gr-no-cheating`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:15e8b42050f96720d43a65b19b2f168977c52cb80094f1455ca6816acfb81c98`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
