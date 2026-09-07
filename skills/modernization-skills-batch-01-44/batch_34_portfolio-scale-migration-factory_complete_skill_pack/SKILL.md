---
name: batch-34-portfolio-scale-migration-factory
description: "Implement the complete Batch 34 skill system for Portfolio-Scale Multi-Repository Migration Factory."
version: 1.0.0
status: implementation-ready
---

# Batch 34: Portfolio-Scale Multi-Repository Migration Factory

## Mission

把单仓库迁移扩展到千仓库、百万行、多个团队和 Runner Fleet，管理 Capability Graph、依赖波次、配额、缓存、批量 PR、灾备和组合级认证。

## Upstream Contract

本 Batch 必须消费 Batch 33 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Portfolio Inventory
- Capability/Dependency Graph
- Multi-repo Work Units
- Migration Waves
- Fleet Scheduling
- Artifact/Dependency Cache
- Tenant Isolation
- Quota/Budget
- Bulk PR/Release Train
- Portfolio Dashboard
- DR/Recovery
- Portfolio Certification

## Skill Inventory

1. `$b34-portfolio-scale-migration-factory-orchestrator`
2. `$b34-portfolio-scale-migration-factory-domain-model`
3. `$b34-portfolio-scale-migration-factory-discovery-inventory`
4. `$b34-portfolio-scale-migration-factory-capability-planning`
5. `$b34-portfolio-scale-migration-factory-deterministic-engine`
6. `$b34-portfolio-scale-migration-factory-adapter-provider`
7. `$b34-portfolio-scale-migration-factory-workflow-runtime`
8. `$b34-portfolio-scale-migration-factory-lineage-reconciliation`
9. `$b34-portfolio-scale-migration-factory-security-policy`
10. `$b34-portfolio-scale-migration-factory-human-approval`
11. `$b34-portfolio-scale-migration-factory-observability-economics`
12. `$b34-portfolio-scale-migration-factory-corpus-benchmark`
13. `$b34-portfolio-scale-migration-factory-failure-recovery`
14. `$b34-portfolio-scale-migration-factory-integration-api`
15. `$b34-portfolio-scale-migration-factory-lifecycle-recertification`
16. `$b34-portfolio-scale-migration-factory-certification-gate`

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
