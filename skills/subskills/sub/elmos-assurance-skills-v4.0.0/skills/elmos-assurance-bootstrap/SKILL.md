---
name: elmos-assurance-bootstrap
description: 仓库盘点与增量集成。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 仓库盘点与增量集成

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 现有Elmos仓库和本包
- AGENTS/CLAUDE约束
- 当前K8/Router/测试配置

## Execute
1. 只读识别四Domain Pack入口、路由、K8、Task、Artifact、Tenant、Usage和CI实际路径；不要从文档猜源码。
2. 逐项将本包逻辑模块映射到真实代码，标reuse/extend/absent/conflict；拒绝平行Harness。
3. 盘点运行时、数据库、编译器、测试runner、Lean及授权；不执行未审批repo hooks。
4. 冻结集成边界、feature flags、N-1契约fixtures和第一条native Golden Route；输出真实工具缺失项。

## Deliver
- `repo-map.json`
- `gap-analysis.md`
- `compatibility-map.json`
- `native-toolchain-inventory.json`

## Acceptance
- Given 发现既有K8签署器; verify 复用其接口并提交最小扩展，不新建绕过入口。
- Given 未读取源码或缺少数据库; verify 相关实现状态必须unknown/NOT_RUN，不能标completed。
- Given 旧E5含义与本包不同; verify 生成显式profile迁移映射，历史证书不变。

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
