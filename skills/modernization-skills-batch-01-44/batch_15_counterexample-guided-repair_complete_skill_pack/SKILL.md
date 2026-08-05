---
name: batch-15-counterexample-guided-repair
description: "Implement the complete Batch 15 skill system for Counterexample-Guided Repair and Self-Evolving Validation."
version: 1.0.0
status: implementation-ready
---

# Batch 15: Counterexample-Guided Repair and Self-Evolving Validation

## Mission

将测试失败、差分、模糊、模型检测和证明反例标准化、最小化并定位根因，生成受约束修复候选，并把重复成功模式沉淀为可认证规则。

## Upstream Contract

本 Batch 必须消费 Batch 14 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Unified Counterexample IR
- Reproduction
- Minimization
- Root-cause Localization
- Repair Obligation
- Patch/Rule Synthesis
- Proof Repair
- Test/Oracle Strengthening
- Mutation/Fuzz Strengthening
- Candidate Arena
- Verification Knowledge Graph
- CR1–CR5

## Skill Inventory

1. `$b15-counterexample-guided-repair-orchestrator`
2. `$b15-counterexample-guided-repair-domain-model`
3. `$b15-counterexample-guided-repair-discovery-inventory`
4. `$b15-counterexample-guided-repair-capability-planning`
5. `$b15-counterexample-guided-repair-deterministic-engine`
6. `$b15-counterexample-guided-repair-adapter-provider`
7. `$b15-counterexample-guided-repair-workflow-runtime`
8. `$b15-counterexample-guided-repair-lineage-reconciliation`
9. `$b15-counterexample-guided-repair-security-policy`
10. `$b15-counterexample-guided-repair-human-approval`
11. `$b15-counterexample-guided-repair-observability-economics`
12. `$b15-counterexample-guided-repair-corpus-benchmark`
13. `$b15-counterexample-guided-repair-failure-recovery`
14. `$b15-counterexample-guided-repair-integration-api`
15. `$b15-counterexample-guided-repair-lifecycle-recertification`
16. `$b15-counterexample-guided-repair-certification-gate`

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
