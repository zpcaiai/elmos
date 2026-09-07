---
name: batch-22-semantic-recovery-hardening
description: "Implement the complete Batch 22 skill system for Semantic Recovery Hardening and Runtime-Enriched CSIR."
version: 1.0.0
status: implementation-ready
---

# Batch 22: Semantic Recovery Hardening and Runtime-Enriched CSIR

## Mission

强化编译器语义、二进制、运行 Trace、反射、动态调用、宏、生成代码、SQL、并发和副作用恢复，形成可量化的 Runtime-enriched CSIR。

## Upstream Contract

本 Batch 必须消费 Batch 21 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Compiler-backed Frontends
- Binary/Bytecode Correlation
- Runtime Trace Correlation
- Reflection/Dynamic Dispatch
- Macro/Metaprogramming
- Generated Code Provenance
- SQL/Dynamic SQL
- Control/Data Flow
- Effects/Exceptions
- Concurrency/Resource
- Coverage/Unknowns
- Semantic Recertification

## Skill Inventory

1. `$b22-semantic-recovery-hardening-orchestrator`
2. `$b22-semantic-recovery-hardening-domain-model`
3. `$b22-semantic-recovery-hardening-discovery-inventory`
4. `$b22-semantic-recovery-hardening-capability-planning`
5. `$b22-semantic-recovery-hardening-deterministic-engine`
6. `$b22-semantic-recovery-hardening-adapter-provider`
7. `$b22-semantic-recovery-hardening-workflow-runtime`
8. `$b22-semantic-recovery-hardening-lineage-reconciliation`
9. `$b22-semantic-recovery-hardening-security-policy`
10. `$b22-semantic-recovery-hardening-human-approval`
11. `$b22-semantic-recovery-hardening-observability-economics`
12. `$b22-semantic-recovery-hardening-corpus-benchmark`
13. `$b22-semantic-recovery-hardening-failure-recovery`
14. `$b22-semantic-recovery-hardening-integration-api`
15. `$b22-semantic-recovery-hardening-lifecycle-recertification`
16. `$b22-semantic-recovery-hardening-certification-gate`

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
