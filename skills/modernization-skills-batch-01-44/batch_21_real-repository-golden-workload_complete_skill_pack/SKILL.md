---
name: batch-21-real-repository-golden-workload
description: "Implement the complete Batch 21 skill system for Real Repository Slice and Golden Workload Factory."
version: 1.0.0
status: implementation-ready
---

# Batch 21: Real Repository Slice and Golden Workload Factory

## Mission

从真实企业仓库中选择可代表业务、技术和风险的纵向切片，建立不可变 Snapshot、源基线、目标验收、Golden/Holdout Workload 与客户数据保护边界。

## Upstream Contract

本 Batch 必须消费 Batch 20 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Repository Qualification
- Vertical Slice Selection
- Golden Workload
- Independent Holdout
- Source Build Baseline
- Source Behavior Baseline
- Representative Data
- Data Redaction
- Workload Fingerprint
- Snapshot Integrity
- Customer Approval
- Corpus Refresh

## Skill Inventory

1. `$b21-real-repository-golden-workload-orchestrator`
2. `$b21-real-repository-golden-workload-domain-model`
3. `$b21-real-repository-golden-workload-discovery-inventory`
4. `$b21-real-repository-golden-workload-capability-planning`
5. `$b21-real-repository-golden-workload-deterministic-engine`
6. `$b21-real-repository-golden-workload-adapter-provider`
7. `$b21-real-repository-golden-workload-workflow-runtime`
8. `$b21-real-repository-golden-workload-lineage-reconciliation`
9. `$b21-real-repository-golden-workload-security-policy`
10. `$b21-real-repository-golden-workload-human-approval`
11. `$b21-real-repository-golden-workload-observability-economics`
12. `$b21-real-repository-golden-workload-corpus-benchmark`
13. `$b21-real-repository-golden-workload-failure-recovery`
14. `$b21-real-repository-golden-workload-integration-api`
15. `$b21-real-repository-golden-workload-lifecycle-recertification`
16. `$b21-real-repository-golden-workload-certification-gate`

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
