---
name: elmos-scope-control
description: 防止客户特例侵蚀 Golden Route 的可重复性和毛利。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-008
  batch: '11'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-008
  source_name: elmos-scope-control
  source_path: skills/elmos-scope-control/SKILL.md
  source_sha256: sha256:99665cb575f5537cbbba62580266806a95626c746cade18ae55eda6ae2bc4bb4
  source_contract_sha256: sha256:5386e69f11317d0977603534544dc857123aa47b287abaded92d71928a9babeb
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Scope & Change Control

## Objective

防止客户特例侵蚀 Golden Route 的可重复性和毛利。

## Scope and capabilities

- Route Contract diff
- 变更单与重新报价
- 核心路线和客户扩展隔离
- 不支持语义的拒绝/保留/定制处理

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

- scope-decision.json
- change-order.md
- deferred-capabilities.json

## Execution workflow

1. 收集产品、竞争、许可与客户事实
2. 区分 current capability、target capability 和 non-goal
3. 形成产品/路线/许可/范围机器契约
4. 由技术、商业、法务共同评审
5. 版本化发布并设置复审日期

## Implementation tasks

- [ ] 定义 `elmos-scope-control` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `elmos-scope-control` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现产品与路线 JSON/YAML Schema
- [ ] 把市场声明绑定到 Claim–Evidence Ledger
- [ ] 实现 Build/Buy/Partner 与许可证 Policy Gate
- [ ] 实现 scope diff、change order 和资源 WIP 限制
- [ ] 建立 L1–L5 maturity evaluator

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 许可证未知时必须 fail closed
- [ ] Roadmap 能力不得被 current capability 查询返回
- [ ] scope change 必须触发重新评估/报价

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：scope-decision.json, change-order.md, deferred-capabilities.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 配置和策略解析应在 200ms 内完成
- [ ] 运行中的冻结 Route 不因 Catalog 更新而漂移

## Stop, block, or escalate when

- 许可证、责任或商业转售权不明确
- 客户请求超出认证 Route 且拒绝变更单
- 公开声明缺少执行 Evidence

## Definition of done

- [ ] 产品、报价、执行、验收和市场宣传使用同一版本化契约
- [ ] 核心自研/外部集成边界和退出计划明确
- [ ] Spring Golden Route 获得 owner、预算与 L3 目标
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：scope-decision.json, change-order.md, deferred-capabilities.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `elmos-spring-route-boundary`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:5386e69f11317d0977603534544dc857123aa47b287abaded92d71928a9babeb`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
