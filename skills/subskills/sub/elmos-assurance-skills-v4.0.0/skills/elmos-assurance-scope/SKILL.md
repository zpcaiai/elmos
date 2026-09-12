---
name: elmos-assurance-scope
description: 范围与风险保证配置。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 范围与风险保证配置

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 客户需求
- support matrix
- 风险和数据分级

## Execute
1. 定义source/target/部署/数据/接口/版本/使用边界、风险等级和目标profile。
2. 按业务线列支持/不支持特性，排除项需要理由、责任人和影响；关键未知不得藏入excluded。
3. 冻结scope digest与obligation分母审批；变更生成新scope，保留审计链。
4. 从服务端profile解析必要门禁；caller不能提交任意宽松policy或空范围。

## Deliver
- `AssuranceScope`
- `ApprovedScopeRecord`
- `ProfileMapping`

## Acceptance
- Given 声明支持的订单权限流程; verify 在scope中形成必测claim。
- Given 用空scope或删除关键接口获得PASS; verify 拒绝或INCONCLUSIVE并保留原分母。
- Given 修改已批准scope字段; verify 旧approval失效且触发受影响证据重跑。

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
