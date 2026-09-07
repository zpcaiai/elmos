---
name: batch-20-skill-sdk-runtime-registry
description: "Implement the complete Batch 20 skill system for Skill SDK, Runtime, Registry and Marketplace Productization."
version: 1.0.0
status: implementation-ready
---

# Batch 20: Skill SDK, Runtime, Registry and Marketplace Productization

## Mission

把所有迁移能力封装为有输入输出 Schema、权限、依赖、签名、版本、运行时、安装升级回滚、CLI/API/IDE/Web 和 Marketplace 治理的产品化 Skill。

## Upstream Contract

本 Batch 必须消费 Batch 19 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Skill Manifest/Input/Output Schema
- Capability Registry
- Multi-language Skill SDK
- Skill Runtime
- Plugin Runtime
- Dependency Resolver/Lockfile
- Package Format
- Permission/Sandbox/Secret/Effect
- Install/Upgrade/Rollback/Uninstall
- CLI/API/IDE/Web
- Registry/Marketplace
- Metering/License/Billing
- SC1–SC5

## Skill Inventory

1. `$b20-skill-sdk-runtime-registry-orchestrator`
2. `$b20-skill-sdk-runtime-registry-domain-model`
3. `$b20-skill-sdk-runtime-registry-discovery-inventory`
4. `$b20-skill-sdk-runtime-registry-capability-planning`
5. `$b20-skill-sdk-runtime-registry-deterministic-engine`
6. `$b20-skill-sdk-runtime-registry-adapter-provider`
7. `$b20-skill-sdk-runtime-registry-workflow-runtime`
8. `$b20-skill-sdk-runtime-registry-lineage-reconciliation`
9. `$b20-skill-sdk-runtime-registry-security-policy`
10. `$b20-skill-sdk-runtime-registry-human-approval`
11. `$b20-skill-sdk-runtime-registry-observability-economics`
12. `$b20-skill-sdk-runtime-registry-corpus-benchmark`
13. `$b20-skill-sdk-runtime-registry-failure-recovery`
14. `$b20-skill-sdk-runtime-registry-integration-api`
15. `$b20-skill-sdk-runtime-registry-lifecycle-recertification`
16. `$b20-skill-sdk-runtime-registry-certification-gate`

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
