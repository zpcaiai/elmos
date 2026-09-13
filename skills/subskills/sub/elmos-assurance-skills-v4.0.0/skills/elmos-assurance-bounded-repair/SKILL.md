---
name: elmos-assurance-bounded-repair
description: 有界修复与证据重新建立。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 有界修复与证据重新建立

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 最小反例/findings
- 原scope和policy
- repair预算

## Execute
1. 分类实现缺陷/规范冲突/环境失败，不让所有失败都交给LLM改代码。
2. 在新worktree生成patch，限制改动目录、迭代/资源，保持原tests与oracle。
3. 禁止删测试、改门槛、改分母或未经批准更新snapshot；改规范需另行审批新scope。
4. 先最小反例与impact验证，后最终全部required regression；新RevisionSet重建相关proof/evidence/Ethen批准。

## Deliver
- `PatchCandidate`
- `RepairLineage`
- `ReverificationPlan`

## Acceptance
- Given 修复Agent删失败测试; verify policy拒绝。
- Given 修复只通过反例但破坏其它功能; verify 最终回归阻断。
- Given 预算耗尽; verify 暂停并输出未决，不强制PASS。

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
