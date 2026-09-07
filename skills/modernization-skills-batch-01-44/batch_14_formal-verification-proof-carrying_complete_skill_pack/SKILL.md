---
name: batch-14-formal-verification-proof-carrying
description: "Implement the complete Batch 14 skill system for Formal Verification and Proof-Carrying Migration."
version: 1.0.0
status: implementation-ready
---

# Batch 14: Formal Verification and Proof-Carrying Migration

## Mission

把 Formal IR、SMT、符号执行、模型检测、精化关系和 Lean Kernel 验证接入迁移证据链，生成与精确代码和假设绑定的 Proof-Carrying Migration。

## Upstream Contract

本 Batch 必须消费 Batch 13 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Formal IR
- Operational/Trace/State-machine Semantics
- Temporal/Concurrency/Memory Models
- SMT Encoder 与 Solver Replay
- Symbolic/Concolic Execution
- Model Checking
- Refinement/Simulation
- Lean Specification Generator
- Proof Provider Adapter
- Lean Kernel Verification
- Proof-to-Code Binding
- F1–F5

## Skill Inventory

1. `$b14-formal-verification-proof-carrying-orchestrator`
2. `$b14-formal-verification-proof-carrying-domain-model`
3. `$b14-formal-verification-proof-carrying-discovery-inventory`
4. `$b14-formal-verification-proof-carrying-capability-planning`
5. `$b14-formal-verification-proof-carrying-deterministic-engine`
6. `$b14-formal-verification-proof-carrying-adapter-provider`
7. `$b14-formal-verification-proof-carrying-workflow-runtime`
8. `$b14-formal-verification-proof-carrying-lineage-reconciliation`
9. `$b14-formal-verification-proof-carrying-security-policy`
10. `$b14-formal-verification-proof-carrying-human-approval`
11. `$b14-formal-verification-proof-carrying-observability-economics`
12. `$b14-formal-verification-proof-carrying-corpus-benchmark`
13. `$b14-formal-verification-proof-carrying-failure-recovery`
14. `$b14-formal-verification-proof-carrying-integration-api`
15. `$b14-formal-verification-proof-carrying-lifecycle-recertification`
16. `$b14-formal-verification-proof-carrying-certification-gate`

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
