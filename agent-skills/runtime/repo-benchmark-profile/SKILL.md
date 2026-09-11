---
name: repo-benchmark-profile
description: 定义 Benchmark 仓库披露的 MRLOC、RCS、模块、测试、依赖、运行维度、基线和独立性。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-023
  batch: '13'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-023
  source_name: repo-benchmark-profile
  source_path: skills/repo-benchmark-profile/SKILL.md
  source_sha256: sha256:3f96de9ddc73815596ffc93b0385fddeaf9feb19f1cfb222ed299b08af217060
  source_contract_sha256: sha256:12793d2464ee19a806e6ddfa9b61f01385c68a9f2cabf56ad771664b8e4d1721
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Benchmark Repository Profile

## Objective

定义 Benchmark 仓库披露的 MRLOC、RCS、模块、测试、依赖、运行维度、基线和独立性。

## Scope and capabilities

- source_family_id
- independent_repository_id
- 匿名脱敏
- MRLOC 审计
- Baseline/Proof 引用

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

- benchmark-profile.json
- public-redacted-profile.json

## Execution workflow

1. 遍历仓库并识别文件来源
2. 统计 Gross/First-party/Production/Test/Config/MRLOC
3. 按 ERSS 分类并计算 RCS
4. 估计/计算 Transformation Surface 与 Semantic Changes
5. 生成可审计 Benchmark/Scale Profile

## Implementation tasks

- [ ] 定义 `repo-benchmark-profile` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `repo-benchmark-profile` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现流式 LOC/文件来源扫描器
- [ ] 实现 ERSS/RCS 版本化公式
- [ ] 实现 Semantic Patch 归因和 Transformation Surface
- [ ] 建立 source_family/independent_repository 身份
- [ ] 输出技术/商业/脱敏报告

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] generated/vendor/build output 不得进入 MRLOC
- [ ] ERSS 边界值测试
- [ ] RCS 每一维可追踪事实
- [ ] fork/branch 家族重复检测

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：benchmark-profile.json, public-redacted-profile.json。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 1M MRLOC 扫描目标 10 分钟内（本地 SSD 参考）
- [ ] 按文件内容哈希增量重算

## Stop, block, or escalate when

- 大体量目录来源不明且影响 Benchmark
- MRLOC audit_required
- unowned semantic changes 存在

## Definition of done

- [ ] MRLOC 可由独立工具重算并在容许误差内
- [ ] ERSS/RCS/Surface 均带版本和证据
- [ ] 大型案例满足 Strong Large 附加条件
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：benchmark-profile.json, public-redacted-profile.json。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `repo-rcs`
- `repo-semantic-accounting`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:12793d2464ee19a806e6ddfa9b61f01385c68a9f2cabf56ad771664b8e4d1721`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
