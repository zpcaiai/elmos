---
name: elmos-assurance-differential-runtime
description: 类型化差分与行为回放。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 类型化差分与行为回放

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 源/目标原生runtime
- 相同scenario corpus
- ComparatorPolicy

## Execute
1. 冻结相同逻辑输入/fixtures、时间和外部依赖，分别执行source/target。
2. 捕获return/error/HTTP/session/DB/MQ/cache/file等scope规定观察。
3. 依类型和声明语义比较ordered/bag/set、decimal、NULL、时间、编码与event偏序。
4. normalization规则带批准前提与测试；差异自动缩减成回归，旧行为不自动等同正确规范。

## Deliver
- `TypedObservations`
- `DiffFindings`
- `MinimizedCounterexamples`

## Acceptance
- Given SQL结果重复行被去重; verify bag comparator必须发现。
- Given 金额差0.01; verify 无批准容差时必须失败。
- Given source/target共同有越权; verify 规范安全oracle仍必须发现。

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
