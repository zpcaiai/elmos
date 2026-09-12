---
name: elmos-assurance-model-checking
description: SMT与有限状态协议校验。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# SMT与有限状态协议校验

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 状态机/资源约束
- 模型边界
- 风险claims

## Execute
1. 优先建lease/fencing/cancel/commit与预算模型，明确finite bounds和fairness。
2. 锁定solver/TLC版本、选项、输入模型hash、proof或counterexample。
3. 将UNKNOWN/timeout与UNSAT/verified区分；对可用证明证书作独立检查。
4. 模型到实现映射和反例回放原生测试单独验收，不能把bounded性质扩成无限保证。

## Deliver
- `ModelCheckObligations`
- `SolverEvidence`
- `NativeCounterexampleTests`

## Acceptance
- Given 旧epoch仍可commit的模型; verify 产出反例并转实现回归。
- Given solver UNKNOWN; verify 禁止PASS。
- Given 仅验证3个worker; verify 报告bound=3，不能宣称任意规模。

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
