---
name: elmos-assurance-workbench-ui
description: 接口覆盖、审计和证据工作台。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 接口覆盖、审计和证据工作台

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- Assurance API
- 权限矩阵
- 设计系统

## Execute
1. 复用现有前端/设计系统，不另造产品；接口清单显示发现来源与盲点。
2. 覆盖显示冻结分母与planned/executed/asserted/passed，可钻取raw evidence与反例。
3. 进度使用真实stage与wall-clock/cost，UNKNOWN/NOT_RUN显眼显示，取消有状态反馈。
4. Ethen审核独立入口；证书显示scope/有效期/撤销与formal边界，隐藏集不泄露到普通前端。

## Deliver
- `ContractReviewUI`
- `CoverageAndRunUI`
- `EthenAndCertificateUI`

## Acceptance
- Given 回归90%执行但100%已执行case通过; verify UI不能显示全功能100%通过。
- Given 普通用户访问Ethen hidden routes; verify 前后端均拒绝。
- Given 证书撤销后缓存页面; verify 显示撤销/查询时间，不能继续绿徽章。

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
