---
name: elmos-assurance-gate-engine
description: 确定性三态认证门禁。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 确定性三态认证门禁

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 服务端ApprovedScope/Policy
- verified evidence facts
- Ethen decision

## Execute
1. 构建无LLM判断的纯决策核，所有required证据齐备且匹配才可PASS。
2. 明确FAIL反例与INCONCLUSIVE证据不足；critical UNKNOWN/SKIP/flake不可绿。
3. 校验覆盖分母非空、tests实际断言、mutation must-kill、formal义务和审计独立性。
4. 输出决定及最小阻塞集合，绑定policy/scope/revision/evidence root；不执行签署。

## Deliver
- `GateDecision`
- `BlockingReasons`
- `BoundedAssuranceClaims`

## Acceptance
- Given 空报告/空suite; verify INCONCLUSIVE且不可签。
- Given 已知critical反例加其它全绿; verify FAIL。
- Given caller提交更宽松policy; verify server拒绝未批准digest。

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
