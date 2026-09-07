---
name: batch-25-behavioral-equivalence-gate
description: "Implement the complete Batch 25 skill system for Behavioral Equivalence Gate and Independent Oracle System."
version: 1.0.0
status: implementation-ready
---

# Batch 25: Behavioral Equivalence Gate and Independent Oracle System

## Mission

汇聚真实仓库、强化语义、框架执行和真实构建证据，使用独立 Oracle、可控调度和状态/副作用差分签发或拒绝行为等价证书。

## Upstream Contract

本 Batch 必须消费 Batch 24 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Oracle Registry
- Scenario Runtime
- Deterministic Environment
- Schedule Control
- State Differential
- Effect Differential
- API/Message/DB/File Diff
- Normalizer/Tolerance
- Error Contract
- Metamorphic/Property Oracle
- Inconclusive Handling
- BE1–BE5 Gate

## Skill Inventory

1. `$b25-behavioral-equivalence-gate-orchestrator`
2. `$b25-behavioral-equivalence-gate-domain-model`
3. `$b25-behavioral-equivalence-gate-discovery-inventory`
4. `$b25-behavioral-equivalence-gate-capability-planning`
5. `$b25-behavioral-equivalence-gate-deterministic-engine`
6. `$b25-behavioral-equivalence-gate-adapter-provider`
7. `$b25-behavioral-equivalence-gate-workflow-runtime`
8. `$b25-behavioral-equivalence-gate-lineage-reconciliation`
9. `$b25-behavioral-equivalence-gate-security-policy`
10. `$b25-behavioral-equivalence-gate-human-approval`
11. `$b25-behavioral-equivalence-gate-observability-economics`
12. `$b25-behavioral-equivalence-gate-corpus-benchmark`
13. `$b25-behavioral-equivalence-gate-failure-recovery`
14. `$b25-behavioral-equivalence-gate-integration-api`
15. `$b25-behavioral-equivalence-gate-lifecycle-recertification`
16. `$b25-behavioral-equivalence-gate-certification-gate`

## Shared Architecture

```text
Versioned Input + Certificate
→ Discovery / Planning
→ Deterministic Core + Approved Adapters
→ Durable Workflow / Isolated Runner
→ Reconciliation / Independent Verification
→ Evidence Graph
→ Human Gate where required
→ Conservative Certificate
```

## Shared Contracts

- `CapabilityPackage`
- `EvidenceRef`
- `WorkflowRun`
- `ApprovalDecision`
- `MetricSnapshot`
- `CertificationDecision`
- `LifecycleRecord`

## Global Invariants

- Evidence before claim; execution before success state.
- Unknown、Unsupported、Opaque 和 Inconclusive 不得被静默抹除。
- Agent 只能提出 Patch/Decision Proposal，不能自批、自证或直接发布。
- 所有 Provider/Tool/Model/Rule 必须锁定版本和权限。
- 所有不可逆动作必须有批准、预演、回退和副作用收据。
- 任何认证都绑定精确 Scope、Snapshot、Digest、版本、Policy 和有效期。

## Certification Gate

Batch Gate 至少检查：Schema、输入证书、真实执行、P0 测试、Critical P1、Holdout/Representative Corpus、Security Negative Tests、Rollback/Recovery、Evidence Completeness、Human Approval、Unknown/Exception Register 和 Certificate Invalidation。

## Definition of Done

全部子 Skill 结构完整并通过静态校验；真正的 `certified` 状态只能在目标仓库、工具链、Provider 和运行环境执行其 Required Tests 后获得。此技能包自身的静态 PASS 不代表产品实现已完成。
