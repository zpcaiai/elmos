---
name: elmos-assurance-commercial-control
description: 多租户商业控制与交付产品化。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 多租户商业控制与交付产品化

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 产品范围
- 现有账号计费/API
- 审计服务策略

## Execute
1. 构建scope→estimate→approve→run→audit→deliver生命周期，商业状态与技术verdict分离。
2. 支持项目/组织权限、审计授权、retention、导出、申诉和证书查询。
3. 计费按真实execution/审计服务，充值不能购买PASS或豁免critical。
4. 报告可机读与人读，支持矩阵/assumptions/exclusions/current status一目了然。

## Deliver
- `AssuranceAPI`
- `EntitlementPolicy`
- `CustomerDeliveryBundle`

## Acceptance
- Given 用户付费但测试FAIL; verify verdict保持FAIL。
- Given 客户验收人未批准; verify 不伪造customer acceptance。
- Given 证书过期; verify 界面和API都显式expired。

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
