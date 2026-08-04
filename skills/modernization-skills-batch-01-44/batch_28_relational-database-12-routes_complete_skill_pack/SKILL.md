---
name: batch-28-relational-database-12-routes
description: "Implement the complete Batch 28 skill system for Oracle, SQL Server, MySQL and PostgreSQL 12 Directional Route Packs."
version: 1.0.0
status: implementation-ready
---

# Batch 28: Oracle, SQL Server, MySQL and PostgreSQL 12 Directional Route Packs

## Mission

为 Oracle、SQL Server、MySQL、PostgreSQL 的全部 12 条有向路线建立版本化 Route Pack，覆盖 Schema、SQL、Routine、Data、CDC、Dual Run、性能、切换和回退。

## Upstream Contract

本 Batch 必须消费 Batch 27 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Oracle→PostgreSQL
- PostgreSQL→Oracle
- Oracle→SQL Server
- SQL Server→Oracle
- Oracle→MySQL
- MySQL→Oracle
- SQL Server→PostgreSQL
- PostgreSQL→SQL Server
- SQL Server→MySQL
- MySQL→SQL Server
- MySQL→PostgreSQL
- PostgreSQL→MySQL
- Shared Route Certification

## Skill Inventory

1. `$b28-relational-database-12-routes-orchestrator`
2. `$b28-relational-database-12-routes-domain-model`
3. `$b28-relational-database-12-routes-discovery-inventory`
4. `$b28-relational-database-12-routes-capability-planning`
5. `$b28-relational-database-12-routes-deterministic-engine`
6. `$b28-relational-database-12-routes-adapter-provider`
7. `$b28-relational-database-12-routes-workflow-runtime`
8. `$b28-relational-database-12-routes-lineage-reconciliation`
9. `$b28-relational-database-12-routes-security-policy`
10. `$b28-relational-database-12-routes-human-approval`
11. `$b28-relational-database-12-routes-observability-economics`
12. `$b28-relational-database-12-routes-corpus-benchmark`
13. `$b28-relational-database-12-routes-failure-recovery`
14. `$b28-relational-database-12-routes-integration-api`
15. `$b28-relational-database-12-routes-lifecycle-recertification`
16. `$b28-relational-database-12-routes-certification-gate`

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
