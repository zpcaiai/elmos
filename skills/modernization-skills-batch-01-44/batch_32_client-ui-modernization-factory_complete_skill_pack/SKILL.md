---
name: batch-32-client-ui-modernization-factory
description: "Implement the complete Batch 32 skill system for Client, UI, Desktop and Mobile Modernization Factory."
version: 1.0.0
status: implementation-ready
---

# Batch 32: Client, UI, Desktop and Mobile Modernization Factory

## Mission

建立 Canonical UI/Interaction IR 和真实用户旅程，迁移组件、模板、状态、表单、路由、API 缓存、身份权限、设计系统、可访问性、桌面与移动能力。

## Upstream Contract

本 Batch 必须消费 Batch 31 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Client Estate Discovery
- Canonical UI IR
- Component/Template/View
- State/Form/Route
- API/Data/Cache
- Identity/Permission/Flags
- Design Tokens/Theme
- Visual/A11y/I18n/SEO
- SSR/Hydration
- Desktop/Web/Cross-platform
- Mobile/Device/Offline
- Client Certification

## Skill Inventory

1. `$b32-client-ui-modernization-factory-orchestrator`
2. `$b32-client-ui-modernization-factory-domain-model`
3. `$b32-client-ui-modernization-factory-discovery-inventory`
4. `$b32-client-ui-modernization-factory-capability-planning`
5. `$b32-client-ui-modernization-factory-deterministic-engine`
6. `$b32-client-ui-modernization-factory-adapter-provider`
7. `$b32-client-ui-modernization-factory-workflow-runtime`
8. `$b32-client-ui-modernization-factory-lineage-reconciliation`
9. `$b32-client-ui-modernization-factory-security-policy`
10. `$b32-client-ui-modernization-factory-human-approval`
11. `$b32-client-ui-modernization-factory-observability-economics`
12. `$b32-client-ui-modernization-factory-corpus-benchmark`
13. `$b32-client-ui-modernization-factory-failure-recovery`
14. `$b32-client-ui-modernization-factory-integration-api`
15. `$b32-client-ui-modernization-factory-lifecycle-recertification`
16. `$b32-client-ui-modernization-factory-certification-gate`

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
