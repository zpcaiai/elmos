---
name: elmos-assurance-repository-domain
description: 全仓库语言转换集成。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 全仓库语言转换集成

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- source repo
- language pair profile
- Semantic IR adapters

## Execute
1. 盘点依赖/公共API/运行时特性，明确数值/异常/资源/反射/并发支持范围。
2. 构建模块级IR语义与compat shims，生成每个rule前提及组合义务。
3. 同输入原生source-target运行，验证serialization/DB/effect/workflow，不只比较函数返回值。
4. 模块proof不能冒充全库proof；按domain反例和native集成晋级语言对。

## Deliver
- `RepositoryRefinementAdapter`
- `ModuleObligationGraph`
- `NativeConversionRoute`

## Acceptance
- Given Java BigDecimal转浮点; verify 精度义务或差分必须阻断。
- Given 模块测试都过但依赖装配失败; verify 仓库native build/workflow失败。
- Given 未支持FFI被静默替换; verify UNSUPPORTED_SEMANTICS。

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
