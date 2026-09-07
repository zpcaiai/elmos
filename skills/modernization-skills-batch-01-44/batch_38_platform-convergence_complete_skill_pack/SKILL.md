---
name: batch-38-platform-convergence
description: "Implement the complete Batch 38 skill system for Canonical CapabilityPackage, Dependency Graph and Platform Convergence."
version: 1.0.0
status: implementation-ready
---

# Batch 38: Canonical CapabilityPackage, Dependency Graph and Platform Convergence

## Mission

统一 Route、Framework、Database、Client、Cloud、Verification、Extension 等 Pack 的父模型、跨 Batch 依赖图、状态、Owner、策略、证据、经济性和 UI/API 生命周期。

## Upstream Contract

本 Batch 必须消费 Batch 37 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- CapabilityPackage Meta-model
- Cross-batch Dependency Graph
- Lifecycle State
- Ownership Model
- Compatibility/Versioning
- Contract Registry
- Policy Binding
- Evidence Binding
- Certification Binding
- Economics
- Unified API
- Unified Console
- Convergence Gate

## Skill Inventory

1. `$b38-platform-convergence-orchestrator`
2. `$b38-platform-convergence-domain-model`
3. `$b38-platform-convergence-discovery-inventory`
4. `$b38-platform-convergence-capability-planning`
5. `$b38-platform-convergence-deterministic-engine`
6. `$b38-platform-convergence-adapter-provider`
7. `$b38-platform-convergence-workflow-runtime`
8. `$b38-platform-convergence-lineage-reconciliation`
9. `$b38-platform-convergence-security-policy`
10. `$b38-platform-convergence-human-approval`
11. `$b38-platform-convergence-observability-economics`
12. `$b38-platform-convergence-corpus-benchmark`
13. `$b38-platform-convergence-failure-recovery`
14. `$b38-platform-convergence-integration-api`
15. `$b38-platform-convergence-lifecycle-recertification`
16. `$b38-platform-convergence-certification-gate`

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
