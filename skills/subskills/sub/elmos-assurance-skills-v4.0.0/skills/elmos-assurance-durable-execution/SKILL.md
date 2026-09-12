---
name: elmos-assurance-durable-execution
description: 恢复、取消、fencing与结果提交。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 恢复、取消、fencing与结果提交

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 现有Workflow/Harness
- TestExecutionPlan
- 权限租约

## Execute
1. 复用现有durable workflow，固化step/attempt/lease/epoch/schema版本。
2. 执行计划绑定VerifiedSecurityContext/CapabilityLease，恢复保留上限并重验当前撤销/期限。
3. Result Interception在commit前校验subject/producer/epoch，唯一键幂等，transactional outbox。
4. 取消提升epoch阻止迟到commit；外部effect未知先对账/补偿，不宣称无条件exactly-once。

## Deliver
- `RunnerBrokerIntegration`
- `DurableEvents`
- `SideEffectReconciliation`

## Acceptance
- Given worker commit前崩溃后重送; verify 控制平面只有一个可见结果。
- Given 过期lease恢复; verify 拒绝或受控换发，不能复活。
- Given 取消后旧worker回传; verify FENCE_REJECTED。

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
