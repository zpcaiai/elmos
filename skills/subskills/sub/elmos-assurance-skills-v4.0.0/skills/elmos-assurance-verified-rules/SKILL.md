---
name: elmos-assurance-verified-rules
description: 带证据变换规则注册中心。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 带证据变换规则注册中心

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- TransformationRule
- formal/native证据
- known counterexamples

## Execute
1. 注册版本化source/target pattern、语义模型、前提、禁用情况、theorem/runtime evidence。
2. 每次应用验证前提与工具链/encoder/lowering版本，LLM不能直接设置PROVED。
3. 缓存key包括rule/semantics/工具链与适用实例信息，租户机密不跨域复用。
4. 新反例或checker问题撤销rule并沿依赖图失效已有claims/attestations。

## Deliver
- `VerifiedRuleRecord`
- `ApplicabilityDecision`
- `RuleRevocationIndex`

## Acceptance
- Given 已证明规则用于不满足NULL前提的SQL; verify 拒绝适用。
- Given rule换版本缓存仍命中; verify 证据不得复用。
- Given rule发现反例; verify 受影响证书进入复审/撤销链。

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
