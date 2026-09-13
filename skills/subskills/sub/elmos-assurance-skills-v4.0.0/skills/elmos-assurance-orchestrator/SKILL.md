---
name: elmos-assurance-orchestrator
description: 总编排：四业务线验证与Ethen独立审计。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 总编排：四业务线验证与Ethen独立审计

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 当前Elmos仓库
- 本包
- 本轮授权范围

## Execute
1. 先执行bootstrap并读取CODEX_START_HERE，不要求用户重复已知业务线。
2. 按roadmap DAG与真实差距选择一个完整纵向切片，四业务线共用契约/证据/安全内核。
3. 逐skill落实actual code+tests+evidence；按需加载，不一次加载所有长文。
4. 持续核对不可变RevisionSet、批准scope、独立Oracle和隐藏集界限。
5. 区分PACKAGE_VALIDATED/REFERENCE_TESTED/PRODUCT_NATIVE_VERIFIED/CUSTOMER_ACCEPTED；未实测绝不升档。
6. 停在签署/生产/权限边界时完成其它非阻塞工作，输出准确阻塞，不伪造Ethen/Lean/客户认证。

## Deliver
- `BatchExecutionReport`
- `EvidenceLinkedDelivery`
- `UnresolvedBlockers`

## Acceptance
- Given 包级pytest全部通过; verify 只报告参考实现通过，不给产品E5。
- Given 有已有功能可复用; verify 最小适配，不重建Harness。
- Given 所有内部测试通过但Ethen未配置; verify E5 INCONCLUSIVE，仍交付完整证据草案。

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
