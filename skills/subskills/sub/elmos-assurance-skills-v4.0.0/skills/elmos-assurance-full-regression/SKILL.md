---
name: elmos-assurance-full-regression
description: 全功能回归与测试资产管理。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 全功能回归与测试资产管理

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 冻结TestManifest
- Smoke PASS
- 同一artifact/fixtures

## Execute
1. 执行全部required case：功能、状态、权限、错误、事务、effect与工作流。
2. 对actual discovered/executed/asserted cases与批准manifest作集合核对。
3. 重试只区分可重试基础设施故障；记录首次失败并处理critical flake，不用多次最终绿掩盖。
4. 修复反馈可用impact tests；最终release按政策执行完整新候选回归或经批准的严格证据复用。

## Deliver
- `RegressionReport`
- `PerObligationResults`
- `FlakeReport`

## Acceptance
- Given critical case被skip; verify 回归INCONCLUSIVE/FAIL，不是100%。
- Given 第一次失败随后偶然通过; verify 保存flake且关键路径阻断。
- Given 回归结束后目标artifact变了; verify 旧回归证据不能签新目标。

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
