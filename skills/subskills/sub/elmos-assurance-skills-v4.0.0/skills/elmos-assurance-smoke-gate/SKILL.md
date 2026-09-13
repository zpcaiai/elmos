---
name: elmos-assurance-smoke-gate
description: 关键路径冒烟门禁。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 关键路径冒烟门禁

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- TestPlan
- 关键义务
- 运行环境

## Execute
1. 按风险/依赖中心性和估算机器成本选最小覆盖关键义务集合，不随机挑case。
2. 包含启动、真实依赖、鉴权与至少一条关键业务effect canary。
3. 在冻结artifact上运行并验证assertions、cleanup、manifest完整性。
4. 缺失/失败时阻断依赖运行健康的昂贵任务；保留证据，允许独立静态/规则证明继续。

## Deliver
- `SmokeManifest`
- `SmokeExecutionEvidence`
- `SmokeGateDecision`

## Acceptance
- Given health=200但下单持久化坏; verify smoke失败。
- Given 预算不足覆盖关键义务; verify 报告uncovered而不是小suite PASS。
- Given smoke失败; verify 不派发依赖它的完整runtime回归。

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
