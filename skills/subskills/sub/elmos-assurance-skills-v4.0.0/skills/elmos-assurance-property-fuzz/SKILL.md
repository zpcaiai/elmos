---
name: elmos-assurance-property-fuzz
description: 性质、变形与模糊测试。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 性质、变形与模糊测试

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 状态/语义模型
- approved metamorphic relations
- bounded budget

## Execute
1. 为每性质定义域和前提，覆盖无效输入与状态序列，不由LLM臆造普适关系。
2. 按业务risk分层seed语料，配置确定性seed/deadline/资源限制。
3. 区分crash、assert failure、timeout/infra，保留原始输入与最小反例。
4. 安全存储fuzz corpus，反例提升为固定regression，追踪污染与覆盖增益。

## Deliver
- `PropertyResults`
- `FuzzCorpus`
- `ReducedReproducers`

## Acceptance
- Given 变形前提不满足; verify 不报伪业务错误，标predicate not applicable。
- Given fuzzer超预算; verify INCONCLUSIVE不能当没发现bug=PASS。
- Given 发现随机反例; verify 固定seed/最小输入可原生复现。

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
