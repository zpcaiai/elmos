---
name: elmos-assurance-state-effects
description: 状态机、副作用与时序模型。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 状态机、副作用与时序模型

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- ContractSnapshot
- DB/MQ/缓存关系
- 并发需求

## Execute
1. 定义可达状态、许可/禁止转移、角色/tenant条件和不变量。
2. 定义每个effect的幂等key、事务边界、可观察点、对账/补偿与超时歧义。
3. 异步事件用因果关联和deadline描述，不任意排序掩盖顺序错误。
4. 生成边界、无效转移、重试、取消和故障注入义务；建立test probes不进入生产artifact。

## Deliver
- `StateMachineSet`
- `EffectCatalog`
- `TemporalProperties`

## Acceptance
- Given 支付超时但结果未知; verify 先对账，禁止自动再次扣款。
- Given 事件晚于规范deadline; verify 语义deadline FAIL而非无限轮询。
- Given 取消后旧worker试图写入; verify fencing拒绝且记录审计。

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
