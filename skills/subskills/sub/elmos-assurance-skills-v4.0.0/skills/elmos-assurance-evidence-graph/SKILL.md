---
name: elmos-assurance-evidence-graph
description: 证据DAG、封存与失效传播。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。
---

# 证据DAG、封存与失效传播

## Mission
在既有Elmos架构内完成此模块的代码、原生集成、负例和证据。优先级 **P0**。本skill不是新的业务canonical route。

## Read first
当前仓库AGENTS.md/CLAUDE.md；本包`CODEX_START_HERE.md`、`docs/00-architecture.md`、`docs/01-contracts-and-states.md`。
安装后的包根为`.elmos/assurance-package-v4.0.0/`。详细任务/验收在同目录implementation.yaml与acceptance.yaml。

## Preconditions
- runner/proof/audit observations
- RevisionSet
- producer identity

## Execute
1. 以content hash保存raw artifacts，校验tenant/project/run/claim/tool/版本/环境/时间绑定。
2. 签名验证以服务端trust store为根，不信repo自带证书；schema严校验不忽略未知字段。
3. 构建claims-assumptions-defeaters-evidence DAG，封存后append-only，断言必须可追原始报告。
4. 变更传播按依赖closure重新计算；记录revocation/freshness，与object storage原子publish协调。

## Deliver
- `EvidenceEnvelope`
- `EvidenceGraph`
- `SealedEvidenceRoot`

## Acceptance
- Given 修改已签报告一个字段; verify 签名校验失败。
- Given 别的tenant的合法证据; verify 拒绝复用。
- Given repo自带根公钥; verify 不得加入服务信任根。

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
