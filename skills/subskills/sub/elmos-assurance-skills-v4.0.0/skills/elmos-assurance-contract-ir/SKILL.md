---
name: elmos-assurance-contract-ir
description: 可执行接口与语义契约。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 可执行接口与语义契约

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- InterfaceInventory
- RequirementSet
- OracleRegistry

## Execute
1. 定义版本化统一Contract IR：protocol/auth/schema/outcomes/state/effect/temporal/error/idempotency。
2. 通过source span与需求ID建立双向映射；不暴露内部函数为生产API。
3. 先校验无歧义和必需语义，再投影OpenAPI等格式；不支持字段需显式loss report。
4. 使用Etag/digest批准不可变snapshot；contract drift要求重新审批和影响分析。

## Deliver
- `ContractSnapshot`
- `OpenAPI/AsyncAPI/proto projections`
- `ContractApproval`

## Acceptance
- Given 只提供OpenAPI无订单状态规则; verify 标注缺失业务契约，不认为全规范已完成。
- Given 有状态接口丢失effect投影; verify loss report阻断相应保证。
- Given 旧contract批准被用于新schema; verify 拒绝摘要不匹配。

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
