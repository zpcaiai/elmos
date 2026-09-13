---
name: elmos-assurance-release-recertification
description: 发布、持续验证与撤销链。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 发布、持续验证与撤销链

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 签署attestation
- 部署版本/环境
- 运行时反馈

## Execute
1. 签署artifact与部署artifact逐字摘要一致；客户scope和运行环境相符才放行。
2. 新依赖/框架/规则/checker/政策/数据边界变化触发精确失效/复验。
3. 影子运行不得产生重复真实effect；canary渐进与自动止损需授权配置。
4. 演练备份恢复、密钥轮换/撤销、关键缺陷回滚；持久记录原决策和更新原因。

## Deliver
- `ReleaseGate`
- `ReverificationTriggers`
- `RollbackAndRevocationEvidence`

## Acceptance
- Given 部署不同镜像但同commit; verify 拒绝发布。
- Given checker/rule被撤销; verify 受影响claims触发重验。
- Given 恢复数据库复活旧证书; verify 校验撤销链防复活。

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
