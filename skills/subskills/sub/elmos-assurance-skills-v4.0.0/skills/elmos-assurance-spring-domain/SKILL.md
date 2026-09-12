---
name: elmos-assurance-spring-domain
description: Spring旧项目原生翻新集成。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# Spring旧项目原生翻新集成

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 旧仓库/runtime
- 批准目标版本
- Framework Semantics Pack

## Execute
1. 隔离旧runtime，记录HTTP/session/views/DB/MQ/security/transactions/jobs。
2. 映射路由/binding/validation/filter/interceptor/security/exception/JSP/Quartz与javax/jakarta变化。
3. 真实代理/DB故障验证transaction/rollback/self invocation，不只grep@Transactional。
4. 批准旧漏洞修复为行为变更；落实Spring domain critical cases，旧系统跑不起来不得声称行为等价。

## Deliver
- `BehaviorRecorder`
- `SpringMigrationAdapter`
- `NativeSpringRoute`

## Acceptance
- Given 保留注解但self invocation导致无事务; verify native DB故障测试发现。
- Given Session returnUrl丢失; verify 旧新完整行为差分失败。
- Given 只有target build成功; verify 不获得迁移行为认证。

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
