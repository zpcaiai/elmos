---
name: elmos-assurance-router-budget
description: 模型路由与验证成本治理。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 模型路由与验证成本治理

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 现有Elmos Router
- ModelExecutionPlan
- Usage Ledger/Budget

## Execute
1. 所有test/proof/audit模型调用复用Elmos语义路由，不将provider endpoint交给caller。
2. 使用purpose隔离的ModelExecutionPlan、安全上下文、数据策略、fallback与deadline。
3. 预留并发/费用，默认每账号3个top-level run；子任务不可绕过。
4. 估算与实际分离，重复回执幂等，未知usage对账；预算不足不缩小必需测试集合。

## Deliver
- `AssuranceModelPorts`
- `BudgetReservations`
- `UsageReconciliation`

## Acceptance
- Given OpenRouter fallback降数据隔离; verify policy拒绝。
- Given 并行任务争抢预算; verify 不超预留上限，失败可见。
- Given timeout无usage; verify 记pending而非0，认证暂停不造PASS。

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
