---
name: batch-27-canonical-database-ir-foundation
description: "Implement the complete Batch 27 skill system for Canonical Database IR, Data Migration and Cutover Foundation."
version: 1.0.0
status: implementation-ready
---

# Batch 27: Canonical Database IR, Data Migration and Cutover Foundation

## Mission

建立数据库资产发现、Canonical Database IR、Schema/Query/Routine/Transaction/ORM/Data Movement/CDC/Cutover 的联合语义底座。

## Upstream Contract

本 Batch 必须消费 Batch 26 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Database Estate Discovery
- Canonical Database IR
- Type/Precision/Collation
- Schema/Constraint/Index/Partition
- Query IR
- Routine/Package/Trigger
- Transaction/Isolation/Lock
- ORM Contract
- Bulk Data/Backfill
- CDC/Dual Write
- Cutover/Rollback
- Database Evidence

## Skill Inventory

1. `$b27-canonical-database-ir-foundation-orchestrator`
2. `$b27-canonical-database-ir-foundation-domain-model`
3. `$b27-canonical-database-ir-foundation-discovery-inventory`
4. `$b27-canonical-database-ir-foundation-capability-planning`
5. `$b27-canonical-database-ir-foundation-deterministic-engine`
6. `$b27-canonical-database-ir-foundation-adapter-provider`
7. `$b27-canonical-database-ir-foundation-workflow-runtime`
8. `$b27-canonical-database-ir-foundation-lineage-reconciliation`
9. `$b27-canonical-database-ir-foundation-security-policy`
10. `$b27-canonical-database-ir-foundation-human-approval`
11. `$b27-canonical-database-ir-foundation-observability-economics`
12. `$b27-canonical-database-ir-foundation-corpus-benchmark`
13. `$b27-canonical-database-ir-foundation-failure-recovery`
14. `$b27-canonical-database-ir-foundation-integration-api`
15. `$b27-canonical-database-ir-foundation-lifecycle-recertification`
16. `$b27-canonical-database-ir-foundation-certification-gate`

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
