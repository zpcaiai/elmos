---
name: batch-24-real-build-test-artifact-lab
description: "Implement the complete Batch 24 skill system for Real Build, Test, Package and Artifact Execution Lab."
version: 1.0.0
status: implementation-ready
---

# Batch 24: Real Build, Test, Package and Artifact Execution Lab

## Mission

在受控工具链和隔离 Runner 中执行真实 Analyze/Compile/Test/Package，保存依赖、日志、制品、签名和可重复性证据，为后续行为与发布认证提供真实 Artifact。

## Upstream Contract

本 Batch 必须消费 Batch 23 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- JDK/Maven/Gradle
- .NET SDK
- Node/TypeScript
- Python
- C/C++
- Go/Rust
- Dart/Flutter
- Clean-room Dependency Restore
- Analyze/Compile/Test
- Package/Artifact
- Reproducible Build
- Signing/Provenance

## Skill Inventory

1. `$b24-real-build-test-artifact-lab-orchestrator`
2. `$b24-real-build-test-artifact-lab-domain-model`
3. `$b24-real-build-test-artifact-lab-discovery-inventory`
4. `$b24-real-build-test-artifact-lab-capability-planning`
5. `$b24-real-build-test-artifact-lab-deterministic-engine`
6. `$b24-real-build-test-artifact-lab-adapter-provider`
7. `$b24-real-build-test-artifact-lab-workflow-runtime`
8. `$b24-real-build-test-artifact-lab-lineage-reconciliation`
9. `$b24-real-build-test-artifact-lab-security-policy`
10. `$b24-real-build-test-artifact-lab-human-approval`
11. `$b24-real-build-test-artifact-lab-observability-economics`
12. `$b24-real-build-test-artifact-lab-corpus-benchmark`
13. `$b24-real-build-test-artifact-lab-failure-recovery`
14. `$b24-real-build-test-artifact-lab-integration-api`
15. `$b24-real-build-test-artifact-lab-lifecycle-recertification`
16. `$b24-real-build-test-artifact-lab-certification-gate`

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
