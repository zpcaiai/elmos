---
name: batch-16-target-architecture-search
description: "Implement the complete Batch 16 skill system for Target Architecture Search and Migration Planning."
version: 1.0.0
status: implementation-ready
---

# Batch 16: Target Architecture Search and Migration Planning

## Mission

从源架构和约束出发搜索语言、框架、数据和部署组合，通过多目标优化、原型和仿真生成 Retain/Rewrite/Wrap/Strangler 决策、迁移波次、ADR 和 Target Blueprint。

## Upstream Contract

本 Batch 必须消费 Batch 15 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Source Architecture Recovery
- Hard/Soft Constraint Registry
- Architecture IR
- Language/Framework/Data/Deployment Search
- Multi-objective Optimization
- Prototype/Simulation
- Retain/Rehost/Refactor/Rewrite
- Wrap/Sidecar/Strangler
- Migration Boundary
- Wave/DAG
- ADR
- AP1–AP5

## Skill Inventory

1. `$b16-target-architecture-search-orchestrator`
2. `$b16-target-architecture-search-domain-model`
3. `$b16-target-architecture-search-discovery-inventory`
4. `$b16-target-architecture-search-capability-planning`
5. `$b16-target-architecture-search-deterministic-engine`
6. `$b16-target-architecture-search-adapter-provider`
7. `$b16-target-architecture-search-workflow-runtime`
8. `$b16-target-architecture-search-lineage-reconciliation`
9. `$b16-target-architecture-search-security-policy`
10. `$b16-target-architecture-search-human-approval`
11. `$b16-target-architecture-search-observability-economics`
12. `$b16-target-architecture-search-corpus-benchmark`
13. `$b16-target-architecture-search-failure-recovery`
14. `$b16-target-architecture-search-integration-api`
15. `$b16-target-architecture-search-lifecycle-recertification`
16. `$b16-target-architecture-search-certification-gate`

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
