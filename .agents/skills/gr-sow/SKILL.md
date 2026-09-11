---
name: gr-sow
description: 把支持范围、客户责任、Baseline 历史失败、P0/P1、UAT、Rollback、变更单写成可执行合同数据。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-085
  batch: '21'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-085
  source_name: gr-sow
  source_path: skills/gr-sow/SKILL.md
  source_sha256: sha256:72ab4edea03d0f5d2b3418ad3f9bf69ff737cefa61ce33f2925cf0bd1d45ad32
  source_contract_sha256: sha256:3973a3b186ad524fdc732724b0e27d41c599db3e2b231d4351dd457d6d9dea07
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# SOW & Acceptance Contract

## Objective

把支持范围、客户责任、Baseline 历史失败、P0/P1、UAT、Rollback、变更单写成可执行合同数据。

## Scope and capabilities

- Mandatory claims
- Acceptance method
- Responsibility matrix
- Change order
- Warranty/limitations

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

- SOW.md
- acceptance-contract.json
- change-order-template.md

## Execution workflow

1. 销售 Assessment
2. 根据资格选择代表性 Pilot
3. 冻结 SOW/价格/数据政策
4. 执行并取得签署 Acceptance
5. 评估毛利/复用/clean-room
6. 升级 Factory Campaign

## Implementation tasks

- [ ] 定义 `gr-sow` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `gr-sow` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现三个 SKU config/portal/billing milestone
- [ ] 实现版本化 Pricing Engine/Rate Card
- [ ] 实现 SOW/Acceptance/Change Order Schema
- [ ] 实现 Customer Data/IP/Model Policy
- [ ] 实现 Pilot selection/success scorecard

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 低置信度仓库不能无条件固定价
- [ ] 无付费/无签署/无 Proof 的 Pilot 不计成功
- [ ] scope diff 必须触发变更单

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：SOW.md, acceptance-contract.json, change-order-template.md。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 报价秒级生成但需人工商业审批
- [ ] 审批等待不占 Runner 资源

## Stop, block, or escalate when

- 无预算/owner/测试环境/数据授权
- SOW 与技术 Route 不一致
- 毛利低于底线或许可成本未知

## Definition of done

- [ ] 至少 3 个独立付费客户 Pilot 达到硬门
- [ ] 客户签署 Completion Proof/UAT
- [ ] Pilot 形成可重复 Factory Proposal
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：SOW.md, acceptance-contract.json, change-order-template.md。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `gr-pricing`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:3973a3b186ad524fdc732724b0e27d41c599db3e2b231d4351dd457d6d9dea07`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
