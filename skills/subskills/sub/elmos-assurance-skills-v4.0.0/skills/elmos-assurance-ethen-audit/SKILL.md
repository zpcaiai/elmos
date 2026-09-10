---
name: elmos-assurance-ethen-audit
description: Ethen外部独立审计适配器。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# Ethen外部独立审计适配器

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- sealed candidate bundle
- 真实auditor identity配置
- hidden challenge策略

## Execute
1. 支持human/organization/external_system，显式control domain/利益冲突/权限/有效期，默认未配置阻断。
2. 独立发现接口、核验规范/分母、选择高risk重跑、hidden challenge和盲mutation。
3. 审计scope/proof statement/assumptions而非只看汇总绿灯；隐藏集与Builder存储隔离。
4. review绑定所有摘要、nonce、audience与期限；输出APPROVE/REJECT/NEEDS_EVIDENCE，不直接改代码。
5. 修复暴露的challenge退役并进入公开回归；Ethen若参与实现则重新声明冲突。

## Deliver
- `AuditSession`
- `SignedAuditDecision`
- `IndependenceDisclosure`

## Acceptance
- Given 只把另一个LLM命名Ethen; verify 不得声称组织独立外审。
- Given Ethen签了旧revision; verify approval拒绝。
- Given builder和auditor不同key但同control domain; verify strict external profile阻断。

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
