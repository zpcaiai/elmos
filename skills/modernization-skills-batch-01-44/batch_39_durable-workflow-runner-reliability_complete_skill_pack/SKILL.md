---
name: batch-39-durable-workflow-runner-reliability
description: "Implement the complete Batch 39 skill system for Durable Workflow, Runner Fleet and Provider Reliability."
version: 1.0.0
status: implementation-ready
---

# Batch 39: Durable Workflow, Runner Fleet and Provider Reliability

## Mission

收敛所有长任务到统一 Durable Workflow，建设 Runner 身份、租约、隔离、离线恢复、日志制品流、容量、故障转移和 Provider 可靠性认证。

## Upstream Contract

本 Batch 必须消费 Batch 38 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Workflow Definition/History
- Task/Step/Compensation
- Lease/Fencing/Idempotency
- Checkpoint/Resume/Cancel
- Scheduler/Queue
- Private Runner Identity
- Container/MicroVM Sandbox
- Offline/Disconnected
- Artifact/Log Streaming
- Fleet Capacity
- Provider Failover
- DR/Recovery
- Reliability Gate

## Skill Inventory

1. `$b39-durable-workflow-runner-reliability-orchestrator`
2. `$b39-durable-workflow-runner-reliability-domain-model`
3. `$b39-durable-workflow-runner-reliability-discovery-inventory`
4. `$b39-durable-workflow-runner-reliability-capability-planning`
5. `$b39-durable-workflow-runner-reliability-deterministic-engine`
6. `$b39-durable-workflow-runner-reliability-adapter-provider`
7. `$b39-durable-workflow-runner-reliability-workflow-runtime`
8. `$b39-durable-workflow-runner-reliability-lineage-reconciliation`
9. `$b39-durable-workflow-runner-reliability-security-policy`
10. `$b39-durable-workflow-runner-reliability-human-approval`
11. `$b39-durable-workflow-runner-reliability-observability-economics`
12. `$b39-durable-workflow-runner-reliability-corpus-benchmark`
13. `$b39-durable-workflow-runner-reliability-failure-recovery`
14. `$b39-durable-workflow-runner-reliability-integration-api`
15. `$b39-durable-workflow-runner-reliability-lifecycle-recertification`
16. `$b39-durable-workflow-runner-reliability-certification-gate`

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
