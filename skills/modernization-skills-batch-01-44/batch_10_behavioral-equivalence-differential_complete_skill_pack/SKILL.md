---
name: batch-10-behavioral-equivalence-differential
description: "Implement the complete Batch 10 skill system for Behavioral Equivalence, Golden Master and Differential Validation."
version: 1.0.0
status: implementation-ready
---

# Batch 10: Behavioral Equivalence, Golden Master and Differential Validation

## Mission

建立独立 Oracle、确定性 Scenario Runtime、状态和副作用差分、Golden Master、属性测试与差分模糊测试，为行为等价提供可审计证据。

## Upstream Contract

本 Batch 必须消费 Batch 09 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Scenario Runtime
- Deterministic Environment
- HTTP/API Diff
- Database State Diff
- Message/Event Diff
- File/Object Diff
- External Effect Diff
- Exception/Error Contract
- Golden Master
- Property-based Testing
- Differential Fuzzing
- Oracle Registry 与容差治理

## Skill Inventory

1. `$b10-behavioral-equivalence-differential-orchestrator`
2. `$b10-behavioral-equivalence-differential-domain-model`
3. `$b10-behavioral-equivalence-differential-discovery-inventory`
4. `$b10-behavioral-equivalence-differential-capability-planning`
5. `$b10-behavioral-equivalence-differential-deterministic-engine`
6. `$b10-behavioral-equivalence-differential-adapter-provider`
7. `$b10-behavioral-equivalence-differential-workflow-runtime`
8. `$b10-behavioral-equivalence-differential-lineage-reconciliation`
9. `$b10-behavioral-equivalence-differential-security-policy`
10. `$b10-behavioral-equivalence-differential-human-approval`
11. `$b10-behavioral-equivalence-differential-observability-economics`
12. `$b10-behavioral-equivalence-differential-corpus-benchmark`
13. `$b10-behavioral-equivalence-differential-failure-recovery`
14. `$b10-behavioral-equivalence-differential-integration-api`
15. `$b10-behavioral-equivalence-differential-lifecycle-recertification`
16. `$b10-behavioral-equivalence-differential-certification-gate`

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
