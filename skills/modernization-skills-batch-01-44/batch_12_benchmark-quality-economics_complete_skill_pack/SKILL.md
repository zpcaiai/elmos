---
name: batch-12-benchmark-quality-economics
description: "Implement the complete Batch 12 skill system for Benchmark, Quality Scoring and Migration Economics."
version: 1.0.0
status: implementation-ready
---

# Batch 12: Benchmark, Quality Scoring and Migration Economics

## Mission

建立可重复 Benchmark、质量评分、成本与人工工作量模型，使用明确分母和置信区间衡量迁移路线，而不是用生成代码行数替代质量。

## Upstream Contract

本 Batch 必须消费 Batch 11 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Compile/Build Rate
- Test Pass Rate
- API Compatibility
- Behavioral Equivalence
- Coverage 与 Translation Coverage
- Maintainability
- Target Idiomaticity
- Manual Effort
- Token/Compute Cost
- Verified Workload Cost
- Calibration/Confidence
- Benchmark Governance

## Skill Inventory

1. `$b12-benchmark-quality-economics-orchestrator`
2. `$b12-benchmark-quality-economics-domain-model`
3. `$b12-benchmark-quality-economics-discovery-inventory`
4. `$b12-benchmark-quality-economics-capability-planning`
5. `$b12-benchmark-quality-economics-deterministic-engine`
6. `$b12-benchmark-quality-economics-adapter-provider`
7. `$b12-benchmark-quality-economics-workflow-runtime`
8. `$b12-benchmark-quality-economics-lineage-reconciliation`
9. `$b12-benchmark-quality-economics-security-policy`
10. `$b12-benchmark-quality-economics-human-approval`
11. `$b12-benchmark-quality-economics-observability-economics`
12. `$b12-benchmark-quality-economics-corpus-benchmark`
13. `$b12-benchmark-quality-economics-failure-recovery`
14. `$b12-benchmark-quality-economics-integration-api`
15. `$b12-benchmark-quality-economics-lifecycle-recertification`
16. `$b12-benchmark-quality-economics-certification-gate`

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
