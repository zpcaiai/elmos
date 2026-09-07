---
name: batch-18-complete-project-generation
description: "Implement the complete Batch 18 skill system for Complete Project Generation Standard."
version: 1.0.0
status: implementation-ready
---

# Batch 18: Complete Project Generation Standard

## Mission

将目标代码扩展为可构建、可运行、可测试、可部署、可观测、可运维的完整项目，并通过 Complete Project Manifest 和 Completeness Score 防止只生成源码。

## Upstream Contract

本 Batch 必须消费 Batch 17 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Complete Project Manifest
- Repository Template Registry
- 10-language Project Generators
- Build/Config/Dependency Closure
- Database/Messaging/Gateway/Mesh
- CI/CD
- Unit/Integration/Journey Tests
- Fuzz/Mutation/Formal Projects
- Observability/Security
- Runbooks/Docs
- One-click Lifecycle
- CP1–CP5

## Skill Inventory

1. `$b18-complete-project-generation-orchestrator`
2. `$b18-complete-project-generation-domain-model`
3. `$b18-complete-project-generation-discovery-inventory`
4. `$b18-complete-project-generation-capability-planning`
5. `$b18-complete-project-generation-deterministic-engine`
6. `$b18-complete-project-generation-adapter-provider`
7. `$b18-complete-project-generation-workflow-runtime`
8. `$b18-complete-project-generation-lineage-reconciliation`
9. `$b18-complete-project-generation-security-policy`
10. `$b18-complete-project-generation-human-approval`
11. `$b18-complete-project-generation-observability-economics`
12. `$b18-complete-project-generation-corpus-benchmark`
13. `$b18-complete-project-generation-failure-recovery`
14. `$b18-complete-project-generation-integration-api`
15. `$b18-complete-project-generation-lifecycle-recertification`
16. `$b18-complete-project-generation-certification-gate`

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
