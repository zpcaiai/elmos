---
name: batch-36-developer-experience-integration
description: "Implement the complete Batch 36 skill system for Developer Experience, CLI, IDE and SCM Integration."
version: 1.0.0
status: implementation-ready
---

# Batch 36: Developer Experience, CLI, IDE and SCM Integration

## Mission

把规划、预览、导航、诊断、审批、执行和证据接入 CLI、VS Code、Visual Studio、IntelliJ 和主要 SCM，同时支持离线与最小权限。

## Upstream Contract

本 Batch 必须消费 Batch 35 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- CLI
- VS Code
- Visual Studio
- IntelliJ
- GitHub/GitLab/Azure DevOps/Bitbucket
- Source Navigation
- Diagnostics/Quick Fix
- Plan/Patch Review
- Approval
- Artifact/Evidence View
- Offline Workflow
- Telemetry/Privacy
- DX Certification

## Skill Inventory

1. `$b36-developer-experience-integration-orchestrator`
2. `$b36-developer-experience-integration-domain-model`
3. `$b36-developer-experience-integration-discovery-inventory`
4. `$b36-developer-experience-integration-capability-planning`
5. `$b36-developer-experience-integration-deterministic-engine`
6. `$b36-developer-experience-integration-adapter-provider`
7. `$b36-developer-experience-integration-workflow-runtime`
8. `$b36-developer-experience-integration-lineage-reconciliation`
9. `$b36-developer-experience-integration-security-policy`
10. `$b36-developer-experience-integration-human-approval`
11. `$b36-developer-experience-integration-observability-economics`
12. `$b36-developer-experience-integration-corpus-benchmark`
13. `$b36-developer-experience-integration-failure-recovery`
14. `$b36-developer-experience-integration-integration-api`
15. `$b36-developer-experience-integration-lifecycle-recertification`
16. `$b36-developer-experience-integration-certification-gate`

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
