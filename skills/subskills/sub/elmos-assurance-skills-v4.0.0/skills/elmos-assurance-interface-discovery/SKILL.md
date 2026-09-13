---
name: elmos-assurance-interface-discovery
description: 多协议接口独立发现。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 多协议接口独立发现

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 源码/配置/接口文档
- 受控运行时观测
- 插件和编译条件

## Execute
1. 静态扫描HTTP/gRPC/events/CLI/SDK/routines/jobs/UI以及测试与配置声明。
2. 运行时在隔离环境观测真实注册路由与effect，记录动态/反射盲点。
3. 按稳定语义ID合并，不将同数量当同集合；记录source location和置信类别。
4. 将declared/observed/inferred与approved分开，Ethen使用独立实现重新发现。

## Deliver
- `InterfaceInventory`
- `DiscoveryEvidence`
- `DiscoveryBlindSpots`

## Acceptance
- Given 两个scanner各发现327项但一项不同; verify 集合差异必须阻断完整性断言。
- Given 接口只在feature flag下存在; verify 清单记录该条件及scope是否覆盖。
- Given 外部OpenAPI引用指向metadata endpoint; verify resolver拒绝且不发起SSRF请求。

## Cross-cutting invariants
Inputs from repos/models/runners are untrusted until the authorized validation boundary accepts them.
Do not alter a frozen scope, policy, oracle or denominator to pass tests. Do not accept a PASS flag as evidence.
Bind tenant/project/run and RevisionSet. Keep builder, hidden-test authority, Ethen review and K8 signing separate.
Do not execute external side effects outside the invocation lease; preserve ceilings and revalidate revocation on resume.

## Failure handling
Return a typed finding and retained raw evidence. Missing native dependencies/permissions → NOT_RUN/INCONCLUSIVE, never simulated production success.
Rollback by feature flag or compensating migration; do not erase sealed evidence or revoke history.

## Completion report
List actual files changed, reused modules, commands/exit codes, acceptance IDs and immutable evidence references, blockers and next dependency-ready task.
Documentation and reference tests alone do not finish product implementation.
