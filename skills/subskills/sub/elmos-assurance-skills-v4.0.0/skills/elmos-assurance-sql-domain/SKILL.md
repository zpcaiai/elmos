---
name: elmos-assurance-sql-domain
description: SQL/例程语义转换集成。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# SQL/例程语义转换集成

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 源/目标SQL/catalog
- native DB版本
- 现有SQL转换入口

## Execute
1. 锁定catalog/collation/timezone/SQL modes/类型与约束，不只parse字符串。
2. 按feature profile分类query/DML/DDL/routine/transaction，unsupported fail closed。
3. 原生双DB数据相同语义生成，按typed bag/order/effects和异常比较。
4. 落实NULL/LEFT JOIN/decimal/order/事务反例；proof规则只在前提和runtime模型成立时使用。

## Deliver
- `SqlSemanticAdapter`
- `NativeSqlRoute`
- `SqlMutationPack`

## Acceptance
- Given NOT IN改写忽略外层NULL; verify 原生反例失败。
- Given 未支持vendor function被best effort忽略; verify 阻断转换认证。
- Given 查询结果相同但DML影响行数不同; verify 副作用差分失败。

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
