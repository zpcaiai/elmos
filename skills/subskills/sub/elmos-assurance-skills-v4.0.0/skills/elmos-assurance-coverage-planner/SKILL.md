---
name: elmos-assurance-coverage-planner
description: 覆盖义务与风险计划编译。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 覆盖义务与风险计划编译

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- ApprovedScopeRecord
- ContractSnapshot
- StateMachineSet

## Execute
1. 生成Requirement/Interface/Input/State/Permission/Error/Effect/Concurrency/Semantics/Platform覆盖维度。
2. 关键路径显式组合；其余允许经批准t-wise，记录强度而非虚假穷尽。
3. 分开planned/executable/executed/asserted/passed，冻结分母与suite版本。
4. 测算机器预算、不可测义务和缺失oracle，不能为节省成本删除required项。

## Deliver
- `ObligationSet`
- `CoverageMatrix`
- `TestPlan`

## Acceptance
- Given 0条可测试义务; verify 返回缺口/INCONCLUSIVE，不给100%。
- Given 只有测试存在但未执行; verify 仅planned上升，passed保持0。
- Given 关键角色/租户组合缺失; verify 即使总覆盖很高也阻断。

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
