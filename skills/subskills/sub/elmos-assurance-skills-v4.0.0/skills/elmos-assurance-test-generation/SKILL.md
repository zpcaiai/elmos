---
name: elmos-assurance-test-generation
description: 独立可执行用例生成。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 独立可执行用例生成

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- Approved Contract/Oracle/ObligationSet
- 语言runner adapter

## Execute
1. 按approved spec生成unit/contract/workflow/effect tests，测试工人不读候选expected。
2. 为每case定义fixture、action、assertion、cleanup、seed、timeout与claims。
3. 拒绝空assert、assert true、仅snapshot未审核；mock边界与真实effect分别标注。
4. 编译原生测试并检查manifest恰好对应实际发现的tests；多/少/skip都留事实。

## Deliver
- `TestManifest`
- `NativeTestSources`
- `AssertionMap`

## Acceptance
- Given service调用没有assert; verify 测试有效性检查必须标弱/无效。
- Given target错误但test复制target输出; verify 独立oracle挑战失败，禁止自洽PASS。
- Given runner发现数小于manifest; verify 未运行项必须阻断required回归。

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
