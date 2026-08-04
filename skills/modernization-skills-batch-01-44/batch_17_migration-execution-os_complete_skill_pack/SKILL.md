---
name: batch-17-migration-execution-os
description: "Implement the complete Batch 17 skill system for Migration Execution Operating System."
version: 1.0.0
status: implementation-ready
---

# Batch 17: Migration Execution Operating System

## Mission

提供统一 Durable Workflow、任务图、租约、检查点、暂停恢复取消、补偿、人工任务、模型与工具路由、预算和多仓库多波次执行内核。

## Upstream Contract

本 Batch 必须消费 Batch 16 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Task Graph Runtime
- Durable Event History
- Checkpoint/Pause/Resume/Cancel
- Worker Lease/Fencing
- Scheduler/Queues
- Model Router
- Tool Runtime
- Sandbox
- Human Approval
- Retry/Idempotency
- Side-effect Ledger
- Cost/Token Governance
- Multi-repo/Multi-wave
- MX1–MX5

## Skill Inventory

1. `$b17-migration-execution-os-orchestrator`
2. `$b17-migration-execution-os-domain-model`
3. `$b17-migration-execution-os-discovery-inventory`
4. `$b17-migration-execution-os-capability-planning`
5. `$b17-migration-execution-os-deterministic-engine`
6. `$b17-migration-execution-os-adapter-provider`
7. `$b17-migration-execution-os-workflow-runtime`
8. `$b17-migration-execution-os-lineage-reconciliation`
9. `$b17-migration-execution-os-security-policy`
10. `$b17-migration-execution-os-human-approval`
11. `$b17-migration-execution-os-observability-economics`
12. `$b17-migration-execution-os-corpus-benchmark`
13. `$b17-migration-execution-os-failure-recovery`
14. `$b17-migration-execution-os-integration-api`
15. `$b17-migration-execution-os-lifecycle-recertification`
16. `$b17-migration-execution-os-certification-gate`

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
