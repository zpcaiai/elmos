---
name: batch-44-unified-production-release-gate
description: "Implement the complete Batch 44 skill system for Unified Production Release Gate and Continuous Recertification."
version: 1.0.0
status: implementation-ready
---

# Batch 44: Unified Production Release Gate and Continuous Recertification

## Mission

把需求、语义、代码、数据库、测试、性能、安全、韧性、运行指标、发布、回滚、客户支持和持续重新认证汇聚为唯一 Production Release Gate 与 Closure Certificate。

## Upstream Contract

本 Batch 必须消费 Batch 43 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Production Readiness Checklist
- Certificate Aggregation
- Business Acceptance
- Customer Acceptance
- Support Readiness
- Operational Dashboard
- Release Decision
- Post-release Verification
- Continuous Security Recertification
- Continuous Performance Recertification
- Continuous Reliability Recertification
- Production Closure Certificate
- Governance/Transparency
- Final Gate

## Skill Inventory

1. `$b44-unified-production-release-gate-orchestrator`
2. `$b44-unified-production-release-gate-domain-model`
3. `$b44-unified-production-release-gate-discovery-inventory`
4. `$b44-unified-production-release-gate-capability-planning`
5. `$b44-unified-production-release-gate-deterministic-engine`
6. `$b44-unified-production-release-gate-adapter-provider`
7. `$b44-unified-production-release-gate-workflow-runtime`
8. `$b44-unified-production-release-gate-lineage-reconciliation`
9. `$b44-unified-production-release-gate-security-policy`
10. `$b44-unified-production-release-gate-human-approval`
11. `$b44-unified-production-release-gate-observability-economics`
12. `$b44-unified-production-release-gate-corpus-benchmark`
13. `$b44-unified-production-release-gate-failure-recovery`
14. `$b44-unified-production-release-gate-integration-api`
15. `$b44-unified-production-release-gate-lifecycle-recertification`
16. `$b44-unified-production-release-gate-certification-gate`

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
