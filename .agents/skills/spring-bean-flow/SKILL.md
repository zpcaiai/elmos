---
name: spring-bean-flow
description: 抽取 DI、Controller/Service/Repository、AOP、profiles 和事务传播/隔离。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-036
  batch: '15'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-036
  source_name: spring-bean-flow
  source_path: skills/spring-bean-flow/SKILL.md
  source_sha256: sha256:f267187de635da99008bf884d3cacef306c98f2a83c9271684dbd805934615f3
  source_contract_sha256: sha256:433c22f17c267d3be5bf208e6f9832b76a57bbae4b929d35d1ef302b3f09c9fd
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Bean Endpoint Transaction Graph

## Objective

抽取 DI、Controller/Service/Repository、AOP、profiles 和事务传播/隔离。

## Scope and capabilities

- Bean candidates/qualifiers
- Endpoint call flow
- AOP/proxy edges
- Transaction semantics
- Test mapping

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

- bean-graph.json
- endpoint-flow.json
- transaction-map.json

## Execution workflow

1. 冻结源码与环境快照
2. 运行源系统并捕获行为指纹
3. 构建 Spring Repository Knowledge Graph
4. 补齐 Bean/Data/Security/Async 专图
5. 建立 Test Mapping、negative 与 holdout corpus

## Implementation tasks

- [ ] 定义 `spring-bean-flow` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `spring-bean-flow` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 CAS snapshot/restore
- [ ] 实现静态+动态 Repository Graph 与 provenance
- [ ] 实现 Bean/Endpoint/Transaction、Data/Query、Security、Async 图
- [ ] 实现 PII/Secret redaction
- [ ] 实现独立 holdout 和 test-integrity gate

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] Graph critical fact 可追踪到源码或运行 Evidence
- [ ] P0 endpoint/data/security/async 均有场景
- [ ] 修复 Agent 不得读取 holdout oracle

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：bean-graph.json, endpoint-flow.json, transaction-map.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 图按模块增量更新并原子提交版本
- [ ] 大型 CSV/索引使用查询而非整表送模型

## Stop, block, or escalate when

- P0 行为无可执行 Baseline
- 关键 Graph completeness 低于阈值
- 测试 oracle 同源且无独立验证

## Definition of done

- [ ] 所有 P0 capabilities 有源行为、Graph 和 verifier
- [ ] Repository Graph 可版本化回放
- [ ] 行为语料包含正例、负例、边界和 holdout
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：bean-graph.json, endpoint-flow.json, transaction-map.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `spring-repo-graph`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:433c22f17c267d3be5bf208e6f9832b76a57bbae4b929d35d1ef302b3f09c9fd`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
