---
name: batch-35-advanced-verification-factory
description: "Implement the complete Batch 35 skill system for Advanced Verification, Fuzzing, Mutation and Formal Assurance Factory."
version: 1.0.0
status: implementation-ready
---

# Batch 35: Advanced Verification, Fuzzing, Mutation and Formal Assurance Factory

## Mission

将属性测试、Fuzz、Mutation、符号/Concolic、模型检测、SMT、并发探索、证明和反例管理产品化为 Verification Pack 与保守认证 Gate。

## Upstream Contract

本 Batch 必须消费 Batch 34 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Property Engine
- Fuzzing
- Mutation Testing
- Symbolic Execution
- Concolic Execution
- Model Checking
- SMT
- Concurrency Explorer
- Oracle Registry
- Proof Adapter
- Coverage/Mutation Score
- Holdout/Representative Workload
- Counterexample
- Assurance Gate

## Skill Inventory

1. `$b35-advanced-verification-factory-orchestrator`
2. `$b35-advanced-verification-factory-domain-model`
3. `$b35-advanced-verification-factory-discovery-inventory`
4. `$b35-advanced-verification-factory-capability-planning`
5. `$b35-advanced-verification-factory-deterministic-engine`
6. `$b35-advanced-verification-factory-adapter-provider`
7. `$b35-advanced-verification-factory-workflow-runtime`
8. `$b35-advanced-verification-factory-lineage-reconciliation`
9. `$b35-advanced-verification-factory-security-policy`
10. `$b35-advanced-verification-factory-human-approval`
11. `$b35-advanced-verification-factory-observability-economics`
12. `$b35-advanced-verification-factory-corpus-benchmark`
13. `$b35-advanced-verification-factory-failure-recovery`
14. `$b35-advanced-verification-factory-integration-api`
15. `$b35-advanced-verification-factory-lifecycle-recertification`
16. `$b35-advanced-verification-factory-certification-gate`

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
