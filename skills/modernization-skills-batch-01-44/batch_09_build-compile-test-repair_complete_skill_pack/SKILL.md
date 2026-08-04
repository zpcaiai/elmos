---
name: batch-09-build-compile-test-repair
description: "Implement the complete Batch 09 skill system for Build, Compile, Test Repair and Bounded Fix Loop."
version: 1.0.0
status: implementation-ready
---

# Batch 09: Build, Compile, Test Repair and Bounded Fix Loop

## Mission

在锁定工具链和隔离环境中复现构建、解析诊断、执行确定性修复和受限 Agent 修复，形成有界、可回滚的 Build/Test 闭环。

## Upstream Contract

本 Batch 必须消费 Batch 08 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Maven/Gradle
- dotnet
- npm/pnpm/yarn
- pip/uv/Poetry
- CMake/Ninja
- Go/Cargo/Dart 工具链
- 诊断标准化
- 错误分类与根因
- 确定性最小 Patch
- Clean-room Build
- 回归与测试完整性
- Fixpoint/回滚/迭代上限

## Skill Inventory

1. `$b09-build-compile-test-repair-orchestrator`
2. `$b09-build-compile-test-repair-domain-model`
3. `$b09-build-compile-test-repair-discovery-inventory`
4. `$b09-build-compile-test-repair-capability-planning`
5. `$b09-build-compile-test-repair-deterministic-engine`
6. `$b09-build-compile-test-repair-adapter-provider`
7. `$b09-build-compile-test-repair-workflow-runtime`
8. `$b09-build-compile-test-repair-lineage-reconciliation`
9. `$b09-build-compile-test-repair-security-policy`
10. `$b09-build-compile-test-repair-human-approval`
11. `$b09-build-compile-test-repair-observability-economics`
12. `$b09-build-compile-test-repair-corpus-benchmark`
13. `$b09-build-compile-test-repair-failure-recovery`
14. `$b09-build-compile-test-repair-integration-api`
15. `$b09-build-compile-test-repair-lifecycle-recertification`
16. `$b09-build-compile-test-repair-certification-gate`

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
