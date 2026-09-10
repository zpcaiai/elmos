---
name: elmos-assurance-generation-domain
description: 项目生成业务线集成。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 项目生成业务线集成

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- Domain spec
- 目标语言support matrix
- 现有生成入口

## Execute
1. 将spec/contract/state/oracle审批放在代码生成之前。
2. 分别生成实现与测试候选，独立规范审核降低共同错误。
3. 验收真实DB/消息/权限/UI流程；不同生成语言分别对规范测试，不互相作唯一Oracle。
4. 落实domain-packs/project-generation全部critical cases，再逐个扩展目标语言。

## Deliver
- `SpecFirstGenerationAdapter`
- `NativeGenerationRoute`
- `DomainAcceptanceEvidence`

## Acceptance
- Given 需求遗漏但API全绿; verify requirement traceability必须失败。
- Given 两种语言共同漏租户隔离; verify 独立安全规范检测。
- Given 只测试Python却宣称所有目标通过; verify support matrix拒绝晋级。

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
