---
name: elmos-assurance-requirement-oracles
description: 需求解析与独立判定基准。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 需求解析与独立判定基准

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 原始需求
- 旧文档/旧行为
- 安全策略

## Execute
1. 将需求拆成可证伪claims、状态/前后置条件、错误与effect；保留原文span。
2. 标记normative/compatibility/invariant/metamorphic/reference/LLM-proposal来源。
3. 独立批准expected和关系前提，不允许从target返回值反向填expected。
4. 规范、源行为或安全要求冲突时创建finding；批准行为变更单独建回归。

## Deliver
- `RequirementSet`
- `OracleRegistry`
- `ConflictFindings`

## Acceptance
- Given 接口返回200但数据库写错; verify 业务oracle失败，不只检查状态码。
- Given 旧系统存在越权漏洞; verify 安全规范优先、兼容变化有授权记录。
- Given 两个Oracle矛盾; verify INCONCLUSIVE并显示冲突，不投票选通过者。

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
