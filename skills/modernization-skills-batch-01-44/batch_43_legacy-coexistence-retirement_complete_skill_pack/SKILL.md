---
name: batch-43-legacy-coexistence-retirement
description: "Implement the complete Batch 43 skill system for Legacy Coexistence, Cutover, Hypercare and Continuous Modernization."
version: 1.0.0
status: implementation-ready
---

# Batch 43: Legacy Coexistence, Cutover, Hypercare and Continuous Modernization

## Mission

管理 Strangler、旧新路由、共享身份、数据所有权、事件桥、混合版本、切换、Hypercare、回滚、归档、源系统退役和上线后的持续现代化。

## Upstream Contract

本 Batch 必须消费 Batch 42 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Strangler/Facade
- Legacy Routing
- Shared Identity
- Data Ownership
- Event/Protocol Bridge
- Mixed-version Matrix
- Cutover Plan
- Hypercare
- Rollback
- Data Archive
- Decommission
- Source Retirement
- Continuous Modernization
- Incident Learning

## Skill Inventory

1. `$b43-legacy-coexistence-retirement-orchestrator`
2. `$b43-legacy-coexistence-retirement-domain-model`
3. `$b43-legacy-coexistence-retirement-discovery-inventory`
4. `$b43-legacy-coexistence-retirement-capability-planning`
5. `$b43-legacy-coexistence-retirement-deterministic-engine`
6. `$b43-legacy-coexistence-retirement-adapter-provider`
7. `$b43-legacy-coexistence-retirement-workflow-runtime`
8. `$b43-legacy-coexistence-retirement-lineage-reconciliation`
9. `$b43-legacy-coexistence-retirement-security-policy`
10. `$b43-legacy-coexistence-retirement-human-approval`
11. `$b43-legacy-coexistence-retirement-observability-economics`
12. `$b43-legacy-coexistence-retirement-corpus-benchmark`
13. `$b43-legacy-coexistence-retirement-failure-recovery`
14. `$b43-legacy-coexistence-retirement-integration-api`
15. `$b43-legacy-coexistence-retirement-lifecycle-recertification`
16. `$b43-legacy-coexistence-retirement-certification-gate`

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
