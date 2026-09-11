---
name: spring-durable-session
description: 持久化 admission、queue/steer、provider turn、tool settlement、resume/interrupt 和 replay cursor。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos commercial implementation specification; upstream code remains under its original license
metadata:
  id: ELMOS-GR-052
  batch: '17'
  priority: P0
  risk: critical
  spec_version: 2.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: ELMOS-GR-052
  source_name: spring-durable-session
  source_path: skills/spring-durable-session/SKILL.md
  source_sha256: sha256:92c94dcf9ef0601d01dd7adcb4bcab2132d0f1ed0dfa7e066fee340e13e27c06
  source_contract_sha256: sha256:5c5dbeebbc0465068a132e821219c07d0fa3fa30e28059f4eb03d165f2b9dba3
  source_origin: commercial-extension
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Durable Migration Session

## Objective

持久化 admission、queue/steer、provider turn、tool settlement、resume/interrupt 和 replay cursor。

## Scope and capabilities

- Event-sourced aggregate
- 同 Session 串行/不同 Session 并发
- Reconnect-safe history
- Context Epoch/compaction
- Provider ambiguity

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

- session-events
- session-projection.json
- history-api

## Execution workflow

1. 解析编译/启动错误并聚类根因
2. 优先 Recipe/结构化 Tool 修复
3. 必要时构建最小 Semantic Context 调用 Repair Agent
4. 持久化 provider turn/tool settlement
5. 审批副作用并支持 crash recovery

## Implementation tasks

- [ ] 定义 `spring-durable-session` 的 public interface、输入/输出/Error Schema 和版本策略。
- [ ] 实现 `spring-durable-session` 的 production adapter/service，不把业务状态只保存在 Prompt 或内存对象中。
- [ ] 实现 tenant/project/run/task 作用域、幂等键、权限判定、Trace 和结构化错误。
- [ ] 将大结果写入 Artifact/Evidence Store，数据库仅存索引、状态和内容哈希。
- [ ] 增加配置、迁移、回滚、故障注入、负例和兼容性处理。
- [ ] 实现诊断 taxonomy/root-cause clustering
- [ ] 实现受限 Repair Agent 与 context slicer
- [ ] 实现 event-sourced session/inbox/context epoch
- [ ] 实现 typed Tool/Side-effect Ledger
- [ ] 实现 lease/fencing/reconciliation/approval/sandbox

## Required tests

- [ ] 单元测试覆盖正常、边界、无效输入和结构化错误。
- [ ] 集成测试必须使用真实或等价容器化依赖，不得只依赖 mock。
- [ ] 至少包含一次故障注入、重复请求、取消或恢复场景（按 Skill 适用范围）。
- [ ] 所有 mandatory 检查被跳过、disabled 或未执行时不得计为 PASS。
- [ ] 重复请求不得重复写操作
- [ ] Worker crash/network partition 下最多一次有效副作用
- [ ] deny 在 handler 前生效
- [ ] Agent 不得修改 holdout/降低断言

## Required evidence

- [ ] 保存输入快照、配置/规则/模型版本、执行命令、退出码和结构化结果。
- [ ] 保存 Artifact URI、SHA-256、producer、schema version、sensitivity 和时间戳。
- [ ] 任何 PASS/完成声明必须链接到不可变 Evidence；无证据只能是 unknown/partial/blocked。
- [ ] 至少生成：session-events, session-projection.json, history-api。

## Security and permissions

- [ ] 默认拒绝未知写权限、未知外部网络目标和未知生产副作用。
- [ ] 不得把仓库 Secret、客户私有源码或凭据发送给未获授权的模型/Provider。
- [ ] 高风险操作必须绑定 tenant/project/run/actor、permission decision 和审计事件。
- [ ] 所有不可信仓库代码在隔离 Runner/Sandbox 中执行。

## Performance and scale

- [ ] 同 Session 串行、不同 Session 有界并发
- [ ] 模型/Tool/Runner 多级预算
- [ ] 上下文选择目标 2s 内

## Stop, block, or escalate when

- Provider dispatch 或副作用状态 ambiguous 且无法对账
- Doom loop/重复 patch 无进展
- 上下文完整性审计失败
- 无合格 approver

## Definition of done

- [ ] 断线/重启后任务可继续且不丢 durable state
- [ ] 所有 Tool I/O 经过 schema/permission
- [ ] Agent patch 最小并通过 targeted+regression tests
- [ ] 本 Skill 的 required outputs 均由真实目标仓库执行产生：session-events, session-projection.json, history-api。
- [ ] 所有 mandatory tests 和 security gates 通过，且无 critical unknown。

## Dependencies

- `spring-context-slicer`
- `spring-migration-dag`

## Production-claim boundary

A valid Skill package, schema, fixture, installer or static test proves only that this specification is internally consistent. It does **not** prove that the target Elmos repository, a customer repository, external Provider, migration run, benchmark campaign or production release has implemented or passed this capability. Production claims require executed immutable Evidence linked through the Completion Gate.

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:5c5dbeebbc0465068a132e821219c07d0fa3fa30e28059f4eb03d165f2b9dba3`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
