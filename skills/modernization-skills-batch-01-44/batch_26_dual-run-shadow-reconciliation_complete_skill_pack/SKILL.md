---
name: batch-26-dual-run-shadow-reconciliation
description: "Implement the complete Batch 26 skill system for Dual Run, Shadow Execution and State Reconciliation."
version: 1.0.0
status: implementation-ready
---

# Batch 26: Dual Run, Shadow Execution and State Reconciliation

## Mission

建立源目标并行运行、流量捕获与回放、影子执行、副作用隔离、状态和 CDC 对账、分歧定位、Canary 和自动停止回滚闭环。

## Upstream Contract

本 Batch 必须消费 Batch 25 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Traffic Capture/Replay
- Route Matching
- Shadow Execution
- Side-effect Suppression
- Read Comparison
- Write Comparison
- CDC
- State Reconciliation
- Divergence Triage
- Safety Budget
- Canary/Stop
- Dual Run Certificate

## Skill Inventory

1. `$b26-dual-run-shadow-reconciliation-orchestrator`
2. `$b26-dual-run-shadow-reconciliation-domain-model`
3. `$b26-dual-run-shadow-reconciliation-discovery-inventory`
4. `$b26-dual-run-shadow-reconciliation-capability-planning`
5. `$b26-dual-run-shadow-reconciliation-deterministic-engine`
6. `$b26-dual-run-shadow-reconciliation-adapter-provider`
7. `$b26-dual-run-shadow-reconciliation-workflow-runtime`
8. `$b26-dual-run-shadow-reconciliation-lineage-reconciliation`
9. `$b26-dual-run-shadow-reconciliation-security-policy`
10. `$b26-dual-run-shadow-reconciliation-human-approval`
11. `$b26-dual-run-shadow-reconciliation-observability-economics`
12. `$b26-dual-run-shadow-reconciliation-corpus-benchmark`
13. `$b26-dual-run-shadow-reconciliation-failure-recovery`
14. `$b26-dual-run-shadow-reconciliation-integration-api`
15. `$b26-dual-run-shadow-reconciliation-lifecycle-recertification`
16. `$b26-dual-run-shadow-reconciliation-certification-gate`

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
