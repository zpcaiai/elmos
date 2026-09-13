---
name: elmos-assurance-lean
description: Lean命题、证明与源码绑定。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# Lean命题、证明与源码绑定

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P1**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- 批准critical claims
- 支持的Semantic DSL
- trusted challenge

## Execute
1. 独立定义精确statement/imports/假设，不让proof作者改challenge缩小问题。
2. 在固定hash工具链和沙箱中构建；做传递axiom审计与版本适用安全检查。
3. 严格profile用可信comparator与兼容独立checker，校验statement与proof artifact；缺checker明确阻塞。
4. 验证rule实例preconditions、source→IR→lowering→artifact绑定；仅元数据proof=true无效。
5. native case仍需测试，Lean输出不替代DB/框架原生行为证据。

## Deliver
- `ProofObligation`
- `ProofVerificationEvidence`
- `ArtifactRefinementLinks`

## Acceptance
- Given proof依赖sorryAx/自定义未批准公理; verify 拒绝critical formal PASS。
- Given 证明x>0但需求含负数; verify statement mismatch阻断。
- Given theorem通过但目标源码变更; verify refinement link失效，要求重验。

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
