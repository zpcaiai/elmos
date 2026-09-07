---
name: batch-41-release-progressive-delivery
description: "Implement the complete Batch 41 skill system for Release Engineering, Progressive Delivery and Automated Rollback."
version: 1.0.0
status: implementation-ready
---

# Batch 41: Release Engineering, Progressive Delivery and Automated Rollback

## Mission

把签名制品、CI 门禁、环境提升、Feature Flag、Canary、Blue/Green、渐进式交付、数据库切换和自动回滚汇聚为可审计发布列车。

## Upstream Contract

本 Batch 必须消费 Batch 40 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Release Train
- Changeset/Version
- Build Provenance
- CI Quality Gates
- Environment Promotion
- Feature Flag
- Canary
- Blue/Green
- Progressive Delivery
- Automated Rollback
- Database/Data Cutover
- Approval/Change Control
- Release Evidence
- Customer Communication
- Release Gate

## Skill Inventory

1. `$b41-release-progressive-delivery-orchestrator`
2. `$b41-release-progressive-delivery-domain-model`
3. `$b41-release-progressive-delivery-discovery-inventory`
4. `$b41-release-progressive-delivery-capability-planning`
5. `$b41-release-progressive-delivery-deterministic-engine`
6. `$b41-release-progressive-delivery-adapter-provider`
7. `$b41-release-progressive-delivery-workflow-runtime`
8. `$b41-release-progressive-delivery-lineage-reconciliation`
9. `$b41-release-progressive-delivery-security-policy`
10. `$b41-release-progressive-delivery-human-approval`
11. `$b41-release-progressive-delivery-observability-economics`
12. `$b41-release-progressive-delivery-corpus-benchmark`
13. `$b41-release-progressive-delivery-failure-recovery`
14. `$b41-release-progressive-delivery-integration-api`
15. `$b41-release-progressive-delivery-lifecycle-recertification`
16. `$b41-release-progressive-delivery-certification-gate`

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
