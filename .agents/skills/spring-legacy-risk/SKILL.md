---
name: spring-legacy-risk
description: 识别 XML-heavy、JSP、EJB、SOAP/RMI、JNI、反射、字节码、旧驱动和私有框架。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-028
  batch: '14'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-028
  source_name: spring-legacy-risk
  source_path: skills/spring-legacy-risk/SKILL.md
  source_sha256: sha256:5eca62d7c7d0ed1c99a9b391d178389412a4d30a9dd86d989257800336304100
  source_contract_sha256: sha256:848fb14b18624c7dad88eee36e5ee57fa4d1ad9bf17393bb97dc5ff758f057f3
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Legacy Risk Detector

## Objective

识别 XML-heavy、JSP、EJB、SOAP/RMI、JNI、反射、字节码、旧驱动和私有框架。

## Scope and capabilities

- 静态+运行检测
- criticality/likelihood/verification difficulty
- 处理路线映射
- 未知默认不按低风险

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

- legacy-risk-register.json
- risk-heatmap.json

## Execution workflow

1. 安全接入并冻结仓库
2. 运行 Source Profile、Scale/Risk 和 Private Dependency Preflight
3. 在可信 Runner 重建 Baseline
4. 计算 Eligibility、机器 ETA、成本与置信区间
5. 生成付费 Assessment 与 Go/No-go

## Implementation tasks

- [ ] 定义 `spring-legacy-risk` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `spring-legacy-risk` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现 Git/archive intake 与 credential broker
- [ ] 实现 Eligibility hard/soft gates
- [ ] 实现 Baseline known-failure ledger
- [ ] 实现 Legacy/Private Dependency detectors
- [ ] 实现 ETA/effort/quote inputs 和 Assessment report

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 同一 commit 接入产生相同 tree hash
- [ ] 两次 Baseline 结果不稳定时必须阻断
- [ ] 固定价项目在低置信度时被拒绝

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：legacy-risk-register.json, risk-heatmap.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] Assessment 支持断点续传和阶段缓存
- [ ] 机器 ETA 按运行事件持续重估

## Stop, block, or escalate when

- 仓库来源/授权/完整性失败
- Baseline 不可重复
- 关键 artifact/凭据/环境缺失
- P0 unsupported 无处理方案

## Definition of done

- [ ] 客户在修改源码前获得可审计 Go/No-go
- [ ] 历史失败与迁移回归边界冻结
- [ ] 报价、ETA、假设和风险进入 SOW
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：legacy-risk-register.json, risk-heatmap.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `spring-baseline-preflight`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:848fb14b18624c7dad88eee36e5ee57fa4d1ad9bf17393bb97dc5ff758f057f3`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
