---
name: elmos-assurance-security-isolation
description: 租户、供应链与不可信执行隔离。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 租户、供应链与不可信执行隔离

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 威胁模型
- 现有身份/网络/存储控制
- 代码/数据分类

## Execute
1. 拒绝repo hooks提升权限，限制归档/引用/解析/执行资源及egress。
2. 多tenant DB/FK/RLS、对象存储scope和broker权限共同约束；superuser/owner例外需测试。
3. builder不能读hidden tests/audit keys，审计runner不共享builder记忆或token。
4. SBOM/provenance/dependency scan+运行沙箱+secret redaction，先native演练后上生产。

## Deliver
- `ThreatModel`
- `RunnerSecurityPolicy`
- `IsolationEvidence`

## Acceptance
- Given tenant A引用B evidence blob; verify 拒绝。
- Given 构建脚本读取host key或docker socket; verify 隔离阻断。
- Given OpenAPI外链/压缩炸弹/恶意proof; verify 受控拒绝，不执行高权限代码。

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
