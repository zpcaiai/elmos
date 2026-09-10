---
name: elmos-assurance-mutation-auditor
description: 领域变异与测试有效性审计。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 领域变异与测试有效性审计

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- Domain MutationPack
- 原始suite
- 独立holdout策略

## Execute
1. 在隔离克隆artifact上注入auth/transaction/NULL/precision/async等领域变异，保证最终artifact不变。
2. 识别invalid/equivalent需理由与独立证据；unreached/timeout/unknown不悄悄排除。
3. 报告保守kill ratio、全部分类分母与关键must-kill结果，不设无依据统一99.9目标。
4. Ethen hidden mutations和历史real-bug corpus分开；核查攻击面是suite还是整个certifier。

## Deliver
- `MutationCampaign`
- `MutantResults`
- `EffectivenessReport`

## Acceptance
- Given 移除权限检查但suite绿; verify critical survivor阻断。
- Given mutant timeout; verify 不得自动计为killed。
- Given 100个mutant中10个unknown; verify unknown显式报告并影响门禁。

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
