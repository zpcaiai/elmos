---
name: elmos-assurance-fixtures-environments
description: 测试数据与原生环境工厂。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 测试数据与原生环境工厂

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- TestManifest
- 数据授权
- native compatibility matrix

## Execute
1. 使用受控原生语言/DB版本启动隔离lane；构建与测试网络权限分离。
2. 生成NULL/极值/Unicode/多tenant/时区等语义数据并记录seed/collation/SQL modes。
3. 每scenario独立schema/namespace，broker发短期最小权限凭据。
4. snapshot/restore与清理可重现，污染检查和TTL清理有证据；缺工具不得用mock替代native。

## Deliver
- `EnvironmentLock`
- `FixtureSnapshots`
- `CleanupEvidence`

## Acceptance
- Given 两个scenario同主键数据; verify 互不污染、独立回放结果一致。
- Given 没有目标DB运行时; verify native status NOT_RUN，不能标DB回归通过。
- Given 测试失败中途退出; verify 自动清理或隔离留档，无凭据泄漏。

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
