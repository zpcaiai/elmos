---
name: batch-37-extension-marketplace-governance
description: "Implement the complete Batch 37 skill system for Extension SDK, Marketplace and Supply-Chain Governance."
version: 1.0.0
status: implementation-ready
---

# Batch 37: Extension SDK, Marketplace and Supply-Chain Governance

## Mission

建立稳定 ABI/API、SDK、Extension Manifest、沙箱与权限、发布者身份、签名/SBOM/Provenance、认证、发布安装升级回滚撤销和商业治理。

## Upstream Contract

本 Batch 必须消费 Batch 36 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Extension ABI/API
- SDKs
- Manifest/Capability
- Sandbox/Permissions
- Publisher Identity
- Signing/SBOM/Provenance
- Security/Compatibility Review
- Publish/Discover
- Install/Activate
- Upgrade/Rollback
- Disable/Uninstall/Revoke
- License/Billing/Revenue Share
- Marketplace Gate

## Skill Inventory

1. `$b37-extension-marketplace-governance-orchestrator`
2. `$b37-extension-marketplace-governance-domain-model`
3. `$b37-extension-marketplace-governance-discovery-inventory`
4. `$b37-extension-marketplace-governance-capability-planning`
5. `$b37-extension-marketplace-governance-deterministic-engine`
6. `$b37-extension-marketplace-governance-adapter-provider`
7. `$b37-extension-marketplace-governance-workflow-runtime`
8. `$b37-extension-marketplace-governance-lineage-reconciliation`
9. `$b37-extension-marketplace-governance-security-policy`
10. `$b37-extension-marketplace-governance-human-approval`
11. `$b37-extension-marketplace-governance-observability-economics`
12. `$b37-extension-marketplace-governance-corpus-benchmark`
13. `$b37-extension-marketplace-governance-failure-recovery`
14. `$b37-extension-marketplace-governance-integration-api`
15. `$b37-extension-marketplace-governance-lifecycle-recertification`
16. `$b37-extension-marketplace-governance-certification-gate`

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
