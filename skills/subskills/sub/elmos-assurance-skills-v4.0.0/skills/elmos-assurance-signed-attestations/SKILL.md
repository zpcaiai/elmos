---
name: elmos-assurance-signed-attestations
description: K8签署、发布与撤销。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# K8签署、发布与撤销

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- GateDecision
- authorized Ethen review
- K8/IdP/KMS

## Execute
1. 复用K8，私钥不进入Agent/runner；正式采用审定的statement/DSSE和KMS接口。
2. 签署前再次验证当前授权、全部subject/原始证据hash、nonce、policy和撤销状态。
3. 签名payload明确scope/exclusions/assumptions/有效期/assurance profile与formal范围。
4. 支持status verify/revoke/suspend/supersede/key rotation，旧决定不可覆盖。
5. 没有生产签署服务只产unsigned draft，禁止伪造签名或“认证人Ethen”名字当授权。

## Deliver
- `ScopedAttestation`
- `RevocationRecord`
- `VerificationEndpoint`

## Acceptance
- Given artifact与certificate subject不匹配; verify verification失败。
- Given 签署key或rule被撤销; verify status不得显示有效。
- Given 没有真实Ethen/KMS; verify 只产draft且明确不可认证。

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
